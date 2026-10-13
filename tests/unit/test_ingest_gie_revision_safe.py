"""Unit tests for the GIE-safe ingest persistence path (REAL-SOURCES-02).

These pin the script-level behaviour around the real PostgreSQL helper without a
database: the whole product batch runs inside one savepoint, each page's **exact**
archive id and hash is stamped on the rows normalized from it, a batch that cannot
be archived fails closed instead of writing rows with false lineage, and a refused
revision is reported as counts/ids only -- never provider payload text.
"""

from __future__ import annotations

import importlib.util
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from eurogas_nexus.db.repositories.public_ingestion_upsert import (
    GieRevisionRequiresHistoryError,
)
from eurogas_nexus.ingestion.gie_transport import GieProduct

SCRIPT_PATH = (
    Path(__file__).resolve().parents[2] / "scripts" / "ops" / "ingest_public_sources.py"
)
RECEIPT = datetime(2026, 10, 10, 6, 0, tzinfo=UTC)
STARTED = datetime(2026, 10, 10, 5, 59, tzinfo=UTC)
SECRET = "unit-test-gie-secret-value"


def _load_script():
    spec = importlib.util.spec_from_file_location("ingest_public_sources", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _raw_payload(code: str = "EU", gas: str = "650.25") -> dict:
    return {
        "data": [
            {
                "code": code,
                "name": code,
                "gasDayStart": "2026-10-10",
                "gasDayEnd": "2026-10-11",
                "gasInStorage": gas,
                "workingGasVolume": "1100.50",
                "updatedAt": "2026-10-10 06:00:00",
            }
        ]
    }


def _page(page: int = 1, *, code: str = "EU", gas: str = "650.25"):
    return SimpleNamespace(
        raw_payload=_raw_payload(code=code, gas=gas),
        received_at_utc=RECEIPT,
        page=page,
        size=30,
        last_page=192,
        total_on_page=1,
        source_reference=f"gie-agsi-api:page={page};size=30",
        records=(),
    )


def _result(pages, *, complete: bool = False):
    return SimpleNamespace(
        product="AGSI",
        pages=tuple(pages),
        records=tuple(record for page in pages for record in page.records),
        provider_last_page=192,
        complete=complete,
        stop_reason="operator_record_budget",
        budget_records=30,
        page_size=30,
        pages_allowed=1,
        record_capacity=30,
        partial_reason="record_budget_whole_page_floor",
        source_reference="gie-agsi-api:pages=1/192;complete=false;stop=operator_record_budget",
    )


class _FakeSession:
    """Minimal session double recording nested-transaction and merge calls."""

    def __init__(self) -> None:
        self.nested_entered = 0
        self.merged: list[Any] = []
        self.added: list[Any] = []

    @contextmanager
    def begin_nested(self):
        self.nested_entered += 1
        yield self

    def merge(self, record):
        self.merged.append(record)
        return record

    def add(self, record):
        self.added.append(record)
        return record

    def flush(self):
        return None


def test_persist_stamps_the_exact_archive_id_and_hash_on_each_row(monkeypatch) -> None:
    script = _load_script()
    session = _FakeSession()
    archived: list[dict[str, Any]] = []

    def fake_archive(session_, **kwargs):
        archived.append(kwargs)
        return {"archive_id": f"raw-page-{kwargs['source_reference']}", "payload_sha256": "b" * 64}

    monkeypatch.setattr(script, "_archive_raw_payload", fake_archive)
    monkeypatch.setattr(
        script,
        "upsert_revision_safe_observation_rows",
        lambda session_, model, rows: {"inserted": len(rows), "unchanged": 0},
    )

    outcome = script._persist_gie_product(
        session,
        product=GieProduct.agsi(),
        source_name="GIE-AGSI",
        gie_result=_result([_page()]),
        model=object,
        started=STARTED,
    )

    assert session.nested_entered == 1
    assert len(archived) == 1
    assert outcome["failure"] is None
    assert outcome["counts"]["inserted"] == 1
    assert outcome["counts"]["unchanged"] == 0
    # The archived row is the one the canonical row points at.
    assert archived[0]["source_reference"] == "gie-agsi-api:page=1;size=30"
    assert archived[0]["payload_json"]["data"][0]["gasInStorage"] == "650.25"


def test_unarchived_payload_fails_closed_without_false_lineage(monkeypatch) -> None:
    script = _load_script()
    session = _FakeSession()
    written: list[Any] = []

    monkeypatch.setattr(script, "_archive_raw_payload", lambda session_, **kwargs: None)
    monkeypatch.setattr(
        script,
        "upsert_revision_safe_observation_rows",
        lambda session_, model, rows: written.append(rows),
    )

    outcome = script._persist_gie_product(
        session,
        product=GieProduct.agsi(),
        source_name="GIE-AGSI",
        gie_result=_result([_page()]),
        model=object,
        started=STARTED,
    )

    assert written == []
    assert outcome["failure"]["code"] == "gie_archive_lineage_required"
    assert outcome["counts"]["inserted"] == 0
    assert outcome["counts"]["unchanged"] == 0


def test_revision_refusal_reports_counts_and_ids_only(monkeypatch) -> None:
    script = _load_script()
    session = _FakeSession()

    monkeypatch.setattr(
        script,
        "_archive_raw_payload",
        lambda session_, **kwargs: {"archive_id": "raw-1", "payload_sha256": "c" * 64},
    )

    def refuse(session_, model, rows):
        raise GieRevisionRequiresHistoryError("refused")

    monkeypatch.setattr(script, "upsert_revision_safe_observation_rows", refuse)

    outcome = script._persist_gie_product(
        session,
        product=GieProduct.agsi(),
        source_name="GIE-AGSI",
        gie_result=_result([_page()]),
        model=object,
        started=STARTED,
    )

    failure = outcome["failure"]
    assert failure["code"] == "gie_revision_requires_history"
    assert failure["observation_ids"] == ["gie-agsi-EU-2026-10-10"]
    # The report carries no provider payload text.
    rendered = repr(outcome)
    assert "650.25" not in rendered
    assert "1100.50" not in rendered
    assert SECRET not in rendered
    # A real failed run is recorded, not a success.
    assert any(getattr(record, "status", None) == "failed" for record in session.merged)


def test_successful_batch_records_the_real_run_and_warning_path(monkeypatch) -> None:
    script = _load_script()
    session = _FakeSession()

    monkeypatch.setattr(
        script,
        "_archive_raw_payload",
        lambda session_, **kwargs: {"archive_id": "raw-1", "payload_sha256": "d" * 64},
    )
    monkeypatch.setattr(
        script,
        "upsert_revision_safe_observation_rows",
        lambda session_, model, rows: {"inserted": 0, "unchanged": len(rows)},
    )

    outcome = script._persist_gie_product(
        session,
        product=GieProduct.agsi(),
        source_name="GIE-AGSI",
        gie_result=_result([_page()], complete=False),
        model=object,
        started=STARTED,
    )

    assert outcome["failure"] is None
    assert outcome["counts"]["unchanged"] == 1
    # An honest bounded partial is recorded as a warning-qualified success.
    assert any(
        getattr(record, "status", None) == "SUCCEEDED_WITH_WARNINGS"
        for record in session.merged
    )


def test_archive_helper_returns_identity_and_skips_oversized(
    monkeypatch, capsys
) -> None:
    script = _load_script()
    stored: list[dict[str, Any]] = []

    def fake_archive_raw_payload(session_, **kwargs):
        stored.append(kwargs)
        return SimpleNamespace(archive_id=kwargs["archive_id"])

    monkeypatch.setattr(
        "eurogas_nexus.db.repositories.raw_archive.archive_raw_payload",
        fake_archive_raw_payload,
    )

    reference = script._archive_raw_payload(
        object(),
        source_system="GIE",
        dataset="AGSI",
        source_reference="gie-agsi-api:page=1;size=30",
        payload_json=_raw_payload(),
        record_count=1,
        received_at=RECEIPT,
    )

    assert reference is not None
    assert reference["archive_id"] == stored[0]["archive_id"]
    assert len(reference["payload_sha256"]) == 64

    monkeypatch.setattr(script, "MAX_ARCHIVE_BYTES", 10)
    assert (
        script._archive_raw_payload(
            object(),
            source_system="GIE",
            dataset="AGSI",
            source_reference="gie-agsi-api:page=2;size=30",
            payload_json=_raw_payload(),
            record_count=1,
            received_at=RECEIPT,
        )
        is None
    )
    assert "archive skipped" in capsys.readouterr().out


def test_connection_test_helper_reports_failure_codes_without_secrets() -> None:
    """The transport check maps a refused key to the stable code only."""

    import httpx

    from eurogas_nexus.ingestion.gie_transport import test_gie_connection

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"error": "access denied", "dataset": "storage ERROR"},
            headers={"date": "Sat, 10 Oct 2026 06:00:00 GMT"},
        )

    client = httpx.Client(
        transport=httpx.MockTransport(handler),
        headers={"User-Agent": "EurogasNexus-test"},
        follow_redirects=False,
    )
    try:
        checks = test_gie_connection(client, api_key=SECRET)
    finally:
        client.close()

    assert all(check.ok is False for check in checks)
    assert all(check.error_code == "gie_access_denied" for check in checks)
    assert SECRET not in repr(checks)
