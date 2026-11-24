"""GOV-1 (P6): the licensed-use meter, the aggregated usage record and the file decision."""

from __future__ import annotations

import importlib.util
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

from eurogas_nexus.application.licensed_use import licensed_families, usage_surface
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import LicensedDataUseRecord
from eurogas_nexus.db.repositories.licensed_use import record_licensed_use, usage_by_family
from eurogas_nexus.domain.dataops.entitlement import filter_rows_for_principal
from eurogas_nexus.governance.entitlement import ExportDecision, file_export_decision
from eurogas_nexus.governance.usage import LicensedUseMeter, metering, not_metered
from eurogas_nexus.release.constants import DB_SCHEMA_REVISION
from eurogas_nexus.security.identity import (
    AuthenticatedPrincipal,
    legacy_public_token_principal,
    principal_allows_source_family,
)

VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"
NOW = datetime(2026, 11, 24, 9, tzinfo=UTC)


def _analyst(*scopes: str) -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        principal_id="usr-analyst", name="analyst", principal_type="USER", role="ANALYST",
        status="ACTIVE", data_scopes=tuple(scopes), auth_method="api_key",
    )


def test_a_request_meter_holds_each_licensed_family_it_was_allowed_to_read() -> None:
    principal = _analyst("EEX")
    assert principal_allows_source_family(principal, "EEX_Sim")  # outside a request: no-op
    with metering() as meter:
        assert principal_allows_source_family(principal, "EEX_Sim")
        assert principal_allows_source_family(principal, "ENTSOG")  # public: not usage
        assert not principal_allows_source_family(principal, "ICE_OCM")  # refused: not usage
        rows = filter_rows_for_principal(
            principal, [{"source_system": "EEX"}, {"source_system": "Trayport"}]
        )
        with not_metered():  # listing what could be read is not a read
            principal_allows_source_family(_analyst("*"), "Kpler")
        with metering() as inner:  # nested units of work share the request's meter
            principal_allows_source_family(_analyst("*"), "WMR")
    assert rows == [{"source_system": "EEX"}]
    assert inner is meter
    assert meter.families == {"EEX", "WMR"}


def test_the_compatibility_principal_is_metered_without_a_check() -> None:
    with metering() as meter:
        filter_rows_for_principal(
            legacy_public_token_principal(),
            [{"source_system": "Trayport"}, {"source_system": "GIE"}],
        )
    assert meter.families == {"Trayport"}


def test_only_vendor_licensed_families_are_usage() -> None:
    assert licensed_families({"EEX", "DEMO", "ETRM", "trayport", "Kpler"}) == {
        "EEX", "Trayport", "Kpler",
    }
    meter = LicensedUseMeter({"EEX"})
    assert usage_surface("GET /api/market/quotes", meter) == "GET /api/market/quotes"
    meter.export_format = "xlsx"
    assert usage_surface("GET /api/x", meter) == "export:xlsx GET /api/x"


@pytest.mark.parametrize(
    ("families", "redistributable", "registered", "decision"),
    [
        (set(), set(), set(), ExportDecision.ALLOWED),
        ({"EEX"}, set(), set(), ExportDecision.RESTRICTED),
        ({"EEX"}, {"EEX"}, {"EEX"}, ExportDecision.ALLOWED),
        ({"Argus"}, set(), set(), ExportDecision.DENIED),  # terms not registered: fail closed
        ({"Argus"}, set(), {"Argus"}, ExportDecision.RESTRICTED),  # the firm holds a licence
        ({"EEX", "Argus"}, {"EEX"}, set(), ExportDecision.DENIED),  # strictest wins
        ({"EEX", "Trayport"}, {"EEX"}, set(), ExportDecision.RESTRICTED),
    ],
)
def test_file_export_decision(families, redistributable, registered, decision) -> None:
    result = file_export_decision(
        families, redistributable=redistributable, registered=registered
    )
    assert result.decision is decision
    assert result.licensed_families == tuple(sorted(families))
    assert bool(result.restrictions) is (decision is ExportDecision.RESTRICTED)


def _engine(tmp_path):
    engine = create_engine(f"sqlite+pysqlite:///{(tmp_path / 'u.sqlite').as_posix()}")
    Base.metadata.create_all(engine)
    return engine


def test_usage_is_counted_up_per_day_principal_family_and_surface(tmp_path) -> None:
    engine = _engine(tmp_path)
    with Session(engine) as session:
        for when, who, surface in (
            (NOW, "usr-a", "GET /api/market/quotes"),
            (NOW + timedelta(minutes=5), "usr-a", "GET /api/market/quotes"),
            (NOW + timedelta(minutes=6), "usr-b", "GET /api/market/quotes"),
            (NOW + timedelta(minutes=7), "usr-a", "export:csv GET /api/portfolio/x"),
            (NOW + timedelta(days=1), "usr-a", "GET /api/market/quotes"),
        ):
            record_licensed_use(
                session, principal_id=who, families={"EEX", "Trayport"} if who == "usr-a"
                else {"EEX"}, surface=surface, now_utc=when,
            )
            session.commit()
        rows = session.query(LicensedDataUseRecord).all()
        first = session.get(
            LicensedDataUseRecord, (NOW.date(), "usr-a", "EEX", "GET /api/market/quotes")
        )
        assert first.reads == 2
        assert first.last_at_utc.replace(tzinfo=UTC) == NOW + timedelta(minutes=5)
        assert len(rows) == 7  # five requests, one row per day, principal, family and surface
        usage = usage_by_family(session, since=NOW.date())
        assert usage["EEX"] == {
            "principals": 2, "reads": 5, "exports": 1,
            "last_read_utc": usage["EEX"]["last_read_utc"],
        }
        assert usage["Trayport"]["principals"] == 1 and usage["Trayport"]["reads"] == 4
        assert usage_by_family(session, since=date(2026, 11, 25))["EEX"]["reads"] == 1


def test_migration_0079_matches_the_model_up_and_down() -> None:
    spec = importlib.util.spec_from_file_location(
        "tests.migration_0079", VERSIONS / "0079_licensed_data_use.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.down_revision == "0078_lng_cargo_hedges"
    assert DB_SCHEMA_REVISION == module.revision == "0079_licensed_data_use"
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as connection:
        module.op = Operations(MigrationContext.configure(connection=connection))
        module.upgrade()
        inspector = inspect(connection)
        table = LicensedDataUseRecord.__table__
        columns = {c["name"] for c in inspector.get_columns(table.name)}
        assert columns == set(table.columns.keys())
        assert inspector.get_pk_constraint(table.name)["constrained_columns"] == [
            "usage_day", "principal_id", "source_family", "surface",
        ]
        indexes = {i["name"] for i in inspector.get_indexes(table.name)}
        assert {i.name for i in table.indexes} <= indexes
        module.downgrade()
        assert inspect(connection).get_table_names() == []
