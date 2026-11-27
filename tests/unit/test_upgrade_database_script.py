"""The gated upgrade command: never migrates on start in production; plans what can be undone."""

from __future__ import annotations

import pytest

from eurogas_nexus.application import database_upgrade
from scripts.ops import upgrade_database


@pytest.mark.parametrize(
    ("environ", "expected"),
    [
        ({}, True),
        ({"EUROGAS_NEXUS_ENV": "development"}, True),
        ({"EUROGAS_NEXUS_ENV": "development", "EUROGAS_NEXUS_AUTO_MIGRATE": "0"}, False),
        ({"EUROGAS_NEXUS_ENV": "release"}, False),
        ({"EUROGAS_NEXUS_ENV": "trial"}, False),
        # Asked for in release: still refused (the upgrade there is the gated step).
        ({"EUROGAS_NEXUS_ENV": "release", "EUROGAS_NEXUS_AUTO_MIGRATE": "1"}, False),
    ],
)
def test_auto_migrate_is_never_on_in_production(environ, expected) -> None:
    assert database_upgrade.auto_migrate_enabled(environ) is expected


@pytest.fixture()
def empty_sqlite(tmp_path, monkeypatch):
    url = f"sqlite+pysqlite:///{(tmp_path / 'empty.sqlite').as_posix()}"
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    return url


def test_release_start_refuses_an_old_schema_and_says_what_to_run(
    empty_sqlite, monkeypatch, capsys
) -> None:
    monkeypatch.setenv("EUROGAS_NEXUS_ENV", "release")
    monkeypatch.setenv("EUROGAS_NEXUS_AUTO_MIGRATE", "1")
    assert upgrade_database.main(["on-start"]) == 1
    out = capsys.readouterr().out
    assert "ignored in trial and release" in out
    assert "upgrade_database.py upgrade --operator" in out
    # Every pending revision with whether it can be undone, in run order.
    assert out.index("  0001_m2_baseline") < out.index("  0094_option_settlements")
    assert "0040_strategy_owner_sharing" in out
    assert "no: going back means restoring the backup" in out


def test_plan_changes_nothing_and_exits_zero(empty_sqlite, capsys) -> None:
    assert upgrade_database.main(["plan"]) == 0
    # Every revision of the chain is pending on an empty store (0095 is the security hardening,
    # 0096 the retention by data class).
    assert "pending revisions : 97" in capsys.readouterr().out


def test_upgrade_needs_confirmation_in_a_script(empty_sqlite, monkeypatch, capsys) -> None:
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    assert upgrade_database.main(["upgrade", "--operator", "Ops"]) == 2
    assert "pass --yes" in capsys.readouterr().out


def test_operator_is_required(empty_sqlite) -> None:
    with pytest.raises(SystemExit):
        upgrade_database.main(["upgrade", "--yes"])


def test_timeouts_are_validated_not_interpolated() -> None:
    from eurogas_nexus.db.migration_rules import migration_timeouts

    assert migration_timeouts({}) == ("10s", "1h")
    assert migration_timeouts({"lock_timeout": "500ms", "statement_timeout": "2h"}) == (
        "500ms",
        "2h",
    )
    with pytest.raises(ValueError):
        migration_timeouts({"lock_timeout": "1s'; DROP TABLE x; --"})
