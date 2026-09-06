"""CR-11 reliability/operations tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from eurogas_nexus.api.app import create_app
from eurogas_nexus.api.middleware.observability import (
    http_metric_lines,
    record_request,
)
from eurogas_nexus.application.shadow_runtime import recover_stale_evaluations
from eurogas_nexus.core.config import Settings
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.session import get_engine
from eurogas_nexus.domain.operations.errors import (
    OperationalErrorCategory,
    classify_exception,
    classify_http_status,
)


def test_liveness_never_depends_on_database(monkeypatch) -> None:
    monkeypatch.delenv("RUNTIME_STORE_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)

    client = TestClient(create_app(Settings(api_profile="release")))
    monkeypatch.setenv("EUROGAS_NEXUS_PUBLIC_API_TOKEN", "public-token")
    response = client.get("/api/health/live", headers={"X-Eurogas-Api-Key": "public-token"})
    assert response.status_code == 200
    assert response.json()["scope"] == "liveness"


def test_readiness_is_not_liveness(monkeypatch) -> None:
    monkeypatch.delenv("RUNTIME_STORE_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    client = TestClient(create_app())

    response = client.get("/api/health/ready")
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "runtime_db_not_configured"


def test_readiness_with_complete_sqlite_schema(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "ready.sqlite"
    engine = create_engine(f"sqlite+pysqlite:///{db_path.as_posix()}", future=True)
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)"
        )
    monkeypatch.setenv(
        "RUNTIME_STORE_DATABASE_URL",
        f"sqlite+pysqlite:///{db_path.as_posix()}",
    )
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    response = TestClient(create_app()).get("/api/health/ready")
    assert response.status_code == 200
    assert response.json()["status"] == "ready"


def test_optional_provider_outage_does_not_change_liveness() -> None:
    # Liveness route never imports provider/LLM/OIDC call paths.
    from eurogas_nexus.api.routes.public.health import health_live

    request = type(
        "Request",
        (),
        {"app": type("App", (), {"state": type("State", (), {"settings": Settings()})()})()},
    )()
    payload = health_live(request)
    assert payload["scope"] == "liveness"


def test_error_taxonomy_is_stable() -> None:
    assert classify_exception(TimeoutError("too slow")).category == OperationalErrorCategory.TIMEOUT
    assert classify_exception(ConnectionError("db")).category == OperationalErrorCategory.DATABASE
    assert classify_http_status(429).code == "rate_limited"
    assert classify_http_status(503).retryable is True
    assert classify_http_status(401).category == OperationalErrorCategory.AUTHENTICATION


def test_http_observability_records_low_cardinality_metrics() -> None:
    record_request("/api/sources/src-123/health", 200, 12.5)
    record_request("/api/market/observations", 503, 80.0)
    lines = http_metric_lines()
    assert any("/api/sources" in line for line in lines)
    assert any("eurogas_http_errors_total" in line for line in lines)
    assert not any("src-123" in line for line in lines)


def test_db_pool_settings_are_applied(monkeypatch) -> None:
    import eurogas_nexus.db.session as db_session

    monkeypatch.setenv("EUROGAS_NEXUS_DB_POOL_SIZE", "3")
    monkeypatch.setenv("EUROGAS_NEXUS_DB_MAX_OVERFLOW", "4")
    monkeypatch.setenv("EUROGAS_NEXUS_DB_POOL_TIMEOUT", "2")
    captured: dict[str, object] = {}

    def fake_create_engine(url: str, **kwargs: object):
        captured["url"] = url
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(db_session, "create_engine", fake_create_engine)
    get_engine("postgresql+pg8000://user:pass@db/eurogas")
    assert captured["pool_size"] == 3
    assert captured["max_overflow"] == 4
    assert captured["pool_timeout"] == 2.0


def test_stale_shadow_evaluation_recovery(tmp_path) -> None:
    db_path = tmp_path / "shadow-recover.sqlite"
    engine = create_engine(f"sqlite+pysqlite:///{db_path.as_posix()}", future=True)
    Base.metadata.create_all(engine)
    from sqlalchemy.orm import Session

    from eurogas_nexus.db.models import (
        StrategyRecord,
        StrategyShadowEvaluationRecord,
        StrategyShadowMonitorRecord,
        StrategyVersionRecord,
    )

    now = datetime.now(UTC)
    with Session(engine) as session:
        strategy = StrategyRecord(
            strategy_id="strategy-recover",
            name="Recover Strategy",
            description="",
            created_by="operator",
            created_at_utc=now,
            updated_at_utc=now,
            research_only=True,
        )
        version = StrategyVersionRecord(
            strategy_version_id="version-recover",
            strategy_id=strategy.strategy_id,
            version_number=1,
            status="FROZEN",
            definition_json={"components": []},
            hypothesis="",
            schema_version="strategy-version/v1",
            content_hash="hash",
            created_by="operator",
            created_at_utc=now,
            research_only=True,
        )
        monitor = StrategyShadowMonitorRecord(
            shadow_monitor_id="monitor-recover",
            strategy_id=strategy.strategy_id,
            strategy_version_id=version.strategy_version_id,
            baseline_run_id=None,
            state="ACTIVE",
            schedule_json={"type": "INTERVAL", "interval_seconds": 3600},
            created_by="operator",
            created_at_utc=now - timedelta(hours=1),
            activated_at_utc=now - timedelta(hours=1),
            consecutive_failures=0,
            health_state="OK",
            cumulative_shadow_pnl_gbp=0.0,
            current_exposure_mwh_per_day=0.0,
            next_evaluation_at_utc=now + timedelta(hours=1),
            research_only=True,
        )
        evaluation = StrategyShadowEvaluationRecord(
            shadow_evaluation_id="eval-recover",
            shadow_monitor_id=monitor.shadow_monitor_id,
            strategy_version_id=version.strategy_version_id,
            scheduled_for_utc=now - timedelta(hours=1),
            started_at_utc=now - timedelta(hours=1),
            decision_time_utc=None,
            completed_at_utc=None,
            state="RUNNING",
            gas_day=None,
            gas_day_start_utc=None,
            gas_day_end_utc=None,
            snapshot_id=None,
            candidate_id=None,
            price_evidence_refs=[],
            fx_evidence_refs=[],
            resource_evidence_refs=[],
            source_systems=[],
            freshness_json=[],
            missing_inputs=[],
            warnings=[],
            result_json=None,
            failure_class=None,
            retry_count=0,
            research_only=True,
            human_review_required=True,
        )
        session.add_all([strategy, version, monitor, evaluation])
        session.commit()

    with Session(engine) as session:
        recovered = recover_stale_evaluations(
            session,
            now_utc=now + timedelta(hours=2),
            stale_after_seconds=300,
        )
        assert recovered == 1
        evaluation = session.get(StrategyShadowEvaluationRecord, "eval-recover")
        assert evaluation.state == "FAILED"
        assert evaluation.failure_class == "INTERNAL_ERROR"
