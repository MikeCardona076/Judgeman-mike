import io
from pathlib import Path

from rich.console import Console

import sys

from judgman.cli import (
    _PlainPrompt,
    _default_prompt_session,
    analyze_file,
    build_parser,
    handle_command,
    run_chat,
    stream_to_console,
)
from judgman.core.chat import ChatSession
from judgman.theme import THEME
from judgman.updates import UpdateInfo


class FakeAnalyzer:
    model = "test/model"

    def stream(self, system_prompt: str, messages: list[dict[str, str]]):
        yield "Hola "
        yield "mundo"


def make_console() -> Console:
    return Console(
        file=io.StringIO(),
        force_terminal=False,
        width=80,
        theme=THEME,
    )


def make_session(workspace: Path) -> ChatSession:
    return ChatSession(
        FakeAnalyzer(),
        workspace,
        mode="file",
        diagnostics_provider=_fake_diagnostics,
    )


def _fake_diagnostics() -> dict:
    return {
        "listening_ports": {
            "available": True,
            "note": None,
            "entries": [
                {
                    "port": 8080,
                    "address": "0.0.0.0",
                    "protocol": "TCP",
                    "pid": 42,
                    "process": "servicio",
                }
            ],
        },
        "processes": {"available": True, "note": None, "entries": []},
        "connections": {"available": True, "note": None, "entries": []},
        "startup": {"available": True, "note": None, "entries": []},
        "services": {"available": True, "note": None, "entries": []},
        "firewall": {"available": True, "note": None, "output": "activo"},
        "hosts": {"hosts_file": "hosts", "hosts_entries": [], "proxy_env": {}},
    }


def test_parser_defaults_to_chat() -> None:
    args = build_parser().parse_args([])

    assert args.command is None


def test_parser_ask_collects_question_words() -> None:
    args = build_parser().parse_args(["ask", "hola", "mundo"])

    assert args.command == "ask"
    assert args.question == ["hola", "mundo"]


def test_parser_analyze_reads_path() -> None:
    args = build_parser().parse_args(["analyze", "notes.txt"])

    assert args.command == "analyze"
    assert args.path == Path("notes.txt")


def test_stream_to_console_returns_full_text(tmp_path: Path) -> None:
    console = make_console()

    result = stream_to_console(console, iter(["a", "b", "c"]))

    assert result == "abc"
    assert "abc" in console.file.getvalue()


def test_handle_command_exit_returns_false(tmp_path: Path) -> None:
    console = make_console()
    session = make_session(tmp_path)

    assert handle_command(console, session, "/exit") is False
    assert handle_command(console, session, "/quit") is False


def test_handle_command_clear_resets_history(tmp_path: Path) -> None:
    console = make_console()
    session = make_session(tmp_path)
    session.ask("hola")

    assert handle_command(console, session, "/clear") is True
    assert session.history == []


def test_handle_command_switches_mode(tmp_path: Path) -> None:
    console = make_console()
    session = make_session(tmp_path)

    handle_command(console, session, "/security")

    assert session.mode == "security"


def test_handle_command_diagnose_sets_mode(tmp_path: Path) -> None:
    console = make_console()
    session = make_session(tmp_path)

    handle_command(console, session, "/diagnose")

    assert session.mode == "diagnose"


def test_handle_command_snapshot_prints_data(tmp_path: Path) -> None:
    console = make_console()
    session = make_session(tmp_path)

    handle_command(console, session, "/snapshot")

    assert "os_name" in console.file.getvalue()


def test_handle_command_status_shows_workspace(tmp_path: Path) -> None:
    console = make_console()
    session = make_session(tmp_path)

    handle_command(console, session, "/status")

    output = console.file.getvalue()
    assert "workspace" in output
    assert "modelo" in output


def test_handle_command_mode_sets_mode_with_argument(tmp_path: Path) -> None:
    console = make_console()
    session = make_session(tmp_path)

    handle_command(console, session, "/mode security")

    assert session.mode == "security"


def test_handle_command_retry_repeats_last_prompt(tmp_path: Path) -> None:
    console = make_console()
    session = make_session(tmp_path)
    session.ask("hola")

    handle_command(console, session, "/retry")

    assert len(session.history) == 4


def test_handle_command_help_lists_commands(tmp_path: Path) -> None:
    console = make_console()
    session = make_session(tmp_path)

    handle_command(console, session, "/help")

    output = console.file.getvalue()
    assert "/status" in output
    assert "/retry" in output
    assert "/diagnose" in output


def test_handle_command_model_shows_model(tmp_path: Path) -> None:
    console = make_console()
    session = make_session(tmp_path)

    handle_command(console, session, "/model")

    assert session.analyzer.model in console.file.getvalue()


def test_analyze_file_streams_analysis(tmp_path: Path) -> None:
    (tmp_path / "notes.txt").write_text("print('hola')", encoding="utf-8")
    console = make_console()
    session = make_session(tmp_path)

    result = analyze_file(console, session, "notes.txt")

    assert result == "Hola mundo"
    assert session.history[0]["content"].endswith("print('hola')")


def test_analyze_file_outside_workspace_reports_error(tmp_path: Path) -> None:
    console = make_console()
    session = make_session(tmp_path)

    result = analyze_file(console, session, str(tmp_path.parent / "x.txt"))

    assert result == ""
    assert "No se pudo leer" in console.file.getvalue()


class FakePrompt:
    def __init__(self, lines: list[str]) -> None:
        self._lines = list(lines)

    def prompt(self, message: str = "jmike > ") -> str:
        if not self._lines:
            raise EOFError
        return self._lines.pop(0)


def test_run_chat_processes_commands_until_exit(tmp_path: Path) -> None:
    console = make_console()
    session = make_session(tmp_path)
    prompt = FakePrompt(["/security", "una pregunta", "/exit"])

    run_chat(session, console, prompt)

    assert session.mode == "security"
    assert "Hola mundo" in console.file.getvalue()
    assert len(session.history) == 2


def test_handle_command_apply_without_actions_warns(tmp_path: Path) -> None:
    console = make_console()
    session = make_session(tmp_path)

    handle_command(console, session, "/apply 1")

    assert "No hay acciones propuestas" in console.file.getvalue()


def test_handle_command_ports_lists_listeners(tmp_path: Path) -> None:
    console = make_console()
    session = make_session(tmp_path)

    handle_command(console, session, "/ports")

    output = console.file.getvalue()
    assert "8080" in output
    assert "servicio" in output


def test_handle_command_port_diagnoses(tmp_path: Path) -> None:
    console = make_console()
    session = make_session(tmp_path)

    handle_command(console, session, "/port 8080")

    output = console.file.getvalue()
    assert "Puerto 8080" in output
    assert "listening" in output


def test_handle_command_pro_lists_roadmap(tmp_path: Path) -> None:
    console = make_console()
    session = make_session(tmp_path)

    handle_command(console, session, "/pro")

    output = console.file.getvalue()
    assert "Próximamente" in output or "Proximamente" in output
    assert "No disponible" in output


def test_parser_update_check_flag() -> None:
    args = build_parser().parse_args(["update", "--check"])

    assert args.command == "update"
    assert args.check is True


def test_handle_command_update_reports_new_version(tmp_path: Path, monkeypatch) -> None:
    import judgman.updates as updates

    monkeypatch.setattr(
        updates,
        "check_for_update",
        lambda *a, **k: UpdateInfo("0.1.0", "0.2.0", True),
    )
    console = make_console()
    session = make_session(tmp_path)

    handle_command(console, session, "/update")

    output = console.file.getvalue()
    assert "0.2.0" in output
    assert "/update --run" in output


def test_handle_command_update_up_to_date(tmp_path: Path, monkeypatch) -> None:
    import judgman.updates as updates

    monkeypatch.setattr(
        updates,
        "check_for_update",
        lambda *a, **k: UpdateInfo("0.1.0", "0.1.0", False),
    )
    console = make_console()
    session = make_session(tmp_path)

    handle_command(console, session, "/update")

    assert "ultima version" in console.file.getvalue().lower()


def test_handle_command_update_run_can_cancel(tmp_path: Path, monkeypatch) -> None:
    import judgman.updates as updates

    monkeypatch.setattr(
        updates,
        "check_for_update",
        lambda *a, **k: UpdateInfo("0.1.0", "0.2.0", True),
    )
    monkeypatch.setattr("builtins.input", lambda *a, **k: "n")
    console = make_console()
    session = make_session(tmp_path)

    handle_command(console, session, "/update --run")

    assert "cancelada" in console.file.getvalue().lower()


def test_default_prompt_session_falls_back_when_not_tty(monkeypatch) -> None:
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False, raising=False)

    assert isinstance(_default_prompt_session(), _PlainPrompt)
