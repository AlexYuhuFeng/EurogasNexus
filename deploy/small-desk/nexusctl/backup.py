"""Backups on the second disk: take, verify, copy, keep, and find them again.

A backup is one PostgreSQL custom-format dump (``pg_dump``: a consistent copy taken while the
desk works) with a small JSON note beside it::

    <backup disk>/nexus-backups/nexus-20261127T013000Z-nightly.dump
    <backup disk>/nexus-backups/nexus-20261127T013000Z-nightly.dump.json

It is verified twice before it counts: its checksum is written as it streams to disk, and
PostgreSQL's own ``pg_restore --list`` must read the whole table of contents back. Only then is
it recorded for the gated database upgrade, copied to the office or removable copy when one is
configured, and older backups thinned (:func:`select_for_deletion`).
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from nexusctl.settings import RECOVERY_NAMES, Settings, read_env, write_env

LABELS = ("nightly", "manual", "pre-update", "before-restore", "before-undo")
STAMP = "%Y%m%dT%H%M%SZ"


@dataclass
class BackupInfo:
    path: Path
    created: datetime
    label: str
    verified: bool
    sha256: str | None = None
    size: int = 0
    version: str | None = None
    db_revision: str | None = None

    def note(self) -> dict:
        return {
            "file": self.path.name,
            "created_at_utc": self.created.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "label": self.label,
            "verified": self.verified,
            "sha256": self.sha256,
            "size_bytes": self.size,
            "version": self.version,
            "db_revision": self.db_revision,
        }


def backup_name(now: datetime, label: str) -> str:
    if label not in LABELS:
        raise ValueError(f"unknown backup label {label!r}")
    return f"nexus-{now.astimezone(timezone.utc).strftime(STAMP)}-{label}.dump"


def parse_name(name: str) -> tuple[datetime, str] | None:
    if not (name.startswith("nexus-") and name.endswith(".dump")):
        return None
    core = name[len("nexus-") : -len(".dump")]
    stamp, _, label = core.partition("-")
    try:
        created = datetime.strptime(stamp, STAMP).replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return created, label or "manual"


def list_backups(directory: Path) -> list[BackupInfo]:
    """Every backup in ``directory``, newest first. A dump without its note is unverified."""

    found: list[BackupInfo] = []
    if not directory.is_dir():
        return found
    for path in directory.glob("nexus-*.dump"):
        parsed = parse_name(path.name)
        if parsed is None:
            continue
        created, label = parsed
        note: dict = {}
        note_path = path.with_name(path.name + ".json")
        if note_path.is_file():
            try:
                note = json.loads(note_path.read_text(encoding="utf-8"))
            except ValueError:
                note = {}
        found.append(
            BackupInfo(
                path=path,
                created=created,
                label=label,
                verified=bool(note.get("verified")),
                sha256=note.get("sha256"),
                size=int(note.get("size_bytes") or path.stat().st_size),
                version=note.get("version"),
                db_revision=note.get("db_revision"),
            )
        )
    found.sort(key=lambda item: item.created, reverse=True)
    return found


def select_for_deletion(
    backups: list[BackupInfo],
    now: datetime,
    *,
    keep_daily: int,
    keep_weekly: int,
    keep_monthly: int,
    protected: frozenset[str] = frozenset(),
) -> list[BackupInfo]:
    """Which backups to delete. Pure.

    Kept: every verified backup of the last ``keep_daily`` days; the newest verified backup of
    each of the last ``keep_weekly`` weeks and ``keep_monthly`` months; the newest verified
    backup whatever its age; every file named in ``protected`` (the backup an update can still
    be undone with). An unverified backup is deleted once it is a day old (a newer good one
    exists or the next night makes one); it is never the only copy of anything.
    """

    verified = [item for item in backups if item.verified]
    keep: set[Path] = {item.path for item in backups if item.path.name in protected}
    if verified:
        keep.add(max(verified, key=lambda item: item.created).path)
    for item in verified:
        if now - item.created <= timedelta(days=keep_daily):
            keep.add(item.path)

    def newest_per(key, limit: int) -> None:
        seen: dict = {}
        for item in sorted(verified, key=lambda entry: entry.created, reverse=True):
            bucket = key(item.created)
            if bucket not in seen:
                seen[bucket] = item
        for bucket in sorted(seen, reverse=True)[:limit]:
            keep.add(seen[bucket].path)

    newest_per(lambda moment: moment.isocalendar()[:2], keep_weekly)
    newest_per(lambda moment: (moment.year, moment.month), keep_monthly)

    delete: list[BackupInfo] = []
    for item in backups:
        if item.path in keep:
            continue
        if not item.verified and now - item.created < timedelta(days=1):
            continue
        delete.append(item)
    return delete


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def toc_is_complete(listing: str) -> bool:
    """``pg_restore --list`` read a whole product dump: the schema version and data are in it."""

    return "TABLE DATA public alembic_version" in listing and "TABLE DATA" in listing


def remove_backup(path: Path) -> None:
    for item in (path, path.with_name(path.name + ".json")):
        try:
            item.unlink()
        except FileNotFoundError:
            pass


def write_note(info: BackupInfo) -> None:
    note_path = info.path.with_name(info.path.name + ".json")
    note_path.write_text(json.dumps(info.note(), indent=2) + "\n", encoding="utf-8")


def copy_to(info: BackupInfo, destination: Path) -> tuple[bool, str]:
    """Copy a verified backup and its note, then check the copy's checksum."""

    target_dir = destination / "nexus-backups"
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        partial = target_dir / (info.path.name + ".partial")
        shutil.copyfile(info.path, partial)
        with partial.open("rb") as handle:
            os.fsync(handle.fileno())
        if sha256_of(partial) != info.sha256:
            partial.unlink()
            return False, "the copy did not match the original (checksum differs)"
        os.replace(partial, target_dir / info.path.name)
        shutil.copyfile(
            info.path.with_name(info.path.name + ".json"),
            target_dir / (info.path.name + ".json"),
        )
    except OSError as exc:
        return False, f"could not write there ({exc.strerror or exc.__class__.__name__})"
    return True, str(target_dir / info.path.name)


def write_recovery_key(settings: Settings, directory: Path) -> Path:
    """The key a restore on a replaced PC needs (second factors, stored provider keys).

    Root-only, on the backup disk beside the backups. Copied to the office copy only when
    NEXUS_COPY_KEYS=yes (the helpdesk card says to keep one copy in the firm's password safe).
    """

    values = read_env(settings.env_path)
    keys = {name: values[name] for name in RECOVERY_NAMES if values.get(name)}
    path = directory / "recovery-key.env"
    write_env(
        path,
        keys,
        header="Eurogas Nexus recovery key. Keep secret. Needed to restore onto a new PC:\n"
        "sudo nexus install ... --recovery-key <this file>",
    )
    return path


def record_attempt(directory: Path, payload: dict, *, success: bool) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    name = "last-backup.json" if success else "last-failed-backup.json"
    (directory / name).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    if success:
        try:
            (directory / "last-failed-backup.json").unlink()
        except FileNotFoundError:
            pass


def last_backup(directory: Path) -> tuple[dict | None, dict | None]:
    """(the last good backup, a failure since it) from the records on the backup disk."""

    def load(name: str) -> dict | None:
        path = directory / name
        if not path.is_file():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            return None

    return load("last-backup.json"), load("last-failed-backup.json")
