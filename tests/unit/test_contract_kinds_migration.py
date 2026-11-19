"""Migration 0073 on SQLite: contract kinds added to existing rows without loss, and back."""

from __future__ import annotations

import importlib.util
from datetime import UTC, datetime
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect

from eurogas_nexus.release.constants import DB_SCHEMA_REVISION

VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"
NEW = {
    "contract_kind",
    "contract_kind_reviewed",
    "kind_terms",
    "unmodelled_terms",
    "master_contract_id",
}


def test_existing_rows_become_unreviewed_gsa_and_the_downgrade_drops_only_the_columns():
    from eurogas_nexus.db.models import UpstreamResourceContractRecord

    spec = importlib.util.spec_from_file_location(
        "tests.migration_0073", VERSIONS / "0073_contract_kinds.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.down_revision == "0072_strategy_tracks_and_trades"
    assert DB_SCHEMA_REVISION == "0073_contract_kinds"
    model_columns = set(UpstreamResourceContractRecord.__table__.columns.keys())
    old_columns = model_columns - NEW
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    now = datetime(2026, 11, 19, tzinfo=UTC)
    with engine.begin() as connection:
        table = sa.Table(
            "upstream_resource_contracts",
            sa.MetaData(),
            *[
                column.copy()
                for column in UpstreamResourceContractRecord.__table__.columns
                if column.name in old_columns
            ],
        )
        table.create(connection)
        connection.execute(
            table.insert().values(
                contract_id="legacy-1",
                contract_name="Legacy",
                resource_type="PIPELINE_IMPORT",
                delivery_point_name="TTF",
                gas_year="2026/27",
                delivery_quantity_mwh_per_day=100.0,
                contract_price_gbp_mwh=30.0,
                contract_price_currency="EUR",
                settlement_frequency="monthly",
                upstream_payment_lag_days=20,
                screen_sale_cash_lag_days=1,
                delivery_tolerance_pct=2.0,
                nomination_tolerance_pct=1.0,
                annual_financing_rate_pct=6.0,
                allowed_exit_points=["TTF"],
                eligible_sale_modes=[],
                notes='{"counterparty": "X"}',
                created_at_utc=now,
                updated_at_utc=now,
            )
        )
        module.op = Operations(MigrationContext.configure(connection=connection))
        module.upgrade()
        columns = {
            c["name"] for c in inspect(connection).get_columns("upstream_resource_contracts")
        }
        assert columns == model_columns
        row = connection.execute(
            sa.text(
                "select contract_kind, contract_kind_reviewed, kind_terms, notes,"
                " delivery_quantity_mwh_per_day from upstream_resource_contracts"
            )
        ).one()
        assert row[0] == "SUPPLY_GSA" and not row[1] and row[2] is None
        assert row[3] == '{"counterparty": "X"}' and row[4] == 100.0
        module.downgrade()
        columns = {
            c["name"] for c in inspect(connection).get_columns("upstream_resource_contracts")
        }
        assert columns == old_columns
        assert (
            connection.execute(sa.text("select count(*) from upstream_resource_contracts")).scalar()
            == 1
        )
