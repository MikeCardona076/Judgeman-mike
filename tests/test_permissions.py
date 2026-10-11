from pathlib import Path

import pytest

from judgman.core.permissions import resolve_within_workspace


def test_accepts_relative_path_inside_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    assert resolve_within_workspace(workspace, "src/main.py") == (
        workspace / "src" / "main.py"
    )


def test_rejects_parent_directory_traversal(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    with pytest.raises(PermissionError):
        resolve_within_workspace(workspace, "../../../etc/passwd")


def test_rejects_absolute_path_outside_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "secret.txt"

    with pytest.raises(PermissionError):
        resolve_within_workspace(workspace, outside)


def test_rejects_symlink_that_points_outside_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("not for the scanner", encoding="utf-8")
    link = workspace / "link.txt"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("El sistema no permite crear enlaces simbolicos")

    with pytest.raises(PermissionError):
        resolve_within_workspace(workspace, link)
