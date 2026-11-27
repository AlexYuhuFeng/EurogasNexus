"""Prerequisite checks for `nexus install` and the facts `nexus status` reports.

Each check returns a :class:`Check` with a plain sentence and what to do. The parsing and the
judgement are pure functions (tested); reading the machine is kept to small helpers.
"""

from __future__ import annotations

import os
import re
import shutil
import socket
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

OK, WARN, FAIL = "ok", "warn", "fail"

#: Free space the installation wants on each disk (GB). The database of a small desk grows by
#: a few GB a year; nightly backups are kept for months.
DATA_DISK_MIN_GB = 40
BACKUP_DISK_MIN_GB = 100
MIN_COMPOSE = (2, 17)


@dataclass(frozen=True)
class Check:
    name: str
    status: str
    message: str
    todo: str | None = None

    @property
    def failed(self) -> bool:
        return self.status == FAIL


# -------------------------------------------------------------------- versions
def parse_version(text: str) -> tuple[int, ...] | None:
    match = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", text or "")
    if not match:
        return None
    return tuple(int(part) for part in match.groups() if part is not None)


def judge_docker(server_version: str | None, compose_version: str | None) -> list[Check]:
    checks: list[Check] = []
    if not server_version:
        checks.append(
            Check(
                "docker",
                FAIL,
                "Docker is not installed or not running.",
                "Ask IT to install Docker Engine (docs/operations/SMALL_DESK_INSTALL.md, step "
                "2), then run this again.",
            )
        )
    else:
        checks.append(Check("docker", OK, f"Docker {server_version} is running."))
    parsed = parse_version(compose_version or "")
    if parsed is None:
        checks.append(
            Check(
                "compose",
                FAIL,
                "The Docker Compose plugin is missing.",
                "Ask IT to install the package docker-compose-plugin, then run this again.",
            )
        )
    elif parsed[:2] < MIN_COMPOSE:
        checks.append(
            Check(
                "compose",
                FAIL,
                f"Docker Compose {compose_version} is too old (2.17 or newer is needed).",
                "Ask IT to update the package docker-compose-plugin.",
            )
        )
    else:
        checks.append(Check("compose", OK, f"Docker Compose {compose_version} is installed."))
    return checks


# -------------------------------------------------------------------- disks
def existing_ancestor(path: Path) -> Path:
    path = Path(path)
    while not path.exists() and path != path.parent:
        path = path.parent
    return path


def judge_disk_space(label: str, free_bytes: int, total_bytes: int, need_gb: int) -> Check:
    free_gb = free_bytes / 1024**3
    if free_gb < need_gb:
        return Check(
            f"disk:{label}",
            FAIL,
            f"The {label} has {free_gb:.0f} GB free; at least {need_gb} GB is needed.",
            f"Free space on the {label} or use a larger disk.",
        )
    share = free_bytes / total_bytes if total_bytes else 1.0
    if share < 0.15:
        return Check(
            f"disk:{label}",
            WARN,
            f"The {label} is {100 - share * 100:.0f}% full ({free_gb:.0f} GB free).",
            f"Free space on the {label} soon.",
        )
    return Check(f"disk:{label}", OK, f"The {label} has {free_gb:.0f} GB free.")


def judge_two_disks(
    data_dir: Path,
    backup_dir: Path,
    *,
    device_of: Callable[[Path], int],
    exists: Callable[[Path], bool],
    allow_same_disk: bool = False,
) -> Check:
    """The database on one disk and its backups on another, so one failed disk loses neither."""

    if not exists(backup_dir):
        return Check(
            "two-disks",
            FAIL,
            f"The backup disk is not there: {backup_dir} does not exist.",
            "Check the second disk is fitted and mounted at that folder (install guide, step 3), "
            "or give its folder with --backup-dir.",
        )
    same = device_of(existing_ancestor(data_dir)) == device_of(backup_dir)
    if same and not allow_same_disk:
        return Check(
            "two-disks",
            FAIL,
            f"The database ({data_dir}) and the backups ({backup_dir}) are on the same disk: "
            "one disk failure would lose both.",
            "Mount the second disk at the backup folder (install guide, step 3).",
        )
    if same:
        return Check(
            "two-disks",
            WARN,
            "The database and the backups are on the same disk (allowed for a test only).",
            "Use a second disk for the backups before the desk relies on this PC.",
        )
    return Check("two-disks", OK, "The database and the backups are on different disks.")


# -------------------------------------------------------------------- clock
def parse_key_values(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in (text or "").splitlines():
        if "=" in line:
            name, value = line.split("=", 1)
            values[name.strip()] = value.strip()
    return values


def parse_chrony_offset(text: str) -> float | None:
    """Seconds the clock is off, from ``chronyc tracking`` ("System time : 0.000012 seconds
    fast of NTP time"); negative when slow."""

    match = re.search(r"System time\s*:\s*([0-9.]+)\s+seconds\s+(fast|slow)", text or "")
    if not match:
        return None
    value = float(match.group(1))
    return value if match.group(2) == "fast" else -value


_UNITS = {"us": 1e-6, "µs": 1e-6, "ms": 1e-3, "s": 1.0, "min": 60.0}


def parse_timesync_offset(text: str) -> float | None:
    """Seconds off, from ``timedatectl timesync-status`` ("Offset: +1.234ms")."""

    match = re.search(r"Offset:\s*([+-]?[0-9.]+)\s*(us|µs|ms|s|min)\b", text or "")
    if not match:
        return None
    return float(match.group(1)) * _UNITS[match.group(2)]


def judge_clock(synchronized: bool | None, offset_seconds: float | None) -> Check:
    """Deals and prices are ordered by time: the PC keeps its clock by NTP (plan section 5)."""

    if synchronized is None:
        return Check(
            "clock",
            WARN,
            "Could not tell whether the clock is kept by a time server.",
            "Ask IT to confirm the PC synchronises its clock (NTP).",
        )
    if not synchronized:
        return Check(
            "clock",
            FAIL,
            "The clock is not synchronised with a time server: deal and price times can be "
            "wrong.",
            "Ask IT to turn on time synchronisation (Ubuntu: sudo timedatectl set-ntp true) and "
            "allow the PC to reach the office time server.",
        )
    if offset_seconds is not None and abs(offset_seconds) > 1.0:
        return Check(
            "clock",
            WARN,
            f"The clock is synchronised but {abs(offset_seconds):.1f} seconds off.",
            "It should correct itself within minutes; if not, ask IT to check the time server.",
        )
    detail = "" if offset_seconds is None else f" (off by {abs(offset_seconds) * 1000:.0f} ms)"
    return Check("clock", OK, f"The clock is synchronised with a time server{detail}.")


# -------------------------------------------------------------------- ports, memory
def port_in_use(port: int, address: str = "0.0.0.0") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind((address, port))
        except OSError:
            return True
    return False


def judge_port(port: int, in_use: bool) -> Check:
    if in_use:
        return Check(
            "port",
            FAIL,
            f"Port {port} is already used by another program on this PC.",
            f"Stop that program, or install with another port (--https-port), for example "
            f"{8443 if port == 443 else port + 1}.",
        )
    return Check("port", OK, f"Port {port} is free for the web address.")


def parse_meminfo_gb(text: str) -> float | None:
    match = re.search(r"MemTotal:\s*(\d+)\s*kB", text or "")
    return int(match.group(1)) / 1024**2 if match else None


def judge_memory(total_gb: float | None, cpus: int | None) -> Check:
    if total_gb is None:
        return Check("memory", WARN, "Could not read the PC's memory size.")
    if total_gb < 8 or (cpus or 0) < 2:
        return Check(
            "memory",
            FAIL,
            f"The PC has {total_gb:.0f} GB of memory and {cpus} processors; at least 8 GB and "
            "2 processors are needed (16 GB and 4 recommended).",
            "Use a PC from the hardware list in the install guide.",
        )
    if total_gb < 16 or (cpus or 0) < 4:
        return Check(
            "memory",
            WARN,
            f"The PC has {total_gb:.1f} GB of memory and {cpus} processors; 16 GB and 4 are "
            "recommended.",
        )
    return Check("memory", OK, f"The PC has {total_gb:.0f} GB of memory and {cpus} processors.")


# -------------------------------------------------------------------- machine readers
def device_of(path: Path) -> int:
    return os.stat(path).st_dev


def disk_usage(path: Path) -> tuple[int, int]:
    usage = shutil.disk_usage(existing_ancestor(path))
    return usage.free, usage.total


def read_text(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError:
        return ""
