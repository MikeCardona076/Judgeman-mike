# judgman/config.py
"""Carga y valida la configuracion de JudgeMan-Mike.

Precedencia (de mayor a menor): argumentos de CLI, variables de entorno,
archivo ``.env`` del directorio actual, archivo de configuracion del usuario y
valores por defecto.
"""

from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from judgman.paths import user_config_path


class Settings(BaseSettings):
    """Configuracion tipada; los secretos se obtienen exclusivamente del entorno."""

    model_config = SettingsConfigDict(
        env_prefix="JUDGMAN_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    api_key: SecretStr = Field(min_length=1)
    model: str = "openai/gpt-4o-mini"
    workspace: Path = Field(default_factory=Path.cwd)
    max_file_bytes: int = Field(default=131072, ge=1, le=2097152)
    enable_system_info: bool = True
    max_question_chars: int = Field(default=2000, ge=1, le=40000)
    path_tools_limit: int = Field(default=40, ge=1, le=500)
    host: str = Field(
        default="127.0.0.1",
        pattern=r"^127\.0\.0\.1$",
        description="El servidor solo puede enlazarse a localhost IPv4.",
    )
    port: int = Field(default=8765, ge=1024, le=65535)

    @field_validator("model")
    @classmethod
    def model_must_have_provider(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("JUDGMAN_MODEL no puede estar vacío")
        if "/" not in cleaned:
            raise ValueError(
                "JUDGMAN_MODEL debe incluir el proveedor con el formato "
                "'proveedor/modelo' (por ejemplo 'openai/gpt-4o-mini', "
                "'deepseek/deepseek-chat' u 'ollama/llama3')"
            )
        return cleaned

    @field_validator("workspace")
    @classmethod
    def workspace_must_exist(cls, value: Path) -> Path:
        resolved = value.expanduser().resolve()
        if not resolved.exists() or not resolved.is_dir():
            raise ValueError(
                "JUDGMAN_WORKSPACE debe ser un directorio existente y accesible"
            )
        return resolved


def load_settings(
    user_config: Path | None = None,
    **overrides: object,
) -> Settings:
    """Carga la configuracion combinando archivos, entorno y overrides.

    ``overrides`` (por ejemplo los flags de la CLI) tienen la maxima prioridad.
    El ``.env`` del directorio actual gana sobre el archivo de usuario.
    """
    user_file = user_config if user_config is not None else user_config_path()
    return Settings(_env_file=(user_file, ".env"), **overrides)


def missing_fields(error: Exception) -> set[str]:
    """Devuelve los nombres de campo que provocaron un error de validacion."""
    errors = getattr(error, "errors", None)
    if not callable(errors):
        return set()
    return {str(item["loc"][0]) for item in errors() if item.get("loc")}
