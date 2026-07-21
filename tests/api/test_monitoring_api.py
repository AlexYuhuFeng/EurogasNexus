"""API tests for PostgreSQL-style monitoring reads and live LLM interaction."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import MonitoringAlertRecord
from eurogas_nexus.llm import DeepSeekCallResult


def _alert() -> MonitoringAlertRecord:
    now = datetime(2026, 7, 22, 8, 0, tzinfo=UTC)
    return MonitoringAlertRecord(
        alert_id="alert-test",
        fingerprint="test:alert",
        category="data_source",
        alert_type="ingestion_failed",
        severity="warning",
        status="open",
        title_en="ENTSOG ingestion failed",
        title_zh_cn="ENTSOG 数据更新失败",
        message_en="Latest run failed.",
        message_zh_cn="最近一次更新失败。",
        entity_type="data_source",
        entity_id="ENTSOG",
        event_time_utc=now,
        detected_at_utc=now,
        updated_at_utc=now,
        acknowledged_at_utc=None,
        resolved_at_utc=None,
        occurrence_count=1,
        evidence_snapshot={"run_id": "run-test"},
        source_refs=["ingestion-run:run-test"],
        warnings=[],
        llm_provider_id="DEEPSEEK",
        llm_status="pending",
        llm_summary_en=None,
        llm_summary_zh_cn=None,
        llm_last_attempt_at_utc=None,
        simulated=False,
        human_review_required=True,
    )


def test_monitoring_api_lists_acknowledges_and_calls_deepseek(
    tmp_path,
    monkeypatch,
) -> None:
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'monitoring.sqlite').as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(_alert())
        session.commit()

    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    monkeypatch.setattr(
        "eurogas_nexus.api.routes.public.monitoring.load_provider_api_key",
        lambda _provider: "never-returned-test-key",
    )
    monkeypatch.setattr(
        "eurogas_nexus.api.routes.public.monitoring.invoke_deepseek",
        lambda **_kwargs: DeepSeekCallResult(
            status="success",
            content="Check the ingestion endpoint and retry schedule.",
        ),
    )
    client = TestClient(create_app())

    listed = client.get("/api/monitoring/alerts")
    summary = client.get("/api/monitoring/summary")
    analyzed = client.post(
        "/api/monitoring/alerts/alert-test/analysis",
        json={
            "question": "What should the trader verify?",
            "language": "en",
            "model": "deepseek-v4-flash",
        },
    )
    acknowledged = client.post("/api/monitoring/alerts/alert-test/acknowledge")

    assert listed.status_code == 200
    assert listed.json()["data"][0]["alert_id"] == "alert-test"
    assert summary.json()["data"]["open_count"] == 1
    assert analyzed.status_code == 200
    assert analyzed.json()["data"]["provider_status"] == "success"
    assert "ingestion endpoint" in analyzed.json()["data"]["answer"]
    assert "never-returned-test-key" not in analyzed.text
    assert acknowledged.json()["data"]["status"] == "acknowledged"
