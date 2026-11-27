"""`nexus install` prerequisite checks and the clock facts `nexus status` reports."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "deploy" / "small-desk"))

from nexusctl import checks  # noqa: E402
from nexusctl.checks import FAIL, OK, WARN  # noqa: E402

GB = 1024**3


def test_docker_and_compose_must_be_present_and_recent() -> None:
    assert [c.status for c in checks.judge_docker("29.1.0", "2.29.1")] == [OK, OK]
    missing = checks.judge_docker(None, None)
    assert [c.status for c in missing] == [FAIL, FAIL]
    assert "install Docker Engine" in missing[0].todo
    old = checks.judge_docker("24.0.0", "v2.10.2")
    assert old[1].status == FAIL and "too old" in old[1].message
    assert checks.judge_docker("29.1.0", "5.6.1")[1].status == OK


def test_database_and_backups_must_be_on_two_disks(tmp_path) -> None:
    data, backup = tmp_path / "ssd" / "nexus", tmp_path / "hdd"
    backup.mkdir()
    devices = {tmp_path: 1, backup: 2}

    def device_of(path: Path) -> int:
        return devices.get(path, 1)

    exists = Path.is_dir
    ok = checks.judge_two_disks(data, backup, device_of=device_of, exists=exists)
    assert ok.status == OK
    devices[backup] = 1
    same = checks.judge_two_disks(data, backup, device_of=device_of, exists=exists)
    assert same.status == FAIL and "same disk" in same.message
    allowed = checks.judge_two_disks(
        data, backup, device_of=device_of, exists=exists, allow_same_disk=True
    )
    assert allowed.status == WARN
    gone = checks.judge_two_disks(data, tmp_path / "absent", device_of=device_of, exists=exists)
    assert gone.status == FAIL and "not there" in gone.message and "mounted" in gone.todo


@pytest.mark.parametrize(
    ("free_gb", "total_gb", "need", "status"),
    [(500, 1000, 40, OK), (30, 1000, 40, FAIL), (100, 1000, 40, WARN)],
)
def test_disk_space(free_gb, total_gb, need, status) -> None:
    check = checks.judge_disk_space("backup disk", free_gb * GB, total_gb * GB, need)
    assert check.status == status
    assert "backup disk" in check.message


def test_clock_must_be_kept_by_ntp() -> None:
    chrony = "Reference ID    : C0A80001\nSystem time     : 0.000210473 seconds slow of NTP time\n"
    assert checks.parse_chrony_offset(chrony) == pytest.approx(-0.000210473)
    assert checks.parse_timesync_offset("       Offset: +1.234ms\n") == pytest.approx(0.001234)
    assert checks.parse_timesync_offset("Offset: -250us") == pytest.approx(-0.00025)
    assert checks.parse_key_values("NTP=yes\nNTPSynchronized=no\n")["NTPSynchronized"] == "no"

    assert checks.judge_clock(True, 0.002).status == OK
    unsynchronised = checks.judge_clock(False, None)
    assert unsynchronised.status == FAIL and "timedatectl set-ntp true" in unsynchronised.todo
    assert checks.judge_clock(True, 3.5).status == WARN
    assert checks.judge_clock(None, None).status == WARN


def test_port_check_finds_a_used_port() -> None:
    import socket

    with socket.socket() as busy:
        busy.bind(("127.0.0.1", 0))
        busy.listen()
        port = busy.getsockname()[1]
        assert checks.port_in_use(port, "127.0.0.1")
        check = checks.judge_port(port, True)
        assert check.status == FAIL and "--https-port" in check.todo
    assert checks.judge_port(18443, False).status == OK


def test_memory_and_processors() -> None:
    assert checks.parse_meminfo_gb("MemTotal:       65536000 kB\n") == pytest.approx(62.5, 0.01)
    assert checks.judge_memory(64, 8).status == OK
    assert checks.judge_memory(12, 4).status == WARN
    assert checks.judge_memory(4, 2).status == FAIL
