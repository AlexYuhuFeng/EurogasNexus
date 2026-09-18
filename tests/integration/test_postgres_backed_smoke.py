"""DB-backed smoke tests against the *configured* runtime store.

These tests run against whatever ``RUNTIME_STORE_DATABASE_URL`` points at
(CI: the PostgreSQL 16 service; locally: any scratch store). They are the
"real database" path the audit asked for: migrations + required-table
contract + DB-backed API reads + append-only writes, all against the actual
store instead of per-test SQLite fixtures.
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.skipif(
    not os.environ.get("RUNTIME_STORE_DATABASE_URL"),
    reason="RUNTIME_STORE_DATABASE_URL not configured; run via scripts/ci/run_postgres_ci.sh",
)


def _engine():
    from sqlalchemy import create_engine

    return create_engine(os.environ["RUNTIME_STORE_DATABASE_URL"], future=True)


def _client() -> TestClient:
    from eurogas_nexus.api.app import create_app

    return TestClient(create_app())


def test_required_tables_contract_against_configured_store() -> None:
    from eurogas_nexus.db.registry import list_missing_required_tables

    missing = list(list_missing_required_tables(_engine()))
    assert missing == [], f"missing required tables: {sorted(missing)}"


def test_db_backed_api_read_serves_from_configured_store() -> None:
    response = _client().get("/api/route-cost/tso-tariffs")
    assert response.status_code == 200
    assert response.json()["meta"]["source_references"] == ["runtime-postgresql"]


def test_audit_event_write_and_readback() -> None:
    from sqlalchemy.orm import Session

    from eurogas_nexus.application.audit_service import record_audit_event
    from eurogas_nexus.db.models import AuditEventRecord

    engine = _engine()
    event_id = record_audit_event(
        event_type="governance.smoke",
        action="postgres_smoke_test",
        resource="test:postgres-backend",
        outcome="recorded",
        detail="db-backed smoke",
    )
    assert event_id is not None
    with Session(engine) as session:
        row = session.get(AuditEventRecord, event_id)
        assert row is not None
        assert row.action == "postgres_smoke_test"


def test_raw_payload_archive_write_and_readback() -> None:
    """The archive accepts a row and reads it back, on a database that already has some.

    The archive is append-only, so the test cannot clean up after itself: it writes a fresh
    identifier per run instead. A fixed id passed on a database that had already seen this
    test - which is what a developer sees when they point the suite at a persistent store
    rather than CI's throw-away service - failed with a duplicate-key error and read as a
    broken archive rather than a broken test.
    """

    from datetime import UTC, datetime
    from uuid import uuid4

    from sqlalchemy.orm import Session

    from eurogas_nexus.db.models import RawPayloadArchiveRecord
    from eurogas_nexus.db.repositories.raw_archive import archive_raw_payload

    archive_id = f"raw-smoke-{uuid4().hex[:12]}"
    engine = _engine()
    with Session(engine) as session:
        archive_raw_payload(
            session,
            archive_id=archive_id,
            source_system="SMOKE",
            dataset="test",
            source_reference="postgres-smoke",
            payload_text="{}",
            payload_sha256="a" * 64,
            record_count=0,
            received_at_utc=datetime(2026, 7, 1, tzinfo=UTC),
        )
        session.commit()
        row = session.get(RawPayloadArchiveRecord, archive_id)
        assert row is not None
        assert row.source_system == "SMOKE"
