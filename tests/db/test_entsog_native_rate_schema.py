"""Real SQLite and optional PostgreSQL checks for ENTSOG native-rate evidence."""

from __future__ import annotations

import importlib.util
import os
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, select
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models.observation import (
    CapacityObservationRecord,
    FlowObservationRecord,
)
from eurogas_nexus.release.constants import DB_SCHEMA_REVISION

ROOT = Path(__file__).resolve().parents[2]
OBSERVED = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)
NATIVE_VERSION = "entsog-native-units-v1"
NATIVE_PAYLOAD = {
    "value": "1000000",
    "unit": "kWh/d",
    "rate": "0.000024",
    "quantity_kind": "energy",
    "basis": "day",
    "normalizer_version": NATIVE_VERSION,
}

_POSTGRES_DSN_ENV = (
    "EUROGAS_NEXUS_TEST_POSTGRES_URL",
    "EUROGAS_NEXUS_TEST_DATABASE_URL",
    "EUROGAS_NEXUS_POSTGRES_URL",
    "TEST_POSTGRES_URL",
    "TEST_DATABASE_URL",
    "POSTGRES_URL",
    "DATABASE_URL",
    "EUROGAS_NEXUS_DB_DSN",
)


def _configured_postgres_url() -> URL | None:
    for name in _POSTGRES_DSN_ENV:
        raw = os.environ.get(name)
        if not raw:
            continue
        try:
            url = make_url(raw)
        except ValueError:
            continue
        if url.get_backend_name() == "postgresql":
            return url
    return None


POSTGRES_URL = _configured_postgres_url()


def _flow_values(key: str = "one", **overrides):
    values = {
        "observation_id": f"flow-{key}",
        "point_id": "DE-TSO-0001",
        "point_name": "Example entry point",
        "direction": "entry",
        "kind": "actual",
        "flow_mcm_d": 12.5,
        "original_value": 12.5,
        "original_unit": "mcm/d",
        "period_start_utc": datetime(2026, 10, 28, 4, 0, tzinfo=UTC),
        "period_end_utc": datetime(2026, 10, 29, 4, 0, tzinfo=UTC),
        "observed_at_utc": OBSERVED,
        "source_system": "entsog",
        "source_reference": f"flow-{key}",
        "source_record_id": f"flow-{key}",
        "freshness": "confirmed",
        "research_only": True,
        "metadata_json": {"provider": "entsog"},
    }
    values.update(overrides)
    return values


def _capacity_values(key: str = "one", **overrides):
    values = {
        "observation_id": f"capacity-{key}",
        "point_id": "DE-TSO-0001",
        "point_name": "Example entry point",
        "direction": "entry",
        "capacity_type": "technical",
        "capacity_mcm_d": 25.0,
        "original_value": 25.0,
        "original_unit": "mcm/d",
        "period_start_utc": datetime(2026, 10, 28, 4, 0, tzinfo=UTC),
        "period_end_utc": datetime(2026, 10, 29, 4, 0, tzinfo=UTC),
        "observed_at_utc": OBSERVED,
        "source_system": "entsog",
        "source_reference": f"capacity-{key}",
        "source_record_id": f"capacity-{key}",
        "freshness": "confirmed",
        "research_only": True,
        "metadata_json": {"provider": "entsog"},
    }
    values.update(overrides)
    return values


@pytest.fixture
def engine() -> Iterator[sa.Engine]:
    active = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(
        active,
        tables=[
            FlowObservationRecord.__table__,
            CapacityObservationRecord.__table__,
        ],
    )
    try:
        yield active
    finally:
        active.dispose()


@pytest.fixture
def migration_engine() -> Iterator[sa.Engine]:
    active = create_engine("sqlite+pysqlite:///:memory:")
    try:
        yield active
    finally:
        active.dispose()


@pytest.fixture
def postgres_migration_engine() -> Iterator[sa.Engine]:
    """Yield an engine isolated in a throw-away PostgreSQL schema."""

    if POSTGRES_URL is None:
        pytest.skip(
            "no PostgreSQL test DSN configured; set "
            "EUROGAS_NEXUS_TEST_POSTGRES_URL to run this test"
        )
    try:
        admin = create_engine(POSTGRES_URL, isolation_level="AUTOCOMMIT")
        with admin.connect() as connection:
            connection.execute(sa.text("SELECT 1"))
    except ModuleNotFoundError as exc:
        pytest.skip(f"PostgreSQL driver unavailable: {exc}")

    schema = f"entsog_native_{uuid.uuid4().hex[:12]}"
    if not (schema.isascii() and schema.isidentifier()):
        raise ValueError(f"unexpected PostgreSQL schema name: {schema!r}")
    with admin.begin() as connection:
        connection.execute(sa.text(f'CREATE SCHEMA "{schema}"'))

    def _pin_search_path(dbapi_connection, _connection_record) -> None:
        previous_autocommit = dbapi_connection.autocommit
        dbapi_connection.autocommit = True
        try:
            cursor = dbapi_connection.cursor()
            try:
                cursor.execute(f'SET search_path TO "{schema}"')
            finally:
                cursor.close()
        finally:
            dbapi_connection.autocommit = previous_autocommit

    active = create_engine(POSTGRES_URL)
    sa.event.listen(active, "connect", _pin_search_path)
    try:
        yield active
    finally:
        active.dispose()
        with admin.begin() as connection:
            connection.execute(sa.text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        admin.dispose()


@pytest.fixture
def session(engine: sa.Engine) -> Iterator[Session]:
    with Session(engine) as active:
        yield active


def _reject(session: Session, model, key: str, **overrides) -> None:
    if model is FlowObservationRecord:
        values = _flow_values(key, **overrides)
    else:
        values = _capacity_values(key, **overrides)
    session.add(model(**values))
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def _migration(filename: str) -> ModuleType:
    path = ROOT / "alembic" / "versions" / filename
    spec = importlib.util.spec_from_file_location(f"test_{path.stem}", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(connection: sa.Connection, module: ModuleType, operation: str) -> None:
    module.op = Operations(MigrationContext.configure(connection))
    getattr(module, operation)()


def _tables(migration: ModuleType, *, with_native_columns: bool):
    return (
        migration._table(with_native_columns=with_native_columns),
        migration._capacity_table(with_native_columns=with_native_columns),
    )


def _create_legacy_schema(connection: sa.Connection, migration: ModuleType):
    flow, capacity = _tables(migration, with_native_columns=False)
    sa.Index(
        "ix_flow_observations_point_period",
        flow.c.point_id,
        flow.c.period_start_utc,
    )
    sa.Index(
        "ix_capacity_observations_point_period",
        capacity.c.point_id,
        capacity.c.period_start_utc,
    )
    flow.append_constraint(
        sa.CheckConstraint(
            "direction IN ('entry', 'exit')",
            name="ck_flow_observations_direction",
        )
    )
    capacity.append_constraint(
        sa.CheckConstraint(
            "direction IN ('entry', 'exit')",
            name="ck_capacity_observations_direction",
        )
    )
    flow.create(connection)
    capacity.create(connection)
    return flow, capacity


def _reflected(connection: sa.Connection, table_name: str):
    return sa.Table(table_name, sa.MetaData(), autoload_with=connection)


def _table_columns(connection: sa.Connection, table_name: str) -> dict[str, dict]:
    return {
        column["name"]: column
        for column in sa.inspect(connection).get_columns(table_name)
    }


def _assert_invalid_insert(connection: sa.Connection, table, values) -> None:
    with pytest.raises(IntegrityError):
        with connection.begin_nested():
            connection.execute(table.insert().values(**values))


def test_schema_revision_and_model_native_contract():
    migration = _migration("0044_entsog_native_rates.py")

    # The ENTSOG native-rate migration is no longer head; it stays in the chain.
    assert migration.revision == "0044_entsog_native_rates"
    assert DB_SCHEMA_REVISION == "0052_trading_books"
    assert migration.down_revision == "0043_national_gas_rest_evidence"

    for model, volume_column, check_name in (
        (
            FlowObservationRecord,
            "flow_mcm_d",
            "ck_flow_observations_native_rate_evidence",
        ),
        (
            CapacityObservationRecord,
            "capacity_mcm_d",
            "ck_capacity_observations_native_rate_evidence",
        ),
    ):
        columns = model.__table__.c
        assert columns[volume_column].nullable is True
        assert columns["normalizer_version"].type.length == 64
        assert columns["normalizer_version"].nullable is True
        assert columns["native_rate_json"].nullable is True
        assert columns["native_rate_json"].type.none_as_null is True
        assert check_name in {
            constraint.name for constraint in model.__table__.constraints
        }


def test_legacy_and_native_rows_are_accepted_with_exact_payload(session: Session):
    legacy_flow = FlowObservationRecord(**_flow_values("legacy-flow"))
    legacy_capacity = CapacityObservationRecord(**_capacity_values("legacy-capacity"))
    native_flow = FlowObservationRecord(
        **_flow_values(
            "native-flow",
            flow_mcm_d=None,
            normalizer_version=NATIVE_VERSION,
            native_rate_json=NATIVE_PAYLOAD,
        )
    )
    native_capacity = CapacityObservationRecord(
        **_capacity_values(
            "native-capacity",
            capacity_mcm_d=None,
            normalizer_version=NATIVE_VERSION,
            native_rate_json=NATIVE_PAYLOAD,
        )
    )
    session.add_all([legacy_flow, legacy_capacity, native_flow, native_capacity])
    session.commit()

    for row in (legacy_flow, legacy_capacity):
        session.refresh(row)
        assert row.normalizer_version is None
        assert row.native_rate_json is None
    for row in (native_flow, native_capacity):
        session.refresh(row)
        assert row.normalizer_version == NATIVE_VERSION
        assert row.native_rate_json == NATIVE_PAYLOAD


@pytest.mark.parametrize("model", [FlowObservationRecord, CapacityObservationRecord])
def test_partial_and_unknown_native_versions_are_rejected(session: Session, model):
    volume_override = (
        {"flow_mcm_d": None}
        if model is FlowObservationRecord
        else {"capacity_mcm_d": None}
    )
    _reject(session, model, "null-volume", **volume_override)
    _reject(session, model, "payload-only", native_rate_json=NATIVE_PAYLOAD)
    _reject(
        session,
        model,
        "version-only",
        normalizer_version=NATIVE_VERSION,
    )
    _reject(
        session,
        model,
        "unknown",
        normalizer_version="entsog-native-units-v2",
        native_rate_json=NATIVE_PAYLOAD,
    )
    _reject(
        session,
        model,
        "unknown-null",
        **(
            {"flow_mcm_d": None}
            if model is FlowObservationRecord
            else {"capacity_mcm_d": None}
        ),
        normalizer_version="entsog-native-units-v2",
        native_rate_json=NATIVE_PAYLOAD,
    )


def test_sqlite_upgrade_preserves_legacy_rows_and_adds_native_contract(
    migration_engine: sa.Engine,
):
    migration = _migration("0044_entsog_native_rates.py")
    with migration_engine.begin() as connection:
        legacy_flow, legacy_capacity = _create_legacy_schema(connection, migration)
        connection.execute(legacy_flow.insert().values(**_flow_values("legacy-flow")))
        connection.execute(
            legacy_capacity.insert().values(**_capacity_values("legacy-capacity"))
        )
        before_flow = (
            connection.execute(
                select(legacy_flow).where(
                    legacy_flow.c.observation_id == "flow-legacy-flow"
                )
            )
            .mappings()
            .one()
        )
        before_capacity = (
            connection.execute(
                select(legacy_capacity).where(
                    legacy_capacity.c.observation_id == "capacity-legacy-capacity"
                )
            )
            .mappings()
            .one()
        )

        _run(connection, migration, "upgrade")

        flow_columns = _table_columns(connection, "flow_observations")
        assert str(flow_columns["kind"]["default"]).strip("'") == "actual"
        capacity_columns = _table_columns(connection, "capacity_observations")
        for columns, volume_column in (
            (flow_columns, "flow_mcm_d"),
            (capacity_columns, "capacity_mcm_d"),
        ):
            assert columns[volume_column]["nullable"] is True
            assert columns["normalizer_version"]["nullable"] is True
            assert columns["native_rate_json"]["nullable"] is True

        flow = _reflected(connection, "flow_observations")
        capacity = _reflected(connection, "capacity_observations")
        after_flow = (
            connection.execute(
                select(flow).where(flow.c.observation_id == "flow-legacy-flow")
            )
            .mappings()
            .one()
        )
        after_capacity = (
            connection.execute(
                select(capacity).where(
                    capacity.c.observation_id == "capacity-legacy-capacity"
                )
            )
            .mappings()
            .one()
        )
        for column in before_flow:
            assert after_flow[column] == before_flow[column]
        for column in before_capacity:
            assert after_capacity[column] == before_capacity[column]
        assert after_flow["normalizer_version"] is None
        assert after_flow["native_rate_json"] is None
        assert after_capacity["normalizer_version"] is None
        assert after_capacity["native_rate_json"] is None

        indexes = {
            index["name"]
            for index in sa.inspect(connection).get_indexes("flow_observations")
        }
        assert "ix_flow_observations_point_period" in indexes

        connection.execute(
            flow.insert().values(
                **_flow_values(
                    "native-flow",
                    flow_mcm_d=None,
                    normalizer_version=NATIVE_VERSION,
                    native_rate_json=NATIVE_PAYLOAD,
                )
            )
        )
        connection.execute(
            capacity.insert().values(
                **_capacity_values(
                    "native-capacity",
                    capacity_mcm_d=None,
                    normalizer_version=NATIVE_VERSION,
                    native_rate_json=NATIVE_PAYLOAD,
                )
            )
        )

        _assert_invalid_insert(
            connection,
            flow,
            _flow_values("null-volume", flow_mcm_d=None),
        )
        _assert_invalid_insert(
            connection,
            flow,
            _flow_values("payload-only", native_rate_json=NATIVE_PAYLOAD),
        )
        _assert_invalid_insert(
            connection,
            flow,
            _flow_values(
                "unknown",
                normalizer_version=NATIVE_VERSION + "-x",
                native_rate_json=NATIVE_PAYLOAD,
            ),
        )
        _assert_invalid_insert(
            connection,
            flow,
            _flow_values("bad-direction", direction="sideways"),
        )

        with pytest.raises(RuntimeError, match="native-rate evidence"):
            _run(connection, migration, "downgrade")

        for table_name in ("flow_observations", "capacity_observations"):
            columns = _table_columns(connection, table_name)
            assert {"normalizer_version", "native_rate_json"} <= columns.keys()

        still_flow = _reflected(connection, "flow_observations")
        still_capacity = _reflected(connection, "capacity_observations")
        assert still_flow.c.normalizer_version is not None
        assert still_capacity.c.normalizer_version is not None

        connection.execute(
            sa.delete(still_flow).where(still_flow.c.observation_id == "flow-native-flow")
        )
        connection.execute(
            sa.delete(still_capacity).where(
                still_capacity.c.observation_id == "capacity-native-capacity"
            )
        )

        _run(connection, migration, "downgrade")

        for table_name, removed in (
            ("flow_observations", {"normalizer_version", "native_rate_json"}),
            ("capacity_observations", {"normalizer_version", "native_rate_json"}),
        ):
            columns = _table_columns(connection, table_name)
            assert not removed & columns.keys()
        assert _table_columns(connection, "flow_observations")["flow_mcm_d"][
            "nullable"
        ] is False
        assert _table_columns(connection, "capacity_observations")["capacity_mcm_d"][
            "nullable"
        ] is False

        downgraded_flow = _reflected(connection, "flow_observations")
        downgraded_capacity = _reflected(connection, "capacity_observations")
        _assert_invalid_insert(
            connection,
            downgraded_flow,
            _flow_values("bad-direction", direction="sideways"),
        )
        preserved_flow = (
            connection.execute(
                select(downgraded_flow).where(
                    downgraded_flow.c.observation_id == "flow-legacy-flow"
                )
            )
            .mappings()
            .one()
        )
        preserved_capacity = (
            connection.execute(
                select(downgraded_capacity).where(
                    downgraded_capacity.c.observation_id == "capacity-legacy-capacity"
                )
            )
            .mappings()
            .one()
        )
        assert dict(preserved_flow) == dict(before_flow)
        assert dict(preserved_capacity) == dict(before_capacity)

        indexes = {
            index["name"]
            for index in sa.inspect(connection).get_indexes("flow_observations")
        }
        assert "ix_flow_observations_point_period" in indexes


@pytest.mark.parametrize(
    ("evidence_table", "native_values"),
    [
        (
            "flow_observations",
            _flow_values(
                "native",
                flow_mcm_d=None,
                normalizer_version=NATIVE_VERSION,
                native_rate_json=NATIVE_PAYLOAD,
            ),
        ),
        (
            "capacity_observations",
            _capacity_values(
                "native",
                capacity_mcm_d=None,
                normalizer_version=NATIVE_VERSION,
                native_rate_json=NATIVE_PAYLOAD,
            ),
        ),
    ],
)
def test_downgrade_refusal_checks_both_tables_before_any_ddl(
    migration_engine: sa.Engine,
    evidence_table: str,
    native_values: dict,
):
    migration = _migration("0044_entsog_native_rates.py")
    with migration_engine.begin() as connection:
        legacy_flow, legacy_capacity = _create_legacy_schema(connection, migration)
        connection.execute(legacy_flow.insert().values(**_flow_values("legacy-flow")))
        connection.execute(
            legacy_capacity.insert().values(**_capacity_values("legacy-capacity"))
        )
        _run(connection, migration, "upgrade")

        flow = _reflected(connection, "flow_observations")
        capacity = _reflected(connection, "capacity_observations")
        target = flow if evidence_table == "flow_observations" else capacity
        connection.execute(target.insert().values(**native_values))

        with pytest.raises(RuntimeError, match="native-rate evidence"):
            _run(connection, migration, "downgrade")

        for table_name in ("flow_observations", "capacity_observations"):
            assert {"normalizer_version", "native_rate_json"} <= _table_columns(
                connection, table_name
            ).keys()
        counts = (
            connection.scalar(select(sa.func.count()).select_from(flow)),
            connection.scalar(select(sa.func.count()).select_from(capacity)),
        )
        expected = (2, 1) if evidence_table == "flow_observations" else (1, 2)
        assert counts == expected


def test_postgres_upgrade_downgrade_and_refusal(
    postgres_migration_engine: sa.Engine,
):
    migration = _migration("0044_entsog_native_rates.py")
    with postgres_migration_engine.begin() as connection:
        legacy_flow, legacy_capacity = _create_legacy_schema(connection, migration)
        connection.execute(legacy_flow.insert().values(**_flow_values("legacy-flow")))
        connection.execute(
            legacy_capacity.insert().values(**_capacity_values("legacy-capacity"))
        )

        _run(connection, migration, "upgrade")

        checks = {
            constraint["name"]
            for constraint in sa.inspect(connection).get_check_constraints(
                "flow_observations"
            )
        }
        assert "ck_flow_observations_native_rate_evidence" in checks
        indexes = {
            index["name"]
            for index in sa.inspect(connection).get_indexes("flow_observations")
        }
        assert "ix_flow_observations_point_period" in indexes

        flow = _reflected(connection, "flow_observations")
        connection.execute(
            flow.insert().values(
                **_flow_values(
                    "native-flow",
                    flow_mcm_d=None,
                    normalizer_version=NATIVE_VERSION,
                    native_rate_json=NATIVE_PAYLOAD,
                )
            )
        )
        with pytest.raises(RuntimeError, match="native-rate evidence"):
            _run(connection, migration, "downgrade")
        assert "normalizer_version" in _table_columns(connection, "capacity_observations")

        connection.execute(
            sa.delete(flow).where(flow.c.observation_id == "flow-native-flow")
        )
        _run(connection, migration, "downgrade")

        assert "normalizer_version" not in _table_columns(connection, "flow_observations")
        downgraded = _reflected(connection, "flow_observations")
        preserved = (
            connection.execute(
                select(downgraded).where(
                    downgraded.c.observation_id == "flow-legacy-flow"
                )
            )
            .mappings()
            .one()
        )
        assert preserved["flow_mcm_d"] == 12.5
        assert preserved["kind"] == "actual"
