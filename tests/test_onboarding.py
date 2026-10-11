import io
import os
from pathlib import Path

import pytest
from pydantic import ValidationError
from rich.console import Console

from judgman.cli import build_parser, resolve_settings
from judgman.config import load_settings, missing_fields
from judgman.onboarding import run_onboarding, save_user_config


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
    return Console(file=io.StringIO())


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
            "JUDGMAN_MODEL": "from-user",
            "JUDGMAN_WORKSPACE": str(isolated_config),
        },
        path=user,
    )
    (isolated_config / ".env").write_text(
        'JUDGMAN_MODEL="from-local"\n', encoding="utf-8"
    )

    assert load_settings(user_config=user).model == "from-local"


def test_run_onboarding_saves_and_returns_settings(
    isolated_config: Path, monkeypatch
) -> None:
    config = isolated_config / "cfg" / "config.env"
    monkeypatch.setattr(
        "judgman.onboarding.getpass.getpass", lambda *a, **k: "typed-key"
    )
    answers = iter(["openai/gpt-4o-mini", str(isolated_config)])
    monkeypatch.setattr("builtins.input", lambda *a, **k: next(answers))

    settings = run_onboarding(make_console(), path=config)

    assert settings.api_key.get_secret_value() == "typed-key"
    assert settings.model == "openai/gpt-4o-mini"
    assert settings.workspace == isolated_config.resolve()
    assert "typed-key" in config.read_text(encoding="utf-8")


def test_missing_fields_reports_api_key(isolated_config: Path) -> None:
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
