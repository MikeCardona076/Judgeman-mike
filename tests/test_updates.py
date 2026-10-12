import urllib.error
from pathlib import Path

import judgman.updates as updates


def test_parse_version_reads_assignment() -> None:
    assert updates.parse_version('__version__ = "1.2.3"') == "1.2.3"
    assert updates.parse_version("__version__ = '4.5.6'\n") == "4.5.6"
    assert updates.parse_version("sin version aqui") is None


def test_is_newer_handles_prefix_and_suffix() -> None:
    assert updates.is_newer("0.2.0", "0.1.0")
    assert updates.is_newer("v0.2.0", "0.1.9")
    assert updates.is_newer("1.0.1", "1.0")
    assert updates.is_newer("0.2.0-rc1", "0.1.0")
    assert not updates.is_newer("0.1.0", "0.1.0")
    assert not updates.is_newer("0.1", "0.1.0")
    assert not updates.is_newer("1.0.0", "1.0")
    assert not updates.is_newer("0.1.0", "0.2.0")


def test_check_for_update_uses_cache_on_second_call(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(updates, "cache_path", lambda: tmp_path / "update.json")
    calls: list[float] = []

    def fake_fetch(timeout):
        calls.append(timeout)
        return "9.9.9"

    info = updates.check_for_update("0.1.0", fetcher=fake_fetch)
    assert info.latest == "9.9.9"
    assert info.available is True
    assert calls == [updates.DEFAULT_TIMEOUT]

    def _boom(timeout):  # no debe llamarse: la cache es reciente
        raise AssertionError("no deberia salir a la red")

    info2 = updates.check_for_update("0.1.0", fetcher=_boom)
    assert info2.latest == "9.9.9"
    assert info2.available is True


def test_check_for_update_force_refetches(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(updates, "cache_path", lambda: tmp_path / "u.json")
    values = iter(["1.0.0", "1.1.0"])

    info1 = updates.check_for_update("1.0.0", fetcher=lambda _t: next(values))
    info2 = updates.check_for_update(
        "1.0.0", force=True, fetcher=lambda _t: next(values)
    )

    assert info1.available is False
    assert info2.latest == "1.1.0"
    assert info2.available is True


def test_check_for_update_offline_without_cache(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(updates, "cache_path", lambda: tmp_path / "missing.json")

    info = updates.check_for_update("0.1.0", allow_network=False)

    assert info.latest is None
    assert info.available is False
    assert info.error


def test_fetch_latest_version_returns_none_on_network_error(monkeypatch) -> None:
    def boom(*_args, **_kwargs):
        raise urllib.error.URLError("offline")

    monkeypatch.setattr(updates.urllib.request, "urlopen", boom)

    assert updates.fetch_latest_version() is None


def test_update_command_for_pip_and_pipx() -> None:
    pip = updates.update_command("pip")
    assert pip[0] == updates.sys.executable
    assert pip[1:3] == ["-m", "pip"]
    assert pip[-1] == updates.GIT_URL

    pipx = updates.update_command("pipx")
    assert pipx[:3] == ["pipx", "install", "--force"]
    assert pipx[-1] == updates.GIT_URL


def test_detect_installer_prefers_pipx_env(monkeypatch) -> None:
    monkeypatch.setenv("PIPX_HOME", str(Path.home()))
    assert updates.detect_installer() == "pipx"


class _Proc:
    def __init__(self, code: int, out: bytes = b"", err: bytes = b"") -> None:
        self.returncode = code
        self.stdout = out
        self.stderr = err


def test_perform_update_ok(monkeypatch) -> None:
    monkeypatch.setattr(updates.subprocess, "run", lambda *a, **k: _Proc(0, b"len"))
    ok, message = updates.perform_update("pip")
    assert ok is True
    assert message == "len"


def test_perform_update_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        updates.subprocess, "run", lambda *a, **k: _Proc(1, b"", b"boom")
    )
    ok, message = updates.perform_update("pip")
    assert ok is False
    assert message == "boom"
