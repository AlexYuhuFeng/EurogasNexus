"""SDK client for /api/v1/glossary."""

import httpx
from pydantic import BaseModel


class GlossaryTerm(BaseModel):
    term: str
    definition: str


def fetch_glossary(base_url: str, *, lang: str = "en") -> list[GlossaryTerm]:
    r = httpx.get(f"{base_url}/api/v1/glossary", params={"lang": lang}, timeout=10)
    r.raise_for_status()
    return [GlossaryTerm(**t) for t in r.json()["data"]]

def fetch_term(base_url: str, term: str, *, lang: str = "en") -> GlossaryTerm:
    r = httpx.get(f"{base_url}/api/v1/glossary/{term}", params={"lang": lang}, timeout=10)
    r.raise_for_status()
    return GlossaryTerm(**r.json()["data"])
