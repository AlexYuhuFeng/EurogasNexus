"""SDK client for /api/glossary."""

from pydantic import BaseModel, Field

from eurogas_nexus.sdk import _http


class GlossaryTerm(BaseModel):
    """One glossary term with localized definitions and relations.

    Attributes:
        term_id: Unique identifier of the term; None when not assigned.
        term: Canonical term name.
        category: Category the term belongs to; None when uncategorized.
        definition: Definition in the requested language.
        definition_en: Definition in English; None when not available.
        definition_zh_cn: Definition in Simplified Chinese; None when not
            available.
        aliases: Alternative names for the term.
        related_terms: Canonical names of related terms.
        source_refs: References to the sources defining the term.
    """

    term_id: str | None = None
    term: str
    category: str | None = None
    definition: str
    definition_en: str | None = None
    definition_zh_cn: str | None = None
    aliases: list[str] = Field(default_factory=list)
    related_terms: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)


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


def fetch_glossary(
    base_url: str,
    *,
    lang: str = "en",
    category: str | None = None,
    q: str | None = None,
) -> list[GlossaryTerm]:
    """Fetch glossary terms, optionally filtered by category or search text.

    Args:
        base_url: Operator-provided server root URL.
        lang: Language code for localized definitions (``en`` or ``zh-CN``).
        category: Only return terms in this category.
        q: Free-text search applied to term names and definitions.

    Returns:
        List of validated glossary terms.

    Raises:
        httpx.HTTPStatusError: If the backend responds with a non-2xx status.
    """
    params = {"lang": lang}
    if category:
        # 仅当显式提供过滤条件时才下发参数：未过滤时服务端返回全量术语，
        # 与传空过滤值的行为保持一致。
        params["category"] = category
    if q:
        params["q"] = q
    r = _http.get(f"{base_url}/api/glossary", params=params, timeout=10)
    r.raise_for_status()
    return [GlossaryTerm(**t) for t in r.json()["data"]]


def fetch_term(base_url: str, term: str, *, lang: str = "en") -> GlossaryTerm:
    """Fetch a single glossary term by its canonical name.

    Args:
        base_url: Operator-provided server root URL.
        term: Canonical glossary term to look up.
        lang: Language code for localized definitions.

    Returns:
        The validated glossary term.

    Raises:
        httpx.HTTPStatusError: If the backend responds with a non-2xx status.
    """
    r = _http.get(f"{base_url}/api/glossary/{term}", params={"lang": lang}, timeout=10)
    r.raise_for_status()
    return GlossaryTerm(**r.json()["data"])


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
    r = _http.get(
        f"{base_url}/api/glossary/{term}/context",
        params={key: value for key, value in params.items() if value},
        timeout=10,
    )
    r.raise_for_status()
    return GlossaryContext(**r.json()["data"])
