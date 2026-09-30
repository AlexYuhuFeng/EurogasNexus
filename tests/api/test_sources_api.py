"""Source registry and ingestion API contract tests (DB-free)."""

import pytest
from fastapi.testclient import TestClient

from eurogas_nexus.api.app import create_app


@pytest.fixture(name="client")
def _client() -> TestClient:
    return TestClient(create_app())


def test_list_sources_returns_200(client: TestClient) -> None:
    response = client.get("/api/sources")
    assert response.status_code == 200

    body = response.json()
    assert isinstance(body["data"], list)
    assert len(body["data"]) >= 13


def test_list_sources_includes_all_families(client: TestClient) -> None:
    response = client.get("/api/sources")
    systems = {s["source_system"] for s in response.json()["data"]}
    assert {
        "Argus",
        "DEEPSEEK",
        "ECB",
        "EEX",
        "ENTSOG",
        "GIE",
        "ICE_OCM",
        "ICIS",
        "Kpler",
        "BBL",
        "IUK",
        "GTS",
        "NaTran",
        "GermanTSO",
        "FluxysBelgium",
        "CNMCEnagas",
        "NationalGasNTS",
        "Platts",
        "Trayport",
        "Weather",
    }.issubset(systems)


def test_sources_are_grouped_for_source_center(client: TestClient) -> None:
    response = client.get("/api/sources")
    data = response.json()["data"]
    by_category = {}
    for source in data:
        by_category.setdefault(source["category"], set()).add(source["source_system"])

    assert {"Platts", "ICIS", "EEX", "ICE_OCM", "Trayport", "Kpler", "Argus"}.issubset(
        by_category["price"]
    )
    assert by_category["fx"] == {"ECB"}
    assert {"ENTSOG", "GIE"}.issubset(by_category["infrastructure"])
    assert {
        "NationalGasNTS",
        "BBL",
        "IUK",
        "GTS",
        "NaTran",
        "GermanTSO",
        "FluxysBelgium",
        "CNMCEnagas",
    }.issubset(by_category["tariff"])
    assert "Weather" in by_category["weather"]
    assert "DEEPSEEK" in by_category["ai"]


def test_sources_include_simulated_market_price_feeds_when_runtime_rows_exist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from eurogas_nexus.api.routes.public import sources as sources_routes

    monkeypatch.setattr(sources_routes, "_db_is_configured", lambda: True)
    monkeypatch.setattr(
        sources_routes,
        "_runtime_source_counts",
        lambda: {
            "EEX_Sim": 18,
            "ICE_OCM_Sim": 2,
            "Trayport_Sim": 12,
            "ICIS_Sim": 6,
        },
    )
    monkeypatch.setattr(
        sources_routes,
        "_latest_ingestion_status_by_source",
        lambda: {
            "src-eex-sim": {
                "latest": {
                    "status": "succeeded",
                    "started_at_utc": "2026-07-01T10:15:00+00:00",
                    "finished_at_utc": "2026-07-01T10:15:00+00:00",
                    "source_reference": "records=18; source=EEX_Sim",
                },
                "last_success_at_utc": "2026-07-01T10:15:00+00:00",
            }
        },
    )
    monkeypatch.setattr(sources_routes, "_credential_status_by_provider", lambda: {})
    monkeypatch.setattr(sources_routes, "_certification_by_source_system", lambda: {})

    response = TestClient(create_app()).get("/api/sources")

    assert response.status_code == 200
    sources = {item["source_system"]: item for item in response.json()["data"]}
    assert sources["EEX_Sim"]["category"] == "price"
    assert sources["EEX_Sim"]["credential_requirements"] == []
    assert sources["EEX_Sim"]["live_record_count"] == 18
    assert sources["EEX_Sim"]["connectivity_status"] == "active"
    assert "live_records_available" in sources["EEX_Sim"]["diagnostics"]
    assert sources["ICE_OCM_Sim"]["live_record_count"] == 2
    assert sources["Trayport_Sim"]["live_record_count"] == 12
    assert sources["ICIS_Sim"]["live_record_count"] == 6


def test_source_center_marks_stale_sources_by_freshness_expectation(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Audit item 3: records alone do not make a source live."""

    from datetime import UTC, datetime, timedelta

    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from eurogas_nexus.db.base import Base
    from eurogas_nexus.db.models import MarketObservationRecord

    db_path = tmp_path / "sources-freshness.sqlite"
    database_url = f"sqlite+pysqlite:///{db_path.as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    now = datetime.now(UTC)

    with Session(engine) as session:
        session.add(
            MarketObservationRecord(
                observation_id="eex-stale",
                market_venue="EEX",
                product="TTF day-ahead",
                price=31.0,
                unit="EUR/MWh",
                currency="EUR",
                period_start_utc=now - timedelta(days=10),
                period_end_utc=now - timedelta(days=9),
                observed_at_utc=now - timedelta(days=10),
                source_system="EEX_Sim",
                source_reference="sim:EEX:TTF:day-ahead:old",
                source_record_id="old",
                freshness="live",
                quality_score=0.9,
                research_only=False,
                metadata_json={"hub": "TTF", "simulated": True},
            )
        )
        session.commit()

    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)

    client = TestClient(create_app())
    response = client.get("/api/sources")

    assert response.status_code == 200
    sources = {item["source_system"]: item for item in response.json()["data"]}
    stale = sources["EEX_Sim"]
    # EEX_Sim declares a 1-minute freshness expectation; the newest row is 10 days old.
    assert stale["live_record_count"] > 0
    assert stale["freshness_status"] == "stale"
    assert stale["connectivity_status"] == "stale"
    assert "data_stale" in stale["diagnostics"]


def test_source_center_marks_fresh_sources_active(tmp_path, monkeypatch) -> None:
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from eurogas_nexus.db.base import Base
    from eurogas_nexus.db.models import MarketObservationRecord

    db_path = tmp_path / "sources-fresh.sqlite"
    database_url = f"sqlite+pysqlite:///{db_path.as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    now = datetime.now(UTC)

    with Session(engine) as session:
        session.add(
            MarketObservationRecord(
                observation_id="eex-fresh",
                market_venue="EEX",
                product="TTF day-ahead",
                price=31.0,
                unit="EUR/MWh",
                currency="EUR",
                period_start_utc=now - timedelta(hours=1),
                period_end_utc=now,
                observed_at_utc=now - timedelta(seconds=30),
                source_system="EEX_Sim",
                source_reference="sim:EEX:TTF:day-ahead:now",
                source_record_id="now",
                freshness="live",
                quality_score=0.9,
                research_only=False,
                metadata_json={"hub": "TTF", "simulated": True},
            )
        )
        session.commit()

    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)

    client = TestClient(create_app())
    response = client.get("/api/sources")

    assert response.status_code == 200
    sources = {item["source_system"]: item for item in response.json()["data"]}
    fresh = sources["EEX_Sim"]
    assert fresh["freshness_status"] == "live"
    assert fresh["connectivity_status"] == "active"
    assert "data_stale" not in fresh["diagnostics"]


def test_licensed_price_sources_show_active_preview_substitute_when_subscription_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from eurogas_nexus.api.routes.public import sources as sources_routes

    monkeypatch.setattr(sources_routes, "_db_is_configured", lambda: True)
    monkeypatch.setattr(
        sources_routes,
        "_runtime_source_counts",
        lambda: {
            "EEX_Sim": 18,
            "ICE_OCM_Sim": 2,
            "Trayport_Sim": 12,
            "ICIS_Sim": 6,
        },
    )
    monkeypatch.setattr(sources_routes, "_latest_ingestion_status_by_source", lambda: {})
    monkeypatch.setattr(sources_routes, "_credential_status_by_provider", lambda: {})
    monkeypatch.setattr(sources_routes, "_certification_by_source_system", lambda: {})

    response = TestClient(create_app()).get("/api/sources")

    assert response.status_code == 200
    sources = {item["source_system"]: item for item in response.json()["data"]}
    assert sources["EEX"]["connectivity_status"] == "needs_credential"
    assert sources["EEX"]["preview_substitute_source_system"] == "EEX_Sim"
    assert sources["EEX"]["preview_substitute_status"] == "active"
    assert sources["EEX"]["preview_substitute_record_count"] == 18
    assert sources["EEX"]["operational_status"] == "active_simulated"
    assert sources["EEX"]["workflow_ready"] is True
    assert sources["EEX"]["effective_source_system"] == "EEX_Sim"
    assert sources["EEX"]["effective_record_count"] == 18
    assert "preview_substitute_active" in sources["EEX"]["diagnostics"]
    assert sources["ICE_OCM"]["preview_substitute_source_system"] == "ICE_OCM_Sim"
    assert sources["ICE_OCM"]["preview_substitute_status"] == "active"
    assert sources["Trayport"]["preview_substitute_source_system"] == "Trayport_Sim"
    assert sources["Trayport"]["operational_status"] == "active_simulated"
    assert sources["Trayport"]["workflow_ready"] is True
    assert sources["ICIS"]["preview_substitute_source_system"] == "ICIS_Sim"
    assert sources["ICIS"]["preview_substitute_status"] == "active"
    assert sources["Platts"]["preview_substitute_source_system"] is None


def test_sources_response_meta_includes_category_posture_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from eurogas_nexus.api.routes.public import sources as sources_routes

    monkeypatch.setattr(sources_routes, "_db_is_configured", lambda: True)
    monkeypatch.setattr(
        sources_routes,
        "_runtime_source_counts",
        lambda: {
            "EEX_Sim": 18,
            "ICE_OCM_Sim": 2,
            "ICIS_Sim": 6,
            "ENTSOG": 140,
            "GIE": 12,
            "NationalGasNTS": 1315,
        },
    )
    monkeypatch.setattr(sources_routes, "_latest_ingestion_status_by_source", lambda: {})
    monkeypatch.setattr(sources_routes, "_credential_status_by_provider", lambda: {})
    monkeypatch.setattr(sources_routes, "_certification_by_source_system", lambda: {})

    response = TestClient(create_app()).get("/api/sources")

    assert response.status_code == 200
    summary = response.json()["meta"]["source_posture_summary"]
    assert summary["totals"]["registered_sources"] >= 20
    assert summary["totals"]["active_sources"] >= 5
    assert summary["totals"]["workflow_ready_sources"] >= 8
    assert summary["totals"]["preview_substitutes_active"] == 3
    assert summary["totals"]["runtime_records"] == 1493

    categories = {item["category"]: item for item in summary["categories"]}
    assert categories["price"]["preview_substitutes_active"] == 3
    assert categories["price"]["workflow_ready_sources"] >= 6
    assert categories["price"]["missing_credentials"] >= 5
    assert categories["price"]["next_action"] == "configure_live_credentials"
    assert categories["infrastructure"]["active_sources"] == 1
    assert categories["infrastructure"]["missing_credentials"] == 1
    assert categories["infrastructure"]["runtime_records"] == 152
    assert categories["tariff"]["runtime_records"] == 1315


def test_source_records_include_diagnostics_and_credential_state(client: TestClient) -> None:
    response = client.get("/api/sources")
    source = next(item for item in response.json()["data"] if item["source_system"] == "ICIS")

    assert source["category"] == "price"
    assert source["category_label"] == "Prices"
    assert source["credential_state"] == "missing"
    assert source["connectivity_status"] == "needs_credential"
    assert source["operational_status"] == "needs_credential"
    assert source["workflow_ready"] is False
    assert source["effective_source_system"] == "ICIS"
    assert source["status"] == source["connectivity_status"]
    assert source["last_success_at_utc"] is None
    assert source["last_failure_at_utc"] is None
    assert source["diagnostics"] == ["credential_missing"]


def test_get_source_by_id_returns_200(client: TestClient) -> None:
    response = client.get("/api/sources/src-entsog")
    assert response.status_code == 200
    assert response.json()["data"]["source_system"] == "ENTSOG"
    assert response.json()["data"]["credential_requirements"] == []


def test_gie_source_declares_operator_key_requirement(client: TestClient) -> None:
    response = client.get("/api/sources/src-gie")
    assert response.status_code == 200
    assert response.json()["data"]["source_system"] == "GIE"
    assert response.json()["data"]["credential_requirements"] == ["api_key"]
    assert response.json()["data"]["category"] == "infrastructure"


def test_national_gas_nts_source_uses_runtime_tariff_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    from eurogas_nexus.api.routes.public import sources as sources_routes

    monkeypatch.setattr(sources_routes, "_db_is_configured", lambda: True)
    monkeypatch.setattr(
        sources_routes,
        "_runtime_source_counts",
        lambda: {"NationalGasNTS": 1315},
    )
    monkeypatch.setattr(sources_routes, "_latest_ingestion_status_by_source", lambda: {})
    monkeypatch.setattr(sources_routes, "_credential_status_by_provider", lambda: {})
    monkeypatch.setattr(sources_routes, "_certification_by_source_system", lambda: {})

    response = TestClient(create_app()).get("/api/sources")
    assert response.status_code == 200

    source = next(
        item for item in response.json()["data"] if item["source_system"] == "NationalGasNTS"
    )
    assert source["live_record_count"] == 1315
    assert source["connectivity_status"] == "active"
    assert source["diagnostics"] == ["live_records_available"]


def test_interconnector_sources_use_runtime_tariff_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    from eurogas_nexus.api.routes.public import sources as sources_routes

    monkeypatch.setattr(sources_routes, "_db_is_configured", lambda: True)
    monkeypatch.setattr(
        sources_routes,
        "_runtime_source_counts",
        lambda: {"BBL": 2, "IUK": 4},
    )
    monkeypatch.setattr(sources_routes, "_latest_ingestion_status_by_source", lambda: {})
    monkeypatch.setattr(sources_routes, "_credential_status_by_provider", lambda: {})
    monkeypatch.setattr(sources_routes, "_certification_by_source_system", lambda: {})

    response = TestClient(create_app()).get("/api/sources")
    assert response.status_code == 200

    sources = {item["source_system"]: item for item in response.json()["data"]}
    assert sources["BBL"]["connectivity_status"] == "active"
    assert sources["BBL"]["live_record_count"] == 2
    assert sources["IUK"]["connectivity_status"] == "active"
    assert sources["IUK"]["live_record_count"] == 4


def test_get_source_unknown_returns_404(client: TestClient) -> None:
    response = client.get("/api/sources/nonexistent")
    assert response.status_code == 404


def test_list_ingestion_runs_returns_200(client: TestClient) -> None:
    response = client.get("/api/ingestion-runs")
    assert response.status_code == 200

    body = response.json()
    assert isinstance(body["data"], list)
    assert body["data"] == []
    assert body["meta"]["source_references"] == ["source-registry"]


def test_list_ingestion_runs_filter_by_source(client: TestClient) -> None:
    response = client.get("/api/ingestion-runs?source_id=src-ecb")
    assert response.status_code == 200

    runs = response.json()["data"]
    assert all(r["source_id"] == "src-ecb" for r in runs)


def test_ingestion_run_notes_parse_records_key_value() -> None:
    from eurogas_nexus.api.routes.public.sources import _records_from_notes

    assert _records_from_notes("records=18; source=EEX_Sim") == 18


def test_response_metadata(client: TestClient) -> None:
    response = client.get("/api/sources")
    meta = response.json()["meta"]
    assert meta["research_only"] is True
    assert meta["human_review_required"] is True


# ---------------------------------------------------------------------------
# Bounded ingestion-run reads (Source Center performance fix).
#
# ``/api/sources`` annotated each source with its newest run, newest succeeded
# run and newest failed run by loading every persisted run through the ORM and
# keeping the first match per source in Python. The ingestion simulator writes a
# run per source per 10-second tick, so that read grew without bound with
# uptime. These tests hold the replacement (DB-side per-source ranking, paged
# ingestion-run listing) to the previous results on a real SQLite store.
# ---------------------------------------------------------------------------


def _runtime_store(tmp_path, name: str, monkeypatch: pytest.MonkeyPatch):
    """Create a scratch runtime store and point the app at it."""

    from sqlalchemy import create_engine

    from eurogas_nexus.db.base import Base

    database_url = f"sqlite+pysqlite:///{(tmp_path / name).as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    return engine, database_url


def _ingestion_run(
    run_id: str,
    source_id: str,
    started_at,
    status: str,
    *,
    finished_at=None,
):
    from eurogas_nexus.db.models import IngestionRunRecord

    return IngestionRunRecord(
        run_id=run_id,
        source_name=source_id.removeprefix("src-").upper(),
        source_id=source_id,
        dataset="probe",
        trigger_type="SCHEDULED",
        status=status,
        started_at_utc=started_at,
        finished_at_utc=finished_at,
        attempt_number=1,
        rows_received=1,
        rows_accepted=1,
        rows_rejected=0,
        rows_inserted=1,
        rows_updated=0,
        duplicate_count=0,
        quality_warning_count=0,
        quality_error_count=0,
        fallback_used=False,
        notes="records=1; source=probe",
    )


def _reference_ingestion_status() -> dict:
    """The pre-change algorithm: order every run, keep firsts in Python."""

    from eurogas_nexus.db.models import IngestionRunRecord
    from eurogas_nexus.db.repositories.dataops import ingestion_run_payload
    from eurogas_nexus.db.session import get_session_factory

    status: dict = {}
    with get_session_factory()() as session:
        runs = [
            ingestion_run_payload(row)
            for row in session.query(IngestionRunRecord).order_by(
                IngestionRunRecord.started_at_utc.desc()
            )
        ]
    for run in runs:
        bucket = status.setdefault(run["source_id"], {})
        bucket.setdefault("latest", run)
        if run["status"] == "succeeded" and "last_success_at_utc" not in bucket:
            bucket["last_success_at_utc"] = run["finished_at_utc"] or run["started_at_utc"]
        if run["status"] == "failed" and "last_failure_at_utc" not in bucket:
            bucket["last_failure_at_utc"] = run["finished_at_utc"] or run["started_at_utc"]
    return status


def test_latest_ingestion_status_matches_full_history_reference(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Latest/success/failure ordering stays identical to the old scan."""

    from datetime import UTC, datetime, timedelta

    from sqlalchemy.orm import Session

    from eurogas_nexus.api.routes.public import sources as sources_routes

    engine, _ = _runtime_store(tmp_path, "runs-reference.sqlite", monkeypatch)
    base = datetime(2026, 7, 1, 10, 0, tzinfo=UTC)
    with Session(engine) as session:
        session.add_all(
            [
                # Newest run succeeded; an older failure must stay visible.
                _ingestion_run(
                    "run-ecb-1",
                    "src-ecb",
                    base,
                    "succeeded",
                    finished_at=base + timedelta(seconds=5),
                ),
                _ingestion_run(
                    "run-ecb-2",
                    "src-ecb",
                    base + timedelta(minutes=1),
                    "failed",
                    finished_at=base + timedelta(minutes=1, seconds=3),
                ),
                _ingestion_run(
                    "run-ecb-3",
                    "src-ecb",
                    base + timedelta(minutes=2),
                    "succeeded",
                    finished_at=base + timedelta(minutes=2, seconds=4),
                ),
                # Newest run failed; the last success must stay visible.
                _ingestion_run(
                    "run-entsog-1",
                    "src-entsog",
                    base,
                    "failed",
                    finished_at=base + timedelta(seconds=1),
                ),
                _ingestion_run(
                    "run-entsog-2",
                    "src-entsog",
                    base + timedelta(minutes=3),
                    "succeeded",
                    finished_at=base + timedelta(minutes=3, seconds=2),
                ),
                _ingestion_run(
                    "run-entsog-3",
                    "src-entsog",
                    base + timedelta(minutes=4),
                    "failed",
                    finished_at=base + timedelta(minutes=4, seconds=1),
                ),
                # Unfinished success falls back to started_at, as before.
                _ingestion_run("run-gie-1", "src-gie", base + timedelta(minutes=5), "succeeded"),
            ]
        )
        session.commit()

    status = sources_routes._latest_ingestion_status_by_source()

    assert status == _reference_ingestion_status()
    assert status["src-ecb"]["latest"]["run_id"] == "run-ecb-3"
    assert status["src-ecb"]["last_success_at_utc"] == "2026-07-01T10:02:04+00:00"
    assert status["src-ecb"]["last_failure_at_utc"] == "2026-07-01T10:01:03+00:00"
    assert status["src-entsog"]["latest"]["status"] == "failed"
    assert status["src-entsog"]["last_success_at_utc"] == "2026-07-01T10:03:02+00:00"
    assert status["src-entsog"]["last_failure_at_utc"] == "2026-07-01T10:04:01+00:00"
    assert status["src-gie"]["last_success_at_utc"] == "2026-07-01T10:05:00+00:00"


def test_latest_ingestion_status_empty_store_returns_empty_mapping(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from eurogas_nexus.api.routes.public import sources as sources_routes

    _runtime_store(tmp_path, "runs-empty.sqlite", monkeypatch)

    assert sources_routes._latest_ingestion_status_by_source() == {}


def test_latest_ingestion_status_is_bounded_by_sources_not_history(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """History size must not set the number of rows or queries per read."""

    from datetime import UTC, datetime, timedelta

    from sqlalchemy import event
    from sqlalchemy.engine import Engine
    from sqlalchemy.orm import Session

    from eurogas_nexus.api.routes.public import sources as sources_routes
    from eurogas_nexus.db.models import IngestionRunRecord

    engine, _ = _runtime_store(tmp_path, "runs-bounded.sqlite", monkeypatch)
    base = datetime(2026, 7, 1, 0, 0, tzinfo=UTC)
    source_ids = [f"src-{index}" for index in range(5)]
    runs_per_source = 400
    with Session(engine) as session:
        for source_index, source_id in enumerate(source_ids):
            for run_index in range(runs_per_source):
                started = base + timedelta(
                    minutes=source_index * runs_per_source + run_index
                )
                status = "failed" if run_index % 7 == 0 else "succeeded"
                session.add(
                    _ingestion_run(
                        f"run-{source_index}-{run_index}",
                        source_id,
                        started,
                        status,
                        finished_at=started + timedelta(seconds=5),
                    )
                )
        session.commit()

    hydrations: list[str] = []
    run_statements: list[str] = []

    def _on_load(target, context) -> None:  # noqa: ANN001
        hydrations.append(target.run_id)

    def _on_statement(conn, cursor, statement, parameters, context, executemany) -> None:  # noqa: ANN001
        if "ingestion_runs" in statement:
            run_statements.append(" ".join(statement.split()))

    event.listen(IngestionRunRecord, "load", _on_load)
    event.listen(Engine, "before_cursor_execute", _on_statement)
    try:
        status = sources_routes._latest_ingestion_status_by_source()
    finally:
        event.remove(IngestionRunRecord, "load", _on_load)
        event.remove(Engine, "before_cursor_execute", _on_statement)

    assert set(status) == set(source_ids)
    # One query per role (newest, newest succeeded, newest failed), regardless
    # of how many runs are persisted, and each ranks per source in the database.
    assert len(run_statements) == 3
    for statement in run_statements:
        assert "row_number() over" in statement.lower()
        assert "source_rank" in statement
    # At most one hydrated row per source per role: 15 for 2,000 persisted runs.
    assert len(hydrations) <= len(source_ids) * 3
    assert len(set(hydrations)) == len(hydrations)


def test_runtime_source_counts_grouped_read_matches_per_system_queries(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Grouped counts must equal the previous one-query-per-system counts."""

    from datetime import UTC, datetime, timedelta

    from sqlalchemy.orm import Session

    from eurogas_nexus.api.routes.public import sources as sources_routes
    from eurogas_nexus.db.models import (
        FxObservationRecord,
        MarketObservationRecord,
        ScreenOrderObservationRecord,
    )

    engine, _ = _runtime_store(tmp_path, "counts-grouped.sqlite", monkeypatch)
    now = datetime(2026, 7, 1, 12, 0, tzinfo=UTC)
    with Session(engine) as session:
        for index in range(3):
            session.add(
                MarketObservationRecord(
                    observation_id=f"eex-sim-{index}",
                    market_venue="EEX",
                    product="TTF day-ahead",
                    price=31.0,
                    unit="EUR/MWh",
                    currency="EUR",
                    period_start_utc=now - timedelta(hours=1),
                    period_end_utc=now,
                    observed_at_utc=now - timedelta(seconds=index),
                    source_system="EEX_Sim",
                    source_reference=f"sim:{index}",
                    source_record_id=str(index),
                    freshness="live",
                    quality_score=0.9,
                    research_only=False,
                    metadata_json={"hub": "TTF"},
                )
            )
        for index in range(2):
            session.add(
                MarketObservationRecord(
                    observation_id=f"ice-ocm-sim-{index}",
                    market_venue="ICE_OCM",
                    product="NBP day-ahead",
                    price=33.0,
                    unit="EUR/MWh",
                    currency="EUR",
                    period_start_utc=now - timedelta(hours=1),
                    period_end_utc=now,
                    observed_at_utc=now - timedelta(seconds=index),
                    source_system="ICE_OCM_Sim",
                    source_reference=f"sim:ice:{index}",
                    source_record_id=str(index),
                    freshness="live",
                    quality_score=0.9,
                    research_only=False,
                    metadata_json={"hub": "NBP"},
                )
            )
        for index in range(4):
            session.add(
                MarketObservationRecord(
                    observation_id=f"weather-{index}",
                    market_venue="Weather",
                    product="temperature",
                    price=15.0,
                    unit="C",
                    currency="EUR",
                    period_start_utc=now - timedelta(hours=1),
                    period_end_utc=now,
                    observed_at_utc=now - timedelta(seconds=index),
                    source_system="Weather",
                    source_reference=f"weather:{index}",
                    source_record_id=str(index),
                    freshness="live",
                    quality_score=0.9,
                    research_only=False,
                    metadata_json=None,
                )
            )
        for index in range(2):
            session.add(
                FxObservationRecord(
                    observation_id=f"ecb-fx-{index}",
                    pair="EURUSD",
                    base_currency="EUR",
                    quote_currency="USD",
                    rate=1.1,
                    rate_type="reference",
                    value_date=f"2026-07-0{index + 1}",
                    observed_at_utc=now - timedelta(hours=index),
                    source_system="ECB",
                    source_reference=f"ecb:{index}",
                    source_record_id=str(index),
                    freshness="live",
                    research_only=False,
                    metadata_json=None,
                )
            )
        screen_orders = [
            # source_system match, provider_id match and both-at-once rows. The
            # previous per-system OR queries counted the both-at-once row once.
            ("screen-1", "Trayport_Sim", "Trayport_Sim"),
            ("screen-2", "Trayport_Sim", "ICE_OCM"),
            ("screen-3", "Trayport", "Trayport"),
        ]
        for order_id, source_system, provider_id in screen_orders:
            session.add(
                ScreenOrderObservationRecord(
                    order_observation_id=order_id,
                    provider_id=provider_id,
                    venue="screen",
                    account_label="probe",
                    external_order_id=order_id,
                    side="buy",
                    order_type="limit",
                    hub="TTF",
                    product="day-ahead",
                    contract_code="TTF-DA",
                    delivery_start_utc=now,
                    delivery_end_utc=now + timedelta(hours=1),
                    price=31.0,
                    currency="EUR",
                    unit="EUR/MWh",
                    quantity_mwh=1.0,
                    filled_quantity_mwh=0.0,
                    remaining_quantity_mwh=1.0,
                    status="open",
                    observed_at_utc=now,
                    source_system=source_system,
                    source_reference=f"screen:{order_id}",
                    research_only=False,
                    human_review_required=True,
                )
            )
        session.commit()

        grouped = sources_routes._runtime_source_counts()

        # Reference shape: the previous one-query-per-system counts.
        reference = {
            system: session.query(MarketObservationRecord)
            .filter(MarketObservationRecord.source_system == system)
            .count()
            for system in (
                "Argus",
                "EEX",
                "EEX_Sim",
                "ICE_OCM",
                "ICE_OCM_Sim",
                "ICIS",
                "ICIS_Sim",
                "Kpler",
                "Platts",
                "Trayport",
                "Trayport_Sim",
            )
        }
        for system in ("ICE_OCM", "ICE_OCM_Sim", "Trayport", "Trayport_Sim"):
            reference[system] = reference.get(system, 0) + (
                session.query(ScreenOrderObservationRecord)
                .filter(
                    (ScreenOrderObservationRecord.source_system == system)
                    | (ScreenOrderObservationRecord.provider_id == system)
                )
                .count()
            )

    for system, expected in reference.items():
        assert grouped[system] == expected, system
    assert grouped["EEX_Sim"] == 3
    assert grouped["ICE_OCM"] == 1  # provider_id match on the Trayport_Sim row
    assert grouped["Trayport_Sim"] == 2  # source match twice, both-at-once once
    assert grouped["Trayport"] == 1
    assert grouped["Weather"] == 4
    assert grouped["ECB"] == 2  # two FX rows, no market rows
    assert grouped["Argus"] == 0
    assert grouped["DEEPSEEK"] == 0


def test_list_ingestion_runs_pages_in_the_database(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The listing keeps the same page and filter while bounding the read."""

    from datetime import UTC, datetime, timedelta

    from sqlalchemy import event
    from sqlalchemy.orm import Session

    from eurogas_nexus.db.models import IngestionRunRecord
    from eurogas_nexus.db.repositories.dataops import ingestion_run_payload

    engine, _ = _runtime_store(tmp_path, "runs-listing.sqlite", monkeypatch)
    base = datetime(2026, 7, 1, 6, 0, tzinfo=UTC)
    with Session(engine) as session:
        for index in range(30):
            session.add(
                _ingestion_run(
                    f"run-ecb-{index:03d}",
                    "src-ecb",
                    base + timedelta(minutes=index),
                    "succeeded",
                    finished_at=base + timedelta(minutes=index, seconds=1),
                )
            )
        for index in range(10):
            session.add(
                _ingestion_run(
                    f"run-entsog-{index:03d}",
                    "src-entsog",
                    base + timedelta(minutes=index),
                    "failed",
                    finished_at=base + timedelta(minutes=index, seconds=2),
                )
            )
        session.commit()
        ordered = [
            ingestion_run_payload(row)
            for row in session.query(IngestionRunRecord).order_by(
                IngestionRunRecord.started_at_utc.desc()
            )
        ]
    expected_page = ordered[:3]
    expected_entsog = [run for run in ordered if run["source_id"] == "src-entsog"][:4]

    hydrations: list[str] = []

    def _on_load(target, context) -> None:  # noqa: ANN001
        hydrations.append(target.run_id)

    event.listen(IngestionRunRecord, "load", _on_load)
    try:
        client = TestClient(create_app())
        page = client.get("/api/ingestion-runs?limit=3")
        filtered = client.get("/api/ingestion-runs?source_id=src-entsog&limit=4")
    finally:
        event.remove(IngestionRunRecord, "load", _on_load)

    assert page.status_code == 200
    assert page.json()["data"] == expected_page
    assert filtered.status_code == 200
    assert filtered.json()["data"] == expected_entsog
    # 40 persisted runs; the two reads hydrate 3 + 4 rows, not the history.
    assert len(hydrations) == 7


def test_sources_response_keeps_run_status_semantics_with_configured_db(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The endpoint reports the same statuses and empty values as before."""

    from datetime import UTC, datetime, timedelta

    from sqlalchemy.orm import Session

    engine, _ = _runtime_store(tmp_path, "runs-endpoint.sqlite", monkeypatch)
    base = datetime(2026, 7, 1, 8, 0, tzinfo=UTC)
    with Session(engine) as session:
        session.add_all(
            [
                _ingestion_run(
                    "run-ecb-a",
                    "src-ecb",
                    base,
                    "succeeded",
                    finished_at=base + timedelta(seconds=1),
                ),
                _ingestion_run(
                    "run-ecb-b",
                    "src-ecb",
                    base + timedelta(minutes=1),
                    "failed",
                    finished_at=base + timedelta(minutes=1, seconds=1),
                ),
            ]
        )
        session.commit()

    response = TestClient(create_app()).get("/api/sources")

    assert response.status_code == 200
    body = response.json()
    assert body["meta"]["source_references"] == ["runtime-postgresql"]
    sources = {item["source_system"]: item for item in body["data"]}

    ecb = sources["ECB"]
    assert ecb["last_ingestion_status"] == "failed"
    assert ecb["connectivity_status"] == "failed"
    assert ecb["status"] == "failed"
    assert "last_ingestion_failed" in ecb["diagnostics"]
    assert ecb["last_success_at_utc"] == "2026-07-01T08:00:01+00:00"
    assert ecb["last_failure_at_utc"] == "2026-07-01T08:01:01+00:00"
    assert ecb["last_ingestion_message"] is None

    # A registered source with no persisted run keeps empty (not fabricated)
    # status fields and the missing-vs-empty behaviour of the registry read.
    entsog = sources["ENTSOG"]
    assert entsog["last_ingestion_status"] is None
    assert entsog["last_ingestion_message"] is None
    assert entsog["last_success_at_utc"] is None
    assert entsog["last_failure_at_utc"] is None
