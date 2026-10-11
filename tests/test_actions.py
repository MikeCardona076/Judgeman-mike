from __future__ import annotations

import platform
from pathlib import Path

from judgman.core.actions import (
    ACTION_CATALOG,
    ActionRunner,
    CommandResult,
    parse_actions,
)

IS_WINDOWS = platform.system() == "Windows"


def _block(payload: str) -> str:
    return f'Puedo hacer esto.\n```action\n{payload}\n```\n'


def test_parse_valid_action() -> None:
    text = _block('{"id": "kill_process", "params": {"pid": 42}, "reason": "x"}')

    actions, errors = parse_actions(text)

    assert errors == []
    assert len(actions) == 1
    assert actions[0].action_id == "kill_process"


def test_parse_rejects_unknown_action() -> None:
    text = _block('{"id": "format_disk", "params": {}}')

    actions, errors = parse_actions(text)

    assert actions == []
    assert any("no permitida" in error for error in errors)


def test_parse_rejects_missing_params() -> None:
    text = _block('{"id": "kill_process", "params": {}}')

    actions, errors = parse_actions(text)

    assert actions == []
    assert any("faltan parametros" in error for error in errors)


def test_parse_rejects_invalid_json() -> None:
    text = _block("{no es json}")

    actions, errors = parse_actions(text)

    assert actions == []
    assert errors


def test_command_matches_platform() -> None:
    actions, _ = parse_actions(_block('{"id": "kill_process", "params": {"pid": 42}}'))

    command = actions[0].command

    if IS_WINDOWS:
        assert command[:2] == ["taskkill", "/PID"]
    else:
        assert command[:2] == ["kill", "-9"]


def test_runner_executes_and_logs_when_confirmed(tmp_path: Path) -> None:
    actions, _ = parse_actions(_block('{"id": "kill_process", "params": {"pid": 42}}'))
    executed: list[list[str]] = []

    def fake_runner(argv, timeout=30.0):
        executed.append(list(argv))
        return CommandResult(tuple(argv), True, "ok")

    runner = ActionRunner(
        confirm=lambda _action: True,
        audit_path=tmp_path / "audit.log",
        runner=fake_runner,
    )

    result = runner.apply(actions[0])

    assert result.executed is True
    assert result.ok is True
    assert executed
    assert (tmp_path / "audit.log").read_text(encoding="utf-8").strip()


def test_runner_skips_when_denied() -> None:
    actions, _ = parse_actions(_block('{"id": "kill_process", "params": {"pid": 42}}'))
    executed: list[object] = []

    def fake_runner(argv, timeout=30.0):
        executed.append(argv)
        return CommandResult(tuple(argv), True, "")

    runner = ActionRunner(confirm=lambda _action: False, runner=fake_runner)

    result = runner.apply(actions[0])

    assert result.confirmed is False
    assert result.executed is False
    assert executed == []


def test_catalog_commands_have_no_shell_metacharacters() -> None:
    for spec in ACTION_CATALOG.values():
        params = {name: "1" for name in spec.required}
        for token in spec.build(params):
            assert ";" not in token
            assert "&&" not in token
            assert "|" not in token
