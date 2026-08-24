"""Analysis and report data contracts (Pydantic models).

这些模型是 LLM 就绪分析/报告链路的统一数据契约：请求、快照、章节、
结果与术语上下文都通过本模块的类型跨层传递，任何一端都不得改用
裸 dict 绕过校验。模型只携带数据，不含任何逻辑。
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class AnalysisTask(StrEnum):
    """Supported analysis task kinds.

    任务种类决定缺失输入判定与默认章节组装（见 builders 模块）。
    """

    DB_INQUIRY = "DB_INQUIRY"
    GLOSSARY_QA = "GLOSSARY_QA"
    PNL_TRACKING = "PNL_TRACKING"
    TSO_STATUS_REPORT = "TSO_STATUS_REPORT"
    PORTFOLIO_REPORT = "PORTFOLIO_REPORT"
    MARKET_MOVEMENT = "MARKET_MOVEMENT"


class AnalysisRequest(BaseModel):
    """One analysis query request.

    Attributes:
        question: The analyst question (1-4096 chars).
        task: Task kind steering missing-input and section logic.
        provider_id: LLM provider id (``DEEPSEEK`` by default).
        model: Provider model name (only ``deepseek-v4-flash`` is accepted).
        invoke_provider: Whether to call the external provider; False keeps
            the pipeline deterministic-only (no external calls).
        include_contract_prices: Whether contract prices enter the context.
        selected_terms: Glossary terms selected by the client.
        selected_assets: Asset/point selections.
        selected_contracts: Contract selections.
        duration_start_utc: Window start; None = unbounded.
        duration_end_utc: Window end; None = unbounded.
        include_sections: Section ids the client wants.
        language: Output language hint (``en`` or ``zh-CN``).
    """

    question: str = Field(min_length=1, max_length=4096)
    task: AnalysisTask = AnalysisTask.DB_INQUIRY
    provider_id: str = "DEEPSEEK"
    model: Literal["deepseek-v4-flash"] = "deepseek-v4-flash"
    invoke_provider: bool = False
    include_contract_prices: bool = False
    selected_terms: list[str] = Field(default_factory=list)
    selected_assets: list[str] = Field(default_factory=list)
    selected_contracts: list[str] = Field(default_factory=list)
    duration_start_utc: datetime | None = None
    duration_end_utc: datetime | None = None
    include_sections: list[str] = Field(default_factory=list)
    language: str = "en"


class PortfolioReportRequest(BaseModel):
    """Request for a portfolio decision-support report.

    Attributes:
        title: Report title (also the question for the LLM synthesis).
        provider_id: LLM provider id.
        model: Provider model name.
        invoke_provider: Whether to call the external provider.
        include_contract_prices: Whether contract prices enter the context.
        portfolio_id: Portfolio filter, or None for all.
        selected_resources: Resource selections.
        selected_contracts: Contract selections.
        selected_strategies: Strategy selections.
        duration_start_utc: Window start; None = unbounded.
        duration_end_utc: Window end; None = unbounded.
        language: Output language hint.
    """

    title: str = "Portfolio decision-support report"
    provider_id: str = "DEEPSEEK"
    model: Literal["deepseek-v4-flash"] = "deepseek-v4-flash"
    invoke_provider: bool = False
    include_contract_prices: bool = False
    portfolio_id: str | None = None
    selected_resources: list[str] = Field(default_factory=list)
    selected_contracts: list[str] = Field(default_factory=list)
    selected_strategies: list[str] = Field(default_factory=list)
    duration_start_utc: datetime | None = None
    duration_end_utc: datetime | None = None
    language: str = "en"


class AnalysisSnapshot(BaseModel):
    """Immutable backend-data snapshot fed to analysis/context builders.

    Attributes:
        snapshot_id: Stable snapshot id (used in citations).
        source: Source tag (``runtime-postgresql`` when DB-backed).
        created_at_utc: Snapshot creation time.
        ontology: Business ontology summary (see builders.business_logic_ontology).
        glossary_terms: Glossary term rows.
        market_observations: Market price observation rows.
        live_market_marks: Live screen mark rows.
        fx_rates: FX reference rows.
        flow_observations: Physical flow rows.
        capacity_context: Capacity profile rows.
        route_candidates: Route candidate rows.
        strategy_runs: Strategy run rows.
        portfolio_context: Portfolio/contract rows.
        warnings: Snapshot-level warnings carried into every output.
    """

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
    """One titled section of a report with citations and warnings.

    Attributes:
        section_id: Stable section id (e.g. ``portfolio``, ``market``).
        title: Section title.
        content: Section body text.
        citations: Source references backing the section.
        warnings: Section-level warnings.
    """

    section_id: str
    title: str
    content: str
    citations: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class AnalysisResult(BaseModel):
    """Deterministic cited output, optionally enriched by a provider.

    Attributes:
        analysis_id: Stable result id.
        task: Task kind evaluated.
        provider_id: Provider id used (or intended).
        provider_status: ``not_invoked`` / ``success`` / provider error tag.
        answer_en: English answer text.
        answer_zh_cn: Chinese answer text (deterministic).
        citations: Snapshot-derived source references.
        sections: Structured report sections.
        missing_inputs: Inputs absent from the snapshot for this task.
        warnings: Aggregated warnings.
        snapshot_id: Snapshot the result was built from.
        created_at_utc: Result creation time.
        research_only: Always True — decision support only.
        human_review_required: Always True — never auto-acts.
    """

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
    """One glossary term enriched with matching runtime context.

    Attributes:
        term: The queried term (normalized by caller).
        context_type: Inferred context type (hub/venue/price_assessment/
            entry_point/exit_point/capacity/generic).
        description: Localized description (per request language).
        description_en: English description.
        description_zh_cn: Chinese description.
        requested_duration: Normalized duration payload, or None.
        entity_summary: Compact summary of matched context.
        matched_entities: Matched entity rows (deduplicated, capped).
        capacity: First matching capacity row, or None.
        capacity_usage: Aggregated capacity-usage payload, or None.
        metrics: Extracted metric list (capacity/prices/live marks/contracts).
        related_prices: Matching market observation rows (capped).
        related_routes: Matching route candidate rows (capped).
        related_contracts: Matching portfolio/contract rows (capped).
        live_market_marks: Matching live mark rows (capped).
        context_sections: Structured display sections.
        related_sources: Source references for the term context.
        data_quality: Snapshot data-quality summary.
        warnings: Aggregated warnings.
        research_only: Always True.
        human_review_required: Always True.
    """

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
