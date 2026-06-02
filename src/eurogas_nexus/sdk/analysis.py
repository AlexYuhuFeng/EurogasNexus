"""SDK client for governed analysis, reporting, and glossary context APIs."""

from __future__ import annotations

import httpx
from pydantic import BaseModel, Field


class ReportSection(BaseModel):
    section_id: str
    title: str
    content: str
    citations: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class AnalysisResult(BaseModel):
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
    response = httpx.get(f"{base_url}/api/v1/analysis/ontology", timeout=10)
    response.raise_for_status()
    return response.json()["data"]


def ask_analysis(base_url: str, **kwargs) -> AnalysisResult:
    response = httpx.post(f"{base_url}/api/v1/analysis/query", json=kwargs, timeout=30)
    response.raise_for_status()
    return AnalysisResult(**response.json()["data"])


def generate_portfolio_report(base_url: str, **kwargs) -> AnalysisResult:
    response = httpx.post(f"{base_url}/api/v1/reports/portfolio", json=kwargs, timeout=30)
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
    params = {
        "lang": lang,
        "duration_start_utc": duration_start_utc,
        "duration_end_utc": duration_end_utc,
    }
    response = httpx.get(
        f"{base_url}/api/v1/glossary/{term}/context",
        params={key: value for key, value in params.items() if value},
        timeout=10,
    )
    response.raise_for_status()
    return GlossaryContext(**response.json()["data"])
