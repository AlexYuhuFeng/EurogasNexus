"""Real SQLite and optional PostgreSQL checks for National Gas REST evidence."""

from __future__ import annotations

import importlib.util
import os
import uuid
from collections.abc import Iterator
from datetime import UTC, date, datetime
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
from eurogas_nexus.db.models.demand import NationalGasActualDemandRecord
from eurogas_nexus.release.constants import DB_SCHEMA_REVISION

ROOT = Path(__file__).resolve().parents[2]
RECEIVED = datetime(2026, 10, 27, 13, 0, tzinfo=UTC)
RAW_SHA256 = "a" * 64

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
    """Capture the optional PostgreSQL DSN before autouse fixtures clear it."""

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


def _values(key: str = "one", **overrides):
    values = {
        "record_id": f"ngd-{key}",
        "source_publication_id": f"pub-{key}",
        "provider_item_id": "PUBOB637",
        "series_key": "national-gas:GB_NTS:PUBOB637",
        "region": "GB_NTS",
        "term": "D+1",
        "label": "Demand Actual, NTS, D+1",
        "gas_day": date(2026, 10, 27),
        "period_start_utc": datetime(2026, 10, 27, 4, 0, tzinfo=UTC),
        "period_end_utc": datetime(2026, 10, 28, 4, 0, tzinfo=UTC),
        "value_text": "176.708",
        "unit": "mscm",
        "received_at_utc": RECEIVED,
        "available_at_utc": RECEIVED,
        "ingested_at_utc": RECEIVED,
        "published_at_utc": None,
        "applicable_at_raw": "27/10/2026 05:00:00",
        "generated_at_raw": "27/10/2026 12:20:01",
        "applicable_at_naive": datetime(2026, 10, 27, 5, 0),
        "generated_at_naive": datetime(2026, 10, 27, 12, 20, 1),
        "quality_indicator": None,
        "provisional_status": "PROVISIONAL",
        "is_provisional": True,
        "raw_sha256": RAW_SHA256,
        "source_url": "https://example.invalid/national-gas.csv",
        "hash_schema": "sha256-canonical/v1",
    }
    values.update(overrides)
    return values


@pytest.fixture
def engine() -> Iterator[sa.Engine]:
    active = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(
        active,
        tables=[NationalGasActualDemandRecord.__table__],
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
    """Yield an engine isolated in a throw-away PostgreSQL schema.

    The test is skipped unless a PostgreSQL test DSN is configured.  The unique
    schema keeps the exercise non-destructive: cleanup drops only that schema.
    """

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

    schema = f"demand_rest_{uuid.uuid4().hex[:12]}"
    if not (schema.isascii() and schema.isidentifier()):
        raise ValueError(f"unexpected PostgreSQL schema name: {schema!r}")
    with admin.begin() as connection:
        connection.execute(sa.text(f'CREATE SCHEMA "{schema}"'))

    def _pin_search_path(dbapi_connection, _connection_record) -> None:
        """Apply search_path outside a transaction so rollbacks cannot undo it."""

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

    engine = create_engine(POSTGRES_URL)
    sa.event.listen(engine, "connect", _pin_search_path)
    try:
        yield engine
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(
                sa.text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
            )
        admin.dispose()


@pytest.fixture
def session(engine: sa.Engine) -> Iterator[Session]:
    with Session(engine) as active:
        yield active


def _reject(session: Session, key: str, **overrides) -> None:
    session.add(NationalGasActualDemandRecord(**_values(key, **overrides)))
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


def _upgrade_to_0043(connection: sa.Connection) -> ModuleType:
    _run(
        connection,
        _migration("0042_national_gas_actual_demand.py"),
        "upgrade",
    )
    evidence = _migration("0043_national_gas_rest_evidence.py")
    _run(connection, evidence, "upgrade")
    return evidence


def _reflected(engine_or_connection, table_name: str = "national_gas_actual_demand"):
    return sa.Table(table_name, sa.MetaData(), autoload_with=engine_or_connection)


def test_schema_revision_matches_the_0043_migration():
    migration = _migration("0043_national_gas_rest_evidence.py")

    assert DB_SCHEMA_REVISION == "0043_national_gas_rest_evidence"
    assert migration.revision == DB_SCHEMA_REVISION
    assert migration.down_revision == "0042_national_gas_actual_demand"


def test_model_defaults_are_csv_and_not_blank(session: Session):
    row = NationalGasActualDemandRecord(**_values())
    session.add(row)
    session.commit()
    session.refresh(row)

    assert row.source_format == "CSV"
    assert row.value_is_blank is False
    assert row.rest_provenance is None


def test_sqlite_server_defaults_apply_without_orm_defaults(engine: sa.Engine):
    table = _reflected(engine)
    with engine.begin() as connection:
        connection.execute(table.insert().values(**_values("server")))
        stored = (
            connection.execute(
                select(table).where(table.c.record_id == "ngd-server")
            )
            .mappings()
            .one()
        )

    assert stored["source_format"] == "CSV"
    assert stored["value_is_blank"] == 0
    assert stored["rest_provenance"] is None


def test_csv_value_text_keeps_nonempty_and_max_64(session: Session):
    session.add(NationalGasActualDemandRecord(**_values("max", value_text="1" * 64)))
    session.commit()

    _reject(session, "empty", value_text="")
    _reject(session, "long", value_text="1" * 65)


def test_blank_value_is_permitted_only_when_explicitly_flagged(session: Session):
    blank = NationalGasActualDemandRecord(
        **_values("blank", value_text="", value_is_blank=True)
    )
    session.add(blank)
    session.commit()
    session.refresh(blank)

    assert blank.value_text == ""
    assert blank.value_is_blank is True

    _reject(session, "nonblank-flag", value_text="176.708", value_is_blank=True)
    _reject(session, "whitespace-flag", value_text=" ", value_is_blank=True)


def test_source_format_allowlist_and_rest_provenance_requirement(session: Session):
    _reject(session, "xml", source_format="XML")
    _reject(session, "rest-missing", source_format="REST")

    rest = NationalGasActualDemandRecord(
        **_values(
            "rest",
            source_format="REST",
            rest_provenance={"request_id": "req-1", "source": "national-gas-rest"},
        )
    )
    session.add(rest)
    session.commit()
    session.refresh(rest)

    assert rest.source_format == "REST"
    assert rest.rest_provenance == {
        "request_id": "req-1",
        "source": "national-gas-rest",
    }


def test_migration_upgrade_preserves_csv_row_and_adds_defaults(
    migration_engine: sa.Engine,
):
    with migration_engine.begin() as connection:
        _run(
            connection,
            _migration("0042_national_gas_actual_demand.py"),
            "upgrade",
        )
        legacy = _reflected(connection)
        connection.execute(legacy.insert().values(**_values("legacy")))
        before = (
            connection.execute(
                select(legacy).where(legacy.c.record_id == "ngd-legacy")
            )
            .mappings()
            .one()
        )

        _run(
            connection,
            _migration("0043_national_gas_rest_evidence.py"),
            "upgrade",
        )
        upgraded = _reflected(connection)
        after = (
            connection.execute(
                select(upgraded).where(upgraded.c.record_id == "ngd-legacy")
            )
            .mappings()
            .one()
        )

    for column in legacy.c:
        assert after[column.name] == before[column.name]
    assert after["source_format"] == "CSV"
    assert after["value_is_blank"] == 0
    assert after["rest_provenance"] is None


def test_migration_downgrade_refuses_rest_and_blank_evidence(
    migration_engine: sa.Engine,
):
    with migration_engine.begin() as connection:
        evidence = _upgrade_to_0043(connection)
        table = _reflected(connection)
        connection.execute(
            table.insert().values(
                **_values(
                    "rest",
                    source_format="REST",
                    rest_provenance={"source": "rest"},
                )
            )
        )
        connection.execute(
            table.insert().values(
                **_values("blank", value_text="", value_is_blank=True)
            )
        )
        before_count = connection.scalar(
            select(sa.func.count()).select_from(table)
        )

        with pytest.raises(RuntimeError, match="REST or blank-value"):
            _run(connection, evidence, "downgrade")

        assert (
            connection.scalar(select(sa.func.count()).select_from(table))
            == before_count
            == 2
        )
        columns = {
            column["name"]
            for column in sa.inspect(connection).get_columns(
                "national_gas_actual_demand"
            )
        }
        assert {"source_format", "rest_provenance", "value_is_blank"} <= columns


def test_migration_downgrade_without_rest_or_blank_preserves_csv(
    migration_engine: sa.Engine,
):
    with migration_engine.begin() as connection:
        evidence = _upgrade_to_0043(connection)
        table = _reflected(connection)
        connection.execute(table.insert().values(**_values("csv")))
        before = (
            connection.execute(
                select(table).where(table.c.record_id == "ngd-csv")
            )
            .mappings()
            .one()
        )

        _run(connection, evidence, "downgrade")

        columns = {
            column["name"]
            for column in sa.inspect(connection).get_columns(
                "national_gas_actual_demand"
            )
        }
        assert not {"source_format", "rest_provenance", "value_is_blank"} & columns

        downgraded = _reflected(connection)
        after = (
            connection.execute(
                select(downgraded).where(downgraded.c.record_id == "ngd-csv")
            )
            .mappings()
            .one()
        )

    for column in downgraded.c:
        assert after[column.name] == before[column.name]
    assert after["value_text"] == "176.708"


def test_postgres_upgrade_and_downgrade_execute(
    postgres_migration_engine: sa.Engine,
):
    with postgres_migration_engine.begin() as connection:
        evidence = _migration("0043_national_gas_rest_evidence.py")
        _run(
            connection,
            _migration("0042_national_gas_actual_demand.py"),
            "upgrade",
        )
        legacy = _reflected(connection)
        connection.execute(legacy.insert().values(**_values("pg-csv")))

        _run(connection, evidence, "upgrade")
        upgraded = _reflected(connection)
        stored = (
            connection.execute(
                select(upgraded).where(upgraded.c.record_id == "ngd-pg-csv")
            )
            .mappings()
            .one()
        )
        assert stored["value_text"] == "176.708"
        assert stored["source_format"] == "CSV"
        assert stored["value_is_blank"] is False
        assert stored["rest_provenance"] is None

        checks = {
            constraint["name"]
            for constraint in sa.inspect(connection).get_check_constraints(
                "national_gas_actual_demand"
            )
        }
        assert {
            "ck_ng_actual_demand_source_format",
            "ck_ng_actual_demand_rest_provenance",
            "ck_ng_actual_demand_value_text",
        } <= checks
        indexes = {
            index["name"]
            for index in sa.inspect(connection).get_indexes(
                "national_gas_actual_demand"
            )
        }
        assert {
            "ix_national_gas_actual_demand_series_gas_day",
            "ix_national_gas_actual_demand_published_utc",
        } <= indexes

        connection.execute(
            upgraded.insert().values(
                **_values(
                    "pg-rest",
                    source_format="REST",
                    rest_provenance={"source": "rest"},
                )
            )
        )
        with pytest.raises(RuntimeError, match="REST or blank-value"):
            _run(connection, evidence, "downgrade")

        still_upgraded = _reflected(connection)
        assert (
            connection.scalar(select(sa.func.count()).select_from(still_upgraded))
            == 2
        )

        connection.execute(
            sa.delete(still_upgraded).where(
                still_upgraded.c.record_id == "ngd-pg-rest"
            )
        )
        _run(connection, evidence, "downgrade")

        downgraded = _reflected(connection)
        columns = {
            column["name"]
            for column in sa.inspect(connection).get_columns(
                "national_gas_actual_demand"
            )
        }
        assert not {"source_format", "rest_provenance", "value_is_blank"} & columns
        preserved = (
            connection.execute(
                select(downgraded).where(downgraded.c.record_id == "ngd-pg-csv")
            )
            .mappings()
            .one()
        )
        assert preserved["value_text"] == "176.708"
