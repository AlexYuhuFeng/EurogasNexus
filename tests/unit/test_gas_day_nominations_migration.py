"""Migration 0076 on SQLite: the nomination checklist events and the contract's agent column."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect

from eurogas_nexus.release.constants import DB_SCHEMA_REVISION

VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"


def test_chain_up_down_and_model_match():
    from eurogas_nexus.db.models import GasDayNominationEventRecord
    from eurogas_nexus.db.models.route_cost import UpstreamResourceContractRecord

    spec = importlib.util.spec_from_file_location(
        "tests.migration_0076", VERSIONS / "0076_gas_day_nominations.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.down_revision == "0075_tso_tariff_entry"
    assert DB_SCHEMA_REVISION == "0078_job_progress_steps"
    contracts = UpstreamResourceContractRecord.__table__
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as connection:
        # The contracts table as it stood before (every column but the new one).
        before = contracts.to_metadata(type(contracts.metadata)())
        before._columns.remove(before.c.nomination_agent)  # noqa: SLF001
        before.create(connection)
        module.op = Operations(MigrationContext.configure(connection=connection))
        module.upgrade()
        columns = {c["name"] for c in inspect(connection).get_columns(
            GasDayNominationEventRecord.__tablename__)}
        assert columns == set(GasDayNominationEventRecord.__table__.columns.keys())
        names = {c["name"] for c in inspect(connection).get_columns(contracts.name)}
        assert names == set(contracts.columns.keys())
        module.downgrade()
        assert inspect(connection).get_table_names() == [contracts.name]
        names = {c["name"] for c in inspect(connection).get_columns(contracts.name)}
        assert "nomination_agent" not in names
