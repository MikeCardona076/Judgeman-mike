"""Recolección de datos benignos del sistema para responder preguntas.

Solo se usan APIs de la librería estándar y lecturas; nunca se ejecutan
comandos de shell, nunca se leen valores de variables de entorno y nunca se
incluye información identificable (usuario, hostname, rutas absolutas).
"""

import os
import platform
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

_SENSITIVE_ENV_MARKERS = (
    "TOKEN",
    "SECRET",
    "KEY",
    "PASSWORD",
    "PASSWD",
    "CREDENTIAL",
    "AUTH",
    "API",
    "COOKIE",
    "SESSION",
    "PRIVATE",
)
_CACHE_TTL_SECONDS = 30.0
_cache: tuple[float, str, dict[str, object]] | None = None


def _memory_info() -> dict[str, int]:
    """Memoria total/disponible en MiB, best-effort y sin dependencias extra."""
    try:
        if sys.platform.startswith("win"):
            return _windows_memory()
        return _unix_memory()
    except (OSError, ValueError, AttributeError):
        return {}


def _windows_memory() -> dict[str, int]:
    import ctypes

    class _MemoryStatusEx(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    status = _MemoryStatusEx()
    status.dwLength = ctypes.sizeof(_MemoryStatusEx)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        return {}
    return {
        "memory_total_mb": int(status.ullTotalPhys // (1024 * 1024)),
        "memory_available_mb": int(status.ullAvailPhys // (1024 * 1024)),
    }


def _unix_memory() -> dict[str, int]:
    page_size = os.sysconf("SC_PAGE_SIZE")
    total = os.sysconf("SC_PHYS_PAGES") * page_size
    available = os.sysconf("SC_AVPHYS_PAGES") * page_size
    return {
        "memory_total_mb": int(total // (1024 * 1024)),
        "memory_available_mb": int(available // (1024 * 1024)),
    }


def _safe_env_names() -> list[str]:
    """Solo los nombres de variables de entorno, filtrando marcadores sensibles."""
    names: list[str] = []
    for name in os.environ:
        upper = name.upper()
        if any(marker in upper for marker in _SENSITIVE_ENV_MARKERS):
            continue
        names.append(name)
    return sorted(names)


def _path_tools(limit: int) -> list[str]:
    """Nombres de ejecutables hallados en el PATH, sin rutas completas."""
    tools: set[str] = set()
    for entry in os.environ.get("PATH", "").split(os.pathsep):
        if not entry:
            continue
        directory = Path(entry)
        try:
            if not directory.is_dir():
                continue
            for child in directory.iterdir():
                try:
                    if child.is_file():
                        tools.add(child.stem.casefold())
                except OSError:
                    continue
        except OSError:
            continue
        if len(tools) >= limit:
            break
    return sorted(tools)[:limit]


def collect_system_snapshot(
    workspace: Path | None = None,
    path_tools_limit: int = 40,
    use_cache: bool = True,
) -> dict[str, object]:
    """Devuelve un snapshot no sensible del sistema, apto para enviar al LLM."""
    global _cache
    key = str(workspace) if workspace is not None else ""
    if use_cache and _cache is not None:
        cached_at, cached_key, cached_value = _cache
        if cached_key == key and (time.monotonic() - cached_at) < _CACHE_TTL_SECONDS:
            return dict(cached_value)

    now = datetime.now().astimezone()
    snapshot: dict[str, object] = {
        "os_name": platform.system(),
        "os_release": platform.release(),
        "os_version": platform.version(),
        "architecture": platform.machine(),
        "processor": platform.processor() or "desconocido",
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "cpu_count": os.cpu_count(),
        "timezone_name": now.tzname() or "desconocida",
        "utc_offset": now.strftime("%z"),
        "local_time": now.strftime("%Y-%m-%d %H:%M:%S"),
        "env_var_names": _safe_env_names(),
        "path_tools": _path_tools(path_tools_limit),
    }
    snapshot.update(_memory_info())

    if workspace is not None:
        try:
            usage = shutil.disk_usage(str(workspace))
            snapshot["disk_total_gb"] = round(usage.total / (1024**3), 1)
            snapshot["disk_free_gb"] = round(usage.free / (1024**3), 1)
        except OSError:
            pass

    if use_cache:
        _cache = (time.monotonic(), key, dict(snapshot))
    return snapshot
