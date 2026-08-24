"""Ingest script fail-closed gates, retry, and raw archive tests (audit item 4)."""

import importlib.util
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

SCRIPT_PATH = (
    Path(__file__).resolve().parents[2] / "scripts" / "ops" / "ingest_public_sources.py"
)


def _load_script():
    spec = importlib.util.spec_from_file_location("ingest_public_sources", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_gate_blockers_pass_for_known_public_sources(tmp_path, monkeypatch) -> None:
    script = _load_script()
    session = MagicMock()

    # ECB is public: entitlement passes, no certification required.
    assert script._gate_blockers(session, "ECB") == []


def test_gate_blockers_require_certification_for_restricted_sources(
    tmp_path, monkeypatch
) -> None:
    script = _load_script()
    session = MagicMock()
    query = MagicMock()
    query.filter.return_value.first.return_value = None
    session.query.return_value = query

    blockers = script._gate_blockers(session, "ENTSOG")

    assert blockers and blockers[0].startswith("certification:")
    assert blockers[0] == "certification:certification_stage_not_live_validated"


def test_gate_blockers_deny_unknown_sources(tmp_path, monkeypatch) -> None:
    script = _load_script()
    session = MagicMock()

    blockers = script._gate_blockers(session, "SomeVendor")

    assert blockers and blockers[0].startswith("entitlement:")


def test_archive_raw_payload_writes_row(tmp_path, monkeypatch) -> None:
    script = _load_script()
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from eurogas_nexus.db.base import Base
    from eurogas_nexus.db.models import RawPayloadArchiveRecord

    db_path = tmp_path / "raw-archive.sqlite"
    engine = create_engine(f"sqlite+pysqlite:///{db_path.as_posix()}", future=True)
    Base.metadata.create_all(engine)
    received = datetime(2026, 7, 1, 10, 0, tzinfo=UTC)

    with Session(engine) as session:
        script._archive_raw_payload(
            session,
            source_system="ECB",
            dataset="fx-reference-rates",
            source_reference="ecb-eurofxref-daily",
            payload_text="<xml/>",
            received_at=received,
        )
        session.commit()
        rows = session.query(RawPayloadArchiveRecord).all()

    assert len(rows) == 1
    row = rows[0]
    assert row.source_system == "ECB"
    assert row.payload_text == "<xml/>"
    assert len(row.payload_sha256) == 64
    # SQLite round-trips timestamps as naive; compare on the UTC instant.
    stored = row.received_at_utc
    if stored.tzinfo is None:
        stored = stored.replace(tzinfo=UTC)
    assert stored == received
    assert row.human_review_required is True


def test_archive_raw_payload_skips_oversized(monkeypatch, capsys) -> None:
    script = _load_script()
    session = MagicMock()
    received = datetime(2026, 7, 1, 10, 0, tzinfo=UTC)

    script._archive_raw_payload(
        session,
        source_system="ENTSOG",
        dataset="operationaldatas",
        source_reference="entsog-operationaldatas",
        payload_text="x" * (script.MAX_ARCHIVE_BYTES + 1),
        received_at=received,
    )

    assert session.add.call_count == 0
    assert "archive skipped" in capsys.readouterr().out


def test_get_with_retry_retries_429_and_5xx(monkeypatch) -> None:
    script = _load_script()
    sleeps = []

    def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(script.time, "sleep", fake_sleep)

    class FakeClient:
        def __init__(self):
            self.calls = 0

        def get(self, url, **kwargs):
            self.calls += 1
            return MagicMock(
                status_code=503 if self.calls < 3 else 200,
                headers={},
            )

    client = FakeClient()
    response = script._get_with_retry(client, "https://example.test/x")

    assert client.calls == 3
    assert response.status_code == 200
    assert sleeps == [1.5, 3.0]


def test_get_with_retry_honors_retry_after_header(monkeypatch) -> None:
    script = _load_script()

    class FakeClient:
        def __init__(self):
            self.calls = 0

        def get(self, url, **kwargs):
            self.calls += 1
            return MagicMock(
                status_code=429,
                headers={"retry-after": "5"},
            )

    client = FakeClient()
    script._get_with_retry(client, "https://example.test/x", attempts=2)

    assert client.calls == 2


def test_retry_delay_seconds_parses_retry_after() -> None:
    script = _load_script()

    response = MagicMock(headers={"retry-after": "12"})
    assert script._retry_delay_seconds(response, 0) == 12.0

    response = MagicMock(headers={})
    assert script._retry_delay_seconds(response, 1) == 3.0
