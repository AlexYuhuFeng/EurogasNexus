"""Start on boot and the nightly backup, as systemd units (Ubuntu). The only Linux-specific part.

Docker itself restarts the containers after a crash (``restart: unless-stopped``); the unit
starts the whole stack at boot through ``nexus start``, after Docker and the network, so the
desk comes back by itself after a power cut. The timer runs ``nexus backup`` every night and,
because it is ``Persistent``, at the next boot when the PC was off at that time.
"""

from __future__ import annotations

from pathlib import Path

SERVICE = "eurogas-nexus.service"
BACKUP_SERVICE = "eurogas-nexus-backup.service"
BACKUP_TIMER = "eurogas-nexus-backup.timer"


def units(nexus: Path, backup_time: str) -> dict[str, str]:
    """The unit files, by name. ``backup_time`` is local time HH:MM."""

    hour, _, minute = backup_time.partition(":")
    if not (hour.isdigit() and minute.isdigit() and int(hour) < 24 and int(minute) < 60):
        raise ValueError(f"backup time must be HH:MM, not {backup_time!r}")
    return {
        SERVICE: f"""[Unit]
Description=Eurogas Nexus (small desk)
Requires=docker.service
After=docker.service network-online.target local-fs.target
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart={nexus} start --quiet
ExecStop={nexus} stop --quiet
TimeoutStartSec=1200
TimeoutStopSec=300

[Install]
WantedBy=multi-user.target
""",
        BACKUP_SERVICE: f"""[Unit]
Description=Eurogas Nexus nightly backup
Requires=docker.service
After=docker.service {SERVICE}

[Service]
Type=oneshot
ExecStart={nexus} backup --scheduled
TimeoutStartSec=7200
""",
        BACKUP_TIMER: f"""[Unit]
Description=Eurogas Nexus nightly backup at {int(hour):02d}:{int(minute):02d}

[Timer]
OnCalendar=*-*-* {int(hour):02d}:{int(minute):02d}:00
Persistent=true
RandomizedDelaySec=300

[Install]
WantedBy=timers.target
""",
    }


def write_units(directory: Path, nexus: Path, backup_time: str) -> list[Path]:
    directory.mkdir(parents=True, exist_ok=True)
    written = []
    for name, text in units(nexus, backup_time).items():
        path = directory / name
        path.write_text(text, encoding="utf-8")
        path.chmod(0o644)
        written.append(path)
    return written


def enable_commands() -> list[list[str]]:
    return [
        ["systemctl", "daemon-reload"],
        ["systemctl", "enable", SERVICE],
        ["systemctl", "enable", "--now", BACKUP_TIMER],
    ]
