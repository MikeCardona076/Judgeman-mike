from pathlib import Path

from judgman.core.system_info import collect_system_snapshot


def test_snapshot_has_expected_benign_keys(tmp_path: Path) -> None:
    snapshot = collect_system_snapshot(tmp_path, use_cache=False)

    for key in (
        "os_name",
        "os_release",
        "architecture",
        "python_version",
        "cpu_count",
        "timezone_name",
        "env_var_names",
        "path_tools",
    ):
        assert key in snapshot

    assert isinstance(snapshot["env_var_names"], list)
    assert isinstance(snapshot["path_tools"], list)


def test_snapshot_includes_disk_usage_for_workspace(tmp_path: Path) -> None:
    snapshot = collect_system_snapshot(tmp_path, use_cache=False)

    assert snapshot["disk_total_gb"] > 0
    assert snapshot["disk_free_gb"] >= 0


def test_snapshot_omits_identifiable_fields(tmp_path: Path) -> None:
    snapshot = collect_system_snapshot(tmp_path, use_cache=False)

    for forbidden in ("hostname", "username", "user", "home", "workspace"):
        assert forbidden not in snapshot


def test_env_values_are_never_included(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LEAK_ME_VALUE", "super-secret-value")
    snapshot = collect_system_snapshot(tmp_path, use_cache=False)

    assert "super-secret-value" not in str(snapshot)
    assert "LEAK_ME_VALUE" in snapshot["env_var_names"]


def test_sensitive_env_names_are_filtered(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MY_APP_API_KEY", "x")
    monkeypatch.setenv("MY_APP_TOKEN", "x")
    monkeypatch.setenv("MY_APP_PASSWORD", "x")
    snapshot = collect_system_snapshot(tmp_path, use_cache=False)

    names = snapshot["env_var_names"]
    assert "MY_APP_API_KEY" not in names
    assert "MY_APP_TOKEN" not in names
    assert "MY_APP_PASSWORD" not in names


def test_path_tools_are_capped(tmp_path: Path) -> None:
    snapshot = collect_system_snapshot(tmp_path, path_tools_limit=5, use_cache=False)

    assert len(snapshot["path_tools"]) <= 5
