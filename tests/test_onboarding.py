import io
import os
from pathlib import Path

import pytest
from pydantic import ValidationError
from rich.console import Console

from judgman.cli import build_parser, resolve_settings
from judgman.config import Settings, load_settings, missing_fields
from judgman.onboarding import (
    normalize_model,
    run_onboarding,
    save_user_config,
    suggest_workspace,
)
from judgman.theme import THEME


@pytest.fixture
def isolated_config(monkeypatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    for key in list(os.environ):
        if key.startswith("JUDGMAN_"):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def make_console() -> Console:
    return Console(file=io.StringIO(), theme=THEME)


def test_save_user_config_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "sub" / "config.env"
    saved = save_user_config(
        {
            "JUDGMAN_API_KEY": "secret",
            "JUDGMAN_MODEL": "openai/gpt-4o-mini",
            "JUDGMAN_WORKSPACE": str(tmp_path),
        },
        path=path,
    )

    assert saved == path
    assert path.is_file()
    settings = load_settings(user_config=path)
    assert settings.api_key.get_secret_value() == "secret"
    assert settings.model == "openai/gpt-4o-mini"
    assert settings.workspace == tmp_path.resolve()


def test_local_env_overrides_user_config(isolated_config: Path) -> None:
    user = isolated_config / "config.env"
    save_user_config(
        {
            "JUDGMAN_API_KEY": "secret",
            "JUDGMAN_MODEL": "openai/from-user",
            "JUDGMAN_WORKSPACE": str(isolated_config),
        },
        path=user,
    )
    (isolated_config / ".env").write_text(
        'JUDGMAN_MODEL="openai/from-local"\n', encoding="utf-8"
    )

    assert load_settings(user_config=user).model == "openai/from-local"


def test_model_requires_provider_prefix() -> None:
    with pytest.raises(ValidationError) as excinfo:
        Settings(_env_file=None, api_key="k", model="deepseek-flash")

    assert missing_fields(excinfo.value) == {"model"}


def test_normalize_model_adds_prefix() -> None:
    assert normalize_model("deepseek", "deepseek-chat") == "deepseek/deepseek-chat"
    assert normalize_model("openai", "openai/gpt-4o-mini") == "openai/gpt-4o-mini"
    assert (
        normalize_model("openrouter", "anthropic/claude-3.5")
        == "openrouter/anthropic/claude-3.5"
    )


def test_normalize_model_other_requires_slash() -> None:
    assert normalize_model("other", "mistral/mistral-large") == (
        "mistral/mistral-large"
    )
    with pytest.raises(ValueError):
        normalize_model("other", "llama3")


def test_suggest_workspace_returns_parent_of_venv(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    scripts = project / ".venv" / "Scripts"
    scripts.mkdir(parents=True)
    (project / ".venv" / "pyvenv.cfg").write_text("", encoding="utf-8")

    assert suggest_workspace(scripts) == project.resolve()


def test_suggest_workspace_defaults_to_start(tmp_path: Path) -> None:
    sub = tmp_path / "sub"
    sub.mkdir()

    assert suggest_workspace(sub) == sub.resolve()


def test_run_onboarding_saves_and_returns_settings(
    isolated_config: Path, monkeypatch
) -> None:
    config = isolated_config / "config.env"
    monkeypatch.setattr("judgman.onboarding.getpass.getpass", lambda *a, **k: "secret")
    monkeypatch.setattr(
        "judgman.onboarding.verify_connection", lambda *a, **k: (True, "")
    )
    answers = iter(["3", "deepseek-chat", str(isolated_config)])
    monkeypatch.setattr("builtins.input", lambda *a, **k: next(answers))

    settings = run_onboarding(make_console(), path=config)

    assert settings.model == "deepseek/deepseek-chat"
    assert settings.api_key.get_secret_value() == "secret"
    assert settings.workspace == isolated_config.resolve()
    assert config.is_file()


def test_missing_fields_detects_api_key(isolated_config: Path) -> None:
    with pytest.raises(ValidationError) as excinfo:
        load_settings(user_config=isolated_config / "missing.env")

    assert missing_fields(excinfo.value) == {"api_key"}


def test_resolve_settings_aborts_without_tty(
    isolated_config: Path, monkeypatch
) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO())
    args = build_parser().parse_args([])

    with pytest.raises(SystemExit):
        resolve_settings(args, make_console())


class _FakeTty:
    def isatty(self) -> bool:
        return True


def test_resolve_settings_onboards_on_invalid_model(
    isolated_config: Path, monkeypatch
) -> None:
    user = isolated_config / "appdata" / "judgman" / "config.env"
    save_user_config(
        {
            "JUDGMAN_API_KEY": "secret",
            "JUDGMAN_MODEL": "deepseek-flash",
            "JUDGMAN_WORKSPACE": str(isolated_config),
        },
        path=user,
    )
    monkeypatch.setattr("sys.stdin", _FakeTty())
    monkeypatch.setattr(
        "judgman.cli.run_onboarding",
        lambda console: Settings(
            _env_file=None,
            api_key="secret",
            model="deepseek/deepseek-chat",
            workspace=isolated_config,
        ),
    )
    args = build_parser().parse_args([])

    settings = resolve_settings(args, make_console())

    assert settings.model == "deepseek/deepseek-chat"
