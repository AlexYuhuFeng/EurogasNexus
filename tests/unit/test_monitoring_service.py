"""Unit tests for deduplicated monitoring and LLM enrichment."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.application.monitoring_service import scan_monitoring_conditions
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import (
    IngestionRunRecord,
    IntradayOpportunityRecord,
    MonitoringAlertRecord,
)
from eurogas_nexus.llm import DeepSeekCallResult


def _opportunity(now: datetime) -> IntradayOpportunityRecord:
    return IntradayOpportunityRecord(
        opportunity_id=f"opp-{now.timestamp()}",
        scan_id=f"scan-{now.timestamp()}",
        opportunity_type="CROSS_HUB_SPREAD",
        status="ACTIONABLE_REVIEW",
        buy_quote_id="quote-buy",
        sell_quote_id="quote-sell",
        route_id="ttf-bbl-nbp",
        route_name="TTF-BBL-NBP",
        buy_venue="EEX_SIM",
        sell_venue="ICE_OCM_SIM",
        buy_hub="TTF",
        sell_hub="NBP",
        product="within-day",
        delivery_start_utc=now,
        delivery_end_utc=now + timedelta(hours=1),
        comparison_currency="GBP",
        comparison_unit="MWh",
        buy_ask=27.0,
        sell_bid=29.0,
        gross_spread=2.0,
        route_cost=0.8,
        trading_cost=0.1,
        risk_buffer=0.2,
        net_margin=0.9,
        max_quantity_mwh=1000.0,
        indicative_net_value=900.0,
        quote_age_seconds=2.0,
        confidence_score=0.93,
        cost_components=[],
        source_refs=["simulated-eex", "simulated-ice-ocm"],
        assumptions=["preview-price-input"],
        missing_inputs=[],
        warnings=[],
        detected_at_utc=now,
        valid_until_utc=now + timedelta(minutes=2),
        simulated=True,
        human_review_required=True,
    )


def test_same_condition_is_deduplicated_and_enriched_once() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    now = datetime(2026, 7, 22, 8, 0, tzinfo=UTC)
    calls: list[dict] = []

    def provider_call(**kwargs) -> DeepSeekCallResult:
        calls.append(kwargs)
        return DeepSeekCallResult(
            status="success",
            content=(
                '{"summary_en":"Review the spread evidence.",'
                '"summary_zh_cn":"请复核价差证据。"}'
            ),
        )

    with Session(engine) as session:
        session.add(_opportunity(now))
        session.commit()
        first = scan_monitoring_conditions(
            session,
            now_utc=now,
            api_key_loader=lambda _provider: "test-key",
            provider_call=provider_call,
        )
        second = scan_monitoring_conditions(
            session,
            now_utc=now + timedelta(seconds=10),
            api_key_loader=lambda _provider: "test-key",
            provider_call=provider_call,
        )
        alert = session.query(MonitoringAlertRecord).one()

    assert first == {"active_count": 1, "resolved_count": 0, "llm_enriched_count": 1}
    assert second == {"active_count": 1, "resolved_count": 0, "llm_enriched_count": 0}
    assert len(calls) == 1
    assert alert.occurrence_count == 1
    assert alert.llm_status == "success"
    assert alert.llm_summary_en == "Review the spread evidence."
    assert alert.llm_summary_zh_cn == "请复核价差证据。"


def test_source_failure_escalation_reopens_llm_enrichment() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    now = datetime(2026, 7, 22, 8, 0, tzinfo=UTC)
    calls = 0

    def provider_call(**_kwargs) -> DeepSeekCallResult:
        nonlocal calls
        calls += 1
        return DeepSeekCallResult(
            status="success",
            content='{"summary_en":"Source check.","summary_zh_cn":"检查数据源。"}',
        )

    with Session(engine) as session:
        session.add(
            IngestionRunRecord(
                run_id="run-1",
                source_name="ENTSOG",
                status="failed",
                started_at_utc=now,
                finished_at_utc=now,
                notes="timeout",
            )
        )
        session.commit()
        scan_monitoring_conditions(
            session,
            now_utc=now,
            api_key_loader=lambda _provider: "test-key",
            provider_call=provider_call,
        )
        for index in (2, 3):
            event_time = now + timedelta(minutes=index)
            session.add(
                IngestionRunRecord(
                    run_id=f"run-{index}",
                    source_name="ENTSOG",
                    status="failed",
                    started_at_utc=event_time,
                    finished_at_utc=event_time,
                    notes="timeout",
                )
            )
        session.commit()
        scan_monitoring_conditions(
            session,
            now_utc=now + timedelta(minutes=4),
            api_key_loader=lambda _provider: "test-key",
            provider_call=provider_call,
        )
        alert = session.query(MonitoringAlertRecord).one()

    assert calls == 2
    assert alert.severity == "critical"
    assert alert.status == "open"
    assert alert.occurrence_count == 2


def test_missing_deepseek_key_is_visible_without_provider_call() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    now = datetime(2026, 7, 22, 8, 0, tzinfo=UTC)

    with Session(engine) as session:
        session.add(_opportunity(now))
        session.commit()
        result = scan_monitoring_conditions(
            session,
            now_utc=now,
            api_key_loader=lambda _provider: None,
            provider_call=lambda **_kwargs: (_ for _ in ()).throw(
                AssertionError("provider must not be called")
            ),
        )
        alert = session.query(MonitoringAlertRecord).one()

    assert result["llm_enriched_count"] == 0
    assert alert.llm_status == "missing_credential"
