"""Human-review evidence pack (CR-15)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


class ReviewPack(BaseModel):
    review_pack_id: str
    agent_run_id: str | None = None
    objective: str
    research_plan: dict[str, Any] = Field(default_factory=dict)
    key_findings: list[dict[str, Any]] = Field(default_factory=list)
    strategy_specification: dict[str, Any] | None = None
    backtest: dict[str, Any] | None = None
    robustness: dict[str, Any] = Field(default_factory=dict)
    challenge_report: dict[str, Any] | None = None
    data_provenance: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    known_limitations: list[str] = Field(default_factory=list)
    alternative_hypotheses: list[str] = Field(default_factory=list)
    status: str = "READY_FOR_HUMAN_REVIEW"
    created_at_utc: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def public_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
