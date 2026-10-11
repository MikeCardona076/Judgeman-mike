"""Sesion de chat para el modo terminal.

Mantiene el historial de la conversacion y ofrece tres modos:

* ``diagnose``: problemas del equipo (puertos, procesos, servicios). Inyecta el
  diagnostico observado como contexto.
* ``security``: caza de amenazas. Inyecta el snapshot y un resumen de red.
* ``file``: analisis del contenido de un archivo concreto.
"""

from collections.abc import Callable, Iterator
from pathlib import Path
import time

from judgman.core.actions import ProposedAction, parse_actions
from judgman.core.analyzer import (
    DIAGNOSTIC_PROMPT,
    SECURITY_PROMPT,
    Analyzer,
    format_snapshot,
)
from judgman.core.diagnostics import (
    collect_diagnostics,
    render_bundle,
    security_bundle,
)
from judgman.core.files import read_text_file
from judgman.core.permissions import resolve_within_workspace
from judgman.core.system_info import collect_system_snapshot

MODES = ("diagnose", "security", "file")

_MODE_PROMPTS = {
    "diagnose": DIAGNOSTIC_PROMPT,
    "security": SECURITY_PROMPT,
    "file": SECURITY_PROMPT,
}


class ChatSession:
    """Historial de conversacion, modos y contexto observado."""

    def __init__(
        self,
        analyzer: Analyzer,
        workspace: Path,
        mode: str = "diagnose",
        path_tools_limit: int = 40,
        max_file_bytes: int = 131072,
        diagnostics_provider: Callable[[], dict] | None = None,
    ) -> None:
        if mode not in MODES:
            raise ValueError(f"Modo desconocido: {mode}")
        self.analyzer = analyzer
        self.workspace = workspace
        self.mode = mode
        self.path_tools_limit = path_tools_limit
        self.max_file_bytes = max_file_bytes
        self.history: list[dict[str, str]] = []
        self._snapshot: dict[str, object] | None = None
        self._diagnostics: dict | None = None
        self._diagnostics_provider = diagnostics_provider
        self.last_prompt: str | None = None
        self.last_mode: str | None = None
        self.last_elapsed: float = 0.0
        self.turn_count: int = 0
        self.last_actions: list[ProposedAction] = []
        self.last_action_errors: list[str] = []

    def set_mode(self, mode: str) -> None:
        if mode not in MODES:
            raise ValueError(f"modo desconocido: {mode}")
        self.mode = mode

    def clear(self) -> None:
        self.history = []
        self.last_actions = []
        self.last_action_errors = []

    def reconfigure(self, model: str, api_key: str, workspace: Path) -> None:
        self.analyzer.model = model
        self.analyzer.api_key = api_key
        self.workspace = workspace
        self._snapshot = None
        self._diagnostics = None

    def snapshot(self) -> dict[str, object]:
        if self._snapshot is None:
            self._snapshot = collect_system_snapshot(
                self.workspace,
                path_tools_limit=self.path_tools_limit,
            )
        return self._snapshot

    def snapshot_text(self) -> str:
        return format_snapshot(self.snapshot())

    def diagnostics(self, refresh: bool = False) -> dict:
        if self._diagnostics is None or refresh:
            if self._diagnostics_provider is not None:
                self._diagnostics = self._diagnostics_provider()
            else:
                self._diagnostics = collect_diagnostics(self.workspace)
        return self._diagnostics

    def diagnostics_text(self, refresh: bool = False) -> str:
        return render_bundle(self.diagnostics(refresh=refresh))

    def security_text(self, refresh: bool = False) -> str:
        data = self.diagnostics(refresh=refresh)
        return (
            "Datos del sistema (hechos observados, no confiables):\n"
            f"{self.snapshot_text()}\n\n"
            "Resumen de red (hechos observados, no confiables):\n"
            f"{security_bundle(data)}"
        )

    def read_file(self, path: str | Path) -> tuple[str, str]:
        content = read_text_file(self.workspace, path, self.max_file_bytes)
        safe_path = resolve_within_workspace(self.workspace, path)
        relative = safe_path.relative_to(self.workspace.resolve())
        return relative.as_posix(), content

    def stream_reply(self, text: str, mode: str | None = None) -> Iterator[str]:
        """Emite la respuesta token a token y registra el turno al terminar."""
        active_mode = mode or self.mode
        system_prompt = _MODE_PROMPTS.get(active_mode, SECURITY_PROMPT)
        user_content = self.decorate(text, active_mode)
        messages = [*self.history, {"role": "user", "content": user_content}]

        parts: list[str] = []
        started = time.perf_counter()
        for chunk in self.analyzer.stream(system_prompt, messages):
            parts.append(chunk)
            yield chunk

        self.last_elapsed = time.perf_counter() - started
        answer = "".join(parts)
        self.history.append({"role": "user", "content": user_content})
        self.history.append({"role": "assistant", "content": answer})
        self.last_prompt = text
        self.last_mode = active_mode
        self.last_actions, self.last_action_errors = parse_actions(answer)
        self.turn_count += 1

    def ask(self, text: str, mode: str | None = None) -> str:
        """Version sin streaming; util para pruebas y respuestas puntuales."""
        return "".join(self.stream_reply(text, mode=mode))

    def decorate(self, text: str, mode: str | None = None) -> str:
        """Añade el contexto observado segun el modo activo."""
        active_mode = mode or self.mode
        if active_mode == "diagnose":
            return (
                "Datos del sistema y diagnostico (hechos observados, no "
                f"confiables):\n{self.diagnostics_text()}\n\n"
                f"Problema o pregunta del usuario: {text}"
            )
        if active_mode == "security":
            return f"{self.security_text()}\n\nConsulta del usuario: {text}"
        return text
