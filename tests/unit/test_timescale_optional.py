"""TimescaleDB is optional (ADR Decision 39): the decision, the plan and the no-op paths.

Nothing here needs TimescaleDB. The PostgreSQL case without the extension is
``tests/integration/test_timescale_optional_postgres.py``.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect

import eurogas_nexus.db.models  # noqa: F401 - registers every model
from eurogas_nexus.db import timescale
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.timescale import (
    HYPERTABLE_PLANS,
    SKIPPED_TABLES,
    Decision,
    ServerFacts,
    TableFacts,
    TimescaleRequiredError,
    catalogue_blockers,
    conversion_statements,
    decide,
    mode_from_env,
)

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "alembic" / "versions" / "0093_timescale_optional.py"
COMMUNITY = ServerFacts(
    dialect="postgresql",
    available_version="2.17.2",
    installed_version=None,
    preloaded=True,
    license="timescale",
)
#: The high-volume tables doc 19 names (sections 1.2 and 2.2): each is planned or skipped.
DOC19_HIGH_VOLUME = {
    "flow_observations",
    "capacity_observations",
    "power_observations",
    "storage_observations",
    "lng_observations",
    "market_observations",
    "forecast_observations",
    "market_quotes",
    "market_trades",
    "market_events",
    "market_event_deliveries",
    "raw_payload_archives",
    "audit_events",
}


def _migration():
    spec = importlib.util.spec_from_file_location("test_0093_timescale_optional", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --- the opt-in ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(None, "off"), ("", "off"), ("  ", "off"), ("off", "off"), ("AUTO", "auto"),
     (" require ", "require")],
)
def test_mode_defaults_to_off_and_reads_the_three_values(raw, expected):
    environ = {} if raw is None else {timescale.ENV_VAR: raw}
    assert mode_from_env(environ) == expected


@pytest.mark.parametrize("raw", ["on", "yes", "true", "1", "timescale"])
def test_an_unknown_mode_is_refused_not_guessed(raw):
    with pytest.raises(ValueError, match="off, auto, require"):
        mode_from_env({timescale.ENV_VAR: raw})


def test_default_is_off():
    assert timescale.DEFAULT_MODE == "off"


# --- the decision ----------------------------------------------------------------------


def test_community_edition_available_and_preloaded_is_used_under_auto_and_require():
    assert decide("auto", COMMUNITY).enabled
    assert decide("require", COMMUNITY).enabled


def test_off_wins_even_where_the_server_has_it():
    decision = decide("off", COMMUNITY)
    assert not decision.enabled
    assert "off" in decision.reason


@pytest.mark.parametrize(
    ("facts", "reason"),
    [
        (ServerFacts(dialect="sqlite"), "not PostgreSQL"),
        (ServerFacts(dialect="postgresql"), "not installed"),
        (ServerFacts(dialect="postgresql", available_version="2.17.2", preloaded=False,
                     license=None), "shared_preload_libraries"),
        (ServerFacts(dialect="postgresql", available_version="2.9.3", preloaded=True,
                     license="timescale"), "older than 2.13"),
        (ServerFacts(dialect="postgresql", available_version="2.17.2", preloaded=True,
                     license="apache"), "Apache-2 edition"),
        (ServerFacts(dialect="postgresql", available_version="2.17.2", preloaded=True,
                     license=None), "unset"),
    ],
)
def test_each_reason_not_to_convert_is_named(facts, reason):
    decision = decide("auto", facts)
    assert not decision.enabled
    assert reason in decision.reason


def test_an_installed_extension_is_judged_by_its_installed_version():
    facts = ServerFacts(dialect="postgresql", available_version="2.17.2",
                        installed_version="2.12.0", preloaded=True, license="timescale")
    assert "2.12.0 is older" in decide("auto", facts).reason


# --- the plan agrees with the models ----------------------------------------------------


def test_every_high_volume_table_is_either_converted_or_skipped_with_a_reason():
    planned = {plan.table for plan in HYPERTABLE_PLANS}
    assert planned == {"raw_payload_archives", "market_quotes", "market_trades"}
    assert not planned & set(SKIPPED_TABLES)
    assert planned | set(SKIPPED_TABLES) == DOC19_HIGH_VOLUME
    assert all(len(reason) > 40 for reason in SKIPPED_TABLES.values())


@pytest.mark.parametrize("plan", HYPERTABLE_PLANS, ids=lambda plan: plan.table)
def test_a_planned_table_has_only_its_id_as_unique_key_and_nothing_references_it(plan):
    table = Base.metadata.tables[plan.table]
    assert [column.name for column in table.primary_key.columns] == [plan.key_column]
    assert table.columns[plan.time_column].nullable is False
    assert not [c for c in table.constraints if c.__class__.__name__ == "UniqueConstraint"]
    assert not [index for index in table.indexes if index.unique]
    assert not any(column.unique for column in table.columns)
    for other in Base.metadata.tables.values():
        for column in other.columns:
            for key in column.foreign_keys:
                assert key.column.table.name != plan.table, f"{other.name} references it"
    for name in plan.segment_by:
        assert name in table.columns


def test_the_skipped_observation_tables_really_are_keyed_on_their_id_alone():
    for name, reason in SKIPPED_TABLES.items():
        table = Base.metadata.tables[name]
        assert len(table.primary_key.columns) >= 1
        if "upserts" in reason:
            assert [column.name for column in table.primary_key.columns][0] in reason


def test_the_outbox_skip_rests_on_its_foreign_key_and_unique_keys():
    deliveries = Base.metadata.tables["market_event_deliveries"]
    targets = {key.column.table.name for column in deliveries.columns
               for key in column.foreign_keys}
    assert "market_events" in targets
    assert "foreign key" in SKIPPED_TABLES["market_event_deliveries"]


# --- catalogue checks and DDL -----------------------------------------------------------

_PLAN = HYPERTABLE_PLANS[1]  # market_quotes
_PLAIN = TableFacts(exists=True, primary_key_name="market_quotes_pkey",
                    primary_key=("quote_id",), time_column_not_null=True)


def test_a_plain_table_as_migrated_has_no_blockers():
    assert catalogue_blockers(_PLAIN, _PLAN) == []


def test_an_already_widened_primary_key_is_accepted():
    facts = TableFacts(exists=True, primary_key=("quote_id", "observed_at_utc"),
                       time_column_not_null=True, is_hypertable=True)
    assert catalogue_blockers(facts, _PLAN) == []


@pytest.mark.parametrize(
    ("facts", "reason"),
    [
        (TableFacts(exists=False), "does not exist"),
        (TableFacts(exists=True, primary_key=("quote_id",)), "does not exist"),
        (TableFacts(exists=True, primary_key=("quote_id",), time_column_not_null=False),
         "nullable"),
        (TableFacts(exists=True, primary_key=("other",), time_column_not_null=True),
         "primary key is (other)"),
        (TableFacts(exists=True, primary_key=("quote_id",), time_column_not_null=True,
                    unique_without_time=("uq_quote_source",)), "uq_quote_source"),
        (TableFacts(exists=True, primary_key=("quote_id",), time_column_not_null=True,
                    referenced_by=("child.fk_quote",)), "child.fk_quote"),
    ],
)
def test_a_constraint_a_hypertable_would_break_blocks_the_conversion(facts, reason):
    assert any(reason in blocker for blocker in catalogue_blockers(facts, _PLAN))


def test_conversion_widens_the_key_then_converts_then_compresses():
    statements = conversion_statements(_PLAN, _PLAIN)
    assert statements[0] == 'ALTER TABLE "market_quotes" DROP CONSTRAINT "market_quotes_pkey"'
    assert 'PRIMARY KEY ("quote_id", "observed_at_utc")' in statements[1]
    assert "create_hypertable('market_quotes'::regclass, 'observed_at_utc'::name" in statements[2]
    assert "migrate_data => true" in statements[2]
    assert "create_default_indexes => false" in statements[2]
    assert "compress_segmentby = 'source_system, hub, product'" in statements[3]
    assert "add_compression_policy('market_quotes'::regclass, INTERVAL '7 days'" in statements[4]


def test_conversion_of_a_converted_table_only_ensures_the_policy():
    facts = TableFacts(exists=True, primary_key=("quote_id", "observed_at_utc"),
                       time_column_not_null=True, is_hypertable=True, compression_enabled=True)
    assert conversion_statements(_PLAN, facts) == [
        "SELECT add_compression_policy('market_quotes'::regclass, INTERVAL '7 days', "
        "if_not_exists => true)"
    ]


def test_a_plan_refuses_anything_but_plain_identifiers_and_intervals():
    with pytest.raises(ValueError):
        timescale.HypertablePlan("t; drop", "ts", "id", "1 day", (), "ts DESC", "7 days",
                                 False, "")
    with pytest.raises(ValueError):
        timescale.HypertablePlan("t", "ts", "id", "1 day'; --", (), "ts DESC", "7 days",
                                 False, "")


# --- apply's flow, with the catalogue faked ---------------------------------------------


class _Savepoint:
    def __init__(self, log):
        self.log = log

    def commit(self):
        self.log.append("RELEASE")

    def rollback(self):
        self.log.append("ROLLBACK")


class _Connection:
    def __init__(self, fail_on: str | None = None):
        self.log: list[str] = []
        self.fail_on = fail_on

    def begin_nested(self):
        self.log.append("SAVEPOINT")
        return _Savepoint(self.log)

    def execute(self, statement, params=None):
        sql = str(statement)
        if self.fail_on and self.fail_on in sql:
            raise RuntimeError("simulated failure")
        self.log.append(sql)


@pytest.fixture
def community(monkeypatch):
    monkeypatch.setattr(timescale, "server_facts", lambda connection: COMMUNITY)
    facts = {plan.table: TableFacts(exists=True, primary_key_name=f"{plan.table}_pkey",
                                    primary_key=(plan.key_column,), time_column_not_null=True)
             for plan in HYPERTABLE_PLANS}
    monkeypatch.setattr(timescale, "table_facts", lambda connection, plan: facts[plan.table])
    return facts


def test_apply_creates_the_extension_and_converts_each_planned_table(community):
    connection = _Connection()
    report = timescale.apply(connection, mode="auto")
    assert report.decision.enabled
    assert report.converted == ["raw_payload_archives", "market_quotes", "market_trades"]
    assert "CREATE EXTENSION IF NOT EXISTS timescaledb" in connection.log
    assert sum("create_hypertable" in line for line in connection.log) == 3
    assert set(SKIPPED_TABLES) <= set(report.skipped)
    assert not report.failed


def test_under_auto_a_failing_table_is_rolled_back_and_the_others_proceed(community):
    connection = _Connection(fail_on="create_hypertable('market_quotes'")
    report = timescale.apply(connection, mode="auto")
    assert report.converted == ["raw_payload_archives", "market_trades"]
    assert "market_quotes" in report.failed
    assert "ROLLBACK" in connection.log


def test_under_require_a_failing_table_stops_the_migration(community):
    with pytest.raises(RuntimeError, match="simulated failure"):
        timescale.apply(_Connection(fail_on="create_hypertable('market_quotes'"),
                        mode="require")


def test_under_auto_a_refused_create_extension_leaves_everything_plain(community):
    connection = _Connection(fail_on="CREATE EXTENSION")
    report = timescale.apply(connection, mode="auto")
    assert not report.decision.enabled
    assert "CREATE EXTENSION" in report.decision.reason
    assert report.converted == []
    assert not any("create_hypertable" in line for line in connection.log)


def test_a_blocked_table_is_skipped_with_its_reason(community):
    community["market_trades"] = TableFacts(exists=True, primary_key=("trade_id",),
                                            time_column_not_null=True,
                                            referenced_by=("x.fk_trade",))
    report = timescale.apply(_Connection(), mode="auto")
    assert "x.fk_trade" in report.skipped["market_trades"]
    assert "market_trades" not in report.converted


# --- SQLite and the migration ----------------------------------------------------------


def _sqlite_with_models():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


def _schema(engine) -> dict:
    inspector = inspect(engine)
    return {
        name: (
            [column["name"] for column in inspector.get_columns(name)],
            inspector.get_pk_constraint(name)["constrained_columns"],
            sorted(index["name"] for index in inspector.get_indexes(name)),
        )
        for name in inspector.get_table_names()
    }


@pytest.mark.parametrize("mode", ["off", "auto"])
def test_apply_on_sqlite_changes_nothing(mode):
    engine = _sqlite_with_models()
    before = _schema(engine)
    with engine.begin() as connection:
        report = timescale.apply(connection, mode=mode)
    assert not report.decision.enabled
    assert report.converted == []
    assert _schema(engine) == before


def test_require_on_sqlite_is_refused():
    engine = _sqlite_with_models()
    with engine.begin() as connection, pytest.raises(TimescaleRequiredError, match="sqlite"):
        timescale.apply(connection, mode="require")


@pytest.mark.parametrize("mode", ["off", "auto", ""])
def test_the_migration_is_a_no_op_on_sqlite_both_ways(monkeypatch, mode):
    monkeypatch.setenv(timescale.ENV_VAR, mode)
    engine = _sqlite_with_models()
    before = _schema(engine)
    migration = _migration()
    with engine.begin() as connection:
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        assert _schema(engine) == before
        migration.downgrade()
    assert _schema(engine) == before


def test_the_migration_chains_after_0092():
    migration = _migration()
    assert migration.revision == "0093_timescale_optional"
    assert len(migration.revision) <= 32
    assert migration.down_revision == "0092_lng_berth_rules"


def test_state_on_sqlite_and_on_an_unreachable_store():
    engine = _sqlite_with_models()
    with engine.connect() as connection:
        assert timescale.state(connection) == "not_postgresql"
        assert not timescale.is_active(connection)
    broken = create_engine("postgresql+pg8000://nobody@127.0.0.1:1/none",
                           connect_args={"timeout": 1})
    assert timescale.engine_state(broken) == "unknown"


def test_the_report_reads_as_plain_data():
    report = timescale.ApplyReport(mode="auto", decision=Decision(False, "absent"))
    assert report.as_dict() == {
        "mode": "auto", "enabled": False, "reason": "absent", "converted": [],
        "already_hypertables": [], "skipped": {}, "failed": {},
    }
