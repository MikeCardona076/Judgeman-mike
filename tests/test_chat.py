from pathlib import Path

import pytest

from judgman.core.chat import ChatSession
from judgman.core.files import FileSkipped


class FakeAnalyzer:
    def __init__(self, chunks: list[str] | None = None) -> None:
        self.calls: list[tuple[str, list[dict[str, str]]]] = []
        self._chunks = chunks or ["Hola ", "mundo"]

    def stream(self, system_prompt: str, messages: list[dict[str, str]]):
        self.calls.append((system_prompt, messages))
        yield from self._chunks


def fake_diagnostics() -> dict:
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
        "firewall": {"available": True, "note": None, "output": "Perfil: activo"},
        "hosts": {"hosts_file": "hosts", "hosts_entries": [], "proxy_env": {}},
    }


def make_session(
    workspace: Path,
    mode: str = "file",
    analyzer: FakeAnalyzer | None = None,
) -> ChatSession:
    return ChatSession(
        analyzer or FakeAnalyzer(),
        workspace,
        mode=mode,
        diagnostics_provider=fake_diagnostics,
    )


def test_ask_returns_streamed_answer_and_records_history(tmp_path: Path) -> None:
    session = make_session(tmp_path)

    answer = session.ask("Cuantas CPUs tengo?")

    assert answer == "Hola mundo"
    assert [turn["role"] for turn in session.history] == ["user", "assistant"]
    assert session.history[0]["content"].endswith("Cuantas CPUs tengo?")
    assert session.history[1]["content"] == "Hola mundo"


def test_diagnose_mode_injects_diagnostics(tmp_path: Path) -> None:
    session = make_session(tmp_path, mode="diagnose")

    session.ask("Por que no responde el 8080?")

    content = session.history[0]["content"]
    assert "diagnostico" in content
    assert "8080" in content


def test_security_mode_injects_context(tmp_path: Path) -> None:
    session = make_session(tmp_path, mode="security")

    session.ask("Hay algo raro?")

    content = session.history[0]["content"]
    assert "Resumen de red" in content
    assert "Datos del sistema" in content


def test_file_mode_does_not_inject_context(tmp_path: Path) -> None:
    session = make_session(tmp_path, mode="file")

    session.ask("Explicame un bucle")

    assert session.history[0]["content"] == "Explicame un bucle"


def test_set_mode_rejects_unknown(tmp_path: Path) -> None:
    session = make_session(tmp_path)

    with pytest.raises(ValueError):
        session.set_mode("desconocido")


def test_set_mode_accepts_new_modes(tmp_path: Path) -> None:
    session = make_session(tmp_path)

    for mode in ("diagnose", "security", "file"):
        session.set_mode(mode)
        assert session.mode == mode


def test_clear_empties_history_and_actions(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    session.ask("hola")

    session.clear()

    assert session.history == []
    assert session.last_actions == []


def test_actions_are_parsed_from_answer(tmp_path: Path) -> None:
    block = (
        'Puedo liberar el puerto.\n'
        '```action\n{"id": "kill_process", "params": {"pid": 42}, '
        '"reason": "ocupa el puerto"}\n```'
    )
    analyzer = FakeAnalyzer([block])
    session = make_session(tmp_path, mode="diagnose", analyzer=analyzer)

    session.ask("libera el 8080")

    assert len(session.last_actions) == 1
    assert session.last_actions[0].action_id == "kill_process"


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
