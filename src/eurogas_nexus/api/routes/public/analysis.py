"""Governed LLM-ready analysis and report endpoints."""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request

from eurogas_nexus.api.dependencies.ai_authority import ai_authority_denial, ai_caller
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

if TYPE_CHECKING:  # pragma: no cover - a type-only import, never executed
    # `_maybe_invoke_provider` annotates the caller it re-authorises. The name was used without
    # being imported, which `from __future__ import annotations` made invisible at runtime and
    # only a linter could see (`F821`): the annotation was unresolved for any tool that reads it.
    from eurogas_nexus.security.identity import AuthenticatedPrincipal

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

    A caller may cite an ``analysis_snapshot_id`` (Architecture V2 Wave 4). The
    reference is verified *before* anything else happens - before the input
    snapshot is loaded and before any provider call - so an unverifiable
    citation can never be paid for with an external request, and the result
    echoes it only when one was supplied. The citation is part of the persisted
    analysis record, so re-reading the analysis does not lose it.

    Args:
        body: Analysis request (question/task/context selections).
        request: Incoming FastAPI request (request-id context).

    Returns:
        Enveloped AnalysisResult with citations, sections and warnings.

    Raises:
        HTTPException: 403 ``llm_provider_denied`` when provider invocation
            is requested without a configured provider key; 422
            ``analysis_selection_not_supported`` when a selection the pipeline
            cannot apply is supplied; the Analysis Snapshot refusal contract
            (503/422) when a citation cannot be verified.
    """

    _refuse_unsupported_selection(
        (
            ("selected_terms", body.selected_terms),
            ("selected_assets", body.selected_assets),
            ("selected_contracts", body.selected_contracts),
            ("include_sections", body.include_sections),
        ),
        resource="analysis_query",
    )
    _require_known_analysis_snapshot(body.analysis_snapshot_id, resource="analysis_query")

    snapshot = _load_snapshot(
        duration_start_utc=body.duration_start_utc,
        duration_end_utc=body.duration_end_utc,
    )
    request_id = getattr(request.state, "request_id", None)
    if body.invoke_provider:
        from eurogas_nexus.api.dependencies.row_entitlement import require_derived_access

        require_derived_access(
            request,
            _snapshot_source_systems(snapshot),
            resource="analysis_query",
        )
    provider_text, provider_status = _maybe_invoke_provider(
        body,
        snapshot,
        request_id=request_id,
        principal=ai_caller(request),
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
    result.analysis_snapshot_id = body.analysis_snapshot_id
    if body.invoke_provider and not body.include_contract_prices:
        # 未授权合约价格参与 LLM 载荷：显式过滤并告警（fail-closed）。
        result.warnings = _unique([*result.warnings, "LLM_PAYLOAD_FILTERED:contract_prices"])
    _persist_analysis_if_db(body, snapshot, result)
    return _env(
        _cited_payload(result),
        request,
        source=snapshot.source,
        warnings=result.warnings,
    )


@router.post("/api/reports/portfolio")
def post_portfolio_report(body: PortfolioReportRequest, request: Request) -> dict:
    """Generate a portfolio decision-support report.

    生成组合决策支持报告（复用分析构建器，任务类型为 PORTFOLIO_REPORT）。

    A caller may cite an ``analysis_snapshot_id`` (Architecture V2 Wave 4). The
    reference is verified before the snapshot is loaded and before any provider
    call, the generated report echoes it only when one was supplied, and the
    tracked report run records it as the snapshot it was computed against - so a
    report that cites nothing keeps its previous payload and job inputs exactly.

    Args:
        body: Portfolio report request.
        request: Incoming FastAPI request (request-id context).

    Returns:
        Enveloped AnalysisResult for the portfolio report.

    Raises:
        HTTPException: 422 ``analysis_selection_not_supported`` when a portfolio,
            resource, contract or strategy selection is supplied - the report is
            computed from the whole entitled snapshot, so a selection would be a
            scope the caller believed was applied.
    """

    _refuse_unsupported_selection(
        (
            ("portfolio_id", body.portfolio_id),
            ("selected_resources", body.selected_resources),
            ("selected_contracts", body.selected_contracts),
            ("selected_strategies", body.selected_strategies),
        ),
        resource="portfolio_report",
    )
    _require_known_analysis_snapshot(body.analysis_snapshot_id, resource="portfolio_report")

    snapshot = _load_snapshot(
        duration_start_utc=body.duration_start_utc,
        duration_end_utc=body.duration_end_utc,
    )
    request_id = getattr(request.state, "request_id", None)
    from eurogas_nexus.api.dependencies.row_entitlement import require_derived_access

    caller = ai_caller(request)
    require_derived_access(
        request,
        _snapshot_source_systems(snapshot),
        resource="portfolio_report",
    )
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
        # No selection is carried over: the route refuses a non-empty one, so a
        # copied field would be a value no builder reads.
        duration_start_utc=body.duration_start_utc,
        duration_end_utc=body.duration_end_utc,
        language=body.language,
    )
    provider_text, provider_status = _maybe_invoke_provider(
        analysis_request,
        snapshot,
        request_id=request_id,
        principal=caller,
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
    result.analysis_snapshot_id = body.analysis_snapshot_id
    if body.invoke_provider and not body.include_contract_prices:
        result.warnings = _unique([*result.warnings, "LLM_PAYLOAD_FILTERED:contract_prices"])
    persisted, store_configured = _persist_report_if_db(body, snapshot, result)
    if store_configured and not persisted:
        # A configured store that refused the write must not be silent: the caller is told
        # the report was generated but not stored, so nobody treats it as filed.
        result.warnings = _unique([*result.warnings, "REPORT_NOT_PERSISTED"])
    _track_report_run(
        body=body,
        result=result,
        persisted=persisted,
        principal=caller,
        request_id=request_id,
    )
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
        _cited_payload(result),
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
    principal: AuthenticatedPrincipal | None = None,
) -> tuple[str | None, str]:
    if not body.invoke_provider:
        return None, "not_invoked"

    from eurogas_nexus.core.config import get_settings

    if not get_settings().llm_external_provider_enabled:
        # P0-2: trial/release profiles never call external LLM providers.
        return None, "LLM_PROVIDER_DISABLED_IN_PROFILE"

    # AI runs under the caller's own authority (Architecture V2 rule 22): the
    # entitlement gate below protects the *payload*, this protects the *invocation*.
    if principal is not None:
        authority_denial = ai_authority_denial(principal)
        if authority_denial:
            _record_audit(
                event_type="governance.policy",
                action="ai.authority",
                resource="analysis_query",
                outcome="denied",
                severity="warning",
                detail=f"LLM invocation blocked; {authority_denial}",
                source_system="analysis",
                request_id=request_id,
            )
            return None, "AI_AUTHORITY_DENIED"

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


def _snapshot_source_systems(snapshot: AnalysisSnapshot) -> set[str]:
    """Return the source-system set of a snapshot (used by entitlement)."""

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
    return sources


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


def _selection_was_supplied(value: object) -> bool:
    """Return whether a caller really filled in a selection field.

    Absent (``None``), blank and empty collections are all "nothing was selected", so a
    caller who sends the field with an empty value is not refused while a caller who names
    a portfolio, a resource, a contract, a strategy, a section, an asset or a term is.
    """

    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, frozenset)):
        return any(str(item).strip() for item in value)
    return True


def _refuse_unsupported_selection(
    selections: Sequence[tuple[str, object]],
    *,
    resource: str,
) -> None:
    """Refuse a selection the analysis pipeline cannot apply.

    The run's deterministic builders read the snapshot, the task and the question.
    They read no glossary term, asset, contract, strategy, section or portfolio
    selection, so a non-empty one describes work that will not happen: the caller
    would receive a report over the whole entitled snapshot while believing it had
    been narrowed to what they named. Refusing is the only honest answer, and it is
    given before the snapshot is loaded, before the run is tracked and before any
    provider call, so a refused selection costs nothing.

    The evidence references an AI action carries are not lost by this refusal: they
    travel inside ``question`` (or the report title), which is exactly what the
    platform records as the run's prompt snapshot and sends to the provider.

    Args:
        selections: ``(field name, value)`` pairs as supplied by the caller.
        resource: Surface label echoed in the refusal.

    Raises:
        HTTPException: 422 ``analysis_selection_not_supported`` naming every
            non-empty field.
    """

    refused = [name for name, value in selections if _selection_was_supplied(value)]
    if not refused:
        return
    raise HTTPException(
        status_code=422,
        detail={
            "error": "analysis_selection_not_supported",
            "message": (
                "The analysis pipeline reads no selection or filter field: it "
                "analyses the whole entitled snapshot for the supplied question. "
                "Send the evidence references inside 'question' instead of a "
                "selection field, or remove the field."
            ),
            "fields": refused,
            "resource": resource,
            "research_only": True,
            "human_review_required": True,
        },
    )


def _require_known_analysis_snapshot(snapshot_id: str | None, *, resource: str) -> None:
    """Fail closed when a supplied Analysis Snapshot reference does not exist.

    The check itself lives in
    :mod:`eurogas_nexus.api.dependencies.analysis_snapshot`, so every run path
    that accepts an optional ``analysis_snapshot_id`` refuses an unknown
    reference with the same status codes and the same error codes.

    Args:
        snapshot_id: The caller-supplied reproducibility reference, or ``None``.
        resource: Surface label used in the 503 message.

    Raises:
        HTTPException: 503 or 422, per the dependency's contract.
    """

    from eurogas_nexus.api.dependencies.analysis_snapshot import (
        require_known_analysis_snapshot,
    )

    require_known_analysis_snapshot(snapshot_id, resource=resource)


def _cited_payload(result: AnalysisResult) -> dict:
    """Serialise a result, carrying the cited reference only when one was given.

    An analysis result always has an input ``snapshot_id``, but the Wave 4
    reproducibility reference is optional and additive: a caller that cites
    nothing keeps the previous payload exactly, so the field is dropped rather
    than sent as a null it never asked for.
    """

    payload = result.model_dump(mode="json")
    if not result.analysis_snapshot_id:
        payload.pop("analysis_snapshot_id", None)
    return payload


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
) -> tuple[bool, bool]:
    """Persist the generated report, reporting whether it really was stored.

    Persistence stays best-effort - a report is decision support and a store that
    refuses the write must not fail the run - but it is no longer silent: the caller
    learns whether the artefact exists, so a run cannot cite a report the store does
    not hold (Architecture V2 Wave 8 job tracking).

    Returns:
        ``(persisted, store_configured)``. A deployment without a runtime store reports
        ``(False, False)``: that is a documented posture the envelope already declares,
        not a failed write.
    """

    if not _db_is_configured():
        return (False, False)
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
        return (True, True)
    except Exception:  # noqa: BLE001 - a refused write must not fail the run
        return (False, True)


def _track_report_run(
    *,
    body: PortfolioReportRequest,
    result: AnalysisResult,
    persisted: bool,
    principal,
    request_id: str | None,
) -> None:
    """Register a generated report into the unified job model (Architecture V2 Wave 8).

    Report generation is synchronous inside the request, so the tracker records the
    outcome that already happened: the job row carries the same request id, the inputs it
    ran with and - only when the report really was persisted - the report as its output
    reference. A run that could not be stored therefore appears in ``/api/jobs`` with an
    honest, empty artefact list instead of citing a report the store does not hold.

    Tracking never changes the response: an unreachable store or a store without
    ``job_records`` leaves the generated report exactly as it is.
    """

    from eurogas_nexus.application.jobs import run_tracked_job

    def _record(handle) -> None:
        if persisted:
            handle.add_output(f"generated_report:{result.analysis_id}")

    run_tracked_job(
        _record,
        kind="REPORT",
        # The job model records the acting principal's name, as the dataset-build and
        # optimisation paths do: the compatibility deployment token's identifier is not
        # expressible in the principal vocabulary, its name is.
        principal=principal.name,
        # A report is not scoped to individual resources: the route refuses a
        # resource selection, and the run records the scope it really had - the
        # cited Analysis Snapshot - rather than a narrowing that never happened.
        scope_refs=(),
        inputs={
            "title": body.title,
            "report_id": result.analysis_id,
            "duration_start_utc": _iso_or_none(body.duration_start_utc),
            "duration_end_utc": _iso_or_none(body.duration_end_utc),
            "provider_invoked": bool(body.invoke_provider),
            "analysis_snapshot_id": body.analysis_snapshot_id or "",
        },
        correlation_id=request_id,
        provenance=("analysis", "portfolio-report"),
        # The Analysis Snapshot the report cites is the reference the run was computed
        # against; a report that cited none records an empty reference rather than a guess.
        snapshot_id=body.analysis_snapshot_id or "",
    )


def _iso_or_none(value) -> str | None:
    """Format an optional datetime for a job input hash."""

    return value.isoformat() if hasattr(value, "isoformat") else None


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
