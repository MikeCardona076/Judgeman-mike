"""Muestreo de metricas del sistema para el HUD de la consola Tron.

Usa ``psutil`` si esta disponible (extra ``monitor``). Si no, degrada a los
datos no sensibles de :mod:`judgman.core.system_info` (memoria y disco), de modo
que el chat siempre funciona, marcando ``available=False``.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from judgman.core.system_info import collect_system_snapshot

try:  # pragma: no cover - depende del entorno
    import psutil
except ImportError:  # pragma: no cover
    psutil = None  # type: ignore[assignment]

PSUTIL_HINT = "psutil no instalado: pip install 'judgman-mike[monitor]'"


@dataclass(frozen=True)
class Metrics:
    """Lectura puntual del estado del sistema."""

    available: bool
    cpu_percent: float = 0.0
    per_core: tuple[float, ...] = field(default_factory=tuple)
    mem_percent: float = 0.0
    mem_used_mb: float = 0.0
    mem_total_mb: float = 0.0
    disk_percent: float = 0.0
    disk_used_gb: float = 0.0
    disk_total_gb: float = 0.0
    process_count: int = 0
    note: str | None = None


class MetricsSampler:
    """Cachea una lectura de metricas durante un intervalo minimo."""

    def __init__(
        self,
        workspace: Path | None = None,
        interval: float = 1.0,
        use_psutil: bool | None = None,
    ) -> None:
        self.workspace = workspace
        self.interval = interval
        self._use_psutil = (psutil is not None) if use_psutil is None else use_psutil
        self._lock = threading.Lock()
        self._last: Metrics | None = None
        self._last_at = 0.0
        if self._use_psutil and psutil is not None:
            try:  # primer llamado no bloqueante para tener base de CPU
                psutil.cpu_percent(interval=None)
            except Exception:  # pragma: no cover - defensivo
                self._use_psutil = False

    def sample(self, force: bool = False) -> Metrics:
        with self._lock:
            now = time.monotonic()
            if (
                not force
                and self._last is not None
                and (now - self._last_at) < self.interval
            ):
                return self._last
            metrics = self._collect()
            self._last = metrics
            self._last_at = now
            return metrics

    def _collect(self) -> Metrics:
        if self._use_psutil and psutil is not None:
            try:
                return self._collect_psutil()
            except Exception as exc:  # pragma: no cover - defensivo
                return self._collect_fallback(f"psutil fallo: {exc}")
        return self._collect_fallback(PSUTIL_HINT)

    def _collect_psutil(self) -> Metrics:
        vm = psutil.virtual_memory()
        metrics = Metrics(
            available=True,
            cpu_percent=round(psutil.cpu_percent(interval=None), 1),
            per_core=tuple(
                round(value, 1)
                for value in psutil.cpu_percent(interval=None, percpu=True)
            ),
            mem_percent=round(vm.percent, 1),
            mem_used_mb=round(vm.used / (1024**2), 1),
            mem_total_mb=round(vm.total / (1024**2), 1),
            process_count=len(psutil.pids()),
        )
        if self.workspace is not None:
            try:
                usage = psutil.disk_usage(str(self.workspace))
                metrics = _with_disk(
                    metrics,
                    percent=round(usage.percent, 1),
                    used_gb=round(usage.used / (1024**3), 1),
                    total_gb=round(usage.total / (1024**3), 1),
                )
            except Exception:  # pragma: no cover - disco no disponible
                pass
        return metrics

    def _collect_fallback(self, note: str | None) -> Metrics:
        snapshot = collect_system_snapshot(self.workspace)
        total = _as_float(snapshot.get("memory_total_mb"))
        free = _as_float(snapshot.get("memory_available_mb"))
        used = total - free if (total is not None and free is not None) else None
        mem_percent = 0.0
        if total and used is not None:
            mem_percent = round(min(used / total, 1.0) * 100, 1)

        disk_total = _as_float(snapshot.get("disk_total_gb"))
        disk_free = _as_float(snapshot.get("disk_free_gb"))
        disk_percent = 0.0
        disk_used = 0.0
        if disk_total and disk_free is not None:
            disk_used = round(disk_total - disk_free, 1)
            disk_percent = round(min(disk_used / disk_total, 1.0) * 100, 1)

        return Metrics(
            available=False,
            mem_percent=mem_percent,
            mem_used_mb=used or 0.0,
            mem_total_mb=total or 0.0,
            disk_percent=disk_percent,
            disk_used_gb=disk_used,
            disk_total_gb=disk_total or 0.0,
            note=note,
        )


def _with_disk(
    metrics: Metrics,
    percent: float,
    used_gb: float,
    total_gb: float,
) -> Metrics:
    return Metrics(
        available=metrics.available,
        cpu_percent=metrics.cpu_percent,
        per_core=metrics.per_core,
        mem_percent=metrics.mem_percent,
        mem_used_mb=metrics.mem_used_mb,
        mem_total_mb=metrics.mem_total_mb,
        disk_percent=percent,
        disk_used_gb=used_gb,
        disk_total_gb=total_gb,
        process_count=metrics.process_count,
        note=metrics.note,
    )


def _as_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None
