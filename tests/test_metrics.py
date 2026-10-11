from pathlib import Path

import judgman.core.metrics as metrics
from judgman.core.metrics import Metrics, MetricsSampler


class FakeMemory:
    percent = 42.0
    used = 4 * 1024**3
    total = 8 * 1024**3


class FakeDisk:
    percent = 30.0
    used = 30 * 1024**3
    total = 100 * 1024**3


class FakePsutil:
    def cpu_percent(self, interval=None, percpu=False):
        if percpu:
            return [10.0, 20.0]
        return 55.0

    def virtual_memory(self):
        return FakeMemory()

    def pids(self):
        return [1, 2, 3, 4]

    def disk_usage(self, path):
        return FakeDisk()


def test_sampler_with_psutil_reports_all_metrics(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(metrics, "psutil", FakePsutil())
    sampler = MetricsSampler(workspace=tmp_path, use_psutil=True)

    result = sampler.sample(force=True)

    assert isinstance(result, Metrics)
    assert result.available is True
    assert result.cpu_percent == 55.0
    assert result.per_core == (10.0, 20.0)
    assert result.mem_percent == 42.0
    assert result.mem_total_mb == 8192.0
    assert result.process_count == 4
    assert result.disk_percent == 30.0
    assert result.note is None


def test_sampler_falls_back_without_psutil(monkeypatch) -> None:
    monkeypatch.setattr(metrics, "psutil", None)
    monkeypatch.setattr(
        metrics,
        "collect_system_snapshot",
        lambda workspace: {
            "memory_total_mb": 8000.0,
            "memory_available_mb": 2000.0,
            "disk_total_gb": 100.0,
            "disk_free_gb": 40.0,
        },
    )
    sampler = MetricsSampler(use_psutil=False)

    result = sampler.sample(force=True)

    assert result.available is False
    assert result.mem_percent == 75.0
    assert result.mem_used_mb == 6000.0
    assert result.disk_percent == 60.0
    assert result.disk_used_gb == 60.0
    assert result.note


def test_sampler_caches_within_interval(monkeypatch) -> None:
    monkeypatch.setattr(metrics, "psutil", None)
    monkeypatch.setattr(
        metrics,
        "collect_system_snapshot",
        lambda workspace: {"memory_total_mb": 100.0, "memory_available_mb": 50.0},
    )
    sampler = MetricsSampler(use_psutil=False, interval=60.0)

    first = sampler.sample()
    second = sampler.sample()

    assert first is second


def test_sampler_force_bypasses_cache(monkeypatch) -> None:
    monkeypatch.setattr(metrics, "psutil", None)
    monkeypatch.setattr(
        metrics,
        "collect_system_snapshot",
        lambda workspace: {"memory_total_mb": 100.0, "memory_available_mb": 50.0},
    )
    sampler = MetricsSampler(use_psutil=False, interval=60.0)

    first = sampler.sample()
    second = sampler.sample(force=True)

    assert first is not second
