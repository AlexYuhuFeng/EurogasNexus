"""Ingest script fail-closed gates, retry, and raw archive tests (audit item 4)."""

import importlib.util
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

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


def test_gie_gate_still_requires_certification(tmp_path, monkeypatch) -> None:
    """The new real GIE transport keeps the fail-closed certification gate."""

    script = _load_script()
    session = MagicMock()
    query = MagicMock()
    query.filter.return_value.first.return_value = None
    session.query.return_value = query

    blockers = script._gate_blockers(session, "GIE")

    assert blockers == ["certification:certification_stage_not_live_validated"]


def test_gie_gate_allows_live_only_with_both_required_checks(monkeypatch) -> None:
    script = _load_script()
    session = MagicMock()

    from eurogas_nexus.db.repositories import certification as certification_repo

    monkeypatch.setattr(
        certification_repo,
        "latest_certification",
        lambda session, source: {
            "stage": "live_validated",
            "checks": ["simulated_shape_match", "live_sample_validation"],
        },
    )
    assert script._gate_blockers(session, "GIE") == []

    monkeypatch.setattr(
        certification_repo,
        "latest_certification",
        lambda session, source: {
            "stage": "live_validated",
            "checks": ["simulated_shape_match"],
        },
    )
    blockers = script._gate_blockers(session, "GIE")

    assert blockers and blockers[0].startswith("certification:missing_required_checks")


def _allow_live_certification(monkeypatch) -> None:
    from eurogas_nexus.db.repositories import certification as certification_repo

    monkeypatch.setattr(
        certification_repo,
        "latest_certification",
        lambda session, source: {
            "stage": "live_validated",
            "checks": ["simulated_shape_match", "live_sample_validation"],
        },
    )


def test_gate_blocks_an_explicitly_disabled_source_operation(monkeypatch) -> None:
    """An operator-disabled GIE runtime operation blocks the live entry itself."""

    script = _load_script()
    session = MagicMock()
    session.query.return_value.filter.return_value.one_or_none.return_value = (
        SimpleNamespace(enabled=False)
    )
    _allow_live_certification(monkeypatch)

    assert script._gate_blockers(session, "GIE") == ["source_operation_disabled"]


def test_gate_blocks_an_unreadable_source_runtime_state(monkeypatch) -> None:
    """An unreadable runtime state is not a confirmed permit, so it blocks too."""

    script = _load_script()
    session = MagicMock()
    session.query.side_effect = RuntimeError("runtime state store unavailable")
    _allow_live_certification(monkeypatch)

    assert script._gate_blockers(session, "GIE") == ["source_state_unreadable"]


def test_gate_absent_runtime_state_is_no_override(monkeypatch) -> None:
    """An absent runtime row leaves the existing certification gate in charge."""

    script = _load_script()
    session = MagicMock()
    session.query.return_value.filter.return_value.one_or_none.return_value = None
    _allow_live_certification(monkeypatch)

    assert script._gate_blockers(session, "GIE") == []


def test_gate_blocks_an_explicitly_disabled_public_source_operation(
    monkeypatch,
) -> None:
    """The same runtime gate applies to a public family such as ECB."""

    script = _load_script()
    session = MagicMock()
    session.query.return_value.filter.return_value.one_or_none.return_value = (
        SimpleNamespace(enabled=False)
    )

    assert script._gate_blockers(session, "ECB") == ["source_operation_disabled"]


def _sqlite_session_factory(tmp_path):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from eurogas_nexus.db.base import Base

    db_path = tmp_path / "ingest-main-gates.sqlite"
    engine = create_engine(f"sqlite+pysqlite:///{db_path.as_posix()}", future=True)
    Base.metadata.create_all(engine)
    return engine, sessionmaker(bind=engine, expire_on_commit=False)


class _RecordingHttpClient:
    instances = []

    def __init__(self, **kwargs) -> None:
        self.calls = []
        _RecordingHttpClient.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc_info) -> bool:
        return False

    def get(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        raise RuntimeError("unexpected live HTTP fetch")


@pytest.mark.parametrize(
    ("mode", "expected_blocker"),
    [
        ("disabled", "source_operation_disabled"),
        ("unreadable", "source_state_unreadable"),
    ],
)
def test_main_ecb_gate_blocks_fetch_and_records_failed_run(
    tmp_path, monkeypatch, capsys, mode, expected_blocker
) -> None:
    """The real main() must not fetch ECB when its runtime state blocks live."""

    script = _load_script()
    engine, session_factory = _sqlite_session_factory(tmp_path)

    from sqlalchemy.orm import Session

    from eurogas_nexus.db.models import (
        FxObservationRecord,
        IngestionRunRecord,
        MarketObservationRecord,
    )

    real_query = Session.query

    def gate_query(self, *entities, **kwargs):
        if entities and getattr(entities[0], "__name__", "") == "SourceRuntimeStateRecord":
            if mode == "unreadable":
                raise RuntimeError("runtime state store unavailable")
            query = MagicMock()
            query.filter.return_value.one_or_none.return_value = SimpleNamespace(
                enabled=False
            )
            return query
        return real_query(self, *entities, **kwargs)

    monkeypatch.setattr(Session, "query", gate_query)
    monkeypatch.setattr(
        script, "resolve_database_url", lambda: "sqlite+pysqlite:///gate-test"
    )
    monkeypatch.setattr(script, "get_engine", lambda database_url: engine)
    monkeypatch.setattr(
        script, "create_session_factory", lambda active_engine: session_factory
    )
    _RecordingHttpClient.instances.clear()
    monkeypatch.setattr(script.httpx, "Client", _RecordingHttpClient)
    monkeypatch.setattr(
        sys, "argv", ["ingest_public_sources.py", "--source", "ecb", "--json"]
    )

    result = script.main()

    assert result == 0
    assert _RecordingHttpClient.instances
    assert all(client.calls == [] for client in _RecordingHttpClient.instances)
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["sources"] == {}
    assert payload["failures"] == []
    assert payload["warnings"] == [
        f"ECB live ingestion blocked (fail-closed): {expected_blocker}"
    ]
    with Session(engine) as session:
        runs = session.query(IngestionRunRecord).all()
        assert [run.status for run in runs] == ["failed"]
        assert runs[0].source_name == "ECB"
        assert expected_blocker in runs[0].notes
        assert session.query(MarketObservationRecord).count() == 0
        assert session.query(FxObservationRecord).count() == 0


def test_main_source_all_processes_independent_providers_after_ecb_gate(
    tmp_path, monkeypatch, capsys
) -> None:
    """A blocked ECB must not remove independent, permitted source families."""

    script = _load_script()
    engine, session_factory = _sqlite_session_factory(tmp_path)

    from sqlalchemy.orm import Session

    from eurogas_nexus.db.models import IngestionRunRecord

    real_runtime_blockers = script._source_runtime_blockers

    def runtime_blockers(session, source_system):
        if source_system == "ECB":
            return ["source_operation_disabled"]
        return real_runtime_blockers(session, source_system)

    monkeypatch.setattr(script, "_source_runtime_blockers", runtime_blockers)
    _allow_live_certification(monkeypatch)
    monkeypatch.setattr(script, "_resolve_gie_api_key", lambda session_factory: None)

    entsog_routes = []
    entsog_point_directions = []

    def fake_entsog(
        client,
        session,
        *,
        route,
        args,
        started,
        report,
        point_directions=None,
    ):
        entsog_routes.append(route)
        entsog_point_directions.append(point_directions)
        report["sources"][route] = {"records": 0}

    monkeypatch.setattr(script, "_ingest_entsog_source", fake_entsog)
    monkeypatch.setattr(
        script, "resolve_database_url", lambda: "sqlite+pysqlite:///gate-test"
    )
    monkeypatch.setattr(script, "get_engine", lambda database_url: engine)
    monkeypatch.setattr(
        script, "create_session_factory", lambda active_engine: session_factory
    )
    _RecordingHttpClient.instances.clear()
    monkeypatch.setattr(script.httpx, "Client", _RecordingHttpClient)
    monkeypatch.setattr(
        sys, "argv", ["ingest_public_sources.py", "--source", "all", "--json"]
    )

    result = script.main()

    assert result == 1
    assert set(entsog_routes) == {"entsog", "entsog-capacity", "entsog-reference"}
    assert entsog_point_directions == [(), (), ()]
    assert _RecordingHttpClient.instances
    assert all(client.calls == [] for client in _RecordingHttpClient.instances)
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert "ECB" not in payload["sources"]
    assert any(
        warning
        == "ECB live ingestion blocked (fail-closed): source_operation_disabled"
        for warning in payload["warnings"]
    )
    with Session(engine) as session:
        ecb_runs = (
            session.query(IngestionRunRecord)
            .filter(IngestionRunRecord.source_name == "ECB")
            .all()
        )
        assert [run.status for run in ecb_runs] == ["failed"]
        assert "source_operation_disabled" in ecb_runs[0].notes


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
