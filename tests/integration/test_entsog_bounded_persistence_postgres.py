"""Real PostgreSQL tests in unique disposable schemas, never business tables.

All provider payloads are development fixtures. No live source is fetched,
enabled or certified. Tests exercise actual archive and canonical transactions.
"""

import hashlib
import os
from contextlib import contextmanager
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from eurogas_nexus.db.models import (
    AuditEventRecord,
    CapacityObservationRecord,
    FlowObservationRecord,
    IngestionRunRecord,
    RawPayloadArchiveRecord,
    ReferenceFacility,
    ReferenceMarketHub,
    ReferenceNode,
    ReferenceTsoAccessPoint,
)
from eurogas_nexus.db.repositories.entsog_observation_persistence import (
    EntsogRevisionRequiresHistoryError,
)
from eurogas_nexus.ingestion import entsog_ingestion as persistence
from scripts.ops import ingest_public_sources as script
from tests.fixtures.entsog_protocol import (
    RECEIPT,
    connectionpoint,
    observation,
    operatorpoint,
    query_result,
)

pytestmark = pytest.mark.skipif(
    not os.environ.get("RUNTIME_STORE_DATABASE_URL", "").startswith("postgresql"),
    reason="Explicit PostgreSQL test URL required; all tables use a disposable schema.",
)


@contextmanager
def _session():
    url = make_url(os.environ["RUNTIME_STORE_DATABASE_URL"])
    connect_args = {"timeout": 5} if url.get_driver_name() == "pg8000" else {"connect_timeout": 5}
    engine = create_engine(url, future=True, connect_args=connect_args)
    schema = f"entsogtest_{uuid4().hex}"
    schema_created = False
    try:
        with engine.begin() as connection:
            connection.execute(text("SET LOCAL statement_timeout = '10s'"))
            connection.execute(text("SET LOCAL lock_timeout = '5s'"))
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            schema_created = True
            connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
            for model in (
                FlowObservationRecord,
                CapacityObservationRecord,
                RawPayloadArchiveRecord,
                ReferenceNode,
                ReferenceFacility,
                ReferenceMarketHub,
                ReferenceTsoAccessPoint,
                IngestionRunRecord,
                AuditEventRecord,
            ):
                model.__table__.create(bind=connection)
            with Session(bind=connection) as session:
                yield session
    finally:
        try:
            if schema_created:
                with engine.begin() as connection:
                    connection.execute(text("SET LOCAL statement_timeout = '10s'"))
                    connection.execute(text("SET LOCAL lock_timeout = '5s'"))
                    connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        finally:
            engine.dispose()


def _rows(session, model):
    return [dict(row) for row in session.execute(select(model.__table__)).mappings()]


@pytest.mark.parametrize(
    "model,indicator",
    [(FlowObservationRecord, "Physical Flow"), (CapacityObservationRecord, "Firm Technical")],
)
def test_real_insert_and_unchanged_poll_preserve_whole_row_and_separate_raw_archives(
    model, indicator
):
    first = query_result(
        "operationaldatas", [observation(indicator=indicator)], indicator=indicator
    )
    second = query_result(
        "operationaldatas",
        [observation(indicator=indicator)],
        indicator=indicator,
        receipt=RECEIPT + timedelta(hours=1),
    )
    with _session() as session:
        outcome = persistence.persist_entsog_observations(
            session, results=[first], model=model, run_id="run-first"
        )
        snapshot = _rows(session, model)
        next_outcome = persistence.persist_entsog_observations(
            session, results=[second], model=model, run_id="run-second"
        )
        assert _rows(session, model) == snapshot
        archives = _rows(session, RawPayloadArchiveRecord)
        assert len(archives) == 2
        stored = snapshot[0]
        assert stored["observed_at_utc"] == RECEIPT
        metadata = stored["metadata_json"]
        exact = next(a for a in archives if a["archive_id"] == metadata["archive_id"])
        assert exact["received_at_utc"] == RECEIPT
        assert exact["record_count"] == 1
        assert exact["payload_text"].encode() == first.pages[0].raw_body
        assert (
            hashlib.sha256(exact["payload_text"].encode()).hexdigest() == metadata["payload_sha256"]
        )
    assert outcome["inserted"] == 1 and outcome["unchanged"] == 0
    assert next_outcome["inserted"] == 0 and next_outcome["unchanged"] == 1


@pytest.mark.parametrize(
    "model,indicator",
    [(FlowObservationRecord, "Physical Flow"), (CapacityObservationRecord, "Firm Booked")],
)
def test_mixed_new_and_revised_batch_rolls_back_all_canonical_writes_retains_raw(model, indicator):
    first = query_result("operationaldatas", [observation(indicator=indicator)])
    revised = query_result(
        "operationaldatas",
        [observation("new", indicator), observation("one", indicator, 21000000)],
        receipt=RECEIPT + timedelta(hours=1),
    )
    with _session() as session:
        persistence.persist_entsog_observations(
            session, results=[first], model=model, run_id="first"
        )
        snapshot = _rows(session, model)
        with pytest.raises(EntsogRevisionRequiresHistoryError) as caught:
            persistence.persist_entsog_observations(
                session, results=[revised], model=model, run_id="refused"
            )
        assert caught.value.code == "entsog_revision_requires_history"
        assert _rows(session, model) == snapshot
        assert len(_rows(session, RawPayloadArchiveRecord)) == 2


def test_four_capacity_queries_are_archived_and_one_empty_query_prevents_all_canonical_writes():
    queries = [
        query_result(
            "operationaldatas",
            [observation(str(i), indicator, None if i == 3 else 10500000)],
            indicator=indicator,
        )
        for i, indicator in enumerate(script.ENTSOG_CAPACITY_INDICATORS)
    ]
    with _session() as session:
        with pytest.raises(persistence.EntsogEmptyNormalizationError):
            persistence.persist_entsog_observations(
                session, results=queries, model=CapacityObservationRecord, run_id="empty-cap"
            )
        assert _rows(session, CapacityObservationRecord) == []
        assert len(_rows(session, RawPayloadArchiveRecord)) == 4


def test_archive_failure_rolls_back_raw_group_and_never_writes_canonical(monkeypatch):
    real_archive = persistence.archive_raw_payload
    calls = []

    def archive(session, **kwargs):
        calls.append(True)
        if len(calls) == 2:
            return None
        return real_archive(session, **kwargs)

    monkeypatch.setattr(persistence, "archive_raw_payload", archive)
    queries = [
        query_result("operationaldatas", [observation("one")]),
        query_result("operationaldatas", [observation("two")]),
    ]
    with _session() as session:
        with pytest.raises(persistence.EntsogArchiveLineageError):
            persistence.persist_entsog_observations(
                session, results=queries, model=FlowObservationRecord, run_id="archive-fail"
            )
        assert _rows(session, RawPayloadArchiveRecord) == []
        assert _rows(session, FlowObservationRecord) == []
        # The caller transaction remains usable, including an independent source.
        session.execute(text("SELECT 1"))


def _old_node(identifier, source="ENTSOG"):
    return ReferenceNode(
        id=identifier,
        name="Existing node",
        node_type="interconnection",
        country="BE",
        lat=51,
        lon=4,
        source_system=source,
        metadata_json={"preserve": True},
    )


def test_partial_reference_keeps_actual_topology_and_archives_both_queries():
    queries = [
        query_result("connectionpoints", [connectionpoint()]),
        query_result("operatorpointdirections", [operatorpoint()], complete=False),
    ]
    with _session() as session:
        session.add_all([_old_node("old-entsog"), _old_node("operator-node", "OPERATOR")])
        session.flush()
        snapshot = _rows(session, ReferenceNode)
        with pytest.raises(persistence.EntsogPartialReferenceError):
            persistence.persist_entsog_reference(
                session,
                results=queries,
                run_id="partial-ref",
                replace_network=script._replace_reference_network,
            )
        assert _rows(session, ReferenceNode) == snapshot
        assert len(_rows(session, RawPayloadArchiveRecord)) == 2


def test_complete_reference_replacement_keeps_operator_rows_and_exact_page_links():
    queries = [
        query_result("connectionpoints", [connectionpoint()]),
        query_result("operatorpointdirections", [operatorpoint()]),
    ]
    with _session() as session:
        session.add_all([_old_node("old-entsog"), _old_node("operator-node", "OPERATOR")])
        session.flush()
        outcome = persistence.persist_entsog_reference(
            session,
            results=queries,
            run_id="complete-ref",
            replace_network=script._replace_reference_network,
        )
        nodes = _rows(session, ReferenceNode)
        assert "old-entsog" not in {r["id"] for r in nodes}
        assert "operator-node" in {r["id"] for r in nodes}
        assert outcome["records"] > 0
        for model in (ReferenceNode, ReferenceTsoAccessPoint):
            for row in _rows(session, model):
                if row["source_system"] != "ENTSOG":
                    continue
                metadata = row["metadata_json"]
                archive = session.get(RawPayloadArchiveRecord, metadata["archive_id"])
                assert archive is not None
                assert archive.payload_sha256 == metadata["payload_sha256"]


def test_reference_exception_after_delete_rolls_back_topology_but_retains_archives():
    queries = [
        query_result("connectionpoints", [connectionpoint()]),
        query_result("operatorpointdirections", [operatorpoint()]),
    ]

    def failing_replace(session, **kwargs):
        session.execute(text("DELETE FROM reference_nodes WHERE source_system='ENTSOG'"))
        raise ValueError("Injected failure after delete")

    with _session() as session:
        session.add(_old_node("old-entsog"))
        session.flush()
        snapshot = _rows(session, ReferenceNode)
        with pytest.raises(ValueError):
            persistence.persist_entsog_reference(
                session, results=queries, run_id="ref-fail", replace_network=failing_replace
            )
        assert _rows(session, ReferenceNode) == snapshot
        assert len(_rows(session, RawPayloadArchiveRecord)) == 2


def test_rolling_run_persists_warning_policy_and_actual_archive_lineage(monkeypatch):
    result = query_result("operationaldatas", [observation()], complete=True)
    monkeypatch.setattr(script, "fetch_entsog_dataset", lambda *args, **kwargs: result)
    args = SimpleNamespace(
        entsog_from=None,
        entsog_to=None,
        entsog_lookback_gas_days=2,
        entsog_window_anchor=RECEIPT.isoformat(),
        limit=10,
        entsog_page_size=2,
        entsog_max_pages=2,
    )
    with _session() as session:
        report = {"sources": {}, "warnings": [], "failures": []}
        script._ingest_entsog_source(
            None, session, route="entsog", args=args, started=RECEIPT, report=report
        )
        session.flush()
        assert not report["failures"]
        run = _rows(session, IngestionRunRecord)[0]
        assert run["status"] == "SUCCEEDED_WITH_WARNINGS"
        assert "calendar=EU-CAM-UTC-2025" in run["notes"]
        assert "open_at_anchor=2026-10-12" in run["notes"]
        row = _rows(session, FlowObservationRecord)[0]
        assert row["metadata_json"]["ingestion_run_id"] == run["run_id"]
        archive = session.get(RawPayloadArchiveRecord, row["metadata_json"]["archive_id"])
        assert archive is not None and archive.payload_sha256 == result.pages[0].payload_sha256
        assert row["observed_at_utc"] == RECEIPT
