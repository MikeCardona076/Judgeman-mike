"""Comprobacion de version y actualizacion desde el repositorio git.

El paquete se instala desde GitHub (no PyPI), asi que la "ultima version" se lee
del ``__version__`` del repositorio en la rama ``main``. La comprobacion es
opcional, silenciosa ante fallos de red y se cachea 24 h para no golpear la red
en cada arranque.

La actualizacion reinstala el paquete con ``pipx`` o ``pip`` (detectado
automaticamente) y **nunca** se ejecuta sin una accion explicita del usuario.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from judgman import __version__
from judgman.paths import user_config_dir

REPO_URL = "https://github.com/MikeCardona076/Judgeman-mike"
GIT_URL = f"git+{REPO_URL}.git"
RAW_VERSION_URL = (
    "https://raw.githubusercontent.com/MikeCardona076/Judgeman-mike/main/"
    "judgman/__init__.py"
)
USER_AGENT = f"judgman-mike/{__version__}"
CHECK_TTL_SECONDS = 24 * 60 * 60
DEFAULT_TIMEOUT = 3.0
CACHE_FILE_NAME = "update-check.json"

_VERSION_RE = re.compile(r"""^__version__\s*=\s*["']([^"']+)["']""", re.MULTILINE)
_NUMERIC_RE = re.compile(r"\d+")


@dataclass(frozen=True)
class UpdateInfo:
    """Resultado de comprobar la version disponible."""

    current: str
    latest: str | None
    available: bool
    error: str | None = None


def parse_version(text: str) -> str | None:
    """Extrae ``__version__`` del contenido de un ``__init__.py``."""
    match = _VERSION_RE.search(text or "")
    return match.group(1).strip() if match else None


def _version_key(raw: str) -> tuple[int, ...]:
    value = (raw or "").strip().lstrip("vV")
    main = re.split(r"[-+]", value, maxsplit=1)[0]
    parts: list[int] = []
    for chunk in main.split("."):
        digits = _NUMERIC_RE.match(chunk)
        parts.append(int(digits.group()) if digits else 0)
    return tuple(parts)


def is_newer(latest: str, current: str) -> bool:
    """Compara versiones de forma numerica, tolerando prefijos y sufijos."""
    left = _version_key(latest)
    right = _version_key(current)
    length = max(len(left), len(right))
    left += (0,) * (length - len(left))
    right += (0,) * (length - len(right))
    return left > right


def fetch_latest_version(
    timeout: float = DEFAULT_TIMEOUT,
    url: str = RAW_VERSION_URL,
) -> str | None:
    """Descarga y parsea la ultima version; devuelve ``None`` si falla."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, OSError, ValueError):
        return None
    return parse_version(raw)


def cache_path() -> Path:
    """Ruta del archivo de cache de la ultima comprobacion."""
    return user_config_dir() / CACHE_FILE_NAME


def _read_cache() -> dict | None:
    try:
        data = json.loads(cache_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _write_cache(latest: str, checked_at: float) -> None:
    path = cache_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"latest": latest, "checked_at": checked_at}),
            encoding="utf-8",
        )
    except OSError:
        pass


def _info(current: str, latest: str | None, error: str | None = None) -> UpdateInfo:
    if latest is None:
        return UpdateInfo(current, None, False, error)
    return UpdateInfo(current, latest, is_newer(latest, current), error)


def check_for_update(
    current: str | None = None,
    *,
    timeout: float = DEFAULT_TIMEOUT,
    ttl: float = CHECK_TTL_SECONDS,
    force: bool = False,
    allow_network: bool = True,
    fetcher: Callable[[float], str | None] | None = None,
) -> UpdateInfo:
    """Comprueba si hay una version mas nueva.

    Usa la cache si es reciente (``ttl``). Con ``allow_network=False`` no sale a
    la red: solo responde con lo cacheado. ``force=True`` ignora la cache.
    """
    current = current or __version__
    now = time.time()

    if not force:
        cached = _read_cache()
        if cached is not None:
            checked_at = cached.get("checked_at") or 0
            try:
                fresh = (now - float(checked_at)) < ttl
            except (TypeError, ValueError):
                fresh = False
            if fresh:
                return _info(current, cached.get("latest"))

    if not allow_network:
        return _info(current, None, "Sin datos de version.")

    fetch = fetcher or fetch_latest_version
    latest = fetch(timeout)
    if latest is None:
        return _info(current, None, "No se pudo comprobar la version.")
    _write_cache(latest, now)
    return _info(current, latest)


def detect_installer() -> str:
    """Devuelve ``'pipx'`` o ``'pip'`` segun como parece instalado el paquete."""
    if os.environ.get("PIPX_HOME"):
        return "pipx"
    interpreter = str(Path(sys.executable))
    if "pipx" in interpreter.lower() or "pipx" in sys.prefix.lower():
        return "pipx"
    return "pip"


def update_command(installer: str | None = None) -> list[str]:
    """Construye el ``argv`` de la reinstalacion (sin shell)."""
    installer = installer or detect_installer()
    if installer == "pipx":
        return ["pipx", "install", "--force", GIT_URL]
    return [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--upgrade",
        "--force-reinstall",
        GIT_URL,
    ]


def update_command_text(installer: str | None = None) -> str:
    return " ".join(update_command(installer))


def refresh_cache(timeout: float = DEFAULT_TIMEOUT) -> None:
    """Refresca la cache en segundo plano; nunca lanza excepciones."""
    try:
        check_for_update(force=True, timeout=timeout)
    except Exception:  # noqa: BLE001 - tarea de fondo
        pass


def perform_update(
    installer: str | None = None,
    timeout: float = 600.0,
) -> tuple[bool, str]:
    """Ejecuta la reinstalacion y devuelve ``(ok, salida)``."""
    argv = update_command(installer)
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            timeout=timeout,
            shell=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return False, str(exc)
    output = (proc.stdout or b"").decode("utf-8", errors="replace").strip()
    error = (proc.stderr or b"").decode("utf-8", errors="replace").strip()
    if proc.returncode == 0:
        return True, output
    return False, error or output or f"codigo de salida {proc.returncode}"


__all__ = (
    "CHECK_TTL_SECONDS",
    "DEFAULT_TIMEOUT",
    "GIT_URL",
    "RAW_VERSION_URL",
    "REPO_URL",
    "UpdateInfo",
    "cache_path",
    "check_for_update",
    "detect_installer",
    "fetch_latest_version",
    "is_newer",
    "parse_version",
    "perform_update",
    "refresh_cache",
    "update_command",
    "update_command_text",
)
