import logging
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from queue import Empty, Full, Queue
from threading import Event, Lock, Thread
from typing import Callable

from watchdog.events import FileSystemEvent, FileSystemEventHandler

from judgman.core.files import FileSkipped, read_text_file
from judgman.core.permissions import resolve_within_workspace

logger = logging.getLogger(__name__)
_DEBOUNCE_SECONDS = 0.4
_MAX_PENDING_FILES = 100


@dataclass(frozen=True)
class FileChange:
    event_id: int
    path: str
    event: str
    timestamp: str
    status: str
    analysis: str | None = None
    detail: str | None = None


class ReadOnlyScanner(FileSystemEventHandler):
    """Observa el workspace y analiza cambios sin modificar los archivos."""

    def __init__(
        self,
        workspace: Path,
        analyzer: Callable[[str], str] | None = None,
        max_events: int = 100,
        max_file_bytes: int = 131072,
    ) -> None:
        self.workspace = workspace.expanduser().resolve()
        if not self.workspace.is_dir():
            raise ValueError(f"El workspace no es un directorio: {self.workspace}")
        if max_events < 1:
            raise ValueError("max_events debe ser mayor que cero")
        if max_file_bytes < 1:
            raise ValueError("max_file_bytes debe ser mayor que cero")
        self._events: deque[FileChange] = deque(maxlen=max_events)
        self._lock = Lock()
        self._analyzer = analyzer
        self._max_file_bytes = max_file_bytes
        self._queue: Queue[tuple[int, Path]] = Queue(maxsize=_MAX_PENDING_FILES)
        self._latest_by_path: dict[str, int] = {}
        self._next_event_id = 0
        self._stop_event = Event()
        self._worker: Thread | None = None

    def on_created(self, event: FileSystemEvent) -> None:
        self._record(event, "created")

    def on_modified(self, event: FileSystemEvent) -> None:
        self._record(event, "modified")

    def recent_events(self) -> list[dict[str, str | None]]:
        with self._lock:
            return [
                {
                    "path": item.path,
                    "event": item.event,
                    "timestamp": item.timestamp,
                    "status": item.status,
                    "analysis": item.analysis,
                    "detail": item.detail,
                }
                for item in reversed(self._events)
            ]

    def start(self) -> None:
        """Inicia el trabajador que lee y analiza eventos en segundo plano."""
        if self._analyzer is None:
            raise RuntimeError("Se requiere un analizador para iniciar el scanner")
        if self._worker is not None and self._worker.is_alive():
            raise RuntimeError("El scanner ya está iniciado")
        self._stop_event.clear()
        self._worker = Thread(
            target=self._process_queue,
            name="judgman-file-analyzer",
            daemon=True,
        )
        self._worker.start()

    def stop(self, timeout: float = 5) -> None:
        """Detiene el trabajador sin modificar archivos pendientes."""
        self._stop_event.set()
        worker = self._worker
        if worker is not None:
            worker.join(timeout=timeout)
            if worker.is_alive():
                logger.warning("El trabajador de análisis no terminó dentro del plazo")

    def _record(self, event: FileSystemEvent, event_name: str) -> None:
        if event.is_directory:
            return

        try:
            path = resolve_within_workspace(self.workspace, event.src_path)
            relative_path = path.relative_to(self.workspace).as_posix()
        except (OSError, PermissionError, ValueError) as exc:
            raise PermissionError(
                f"Evento de archivo rechazado por el limite del workspace: "
                f"{event.src_path}"
            ) from exc

        with self._lock:
            self._next_event_id += 1
            event_id = self._next_event_id
            self._latest_by_path[relative_path] = event_id
            status = "pending" if self._analyzer else "observed"
            detail = None
            if self._analyzer is not None and self._worker is not None:
                try:
                    self._queue.put_nowait((event_id, path))
                except Full:
                    status = "error"
                    detail = "Cola de análisis llena; el archivo no se analizó."
            if len(self._events) == self._events.maxlen:
                oldest = self._events[0]
                if self._latest_by_path.get(oldest.path) == oldest.event_id:
                    self._latest_by_path.pop(oldest.path, None)
            change = FileChange(
                event_id=event_id,
                path=relative_path,
                event=event_name,
                timestamp=datetime.now(timezone.utc).isoformat(),
                status=status,
                detail=detail,
            )
            self._events.append(change)
            if detail is not None:
                logger.error("Cola de análisis llena; evento rechazado: %s", path)

    def _process_queue(self) -> None:
        while not self._stop_event.is_set():
            try:
                event_id, path = self._queue.get(timeout=0.2)
            except Empty:
                continue

            if self._stop_event.wait(_DEBOUNCE_SECONDS):
                break
            with self._lock:
                relative_path = path.relative_to(self.workspace).as_posix()
                if self._latest_by_path.get(relative_path) != event_id:
                    continue

            try:
                content = self._read_text_file(path, event_id)
                if content is None:
                    continue
                with self._lock:
                    if self._latest_by_path.get(relative_path) != event_id:
                        continue
                if self._analyzer is None:
                    raise RuntimeError("El analizador no está configurado")
                analysis = self._analyzer(content)
                with self._lock:
                    if self._latest_by_path.get(relative_path) != event_id:
                        continue
                self._replace_change(
                    event_id,
                    status="analyzed",
                    analysis=analysis,
                    detail=None,
                )
            except (OSError, PermissionError, UnicodeError, ValueError) as exc:
                logger.warning("No se pudo leer el archivo %s: %s", path, exc)
                self._replace_change(
                    event_id,
                    status="skipped",
                    detail=str(exc),
                )
            except Exception:
                logger.exception("No se pudo analizar el archivo %s", path)
                self._replace_change(
                    event_id,
                    status="error",
                    detail="El análisis falló; consulta el registro local.",
                )

    def _read_text_file(self, path: Path, event_id: int) -> str | None:
        """Lee únicamente archivos de texto validados y con tamaño limitado."""
        try:
            return read_text_file(self.workspace, path, self._max_file_bytes)
        except FileSkipped as exc:
            self._replace_change(event_id, status="skipped", detail=exc.detail)
            return None

    def _replace_change(
        self,
        event_id: int,
        status: str,
        analysis: str | None = None,
        detail: str | None = None,
    ) -> None:
        with self._lock:
            for index, change in enumerate(self._events):
                if change.event_id == event_id:
                    self._events[index] = FileChange(
                        event_id=change.event_id,
                        path=change.path,
                        event=change.event,
                        timestamp=change.timestamp,
                        status=status,
                        analysis=analysis,
                        detail=detail,
                    )
                    return
