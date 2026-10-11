"""Punto de entrada de la CLI ``jmike``.

Subcomandos:
    jmike            Abre el chat interactivo en la terminal (por defecto).
    jmike chat       Igual que ``jmike``.
    jmike serve      Inicia el monitor pasivo: scanner, API local y bandeja.
    jmike config     Reconfigura el proveedor y el workspace.
    jmike ask Q...   Responde una pregunta sobre el sistema (sin chat).
    jmike analyze R  Analiza pedagogicamente un archivo del workspace.
"""

import argparse
import subprocess
import sys
from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.history import InMemoryHistory
from pydantic import ValidationError
from rich.console import Console
from rich.panel import Panel

from judgman.config import Settings, load_settings, missing_fields
from judgman.core.analyzer import Analyzer
from judgman.core.chat import ChatSession
from judgman.core.files import FileSkipped
from judgman.onboarding import run_onboarding
from judgman.theme import BANNER, make_console, prompt_style

CHAT_COMMANDS = [
    "/help",
    "/system",
    "/code",
    "/file",
    "/snapshot",
    "/serve",
    "/settings",
    "/clear",
    "/exit",
    "/quit",
]

HELP_TEXT = """Comandos disponibles:
  /help            Muestra esta ayuda.
  /system          Cambia al modo sistema (preguntas sobre tu SO).
  /code            Cambia al modo codigo (preguntas generales).
  /file <ruta>     Analiza un archivo dentro del workspace.
  /snapshot        Muestra los datos del sistema que se enviarian.
  /serve           Inicia el monitor web en segundo plano.
  /settings        Reconfigura la API key, el modelo o el workspace.
  /clear           Borra el historial de la conversacion.
  /exit, /quit     Sale del chat.

Escribe una pregunta y pulsa Enter. Ctrl+C cancela la entrada, Ctrl+D sale."""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jmike",
        description="Judgman Mike: chat y monitor de archivos local.",
    )
    parser.add_argument(
        "--model",
        help="Sobrescribe JUDGMAN_MODEL para esta sesion.",
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        help="Sobrescribe JUDGMAN_WORKSPACE para esta sesion.",
    )
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("chat", help="Abre el chat interactivo (por defecto).")
    subparsers.add_parser("serve", help="Inicia monitor, API local y bandeja.")
    subparsers.add_parser("config", help="Reconfigura el proveedor y el workspace.")

    ask = subparsers.add_parser("ask", help="Pregunta puntual sobre el sistema.")
    ask.add_argument("question", nargs="+", help="Pregunta a responder.")

    analyze = subparsers.add_parser(
        "analyze", help="Analiza un archivo del workspace."
    )
    analyze.add_argument("path", type=Path, help="Ruta del archivo a analizar.")

    return parser


def resolve_settings(args: argparse.Namespace, console: Console) -> Settings:
    """Carga la configuracion; lanza el onboarding si falta la API key."""
    overrides: dict[str, object] = {}
    if args.model:
        overrides["model"] = args.model
    if args.workspace is not None:
        overrides["workspace"] = args.workspace

    fixable = {"api_key", "model", "workspace"}
    try:
        return load_settings(**overrides)
    except ValidationError as exc:
        invalid = missing_fields(exc)
        if not invalid or not invalid <= fixable:
            raise
        if not sys.stdin.isatty():
            console.print(
                "[jmike.err]La configuracion esta incompleta o es invalida.[/jmike.err] "
                "Ejecuta 'jmike config' en una terminal interactiva o revisa el .env."
            )
            raise SystemExit(1) from exc
        settings = run_onboarding(console)
        return load_settings(**overrides) if overrides else settings


def build_session(settings: Settings) -> ChatSession:
    analyzer = Analyzer(
        model=settings.model,
        api_key=settings.api_key.get_secret_value(),
    )
    return ChatSession(
        analyzer,
        settings.workspace,
        path_tools_limit=settings.path_tools_limit,
        max_file_bytes=settings.max_file_bytes,
    )


def stream_to_console(
    console: Console,
    chunks,
    status_text: str = "pensando",
) -> str:
    """Muestra un estado mientras espera y luego imprime token a token."""
    iterator = iter(chunks)
    with console.status(f"[jmike.violet]{status_text}...[/jmike.violet]", spinner="dots"):
        try:
            first = next(iterator)
        except StopIteration:
            first = None

    parts: list[str] = []
    if first:
        parts.append(first)
        console.print(first, end="")
    for chunk in iterator:
        parts.append(chunk)
        console.print(chunk, end="")
    console.print("")
    return "".join(parts)


def print_snapshot(console: Console, session: ChatSession) -> None:
    console.print(
        Panel(
            session.snapshot_text(),
            title="Datos del sistema que se enviarian",
            border_style="jmike.violet",
        )
    )


def handle_command(
    console: Console,
    session: ChatSession,
    command: str,
) -> bool:
    """Procesa un comando con barra. Devuelve False para salir del chat."""
    name, _, argument = command.partition(" ")
    name = name.casefold()
    argument = argument.strip()

    if name in ("/exit", "/quit"):
        return False
    if name == "/help":
        console.print(
            Panel(HELP_TEXT, title="Judgman Mike", border_style="jmike.accent")
        )
    elif name == "/system":
        session.set_mode("system")
        console.print("[jmike.ok]Modo sistema activado.[/jmike.ok]")
    elif name == "/code":
        session.set_mode("code")
        console.print("[jmike.ok]Modo codigo activado.[/jmike.ok]")
    elif name == "/snapshot":
        print_snapshot(console, session)
    elif name == "/serve":
        launch_serve(console)
    elif name == "/settings":
        reconfigure(console, session)
    elif name == "/clear":
        session.clear()
        console.print("[jmike.ok]Historial borrado.[/jmike.ok]")
    elif name == "/file":
        if not argument:
            console.print("[jmike.warn]Uso: /file <ruta>[/jmike.warn]")
        else:
            analyze_file(console, session, argument)
    else:
        console.print(f"[jmike.warn]Comando desconocido: {name}[/jmike.warn]")
    return True


def analyze_file(console: Console, session: ChatSession, raw_path: str) -> str:
    try:
        relative, content = session.read_file(raw_path)
    except (PermissionError, ValueError, FileSkipped, UnicodeError, OSError) as exc:
        console.print(f"[jmike.err]No se pudo leer el archivo:[/jmike.err] {exc}")
        return ""

    prompt = (
        f"Analiza pedagogicamente el archivo '{relative}' sin modificarlo. "
        "Sugiere cambios como diff.\n\n"
        f"{content}"
    )
    return stream_to_console(console, session.stream_reply(prompt, mode="code"))


def reconfigure(console: Console, session: ChatSession) -> None:
    settings = run_onboarding(console)
    session.reconfigure(
        model=settings.model,
        api_key=settings.api_key.get_secret_value(),
        workspace=settings.workspace,
    )
    console.print("[jmike.ok]Ajustes actualizados.[/jmike.ok]")


def launch_serve(console: Console) -> None:
    try:
        settings = load_settings()
    except Exception as exc:
        console.print(f"[jmike.err]Configuracion invalida:[/jmike.err] {exc}")
        return
    subprocess.Popen([sys.executable, "-m", "judgman", "serve"])
    console.print(
        f"[jmike.ok]Monitor iniciado en[/jmike.ok] "
        f"http://{settings.host}:{settings.port}"
    )


class _PlainPrompt:
    """Lector de lineas de respaldo cuando no hay terminal interactiva."""

    def prompt(self, message: str) -> str:
        return input(message)


def _default_prompt_session() -> PromptSession | _PlainPrompt:
    if sys.stdin.isatty():
        return PromptSession(
            history=InMemoryHistory(),
            completer=WordCompleter(CHAT_COMMANDS, ignore_case=True),
            complete_while_typing=True,
            style=prompt_style(),
            message=[("class:prompt", "jmike > ")],
        )
    return _PlainPrompt()


def run_chat(
    session: ChatSession,
    console: Console | None = None,
    prompt_session: PromptSession | _PlainPrompt | None = None,
) -> None:
    console = console or make_console()
    if prompt_session is None:
        prompt_session = _default_prompt_session()

    console.print(BANNER, style="jmike.accent")
    console.print(
        Panel(
            f"Chat local de Judgman Mike. Modo [jmike.violet]{session.mode}[/jmike.violet]. "
            "Escribe /help para ver los comandos.",
            border_style="jmike.accent",
        )
    )
    while True:
        try:
            line = prompt_session.prompt("jmike > ")
        except KeyboardInterrupt:
            continue
        except EOFError:
            console.print("\n[jmike.dim]Hasta luego.[/jmike.dim]")
            return

        line = line.strip()
        if not line:
            continue
        if line.startswith("/"):
            if not handle_command(console, session, line):
                console.print("[jmike.dim]Hasta luego.[/jmike.dim]")
                return
            continue

        try:
            stream_to_console(console, session.stream_reply(line))
        except Exception as exc:  # pragma: no cover - depende del proveedor
            console.print(f"[jmike.err]Error del proveedor:[/jmike.err] {exc}")
            console.print(
                "[jmike.dim]Revisa el modelo con '/settings'. Debe tener el "
                "formato proveedor/modelo, por ejemplo 'deepseek/deepseek-chat'."
                "[/jmike.dim]"
            )


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    console = make_console()

    command = args.command or "chat"
    if command == "config":
        run_onboarding(console)
        return

    try:
        settings = resolve_settings(args, console)
    except Exception as exc:
        console.print(
            f"[jmike.err]Configuracion invalida.[/jmike.err] Crea un archivo "
            f".env valido ({exc})"
        )
        raise SystemExit(1) from exc

    if command == "serve":
        from judgman.main import serve

        try:
            serve(settings)
        except Exception as exc:  # pragma: no cover - arranque del servidor
            console.print(f"[jmike.err]No se pudo iniciar el monitor:[/jmike.err] {exc}")
            raise SystemExit(1)
        return

    session = build_session(settings)

    try:
        if command == "ask":
            stream_to_console(console, session.stream_reply(" ".join(args.question)))
        elif command == "analyze":
            analyze_file(console, session, str(args.path))
        else:
            run_chat(session, console)
    except KeyboardInterrupt:  # pragma: no cover - interaccion de usuario
        console.print("\n[jmike.dim]Hasta luego.[/jmike.dim]")


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
