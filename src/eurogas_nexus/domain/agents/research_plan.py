"""Structured ResearchPlan and semantic plan validation (CR-15)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

PLAN_SCHEMA_VERSION = "research-plan/v1"


class EvidenceRequirement(BaseModel):
    series_id: str = Field(min_length=1, max_length=160)
    required: bool = True
    max_source_age_seconds: int | None = Field(default=None, ge=0)
    temporal_integrity_min: str = "TEMPORAL_APPROXIMATE"
    unit: str | None = None


class AnalysisRequirement(BaseModel):
    analysis_id: str = Field(pattern=r"^[a-z][a-z0-9._-]{2,95}$")
    analysis_type: str
    input_series: list[str] = Field(default_factory=list)
    parameters: dict[str, Any] = Field(default_factory=dict)


class ResearchPlan(BaseModel):
    research_plan_id: str = Field(pattern=r"^plan-[A-Za-z0-9._-]{4,120}$")
    objective: str = Field(min_length=8, max_length=4000)
    question: str = Field(min_length=8, max_length=4000)
    market_scope: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    product: str = "DAY_AHEAD"
    horizon: str = "D1"
    hypotheses_to_test: list[str] = Field(default_factory=list)
    required_evidence: list[EvidenceRequirement] = Field(default_factory=list)
    analyses: list[AnalysisRequirement] = Field(default_factory=list)
    data_quality_requirements: dict[str, Any] = Field(default_factory=dict)
    statistical_requirements: dict[str, Any] = Field(default_factory=dict)
    strategy_generation_allowed: bool = False
    stopping_conditions: list[str] = Field(default_factory=list)
    created_by: str = "agent"
    agent_run_id: str | None = None
    schema_version: str = PLAN_SCHEMA_VERSION
    created_at_utc: datetime = Field(default_factory=lambda: datetime.now(UTC))


class PlanValidationIssue(BaseModel):
    code: str
    detail: str
    evidence: str | None = None


class PlanValidationResult(BaseModel):
    plan_id: str
    ok: bool
    issues: list[PlanValidationIssue] = Field(default_factory=list)
    supported_analyses: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)

    def add(self, code: str, detail: str, evidence: str | None = None) -> None:
        self.issues.append(PlanValidationIssue(code=code, detail=detail, evidence=evidence))
        self.blockers.append(code)
        self.ok = False


_SUPPORTED_ANALYSIS_TYPES = frozenset(
    {
        "distribution",
        "rolling_volatility",
        "correlation",
        "cross_correlation",
        "seasonality",
        "zscore",
        "event_study",
        "regime_summary",
        "spread_distribution",
    }
)

_KNOWN_ENTITY_TYPES = frozenset(
    {
        "market_hub",
        "market_area",
        "interconnector",
        "network_node",
        "storage_facility",
        "lng_terminal",
        "resource",
        "route",
    }
)


def validate_research_plan(
    plan: ResearchPlan,
    *,
    known_entities: set[str] | None = None,
    available_series: dict[str, dict[str, Any]] | None = None,
    min_history_days: int = 14,
    entitled_source_families: set[str] | None = None,
) -> PlanValidationResult:
    """Validate a plan against semantic, data, and entitlement facts.

    This function is deterministic and never invents substitutes.
    """

    result = PlanValidationResult(plan_id=plan.research_plan_id, ok=True)
    entities = known_entities if known_entities is not None else set()
    series = available_series if available_series is not None else {}
    entitled = entitled_source_families if entitled_source_families is not None else set()

    if not plan.question.strip() or len(plan.question.strip()) < 8:
        result.add("INVALID_ANALYSIS", "research question is too short")
    for entity in plan.entities:
        if entity not in entities:
            result.add(
                "ENTITY_NOT_FOUND",
                f"entity {entity!r} is not in the known entity set",
                entity,
            )
    if plan.horizon and not _valid_horizon(plan.horizon):
        result.add("HORIZON_INVALID", f"horizon {plan.horizon!r} is not Dn/Hn")
    for analysis in plan.analyses:
        if analysis.analysis_type not in _SUPPORTED_ANALYSIS_TYPES:
            result.add(
                "INVALID_ANALYSIS",
                f"unsupported analysis type {analysis.analysis_type!r}",
                analysis.analysis_id,
            )
            continue
        result.supported_analyses.append(analysis.analysis_id)
        if not analysis.input_series:
            result.add(
                "DATA_MISSING",
                f"analysis {analysis.analysis_id!r} has no input series",
                analysis.analysis_id,
            )
        for series_id in analysis.input_series:
            metadata = series.get(series_id)
            if metadata is None:
                result.add(
                    "SERIES_UNAVAILABLE",
                    f"series {series_id!r} is unavailable",
                    series_id,
                )
                continue
            family = str(metadata.get("source_family") or "")
            if (
                family
                and entitled
                and "*" not in entitled
                and family not in entitled
                and family.removesuffix("_Sim") not in entitled
            ):
                result.add(
                    "ENTITLEMENT_MISSING",
                    f"series {series_id!r} source family {family!r} is not entitled",
                    series_id,
                )
            if int(metadata.get("history_days") or 0) < min_history_days:
                result.add(
                    "INSUFFICIENT_HISTORY",
                    f"series {series_id!r} has less than {min_history_days} days",
                    series_id,
                )
            integrity = str(metadata.get("temporal_integrity") or "")
            if integrity == "TEMPORAL_INSUFFICIENT":
                result.add(
                    "TEMPORAL_PROVENANCE_INSUFFICIENT",
                    f"series {series_id!r} has insufficient temporal provenance",
                    series_id,
                )
    for requirement in plan.required_evidence:
        if requirement.series_id not in series and requirement.required:
            result.add(
                "SERIES_UNAVAILABLE",
                f"required evidence series {requirement.series_id!r} is unavailable",
                requirement.series_id,
            )
    return result


def _valid_horizon(value: str) -> bool:
    import re

    return bool(re.fullmatch(r"[HhDd][0-9]{1,3}", value.strip()))


def deterministic_plan(objective: str, *, agent_run_id: str | None = None) -> ResearchPlan:
    """Draft a conservative plan without any LLM call.

    Used as the offline/deterministic fallback and as the base for provider
    drafting. It never invents market values; it only names required evidence.
    """

    text = (objective or "").strip()
    entities = ["ent:market_hub:NBP", "ent:market_hub:TTF"]
    product = "DAY_AHEAD"
    if "within-day" in text.casefold() or "intraday" in text.casefold():
        product = "WITHIN_DAY"
    evidence = [
        EvidenceRequirement(series_id="market.price.NBP.DAY_AHEAD", unit="EUR/MWh"),
        EvidenceRequirement(series_id="market.price.TTF.DAY_AHEAD", unit="EUR/MWh"),
        EvidenceRequirement(series_id="market.fx.EUR.GBP", unit="GBP/EUR"),
    ]
    analyses = [
        AnalysisRequirement(
            analysis_id="spread-distribution",
            analysis_type="spread_distribution",
            input_series=[
                "market.price.NBP.DAY_AHEAD",
                "market.price.TTF.DAY_AHEAD",
            ],
        ),
        AnalysisRequirement(
            analysis_id="rolling-volatility",
            analysis_type="rolling_volatility",
            input_series=["market.price.NBP.DAY_AHEAD"],
            parameters={"window": 21},
        ),
    ]
    return ResearchPlan(
        research_plan_id=(
            f"plan-{_short_hash((text or 'research') + '|' + (agent_run_id or 'no-run'))}"
        ),
        objective=text or "Untitled research objective",
        question=text or "What is the evidence for the requested research objective?",
        market_scope=["NBP", "TTF"],
        entities=entities,
        product=product,
        hypotheses_to_test=[
            "Observed spread behavior is consistent with the stated objective."
        ],
        required_evidence=evidence,
        analyses=analyses,
        data_quality_requirements={"minimum_coverage": 0.5, "strict_temporal": False},
        statistical_requirements={"minimum_observations": 30},
        strategy_generation_allowed=False,
        stopping_conditions=["BLOCKER: data requirement cannot be satisfied"],
        created_by="deterministic-planner",
        agent_run_id=agent_run_id,
    )


def _short_hash(value: str) -> str:
    import hashlib

    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
