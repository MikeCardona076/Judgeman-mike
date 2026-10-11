"""Asistente de primer arranque y guardado de la configuracion del usuario."""

import getpass
import os
from pathlib import Path

from dotenv import set_key
from rich.console import Console
from rich.panel import Panel

from judgman.config import Settings, load_settings
from judgman.paths import user_config_path

DEFAULT_MODEL = "openai/gpt-4o-mini"


def save_user_config(values: dict[str, str], path: Path | None = None) -> Path:
    """Escribe los valores en el ``config.env`` del usuario."""
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
        console.print("[red]La API key no puede estar vacia.[/red]")


def _prompt_workspace(console: Console) -> str:
    while True:
        raw = _prompt("Carpeta a vigilar (workspace)", str(Path.cwd()))
        resolved = Path(raw).expanduser()
        if resolved.is_dir():
            return str(resolved)
        console.print(f"[red]La carpeta no existe:[/red] {resolved}")


def run_onboarding(
    console: Console | None = None,
    path: Path | None = None,
) -> Settings:
    """Pregunta los datos minimos, los guarda y devuelve la configuracion."""
    console = console or Console()
    target = path or user_config_path()
    console.print(
        Panel(
            "Primer arranque. Configura tu proveedor.\n"
            "La clave se guarda en tu archivo de configuracion de usuario, "
            "fuera del proyecto.",
            title="Judgman Mike",
            border_style="cyan",
        )
    )
    api_key = _prompt_secret(console)
    model = _prompt("Modelo (LiteLLM)", DEFAULT_MODEL)
    workspace = _prompt_workspace(console)

    values = {
        "JUDGMAN_API_KEY": api_key,
        "JUDGMAN_MODEL": model,
        "JUDGMAN_WORKSPACE": workspace,
    }
    saved = save_user_config(values, path=target)
    console.print(f"[green]Configuracion guardada en[/green] {saved}")
    return load_settings(user_config=saved)
