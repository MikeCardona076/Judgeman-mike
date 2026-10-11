"""Punto de entrada de la CLI ``jmike``.

Subcomandos:
    jmike            Abre la consola interactiva (TUI Tron si hay terminal).
    jmike chat       Igual que ``jmike``.
    jmike serve      Inicia el monitor pasivo: scanner, API local y bandeja.
    jmike config     Reconfigura el proveedor y el workspace.
    jmike ask Q...   Responde una pregunta sobre el sistema (sin chat).
    jmike analyze R  Analiza un archivo del workspace.
"""

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.key_binding import KeyBindings
from pydantic import ValidationError
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from judgman.config import Settings, load_settings, missing_fields
from judgman.core.actions import ActionRunner, ProposedAction
from judgman.core.analyzer import Analyzer
from judgman.core.chat import MODES, ChatSession
from judgman.core.diagnostics import check_port, render_bundle
from judgman.core.files import FileSkipped
from judgman.onboarding import run_onboarding
from judgman.paths import user_audit_path
from judgman.theme import BANNER, COMMAND_HELP, make_console, prompt_style


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jmike",
        description="JudgeMan-Mike: diagnostico y seguridad local.",
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
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Desactiva el color (tambien via la variable NO_COLOR).",
    )
    parser.add_argument(
        "--plain",
        action="store_true",
        help="Fuerza el modo de consola simple (sin TUI a pantalla completa).",
    )
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("chat", help="Abre la consola interactiva (por defecto).")
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
    """Carga la configuracion; lanza el onboarding si falta o es invalida."""
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
    status_text: str = "analizando",
) -> str:
    """Muestra la respuesta en vivo y la repinta como Markdown al terminar."""
    iterator = iter(chunks)
    if not console.is_terminal:
        parts: list[str] = []
        for chunk in iterator:
            parts.append(chunk)
            console.print(Text(chunk), end="")
        console.print("")
        return "".join(parts)

    buffer = ""
    with Live("", console=console, refresh_per_second=12, transient=True) as live:
        live.update(f"[jmike.dim]{status_text}...[/jmike.dim]")
        for chunk in chunks:
            buffer += chunk
            live.update(Text(buffer))
    if buffer:
        console.print(Markdown(buffer))
    return buffer


def session_table(session: ChatSession) -> Table:
    table = Table.grid(padding=(0, 1))
    table.add_column(style="jmike.key", no_wrap=True)
    table.add_column(style="jmike.text")
    table.add_row("modelo", session.analyzer.model)
    table.add_row("workspace", str(session.workspace))
    table.add_row("modo", session.mode)
    return table


def session_panel(session: ChatSession) -> Panel:
    return Panel(
        session_table(session),
        title="sesion",
        subtitle="[jmike.dim]Alt+Enter multilinea  Ctrl+L limpiar  "
        "Ctrl+D salir[/jmike.dim]",
        border_style="jmike.blue",
    )


def print_session(console: Console, session: ChatSession) -> None:
    console.print(session_panel(session))


def help_table() -> Table:
    table = Table(
        title="Comandos",
        border_style="jmike.accent",
        header_style="jmike.heading",
        expand=False,
    )
    table.add_column("Comando", style="jmike.key", no_wrap=True)
    table.add_column("Descripcion", style="jmike.text")
    for usage, description in COMMAND_HELP:
        table.add_row(usage, description)
    return table


def print_provider_error(console: Console, exc: Exception) -> None:
    console.print(
        Panel(
            Text(str(exc), style="jmike.err"),
            title="Error del proveedor",
            border_style="jmike.err",
            subtitle="[jmike.dim]Revisa el modelo con /settings; debe tener el "
            "formato proveedor/modelo[/jmike.dim]",
        )
    )


def run_reply(
    console: Console,
    session: ChatSession,
    text: str,
    mode: str | None = None,
) -> str:
    if not console.is_terminal:
        console.print(Text(f"> {text}", style="jmike.user"))
    console.print("[jmike.heading]◆ JudgeMan-Mike[/jmike.heading]")
    try:
        answer = stream_to_console(console, session.stream_reply(text, mode=mode))
    except KeyboardInterrupt:
        console.print("\n[jmike.warn][cancelado][/jmike.warn]")
        return ""
    except Exception as exc:  # noqa: BLE001 - se muestra al usuario
        print_provider_error(console, exc)
        return ""
    show_proposed_actions(console, session)
    return answer


def show_proposed_actions(console: Console, session: ChatSession) -> None:
    for error in session.last_action_errors:
        console.print(f"[jmike.warn]{error}[/jmike.warn]")
    if not session.last_actions:
        return
    console.print(actions_table(session.last_actions))
    console.print(
        "[jmike.dim]Usa /apply <n> (o /apply all) para ejecutar; se pedira "
        "confirmacion.[/jmike.dim]"
    )


def actions_table(actions: list[ProposedAction]) -> Table:
    table = Table(
        title="Acciones propuestas",
        border_style="jmike.warn",
        header_style="jmike.heading",
    )
    table.add_column("#", style="jmike.key", no_wrap=True)
    table.add_column("Accion", style="jmike.text")
    table.add_column("Riesgo", style="jmike.text")
    table.add_column("Comando", style="jmike.dim")
    for index, action in enumerate(actions, start=1):
        table.add_row(
            str(index),
            action.action_id,
            action.spec.risk,
            " ".join(action.command),
        )
    return table


def snapshot_panel(session: ChatSession) -> Panel:
    return Panel(
        Text(session.snapshot_text()),
        title="Datos basicos del sistema que se enviarian",
        border_style="jmike.blue",
    )


def diagnostics_panel(session: ChatSession) -> Panel:
    return Panel(
        Text(render_bundle(session.diagnostics())),
        title="Datos de diagnostico que se enviarian",
        border_style="jmike.blue",
    )


def ports_table(session: ChatSession) -> Table:
    data = session.diagnostics()["listening_ports"]
    table = Table(
        title="Puertos a la escucha",
        border_style="jmike.accent",
        header_style="jmike.heading",
    )
    for column in ("Protocolo", "Direccion", "Puerto", "PID", "Proceso"):
        table.add_column(column, style="jmike.text")
    if not data.get("available"):
        table.add_row(data.get("note") or "no disponible", "", "", "", "")
        return table
    for entry in data.get("entries", [])[:60]:
        table.add_row(
            str(entry["protocol"]),
            str(entry["address"]),
            str(entry["port"]),
            str(entry["pid"]),
            str(entry["process"]),
        )
    if not data.get("entries"):
        table.add_row("(ninguno)", "", "", "", "")
    return table


def port_panel(session: ChatSession, raw_port: str) -> Panel:
    try:
        port = int(raw_port)
    except ValueError:
        return Panel(
            Text(f"Puerto invalido: {raw_port}", style="jmike.err"),
            border_style="jmike.err",
        )
    info = check_port(port, session.diagnostics()["listening_ports"])
    lines = [f"Veredicto: {info['verdict']}", info["detail"], ""]
    for listener in info["listeners"]:
        lines.append(
            f"  {listener['protocol']} {listener['address']}:{listener['port']} "
            f"PID {listener['pid']} ({listener['process']})"
        )
    if info.get("note"):
        lines.append(f"Nota: {info['note']}")
    return Panel(Text("\n".join(lines)), title=f"Puerto {port}", border_style="jmike.blue")


def processes_table(session: ChatSession) -> Table:
    data = session.diagnostics()["processes"]
    table = Table(
        title="Procesos con mas carga",
        border_style="jmike.accent",
        header_style="jmike.heading",
    )
    for column in ("PID", "Proceso", "CPU%", "MEM%", "Usuario", "Ejecutable"):
        table.add_column(column, style="jmike.text")
    if not data.get("available"):
        table.add_row(data.get("note") or "no disponible", "", "", "", "", "")
        return table
    for entry in data.get("entries", []):
        table.add_row(
            str(entry["pid"]),
            str(entry["name"]),
            str(entry["cpu_percent"]),
            str(entry["mem_percent"]),
            str(entry["user"]),
            str(entry["exe"]),
        )
    return table


def connections_table(session: ChatSession) -> Table:
    data = session.diagnostics()["connections"]
    table = Table(
        title="Conexiones salientes establecidas",
        border_style="jmike.accent",
        header_style="jmike.heading",
    )
    for column in ("Remoto", "Estado", "PID", "Proceso"):
        table.add_column(column, style="jmike.text")
    if not data.get("available"):
        table.add_row(data.get("note") or "no disponible", "", "", "")
        return table
    for entry in data.get("entries", []):
        table.add_row(
            str(entry["remote"]),
            str(entry["status"]),
            str(entry["pid"]),
            str(entry["process"]),
        )
    if not data.get("entries"):
        table.add_row("(ninguna)", "", "", "")
    return table


def services_table(session: ChatSession) -> Table:
    data = session.diagnostics()["services"]
    table = Table(
        title="Servicios detenidos o relevantes",
        border_style="jmike.accent",
        header_style="jmike.heading",
    )
    table.add_column("Servicio", style="jmike.text")
    table.add_column("Estado", style="jmike.text")
    if not data.get("available"):
        table.add_row(data.get("note") or "no disponible", "")
        return table
    for entry in data.get("entries", []):
        table.add_row(str(entry["name"]), str(entry["state"]))
    return table


def startup_table(session: ChatSession) -> Table:
    data = session.diagnostics()["startup"]
    table = Table(
        title="Arranque automatico",
        border_style="jmike.accent",
        header_style="jmike.heading",
    )
    table.add_column("Nombre", style="jmike.text")
    table.add_column("Valor", style="jmike.text")
    table.add_column("Origen", style="jmike.dim")
    if not data.get("available"):
        table.add_row(data.get("note") or "no disponible", "", "")
        return table
    for entry in data.get("entries", []):
        table.add_row(str(entry["name"]), str(entry["value"]), str(entry["source"]))
    if not data.get("entries"):
        table.add_row("(ninguno)", "", "")
    return table


def firewall_panel(session: ChatSession) -> Panel:
    data = session.diagnostics()["firewall"]
    text = data.get("output") if data.get("available") else data.get("note")
    return Panel(
        Text(text or "no disponible"),
        title="Firewall",
        border_style="jmike.blue",
    )


def hosts_panel(session: ChatSession) -> Panel:
    data = session.diagnostics()["hosts"]
    lines: list[str] = [f"Archivo: {data.get('hosts_file')}", ""]
    if data.get("hosts_entries"):
        lines.append("Entradas de hosts:")
        lines.extend(f"  {entry}" for entry in data["hosts_entries"])
    else:
        lines.append("Entradas de hosts: (ninguna relevante)")
    if data.get("proxy_env"):
        lines.append("")
        lines.append("Proxy de entorno:")
        lines.extend(f"  {name}={value}" for name, value in data["proxy_env"].items())
    return Panel(Text("\n".join(lines)), title="hosts / DNS / proxy", border_style="jmike.blue")


def file_prompt(session: ChatSession, raw_path: str) -> str:
    """Construye el prompt de analisis de archivo; lanza si no se puede leer."""
    relative, content = session.read_file(raw_path)
    return (
        f"Analiza el archivo '{relative}' buscando amenazas o riesgos y como "
        "mitigarlos; si propones un cambio, hazlo como diff sin modificarlo.\n\n"
        f"{content}"
    )


def build_file_prompt(session: ChatSession, raw_path: str) -> tuple[str | None, str]:
    """Devuelve ``(prompt, error)``; uno de los dos es cadena vacia/None."""
    try:
        return file_prompt(session, raw_path), ""
    except (PermissionError, ValueError, FileSkipped, UnicodeError, OSError) as exc:
        return None, f"No se pudo leer el archivo: {exc}"


@dataclass
class CommandOutcome:
    """Resultado de un comando, independiente de como se renderice."""

    renderables: list[object] = field(default_factory=list)
    quit: bool = False
    clear_screen: bool = False
    reply: tuple[str, str | None] | None = None
    apply_actions: list[ProposedAction] = field(default_factory=list)


def _select_actions(
    actions: list[ProposedAction], argument: str
) -> tuple[list[ProposedAction], str]:
    if not actions:
        return [], "No hay acciones propuestas."
    if argument.strip().lower() in ("all", "todas", "*"):
        return list(actions), ""
    selected: list[ProposedAction] = []
    invalid: list[str] = []
    for token in re.split(r"[\s,]+", argument.strip()):
        if not token:
            continue
        if not token.isdigit():
            invalid.append(token)
            continue
        index = int(token)
        if 1 <= index <= len(actions):
            selected.append(actions[index - 1])
        else:
            invalid.append(token)
    if not selected:
        return [], f"Seleccion invalida: {', '.join(invalid) or argument}"
    return selected, ""


def execute_command(session: ChatSession, command: str) -> CommandOutcome:
    """Interpreta un comando con barra sin imprimir. Reutilizable por TUI y CLI."""
    name, _, argument = command.partition(" ")
    name = name.strip().lower()
    argument = argument.strip()

    if name in ("/exit", "/quit"):
        return CommandOutcome(quit=True)
    if name == "/help":
        return CommandOutcome([help_table()])
    if name == "/status":
        return CommandOutcome([session_panel(session)])
    if name == "/model":
        return CommandOutcome([f"[jmike.key]modelo[/jmike.key]  {session.analyzer.model}"])
    if name in ("/diagnose", "/security"):
        target = name[1:]
        if argument:
            return CommandOutcome(reply=(argument, target))
        session.set_mode(target)
        return CommandOutcome([f"[jmike.ok]Modo {target} activado.[/jmike.ok]"])
    if name == "/mode":
        if not argument:
            return CommandOutcome(
                [f"[jmike.text]Modo actual:[/jmike.text] [jmike.violet]{session.mode}[/jmike.violet]"]
            )
        if argument in MODES:
            session.set_mode(argument)
            return CommandOutcome([f"[jmike.ok]Modo {argument} activado.[/jmike.ok]"])
        return CommandOutcome(["[jmike.warn]Uso: /mode diagnose|security|file[/jmike.warn]"])
    if name == "/pro":
        return CommandOutcome(
            [
                "[jmike.heading]JudgeMan-Mike Pro — Próximamente[/jmike.heading]",
                "[jmike.text]No disponible en esta versión.[/jmike.text]",
                "[jmike.dim]Roadmap: monitor continuo + alertas, historial/timeline/export, auditoría firmada, catálogo ampliado con rollback/schedule, multi-máquina/dashboard, modelo hospedado, licencia por key + auto-update, SSO/RBAC.[/jmike.dim]",
            ]
        )
    if name == "/snapshot":
        return CommandOutcome([snapshot_panel(session)])
    if name == "/diagnostics":
        return CommandOutcome([diagnostics_panel(session)])
    if name == "/ports":
        return CommandOutcome([ports_table(session)])
    if name == "/port":
        if not argument:
            return CommandOutcome(["[jmike.warn]Uso: /port <numero>[/jmike.warn]"])
        return CommandOutcome([port_panel(session, argument)])
    if name == "/procs":
        return CommandOutcome([processes_table(session)])
    if name == "/connections":
        return CommandOutcome([connections_table(session)])
    if name == "/services":
        return CommandOutcome([services_table(session)])
    if name == "/startup":
        return CommandOutcome([startup_table(session)])
    if name == "/firewall":
        return CommandOutcome([firewall_panel(session)])
    if name == "/hosts":
        return CommandOutcome([hosts_panel(session)])
    if name == "/apply":
        selected, error = _select_actions(session.last_actions, argument)
        if error:
            return CommandOutcome([f"[jmike.warn]{error}[/jmike.warn]"])
        return CommandOutcome(apply_actions=selected)
    if name == "/serve":
        return CommandOutcome([launch_serve()])
    if name == "/settings":
        return CommandOutcome([reconfigure(session)])
    if name == "/retry":
        if session.last_prompt:
            return CommandOutcome(reply=(session.last_prompt, session.last_mode))
        return CommandOutcome(["[jmike.warn]No hay una pregunta previa.[/jmike.warn]"])
    if name in ("/clear", "/new"):
        session.clear()
        return CommandOutcome(
            ["[jmike.ok]Historial y pantalla limpiados.[/jmike.ok]"],
            clear_screen=True,
        )
    if name == "/file":
        if not argument:
            return CommandOutcome(["[jmike.warn]Uso: /file <ruta>[/jmike.warn]"])
        prompt, error = build_file_prompt(session, argument)
        if prompt is None:
            return CommandOutcome([f"[jmike.err]{error}[/jmike.err]"])
        return CommandOutcome([], reply=(prompt, "file"))
    return CommandOutcome([f"[jmike.warn]Comando desconocido: {name}[/jmike.warn]"])


def confirm_action(console: Console, action: ProposedAction) -> bool:
    console.print(actions_table([action]))
    console.print(
        f"[jmike.warn]Vas a ejecutar:[/jmike.warn] {' '.join(action.command)}"
    )
    try:
        answer = input("Ejecutar esta accion? [y/N]: ").strip().casefold()
    except (EOFError, KeyboardInterrupt):
        console.print("")
        return False
    return answer in ("y", "yes", "s", "si", "sí")


def apply_actions(
    console: Console,
    session: ChatSession,
    actions: list[ProposedAction],
) -> None:
    runner = ActionRunner(
        confirm=lambda action: confirm_action(console, action),
        audit_path=user_audit_path(),
    )
    for action in actions:
        result = runner.apply(action)
        if not result.confirmed:
            console.print("[jmike.dim]Cancelado por el usuario.[/jmike.dim]")
        elif result.ok:
            console.print(f"[jmike.ok]Ejecutado:[/jmike.ok] {action.action_id}")
            if result.output:
                console.print(Text(result.output, style="jmike.dim"))
        else:
            console.print(f"[jmike.err]Fallo:[/jmike.err] {action.action_id}")
            if result.error:
                console.print(Text(result.error, style="jmike.err"))


def handle_command(
    console: Console,
    session: ChatSession,
    command: str,
) -> bool:
    """Procesa un comando con barra en el flujo plano. Devuelve False al salir."""
    outcome = execute_command(session, command)
    for renderable in outcome.renderables:
        console.print(renderable)
    if outcome.reply is not None:
        text, mode = outcome.reply
        run_reply(console, session, text, mode=mode)
    if outcome.apply_actions:
        apply_actions(console, session, outcome.apply_actions)
    return not outcome.quit


def analyze_file(console: Console, session: ChatSession, raw_path: str) -> str:
    prompt, error = build_file_prompt(session, raw_path)
    if prompt is None:
        console.print(f"[jmike.err]{error}[/jmike.err]")
        return ""
    return run_reply(console, session, prompt, mode="file")


def reconfigure(session: ChatSession, console: Console | None = None) -> str:
    settings = run_onboarding(console or make_console())
    session.reconfigure(
        model=settings.model,
        api_key=settings.api_key.get_secret_value(),
        workspace=settings.workspace,
    )
    return "[jmike.ok]Ajustes actualizados.[/jmike.ok]"


def launch_serve() -> str:
    try:
        settings = load_settings()
    except Exception as exc:
        return f"[jmike.err]Configuracion invalida:[/jmike.err] {exc}"
    subprocess.Popen([sys.executable, "-m", "judgman", "serve"])
    return (
        f"[jmike.ok]Monitor iniciado en[/jmike.ok] "
        f"http://{settings.host}:{settings.port}"
    )


class CommandCompleter(Completer):
    """Completador de comandos con descripcion en el menu."""

    def __init__(self, commands: tuple[tuple[str, str], ...]) -> None:
        self._commands = commands

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        if text.startswith("/") and " " not in text:
            for usage, description in self._commands:
                command = usage.split()[0]
                if command.startswith(text):
                    yield Completion(
                        command,
                        start_position=-len(text),
                        display_meta=description,
                    )


class _PlainPrompt:
    """Fallback de lectura en linea cuando no hay TTY."""

    def prompt(self, message: str = "jmike > ") -> str:
        return input(message)


def _key_bindings() -> KeyBindings:
    bindings = KeyBindings()

    @bindings.add("c-l")
    def _clear(event) -> None:
        event.app.renderer.clear()

    return bindings


def _make_message(session: ChatSession | None) -> object:
    def message():
        mode = session.mode if session is not None else "diagnose"
        return [
            ("class:prompt", "$ "),
            ("class:mode." + mode, f"[{mode}] "),
        ]

    return message


def _default_prompt_session(
    session: ChatSession | None = None,
) -> PromptSession | _PlainPrompt:
    if not sys.stdin.isatty():
        return _PlainPrompt()
    return PromptSession(
        history=InMemoryHistory(),
        completer=CommandCompleter(COMMAND_HELP),
        style=prompt_style(),
        message=_make_message(session) if session is not None else "jmike > ",
        multiline=False,
        key_bindings=_key_bindings(),
    )


def run_plain_chat(
    session: ChatSession,
    console: Console,
    prompt_session: PromptSession | _PlainPrompt,
) -> None:
    """Consola simple en linea (sin TUI, en tests y con --plain)."""
    if console.is_terminal:
        console.clear()
    console.print(BANNER, style="jmike.accent")
    print_session(console, session)

    while True:
        try:
            line = prompt_session.prompt()
        except KeyboardInterrupt:
            console.print("")
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

        console.print(Rule(style="jmike.rule"))
        run_reply(console, session, line)


def run_chat(
    session: ChatSession,
    console: Console | None = None,
    prompt_session: PromptSession | _PlainPrompt | None = None,
    force_plain: bool = False,
) -> None:
    console = console or make_console()

    if (
        not force_plain
        and prompt_session is None
        and console.is_terminal
        and sys.stdin.isatty()
        and sys.stdout.isatty()
    ):
        try:
            from judgman.tui import run_tui
        except ImportError:  # pragma: no cover - entorno sin prompt_toolkit
            run_tui = None  # type: ignore[assignment]
        if run_tui is not None:
            run_tui(session, console)
            return

    if prompt_session is None:
        prompt_session = _default_prompt_session(session)
    run_plain_chat(session, console, prompt_session)


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    console = make_console(no_color=args.no_color)

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
            console.print(
                f"[jmike.err]No se pudo iniciar el monitor:[/jmike.err] {exc}"
            )
            raise SystemExit(1)
        return

    session = build_session(settings)

    try:
        if command == "ask":
            run_reply(console, session, " ".join(args.question), mode="diagnose")
        elif command == "analyze":
            analyze_file(console, session, str(args.path))
        else:
            run_chat(session, console, force_plain=args.plain)
    except KeyboardInterrupt:  # pragma: no cover - interaccion de usuario
        console.print("\n[jmike.dim]Hasta luego.[/jmike.dim]")


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
