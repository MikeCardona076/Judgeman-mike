"""Catalogo cerrado de acciones de reparacion con confirmacion y auditoria.

El modelo nunca ejecuta comandos libres: solo puede proponer acciones mediante
un bloque ```action``` con JSON que se valida contra :data:`ACTION_CATALOG`.
Cada accion se traduce a un ``argv`` sin shell y, antes de ejecutarse, exige la
confirmacion explicita del usuario a traves de un ``confirm`` callback. Toda
propuesta y resultado queda registrado en el log de auditoria.
"""

from __future__ import annotations

import json
import locale
import platform
import re
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

IS_WINDOWS = platform.system() == "Windows"


def _decode(raw: bytes) -> str:
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode(locale.getpreferredencoding(False), errors="replace")


@dataclass(frozen=True)
class CommandResult:
    """Salida de un comando ya ejecutado."""

    argv: tuple[str, ...]
    ok: bool
    output: str
    error: str | None = None


def default_command_runner(
    argv: Sequence[str],
    timeout: float = 30.0,
) -> CommandResult:
    """Ejecuta ``argv`` sin shell y captura la salida de forma robusta."""
    args = list(argv)
    try:
        proc = subprocess.run(
            args,
            capture_output=True,
            timeout=timeout,
            shell=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return CommandResult(tuple(args), False, "", str(exc))
    output = _decode(proc.stdout).strip()
    error = _decode(proc.stderr).strip() or None
    return CommandResult(tuple(args), proc.returncode == 0, output, error)


@dataclass(frozen=True)
class ActionSpec:
    """Accion permitida del catalogo."""

    action_id: str
    title: str
    description: str
    risk: str
    reversible: bool
    required: tuple[str, ...]
    build: Callable[[dict[str, object]], list[str]]


def _require(params: dict[str, object], names: tuple[str, ...]) -> None:
    missing = [name for name in names if name not in params]
    if missing:
        raise ValueError(f"Faltan parametros: {', '.join(missing)}")


def _build_kill_process(params: dict[str, object]) -> list[str]:
    _require(params, ("pid",))
    pid = str(int(params["pid"]))
    if IS_WINDOWS:
        return ["taskkill", "/PID", pid, "/F"]
    return ["kill", "-9", pid]


def _protocol(params: dict[str, object]) -> str:
    return str(params.get("protocol", "TCP")).upper()


def _build_open_firewall_port(params: dict[str, object]) -> list[str]:
    _require(params, ("port",))
    port = str(int(params["port"]))
    protocol = _protocol(params)
    name = str(params.get("name") or f"judgman-allow-{port}")
    if IS_WINDOWS:
        return [
            "netsh",
            "advfirewall",
            "firewall",
            "add",
            "rule",
            f"name={name}",
            "dir=in",
            "action=allow",
            f"protocol={protocol}",
            f"localport={port}",
        ]
    return ["ufw", "allow", f"{port}/{protocol.lower()}"]


def _build_close_firewall_port(params: dict[str, object]) -> list[str]:
    _require(params, ("port",))
    port = str(int(params["port"]))
    protocol = _protocol(params)
    name = str(params.get("name") or f"judgman-allow-{port}")
    if IS_WINDOWS:
        return [
            "netsh",
            "advfirewall",
            "firewall",
            "delete",
            "rule",
            f"name={name}",
        ]
    return ["ufw", "delete", "allow", f"{port}/{protocol.lower()}"]


def _build_service(verb: str) -> Callable[[dict[str, object]], list[str]]:
    def build(params: dict[str, object]) -> list[str]:
        _require(params, ("name",))
        name = str(params["name"])
        if IS_WINDOWS:
            return ["sc", verb, name]
        return ["systemctl", verb, name]

    return build


ACTION_CATALOG: dict[str, ActionSpec] = {
    "kill_process": ActionSpec(
        action_id="kill_process",
        title="Terminar proceso",
        description="Finaliza de forma forzada el proceso indicado por su PID.",
        risk="alto",
        reversible=False,
        required=("pid",),
        build=_build_kill_process,
    ),
    "open_firewall_port": ActionSpec(
        action_id="open_firewall_port",
        title="Permitir puerto en el firewall",
        description="Crea una regla de entrada para permitir el puerto indicado.",
        risk="medio",
        reversible=True,
        required=("port",),
        build=_build_open_firewall_port,
    ),
    "close_firewall_port": ActionSpec(
        action_id="close_firewall_port",
        title="Cerrar puerto en el firewall",
        description="Elimina la regla de entrada que permitia el puerto indicado.",
        risk="bajo",
        reversible=True,
        required=("port",),
        build=_build_close_firewall_port,
    ),
    "start_service": ActionSpec(
        action_id="start_service",
        title="Iniciar servicio",
        description="Inicia el servicio indicado por su nombre.",
        risk="bajo",
        reversible=True,
        required=("name",),
        build=_build_service("start"),
    ),
    "stop_service": ActionSpec(
        action_id="stop_service",
        title="Detener servicio",
        description="Detiene el servicio indicado por su nombre.",
        risk="medio",
        reversible=True,
        required=("name",),
        build=_build_service("stop"),
    ),
    "restart_service": ActionSpec(
        action_id="restart_service",
        title="Reiniciar servicio",
        description="Reinicia el servicio indicado por su nombre.",
        risk="medio",
        reversible=True,
        required=("name",),
        build=_build_service("restart"),
    ),
}


def action_catalog_text() -> str:
    """Lista el catalogo para incluirla en los prompts del modelo."""
    lines: list[str] = []
    for spec in ACTION_CATALOG.values():
        params = ", ".join(spec.required)
        reversible = "reversible" if spec.reversible else "no reversible"
        lines.append(
            f"- {spec.action_id} (parametros: {params}; riesgo "
            f"{spec.risk}, {reversible}): {spec.description}"
        )
    return "\n".join(lines)


_ACTION_BLOCK = re.compile(r"```action\s*(\{.*?\})\s*```", re.DOTALL)


@dataclass(frozen=True)
class ProposedAction:
    """Accion propuesta por el modelo y validada contra el catalogo."""

    action_id: str
    params: dict[str, object]
    reason: str
    spec: ActionSpec

    @property
    def command(self) -> list[str]:
        return self.spec.build(self.params)


def parse_actions(text: str) -> tuple[list[ProposedAction], list[str]]:
    """Extrae y valida las acciones propuestas; devuelve ``(acciones, errores)``."""
    actions: list[ProposedAction] = []
    errors: list[str] = []
    for raw in _ACTION_BLOCK.findall(text):
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            errors.append("Bloque de accion con JSON invalido.")
            continue
        if not isinstance(payload, dict):
            errors.append("El bloque de accion no es un objeto JSON.")
            continue
        action_id = str(payload.get("id", "")).strip()
        spec = ACTION_CATALOG.get(action_id)
        if spec is None:
            errors.append(f"Accion no permitida por el catalogo: {action_id!r}.")
            continue
        params = payload.get("params") or {}
        if not isinstance(params, dict):
            errors.append(f"Parametros invalidos en la accion {action_id}.")
            continue
        missing = [name for name in spec.required if name not in params]
        if missing:
            errors.append(
                f"A la accion {action_id} le faltan parametros: {', '.join(missing)}."
            )
            continue
        try:
            spec.build(params)
        except (ValueError, TypeError) as exc:
            errors.append(f"Parametros invalidos en {action_id}: {exc}")
            continue
        actions.append(
            ProposedAction(
                action_id=action_id,
                params=params,
                reason=str(payload.get("reason", "")).strip(),
                spec=spec,
            )
        )
    return actions, errors


@dataclass(frozen=True)
class ActionResult:
    """Resultado de intentar aplicar una accion."""

    action: ProposedAction
    confirmed: bool
    executed: bool
    ok: bool
    output: str
    error: str | None = None


@dataclass
class ActionRunner:
    """Aplica acciones confirmadas y registra todo en el log de auditoria."""

    confirm: Callable[[ProposedAction], bool]
    audit_path: Path | None = None
    runner: Callable[[Sequence[str], float], CommandResult] = default_command_runner
    timeout: float = 30.0
    _log_lines: list[str] = field(default_factory=list, repr=False)

    def apply(self, action: ProposedAction) -> ActionResult:
        confirmed = bool(self.confirm(action))
        if not confirmed:
            result = ActionResult(action, False, False, False, "", "Cancelado.")
            self._audit(result)
            return result

        try:
            command = self.runner(action.command, self.timeout)
        except Exception as exc:  # noqa: BLE001 - se reporta al usuario
            result = ActionResult(
                action, True, True, False, "", f"Error al ejecutar: {exc}"
            )
            self._audit(result)
            return result

        result = ActionResult(
            action=action,
            confirmed=True,
            executed=True,
            ok=command.ok,
            output=command.output,
            error=command.error,
        )
        self._audit(result)
        return result

    def _audit(self, result: ActionResult) -> None:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": result.action.action_id,
            "params": result.action.params,
            "command": result.action.command,
            "confirmed": result.confirmed,
            "executed": result.executed,
            "ok": result.ok,
            "error": result.error,
        }
        line = json.dumps(entry, ensure_ascii=False)
        self._log_lines.append(line)
        if self.audit_path is None:
            return
        try:
            self.audit_path.parent.mkdir(parents=True, exist_ok=True)
            with self.audit_path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        except OSError:
            pass

    @property
    def log_lines(self) -> list[str]:
        return list(self._log_lines)


__all__ = (
    "ACTION_CATALOG",
    "ActionResult",
    "ActionRunner",
    "ActionSpec",
    "CommandResult",
    "ProposedAction",
    "action_catalog_text",
    "default_command_runner",
    "parse_actions",
)
