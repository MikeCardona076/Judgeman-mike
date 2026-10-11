from pathlib import Path

from judgman import paths


def test_user_config_dir_on_windows(tmp_path: Path) -> None:
    env = {"APPDATA": str(tmp_path / "appdata")}

    assert paths.user_config_dir(env=env, platform="nt") == (
        tmp_path / "appdata" / "judgman"
    )


def test_user_config_dir_respects_xdg(tmp_path: Path) -> None:
    env = {"XDG_CONFIG_HOME": str(tmp_path / "cfg")}

    assert paths.user_config_dir(env=env, platform="posix") == (
        tmp_path / "cfg" / "judgman"
    )


def test_user_config_dir_falls_back_to_home(tmp_path: Path) -> None:
    env = {"HOME": str(tmp_path)}

    assert paths.user_config_dir(env=env, platform="posix") == (
        tmp_path / ".config" / "judgman"
    )


def test_user_config_path_points_to_config_env(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(paths.os, "name", "nt")
    monkeypatch.setenv("APPDATA", str(tmp_path))

    assert paths.user_config_path() == tmp_path / "judgman" / "config.env"
