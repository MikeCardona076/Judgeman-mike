from pathlib import Path
from threading import Event
from unittest.mock import patch

import pytest
from watchdog.events import DirCreatedEvent, FileCreatedEvent, FileModifiedEvent

from judgman.core.scanner import ReadOnlyScanner


def test_created_and_modified_events_record_metadata_only(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    tracked_file = workspace / "example.py"
    tracked_file.write_text("original content", encoding="utf-8")
    scanner = ReadOnlyScanner(workspace)

    with (
        patch.object(Path, "write_text", side_effect=AssertionError("write attempted")),
        patch.object(Path, "unlink", side_effect=AssertionError("delete attempted")),
    ):
        scanner.on_created(FileCreatedEvent(str(tracked_file)))
        scanner.on_modified(FileModifiedEvent(str(tracked_file)))

    assert tracked_file.read_text(encoding="utf-8") == "original content"
    assert [event["event"] for event in scanner.recent_events()] == [
        "modified",
        "created",
    ]
    assert all(event["path"] == "example.py" for event in scanner.recent_events())


def test_ignores_directory_events(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    scanner = ReadOnlyScanner(workspace)

    scanner.on_created(DirCreatedEvent(str(workspace / "new-folder")))

    assert scanner.recent_events() == []


def test_rejects_file_event_outside_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("unchanged", encoding="utf-8")
    scanner = ReadOnlyScanner(workspace)

    with pytest.raises(PermissionError):
        scanner.on_modified(FileModifiedEvent(str(outside)))

    assert outside.read_text(encoding="utf-8") == "unchanged"


def test_analyzes_text_file_without_writing_it(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    tracked_file = workspace / "notes.txt"
    tracked_file.write_text("a harmless note", encoding="utf-8")
    analyzed = Event()
    submitted: list[str] = []

    def analyze(content: str) -> str:
        submitted.append(content)
        analyzed.set()
        return "Explicacion educativa"

    scanner = ReadOnlyScanner(workspace, analyzer=analyze)
    scanner.start()
    try:
        scanner.on_modified(FileModifiedEvent(str(tracked_file)))
        assert analyzed.wait(timeout=3)
        latest = scanner.recent_events()[0]
        assert submitted == ["a harmless note"]
        assert latest["status"] == "analyzed"
        assert latest["analysis"] == "Explicacion educativa"
        assert tracked_file.read_text(encoding="utf-8") == "a harmless note"
    finally:
        scanner.stop()


def test_skips_sensitive_files_without_sending_content(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    secret_file = workspace / ".env"
    secret_file.write_text("SECRET=do-not-send", encoding="utf-8")
    submitted: list[str] = []

    def analyze(content: str) -> str:
        submitted.append(content)
        return "Unexpected analysis"

    scanner = ReadOnlyScanner(workspace, analyzer=analyze)
    scanner.start()
    try:
        scanner.on_created(FileCreatedEvent(str(secret_file)))
        for _ in range(30):
            if scanner.recent_events()[0]["status"] != "pending":
                break
            Event().wait(0.1)
        latest = scanner.recent_events()[0]
        assert latest["status"] == "skipped"
        assert submitted == []
    finally:
        scanner.stop()


def test_skips_binary_files(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    binary_file = workspace / "image.bin"
    binary_file.write_bytes(b"\x00\x01\x02")
    submitted: list[str] = []

    def analyze(content: str) -> str:
        submitted.append(content)
        return "Unexpected analysis"

    scanner = ReadOnlyScanner(workspace, analyzer=analyze)
    scanner.start()
    try:
        scanner.on_created(FileCreatedEvent(str(binary_file)))
        for _ in range(30):
            if scanner.recent_events()[0]["status"] != "pending":
                break
            Event().wait(0.1)
        latest = scanner.recent_events()[0]
        assert latest["status"] == "skipped"
        assert submitted == []
    finally:
        scanner.stop()
