"""The server's clock check (small-desk plan section 5): offset, synchronisation, threshold."""

from __future__ import annotations

import socket
import struct
import threading
import time

from eurogas_nexus.application import clock_check
from eurogas_nexus.application.clock_check import WARN_OFFSET_SECONDS, assess


def test_the_verdict_warns_above_the_threshold_or_without_synchronisation():
    assert assess(offset_seconds=0.02, synchronised=True, reference="ntp")["state"] == "ok"
    high = assess(offset_seconds=-(WARN_OFFSET_SECONDS + 0.1), synchronised=True,
                  reference="ntp")
    assert high["state"] == "warning" and high["problems"] == ["offset_above_threshold"]
    unsynced = assess(offset_seconds=0.01, synchronised=False, reference="ntp")
    assert unsynced["problems"] == ["not_synchronised"]
    assert assess(offset_seconds=None, synchronised=None, reference="none")["state"] == "unknown"
    assert WARN_OFFSET_SECONDS == 0.5


def _fake_ntp_server(offset: float) -> tuple[socket.socket, int]:
    """A one-shot SNTP server whose clock is ``offset`` seconds ahead of this one."""

    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server.bind(("127.0.0.1", 0))

    def answer():
        _, address = server.recvfrom(512)
        now = time.time() + offset + 2_208_988_800
        seconds, fraction = int(now), int((now % 1) * 2**32)
        reply = bytearray(48)
        reply[0], reply[1] = 0x24, 2  # version 4, mode 4 (server); stratum 2
        reply[32:48] = struct.pack("!4I", seconds, fraction, seconds, fraction)
        server.sendto(bytes(reply), address)

    threading.Thread(target=answer, daemon=True).start()
    return server, server.getsockname()[1]


def test_sntp_measures_the_offset_against_the_reference():
    server, port = _fake_ntp_server(offset=2.0)
    try:
        offset = clock_check.sntp_offset("127.0.0.1", timeout=2.0, port=port)
    finally:
        server.close()
    # The reference is 2 s ahead, so this clock is 2 s behind.
    assert abs(offset + 2.0) < 0.05


def test_reading_the_status_never_waits_for_the_network(monkeypatch):
    clock_check.reset_for_tests()
    started = threading.Event()

    def slow_measure():
        started.set()
        time.sleep(1.0)
        return assess(offset_seconds=0.0, synchronised=True, reference="ntp")

    monkeypatch.setattr(clock_check, "measure", slow_measure)
    began = time.monotonic()
    first = clock_check.clock_status()
    assert time.monotonic() - began < 0.2
    assert first["state"] == "checking"
    assert started.wait(2)
    clock_check.reset_for_tests(assess(offset_seconds=0.9, synchronised=True, reference="ntp"))
    lines = clock_check.prometheus_lines()
    assert 'eurogas_clock_offset_seconds{reference="ntp"} 0.9' in lines
    assert "eurogas_clock_synchronised 1" in lines and "eurogas_clock_warning 1" in lines
    clock_check.reset_for_tests()


def test_health_reports_the_server_time_and_the_clock(monkeypatch):
    from fastapi.testclient import TestClient

    from eurogas_nexus.api.app import create_app

    clock_check.reset_for_tests(assess(offset_seconds=0.01, synchronised=True, reference="ntp"))
    body = TestClient(create_app()).get("/api/health").json()
    clock_check.reset_for_tests()
    assert body["server_time_utc"].endswith("+00:00")
    assert body["clock"]["state"] == "ok" and body["clock"]["threshold_seconds"] == 0.5
