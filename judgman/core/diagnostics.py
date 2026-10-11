"""Recoleccion de diagnostico del equipo en modo solo lectura.

Fuentes:

* ``psutil`` (extra ``monitor``) para puertos, procesos y conexiones.
* Comandos del sistema de solo lectura (``netsh``/``sc``/``uwaf``/``systemctl``),
  ejecutados sin shell y con timeout, para firewall y servicios.
* Lecturas directas (registro de Windows, carpeta de inicio, archivo ``hosts``)
  para el arranque automatico y el secuestro de hosts/DNS/proxy.

Nunca se modifica el sistema: la reparacion vive en :mod:`judgman.core.actions`
y siempre exige confirmacion. El resultado se puede redactar antes de enviarlo
al proveedor.
"""

from __future__ import annotations

import os
import platform
import re
import socket
import time
from pathlib import Path
from typing import Callable

from judgman.core.actions import CommandResult, default_command_runner

try:  # pragma: no cover - depende del entorno
    import psutil
except ImportError:  # pragma: no cover
    psutil = None  # type: ignore[assignment]

IS_WINDOWS = platform.system() == "Windows"
PSUTIL_HINT = "psutil no instalado: pip install 'judgman-mike[monitor]'"
PSUTIL_COMMAND_HINT = "Se requieren permisos elevados para ver el PID de algunos puertos."

_COMMAND_TIMEOUT = 8.0
_CACHE_TTL_SECONDS = 15.0
_cache: tuple[float, str, dict[str, object]] | None = None

_command_runner: Callable[[list[str], float], CommandResult] = default_command_runner


def set_command_runner(
    runner: Callable[[list[str], float], CommandResult] | None
) -> None:
    """Sustituye el ejecutor de comandos (usado por las pruebas)."""
    global _command_runner
    _command_runner = runner or default_command_runner


def _run(argv: list[str], timeout: float = 8.0) -> CommandResult:
    return _command_runner(argv, timeout)


def _unavailable(note: str) -> dict[str, object]:
    return {"available": False, "note": note}


# --------------------------------------------------------------------- psutil
def _process_name(pid: int | None, cache: dict[int, str]) -> str:
    if pid is None or psutil is None:
        return "(desconocido)"
    if pid in cache:
        return cache[pid]
    try:
        name = psutil.Process(pid).name()
    except Exception:  # psutil.Error o acceso denegado
        name = "(sin acceso)"
    cache[pid] = name
    return name


def listening_ports() -> dict:
    if psutil is None:
        return {"available": False, "note": PSUTIL_HINT, "entries": []}
    try:
        connections = psutil.net_connections(kind="inet")
    except Exception as exc:  # pragma: no cover - defensivo
        return {"available": False, "note": f"psutil fallo: {exc}", "entries": []}

    cache: dict[int, str] = {}
    entries: list[dict[str, object]] = []
    for conn in connections:
        if conn.status != psutil.CONN_LISTEN:
            continue
        laddr = conn.laddr
        entries.append(
            {
                "port": laddr.port,
                "address": laddr.ip,
                "protocol": "TCP" if conn.type == socket.SOCK_STREAM else "UDP",
                "pid": conn.pid,
                "process": _process_name(conn.pid, cache),
            }
        )
    entries.sort(key=lambda item: (item["port"], item["protocol"]))
    note = None
    if any(item["pid"] is None for item in entries):
        note = "Algunos PID no se pudieron resolver (permisos)."
    return {"available": True, "note": note, "entries": entries}


def check_port(port: int, ports: dict | None = None) -> dict:
    """Diagnostica si un puerto esta a la escucha y quien lo ocupa."""
    if ports is None:
        ports = listening_ports()
    listeners = [
        entry
        for entry in ports.get("entries", [])
        if entry.get("port") == port
    ]
    if listeners:
        verdict = "listening"
        detail = "Algo ya esta escuchando en ese puerto."
    else:
        verdict = "not_listening"
        detail = (
            "Nada escucha en ese puerto: el servicio no esta corriendo o usa "
            "otro puerto. Un firewall no puede 'bloquear' un puerto donde nada "
            "escucha."
        )
    return {
        "port": port,
        "verdict": verdict,
        "detail": detail,
        "listeners": listeners,
        "ports_available": ports.get("available", False),
        "note": ports.get("note"),
    }


def top_processes(limit: int = 12, sample_seconds: float = 0.1) -> dict:
    if psutil is None:
        return {"available": False, "note": PSUTIL_HINT, "entries": []}
    try:
        processes = list(
            psutil.process_iter(
                ["pid", "name", "username", "memory_percent", "exe"]
            )
        )
    except Exception as exc:  # pragma: no cover - defensivo
        return {"available": False, "note": f"psutil fallo: {exc}", "entries": []}

    for proc in processes:
        try:
            proc.cpu_percent(None)
        except Exception:
            continue
    time.sleep(sample_seconds)

    rows: list[dict[str, object]] = []
    for proc in processes:
        try:
            info = proc.info
            cpu = round(proc.cpu_percent(None), 1)
        except Exception:
            continue
        rows.append(
            {
                "pid": info.get("pid"),
                "name": info.get("name"),
                "user": info.get("username"),
                "cpu_percent": cpu,
                "mem_percent": round(info.get("memory_percent") or 0.0, 1),
                "exe": info.get("exe"),
            }
        )
    rows.sort(
        key=lambda row: (row["cpu_percent"], row["mem_percent"]), reverse=True
    )
    return {"available": True, "note": None, "entries": rows[:limit]}


def connections(limit: int = 20) -> dict:
    if psutil is None:
        return {"available": False, "note": PSUTIL_HINT, "entries": []}
    try:
        raw = psutil.net_connections(kind="inet")
    except Exception as exc:  # pragma: no cover - defensivo
        return {"available": False, "note": f"psutil fallo: {exc}", "entries": []}

    cache: dict[int, str] = {}
    entries: list[dict[str, object]] = []
    for conn in raw:
        if conn.status not in (psutil.CONN_ESTABLISHED, psutil.CONN_SYN_SENT):
            continue
        if not conn.raddr:
            continue
        entries.append(
            {
                "local_port": conn.laddr.port,
                "remote": f"{conn.raddr.ip}:{conn.raddr.port}",
                "status": conn.status,
                "pid": conn.pid,
                "process": _process_name(conn.pid, cache),
            }
        )
    entries.sort(key=lambda item: item["remote"])
    return {"available": True, "note": None, "entries": entries[:limit]}


def startup_entries(limit: int = 20) -> dict:
    if IS_WINDOWS:
        return _windows_startup(limit)
    return _posix_startup(limit)


def _windows_startup(limit: int) -> dict:
    try:
        import winreg
    except ImportError:  # pragma: no cover - Windows garantiza winreg
        return {"available": False, "note": "winreg no disponible.", "entries": []}

    locations = (
        (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run"),
        (
            winreg.HKEY_LOCAL_MACHINE,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
        ),
    )
    entries: list[dict[str, object]] = []
    for root, path in locations:
        try:
            with winreg.OpenKey(root, path) as key:
                index = 0
                while len(entries) < limit:
                    try:
                        name, value, _ = winreg.EnumValue(key, index)
                    except OSError:
                        break
                    entries.append({"source": path, "name": name, "value": value})
                    index += 1
        except OSError:
            continue
    return {"available": True, "note": None, "entries": entries}


def _posix_startup(limit: int) -> dict:
    directories = (
        Path.home() / ".config" / "autostart",
        Path("/etc/xdg/autostart"),
    )
    entries: list[dict[str, object]] = []
    for directory in directories:
        if not directory.is_dir():
            continue
        for child in sorted(directory.glob("*.desktop")):
            if len(entries) >= limit:
                break
            try:
                text = child.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            exec_line = ""
            for line in text.splitlines():
                if line.startswith("Exec="):
                    exec_line = line[len("Exec=") :].strip()
                    break
            entries.append({"source": str(directory), "name": child.name, "value": exec_line})
    return {"available": True, "note": None, "entries": entries[:limit]}


def services(limit: int = 40) -> dict:
    if IS_WINDOWS and psutil is not None:
        return _windows_services_psutil(limit)
    if IS_WINDOWS:
        result = _run(["sc", "query", "type=", "service", "state=", "all"])
    else:
        result = _run(
            [
                "systemctl",
                "--no-pager",
                "--no-legend",
                "list-units",
                "--type=service",
                "--all",
            ]
        )
    if not result.ok and not result.output:
        return {
            "available": False,
            "note": result.error or "No se pudo consultar los servicios.",
            "entries": [],
        }
    entries = (
        _parse_sc_services(result.output)
        if IS_WINDOWS
        else _parse_systemctl_services(result.output)
    )
    stopped = [entry for entry in entries if not _is_running(entry["state"])]
    return {
        "available": True,
        "note": result.error,
        "entries": (stopped or entries)[:limit],
    }


def _windows_services_psutil(limit: int) -> dict:
    entries: list[dict[str, object]] = []
    try:
        iterator = psutil.win_service_iter()
    except Exception as exc:  # pragma: no cover - defensivo
        return {"available": False, "note": f"psutil fallo: {exc}", "entries": []}
    for service in iterator:
        try:
            info = service.as_dict()
        except Exception:  # pragma: no cover - acceso denegado
            continue
        entries.append(
            {
                "name": info.get("name"),
                "display": info.get("display_name"),
                "state": str(info.get("status") or "").lower(),
                "start_type": str(info.get("start_type") or "").lower(),
            }
        )
    stopped = [entry for entry in entries if not _is_running(entry["state"])]
    return {"available": True, "note": None, "entries": (stopped or entries)[:limit]}


def _is_running(state: str) -> bool:
    value = state.casefold()
    return "running" in value or "ejecuc" in value


def _parse_sc_services(output: str) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    name: str | None = None
    for line in output.splitlines():
        stripped = line.strip()
        upper = stripped.upper()
        if upper.startswith("SERVICE_NAME:") or upper.startswith("NOMBRE_SERVICIO:"):
            name = stripped.split(":", 1)[1].strip()
        elif (upper.startswith("STATE") or upper.startswith("ESTADO")) and ":" in stripped:
            value = stripped.split(":", 1)[1].strip()
            if name is not None:
                entries.append({"name": name, "state": value})
                name = None
    return entries


def _parse_systemctl_services(output: str) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    for line in output.splitlines():
        parts = line.split()
        if len(parts) < 4:
            continue
        entries.append(
            {
                "name": parts[0].lstrip("\u25cf").strip(),
                "state": parts[3],
            }
        )
    return entries


def firewall_status() -> dict:
    if IS_WINDOWS:
        result = _run(["netsh", "advfirewall", "show", "allprofiles"])
    else:
        result = _run(["ufw", "status"])
        if not result.ok and not result.output:
            result = _run(["firewall-cmd", "--state"])
    if not result.ok and not result.output:
        return {
            "available": False,
            "note": result.error or "No se pudo consultar el firewall.",
            "output": "",
        }
    return {"available": True, "note": result.error, "output": result.output.strip()}


def hosts_dns_proxy() -> dict:
    if IS_WINDOWS:
        hosts_path = (
            Path(os.environ.get("SystemRoot", r"C:\Windows"))
            / "System32"
            / "drivers"
            / "etc"
            / "hosts"
        )
    else:
        hosts_path = Path("/etc/hosts")

    hosts_lines: list[str] = []
    try:
        for line in hosts_path.read_text(encoding="utf-8", errors="replace").splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                hosts_lines.append(stripped)
            if len(hosts_lines) >= 40:
                break
    except OSError:
        pass

    proxy: dict[str, str] = {}
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY"):
        value = os.environ.get(name) or os.environ.get(name.lower())
        if value:
            proxy[name] = _redact_proxy(value)

    return {
        "hosts_file": str(hosts_path),
        "hosts_entries": hosts_lines,
        "proxy_env": proxy,
    }


def _redact_proxy(value: str) -> str:
    return re.sub(r"://[^@/]+@", "://<credenciales>@", value)


def collect_diagnostics(workspace: Path | None = None, use_cache: bool = True) -> dict:
    """Reune todas las secciones de diagnostico (con cache de pocos segundos)."""
    global _cache
    key = str(workspace) if workspace is not None else ""
    if use_cache and _cache is not None:
        cached_at, cached_key, cached_value = _cache
        if cached_key == key and (time.monotonic() - cached_at) < _CACHE_TTL_SECONDS:
            return dict(cached_value)

    data = {
        "listening_ports": listening_ports(),
        "processes": top_processes(),
        "connections": connections(),
        "startup": startup_entries(),
        "services": services(),
        "firewall": firewall_status(),
        "hosts": hosts_dns_proxy(),
    }
    if use_cache:
        _cache = (time.monotonic(), key, dict(data))
    return data


def render_bundle(data: dict, redact: bool = True, max_chars: int = 4000) -> str:
    """Convierte el diagnostico en texto legible y acotado para el modelo."""
    lines: list[str] = []

    ports = data.get("listening_ports", {})
    lines.append("## Puertos a la escucha")
    if not ports.get("available"):
        lines.append(f"(no disponible) {ports.get('note') or ''}".strip())
    else:
        for entry in ports.get("entries", [])[:30]:
            lines.append(
                f"- {entry['protocol']} {entry['address']}:{entry['port']} "
                f"PID {entry['pid']} ({entry['process']})"
            )
        if not ports.get("entries"):
            lines.append("- (ninguno)")

    procs = data.get("processes", {})
    lines.append("\n## Procesos con mas carga")
    if not procs.get("available"):
        lines.append(f"(no disponible) {procs.get('note') or ''}".strip())
    else:
        for entry in procs.get("entries", [])[:12]:
            lines.append(
                f"- PID {entry['pid']} {entry['name']} cpu={entry['cpu_percent']}% "
                f"mem={entry['mem_percent']}% user={entry['user']} exe={entry['exe']}"
            )

    conns = data.get("connections", {})
    lines.append("\n## Conexiones salientes establecidas")
    if not conns.get("available"):
        lines.append(f"(no disponible) {conns.get('note') or ''}".strip())
    else:
        for entry in conns.get("entries", [])[:15]:
            lines.append(
                f"- {entry['remote']} ({entry['status']}) PID {entry['pid']} "
                f"({entry['process']})"
            )
        if not conns.get("entries"):
            lines.append("- (ninguna)")

    startup = data.get("startup", {})
    lines.append("\n## Arranque automatico")
    if not startup.get("available"):
        lines.append(f"(no disponible) {startup.get('note') or ''}".strip())
    else:
        for entry in startup.get("entries", [])[:15]:
            lines.append(f"- {entry['name']}: {entry['value']} [{entry['source']}]")
        if not startup.get("entries"):
            lines.append("- (ninguno)")

    svc = data.get("services", {})
    lines.append("\n## Servicios detenidos o relevantes")
    if not svc.get("available"):
        lines.append(f"(no disponible) {svc.get('note') or ''}".strip())
    else:
        for entry in svc.get("entries", [])[:20]:
            lines.append(f"- {entry['name']}: {entry['state']}")

    fw = data.get("firewall", {})
    lines.append("\n## Firewall")
    if not fw.get("available"):
        lines.append(f"(no disponible) {fw.get('note') or ''}".strip())
    else:
        output = (fw.get("output") or "").splitlines()
        lines.extend(f"- {line.strip()}" for line in output[:25] if line.strip())

    hosts = data.get("hosts", {})
    lines.append("\n## hosts / proxy")
    if hosts.get("hosts_entries"):
        for entry in hosts["hosts_entries"][:20]:
            lines.append(f"- hosts: {entry}")
    else:
        lines.append("- hosts: (sin entradas relevantes)")
    if hosts.get("proxy_env"):
        for name, value in hosts["proxy_env"].items():
            lines.append(f"- {name}={value}")

    text = "\n".join(lines)
    if redact:
        text = redact_text(text)
    if len(text) > max_chars:
        text = text[:max_chars] + "\n... (recortado)"
    return text


def security_bundle(data: dict, workspace: Path | None = None) -> str:
    """Contexto reducido para el modo de seguridad: puertos y conexiones."""
    subset = {
        "listening_ports": data.get("listening_ports", {}),
        "connections": data.get("connections", {}),
        "services": data.get("services", {}),
    }
    return render_bundle(subset, redact=True)


def redact_text(text: str) -> str:
    """Oculta el nombre de usuario y la carpeta personal antes de enviar."""
    home = str(Path.home())
    user = os.environ.get("USERNAME") or os.environ.get("USER") or ""
    result = text.replace(home, "~")
    if user:
        result = re.sub(re.escape(user), "<usuario>", result, flags=re.IGNORECASE)
    return result


__all__ = (
    "PSUTIL_HINT",
    "check_port",
    "collect_diagnostics",
    "connections",
    "firewall_status",
    "hosts_dns_proxy",
    "listening_ports",
    "redact_text",
    "render_bundle",
    "security_bundle",
    "services",
    "set_command_runner",
    "startup_entries",
    "top_processes",
)
