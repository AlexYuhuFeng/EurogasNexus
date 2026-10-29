"""ENTSOG integration failure and dispatch checks, with no network/DB writes."""

from contextlib import nullcontext
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from eurogas_nexus.db.models import FlowObservationRecord
from eurogas_nexus.ingestion import entsog_ingestion as persistence
from eurogas_nexus.ingestion.entsog_transport import EntsogWindowError, validate_entsog_window
from scripts.ops import ingest_public_sources as script
from scripts.ops.run_public_ingestion_worker import build_ingestion_command, run_worker
from tests.fixtures.entsog_protocol import (
    RECEIPT,
    connectionpoint,
    observation,
    operatorpoint,
    query_result,
)


def _session():
    session = MagicMock()
    session.begin_nested.side_effect = lambda: nullcontext()
    return session


def _archive(monkeypatch):
    archived = []

    def archive(session, **kwargs):
        archived.append(kwargs)
        return SimpleNamespace(**kwargs)

    monkeypatch.setattr(persistence, "archive_raw_payload", archive)
    return archived


def test_capacity_queries_archive_each_page_with_actual_receipt_and_exact_lineage(monkeypatch):
    archived = _archive(monkeypatch)
    queries = [
        query_result(
            "operationaldatas",
            [observation(str(i), indicator)],
            indicator=indicator,
            receipt=RECEIPT + timedelta(seconds=i),
        )
        for i, indicator in enumerate(script.ENTSOG_CAPACITY_INDICATORS)
    ]
    written = []
    monkeypatch.setattr(
        persistence,
        "upsert_entsog_observation_rows",
        lambda session, model, rows: (
            written.extend(rows) or {"inserted": len(rows), "unchanged": 0}
        ),
    )
    outcome = persistence.persist_entsog_observations(
        _session(), results=queries, model=script.CapacityObservationRecord, run_id="run-cap-test"
    )
    assert outcome["archived_pages"] == 4 and outcome["records"] == 4
    for row, record, result in zip(written, archived, queries, strict=True):
        page = result.pages[0]
        assert record["received_at_utc"] == page.received_at_utc
        assert record["record_count"] == 1 and record["payload_text"].encode() == page.raw_body
        assert record["payload_sha256"] == page.payload_sha256
        assert row["observed_at_utc"] == page.received_at_utc
        assert row["metadata_json"]["archive_id"] == record["archive_id"]
        assert row["metadata_json"]["payload_sha256"] == record["payload_sha256"]
        assert row["metadata_json"]["availability_basis"] == "response_receipt"


def test_archive_failure_refuses_canonical_writes(monkeypatch):
    monkeypatch.setattr(persistence, "archive_raw_payload", lambda session, **kwargs: None)
    monkeypatch.setattr(
        persistence,
        "upsert_entsog_observation_rows",
        lambda *args: pytest.fail("Canonical write without archive"),
    )
    with pytest.raises(persistence.EntsogArchiveLineageError):
        persistence.persist_entsog_observations(
            _session(),
            results=[query_result("operationaldatas", [observation()])],
            model=FlowObservationRecord,
            run_id="run-test",
        )


def test_capacity_zero_normalization_refuses_entire_batch_after_archival(monkeypatch):
    archived = _archive(monkeypatch)
    queries = [
        query_result("operationaldatas", [observation(indicator="Firm Technical")]),
        query_result("operationaldatas", [observation("empty", "Firm Booked", None)]),
    ]
    monkeypatch.setattr(
        persistence,
        "upsert_entsog_observation_rows",
        lambda *args: pytest.fail("Partial capacity canonical write"),
    )
    with pytest.raises(persistence.EntsogEmptyNormalizationError):
        persistence.persist_entsog_observations(
            _session(), results=queries, model=script.CapacityObservationRecord, run_id="run-test"
        )
    assert len(archived) == 2


def test_partial_reference_never_calls_replace_delete_even_with_usable_rows(monkeypatch):
    archived = _archive(monkeypatch)
    queries = [
        query_result("connectionpoints", [connectionpoint()]),
        query_result("operatorpointdirections", [operatorpoint()], complete=False),
    ]
    with pytest.raises(persistence.EntsogPartialReferenceError):
        persistence.persist_entsog_reference(
            _session(),
            results=queries,
            run_id="run-ref",
            replace_network=lambda *args, **kwargs: pytest.fail("Partial topology replacement"),
        )
    assert len(archived) == 2


def _args(**overrides):
    return SimpleNamespace(
        entsog_from="2026-10-10",
        entsog_to="2026-10-11",
        entsog_page_size=2,
        entsog_max_pages=2,
        limit=3,
        **overrides,
    )


def test_partial_observation_run_status_and_counters_are_explicit(monkeypatch):
    _archive(monkeypatch)
    query = query_result("operationaldatas", [observation()], complete=False)
    calls = []
    monkeypatch.setattr(
        script,
        "fetch_entsog_dataset",
        lambda client, dataset, **kwargs: calls.append(kwargs) or query,
    )
    monkeypatch.setattr(
        persistence, "upsert_entsog_observation_rows", lambda *args: {"inserted": 1, "unchanged": 0}
    )
    report = {"sources": {}, "warnings": [], "failures": []}
    session = _session()
    script._ingest_entsog_source(
        None,
        session,
        route="entsog",
        args=_args(),
        started=RECEIPT - timedelta(hours=1),
        report=report,
    )
    assert calls[0]["filters"] == {
        "from": "2026-10-10",
        "to": "2026-10-11",
        "indicator": "Physical Flow",
    }
    source = report["sources"]["ENTSOG"]
    assert source["complete"] is False and source["status"] == "SUCCEEDED_WITH_WARNINGS"
    assert source["received_records"] == source["records"] == 1
    assert source["queries"][0]["stop_reason"] == "operator_record_budget"
    assert session.merge.call_args.args[0].status == "SUCCEEDED_WITH_WARNINGS"
    assert report["warnings"] and not report["failures"]


def test_rolling_observation_persists_open_day_qualifier_even_when_traversal_exhausts(monkeypatch):
    _archive(monkeypatch)
    calls = []
    monkeypatch.setattr(
        script,
        "fetch_entsog_dataset",
        lambda client, dataset, **kwargs: (
            calls.append(kwargs) or query_result("operationaldatas", [observation()], complete=True)
        ),
    )
    monkeypatch.setattr(
        persistence, "upsert_entsog_observation_rows", lambda *args: {"inserted": 1, "unchanged": 0}
    )
    args = _args()
    args.entsog_from = args.entsog_to = None
    args.entsog_lookback_gas_days = 2
    args.entsog_window_anchor = "2026-01-02T04:59:59+00:00"
    session = _session()
    report = {"sources": {}, "warnings": [], "failures": []}
    script._ingest_entsog_source(
        None, session, route="entsog", args=args, started=RECEIPT, report=report
    )
    source = report["sources"]["ENTSOG"]
    assert source["complete"] is True and source["status"] == "SUCCEEDED_WITH_WARNINGS"
    assert source["window"]["open_gas_day_at_anchor"] == "2026-01-01"
    assert calls[0]["filters"]["from"] == "2025-12-30"
    row = session.merge.call_args.args[0]
    assert row.status == "SUCCEEDED_WITH_WARNINGS" and "open_at_anchor=2026-01-01" in row.notes


def test_missing_window_records_failure_without_network_or_blocking_other_source_session(
    monkeypatch,
):
    monkeypatch.setattr(
        script,
        "fetch_entsog_dataset",
        lambda *args, **kwargs: pytest.fail("Unbounded provider call"),
    )
    report = {"sources": {"ECB": {"records": 2}}, "warnings": [], "failures": []}
    args = _args()
    args.entsog_from = None
    session = _session()
    script._ingest_entsog_source(
        None, session, route="entsog", args=args, started=RECEIPT, report=report
    )
    assert report["failures"] == [{"source": "ENTSOG", "code": "entsog_window_required"}]
    assert report["sources"]["ECB"]["records"] == 2
    assert session.merge.call_args.args[0].status == "failed"
    session.rollback.assert_not_called()


@pytest.mark.parametrize("has_prefix", [False, True])
def test_later_capacity_fetch_failure_archives_completed_queries_without_canonical(
    monkeypatch, has_prefix
):
    from eurogas_nexus.ingestion.entsog_transport import EntsogTransportError

    archived = _archive(monkeypatch)
    calls = []

    def fetch(client, dataset, **kwargs):
        calls.append(kwargs)
        if len(calls) == 2:
            error = EntsogTransportError("Provider failed.")
            if has_prefix:
                error.validated_prefix_result = query_result(
                    "operationaldatas", [observation("prefix", "Firm Booked")], complete=False
                )
            raise error
        return query_result("operationaldatas", [observation(indicator="Firm Technical")])

    monkeypatch.setattr(script, "fetch_entsog_dataset", fetch)
    monkeypatch.setattr(
        persistence,
        "upsert_entsog_observation_rows",
        lambda *args: pytest.fail("Canonical write after incomplete query batch"),
    )
    report = {"sources": {}, "warnings": [], "failures": []}
    script._ingest_entsog_source(
        None, _session(), route="entsog-capacity", args=_args(), started=RECEIPT, report=report
    )
    assert len(archived) == 1 + has_prefix
    assert report["sources"]["ENTSOG-capacity"]["archived_pages"] == 1 + has_prefix
    assert report["sources"]["ENTSOG-capacity"]["records"] == 0
    assert report["sources"]["ENTSOG-capacity"]["status"] == "failed"


def test_recurring_worker_passes_window_and_missing_window_fails_preflight():
    command = build_ingestion_command(
        ["ecb", "entsog"], 20, entsog_from="2026-10-10", entsog_to="2026-10-11"
    )
    assert command[command.index("--entsog-from") + 1] == "2026-10-10"
    assert command[command.index("--entsog-to") + 1] == "2026-10-11"
    with pytest.raises(EntsogWindowError):
        run_worker(
            sources=["entsog"],
            limit=20,
            interval_seconds=60,
            max_iterations=1,
            runner=lambda *args, **kwargs: pytest.fail("Misconfigured supervisor started"),
        )


def test_recurring_worker_missing_window_keeps_independent_sources_running(capsys):
    commands = []
    code = run_worker(
        sources=["entsog", "ecb", "gie-agsi"],
        limit=20,
        interval_seconds=60,
        max_iterations=1,
        runner=lambda command, **kwargs: commands.append(command) or SimpleNamespace(returncode=0),
    )
    assert code == 2 and len(commands) == 1
    assert "entsog" not in commands[0] and "ecb" in commands[0] and "gie-agsi" in commands[0]
    assert "degraded (entsog_window_required)" in capsys.readouterr().out


@pytest.mark.parametrize(
    "start,end",
    [
        (None, None),
        ("2026-10-10", None),
        ("bad", "2026-10-11"),
        ("20261010", "2026-10-11"),
        ("2026-10-11", "2026-10-10"),
        ("2026-10-10", "2026-10-10"),
        ("2026-09-01", "2026-10-11"),
    ],
)
def test_invalid_windows_refuse_collection(start, end):
    with pytest.raises(EntsogWindowError):
        validate_entsog_window(start, end)


@pytest.mark.parametrize(
    ("route", "source_name", "query_count"),
    [
        ("entsog", "ENTSOG", 1),
        ("entsog-capacity", "ENTSOG-capacity", 4),
    ],
)
def test_explicit_point_scope_is_forwarded_to_flow_and_capacity_queries(
    monkeypatch, route, source_name, query_count
):
    _archive(monkeypatch)
    calls = []

    def fetch(client, dataset, **kwargs):
        filters = kwargs["filters"]
        calls.append((dataset, filters))
        return query_result(
            "operationaldatas",
            [observation(str(len(calls)), filters["indicator"])],
            indicator=filters["indicator"],
            complete=True,
        )

    monkeypatch.setattr(script, "fetch_entsog_dataset", fetch)
    monkeypatch.setattr(
        persistence,
        "upsert_entsog_observation_rows",
        lambda *args: {"inserted": 0, "unchanged": 1},
    )
    scope = (
        "de-tso-0009itp-00126entry",
        "de-tso-0009itp-00126exit",
    )
    report = {"sources": {}, "warnings": [], "failures": []}
    script._ingest_entsog_source(
        None,
        _session(),
        route=route,
        args=_args(),
        started=RECEIPT,
        report=report,
        point_directions=scope,
    )
    assert len(calls) == query_count
    assert all(dataset == "operationaldatas" for dataset, _ in calls)
    assert all(filters["pointDirection"] == ",".join(scope) for _, filters in calls)
    detail = report["sources"][source_name]
    assert detail["point_direction"] == ",".join(scope)
    assert detail["point_directions"] == list(scope)


def test_unspecified_point_scope_preserves_existing_operational_filters(monkeypatch):
    _archive(monkeypatch)
    calls = []

    def fetch(client, dataset, **kwargs):
        calls.append(kwargs["filters"])
        return query_result("operationaldatas", [observation()], complete=True)

    monkeypatch.setattr(script, "fetch_entsog_dataset", fetch)
    monkeypatch.setattr(
        persistence,
        "upsert_entsog_observation_rows",
        lambda *args: {"inserted": 1, "unchanged": 0},
    )
    report = {"sources": {}, "warnings": [], "failures": []}
    script._ingest_entsog_source(
        None, _session(), route="entsog", args=_args(), started=RECEIPT, report=report
    )
    assert calls == [
        {
            "from": "2026-10-10",
            "to": "2026-10-11",
            "indicator": "Physical Flow",
        }
    ]
    detail = report["sources"]["ENTSOG"]
    assert "point_direction" not in detail and "point_directions" not in detail


def test_reference_queries_never_receive_observation_point_scope(monkeypatch):
    _archive(monkeypatch)
    calls = []

    def fetch(client, dataset, **kwargs):
        calls.append((dataset, kwargs["filters"]))
        rows = [connectionpoint()] if dataset == "connectionpoints" else [operatorpoint()]
        return query_result(dataset, rows, complete=True)

    monkeypatch.setattr(script, "fetch_entsog_dataset", fetch)
    monkeypatch.setattr(
        script,
        "persist_entsog_reference",
        lambda *args, **kwargs: {"records": 2, "replaced": 2, "skipped_tables": []},
    )
    report = {"sources": {}, "warnings": [], "failures": []}
    script._ingest_entsog_source(
        None,
        _session(),
        route="entsog-reference",
        args=_args(),
        started=RECEIPT,
        report=report,
        point_directions=("de-tso-0009itp-00126entry",),
    )
    assert calls == [
        ("connectionpoints", {"extended": "1"}),
        ("operatorpointdirections", {"hasData": "1"}),
    ]
    detail = report["sources"]["ENTSOG-reference"]
    assert "point_direction" not in detail and "point_directions" not in detail


def test_point_direction_validation_lowercases_deduplicates_and_sorts():
    result = script._validate_entsog_point_directions(
        [
            "DE-TSO-0009ITP-00126ENTRY, de-tso-0009itp-00126exit",
            "de-tso-0009itp-00126entry",
            "AT-TSO-0001ITP-00002EXIT",
        ]
    )
    assert result == (
        "at-tso-0001itp-00002exit",
        "de-tso-0009itp-00126entry",
        "de-tso-0009itp-00126exit",
    )


@pytest.mark.parametrize(
    "values",
    [
        [""],
        ["   "],
        ["de-tso-0009itp-00126"],
        ["http://example.invalid/de-tso-0009itp-00126entry"],
        ["de-tso-0009itp-00126entry\x01"],
        ["dé-tso-0009itp-00126entry"],
        [",".join(f"de-tso-{index:04d}itp-00126entry" for index in range(65))],
        ["a" * 8188 + "entry"],
    ],
)
def test_point_direction_validation_refuses_invalid_scope(values):
    with pytest.raises(ValueError):
        script._validate_entsog_point_directions(values)


def test_invalid_scope_is_refused_before_database_resolution(monkeypatch):
    monkeypatch.setattr(
        "sys.argv",
        ["ingest_public_sources.py", "--entsog-point-direction", "not-a-direction"],
    )
    monkeypatch.setattr(
        script,
        "resolve_database_url",
        lambda: pytest.fail("Database resolution happened before scope validation"),
    )
    with pytest.raises(SystemExit) as exit_info:
        script.main()
    assert exit_info.value.code == 2
