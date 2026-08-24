"""Governed LLM-ready analysis and report endpoints."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request

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
from eurogas_nexus.llm import invoke_deepseek
from eurogas_nexus.security.provider_keys import load_provider_api_key

router = APIRouter(tags=["analysis"])


@router.get("/api/analysis/ontology")
def get_business_ontology(request: Request) -> dict:
    """Return the business ontology used by analysis and reports.

    返回业务本体摘要（实体/关系/护栏），来源为领域契约而非运行时库。

    Args:
        request: Incoming FastAPI request (envelope context).

    Returns:
        Enveloped ontology dict with ``domain-contract`` source tag.
    """

    return _env(business_logic_ontology(), request, source="domain-contract")


@router.post("/api/analysis/query")
def post_analysis_query(body: AnalysisRequest, request: Request) -> dict:
    """Run one analysis query with optional provider synthesis.

    执行分析查询：加载快照 → （可选）调用 LLM provider → 组装确定性
    结果 → 审计与持久化。provider 仅在请求显式开启且密钥可用时调用。

    Args:
        body: Analysis request (question/task/context selections).
        request: Incoming FastAPI request (request-id context).

    Returns:
        Enveloped AnalysisResult with citations, sections and warnings.

    Raises:
        HTTPException: 403 ``llm_provider_denied`` when provider invocation
            is requested without a configured provider key.
    """

    snapshot = _load_snapshot(
        duration_start_utc=body.duration_start_utc,
        duration_end_utc=body.duration_end_utc,
    )
    request_id = getattr(request.state, "request_id", None)
    provider_text, provider_status = _maybe_invoke_provider(
        body,
        snapshot,
        request_id=request_id,
    )
    _audit_llm_decision(
        body=body,
        provider_status=provider_status,
        snapshot=snapshot,
        request_id=request_id,
    )
    result = build_analysis_result(
        body,
        snapshot,
        provider_text=provider_text,
        provider_status=provider_status,
    )
    if body.invoke_provider and not body.include_contract_prices:
        # 未授权合约价格参与 LLM 载荷：显式过滤并告警（fail-closed）。
        result.warnings = _unique([*result.warnings, "LLM_PAYLOAD_FILTERED:contract_prices"])
    _persist_analysis_if_db(body, snapshot, result)
    return _env(
        result.model_dump(mode="json"),
        request,
        source=snapshot.source,
        warnings=result.warnings,
    )


@router.post("/api/reports/portfolio")
def post_portfolio_report(body: PortfolioReportRequest, request: Request) -> dict:
    """Generate a portfolio decision-support report.

    生成组合决策支持报告（复用分析构建器，任务类型为 PORTFOLIO_REPORT）。

    Args:
        body: Portfolio report request.
        request: Incoming FastAPI request (request-id context).

    Returns:
        Enveloped AnalysisResult for the portfolio report.
    """

    snapshot = _load_snapshot(
        duration_start_utc=body.duration_start_utc,
        duration_end_utc=body.duration_end_utc,
    )
    request_id = getattr(request.state, "request_id", None)
    export_blocker = _export_blocker(snapshot)
    if export_blocker is not None:
        _record_audit(
            event_type="governance.policy",
            action="export.denied",
            resource="generated_reports",
            outcome="denied",
            severity="warning",
            detail=f"report generation blocked; unentitled snapshot source={export_blocker}",
            source_system="analysis",
            request_id=request_id,
        )
        raise HTTPException(
            status_code=403,
            detail={
                "error": "export_denied",
                "message": (
                    "Report generation blocked: snapshot contains data from an "
                    "unentitled source (fail-closed export policy)."
                ),
                "source_system": export_blocker,
                "research_only": True,
                "human_review_required": True,
            },
        )
    analysis_request = AnalysisRequest(
        question=body.title,
        task="PORTFOLIO_REPORT",
        provider_id=body.provider_id,
        model=body.model,
        invoke_provider=body.invoke_provider,
        include_contract_prices=body.include_contract_prices,
        selected_assets=body.selected_resources,
        selected_contracts=body.selected_contracts,
        duration_start_utc=body.duration_start_utc,
        duration_end_utc=body.duration_end_utc,
        language=body.language,
    )
    provider_text, provider_status = _maybe_invoke_provider(
        analysis_request,
        snapshot,
        request_id=request_id,
    )
    _audit_llm_decision(
        body=analysis_request,
        provider_status=provider_status,
        snapshot=snapshot,
        request_id=request_id,
    )
    result = build_portfolio_report(
        body,
        snapshot,
        provider_text=provider_text,
        provider_status=provider_status,
    )
    if body.invoke_provider and not body.include_contract_prices:
        result.warnings = _unique([*result.warnings, "LLM_PAYLOAD_FILTERED:contract_prices"])
    _persist_report_if_db(body, snapshot, result)
    _record_audit(
        event_type="governance.action",
        action="report.generated",
        resource=f"generated_reports:{result.analysis_id}",
        outcome="generated",
        severity="info",
        detail=f"portfolio report generated; provider_status={provider_status}",
        source_system="analysis",
        request_id=request_id,
    )
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
    if not _db_is_configured():
        return _empty_snapshot(
            source="runtime-db-not-configured",
            warnings=["RUNTIME_DB_NOT_CONFIGURED"],
        )
    return _db_snapshot(
        duration_start_utc=duration_start_utc,
        duration_end_utc=duration_end_utc,
    )


def _empty_snapshot(*, source: str, warnings: list[str]) -> AnalysisSnapshot:
    now = datetime.now(UTC)
    return AnalysisSnapshot(
        snapshot_id=f"snapshot-{uuid4().hex[:12]}",
        source=source,
        created_at_utc=now,
        ontology=business_logic_ontology(),
        glossary_terms=[term.localized("en") for term in baseline_glossary_terms()[:20]],
        warnings=warnings,
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
                        "aliases": row.aliases,
                        "related_terms": row.related_terms,
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
        return _empty_snapshot(
            source="runtime-postgresql-unavailable",
            warnings=["RUNTIME_POSTGRESQL_UNAVAILABLE"],
        )


def _maybe_invoke_provider(
    body: AnalysisRequest,
    snapshot: AnalysisSnapshot,
    *,
    request_id: str | None = None,
) -> tuple[str | None, str]:
    if not body.invoke_provider:
        return None, "not_invoked"

    from eurogas_nexus.core.config import get_settings

    if not get_settings().llm_external_provider_enabled:
        # P0-2: trial/release profiles never call external LLM providers.
        return None, "LLM_PROVIDER_DISABLED_IN_PROFILE"

    entitlement_blocker = _snapshot_entitlement_blocker(snapshot)
    if entitlement_blocker is not None:
        # P0-2: fail closed before any provider call when snapshot data is not
        # in the known-entitled set.
        _record_audit(
            event_type="governance.policy",
            action="entitlement.denied",
            resource="analysis_query",
            outcome="denied",
            severity="warning",
            detail=f"LLM invocation blocked; unentitled snapshot source={entitlement_blocker}",
            source_system="analysis",
            request_id=request_id,
        )
        return None, f"ENTITLEMENT_DENIED:{entitlement_blocker}"

    if body.provider_id != "DEEPSEEK":
        return None, "LLM_PROVIDER_NOT_SUPPORTED_IN_V1"
    credential = load_provider_api_key("DEEPSEEK") or load_provider_api_key("LLM")
    if credential is None:
        return None, "LLM_PROVIDER_CREDENTIAL_MISSING"

    snapshot_payload = _filtered_llm_payload(
        snapshot,
        include_contract_prices=body.include_contract_prices,
    )
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
                    "snapshot": snapshot_payload,
                },
                ensure_ascii=False,
            ),
        },
    ]
    result = invoke_deepseek(
        api_key=credential,
        messages=messages,
        model=body.model,
        temperature=0.2,
        max_tokens=1600,
    )
    if result.status == "success":
        return result.content, "success"
    return None, f"LLM_PROVIDER_CALL_FAILED:{result.error_code or result.status}"


# Financial fields excluded from LLM payloads unless the caller opts in.
_LLM_CONTRACT_FINANCIAL_FIELDS = frozenset(
    {
        "contract_price_gbp_mwh",
        "tolerance_risk_allowance_gbp_mwh",
        "annual_financing_rate_pct",
        "owned_entry_capacity_mwh_per_day",
        "owned_exit_capacity_mwh_per_day",
    }
)


def _filtered_llm_payload(
    snapshot: AnalysisSnapshot,
    *,
    include_contract_prices: bool,
) -> dict:
    """Return the provider-bound snapshot payload with field filtering.

    Gate 1: contract financial details are excluded by default so raw
    commercial prices never leave the platform without explicit opt-in.
    """

    payload = snapshot.model_dump(mode="json")
    if include_contract_prices:
        return payload
    filtered_contracts = []
    for row in payload.get("portfolio_context") or []:
        filtered_contracts.append(
            {
                key: value
                for key, value in row.items()
                if key not in _LLM_CONTRACT_FINANCIAL_FIELDS
            }
        )
    payload["portfolio_context"] = filtered_contracts
    return payload


def _export_blocker(snapshot: AnalysisSnapshot) -> str | None:
    """Return the first snapshot source whose entitlement scope is UNKNOWN.

    Unknown scope fails closed for export-like actions (report generation);
    internal-research and public scopes remain restricted-but-allowed inside
    the platform.
    """

    from eurogas_nexus.governance.entitlement import entitlement_check, export_check

    sources: set[str] = set()
    row_sections = (
        "market_observations",
        "live_market_marks",
        "fx_rates",
        "flow_observations",
        "capacity_context",
        "portfolio_context",
    )
    for section in row_sections:
        for row in getattr(snapshot, section, None) or []:
            value = row.get("source_system") if isinstance(row, dict) else None
            if isinstance(value, str) and value.strip():
                sources.add(value.strip())
    if not sources:
        return None
    for source in sorted(sources):
        candidate = source.removesuffix("_Sim") if source.endswith("_Sim") else source
        decision = entitlement_check(
            candidate,
            known_entitled_systems=_KNOWN_ENTITLED_SYSTEMS,
        )
        export = export_check(decision.scope)
        if export.decision.value == "denied":
            return source
    return None


def _audit_llm_decision(
    *,
    body: AnalysisRequest,
    provider_status: str,
    snapshot: AnalysisSnapshot,
    request_id: str | None,
) -> None:
    """Record an audit event for every requested LLM invocation attempt."""

    if not body.invoke_provider:
        return
    denied = provider_status.startswith("ENTITLEMENT_DENIED")
    _record_audit(
        event_type="governance.policy" if denied else "governance.action",
        action="llm.invoke.denied" if denied else "llm.invoke",
        resource=f"analysis_query:{body.task.value}",
        outcome=provider_status,
        severity="warning" if denied else "info",
        detail=(
            f"provider={body.provider_id}; filtered={not body.include_contract_prices}; "
            f"snapshot_source={snapshot.source}"
        ),
        source_system="analysis",
        request_id=request_id,
    )


def _record_audit(
    *,
    event_type: str,
    action: str,
    resource: str,
    outcome: str,
    severity: str,
    detail: str,
    source_system: str,
    request_id: str | None,
) -> None:
    from eurogas_nexus.application.audit_service import record_audit_event

    record_audit_event(
        event_type=event_type,
        action=action,
        resource=resource,
        outcome=outcome,
        severity=severity,
        detail=detail,
        source_system=source_system,
        request_id=request_id,
    )


_KNOWN_ENTITLED_SYSTEMS = frozenset(
    {
        "operator-input",
        "ENTSOG",
        "GIE",
        "ECB",
        "EEX",
        "Trayport",
        "ICE_OCM",
        "Weather",
    }
)


def _snapshot_entitlement_blocker(snapshot: AnalysisSnapshot) -> str | None:
    """Return the first source system in the snapshot that is not entitled.

    Simulated sources are evaluated by their licensed family (``EEX_Sim`` ->
    ``EEX``), so simulated rows follow the same entitlement boundary as their
    commercial counterpart. When no source rows are present (e.g. empty DB),
    there is nothing to leak and the check passes.
    """

    from eurogas_nexus.governance.entitlement import entitlement_check

    sources: set[str] = set()
    row_sections = (
        "market_observations",
        "live_market_marks",
        "fx_rates",
        "flow_observations",
        "capacity_context",
        "portfolio_context",
    )
    for section in row_sections:
        for row in getattr(snapshot, section, None) or []:
            value = row.get("source_system") if isinstance(row, dict) else None
            if isinstance(value, str) and value.strip():
                sources.add(value.strip())
    for row in snapshot.route_candidates or []:
        if not isinstance(row, dict):
            continue
        for value in row.get("source_systems") or []:
            if isinstance(value, str) and value.strip():
                sources.add(value.strip())
    if not sources:
        return None

    for source in sorted(sources):
        candidate = source.removesuffix("_Sim") if source.endswith("_Sim") else source
        decision = entitlement_check(
            candidate,
            known_entitled_systems=_KNOWN_ENTITLED_SYSTEMS,
        )
        if not decision.granted:
            return source
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
    from eurogas_nexus.governance.entitlement import entitlement_scope_for_source

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
        "entitlement_scope": entitlement_scope_for_source(row.source_system),
    }


def _live_mark_row(row) -> dict:
    from eurogas_nexus.governance.entitlement import entitlement_scope_for_source

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
        "entitlement_scope": entitlement_scope_for_source(row.source_system),
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
    from eurogas_nexus.governance.entitlement import entitlement_scope_for_source

    return {
        "point_name": row.point_name,
        "direction": row.direction,
        "kind": row.kind,
        "flow_mcm_d": row.flow_mcm_d,
        "period_start_utc": row.period_start_utc.isoformat(),
        "period_end_utc": row.period_end_utc.isoformat(),
        "source_system": row.source_system,
        "source_reference": row.source_reference,
        "freshness": row.freshness,
        "entitlement_scope": entitlement_scope_for_source(row.source_system),
    }


def _capacity_row(row) -> dict:
    from eurogas_nexus.governance.entitlement import entitlement_scope_for_source

    return {
        "capacity_profile_id": row.capacity_profile_id,
        "contract_id": row.contract_id,
        "point_name": row.point_name,
        "direction": row.direction,
        "capacity_mwh_per_day": row.capacity_mwh_per_day,
        "firmness": row.firmness,
        "capacity_product": row.capacity_product,
        "capacity_scope": row.capacity_scope,
        "valid_from_utc": row.valid_from_utc.isoformat(),
        "valid_to_utc": row.valid_to_utc.isoformat(),
        "source_reference": row.source_reference,
        "entitlement_scope": entitlement_scope_for_source("operator-input"),
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


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))
