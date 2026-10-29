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
    StorageObservationRecord,
)
from eurogas_nexus.db.repositories.public_ingestion_upsert import (
    GieRevisionRaceError,
    replace_reference_snapshot,
    upsert_observation_rows,
    upsert_revision_safe_observation_rows,
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


# ---------------------------------------------------------------------------
# Revision-safe GIE race fallback (REAL-SOURCES-02 review)
#
# The conflict/re-read path retries once when the conflicting transaction rolled
# back. The retry must be *confirmed*: a second ``ON CONFLICT DO NOTHING`` that
# also reports no affected row is never booked as an insert.
# ---------------------------------------------------------------------------


def _gie_row() -> dict:
    return {
        "observation_id": "gie-agsi-EU-2026-10-10",
        "source_dataset": "AGSI",
        "facility_id": "EU",
        "facility_name": "EU",
        "country": "EU",
        "inventory_twh": 650.25,
        "working_capacity_twh": 1100.5,
        "fill_pct": 59.1,
        "injection_twh_d": 0.0025,
        "withdrawal_twh_d": 0.0012,
        "period_start_utc": datetime(2026, 10, 10, tzinfo=UTC),
        "period_end_utc": datetime(2026, 10, 11, tzinfo=UTC),
        "observed_at_utc": datetime(2026, 10, 10, 6, tzinfo=UTC),
        "source_system": "GIE",
        "source_reference": "gie-agsi-api",
        "source_record_id": "EU-2026-10-10",
        "freshness": "live",
        "research_only": True,
        "metadata_json": {},
    }


class _ScriptedResult:
    def __init__(self, *, rowcount: int = 0, mapping: dict | None = None) -> None:
        self.rowcount = rowcount
        self._mapping = mapping

    def mappings(self):
        return self

    def first(self):
        return self._mapping


class _ScriptedSession:
    """Session double returning a fixed sequence of execute() results."""

    def __init__(self, *results: _ScriptedResult) -> None:
        self._results = list(results)
        self.calls = 0

    def execute(self, statement, *args, **kwargs):  # noqa: ANN002, ANN003 - stub
        self.calls += 1
        return self._results.pop(0)


def _no_row() -> _ScriptedResult:
    return _ScriptedResult(mapping=None)


def _conflict() -> _ScriptedResult:
    return _ScriptedResult(rowcount=0)


def _inserted() -> _ScriptedResult:
    return _ScriptedResult(rowcount=1)


def test_revision_safe_race_retry_never_books_an_unconfirmed_insert() -> None:
    """Two unconfirmed DO NOTHINGs with no re-readable row fail closed."""

    session = _ScriptedSession(
        _no_row(),  # first read: key absent
        _conflict(),  # insert conflicts (winner uncommitted)
        _no_row(),  # re-read: winner rolled back
        _conflict(),  # retry also conflicts (another writer holds the key)
        _no_row(),  # re-read: still not readable
    )

    with pytest.raises(GieRevisionRaceError) as refusal:
        upsert_revision_safe_observation_rows(
            session, StorageObservationRecord, [_gie_row()]
        )

    assert refusal.value.code == "gie_revision_race_unresolved"


def test_revision_safe_race_retry_counts_a_confirmed_insert() -> None:
    """When the retry really writes the row, the confirmed insert is reported."""

    session = _ScriptedSession(_no_row(), _conflict(), _no_row(), _inserted())

    outcome = upsert_revision_safe_observation_rows(
        session, StorageObservationRecord, [_gie_row()]
    )

    assert outcome == {"inserted": 1, "unchanged": 0}


def test_revision_safe_race_reread_verifies_the_committed_row() -> None:
    """A conflict whose committed row is unchanged is verified, never re-inserted."""

    session = _ScriptedSession(_no_row(), _conflict(), _ScriptedResult(mapping=_gie_row()))

    outcome = upsert_revision_safe_observation_rows(
        session, StorageObservationRecord, [_gie_row()]
    )

    assert outcome == {"inserted": 0, "unchanged": 1}


@pytest.mark.parametrize(
    ("old", "new", "expected"),
    [
        ({}, {}, []),
        ({}, {"flowStatus": None}, ["metadata_json.flowStatus"]),
        ({"flowStatus": None}, {}, ["metadata_json.flowStatus"]),
        ({"flowStatus": None}, {"flowStatus": "confirmed"}, ["metadata_json.flowStatus"]),
        ({"flowStatus": False}, {"flowStatus": 0}, ["metadata_json.flowStatus"]),
        (
            {"flowStatus": "confirmed", "archive_id": "first"},
            {"flowStatus": "confirmed", "archive_id": "next"},
            [],
        ),
        (["malformed"], {}, ["metadata_json"]),
    ],
)
def test_allowlisted_metadata_preserves_presence_type_and_ignores_receipt_churn(
    old, new, expected
):
    from eurogas_nexus.db.repositories.public_ingestion_upsert import (
        _metadata_semantic_mismatches,
    )

    existing = {"metadata_json": old}
    incoming = {"metadata_json": new}
    assert _metadata_semantic_mismatches(existing, incoming, ("flowStatus",)) == expected
    assert _metadata_semantic_mismatches(existing, incoming, ()) == []
