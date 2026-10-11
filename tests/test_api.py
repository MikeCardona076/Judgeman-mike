from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from judgman.api.server import create_app
from judgman.config import Settings
from judgman.core.scanner import ReadOnlyScanner


class FakeAnalyzer:
    def __init__(self) -> None:
        self.last_system_call: tuple[str, dict[str, object]] | None = None

    def analyze(self, content: str) -> str:
        return "Analisis educativo"

    def analyze_system(self, question: str, snapshot: dict[str, object]) -> str:
        self.last_system_call = (question, snapshot)
        return "Respuesta sobre el sistema"


def build_client(tmp_path: Path, **overrides: object) -> tuple[TestClient, FakeAnalyzer]:
    workspace = tmp_path / "workspace"
    workspace.mkdir(exist_ok=True)
    settings = Settings(
        _env_file=None,
        api_key="test-key",
        workspace=workspace,
        **overrides,
    )
    scanner = ReadOnlyScanner(workspace)
    analyzer = FakeAnalyzer()
    app = create_app(settings, scanner, analyzer=analyzer)
    return TestClient(app), analyzer


def test_system_snapshot_endpoint_returns_data(tmp_path: Path) -> None:
    client, _ = build_client(tmp_path)

    response = client.get("/api/system/snapshot")

    assert response.status_code == 200
    assert "os_name" in response.json()


def test_system_endpoint_answers_question(tmp_path: Path) -> None:
    client, analyzer = build_client(tmp_path)

    response = client.post("/api/system", json={"question": "Cuantas CPUs tengo?"})

    assert response.status_code == 200
    assert response.json()["answer"] == "Respuesta sobre el sistema"
    assert analyzer.last_system_call is not None
    question, snapshot = analyzer.last_system_call
    assert question == "Cuantas CPUs tengo?"
    assert "cpu_count" in snapshot


def test_system_endpoint_rejects_blank_question(tmp_path: Path) -> None:
    client, _ = build_client(tmp_path)

    response = client.post("/api/system", json={"question": "   "})

    assert response.status_code == 422


def test_system_endpoint_rejects_long_question(tmp_path: Path) -> None:
    client, _ = build_client(tmp_path, max_question_chars=10)

    response = client.post("/api/system", json={"question": "x" * 20})

    assert response.status_code == 422


def test_system_endpoints_disabled_return_404(tmp_path: Path) -> None:
    client, _ = build_client(tmp_path, enable_system_info=False)

    assert client.get("/api/system/snapshot").status_code == 404
    assert client.post("/api/system", json={"question": "hola"}).status_code == 404
