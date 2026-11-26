"""Migration 0076 on SQLite: the nomination checklist events and the contract's agent column."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect

from eurogas_nexus.release.constants import DB_SCHEMA_REVISION

VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"


def _load_0085():
    spec = importlib.util.spec_from_file_location(
        "tests.migration_0085", VERSIONS / "0085_sched1_nomination_matching.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_chain_up_down_and_model_match():
    from eurogas_nexus.db.models import GasDayNominationEventRecord
    from eurogas_nexus.db.models.route_cost import UpstreamResourceContractRecord

    spec = importlib.util.spec_from_file_location(
        "tests.migration_0076", VERSIONS / "0076_gas_day_nominations.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.down_revision == "0075_tso_tariff_entry"
    assert DB_SCHEMA_REVISION == "0088_tar2_capacity_bookings"
    contracts = UpstreamResourceContractRecord.__table__
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as connection:
        # The contracts table as it stood before (every column but the new one).
        before = contracts.to_metadata(type(contracts.metadata)())
        before._columns.remove(before.c.nomination_agent)  # noqa: SLF001
        before.create(connection)
        module.op = Operations(MigrationContext.configure(connection=connection))
        module.upgrade()
        # SCHED-1 (0085) adds the matching columns: the model is 0076 plus those.
        matching = _load_0085()
        matching.op = module.op
        matching.upgrade()
        columns = {c["name"] for c in inspect(connection).get_columns(
            GasDayNominationEventRecord.__tablename__)}
        assert columns == set(GasDayNominationEventRecord.__table__.columns.keys())
        matching.downgrade()
        names = {c["name"] for c in inspect(connection).get_columns(contracts.name)}
        assert names == set(contracts.columns.keys())
        module.downgrade()
        assert inspect(connection).get_table_names() == [contracts.name]
        names = {c["name"] for c in inspect(connection).get_columns(contracts.name)}
        assert "nomination_agent" not in names


def test_0085_adds_the_matching_columns_and_drops_only_them():
    matching = _load_0085()
    assert matching.down_revision == "0083_tar1_tariff_book"
    added = {"counterparty", "direction", "point", "shipper_code",
             "counterparty_shipper_code", "counterparty_quantity_mwh"}
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as connection:
        spec = importlib.util.spec_from_file_location(
            "tests.migration_0076b", VERSIONS / "0076_gas_day_nominations.py"
        )
        base = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(base)
        connection.exec_driver_sql(
            "CREATE TABLE upstream_resource_contracts (contract_id VARCHAR PRIMARY KEY)")
        base.op = Operations(MigrationContext.configure(connection=connection))
        base.upgrade()
        before = {c["name"] for c in inspect(connection).get_columns("gas_day_nomination_events")}
        matching.op = base.op
        matching.upgrade()
        after = {c["name"] for c in inspect(connection).get_columns("gas_day_nomination_events")}
        assert after - before == added
        assert all(c["nullable"] for c in inspect(connection).get_columns(
            "gas_day_nomination_events") if c["name"] in added)
        matching.downgrade()
        again = {c["name"] for c in inspect(connection).get_columns("gas_day_nomination_events")}
        assert again == before
