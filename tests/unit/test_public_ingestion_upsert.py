"""Public-source ingestion idempotency helper tests.

Statement compilation is checked against the PostgreSQL dialect without any
database connection; execution paths use a mock session.
"""

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from eurogas_nexus.db.models import (
    MarketObservationRecord,
    NodeFacilityMapping,
    ReferenceNode,
)
from eurogas_nexus.db.repositories.public_ingestion_upsert import (
    replace_reference_snapshot,
    upsert_observation_rows,
)


def _ecb_row() -> dict:
    return {
        "observation_id": "ecb-fx-2026-05-29-USD",
        "market_venue": "ECB",
        "product": "EUR/USD",
        "price": 1.085,
        "unit": "USD per EUR",
        "currency": "USD",
        "period_start_utc": datetime(2026, 5, 29, tzinfo=UTC),
        "period_end_utc": datetime(2026, 5, 30, tzinfo=UTC),
        "observed_at_utc": datetime(2026, 5, 29, 15, 0, tzinfo=UTC),
        "source_system": "ECB",
        "source_reference": "ecb-eurofxref-daily",
        "source_record_id": "2026-05-29-USD",
        "freshness": "live",
        "quality_score": 1.0,
        "research_only": True,
        "metadata_json": {"dataset": "eurofxref-daily"},
    }


def _node_row() -> dict:
    return {
        "id": "entsog-be-zee",
        "name": "Zeebrugge",
        "node_type": "interconnection",
        "country": "BE",
        "lat": 51.34,
        "lon": 3.21,
        "capacity_boe_d": None,
        "source_system": "ENTSOG",
        "source_dataset": "connectionpoints",
        "source_reference": "entsog-connectionpoints",
        "source_record_id": "be-zee",
        "data_quality": "display_approximation",
        "metadata_json": {},
        "created_at_utc": datetime(2026, 5, 29, tzinfo=UTC),
    }


def test_observation_upsert_compiles_to_on_conflict_with_first_seen_timestamp() -> None:
    session = MagicMock()
    count = upsert_observation_rows(session, MarketObservationRecord, [_ecb_row()])

    assert count == 1
    statement = session.execute.call_args.args[0]
    sql = str(statement.compile(dialect=postgresql.dialect()))
    assert "ON CONFLICT (observation_id) DO UPDATE" in sql
    assert "price = excluded.price" in sql
    # first-seen semantics: re-runs must not overwrite observed_at_utc
    assert "observed_at_utc = excluded.observed_at_utc" not in sql


def test_observation_upsert_with_no_rows_does_not_touch_session() -> None:
    session = MagicMock()

    assert upsert_observation_rows(session, MarketObservationRecord, []) == 0
    session.execute.assert_not_called()


def test_reference_snapshot_with_empty_payload_keeps_existing_rows() -> None:
    session = MagicMock()

    count = replace_reference_snapshot(session, ReferenceNode, [], source_system="ENTSOG")

    assert count == 0
    session.execute.assert_not_called()


def test_reference_snapshot_scopes_delete_to_source_and_upserts() -> None:
    session = MagicMock()

    count = replace_reference_snapshot(
        session, ReferenceNode, [_node_row()], source_system="ENTSOG"
    )

    assert count == 1
    delete_statement = session.execute.call_args_list[0].args[0]
    delete_sql = str(delete_statement.compile(dialect=postgresql.dialect()))
    assert "DELETE FROM reference_nodes" in delete_sql
    assert "reference_nodes.source_system" in delete_sql
    assert "%(source_system_1)s" in delete_sql

    upsert_statement = session.execute.call_args_list[1].args[0]
    upsert_sql = str(upsert_statement.compile(dialect=postgresql.dialect()))
    assert "ON CONFLICT (id) DO UPDATE" in upsert_sql
    # first-created semantics: re-runs must not rewrite created_at_utc
    assert "created_at_utc = excluded.created_at_utc" not in upsert_sql


def test_reference_snapshot_requires_source_system_column() -> None:
    session = MagicMock()
    with pytest.raises(ValueError, match="no source_system column"):
        replace_reference_snapshot(
            session,
            NodeFacilityMapping,
            [{"id": "mapping-1"}],
            source_system="ENTSOG",
        )
    session.execute.assert_not_called()
