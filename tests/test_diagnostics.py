from __future__ import annotations

import socket
from pathlib import Path

import pytest

import judgman.core.diagnostics as diag
from judgman.core.actions import CommandResult


class FakeAddr:
    def __init__(self, ip: str, port: int) -> None:
        self.ip = ip
        self.port = port


class FakeConn:
    def __init__(self, status, laddr, raddr=None, pid=0, type_=socket.SOCK_STREAM):
        self.status = status
        self.laddr = laddr
        self.raddr = raddr
        self.pid = pid
        self.type = type_


class FakeProcess:
    def __init__(self, pid, name, cpu, mem, user, exe):
        self.info = {
            "pid": pid,
            "name": name,
            "username": user,
            "memory_percent": mem,
            "exe": exe,
        }
        self._cpu = cpu

    def cpu_percent(self, interval=None):
        return self._cpu

    def name(self):
        return self.info["name"]


class FakePsutil:
    CONN_LISTEN = "LISTEN"
    CONN_ESTABLISHED = "ESTABLISHED"
    CONN_SYN_SENT = "SYN_SENT"

    def __init__(self):
        self.conns = [
            FakeConn(self.CONN_LISTEN, FakeAddr("0.0.0.0", 8080), pid=42),
            FakeConn(self.CONN_LISTEN, FakeAddr("127.0.0.1", 8765), pid=7),
            FakeConn(
                self.CONN_ESTABLISHED,
                FakeAddr("127.0.0.1", 51000),
                FakeAddr("93.184.216.34", 443),
                pid=42,
            ),
        ]
        self.procs = [
            FakeProcess(42, "servicio", 12.5, 3.0, "alice", r"C:\srv.exe"),
            FakeProcess(7, "idle", 0.0, 0.5, "alice", r"C:\idle.exe"),
        ]

    def net_connections(self, kind="inet"):
        return self.conns

    def process_iter(self, attrs=None):
        return list(self.procs)

    def Process(self, pid):
        for proc in self.procs:
            if proc.info["pid"] == pid:
                return proc
        raise ProcessLookupError


@pytest.fixture()
def fake_psutil(monkeypatch):
    fake = FakePsutil()
    monkeypatch.setattr(diag, "psutil", fake)
    diag._cache = None
    return fake


def test_listening_ports_lists_only_listen(fake_psutil) -> None:
    data = diag.listening_ports()

    assert data["available"] is True
    ports = {entry["port"] for entry in data["entries"]}
    assert ports == {8080, 8765}
    assert all(entry["protocol"] == "TCP" for entry in data["entries"])


def test_connections_lists_established(fake_psutil) -> None:
    data = diag.connections()

    assert data["available"] is True
    assert data["entries"][0]["remote"] == "93.184.216.34:443"


def test_top_processes_sorted_by_cpu(fake_psutil) -> None:
    data = diag.top_processes(sample_seconds=0.0)

    assert data["entries"][0]["name"] == "servicio"


def test_psutil_missing_degrades(monkeypatch) -> None:
    monkeypatch.setattr(diag, "psutil", None)

    data = diag.listening_ports()

    assert data["available"] is False
    assert "psutil" in data["note"]


def test_check_port_listening(fake_psutil) -> None:
    info = diag.check_port(8080, diag.listening_ports())

    assert info["verdict"] == "listening"
    assert info["listeners"][0]["process"] == "servicio"


def test_check_port_not_listening() -> None:
    ports = {"available": True, "note": None, "entries": []}

    info = diag.check_port(9999, ports)

    assert info["verdict"] == "not_listening"


def test_services_uses_readonly_command(monkeypatch) -> None:
    monkeypatch.setattr(diag, "psutil", None)
    output = (
        "SERVICE_NAME: spooler\n"
        "        STATE   : 4  RUNNING\n"
        "SERVICE_NAME: roto\n"
        "        STATE   : 1  STOPPED\n"
    )

    def fake_runner(argv, timeout=8.0):
        return CommandResult(tuple(argv), True, output)

    monkeypatch.setattr(diag, "_command_runner", fake_runner)

    data = diag.services()

    assert data["available"] is True
    names = {entry["name"] for entry in data["entries"]}
    assert "roto" in names


def test_firewall_status_uses_readonly_command(monkeypatch) -> None:
    def fake_runner(argv, timeout=8.0):
        return CommandResult(tuple(argv), True, "Estado: activado")

    monkeypatch.setattr(diag, "_command_runner", fake_runner)

    data = diag.firewall_status()

    assert data["available"] is True
    assert "activado" in data["output"]


def test_render_bundle_and_redact(fake_psutil, monkeypatch) -> None:
    monkeypatch.setenv("USERNAME", "alice")
    data = diag.collect_diagnostics(use_cache=False)

    text = diag.render_bundle(data)

    assert "Puertos a la escucha" in text
    assert "8080" in text
    assert "alice" not in text


def test_parse_sc_services() -> None:
    entries = diag._parse_sc_services(
        "SERVICE_NAME: a\n        STATE   : 4  RUNNING\n"
    )

    assert entries == [{"name": "a", "state": "4  RUNNING"}]
