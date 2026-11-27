"""Is the server's clock right? (small-desk plan section 5: the PC keeps its clock by NTP.)

Deals and prices are ordered by their timestamps, so a server clock that drifts puts a deal
before the price it was traded on, or a price in the wrong minute. This module answers two
questions, cheaply and without ever blocking a request:

* **Is synchronisation active?** Read from the kernel's own clock discipline
  (``adjtimex``, which ``chronyd``, ``ntpd`` and ``systemd-timesyncd`` all steer). A
  container shares the host's kernel clock, so this is the PC's state, not the container's.
  ``None`` where the platform cannot say (not Linux).
* **How far off is it?** Measured against an NTP server (``EUROGAS_NEXUS_NTP_SERVER``,
  default ``pool.ntp.org``; ``off`` to skip) with one SNTP query, the best reference there
  is. Without an answer (no route to an NTP server), the kernel's own estimated error is the
  best available figure and is reported as such (``reference: "kernel_estimate"``).

The answer is kept for :data:`CHECK_EVERY_SECONDS`; reading it never waits for the network
(a stale answer is returned while one background thread refreshes it).

**Threshold** (:data:`WARN_OFFSET_SECONDS`, 0.5 s): NTP over the internet keeps a PC within
tens of milliseconds, so half a second is ten times its normal error and means synchronisation
is broken, while it is still below the one-second resolution of the exchanges' trade exports,
so a deal can not yet land in the wrong second against the exchange record. Above it, or with
synchronisation off, the health payload, ``/metrics`` and the Runtime page say so.

服务器时钟检查：内核同步状态与 NTP 偏差；超过 0.5 秒或未同步时告警。
"""

from __future__ import annotations

import ctypes
import ctypes.util
import os
import socket
import struct
import threading
import time
from datetime import UTC, datetime
from typing import Any

NTP_SERVER_ENV = "EUROGAS_NEXUS_NTP_SERVER"
DEFAULT_NTP_SERVER = "pool.ntp.org"
#: Above this offset (either way) the clock is reported as wrong.
WARN_OFFSET_SECONDS = 0.5
#: How long one check is reused.
CHECK_EVERY_SECONDS = 300.0
#: One SNTP query's limit.
NTP_TIMEOUT_SECONDS = 1.5
#: Seconds between 1900-01-01 (NTP era 0) and 1970-01-01.
_NTP_EPOCH_DELTA = 2_208_988_800

_lock = threading.Lock()
# ``checked_at`` is None until the first check: the monotonic clock counts from boot, so "0"
# would read as "checked at boot" and a freshly started PC would skip its first check.
_state: dict[str, Any] = {"result": None, "checked_at": None, "running": False}


class _Timeval(ctypes.Structure):
    _fields_ = [("tv_sec", ctypes.c_long), ("tv_usec", ctypes.c_long)]


class _Timex(ctypes.Structure):
    # struct timex (linux/timex.h): the fields read here come first; the tail is padding.
    _fields_ = [
        ("modes", ctypes.c_uint),
        ("offset", ctypes.c_long),
        ("freq", ctypes.c_long),
        ("maxerror", ctypes.c_long),
        ("esterror", ctypes.c_long),
        ("status", ctypes.c_int),
        ("constant", ctypes.c_long),
        ("precision", ctypes.c_long),
        ("tolerance", ctypes.c_long),
        ("time", _Timeval),
        ("tick", ctypes.c_long),
        ("ppsfreq", ctypes.c_long),
        ("jitter", ctypes.c_long),
        ("shift", ctypes.c_int),
        ("stabil", ctypes.c_long),
        ("jitcnt", ctypes.c_long),
        ("calcnt", ctypes.c_long),
        ("errcnt", ctypes.c_long),
        ("stbcnt", ctypes.c_long),
        ("tai", ctypes.c_int),
        ("_padding", ctypes.c_int * 11),
    ]


_STA_UNSYNC = 0x0040
_TIME_ERROR = 5


def kernel_clock() -> dict[str, Any]:
    """The kernel's clock discipline: synchronised or not, and its estimated error.

    ``synchronised`` is ``None`` where it cannot be read (not Linux, or the call refused).
    """

    if not os.sys.platform.startswith("linux"):
        return {"synchronised": None, "estimated_error_seconds": None}
    try:
        libc = ctypes.CDLL(ctypes.util.find_library("c") or "libc.so.6", use_errno=True)
        timex = _Timex()
        timex.modes = 0  # read only: nothing is changed
        state = libc.adjtimex(ctypes.byref(timex))
    except (OSError, AttributeError):
        return {"synchronised": None, "estimated_error_seconds": None}
    if state < 0:
        return {"synchronised": None, "estimated_error_seconds": None}
    synchronised = not (timex.status & _STA_UNSYNC) and state != _TIME_ERROR
    return {
        "synchronised": bool(synchronised),
        # Microseconds in the kernel; a bound on the error while synchronised.
        "estimated_error_seconds": round(timex.esterror / 1_000_000, 6),
    }


def sntp_offset(server: str, timeout: float = NTP_TIMEOUT_SECONDS, port: int = 123) -> float:
    """This clock's offset from ``server`` in seconds (positive: this clock is ahead).

    One SNTP v4 client query (RFC 4330); the offset is ``((t1 - t0) + (t2 - t3)) / 2``
    negated so that a positive figure means the server's clock is ahead of the reference.

    Raises:
        OSError: no answer in time, or an answer that is not a usable NTP reply.
    """

    packet = b"\x23" + 47 * b"\0"  # LI 0, version 4, mode 3 (client)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout)
        sent = time.time()
        sock.sendto(packet, (server, port))
        data, _ = sock.recvfrom(512)
        received = time.time()
    if len(data) < 48:
        raise OSError("short NTP reply")
    stratum = data[1]
    if stratum == 0 or stratum > 15:
        raise OSError("NTP server is not synchronised")
    receive_s, receive_f, transmit_s, transmit_f = struct.unpack("!4I", data[32:48])
    t1 = receive_s - _NTP_EPOCH_DELTA + receive_f / 2**32
    t2 = transmit_s - _NTP_EPOCH_DELTA + transmit_f / 2**32
    reference_minus_local = ((t1 - sent) + (t2 - received)) / 2
    return -reference_minus_local


def configured_server() -> str | None:
    value = (os.environ.get(NTP_SERVER_ENV) or "").strip()
    if value.lower() in {"off", "none", "false", "0"}:
        return None
    return value or DEFAULT_NTP_SERVER


def measure() -> dict[str, Any]:
    """One full check now (may wait up to :data:`NTP_TIMEOUT_SECONDS` for the NTP server)."""

    kernel = kernel_clock()
    server = configured_server()
    offset: float | None = None
    reference = "none"
    if server is not None:
        try:
            offset = round(sntp_offset(server), 4)
            reference = "ntp"
        except OSError:
            offset = None
    if offset is None and kernel["synchronised"] and kernel["estimated_error_seconds"] is not None:
        # No NTP answer: the kernel's own error bound is the best figure there is.
        offset = kernel["estimated_error_seconds"]
        reference = "kernel_estimate"
    return assess(
        offset_seconds=offset,
        synchronised=kernel["synchronised"],
        reference=reference,
        server=server if reference == "ntp" else None,
    )


def assess(
    *,
    offset_seconds: float | None,
    synchronised: bool | None,
    reference: str,
    server: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """The clock verdict: ``ok``, ``warning`` (off by more than the threshold, or not
    synchronised) or ``unknown`` (nothing could be measured)."""

    problems = []
    if synchronised is False:
        problems.append("not_synchronised")
    if offset_seconds is not None and abs(offset_seconds) > WARN_OFFSET_SECONDS:
        problems.append("offset_above_threshold")
    if problems:
        state = "warning"
    elif offset_seconds is None and synchronised is None:
        state = "unknown"
    else:
        state = "ok"
    return {
        "state": state,
        "problems": problems,
        "offset_seconds": offset_seconds,
        "synchronised": synchronised,
        "reference": reference,
        "ntp_server": server,
        "threshold_seconds": WARN_OFFSET_SECONDS,
        "checked_at_utc": (now or datetime.now(UTC)).isoformat(),
    }


def _refresh() -> None:
    try:
        result = measure()
    except Exception:  # noqa: BLE001 - a failed check reports "unknown", never an error
        result = assess(offset_seconds=None, synchronised=None, reference="none")
    with _lock:
        _state.update(result=result, checked_at=time.monotonic(), running=False)


def clock_status(*, wait: bool = False) -> dict[str, Any]:
    """The last clock check; starts a fresh one in the background when it is due.

    Never waits for the network unless ``wait`` (the first check of a command-line run).
    Before the first check has finished the answer is ``state: "checking"``.
    """

    with _lock:
        checked_at = _state["checked_at"]
        due = checked_at is None or time.monotonic() - checked_at >= CHECK_EVERY_SECONDS
        start = due and not _state["running"]
        if start:
            _state["running"] = True
        result = _state["result"]
    if start:
        if wait:
            _refresh()
            with _lock:
                return dict(_state["result"])
        threading.Thread(target=_refresh, name="clock-check", daemon=True).start()
    if result is None:
        return {"state": "checking", "problems": [], "offset_seconds": None,
                "synchronised": None, "reference": "none", "ntp_server": None,
                "threshold_seconds": WARN_OFFSET_SECONDS, "checked_at_utc": None}
    return dict(result)


def prometheus_lines() -> str:
    """The clock as ``/metrics`` gauges (absent figures are left out, not zero)."""

    status = clock_status()
    lines = [
        "# HELP eurogas_clock_offset_seconds The server clock's offset from the reference "
        "(positive: ahead).",
        "# TYPE eurogas_clock_offset_seconds gauge",
    ]
    if status["offset_seconds"] is not None:
        lines.append(f'eurogas_clock_offset_seconds{{reference="{status["reference"]}"}} '
                     f'{status["offset_seconds"]}')
    lines += [
        "# HELP eurogas_clock_synchronised 1 when the kernel clock is synchronised (NTP), 0 when "
        "not.",
        "# TYPE eurogas_clock_synchronised gauge",
    ]
    if status["synchronised"] is not None:
        lines.append(f"eurogas_clock_synchronised {1 if status['synchronised'] else 0}")
    lines += [
        "# HELP eurogas_clock_warning 1 when the clock is off by more than the threshold or not "
        "synchronised.",
        "# TYPE eurogas_clock_warning gauge",
        f"eurogas_clock_warning {1 if status['state'] == 'warning' else 0}",
    ]
    return "\n".join(lines) + "\n"


def reset_for_tests(result: dict[str, Any] | None = None) -> None:
    with _lock:
        _state.update(result=result, checked_at=time.monotonic() if result else None,
                      running=False)


__all__ = [
    "CHECK_EVERY_SECONDS",
    "DEFAULT_NTP_SERVER",
    "WARN_OFFSET_SECONDS",
    "assess",
    "clock_status",
    "configured_server",
    "kernel_clock",
    "measure",
    "prometheus_lines",
    "sntp_offset",
]
