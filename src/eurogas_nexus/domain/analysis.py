"""LLM-ready analysis and report contracts built from backend data snapshots."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, Field


class AnalysisTask(StrEnum):
    DB_INQUIRY = "DB_INQUIRY"
    GLOSSARY_QA = "GLOSSARY_QA"
    PNL_TRACKING = "PNL_TRACKING"
    TSO_STATUS_REPORT = "TSO_STATUS_REPORT"
    PORTFOLIO_REPORT = "PORTFOLIO_REPORT"
    MARKET_MOVEMENT = "MARKET_MOVEMENT"


class AnalysisRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4096)
    task: AnalysisTask = AnalysisTask.DB_INQUIRY
    provider_id: str = "DEEPSEEK"
    model: str = "deepseek-chat"
    invoke_provider: bool = False
    selected_terms: list[str] = Field(default_factory=list)
    selected_assets: list[str] = Field(default_factory=list)
    selected_contracts: list[str] = Field(default_factory=list)
    duration_start_utc: datetime | None = None
    duration_end_utc: datetime | None = None
    include_sections: list[str] = Field(default_factory=list)
    language: str = "en"


class PortfolioReportRequest(BaseModel):
    title: str = "Portfolio decision-support report"
    provider_id: str = "DEEPSEEK"
    model: str = "deepseek-chat"
    invoke_provider: bool = False
    portfolio_id: str | None = None
    selected_resources: list[str] = Field(default_factory=list)
    selected_contracts: list[str] = Field(default_factory=list)
    selected_strategies: list[str] = Field(default_factory=list)
    duration_start_utc: datetime | None = None
    duration_end_utc: datetime | None = None
    language: str = "en"


class AnalysisSnapshot(BaseModel):
    snapshot_id: str
    source: str
    created_at_utc: datetime
    ontology: dict
    glossary_terms: list[dict] = Field(default_factory=list)
    market_observations: list[dict] = Field(default_factory=list)
    fx_rates: list[dict] = Field(default_factory=list)
    flow_observations: list[dict] = Field(default_factory=list)
    capacity_context: list[dict] = Field(default_factory=list)
    route_candidates: list[dict] = Field(default_factory=list)
    strategy_runs: list[dict] = Field(default_factory=list)
    portfolio_context: list[dict] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ReportSection(BaseModel):
    section_id: str
    title: str
    content: str
    citations: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class AnalysisResult(BaseModel):
    analysis_id: str
    task: AnalysisTask
    provider_id: str
    provider_status: str
    answer_en: str
    answer_zh_cn: str
    citations: list[str] = Field(default_factory=list)
    sections: list[ReportSection] = Field(default_factory=list)
    missing_inputs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    snapshot_id: str
    created_at_utc: datetime
    research_only: bool = True
    human_review_required: bool = True


class GlossaryContext(BaseModel):
    term: str
    context_type: str
    description: str
    capacity: dict | None = None
    capacity_usage: dict | None = None
    related_prices: list[dict] = Field(default_factory=list)
    related_routes: list[dict] = Field(default_factory=list)
    related_sources: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    research_only: bool = True
    human_review_required: bool = True


def business_logic_ontology() -> dict:
    """Return the V1 business ontology used by analysis and reports."""

    return {
        "entities": [
            "UpstreamResourceContract",
            "ResourcePool",
            "CapacityProfile",
            "RouteCandidate",
            "TsoTariff",
            "MarketObservation",
            "LiveMarketMark",
            "FxObservation",
            "FlowObservation",
            "LngRegasScenario",
            "StrategyDefinition",
            "StrategyRun",
            "StrategyAllocationTarget",
            "GlossaryTerm",
            "GeneratedReport",
        ],
        "relationships": [
            "resource_contract feeds resource_pool",
            "resource_pool allocates_to route_candidate",
            "route_candidate requires tso_tariff and company_tso_access",
            "route_candidate consumes market_observation and live_market_mark",
            "lng_regas_scenario requires terminal_access and slot_window",
            "strategy_run evaluates resource_pool, market_observation, and risk_control",
            "generated_report cites source snapshots and strategy runs",
            "glossary_term links to operational context when identifiers match",
        ],
        "guardrails": [
            "PostgreSQL is runtime source of truth",
            "clients access data through API/SDK only",
            "LLM providers are not source of truth",
            "outputs are decision support and human review required",
            "no order entry, routing, execution, trade capture, or nomination submission",
        ],
    }


def build_analysis_result(
    request: AnalysisRequest,
    snapshot: AnalysisSnapshot,
    *,
    provider_text: str | None = None,
    provider_status: str = "not_invoked",
) -> AnalysisResult:
    """Build deterministic cited output, optionally enriched by provider text."""

    citations = _snapshot_citations(snapshot)
    missing_inputs = _missing_inputs_for_task(request, snapshot)
    warnings = [*snapshot.warnings]
    if not request.invoke_provider:
        warnings.append("LLM_PROVIDER_NOT_INVOKED")
    if provider_status not in {"not_invoked", "success"}:
        warnings.append(provider_status)

    sections = _default_sections(request, snapshot, provider_text)
    answer_en = provider_text or _deterministic_answer_en(request, snapshot)
    answer_zh = _deterministic_answer_zh(request, snapshot)
    return AnalysisResult(
        analysis_id=f"analysis-{uuid4().hex[:12]}",
        task=request.task,
        provider_id=request.provider_id,
        provider_status=provider_status,
        answer_en=answer_en,
        answer_zh_cn=answer_zh,
        citations=citations,
        sections=sections,
        missing_inputs=missing_inputs,
        warnings=_unique(warnings),
        snapshot_id=snapshot.snapshot_id,
        created_at_utc=datetime.now(UTC),
    )


def build_portfolio_report(
    request: PortfolioReportRequest,
    snapshot: AnalysisSnapshot,
    *,
    provider_text: str | None = None,
    provider_status: str = "not_invoked",
) -> AnalysisResult:
    analysis_request = AnalysisRequest(
        question=request.title,
        task=AnalysisTask.PORTFOLIO_REPORT,
        provider_id=request.provider_id,
        model=request.model,
        invoke_provider=request.invoke_provider,
        selected_contracts=request.selected_contracts,
        selected_assets=request.selected_resources,
        duration_start_utc=request.duration_start_utc,
        duration_end_utc=request.duration_end_utc,
        language=request.language,
    )
    return build_analysis_result(
        analysis_request,
        snapshot,
        provider_text=provider_text,
        provider_status=provider_status,
    )


def build_glossary_context(term: str, snapshot: AnalysisSnapshot) -> GlossaryContext:
    key = term.strip().lower()
    if "easington" in key:
        return GlossaryContext(
            term=term,
            context_type="entry_point",
            description=(
                "UK National Gas NTS entry point and beach delivery reference. "
                "Capacity, usage, and prices should be read from runtime DB when available."
            ),
            capacity=_first_capacity(snapshot, "easington"),
            capacity_usage=_capacity_usage(snapshot, "easington"),
            related_prices=_related_prices(snapshot, ["NBP", "ICE OCM", "ICIS"]),
            related_routes=_related_routes(snapshot, ["Easington", "NBP", "Bacton"]),
            related_sources=["National Gas NTS", "ENTSOG", "ICE OCM", "ICIS Heren"],
            warnings=_context_warnings(snapshot),
        )
    if "icis" in key or "heren" in key:
        return GlossaryContext(
            term=term,
            context_type="price_assessment",
            description=(
                "ICIS Heren is treated as a price-assessment reference. Values must "
                "come from licensed user data or operator-entered records."
            ),
            related_prices=_related_prices(snapshot, ["ICIS", "NBP", "TTF"]),
            related_sources=["ICIS Heren", "licensed user data"],
            warnings=[
                *_context_warnings(snapshot),
                "ICIS_HEREN_REQUIRES_CUSTOMER_LICENSED_DATA",
            ],
        )
    return GlossaryContext(
        term=term,
        context_type="generic",
        description="No dedicated operational context mapping exists yet for this term.",
        related_prices=_related_prices(snapshot, [term]),
        related_sources=_snapshot_citations(snapshot),
        warnings=[*_context_warnings(snapshot), "TERM_CONTEXT_MAPPING_PARTIAL"],
    )


def _default_sections(
    request: AnalysisRequest,
    snapshot: AnalysisSnapshot,
    provider_text: str | None,
) -> list[ReportSection]:
    sections = [
        ReportSection(
            section_id="portfolio",
            title="Portfolio and resources",
            content=(
                f"{len(snapshot.portfolio_context)} portfolio records and "
                f"{len(snapshot.route_candidates)} route candidates were available."
            ),
            citations=_snapshot_citations(snapshot),
        ),
        ReportSection(
            section_id="market",
            title="Market and physical context",
            content=(
                f"{len(snapshot.market_observations)} market observations, "
                f"{len(snapshot.fx_rates)} FX rates, and "
                f"{len(snapshot.flow_observations)} flow observations were available."
            ),
            citations=_snapshot_citations(snapshot),
        ),
        ReportSection(
            section_id="strategy",
            title="Strategy and PnL context",
            content=(
                f"{len(snapshot.strategy_runs)} strategy run records were available. "
                "Historical PnL requires persisted strategy or portfolio PnL records."
            ),
            citations=_snapshot_citations(snapshot),
            warnings=["HISTORICAL_PNL_REQUIRES_PERSISTED_PNL_SERIES"],
        ),
    ]
    if provider_text:
        sections.append(
            ReportSection(
                section_id="llm",
                title=f"{request.provider_id} synthesis",
                content=provider_text,
                citations=_snapshot_citations(snapshot),
            )
        )
    return sections


def _deterministic_answer_en(request: AnalysisRequest, snapshot: AnalysisSnapshot) -> str:
    return (
        f"{request.task} was evaluated against snapshot {snapshot.snapshot_id}. "
        f"Available context: {len(snapshot.market_observations)} market observations, "
        f"{len(snapshot.fx_rates)} FX rates, {len(snapshot.flow_observations)} flow records, "
        f"{len(snapshot.route_candidates)} routes, and "
        f"{len(snapshot.strategy_runs)} strategy runs. "
        "Use the cited source snapshots and warnings before making any commercial decision."
    )


def _deterministic_answer_zh(request: AnalysisRequest, snapshot: AnalysisSnapshot) -> str:
    return (
        f"{request.task} 已基于快照 {snapshot.snapshot_id} 进行评估。"
        f"可用上下文包括 {len(snapshot.market_observations)} 条市场观测、"
        f"{len(snapshot.fx_rates)} 条汇率、{len(snapshot.flow_observations)} 条物理流量、"
        f"{len(snapshot.route_candidates)} 条路线和 {len(snapshot.strategy_runs)} 条策略运行。"
        "在作出任何商业决策前，必须查看引用来源、缺失输入和预警。"
    )


def _missing_inputs_for_task(
    request: AnalysisRequest,
    snapshot: AnalysisSnapshot,
) -> list[str]:
    missing: list[str] = []
    if request.task in {AnalysisTask.PNL_TRACKING, AnalysisTask.PORTFOLIO_REPORT}:
        if not snapshot.strategy_runs:
            missing.append("STRATEGY_OR_PORTFOLIO_PNL_SERIES_MISSING")
        if not snapshot.portfolio_context:
            missing.append("PORTFOLIO_CONTEXT_MISSING")
    if request.task == AnalysisTask.TSO_STATUS_REPORT and not snapshot.flow_observations:
        missing.append("TSO_FLOW_OBSERVATIONS_MISSING")
    if request.task == AnalysisTask.MARKET_MOVEMENT and not snapshot.market_observations:
        missing.append("MARKET_OBSERVATIONS_MISSING")
    return missing


def _snapshot_citations(snapshot: AnalysisSnapshot) -> list[str]:
    citations = [snapshot.source]
    for collection in (
        snapshot.market_observations,
        snapshot.fx_rates,
        snapshot.flow_observations,
        snapshot.capacity_context,
        snapshot.route_candidates,
        snapshot.strategy_runs,
    ):
        for row in collection:
            ref = row.get("source_reference") or row.get("source_system")
            if ref:
                citations.append(str(ref))
    return _unique(citations)


def _first_capacity(snapshot: AnalysisSnapshot, point_key: str) -> dict | None:
    for row in snapshot.capacity_context:
        if point_key in str(row.get("point_name", "")).lower():
            return row
    return None


def _capacity_usage(snapshot: AnalysisSnapshot, point_key: str) -> dict | None:
    for row in snapshot.flow_observations:
        if point_key in str(row.get("point_name", "")).lower():
            capacity = _first_capacity(snapshot, point_key) or {}
            capacity_value = capacity.get("capacity_mwh_per_day") or capacity.get("capacity_mcm_d")
            flow_value = row.get("flow_mwh_per_day") or row.get("flow_mcm_d")
            usage_pct = None
            if capacity_value and flow_value:
                usage_pct = round(float(flow_value) / float(capacity_value) * 100, 2)
            return {
                "period_start_utc": row.get("period_start_utc"),
                "period_end_utc": row.get("period_end_utc"),
                "used": flow_value,
                "capacity": capacity_value,
                "usage_pct": usage_pct,
                "source_reference": row.get("source_reference"),
            }
    return None


def _related_prices(snapshot: AnalysisSnapshot, keys: list[str]) -> list[dict]:
    normalized = [key.lower() for key in keys]
    prices: list[dict] = []
    for row in snapshot.market_observations:
        haystack = " ".join(
            str(row.get(field, ""))
            for field in ("market_venue", "product", "price_name", "source_system")
        ).lower()
        if any(key in haystack for key in normalized):
            prices.append(row)
    return prices[:10]


def _related_routes(snapshot: AnalysisSnapshot, keys: list[str]) -> list[dict]:
    normalized = [key.lower() for key in keys]
    routes: list[dict] = []
    for row in snapshot.route_candidates:
        haystack = " ".join(str(value) for value in row.values()).lower()
        if any(key.lower() in haystack for key in normalized):
            routes.append(row)
    return routes[:10]


def _context_warnings(snapshot: AnalysisSnapshot) -> list[str]:
    warnings = list(snapshot.warnings)
    if snapshot.source != "runtime-postgresql":
        warnings.append("RUNTIME_DB_CONTEXT_NOT_AVAILABLE")
    return _unique(warnings)


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))
