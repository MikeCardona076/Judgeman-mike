"""Lectura de solo lectura de archivos confinados al workspace.

Compartido por el scanner automatico y por el chat de terminal para aplicar
las mismas reglas: ruta dentro del workspace, exclusion de archivos sensibles,
limite de tamano y deteccion de binarios.
"""

from pathlib import Path

from judgman.core.permissions import resolve_within_workspace

_SENSITIVE_NAMES = {
    ".env",
    "id_rsa",
    "id_ed25519",
    "credentials",
    "credentials.json",
    "secrets.json",
}
_SENSITIVE_DIRECTORIES = {
    ".aws",
    ".azure",
    ".gnupg",
    ".ssh",
    "credentials",
    "secrets",
}


class FileSkipped(Exception):
    """El archivo no debe analizarse; ``detail`` explica el motivo."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


def is_sensitive(path: Path) -> bool:
    """Heuristica que marca rutas con nombres o extensiones de credenciales."""
    name = path.name.casefold()
    return (
        name in _SENSITIVE_NAMES
        or name.startswith(".env.")
        or name in {".netrc", ".npmrc", ".pypirc", "authorized_keys"}
        or name.startswith("id_")
        or path.suffix.casefold() in {".key", ".pem", ".p12", ".pfx"}
        or any(part.casefold() in _SENSITIVE_DIRECTORIES for part in path.parts)
        or any(
            term in part.casefold()
            for part in path.parts
            for term in ("secret", "credential", "password")
        )
    )


def read_text_file(workspace: Path, path: str | Path, max_bytes: int) -> str:
    """Lee un archivo de texto validado dentro del workspace.

    Raises:
        PermissionError: si la ruta queda fuera del workspace.
        ValueError: si la ruta ya no es un archivo regular.
        FileSkipped: si el archivo es sensible, demasiado grande o binario.
        UnicodeError: si el contenido no es UTF-8 valido.
    """
    safe_path = resolve_within_workspace(workspace, path)
    if not safe_path.is_file():
        raise ValueError("El evento ya no apunta a un archivo regular")
    if is_sensitive(safe_path.relative_to(workspace)):
        raise FileSkipped("Archivo potencialmente sensible excluido del analisis.")

    with safe_path.open("rb") as file_handle:
        raw_content = file_handle.read(max_bytes + 1)
    if len(raw_content) > max_bytes:
        raise FileSkipped(f"Archivo mayor que el limite de {max_bytes} bytes.")
    if b"\0" in raw_content:
        raise FileSkipped("Archivo binario excluido del analisis.")
    return raw_content.decode("utf-8")
