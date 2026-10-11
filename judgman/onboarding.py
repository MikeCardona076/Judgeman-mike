"""Asistente de primer arranque y configuracion guiada."""

import getpass
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import set_key
from pydantic import ValidationError
from rich.console import Console
from rich.panel import Panel

from judgman.config import Settings, load_settings
from judgman.paths import user_config_path
from judgman.theme import make_console


@dataclass(frozen=True)
class Provider:
    key: str
    label: str
    default_model: str
    needs_key: bool = True


PROVIDERS: tuple[Provider, ...] = (
    Provider("openai", "OpenAI", "openai/gpt-4o-mini"),
    Provider("anthropic", "Anthropic", "anthropic/claude-3-5-sonnet-latest"),
    Provider("deepseek", "DeepSeek", "deepseek/deepseek-chat"),
    Provider("gemini", "Google Gemini", "gemini/gemini-1.5-flash"),
    Provider("groq", "Groq", "groq/llama-3.1-70b-versatile"),
    Provider("openrouter", "OpenRouter", "openrouter/anthropic/claude-3.5-sonnet"),
    Provider("ollama", "Ollama (local)", "ollama/llama3.1", needs_key=False),
    Provider("other", "Otro (LiteLLM)", ""),
)

_INTRO = (
    "Primer arranque. Configura tu proveedor.\n"
    "La clave se guarda en tu archivo de configuracion de usuario, fuera del "
    "proyecto."
)


def normalize_model(provider: str, raw_model: str) -> str:
    """Garantiza el formato ``proveedor/modelo`` que exige LiteLLM."""
    cleaned = raw_model.strip()
    if not cleaned:
        raise ValueError("El modelo no puede estar vacio")
    if provider == "other":
        if "/" not in cleaned:
            raise ValueError(
                "Escribe el modelo completo con prefijo, por ejemplo "
                "'mistral/mistral-large-latest'"
            )
        return cleaned
    prefix = f"{provider}/"
    if cleaned.startswith(prefix):
        return cleaned
    return f"{prefix}{cleaned.lstrip('/')}"


def suggest_workspace(start: Path | None = None) -> Path:
    """Propone el directorio padre si se esta dentro de un entorno virtual."""
    current = (start or Path.cwd()).expanduser().resolve()
    for candidate in (current, *current.parents):
        if (candidate / "pyvenv.cfg").is_file():
            return candidate.parent
    return current


def verify_connection(
    model: str,
    api_key: str,
    timeout: float = 15.0,
) -> tuple[bool, str]:
    """Hace una llamada minima al proveedor para validar la configuracion."""
    from litellm import completion

    try:
        completion(
            model=model,
            api_key=api_key,
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=1,
            timeout=timeout,
        )
    except Exception as exc:  # noqa: BLE001 - se muestra al usuario
        return False, str(exc)
    return True, ""


def save_user_config(values: dict[str, str], path: Path | None = None) -> Path:
    target = path or user_config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.touch(exist_ok=True)
    for key, value in values.items():
        set_key(str(target), key, value, quote_mode="always")
    _restrict_permissions(target)
    return target


def _restrict_permissions(path: Path) -> None:
    if os.name != "nt":
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass


def _prompt(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    try:
        answer = input(f"{prompt}{suffix}: ").strip()
    except (EOFError, KeyboardInterrupt):
        raise SystemExit(1) from None
    return answer or default


def _prompt_secret(console: Console) -> str:
    while True:
        try:
            value = getpass.getpass("API key del proveedor (no se mostrara): ")
        except (EOFError, KeyboardInterrupt):
            raise SystemExit(1) from None
        value = value.strip()
        if value:
            return value
        console.print("[jmike.err]La API key no puede estar vacia.[/jmike.err]")


def _choose_provider(console: Console) -> Provider:
    console.print("\n[jmike.accent]Elige tu proveedor:[/jmike.accent]")
    for index, provider in enumerate(PROVIDERS, start=1):
        console.print(f"  [jmike.violet]{index}[/jmike.violet]. {provider.label}")
    while True:
        raw = _prompt("Proveedor", "1")
        try:
            selected = int(raw)
        except ValueError:
            console.print("[jmike.warn]Escribe el numero del proveedor.[/jmike.warn]")
            continue
        if 1 <= selected <= len(PROVIDERS):
            return PROVIDERS[selected - 1]
        console.print("[jmike.warn]Numero fuera de rango.[/jmike.warn]")


def _prompt_model(console: Console, provider: Provider) -> str:
    while True:
        raw = _prompt("Modelo (LiteLLM)", provider.default_model)
        try:
            return normalize_model(provider.key, raw)
        except ValueError as exc:
            console.print(f"[jmike.warn]{exc}[/jmike.warn]")


def _prompt_workspace(console: Console, default: Path) -> str:
    while True:
        raw = _prompt("Carpeta a vigilar (workspace)", str(default))
        resolved = Path(raw).expanduser()
        if resolved.is_dir():
            return str(resolved)
        console.print(f"[jmike.err]La carpeta no existe:[/jmike.err] {resolved}")


def _resolve_failed_connection(console: Console, error: str) -> str:
    console.print(f"[jmike.err]No se pudo conectar:[/jmike.err] {error}")
    console.print(
        "  [jmike.violet]r[/jmike.violet]. Reintentar    "
        "[jmike.violet]e[/jmike.violet]. Editar modelo    "
        "[jmike.violet]g[/jmike.violet]. Guardar de todos modos    "
        "[jmike.violet]s[/jmike.violet]. Salir"
    )
    return _prompt("Opcion", "r").casefold()


def run_onboarding(
    console: Console | None = None,
    path: Path | None = None,
) -> Settings:
    """Pregunta los datos minimos, los guarda y devuelve la configuracion."""
    console = console or make_console()
    target = path or user_config_path()
    console.print(
        Panel(_INTRO, title="Judgman Mike", border_style="jmike.accent")
    )

    provider = _choose_provider(console)
    model = _prompt_model(console, provider)
    api_key = _prompt_secret(console) if provider.needs_key else "ollama"
    workspace = _prompt_workspace(console, suggest_workspace())

    while True:
        ok, error = verify_connection(model, api_key)
        if ok:
            console.print("[jmike.ok]Conexion verificada.[/jmike.ok]")
            break
        choice = _resolve_failed_connection(console, error)
        if choice.startswith("r"):
            continue
        if choice.startswith("e"):
            provider = _choose_provider(console)
            model = _prompt_model(console, provider)
            continue
        if choice.startswith("g"):
            break
        raise SystemExit(1)

    values = {
        "JUDGMAN_API_KEY": api_key,
        "JUDGMAN_MODEL": model,
        "JUDGMAN_WORKSPACE": workspace,
    }
    saved = save_user_config(values, path=target)
    console.print(f"[jmike.ok]Configuracion guardada en[/jmike.ok] {saved}")
    return load_settings(user_config=saved)


__all__ = (
    "PROVIDERS",
    "Provider",
    "normalize_model",
    "run_onboarding",
    "save_user_config",
    "suggest_workspace",
    "verify_connection",
)
