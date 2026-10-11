# judgman/core/permissions.py
"""Validación de rutas para limitar el acceso al directorio autorizado."""

from pathlib import Path


def resolve_within_workspace(base_dir: Path, candidate: str | Path) -> Path:
    """Resuelve una ruta y rechaza escapes, incluidos los causados por symlinks.

    Las rutas relativas se interpretan desde ``base_dir``. La función solo
    normaliza y valida rutas; no abre ni modifica archivos.
    """
    root = base_dir.expanduser().resolve()
    path = Path(candidate).expanduser()
    resolved = (path if path.is_absolute() else root / path).resolve()

    if not resolved.is_relative_to(root):
        raise PermissionError(
            f"La ruta está fuera del directorio autorizado: {candidate}"
        )
    return resolved
