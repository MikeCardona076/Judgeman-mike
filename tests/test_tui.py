from pathlib import Path

import pytest
from prompt_toolkit.application import Application
from prompt_toolkit.document import Document
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput

from judgman.core.chat import ChatSession
from judgman.theme import BANNER
from judgman.tui import TronConsole, TuiCompleter
from rich.text import Text


class FakeAnalyzer:
    model = "test/model"

    def __init__(self, chunks: list[str] | None = None) -> None:
        self._chunks = chunks or ["Hola ", "mundo"]

    def stream(self, system_prompt: str, messages: list[dict[str, str]]):
        yield from self._chunks


def make_session(workspace: Path, analyzer: FakeAnalyzer | None = None) -> ChatSession:
    return ChatSession(analyzer or FakeAnalyzer(), workspace)


def make_console(tmp_path: Path, session: ChatSession | None = None) -> TronConsole:
    return TronConsole(
        session or make_session(tmp_path),
        fallback_width=100,
        fallback_height=30,
        history_path=tmp_path / "history",
    )


def test_completer_suggests_commands() -> None:
    completer = TuiCompleter(Path("."))

    completions = list(completer.get_completions(Document("/he"), None))

    texts = [item.text for item in completions]
    assert "/help" in texts


def test_completer_suggests_files(tmp_path: Path) -> None:
    (tmp_path / "notes.txt").write_text("hola", encoding="utf-8")
    completer = TuiCompleter(tmp_path)

    completions = list(completer.get_completions(Document("/file no"), None))

    texts = [item.text for item in completions]
    assert "notes.txt" in texts


def test_completer_ignores_plain_text(tmp_path: Path) -> None:
    completer = TuiCompleter(tmp_path)

    completions = list(completer.get_completions(Document("hola"), None))

    assert completions == []


def test_console_renders_body(tmp_path: Path) -> None:
    console = make_console(tmp_path)

    console._append(console._render(Text(BANNER, style="jmike.accent")))

    assert console._body_rows() > 0
    assert "J U D G E M A N" in str(console._body())


def test_console_handles_model_command(tmp_path: Path) -> None:
    console = make_console(tmp_path)

    console._handle_command("/model")

    assert "modelo" in "\n".join(console._lines)


def test_console_clear_command_empties_history(tmp_path: Path) -> None:
    console = make_console(tmp_path)
    console._append(console._render(Text("contenido")))

    console._handle_command("/clear")

    assert console._lines == []
    assert console.session.history == []


def test_console_unknown_command_does_not_crash(tmp_path: Path) -> None:
    console = make_console(tmp_path)

    console._handle_command("/nope")

    assert "desconocido" in "\n".join(console._lines)


def test_console_update_run_cancel(tmp_path: Path, monkeypatch) -> None:
    import judgman.updates as updates

    monkeypatch.setattr(
        updates,
        "check_for_update",
        lambda *a, **k: updates.UpdateInfo("0.1.0", "0.2.0", True),
    )
    console = make_console(tmp_path)

    console._handle_command("/update --run")
    assert console._pending_update is True

    console._resolve_update("n")

    assert console._pending_update is False
    assert "cancelada" in "\n".join(console._lines).lower()


def test_console_update_run_executes(tmp_path: Path, monkeypatch) -> None:
    import time

    import judgman.updates as updates

    monkeypatch.setattr(
        updates,
        "check_for_update",
        lambda *a, **k: updates.UpdateInfo("0.1.0", "0.2.0", True),
    )
    calls = {"n": 0}

    def fake_perform(*_args, **_kwargs):
        calls["n"] += 1
        return True, "ok"

    monkeypatch.setattr(updates, "perform_update", fake_perform)
    console = make_console(tmp_path)

    console._handle_command("/update --run")
    console._resolve_update("y")

    for _ in range(100):
        if calls["n"]:
            break
        time.sleep(0.02)

    assert calls["n"] == 1
    assert "actualizado" in "\n".join(console._lines).lower()


def test_console_exit_command_is_safe_without_app(tmp_path: Path) -> None:
    console = make_console(tmp_path)

    console._handle_command("/exit")


def test_stream_worker_records_turn(tmp_path: Path) -> None:
    console = make_console(tmp_path)
    console._busy = True
    console._stream_start = len(console._lines)
    console._lines.append("")

    console._stream_worker("pregunta", None)

    assert console.session.turn_count == 1
    assert "Hola mundo" in "\n".join(console._lines)
    assert console._busy is False


def test_scroll_bindings_move_history(tmp_path: Path) -> None:
    console = make_console(tmp_path)
    for index in range(200):
        console._append(str(index))

    console._scroll_by(console._body_rows())
    assert console._scroll > 0
    assert "199" not in str(console._body())

    console._scroll_to_bottom()
    assert console._scroll == 0
    assert "199" in str(console._body())

    console._scroll_to_top()
    assert console._scroll == max(0, len(console._lines) - console._body_rows())
    assert "0" in str(console._body())


def test_application_runs_and_exits(tmp_path: Path) -> None:
    console = make_console(tmp_path)
    try:
        ctx = create_pipe_input()
        pipe = ctx.__enter__()
    except Exception:  # pragma: no cover - plataforma sin soporte de pipe
        pytest.skip("create_pipe_input no disponible")

    try:
        app = Application(
            layout=console._layout,
            key_bindings=console._key_bindings(),
            full_screen=False,
            input=pipe,
            output=DummyOutput(),
            refresh_interval=None,
        )
        console._app = app
        pipe.send_text("/help\r")
        pipe.send_text("/exit\r")
        app.run()
    finally:
        ctx.__exit__(None, None, None)

    assert any("Comandos" in line or "help" in line for line in console._lines)
