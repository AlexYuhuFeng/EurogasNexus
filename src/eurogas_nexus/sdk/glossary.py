"""SDK client for /api/glossary."""

import httpx
from pydantic import BaseModel, Field


class GlossaryTerm(BaseModel):
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
    params = {"lang": lang}
    if category:
        params["category"] = category
    if q:
        params["q"] = q
    r = httpx.get(f"{base_url}/api/glossary", params=params, timeout=10)
    r.raise_for_status()
    return [GlossaryTerm(**t) for t in r.json()["data"]]


def fetch_term(base_url: str, term: str, *, lang: str = "en") -> GlossaryTerm:
    r = httpx.get(f"{base_url}/api/glossary/{term}", params={"lang": lang}, timeout=10)
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
    params = {
        "lang": lang,
        "duration_start_utc": duration_start_utc,
        "duration_end_utc": duration_end_utc,
    }
    r = httpx.get(
        f"{base_url}/api/glossary/{term}/context",
        params={key: value for key, value in params.items() if value},
        timeout=10,
    )
    r.raise_for_status()
    return GlossaryContext(**r.json()["data"])
