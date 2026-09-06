"""Structured research findings (CR-15)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


class ResearchFinding(BaseModel):
    """One structured analytical finding with evidence and limitations."""

    finding_id: str
    research_plan_id: str | None = None
    question: str
    statistic: str
    value: float | str | None = None
    unit: str | None = None
    sample: str = ""
    period: str = ""
    methodology: str
    evidence: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    quality_state: str = "VERIFIED"
    created_by: str = "deterministic-analytics"
    created_at_utc: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def public_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def finding_payload_for_analytics(
    *,
    finding_id: str,
    research_plan_id: str,
    question: str,
    statistic: str,
    value: float,
    unit: str,
    sample: str,
    period: str,
    methodology: str,
    evidence: list[str],
    limitations: list[str] | None = None,
) -> ResearchFinding:
    return ResearchFinding(
        finding_id=finding_id,
        research_plan_id=research_plan_id,
        question=question,
        statistic=statistic,
        value=value,
        unit=unit,
        sample=sample,
        period=period,
        methodology=methodology,
        evidence=evidence,
        limitations=limitations or [],
    )
