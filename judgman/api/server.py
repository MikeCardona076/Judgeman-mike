import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from judgman.config import Settings
from judgman.core.analyzer import Analyzer
from judgman.core.scanner import ReadOnlyScanner
from judgman.core.system_info import collect_system_snapshot

logger = logging.getLogger(__name__)
UI_DIRECTORY = Path(__file__).resolve().parents[1] / "ui"


class AnalyzeRequest(BaseModel):
    code: str = Field(min_length=1, max_length=40_000)


class AnalyzeResponse(BaseModel):
    analysis: str


class SystemRequest(BaseModel):
    question: str = Field(min_length=1)


class SystemResponse(BaseModel):
    answer: str


def create_app(
    settings: Settings,
    scanner: ReadOnlyScanner,
    analyzer: Analyzer | None = None,
) -> FastAPI:
    app = FastAPI(
        title="JudgeMan-Mike",
        description="API local de solo lectura para diagnostico y seguridad.",
        docs_url=None,
        redoc_url=None,
    )
    app.state.scanner = scanner
    app.state.analyzer = analyzer or Analyzer(
        model=settings.model,
        api_key=settings.api_key.get_secret_value(),
    )
    app.mount("/static", StaticFiles(directory=UI_DIRECTORY), name="static")

    def _snapshot() -> dict[str, object]:
        return collect_system_snapshot(
            settings.workspace,
            path_tools_limit=settings.path_tools_limit,
        )

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(UI_DIRECTORY / "index.html")

    @app.get("/api/events")
    def get_events() -> list[dict[str, str | None]]:
        return scanner.recent_events()

    @app.post("/api/analyze", response_model=AnalyzeResponse)
    def analyze(request: AnalyzeRequest) -> AnalyzeResponse:
        try:
            result = app.state.analyzer.analyze(request.code)
        except Exception as exc:
            logger.exception("No se pudo analizar el texto")
            raise HTTPException(
                status_code=502,
                detail="El proveedor de analisis no pudo completar la solicitud.",
            ) from exc
        return AnalyzeResponse(analysis=result)

    @app.get("/api/system/snapshot")
    def system_snapshot() -> dict[str, object]:
        if not settings.enable_system_info:
            raise HTTPException(status_code=404, detail="Funcion deshabilitada.")
        return _snapshot()

    @app.post("/api/system", response_model=SystemResponse)
    def analyze_system(request: SystemRequest) -> SystemResponse:
        if not settings.enable_system_info:
            raise HTTPException(status_code=404, detail="Funcion deshabilitada.")
        question = request.question.strip()
        if not question:
            raise HTTPException(status_code=422, detail="La pregunta no puede estar vacia.")
        if len(question) > settings.max_question_chars:
            raise HTTPException(
                status_code=422,
                detail=(
                    "La pregunta supera el limite de "
                    f"{settings.max_question_chars} caracteres."
                ),
            )
        try:
            result = app.state.analyzer.analyze_system(question, _snapshot())
        except Exception as exc:
            logger.exception("No se pudo responder la pregunta del sistema")
            raise HTTPException(
                status_code=502,
                detail="El proveedor de analisis no pudo completar la solicitud.",
            ) from exc
        return SystemResponse(answer=result)

    return app
