"""What `nexus backup` keeps, and how `nexus update` / `undo-update` decide."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "deploy" / "small-desk"))

from nexusctl import backup as backups  # noqa: E402
from nexusctl import operations, release  # noqa: E402
from nexusctl.settings import Settings  # noqa: E402
from nexusctl.ui import Out  # noqa: E402

NOW = datetime(2026, 11, 27, 2, 0, tzinfo=UTC)


def info(days: float, label: str = "nightly", verified: bool = True) -> backups.BackupInfo:
    created = NOW - timedelta(days=days)
    return backups.BackupInfo(
        path=Path(backups.backup_name(created, label)), created=created, label=label,
        verified=verified,
    )


# ---------------------------------------------------------------- retention
def test_backup_names_round_trip() -> None:
    name = backups.backup_name(NOW, "pre-update")
    assert name == "nexus-20261127T020000Z-pre-update.dump"
    assert backups.parse_name(name) == (NOW, "pre-update")
    assert backups.parse_name("something-else.dump") is None
    with pytest.raises(ValueError):
        backups.backup_name(NOW, "weekly")


def test_retention_keeps_days_weeks_months_and_never_the_last_good_one() -> None:
    nightly = [info(day) for day in range(0, 400)]
    doomed = {item.path for item in backups.select_for_deletion(
        nightly, NOW, keep_daily=14, keep_weekly=8, keep_monthly=12
    )}
    kept = [item for item in nightly if item.path not in doomed]
    assert all(item in kept for item in nightly[:15])  # the last 14 days, every night
    ages = sorted((NOW - item.created).days for item in kept)
    assert max(ages) < 366  # nothing older than the 12 monthly
    assert len(kept) < 15 + 8 + 12 + 1
    months = {(item.created.year, item.created.month) for item in kept}
    assert len(months) >= 12


def test_retention_never_deletes_the_only_good_backup_or_a_protected_one() -> None:
    old = info(200)
    assert backups.select_for_deletion([old], NOW, keep_daily=1, keep_weekly=0,
                                       keep_monthly=0) == []
    pre_update = info(300, "pre-update")
    doomed = backups.select_for_deletion(
        [info(0), pre_update], NOW, keep_daily=1, keep_weekly=0, keep_monthly=0,
        protected=frozenset({pre_update.path.name}),
    )
    assert doomed == []


def test_unverified_backups_go_after_a_day_and_never_count() -> None:
    fresh_bad, old_bad = info(0.1, verified=False), info(3, verified=False)
    good = info(1)
    doomed = backups.select_for_deletion(
        [fresh_bad, old_bad, good], NOW, keep_daily=14, keep_weekly=8, keep_monthly=12
    )
    assert doomed == [old_bad]


def test_verification_needs_a_complete_table_of_contents() -> None:
    listing = (
        ";\n; Archive created at 2026-11-27\n"
        "3456; 0 16390 TABLE DATA public alembic_version eurogas_owner\n"
        "3457; 0 16400 TABLE DATA public audit_events eurogas_owner\n"
    )
    assert backups.toc_is_complete(listing)
    assert not backups.toc_is_complete("; Archive created\n")


def test_list_backups_reads_the_notes(tmp_path) -> None:
    path = tmp_path / backups.backup_name(NOW, "manual")
    path.write_bytes(b"dump")
    item = backups.BackupInfo(path=path, created=NOW, label="manual", verified=True,
                              sha256=backups.sha256_of(path), size=4, version="1.0")
    backups.write_note(item)
    (tmp_path / backups.backup_name(NOW - timedelta(days=1), "nightly")).write_bytes(b"x")
    rows = backups.list_backups(tmp_path)
    assert [row.label for row in rows] == ["manual", "nightly"]
    assert rows[0].verified and not rows[1].verified  # no note: not verified
    ok, detail = backups.copy_to(rows[0], tmp_path / "office")
    assert ok, detail
    assert (tmp_path / "office" / "nexus-backups" / path.name).read_bytes() == b"dump"


# ---------------------------------------------------------------- undo decision
def test_undo_plan_follows_the_reversibility_declarations() -> None:
    assert release.plan_undo([]).method == "switch"
    plan = release.plan_undo(
        [{"revision": "0097_a", "reversibility": "reversible"},
         {"revision": "0098_b", "reversibility": "conditional"},
         {"revision": "0099_c", "reversibility": "no-op"}]
    )
    assert plan.method == "downgrade"
    plan = release.plan_undo(
        [{"revision": "0097_a", "reversibility": "reversible"},
         {"revision": "0098_b", "reversibility": "irreversible"}]
    )
    assert plan.method == "restore" and plan.blocking == ("0098_b",)
    assert "restoring the backup taken just before the update" in plan.reason
    # A migration that declares nothing is treated as irreversible.
    assert release.plan_undo([{"revision": "0097_x"}]).method == "restore"


@pytest.mark.parametrize(
    ("code", "ready", "failed", "probe", "healthy"),
    [
        (0, True, [], {"database": {"reachable": True, "revision": "r2",
                                    "required_revision": "r2"}}, True),
        (1, True, [], None, False),
        (0, False, ["api"], None, False),
        (0, False, [], None, False),
        (0, True, [], {"database": {"reachable": False}}, False),
        (0, True, [], {"database": {"reachable": True, "revision": "r1",
                                    "required_revision": "r2"}}, False),
    ],
)
def test_update_health_decision(code, ready, failed, probe, healthy) -> None:
    result, reason = release.update_outcome(
        upgrade_returncode=code, ready=ready, failed_parts=failed, probe=probe
    )
    assert result is healthy and reason


# ---------------------------------------------------------------- the update flow
class FakeStack:
    def __init__(self, version: str) -> None:
        self.version = version
        self.calls: list[str] = []

    def remove_application(self):
        self.calls.append("remove")

    def up(self, services=()):
        self.calls.append("up")

    def wait_database(self, *args, **kwargs):
        return True


@pytest.fixture()
def updating(tmp_path, monkeypatch):
    settings = Settings(root=tmp_path / "opt", data_dir=tmp_path / "ssd",
                        backup_dir=tmp_path / "hdd")
    settings.root.mkdir()
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    state = {"current": {"version": "1.0", "api_image": "img:1.0"}, "previous": None}
    out_lines: list[str] = []

    class Capture(Out):
        def _emit(self, text: str) -> None:
            out_lines.append(text)

    ctx = operations.Context(settings, runner=None, out=Capture(), state=state)
    stacks: dict[str, FakeStack] = {}
    monkeypatch.setattr(ctx.__class__, "stack_for",
                        lambda self, v: stacks.setdefault(v, FakeStack(v)))
    monkeypatch.setattr(operations.release, "read_release",
                        lambda path: {"version": "2.0", "api_image": "img:2.0"})
    monkeypatch.setattr(operations.release, "install_release",
                        lambda *a, **k: tmp_path / "opt" / "releases" / "2.0")
    monkeypatch.setattr(operations, "Stack",
                        lambda *a, **k: stacks.setdefault("2.0", FakeStack("2.0")))
    pre = backups.BackupInfo(path=tmp_path / "pre.dump", created=NOW, label="pre-update",
                             verified=True)
    monkeypatch.setattr(operations, "take_backup", lambda *a, **k: pre)
    monkeypatch.setattr(operations, "db_revision", lambda stack, db=None: "r1")
    monkeypatch.setattr(
        operations, "migrate_plan",
        lambda stack: {"pending": [{"revision": "r2", "reversibility": "reversible"}]},
    )
    monkeypatch.setattr(operations, "run_upgrade", lambda *a, **k: 0)
    undo_calls: list[bool] = []
    monkeypatch.setattr(
        operations, "undo_update",
        lambda ctx, **kw: undo_calls.append(kw.get("automatic")) or 0,
    )
    return ctx, bundle, out_lines, undo_calls


def test_update_records_the_previous_version_and_backup_first(updating, monkeypatch) -> None:
    ctx, bundle, out, undo_calls = updating
    monkeypatch.setattr(operations, "bring_up", lambda ctx, stack, **kw: (True, "fine"))
    assert operations.update(ctx, bundle, assume_yes=True) == 0
    saved = json.loads(ctx.settings.state_path.read_text())
    assert saved["current"]["version"] == "2.0"
    assert saved["previous"]["version"] == "1.0"
    assert saved["update"]["from_revision"] == "r1"
    assert saved["update"]["applied"] == [{"revision": "r2", "reversibility": "reversible"}]
    assert saved["update"]["pre_update_backup"].endswith("pre.dump")
    assert saved["update"]["status"] == "done"
    assert undo_calls == []


def test_a_failed_health_check_rolls_back_by_itself(updating, monkeypatch) -> None:
    ctx, bundle, out, undo_calls = updating
    monkeypatch.setattr(
        operations, "bring_up", lambda ctx, stack, **kw: (False, "the product did not start")
    )
    with pytest.raises(operations.Stop) as stop:
        operations.update(ctx, bundle, assume_yes=True)
    assert undo_calls == [True]
    assert "failed and was undone" in str(stop.value)
    assert any("Going back to 1.0 automatically" in line for line in out)


def test_a_failed_database_upgrade_rolls_back_without_starting(updating, monkeypatch) -> None:
    ctx, bundle, out, undo_calls = updating
    monkeypatch.setattr(operations, "run_upgrade", lambda *a, **k: 1)
    started: list[str] = []
    monkeypatch.setattr(operations, "bring_up",
                        lambda ctx, stack, **kw: started.append("up") or (True, ""))
    with pytest.raises(operations.Stop):
        operations.update(ctx, bundle, assume_yes=True)
    assert started == [] and undo_calls == [True]


def test_no_backup_no_update(updating, monkeypatch) -> None:
    ctx, bundle, out, undo_calls = updating

    def refuse(*a, **k):
        raise operations.Stop("The backup failed: disk full.")

    monkeypatch.setattr(operations, "take_backup", refuse)
    installed: list[str] = []
    monkeypatch.setattr(operations.release, "install_release",
                        lambda *a, **k: installed.append("x"))
    with pytest.raises(operations.Stop):
        operations.update(ctx, bundle, assume_yes=True)
    assert installed == []
    assert ctx.state["current"]["version"] == "1.0"
