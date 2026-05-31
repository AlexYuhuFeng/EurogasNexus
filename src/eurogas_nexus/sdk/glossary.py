"""SDK client for /api/v1/glossary."""

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
    r = httpx.get(f"{base_url}/api/v1/glossary", params=params, timeout=10)
    r.raise_for_status()
    return [GlossaryTerm(**t) for t in r.json()["data"]]


def fetch_term(base_url: str, term: str, *, lang: str = "en") -> GlossaryTerm:
    r = httpx.get(f"{base_url}/api/v1/glossary/{term}", params={"lang": lang}, timeout=10)
    r.raise_for_status()
    return GlossaryTerm(**r.json()["data"])
