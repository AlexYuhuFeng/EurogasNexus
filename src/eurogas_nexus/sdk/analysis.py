"""SDK client for governed analysis, reporting, and glossary context APIs."""

from __future__ import annotations

from pydantic import BaseModel, Field

from eurogas_nexus.sdk import _http


class ReportSection(BaseModel):
    """One titled section of a generated report.

    Attributes:
        section_id: Unique identifier of the section.
        title: Section heading.
        content: Rendered section content.
        citations: References backing the section content.
        warnings: Non-blocking warnings raised while building the section.
    """

    section_id: str
    title: str
    content: str
    citations: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class AnalysisResult(BaseModel):
    """Structured answer from a governed analysis provider.

    Attributes:
        analysis_id: Unique identifier of the analysis.
        task: The analysis task that was executed.
        provider_id: Identifier of the provider that answered.
        provider_status: Provider-side status of the answer.
        answer_en: Answer rendered in English.
        answer_zh_cn: Answer rendered in Simplified Chinese.
        citations: References backing the answer.
        sections: Optional structured report sections.
        missing_inputs: Inputs that were missing during analysis.
        warnings: Non-blocking warnings about the analysis.
        snapshot_id: Identifier of the data snapshot the analysis used.
        created_at_utc: Creation time of the analysis (ISO 8601).
        research_only: Whether the answer is restricted to research use.
        human_review_required: Whether the answer needs human review.
    """

    analysis_id: str
    task: str
    provider_id: str
    provider_status: str
    answer_en: str
    answer_zh_cn: str
    citations: list[str] = Field(default_factory=list)
    sections: list[ReportSection] = Field(default_factory=list)
    missing_inputs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    snapshot_id: str
    created_at_utc: str
    research_only: bool
    human_review_required: bool


class GlossaryContext(BaseModel):
    """Context enrichment for one glossary term.

    Attributes:
        term: The glossary term that was resolved.
        context_type: Kind of context produced (e.g., term, entity, capacity).
        description: Context description in the requested language.
        description_en: Description in English; None when not produced.
        description_zh_cn: Description in Simplified Chinese; None when not
            produced.
        requested_duration: The duration window echoed back; None when not
            requested.
        entity_summary: Summary of matched entities; None when not applicable.
        matched_entities: Entities matched for the term.
        capacity: Capacity context; None when not applicable.
        capacity_usage: Capacity usage context; None when not applicable.
        metrics: Relevant metrics for the term.
        related_prices: Related market prices.
        related_routes: Related transport routes.
        related_contracts: Related contracts.
        live_market_marks: Live market marks used as context.
        context_sections: Structured context sections.
        related_sources: References to related sources.
        data_quality: Data quality assessment for the context.
        warnings: Non-blocking warnings about the context.
        research_only: Whether the context is restricted to research use.
        human_review_required: Whether the context needs human review.
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
    research_only: bool
    human_review_required: bool


def fetch_business_ontology(base_url: str) -> dict:
    """Fetch the governed business ontology used to interpret analysis input.

    Args:
        base_url: Operator-provided server root URL.

    Returns:
        The ontology document as a raw dictionary.

    Raises:
        httpx.HTTPStatusError: If the backend responds with a non-2xx status.
    """
    response = _http.get(f"{base_url}/api/analysis/ontology", timeout=10)
    response.raise_for_status()
    return response.json()["data"]


def ask_analysis(base_url: str, **kwargs) -> AnalysisResult:
    """Ask a governed analysis question and return the structured answer.

    Args:
        base_url: Operator-provided server root URL.
        **kwargs: Analysis options forwarded verbatim to the backend
            (e.g., question text, language, scope filters).

    Returns:
        The validated analysis result with answer, citations, and warnings.

    Raises:
        httpx.HTTPStatusError: If the backend responds with a non-2xx status.
    """
    # 分析选项以 **kwargs 原样透传：参数契约由服务端演进，客户端无需随
    # 每个新增分析选项发版；LLM 分析是慢路径，超时放宽到 30s。
    response = _http.post(f"{base_url}/api/analysis/query", json=kwargs, timeout=30)
    response.raise_for_status()
    return AnalysisResult(**response.json()["data"])


def generate_portfolio_report(base_url: str, **kwargs) -> AnalysisResult:
    """Generate a governed portfolio report and return its sections.

    Args:
        base_url: Operator-provided server root URL.
        **kwargs: Report options forwarded verbatim to the backend.

    Returns:
        The validated report result; ``sections`` holds the rendered report.

    Raises:
        httpx.HTTPStatusError: If the backend responds with a non-2xx status.
    """
    response = _http.post(f"{base_url}/api/reports/portfolio", json=kwargs, timeout=30)
    response.raise_for_status()
    return AnalysisResult(**response.json()["data"])


def fetch_glossary_context(
    base_url: str,
    term: str,
    *,
    lang: str = "en",
    duration_start_utc: str | None = None,
    duration_end_utc: str | None = None,
) -> GlossaryContext:
    """Fetch a term's glossary context enriched with live market data.

    Args:
        base_url: Operator-provided server root URL.
        term: Glossary term to resolve.
        lang: Response language code (``en`` or ``zh-CN``).
        duration_start_utc: Start of the context window (ISO 8601); omitted
            to use the backend default.
        duration_end_utc: End of the context window (ISO 8601); omitted to
            use the backend default.

    Returns:
        The validated glossary context for the term.

    Raises:
        httpx.HTTPStatusError: If the backend responds with a non-2xx status.
    """
    params = {
        "lang": lang,
        "duration_start_utc": duration_start_utc,
        "duration_end_utc": duration_end_utc,
    }
    # 过滤掉未提供的可选参数：显式 null/空串会覆盖服务端默认（如默认时段），
    # 缺省发送反而让服务端按自己的默认行为处理。
    response = _http.get(
        f"{base_url}/api/glossary/{term}/context",
        params={key: value for key, value in params.items() if value},
        timeout=10,
    )
    response.raise_for_status()
    return GlossaryContext(**response.json()["data"])
