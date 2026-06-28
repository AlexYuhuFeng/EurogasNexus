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
    live_market_marks: list[dict] = Field(default_factory=list)
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
    description_en: str | None = None
    description_zh_cn: str | None = None
    requested_duration: dict | None = None
    entity_summary: dict | None = None
    matched_entities: list[dict] = Field(default_factory=list)
    capacity: dict | None = None
    capacity_usage: dict | None = None
    metrics: list[dict] = Field(default_factory=list)
    related_prices: list[dict] = Field(default_factory=list)
    related_routes: list[dict] = Field(default_factory=list)
    related_contracts: list[dict] = Field(default_factory=list)
    live_market_marks: list[dict] = Field(default_factory=list)
    context_sections: list[dict] = Field(default_factory=list)
    related_sources: list[str] = Field(default_factory=list)
    data_quality: dict = Field(default_factory=dict)
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


def build_glossary_context(
    term: str,
    snapshot: AnalysisSnapshot,
    *,
    duration_start_utc: datetime | None = None,
    duration_end_utc: datetime | None = None,
    lang: str = "en",
) -> GlossaryContext:
    profile = _resolved_glossary_context_profile(term, snapshot)
    duration = _duration_payload(duration_start_utc, duration_end_utc)
    point_keys = profile["point_keys"]
    price_keys = profile["price_keys"]
    route_keys = profile["route_keys"]
    matched_entities = _matched_entities(
        snapshot,
        point_keys=point_keys,
        price_keys=price_keys,
        route_keys=route_keys,
        contract_keys=[*point_keys, *route_keys],
    )

    capacity = _first_capacity(
        snapshot,
        point_keys,
        duration_start_utc=duration_start_utc,
        duration_end_utc=duration_end_utc,
    )
    capacity_usage = _capacity_usage(
        snapshot,
        point_keys,
        duration_start_utc=duration_start_utc,
        duration_end_utc=duration_end_utc,
    )
    prices = _related_prices(
        snapshot,
        price_keys,
        duration_start_utc=duration_start_utc,
        duration_end_utc=duration_end_utc,
    )
    live_marks = _related_live_marks(
        snapshot,
        price_keys,
        duration_start_utc=duration_start_utc,
        duration_end_utc=duration_end_utc,
    )
    routes = _related_routes(snapshot, route_keys)
    contracts = _related_contracts(snapshot, [*point_keys, *route_keys])
    warnings = _context_warnings(snapshot)
    warnings.extend(profile["warnings"])
    if profile["context_type"] in {"entry_point", "exit_point", "capacity"} and capacity is None:
        warnings.append("CAPACITY_CONTEXT_MISSING")
    if (
        profile["context_type"] in {"entry_point", "exit_point", "capacity"}
        and capacity_usage is None
    ):
        warnings.append("CAPACITY_USAGE_CONTEXT_MISSING")
    if (
        profile["context_type"] in {"price_assessment", "hub", "venue"}
        and not prices
        and not live_marks
    ):
        warnings.append("PRICE_CONTEXT_MISSING")

    description_en = profile["description_en"]
    description_zh_cn = profile["description_zh_cn"]
    entity_summary = _entity_summary(
        term=term,
        profile=profile,
        capacity=capacity,
        capacity_usage=capacity_usage,
        prices=prices,
        live_marks=live_marks,
        routes=routes,
        contracts=contracts,
        matched_entities=matched_entities,
    )
    metrics = _context_metrics(capacity, capacity_usage, prices, live_marks, contracts)
    data_quality = _context_data_quality(
        snapshot,
        prices,
        live_marks,
        capacity,
        capacity_usage,
        matched_entities,
    )
    return GlossaryContext(
        term=term,
        context_type=profile["context_type"],
        description=description_zh_cn if lang in {"zh", "zh-CN"} else description_en,
        description_en=description_en,
        description_zh_cn=description_zh_cn,
        requested_duration=duration,
        entity_summary=entity_summary,
        matched_entities=matched_entities,
        capacity=capacity,
        capacity_usage=capacity_usage,
        metrics=metrics,
        related_prices=prices,
        related_routes=routes,
        related_contracts=contracts,
        live_market_marks=live_marks,
        context_sections=_context_sections(
            entity_summary=entity_summary,
            capacity=capacity,
            capacity_usage=capacity_usage,
            metrics=metrics,
            prices=prices,
            live_marks=live_marks,
            routes=routes,
            contracts=contracts,
            data_quality=data_quality,
            warnings=warnings,
        ),
        related_sources=profile["related_sources"] or _sources_from_matched_entities(
            matched_entities,
            snapshot,
        ),
        data_quality=data_quality,
        warnings=_unique(warnings),
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
        snapshot.live_market_marks,
        snapshot.fx_rates,
        snapshot.flow_observations,
        snapshot.capacity_context,
        snapshot.route_candidates,
        snapshot.strategy_runs,
        snapshot.portfolio_context,
    ):
        for row in collection:
            ref = row.get("source_reference") or row.get("source_system")
            if ref:
                citations.append(str(ref))
    return _unique(citations)


def _resolved_glossary_context_profile(term: str, snapshot: AnalysisSnapshot) -> dict:
    key = term.strip().lower()
    profile = _glossary_context_profile(key)
    glossary_rows = _matching_glossary_rows(term, snapshot)
    point_keys = _unique(
        [
            *profile["point_keys"],
            term,
            *_term_operational_keys(term),
            *[
                value
                for row in glossary_rows
                for value in [row.get("term"), *row.get("aliases", [])]
            ],
        ]
    )
    related_terms = _unique(
        [
            value
            for row in glossary_rows
            for value in [*row.get("related_terms", []), *row.get("source_refs", [])]
        ]
    )
    price_keys = _unique(
        [
            *profile["price_keys"],
            term,
            *_term_operational_keys(term),
            *related_terms,
        ]
    )
    route_keys = _unique([*profile["route_keys"], *point_keys, *related_terms])
    matched = _matched_entities(
        snapshot,
        point_keys=point_keys,
        price_keys=price_keys,
        route_keys=route_keys,
        contract_keys=[*point_keys, *route_keys],
    )
    context_type = _infer_context_type(profile["context_type"], term, glossary_rows, matched)
    description_en, description_zh_cn = _context_description(
        term,
        profile=profile,
        glossary_rows=glossary_rows,
        context_type=context_type,
    )
    warnings = list(profile["warnings"])
    if profile["context_type"] == "generic" and matched:
        warnings = [warning for warning in warnings if warning != "TERM_CONTEXT_MAPPING_PARTIAL"]
    related_sources = _unique([*profile["related_sources"], *related_terms])
    return {
        **profile,
        "context_type": context_type,
        "point_keys": point_keys,
        "price_keys": price_keys,
        "route_keys": route_keys,
        "description_en": description_en,
        "description_zh_cn": description_zh_cn,
        "related_sources": related_sources,
        "warnings": warnings,
    }


def _matching_glossary_rows(term: str, snapshot: AnalysisSnapshot) -> list[dict]:
    key = term.strip().lower()
    matches: list[dict] = []
    for row in snapshot.glossary_terms:
        candidates = [
            row.get("term"),
            row.get("term_id"),
            *row.get("aliases", []),
        ]
        normalized = [str(value).strip().lower() for value in candidates if value]
        if key in normalized or any(candidate and candidate in key for candidate in normalized):
            matches.append(row)
    return matches


def _term_operational_keys(term: str) -> list[str]:
    key = term.strip()
    lower_key = key.lower()
    variants = [key]
    suffixes = (
        " entry point",
        " exit point",
        " beach terminal",
        " terminal",
        " assessment",
        " price",
    )
    for suffix in suffixes:
        if lower_key.endswith(suffix):
            variants.append(key[: -len(suffix)].strip())
    tokens = [token for token in key.replace("-", " ").split() if len(token) >= 3]
    if len(tokens) >= 2:
        variants.append(" ".join(tokens[:2]))
    return _unique([value for value in variants if value])


def _infer_context_type(
    base_context_type: str,
    term: str,
    glossary_rows: list[dict],
    matched_entities: list[dict],
) -> str:
    if base_context_type != "generic":
        return base_context_type
    key = term.strip().lower()
    categories = {str(row.get("category", "")).lower() for row in glossary_rows}
    if "entry point" in key:
        return "entry_point"
    if "exit point" in key:
        return "exit_point"
    if "hub" in categories:
        return "hub"
    if "venue" in categories:
        return "venue"
    if "price" in categories:
        return "price_assessment"
    if any(
        entity["entity_type"] in {"capacity_point", "flow_point"}
        for entity in matched_entities
    ):
        directions = {str(entity.get("direction", "")).lower() for entity in matched_entities}
        if "entry" in directions:
            return "entry_point"
        if "exit" in directions:
            return "exit_point"
        return "capacity"
    if any(
        entity["entity_type"] in {"market_price", "live_market_mark"}
        for entity in matched_entities
    ):
        return "price_assessment"
    return base_context_type


def _context_description(
    term: str,
    *,
    profile: dict,
    glossary_rows: list[dict],
    context_type: str,
) -> tuple[str, str]:
    if profile["context_type"] != "generic":
        return profile["description_en"], profile["description_zh_cn"]
    if glossary_rows:
        row = glossary_rows[0]
        en = str(row.get("definition_en") or row.get("definition") or "").strip()
        zh = str(row.get("definition_zh_cn") or en).strip()
        if en:
            return en, zh
    en = (
        f"{term} is resolved from matching runtime records. Context type is "
        f"{context_type}; available capacity, usage, prices, live marks, routes, "
        "and contracts are shown when present in PostgreSQL."
    )
    zh = (
        f"{term} 由运行库中的匹配记录解析。上下文类型为 {context_type}；"
        "当 PostgreSQL 中存在容量、使用量、价格、实时标记、路线和合同记录时会一并展示。"
    )
    return en, zh


def _glossary_context_profile(key: str) -> dict:
    if "icis" in key or "heren" in key:
        return {
            "context_type": "price_assessment",
            "point_keys": ["nbp"],
            "price_keys": ["icis", "heren", "nbp", "day-ahead"],
            "route_keys": ["nbp", "iuk", "bbl"],
            "description_en": (
                "ICIS Heren is a licensed price-assessment reference. Eurogas Nexus "
                "can display and compare customer-licensed or operator-entered ICIS "
                "records against screen marks, but the repository must not contain "
                "raw licensed assessment data."
            ),
            "description_zh_cn": (
                "ICIS Heren 是需授权的价格评估来源。Eurogas Nexus 可以展示并比较客户授权"
                "或操作员录入的 ICIS 价格与屏幕价格，但代码仓库不得包含原始授权评估数据。"
            ),
            "related_sources": ["ICIS Heren", "licensed customer data", "operator-entered records"],
            "warnings": ["ICIS_HEREN_REQUIRES_CUSTOMER_LICENSED_DATA"],
        }
    if key in {"nbp", "national balancing point"} or "national balancing point" in key:
        return {
            "context_type": "hub",
            "point_keys": ["nbp"],
            "price_keys": ["nbp", "ice ocm", "icis", "eex"],
            "route_keys": ["nbp", "iuk", "bbl"],
            "description_en": (
                "NBP is the UK virtual gas hub. Context links the hub to UK route "
                "options, screen marks, day-ahead assessments, and physical entry "
                "points that can monetize upstream resources."
            ),
            "description_zh_cn": (
                "NBP 是英国虚拟天然气交易枢纽。上下文会关联英国路线、屏幕价格、日前评估价"
                "以及可用于变现上游资源的物理入口点。"
            ),
            "related_sources": ["ICE OCM", "EEX", "ICIS Heren", "National Gas NTS"],
            "warnings": [],
        }
    if key in {"ttf", "title transfer facility"} or "title transfer facility" in key:
        return {
            "context_type": "hub",
            "point_keys": ["ttf"],
            "price_keys": ["ttf", "eex", "ice"],
            "route_keys": ["ttf", "the", "ncg"],
            "description_en": (
                "TTF is the Dutch virtual gas hub and a continental European benchmark. "
                "Context focuses on related marks, route candidates, and FX where "
                "available."
            ),
            "description_zh_cn": (
                "TTF 是荷兰虚拟天然气枢纽和欧洲大陆基准价。"
                "上下文重点展示相关价格、路线和可用汇率。"
            ),
            "related_sources": ["EEX", "ICE", "ECB"],
            "warnings": [],
        }
    if "ice ocm" in key or key == "ocm":
        return {
            "context_type": "venue",
            "point_keys": ["nbp"],
            "price_keys": ["ice ocm", "ocm", "nbp", "within-day"],
            "route_keys": ["nbp", "iuk", "bbl"],
            "description_en": (
                "ICE OCM is the UK within-day gas market. Context emphasizes bid, ask, "
                "last marks and the resource routes whose PnL can be marked against "
                "those executable screen prices."
            ),
            "description_zh_cn": (
                "ICE OCM 是英国日内天然气市场。上下文重点展示买价、卖价、"
                "最新价以及可按这些屏幕价盯市的资源路线。"
            ),
            "related_sources": ["ICE OCM", "National Gas NTS"],
            "warnings": [],
        }
    if "entry capacity" in key or "exit capacity" in key:
        direction = "entry" if "entry" in key else "exit"
        return {
            "context_type": "capacity",
            "point_keys": [direction],
            "price_keys": ["capacity", "tariff", "nts"],
            "route_keys": [direction, "national gas"],
            "description_en": (
                f"{direction.title()} capacity is the contractual or tariffed right "
                "to flow gas through a system point. Context shows matching capacity "
                "profiles, usage observations, tariffs or routes when present."
            ),
            "description_zh_cn": (
                f"{direction.title()} capacity 表示在系统点进行天然气流动所需的合同或收费容量权利。"
                "上下文会展示匹配的容量、使用量、费率或路线。"
            ),
            "related_sources": ["TSO tariff", "ENTSOG", "capacity profile"],
            "warnings": [],
        }
    return {
        "context_type": "generic",
        "point_keys": [key],
        "price_keys": [key],
        "route_keys": [key],
        "description_en": "No dedicated operational context mapping exists yet for this term.",
        "description_zh_cn": "该术语暂未配置专用运行上下文映射。",
        "related_sources": [],
        "warnings": ["TERM_CONTEXT_MAPPING_PARTIAL"],
    }


def _duration_payload(
    duration_start_utc: datetime | None,
    duration_end_utc: datetime | None,
) -> dict | None:
    if duration_start_utc is None and duration_end_utc is None:
        return None
    return {
        "duration_start_utc": duration_start_utc.isoformat() if duration_start_utc else None,
        "duration_end_utc": duration_end_utc.isoformat() if duration_end_utc else None,
    }


def _first_capacity(
    snapshot: AnalysisSnapshot,
    point_keys: list[str],
    *,
    duration_start_utc: datetime | None = None,
    duration_end_utc: datetime | None = None,
) -> dict | None:
    for row in snapshot.capacity_context:
        if _contains_any(row, point_keys) and _row_matches_duration(
            row,
            duration_start_utc=duration_start_utc,
            duration_end_utc=duration_end_utc,
            start_fields=("valid_from_utc", "period_start_utc"),
            end_fields=("valid_to_utc", "period_end_utc"),
        ):
            return row
    return None


def _capacity_usage(
    snapshot: AnalysisSnapshot,
    point_keys: list[str],
    *,
    duration_start_utc: datetime | None = None,
    duration_end_utc: datetime | None = None,
) -> dict | None:
    matching_rows = [
        row
        for row in snapshot.flow_observations
        if _contains_any(row, point_keys)
        and _row_matches_duration(
            row,
            duration_start_utc=duration_start_utc,
            duration_end_utc=duration_end_utc,
            start_fields=("period_start_utc",),
            end_fields=("period_end_utc",),
        )
    ]
    if not matching_rows:
        return None

    capacity = _first_capacity(
        snapshot,
        point_keys,
        duration_start_utc=duration_start_utc,
        duration_end_utc=duration_end_utc,
    ) or {}
    capacity_mwh = capacity.get("capacity_mwh_per_day")
    capacity_mcm = capacity.get("capacity_mcm_d")
    converted_rows: list[dict] = []
    conversion_assumptions: list[str] = []
    for row in matching_rows:
        flow_mwh = row.get("flow_mwh_per_day")
        flow_mcm = row.get("flow_mcm_d")
        conversion_assumption = None
        if flow_mwh is None and flow_mcm is not None and capacity_mwh is not None:
            flow_mwh = round(float(flow_mcm) * 10550, 4)
            conversion_assumption = (
                "1 mcm = 10,550 MWh; replace with CV-specific conversion in production."
            )
            conversion_assumptions.append(conversion_assumption)
        converted_rows.append(
            {
                **row,
                "flow_mwh_per_day": flow_mwh,
                "flow_mcm_d": flow_mcm,
                "conversion_assumption": conversion_assumption,
            }
        )

    used_mwh_values = [
        float(row["flow_mwh_per_day"])
        for row in converted_rows
        if row.get("flow_mwh_per_day") is not None
    ]
    used_mcm_values = [
        float(row["flow_mcm_d"]) for row in converted_rows if row.get("flow_mcm_d") is not None
    ]
    average_mwh = round(sum(used_mwh_values) / len(used_mwh_values), 4) if used_mwh_values else None
    average_mcm = round(sum(used_mcm_values) / len(used_mcm_values), 4) if used_mcm_values else None
    peak_mwh = round(max(used_mwh_values), 4) if used_mwh_values else None
    peak_mcm = round(max(used_mcm_values), 4) if used_mcm_values else None
    capacity_value = capacity_mwh or capacity_mcm
    used_value = average_mwh if average_mwh is not None else average_mcm
    usage_pct = (
        round(float(used_value) / float(capacity_value) * 100, 2)
        if capacity_value and used_value
        else None
    )
    peak_used_value = peak_mwh if peak_mwh is not None else peak_mcm
    peak_usage_pct = (
        round(float(peak_used_value) / float(capacity_value) * 100, 2)
        if capacity_value and peak_used_value
        else None
    )
    period_starts = [
        parsed
        for row in converted_rows
        if (parsed := _parse_datetime(row.get("period_start_utc"))) is not None
    ]
    period_ends = [
        parsed
        for row in converted_rows
        if (parsed := _parse_datetime(row.get("period_end_utc"))) is not None
    ]
    latest_row = max(
        converted_rows,
        key=lambda row: _parse_datetime(row.get("period_end_utc"))
        or datetime.min.replace(tzinfo=UTC),
    )
    return {
        "period_start_utc": min(period_starts).isoformat() if period_starts else None,
        "period_end_utc": max(period_ends).isoformat() if period_ends else None,
        "used": used_value,
        "capacity": capacity_value,
        "used_mwh_per_day": average_mwh,
        "capacity_mwh_per_day": capacity_mwh,
        "used_mcm_d": average_mcm,
        "capacity_mcm_d": capacity_mcm,
        "peak_used_mwh_per_day": peak_mwh,
        "peak_used_mcm_d": peak_mcm,
        "usage_pct": usage_pct,
        "peak_usage_pct": peak_usage_pct,
        "observations_count": len(converted_rows),
        "direction": latest_row.get("direction"),
        "unit": "MWh/d" if capacity_mwh or average_mwh else "mcm/d",
        "source_reference": latest_row.get("source_reference"),
        "source_references": _unique(
            [
                str(row.get("source_reference"))
                for row in converted_rows
                if row.get("source_reference")
            ]
        ),
        "conversion_assumption": conversion_assumptions[0] if conversion_assumptions else None,
    }


def _related_prices(
    snapshot: AnalysisSnapshot,
    keys: list[str],
    *,
    duration_start_utc: datetime | None = None,
    duration_end_utc: datetime | None = None,
) -> list[dict]:
    normalized = [key.lower() for key in keys]
    prices: list[dict] = []
    for row in snapshot.market_observations:
        if _contains_any(
            row,
            normalized,
            fields=("market_venue", "product", "price_name", "source_system", "source_reference"),
        ) and _row_matches_duration(
            row,
            duration_start_utc=duration_start_utc,
            duration_end_utc=duration_end_utc,
            start_fields=("period_start_utc", "observed_at_utc"),
            end_fields=("period_end_utc", "observed_at_utc"),
        ):
            prices.append(row)
    return prices[:10]


def _related_live_marks(
    snapshot: AnalysisSnapshot,
    keys: list[str],
    *,
    duration_start_utc: datetime | None = None,
    duration_end_utc: datetime | None = None,
) -> list[dict]:
    marks: list[dict] = []
    for row in snapshot.live_market_marks:
        if _contains_any(
            row,
            keys,
            fields=("venue", "hub", "product", "source_system", "source_reference"),
        ) and _row_matches_duration(
            row,
            duration_start_utc=duration_start_utc,
            duration_end_utc=duration_end_utc,
            start_fields=("mark_time_utc",),
            end_fields=("mark_time_utc",),
        ):
            marks.append(row)
    return marks[:10]


def _related_routes(snapshot: AnalysisSnapshot, keys: list[str]) -> list[dict]:
    routes: list[dict] = []
    for row in snapshot.route_candidates:
        if _contains_any(row, keys):
            routes.append(row)
    return routes[:10]


def _related_contracts(snapshot: AnalysisSnapshot, keys: list[str]) -> list[dict]:
    contracts: list[dict] = []
    for row in snapshot.portfolio_context:
        if _contains_any(row, keys):
            contracts.append(row)
    return contracts[:10]


def _matched_entities(
    snapshot: AnalysisSnapshot,
    *,
    point_keys: list[str],
    price_keys: list[str],
    route_keys: list[str],
    contract_keys: list[str],
) -> list[dict]:
    entities: list[dict] = []
    for row in snapshot.glossary_terms:
        if _contains_any(
            row,
            [*point_keys, *price_keys],
            fields=("term", "term_id", "category", "definition_en", "aliases", "related_terms"),
        ):
            entities.append(
                _entity_payload(
                    "glossary_term",
                    str(row.get("term") or row.get("term_id")),
                    row,
                    category=row.get("category"),
                )
            )
    for row in snapshot.capacity_context:
        if _contains_any(row, point_keys, fields=("point_name", "direction", "source_reference")):
            entities.append(
                _entity_payload(
                    "capacity_point",
                    str(row.get("point_name")),
                    row,
                    direction=row.get("direction"),
                )
            )
    for row in snapshot.flow_observations:
        if _contains_any(row, point_keys, fields=("point_name", "direction", "source_reference")):
            entities.append(
                _entity_payload(
                    "flow_point",
                    str(row.get("point_name")),
                    row,
                    direction=row.get("direction"),
                )
            )
    for row in snapshot.market_observations:
        if _contains_any(
            row,
            price_keys,
            fields=("market_venue", "product", "source_system", "source_reference"),
        ):
            entities.append(
                _entity_payload(
                    "market_price",
                    f"{row.get('market_venue')} {row.get('product')}".strip(),
                    row,
                )
            )
    for row in snapshot.live_market_marks:
        if _contains_any(
            row,
            price_keys,
            fields=("venue", "hub", "product", "source_system", "source_reference"),
        ):
            entities.append(
                _entity_payload(
                    "live_market_mark",
                    f"{row.get('venue')} {row.get('hub')} {row.get('product')}".strip(),
                    row,
                )
            )
    for row in snapshot.route_candidates:
        if _contains_any(row, route_keys):
            entities.append(
                _entity_payload(
                    "route_candidate",
                    str(row.get("route_name") or row.get("route_id")),
                    row,
                )
            )
    for row in snapshot.portfolio_context:
        if _contains_any(row, contract_keys):
            entities.append(
                _entity_payload(
                    "upstream_contract",
                    str(row.get("contract_name") or row.get("contract_id")),
                    row,
                )
            )
    return _unique_entities(entities)[:30]


def _entity_payload(
    entity_type: str,
    label: str,
    row: dict,
    **extra: object,
) -> dict:
    return {
        "entity_type": entity_type,
        "label": label,
        "source_reference": row.get("source_reference")
        or row.get("source_system")
        or row.get("source_refs"),
        **{key: value for key, value in extra.items() if value is not None},
    }


def _unique_entities(entities: list[dict]) -> list[dict]:
    unique: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for entity in entities:
        key = (str(entity.get("entity_type")), str(entity.get("label")).lower())
        if key in seen:
            continue
        seen.add(key)
        unique.append(entity)
    return unique


def _sources_from_matched_entities(
    matched_entities: list[dict],
    snapshot: AnalysisSnapshot,
) -> list[str]:
    sources = [
        str(entity.get("source_reference"))
        for entity in matched_entities
        if entity.get("source_reference")
    ]
    return _unique(sources) or _snapshot_citations(snapshot)


def _entity_summary(
    *,
    term: str,
    profile: dict,
    capacity: dict | None,
    capacity_usage: dict | None,
    prices: list[dict],
    live_marks: list[dict],
    routes: list[dict],
    contracts: list[dict],
    matched_entities: list[dict],
) -> dict:
    return {
        "term": term,
        "context_type": profile["context_type"],
        "has_capacity": capacity is not None,
        "has_capacity_usage": capacity_usage is not None,
        "price_count": len(prices),
        "live_mark_count": len(live_marks),
        "route_count": len(routes),
        "contract_count": len(contracts),
        "matched_entity_count": len(matched_entities),
        "matched_entity_types": _unique(
            [str(entity.get("entity_type")) for entity in matched_entities]
        ),
        "primary_sources": profile["related_sources"],
    }


def _context_metrics(
    capacity: dict | None,
    capacity_usage: dict | None,
    prices: list[dict],
    live_marks: list[dict],
    contracts: list[dict],
) -> list[dict]:
    metrics: list[dict] = []
    if capacity:
        value = capacity.get("capacity_mwh_per_day") or capacity.get("capacity_mcm_d")
        metrics.append(
            {
                "metric_id": "capacity",
                "label": "Capacity",
                "value": value,
                "unit": "MWh/d" if capacity.get("capacity_mwh_per_day") else "mcm/d",
                "source_reference": capacity.get("source_reference"),
            }
        )
    if capacity_usage:
        metrics.extend(
            [
                {
                    "metric_id": "capacity_used",
                    "label": "Capacity in use",
                    "value": capacity_usage.get("used"),
                    "unit": capacity_usage.get("unit"),
                    "source_reference": capacity_usage.get("source_reference"),
                },
                {
                    "metric_id": "capacity_usage_pct",
                    "label": "Capacity utilization",
                    "value": capacity_usage.get("usage_pct"),
                    "unit": "%",
                    "source_reference": capacity_usage.get("source_reference"),
                },
            ]
        )
    for index, price in enumerate(prices[:4]):
        metrics.append(
            {
                "metric_id": f"price_{index}",
                "label": (
                    f"{price.get('market_venue', price.get('source_system', 'Price'))} "
                    f"{price.get('product', '')}"
                ).strip(),
                "value": price.get("price"),
                "unit": price.get("unit") or price.get("currency"),
                "source_reference": price.get("source_reference"),
            }
        )
    for index, mark in enumerate(live_marks[:3]):
        metrics.append(
            {
                "metric_id": f"live_mark_{index}",
                "label": f"{mark.get('venue', 'Live mark')} {mark.get('product', '')}".strip(),
                "value": (
                    mark.get("last_gbp_mwh")
                    or mark.get("bid_gbp_mwh")
                    or mark.get("ask_gbp_mwh")
                ),
                "unit": "GBP/MWh",
                "source_reference": mark.get("source_reference"),
            }
        )
    if contracts:
        metrics.append(
            {
                "metric_id": "linked_contracts",
                "label": "Linked contracts",
                "value": len(contracts),
                "unit": "count",
                "source_reference": "runtime-postgresql" if contracts else None,
            }
        )
    return metrics


def _context_data_quality(
    snapshot: AnalysisSnapshot,
    prices: list[dict],
    live_marks: list[dict],
    capacity: dict | None,
    capacity_usage: dict | None,
    matched_entities: list[dict],
) -> dict:
    return {
        "snapshot_id": snapshot.snapshot_id,
        "snapshot_source": snapshot.source,
        "runtime_db": snapshot.source == "runtime-postgresql",
        "market_observation_count": len(prices),
        "live_mark_count": len(live_marks),
        "has_capacity": capacity is not None,
        "has_capacity_usage": capacity_usage is not None,
        "matched_entity_count": len(matched_entities),
        "warning_count": len(snapshot.warnings),
    }


def _context_sections(
    *,
    entity_summary: dict,
    capacity: dict | None,
    capacity_usage: dict | None,
    metrics: list[dict],
    prices: list[dict],
    live_marks: list[dict],
    routes: list[dict],
    contracts: list[dict],
    data_quality: dict,
    warnings: list[str],
) -> list[dict]:
    return [
        {
            "section_id": "overview",
            "title": "Overview",
            "items": [entity_summary],
            "warnings": [],
        },
        {
            "section_id": "capacity",
            "title": "Capacity and utilization",
            "items": [item for item in [capacity, capacity_usage] if item],
            "metrics": [
                metric
                for metric in metrics
                if str(metric.get("metric_id", "")).startswith("capacity")
            ],
            "warnings": [
                warning
                for warning in warnings
                if warning in {"CAPACITY_CONTEXT_MISSING", "CAPACITY_USAGE_CONTEXT_MISSING"}
            ],
        },
        {
            "section_id": "prices",
            "title": "Prices and live marks",
            "items": [*prices, *live_marks],
            "metrics": [
                metric
                for metric in metrics
                if str(metric.get("metric_id", "")).startswith(("price", "live_mark"))
            ],
            "warnings": [warning for warning in warnings if warning == "PRICE_CONTEXT_MISSING"],
        },
        {
            "section_id": "routes",
            "title": "Route options",
            "items": routes,
            "warnings": [],
        },
        {
            "section_id": "contracts",
            "title": "Linked contracts",
            "items": contracts,
            "metrics": [
                metric for metric in metrics if metric.get("metric_id") == "linked_contracts"
            ],
            "warnings": [],
        },
        {
            "section_id": "data_quality",
            "title": "Data quality",
            "items": [data_quality],
            "warnings": _unique(warnings),
        },
    ]


def _context_warnings(snapshot: AnalysisSnapshot) -> list[str]:
    warnings = list(snapshot.warnings)
    if snapshot.source != "runtime-postgresql":
        warnings.append("RUNTIME_DB_CONTEXT_NOT_AVAILABLE")
    return _unique(warnings)


def _contains_any(
    row: dict,
    keys: list[str],
    *,
    fields: tuple[str, ...] | None = None,
) -> bool:
    normalized = [key.lower() for key in keys if key]
    if not normalized:
        return False
    values = [row.get(field, "") for field in fields] if fields else row.values()
    haystack = " ".join(str(value) for value in values).lower()
    return any(key in haystack for key in normalized)


def _row_matches_duration(
    row: dict,
    *,
    duration_start_utc: datetime | None,
    duration_end_utc: datetime | None,
    start_fields: tuple[str, ...],
    end_fields: tuple[str, ...],
) -> bool:
    if duration_start_utc is None and duration_end_utc is None:
        return True
    row_start = _first_datetime(row, start_fields)
    row_end = _first_datetime(row, end_fields) or row_start
    if duration_start_utc and row_end and row_end < duration_start_utc:
        return False
    if duration_end_utc and row_start and row_start > duration_end_utc:
        return False
    return True


def _first_datetime(row: dict, fields: tuple[str, ...]) -> datetime | None:
    for field in fields:
        parsed = _parse_datetime(row.get(field))
        if parsed is not None:
            return parsed
    return None


def _parse_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))
