"""Unit tests for deduplicated monitoring and LLM enrichment."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.application.monitoring_service import scan_monitoring_conditions
from eurogas_nexus.application.service_identity import SERVICE_PRINCIPAL_ENV
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import (
    IngestionRunRecord,
    IntradayOpportunityRecord,
    MonitoringAlertRecord,
)
from eurogas_nexus.db.repositories.identity import create_identity_principal
from eurogas_nexus.llm import DeepSeekCallResult

SERVICE_PRINCIPAL_NAME = "monitoring-test-worker"


def _provision_service_identity(session, monkeypatch) -> None:
    """Provision the persisted SERVICE identity these enrichments act as (owner decision D7).

    The provider boundary re-reads this row before every call and refuses anything that is not
    the deployment's configured service principal, so the tests provision the identity rather
    than hand-building an authority dataclass the boundary would (rightly) not trust.
    """

    create_identity_principal(
        session,
        name=SERVICE_PRINCIPAL_NAME,
        display_name="Monitoring Test Worker",
        role="ANALYST",
        principal_type="SERVICE",
        data_scopes=[],
    )
    session.commit()
    monkeypatch.setenv(SERVICE_PRINCIPAL_ENV, SERVICE_PRINCIPAL_NAME)


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


def test_same_condition_is_deduplicated_and_enriched_once(monkeypatch) -> None:
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
        _provision_service_identity(session, monkeypatch)
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

    assert first["active_count"] == 1
    assert first["resolved_count"] == 0
    assert first["llm_enriched_count"] == 1
    # D7: a granted run enriches and reports no refusal.
    assert first["llm_enrichment_refused"] == ""
    assert second["active_count"] == 1
    assert second["resolved_count"] == 0
    # The deduplicated condition is not enriched a second time, under the same granted authority.
    assert second["llm_enriched_count"] == 0
    assert len(calls) == 1
    assert alert.occurrence_count == 1
    assert alert.llm_status == "success"
    assert alert.llm_summary_en == "Review the spread evidence."
    assert alert.llm_summary_zh_cn == "请复核价差证据。"


def test_source_failure_escalation_reopens_llm_enrichment(monkeypatch) -> None:
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
        _provision_service_identity(session, monkeypatch)
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


def test_missing_deepseek_key_is_visible_without_provider_call(monkeypatch) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    now = datetime(2026, 7, 22, 8, 0, tzinfo=UTC)

    with Session(engine) as session:
        _provision_service_identity(session, monkeypatch)
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


def test_source_failure_alerts_count_canonical_and_legacy_failures_identically() -> None:
    """The shared vocabulary drives the alert condition and the streak count.

    ``FAILED`` and legacy ``failed`` are the same failure outcome; pending,
    cancelled, warning-qualified success and unknown stored values are not
    failures and interrupt the streak. The raw stored status stays visible in
    the evidence snapshot.
    """

    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    now = datetime(2026, 7, 22, 9, 0, tzinfo=UTC)
    runs = [
        # Two consecutive failures, canonical on top of legacy.
        ("ENTSOG", "run-entsog-3", "FAILED", 3),
        ("ENTSOG", "run-entsog-2", "failed", 2),
        ("ENTSOG", "run-entsog-1", "SUCCEEDED", 1),
        # Three consecutive failures, mixed spellings: critical.
        ("GIE", "run-gie-3", "failed", 3),
        ("GIE", "run-gie-2", "FAILED", 2),
        ("GIE", "run-gie-1", "FAILED", 1),
        # A warning-qualified success is not a failure alert.
        ("ECB", "run-ecb-2", "SUCCEEDED_WITH_WARNINGS", 2),
        ("ECB", "run-ecb-1", "FAILED", 1),
        # Cancelled, unknown and pending runs are not failures, and each one
        # interrupts the streak behind it.
        ("BBL", "run-bbl-2", "CANCELLED", 2),
        ("BBL", "run-bbl-1", "failed", 1),
        ("IUK", "run-iuk-2", "MYSTERY", 2),
        ("IUK", "run-iuk-1", "failed", 1),
        ("GTS", "run-gts-2", "running", 2),
        ("GTS", "run-gts-1", "FAILED", 1),
    ]

    with Session(engine) as session:
        for source_name, run_id, status, minute in runs:
            event_time = now + timedelta(minutes=minute)
            session.add(
                IngestionRunRecord(
                    run_id=run_id,
                    source_name=source_name,
                    status=status,
                    started_at_utc=event_time,
                    finished_at_utc=event_time,
                    notes="probe",
                )
            )
        session.commit()
        result = scan_monitoring_conditions(
            session,
            now_utc=now + timedelta(minutes=5),
            enrich_with_llm=False,
        )
        alerts = session.query(MonitoringAlertRecord).order_by(
            MonitoringAlertRecord.entity_id
        ).all()

    assert result["active_count"] == 2
    assert [alert.entity_id for alert in alerts] == ["ENTSOG", "GIE"]

    by_source = {alert.entity_id: alert for alert in alerts}
    assert by_source["ENTSOG"].severity == "warning"
    assert by_source["ENTSOG"].evidence_snapshot["consecutive_failures"] == 2
    assert by_source["ENTSOG"].evidence_snapshot["status"] == "FAILED"
    assert by_source["GIE"].severity == "critical"
    assert by_source["GIE"].evidence_snapshot["consecutive_failures"] == 3
    assert by_source["GIE"].evidence_snapshot["status"] == "failed"
