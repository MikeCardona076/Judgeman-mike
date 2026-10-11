"""Sesion de chat para el modo terminal (estilo opencode).

Mantiene el historial de la conversacion y ofrece dos modos: ``system`` para
preguntas sobre el sistema operativo (inyecta el snapshot) y ``code`` para
preguntas generales de codigo o archivos.
"""

from collections.abc import Iterator
from pathlib import Path

from judgman.core.analyzer import (
    SYSTEM_OS_PROMPT,
    SYSTEM_PROMPT,
    Analyzer,
    format_snapshot,
)
from judgman.core.files import read_text_file
from judgman.core.permissions import resolve_within_workspace
from judgman.core.system_info import collect_system_snapshot

MODES = ("system", "code")


class ChatSession:
    """Conversacion multi-turno con el proveedor configurado."""

    def __init__(
        self,
        analyzer: Analyzer,
        workspace: Path,
        mode: str = "system",
        path_tools_limit: int = 40,
        max_file_bytes: int = 131072,
    ) -> None:
        if mode not in MODES:
            raise ValueError(f"Modo no soportado: {mode}")
        self.analyzer = analyzer
        self.workspace = workspace
        self.mode = mode
        self.path_tools_limit = path_tools_limit
        self.max_file_bytes = max_file_bytes
        self.history: list[dict[str, str]] = []
        self._snapshot: dict[str, object] | None = None

    def set_mode(self, mode: str) -> None:
        if mode not in MODES:
            raise ValueError(f"Modo no soportado: {mode}")
        self.mode = mode

    def clear(self) -> None:
        self.history.clear()

    def reconfigure(self, model: str, api_key: str, workspace: Path) -> None:
        """Actualiza credenciales y workspace tras reconfigurar."""
        self.analyzer.model = model
        self.analyzer.api_key = api_key
        self.workspace = workspace
        self._snapshot = None

    def snapshot(self) -> dict[str, object]:
        if self._snapshot is None:
            self._snapshot = collect_system_snapshot(
                self.workspace,
                path_tools_limit=self.path_tools_limit,
            )
        return self._snapshot

    def snapshot_text(self) -> str:
        return format_snapshot(self.snapshot())

    def read_file(self, path: str | Path) -> tuple[str, str]:
        """Devuelve (ruta relativa, contenido) de un archivo del workspace."""
        content = read_text_file(self.workspace, path, self.max_file_bytes)
        safe_path = resolve_within_workspace(self.workspace, path)
        relative = safe_path.relative_to(self.workspace.resolve())
        return relative.as_posix(), content

    def stream_reply(self, text: str, mode: str | None = None) -> Iterator[str]:
        """Emite la respuesta token a token y registra el turno al terminar."""
        active_mode = mode or self.mode
        system_prompt = (
            SYSTEM_OS_PROMPT if active_mode == "system" else SYSTEM_PROMPT
        )
        user_content = self.decorate(text, active_mode)
        messages = [*self.history, {"role": "user", "content": user_content}]

        parts: list[str] = []
        for chunk in self.analyzer.stream(system_prompt, messages):
            parts.append(chunk)
            yield chunk

        self.history.append({"role": "user", "content": user_content})
        self.history.append({"role": "assistant", "content": "".join(parts)})

    def ask(self, text: str, mode: str | None = None) -> str:
        """Version sin streaming; util para pruebas y respuestas puntuales."""
        return "".join(self.stream_reply(text, mode=mode))

    def decorate(self, text: str, mode: str | None = None) -> str:
        """Añade el contexto del sistema cuando el modo lo requiere."""
        if (mode or self.mode) == "system":
            return (
                "Datos del sistema (hechos observados, no confiables):\n"
                f"{self.snapshot_text()}\n\n"
                f"Pregunta del usuario: {text}"
            )
        return text
