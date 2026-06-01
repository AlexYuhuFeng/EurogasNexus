"""Governed LLM-ready analysis and report endpoints."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

import httpx
from fastapi import APIRouter, Request

from eurogas_nexus.domain.analysis import (
    AnalysisRequest,
    AnalysisResult,
    AnalysisSnapshot,
    PortfolioReportRequest,
    build_analysis_result,
    build_portfolio_report,
    business_logic_ontology,
)
from eurogas_nexus.domain.glossary import baseline_glossary_terms

router = APIRouter(tags=["analysis"])


@router.get("/api/v1/analysis/ontology")
def get_business_ontology(request: Request) -> dict:
    return _env(business_logic_ontology(), request, source="domain-contract")


@router.post("/api/v1/analysis/query")
def post_analysis_query(body: AnalysisRequest, request: Request) -> dict:
    snapshot = _load_snapshot()
    provider_text, provider_status = _maybe_invoke_provider(body, snapshot)
    result = build_analysis_result(
        body,
        snapshot,
        provider_text=provider_text,
        provider_status=provider_status,
    )
    _persist_analysis_if_db(body, snapshot, result)
    return _env(
        result.model_dump(mode="json"),
        request,
        source=snapshot.source,
        warnings=result.warnings,
    )


@router.post("/api/v1/reports/portfolio")
def post_portfolio_report(body: PortfolioReportRequest, request: Request) -> dict:
    snapshot = _load_snapshot()
    analysis_request = AnalysisRequest(
        question=body.title,
        task="PORTFOLIO_REPORT",
        provider_id=body.provider_id,
        model=body.model,
        invoke_provider=body.invoke_provider,
        selected_assets=body.selected_resources,
        selected_contracts=body.selected_contracts,
        duration_start_utc=body.duration_start_utc,
        duration_end_utc=body.duration_end_utc,
        language=body.language,
    )
    provider_text, provider_status = _maybe_invoke_provider(analysis_request, snapshot)
    result = build_portfolio_report(
        body,
        snapshot,
        provider_text=provider_text,
        provider_status=provider_status,
    )
    _persist_report_if_db(body, snapshot, result)
    return _env(
        result.model_dump(mode="json"),
        request,
        source=snapshot.source,
        warnings=result.warnings,
    )


def _load_snapshot(
    *,
    duration_start_utc: datetime | None = None,
    duration_end_utc: datetime | None = None,
) -> AnalysisSnapshot:
    if _db_is_configured():
        return _db_snapshot(
            duration_start_utc=duration_start_utc,
            duration_end_utc=duration_end_utc,
        )
    return _fallback_snapshot()


def _fallback_snapshot() -> AnalysisSnapshot:
    now = datetime.now(UTC)
    return AnalysisSnapshot(
        snapshot_id=f"snapshot-{uuid4().hex[:12]}",
        source="synthetic-fixture",
        created_at_utc=now,
        ontology=business_logic_ontology(),
        glossary_terms=[term.localized("en") for term in baseline_glossary_terms()[:20]],
        market_observations=[
            {
                "market_venue": "NBP",
                "product": "day-ahead",
                "price": 28.0,
                "unit": "GBP/MWh",
                "source_system": "synthetic-fixture",
                "source_reference": "synthetic-nbp-day-ahead",
            },
            {
                "market_venue": "ICE OCM",
                "product": "within-day",
                "price": 28.3,
                "unit": "GBP/MWh",
                "source_system": "synthetic-fixture",
                "source_reference": "synthetic-ice-ocm",
            },
            {
                "market_venue": "ICIS Heren",
                "product": "NBP day-ahead assessment",
                "price": 27.9,
                "unit": "GBP/MWh",
                "source_system": "synthetic-fixture",
                "source_reference": "synthetic-icis-heren",
            },
        ],
        live_market_marks=[
            {
                "venue": "ICE OCM",
                "hub": "NBP",
                "product": "within-day",
                "bid_gbp_mwh": 28.2,
                "ask_gbp_mwh": 28.4,
                "last_gbp_mwh": 28.3,
                "mark_time_utc": now.isoformat(),
                "source_system": "synthetic-fixture",
                "source_reference": "synthetic-ice-ocm-live-mark",
            }
        ],
        fx_rates=[
            {
                "pair": "EURGBP",
                "rate": 0.851,
                "source_system": "ECB",
                "source_reference": "synthetic-ecb-fx",
            }
        ],
        flow_observations=[
            {
                "point_name": "Easington Beach Terminal",
                "direction": "entry",
                "flow_mcm_d": 42.0,
                "period_start_utc": "2026-05-31T06:00:00Z",
                "period_end_utc": "2026-06-01T06:00:00Z",
                "source_system": "synthetic-fixture",
                "source_reference": "synthetic-easington-flow",
            }
        ],
        capacity_context=[
            {
                "point_name": "Easington Beach Terminal",
                "capacity_mcm_d": 100.0,
                "capacity_mwh_per_day": 1055000.0,
                "capacity_type": "technical",
                "direction": "entry",
                "valid_from_utc": "2026-01-01T00:00:00Z",
                "valid_to_utc": "2026-12-31T23:59:59Z",
                "source_system": "synthetic-fixture",
                "source_reference": "synthetic-easington-capacity",
            }
        ],
        route_candidates=[
            {
                "route_name": "Easington beach delivery -> NBP virtual sale",
                "required_tso_access": ["National Gas NTS"],
                "source_system": "synthetic-fixture",
            }
        ],
        portfolio_context=[
            {
                "contract_id": "demo-easington-contract",
                "contract_name": "Easington gas year contract",
                "resource_type": "BEACH_DELIVERY",
                "delivery_point_name": "Easington Entry Point",
                "delivery_quantity_mwh_per_day": 10000.0,
                "settlement_frequency": "monthly",
                "eligible_sale_modes": ["VIRTUAL_HUB_SALE", "PHYSICAL_DELIVERY"],
                "source_reference": "synthetic-easington-contract",
            }
        ],
        warnings=["Synthetic fallback context; connect PostgreSQL for customer use."],
    )


def _db_snapshot(
    *,
    duration_start_utc: datetime | None = None,
    duration_end_utc: datetime | None = None,
) -> AnalysisSnapshot:
    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        from eurogas_nexus.db.models import (
            CapacityProfileRecord,
            FlowObservationRecord,
            FxObservationRecord,
            GlossaryTermRecord,
            LiveMarketMarkRecord,
            MarketObservationRecord,
            RouteCandidateRecord,
            StrategyRunRecord,
            UpstreamResourceContractRecord,
        )
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            glossary = session.query(GlossaryTermRecord).filter(
                GlossaryTermRecord.active.is_(True)
            ).limit(50).all()
            market_query = session.query(MarketObservationRecord)
            if duration_start_utc:
                market_query = market_query.filter(
                    MarketObservationRecord.period_end_utc >= duration_start_utc
                )
            if duration_end_utc:
                market_query = market_query.filter(
                    MarketObservationRecord.period_start_utc <= duration_end_utc
                )
            markets = (
                market_query.order_by(MarketObservationRecord.observed_at_utc.desc())
                .limit(50)
                .all()
            )
            live_mark_query = session.query(LiveMarketMarkRecord)
            if duration_start_utc:
                live_mark_query = live_mark_query.filter(
                    LiveMarketMarkRecord.mark_time_utc >= duration_start_utc
                )
            if duration_end_utc:
                live_mark_query = live_mark_query.filter(
                    LiveMarketMarkRecord.mark_time_utc <= duration_end_utc
                )
            live_marks = (
                live_mark_query.order_by(LiveMarketMarkRecord.mark_time_utc.desc())
                .limit(50)
                .all()
            )
            fx_rows = session.query(FxObservationRecord).order_by(
                FxObservationRecord.observed_at_utc.desc()
            ).limit(20).all()
            flow_query = session.query(FlowObservationRecord)
            if duration_start_utc:
                flow_query = flow_query.filter(
                    FlowObservationRecord.period_end_utc >= duration_start_utc
                )
            if duration_end_utc:
                flow_query = flow_query.filter(
                    FlowObservationRecord.period_start_utc <= duration_end_utc
                )
            flows = (
                flow_query.order_by(FlowObservationRecord.period_end_utc.desc())
                .limit(50)
                .all()
            )
            capacity_query = session.query(CapacityProfileRecord)
            if duration_start_utc:
                capacity_query = capacity_query.filter(
                    CapacityProfileRecord.valid_to_utc >= duration_start_utc
                )
            if duration_end_utc:
                capacity_query = capacity_query.filter(
                    CapacityProfileRecord.valid_from_utc <= duration_end_utc
                )
            capacities = (
                capacity_query.order_by(CapacityProfileRecord.valid_from_utc.desc())
                .limit(50)
                .all()
            )
            routes = session.query(RouteCandidateRecord).filter(
                RouteCandidateRecord.active.is_(True)
            ).limit(50).all()
            strategies = session.query(StrategyRunRecord).order_by(
                StrategyRunRecord.started_at_utc.desc()
            ).limit(20).all()
            contracts = session.query(UpstreamResourceContractRecord).limit(50).all()
            return AnalysisSnapshot(
                snapshot_id=f"snapshot-{uuid4().hex[:12]}",
                source="runtime-postgresql",
                created_at_utc=datetime.now(UTC),
                ontology=business_logic_ontology(),
                glossary_terms=[
                    {
                        "term_id": row.term_id,
                        "term": row.term,
                        "category": row.category,
                        "definition_en": row.definition_en,
                        "definition_zh_cn": row.definition_zh_cn,
                        "source_refs": row.source_refs,
                    }
                    for row in glossary
                ],
                market_observations=[_market_row(row) for row in markets],
                live_market_marks=[_live_mark_row(row) for row in live_marks],
                fx_rates=[_fx_row(row) for row in fx_rows],
                flow_observations=[_flow_row(row) for row in flows],
                capacity_context=[_capacity_row(row) for row in capacities],
                route_candidates=[_route_row(row) for row in routes],
                strategy_runs=[_strategy_row(row) for row in strategies],
                portfolio_context=[_contract_row(row) for row in contracts],
            )
    except sqlalchemy_error:
        return _fallback_snapshot()


def _maybe_invoke_provider(
    body: AnalysisRequest,
    snapshot: AnalysisSnapshot,
) -> tuple[str | None, str]:
    if not body.invoke_provider:
        return None, "not_invoked"
    if body.provider_id != "DEEPSEEK":
        return None, "LLM_PROVIDER_NOT_SUPPORTED_IN_V1"
    credential = _load_provider_api_key("DEEPSEEK") or _load_provider_api_key("LLM")
    if credential is None:
        return None, "LLM_PROVIDER_CREDENTIAL_MISSING"

    messages = [
        {
            "role": "system",
            "content": (
                "You are Eurogas Nexus analysis support. Use only the supplied "
                "snapshot. Return decision-support analysis with citations, warnings, "
                "missing inputs, research_only=true, and human_review_required=true. "
                "Do not create orders, nominations, execution instructions, legal "
                "advice, or official trading recommendations."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "question": body.question,
                    "task": body.task,
                    "snapshot": snapshot.model_dump(mode="json"),
                },
                ensure_ascii=False,
            ),
        },
    ]
    try:
        response = httpx.post(
            "https://api.deepseek.com/chat/completions",
            headers={"Authorization": f"Bearer {credential}", "Content-Type": "application/json"},
            json={"model": body.model, "messages": messages, "temperature": 0.2},
            timeout=45,
        )
        response.raise_for_status()
        payload = response.json()
        text = payload["choices"][0]["message"]["content"]
        return str(text), "success"
    except Exception as exc:
        return None, f"LLM_PROVIDER_CALL_FAILED:{exc.__class__.__name__}"


def _load_provider_api_key(provider_id: str) -> str | None:
    if not _db_is_configured():
        return None
    try:
        from eurogas_nexus.db.models import ProviderCredentialRecord
        from eurogas_nexus.db.session import get_session_factory
        from eurogas_nexus.security.credentials import decrypt_credential_payload

        with get_session_factory()() as session:
            row = session.get(ProviderCredentialRecord, provider_id)
            if row is None:
                return None
            payload = decrypt_credential_payload(row.encrypted_payload)
            value = payload.get("api_key")
            return str(value) if value else None
    except Exception:
        return None


def _persist_analysis_if_db(
    body: AnalysisRequest,
    snapshot: AnalysisSnapshot,
    result: AnalysisResult,
) -> None:
    if not _db_is_configured():
        return
    try:
        from eurogas_nexus.db.models import AnalysisRunRecord
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            session.merge(
                AnalysisRunRecord(
                    analysis_id=result.analysis_id,
                    task=result.task.value,
                    provider_id=result.provider_id,
                    provider_status=result.provider_status,
                    prompt_snapshot={"question": body.question, "task": body.task.value},
                    input_snapshot=snapshot.model_dump(mode="json"),
                    output_snapshot=result.model_dump(mode="json"),
                    source_refs=result.citations,
                    warnings=result.warnings,
                    created_at_utc=result.created_at_utc,
                    research_only=True,
                    human_review_required=True,
                )
            )
            session.commit()
    except Exception:
        return


def _persist_report_if_db(
    body: PortfolioReportRequest,
    snapshot: AnalysisSnapshot,
    result: AnalysisResult,
) -> None:
    if not _db_is_configured():
        return
    try:
        from eurogas_nexus.db.models import GeneratedReportRecord
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            session.merge(
                GeneratedReportRecord(
                    report_id=result.analysis_id,
                    report_type="PORTFOLIO",
                    title=body.title,
                    status=result.provider_status,
                    duration_start_utc=body.duration_start_utc,
                    duration_end_utc=body.duration_end_utc,
                    input_snapshot=snapshot.model_dump(mode="json"),
                    sections=[section.model_dump(mode="json") for section in result.sections],
                    source_refs=result.citations,
                    warnings=result.warnings,
                    created_at_utc=result.created_at_utc,
                    research_only=True,
                    human_review_required=True,
                )
            )
            session.commit()
    except Exception:
        return


def _market_row(row) -> dict:
    return {
        "market_venue": row.market_venue,
        "product": row.product,
        "price": row.price,
        "unit": row.unit,
        "currency": row.currency,
        "period_start_utc": row.period_start_utc.isoformat(),
        "period_end_utc": row.period_end_utc.isoformat(),
        "source_system": row.source_system,
        "source_reference": row.source_reference,
        "freshness": row.freshness,
    }


def _live_mark_row(row) -> dict:
    return {
        "venue": row.venue,
        "hub": row.hub,
        "product": row.product,
        "bid_gbp_mwh": row.bid_gbp_mwh,
        "ask_gbp_mwh": row.ask_gbp_mwh,
        "last_gbp_mwh": row.last_gbp_mwh,
        "mark_time_utc": row.mark_time_utc.isoformat(),
        "source_system": row.source_system,
        "source_reference": row.source_reference,
    }


def _fx_row(row) -> dict:
    return {
        "pair": row.pair,
        "rate": row.rate,
        "rate_type": row.rate_type,
        "value_date": row.value_date,
        "source_system": row.source_system,
        "source_reference": row.source_reference,
        "freshness": row.freshness,
    }


def _flow_row(row) -> dict:
    return {
        "point_name": row.point_name,
        "direction": row.direction,
        "flow_mcm_d": row.flow_mcm_d,
        "period_start_utc": row.period_start_utc.isoformat(),
        "period_end_utc": row.period_end_utc.isoformat(),
        "source_system": row.source_system,
        "source_reference": row.source_reference,
        "freshness": row.freshness,
    }


def _capacity_row(row) -> dict:
    return {
        "capacity_profile_id": row.capacity_profile_id,
        "contract_id": row.contract_id,
        "point_name": row.point_name,
        "direction": row.direction,
        "capacity_mwh_per_day": row.capacity_mwh_per_day,
        "firmness": row.firmness,
        "valid_from_utc": row.valid_from_utc.isoformat(),
        "valid_to_utc": row.valid_to_utc.isoformat(),
        "source_reference": row.source_reference,
    }


def _route_row(row) -> dict:
    return {
        "route_id": row.route_id,
        "route_name": row.route_name,
        "start_point_name": row.start_point_name,
        "target_point_name": row.target_point_name,
        "business_model": row.business_model,
        "required_tso_access": row.required_tso_access,
        "source_systems": row.source_systems,
    }


def _strategy_row(row) -> dict:
    return {
        "run_id": row.run_id,
        "strategy_id": row.strategy_id,
        "run_mode": row.run_mode,
        "status": row.status,
        "started_at_utc": row.started_at_utc.isoformat(),
        "finished_at_utc": row.finished_at_utc.isoformat() if row.finished_at_utc else None,
        "source_refs": row.source_refs,
        "warnings": row.warnings,
    }


def _contract_row(row) -> dict:
    return {
        "contract_id": row.contract_id,
        "contract_name": row.contract_name,
        "resource_type": row.resource_type,
        "delivery_point_name": row.delivery_point_name,
        "gas_year": row.gas_year,
        "delivery_quantity_mwh_per_day": row.delivery_quantity_mwh_per_day,
        "contract_price_gbp_mwh": row.contract_price_gbp_mwh,
        "settlement_frequency": row.settlement_frequency,
        "eligible_sale_modes": row.eligible_sale_modes,
        "source_reference": row.contract_id,
    }


def _db_is_configured() -> bool:
    from eurogas_nexus.db.session import resolve_database_url

    return resolve_database_url() is not None


def _sqlalchemy_error_type():
    from sqlalchemy.exc import SQLAlchemyError

    return SQLAlchemyError


def _env(
    data: object,
    _request: Request,
    *,
    source: str,
    warnings: list[str] | None = None,
) -> dict:
    return {
        "data": data,
        "meta": {
            "research_only": True,
            "human_review_required": True,
            "source_references": [source],
            "warnings": list(dict.fromkeys(warnings or [])),
        },
    }
