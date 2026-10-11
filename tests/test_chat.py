from pathlib import Path

import pytest

from judgman.core.chat import ChatSession
from judgman.core.files import FileSkipped


class FakeAnalyzer:
    def __init__(self) -> None:
        self.calls: list[tuple[str, list[dict[str, str]]]] = []

    def stream(self, system_prompt: str, messages: list[dict[str, str]]):
        self.calls.append((system_prompt, messages))
        yield "Hola "
        yield "mundo"


def make_session(workspace: Path, mode: str = "system") -> ChatSession:
    return ChatSession(FakeAnalyzer(), workspace, mode=mode)


def test_ask_returns_streamed_answer_and_records_history(tmp_path: Path) -> None:
    session = make_session(tmp_path)

    answer = session.ask("Cuantas CPUs tengo?")

    assert answer == "Hola mundo"
    assert [turn["role"] for turn in session.history] == ["user", "assistant"]
    assert session.history[0]["content"].endswith("Cuantas CPUs tengo?")
    assert session.history[1]["content"] == "Hola mundo"


def test_system_mode_injects_snapshot(tmp_path: Path) -> None:
    session = make_session(tmp_path, mode="system")

    session.ask("Que sistema uso?")

    assert "Datos del sistema" in session.history[0]["content"]


def test_code_mode_does_not_inject_snapshot(tmp_path: Path) -> None:
    session = make_session(tmp_path, mode="code")

    session.ask("Explicame un bucle")

    assert "Datos del sistema" not in session.history[0]["content"]


def test_set_mode_rejects_unknown(tmp_path: Path) -> None:
    session = make_session(tmp_path)

    with pytest.raises(ValueError):
        session.set_mode("desconocido")


def test_clear_empties_history(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    session.ask("hola")

    session.clear()

    assert session.history == []


def test_read_file_returns_relative_path_and_content(tmp_path: Path) -> None:
    (tmp_path / "notes.txt").write_text("contenido", encoding="utf-8")
    session = make_session(tmp_path)

    relative, content = session.read_file("notes.txt")

    assert relative == "notes.txt"
    assert content == "contenido"


def test_read_file_outside_workspace_is_rejected(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("no", encoding="utf-8")
    session = make_session(workspace)

    with pytest.raises(PermissionError):
        session.read_file(outside)


def test_read_file_sensitive_is_skipped(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("SECRET=1", encoding="utf-8")
    session = make_session(tmp_path)

    with pytest.raises(FileSkipped):
        session.read_file(".env")
