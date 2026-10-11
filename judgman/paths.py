"""Ubicaciones de configuracion del usuario, sin dependencias externas."""

import os
from collections.abc import Mapping
from pathlib import Path

_APP_DIR_NAME = "judgman"
_CONFIG_FILE_NAME = "config.env"


def user_config_dir(
    env: Mapping[str, str] | None = None,
    platform: str | None = None,
) -> Path:
    """Directorio de configuracion del usuario segun el sistema operativo."""
    env = os.environ if env is None else env
    platform = os.name if platform is None else platform

    if platform == "nt":
        base = env.get("APPDATA")
        root = Path(base) if base else Path.home() / "AppData" / "Roaming"
    else:
        base = env.get("XDG_CONFIG_HOME")
        if base:
            root = Path(base)
        else:
            home = env.get("HOME")
            root = Path(home) / ".config" if home else Path.home() / ".config"
    return root / _APP_DIR_NAME


def user_config_path() -> Path:
    """Ruta del archivo ``config.env`` del usuario."""
    return user_config_dir() / _CONFIG_FILE_NAME
