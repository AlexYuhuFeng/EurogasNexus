"""Research workflow result models — all research-only, no execution semantics."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

# --- Shared result envelope --------------------------------------------------


@dataclass(frozen=True)
class ResearchResult:
    """Base research result with required metadata fields."""

    research_only: bool = True
    human_review_required: bool = True
    assumptions: list[str] = field(default_factory=list)
    missing_inputs: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    source_references: list[str] = field(default_factory=list)
    lineage: list[str] = field(default_factory=list)
    generated_at_utc: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )


# --- Route cost --------------------------------------------------------------


class CostComponentType(StrEnum):
    TARIFF = "tariff"
    FUEL = "fuel"
    TRANSPORT = "transport"
    REGAS = "regas"
    STORAGE = "storage"
    FX = "fx"
    OTHER = "other"


@dataclass(frozen=True)
class CostComponent(ResearchResult):
    component_id: str = ""
    component_type: CostComponentType = CostComponentType.OTHER
    amount: float = 0.0
    unit: str = "EUR/MWh"
    currency: str = "EUR"
    description: str = ""


@dataclass(frozen=True)
class RouteCostResult(ResearchResult):
    result_id: str = ""
    route_name: str = ""
    from_node_id: str = ""
    to_node_id: str = ""
    total_cost_eur_mwh: float = 0.0
    total_cost_boe: float = 0.0
    cost_components: list[CostComponent] = field(default_factory=list)
    route_km: float | None = None


# --- Indicative netback ------------------------------------------------------


@dataclass(frozen=True)
class IndicativeNetbackResult(ResearchResult):
    result_id: str = ""
    route_name: str = ""
    from_market: str = ""
    to_market: str = ""
    market_price_eur_mwh: float = 0.0
    route_cost_eur_mwh: float = 0.0
    netback_eur_mwh: float = 0.0
    fx_rate: float = 1.0
    unit_conversions_applied: list[str] = field(default_factory=list)


# --- Feasibility -------------------------------------------------------------


class FeasibilityStatus(StrEnum):
    FEASIBLE = "feasible"
    INFEASIBLE = "infeasible"
    CONDITIONAL = "conditional"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class FeasibilityResult(ResearchResult):
    result_id: str = ""
    route_name: str = ""
    status: FeasibilityStatus = FeasibilityStatus.UNKNOWN
    blockers: list[str] = field(default_factory=list)
    conditions: list[str] = field(default_factory=list)


# --- Allocation scenario -----------------------------------------------------


@dataclass(frozen=True)
class AllocationCandidate(ResearchResult):
    candidate_id: str = ""
    route_name: str = ""
    allocated_volume_boe_d: float = 0.0
    price_eur_mwh: float = 0.0
    rank: int = 0


@dataclass(frozen=True)
class AllocationScenarioResult(ResearchResult):
    result_id: str = ""
    scenario_name: str = ""
    total_demand_boe_d: float = 0.0
    total_allocated_boe_d: float = 0.0
    unallocated_boe_d: float = 0.0
    candidates: list[AllocationCandidate] = field(default_factory=list)


# --- Monitoring and alerts ---------------------------------------------------


class AlertSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass(frozen=True)
class MonitoringAlert(ResearchResult):
    alert_id: str = ""
    alert_type: str = ""
    severity: AlertSeverity = AlertSeverity.INFO
    message: str = ""
    related_entity_id: str = ""
    triggered_at_utc: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )


# --- Weather-adjusted nowcast ------------------------------------------------


@dataclass(frozen=True)
class NowcastResult(ResearchResult):
    result_id: str = ""
    market: str = ""
    period_start_utc: str = ""
    period_end_utc: str = ""
    base_demand_boe_d: float = 0.0
    weather_adjustment_boe_d: float = 0.0
    adjusted_demand_boe_d: float = 0.0
    hdd: float = 0.0
    cdd: float = 0.0


# --- Strategy backtest -------------------------------------------------------


@dataclass(frozen=True)
class BacktestResult(ResearchResult):
    result_id: str = ""
    strategy_name: str = ""
    start_utc: str = ""
    end_utc: str = ""
    total_return_eur: float = 0.0
    sharpe_ratio: float | None = None
    max_drawdown_pct: float | None = None
    trade_count: int = 0
    win_rate_pct: float | None = None


# --- Shadow run (paper evaluation) -------------------------------------------


class ShadowRunStatus(StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"
    PAUSED = "paused"


class CandidateAction(StrEnum):
    RESEARCH_CANDIDATE = "research_candidate"
    CANDIDATE_RANKING = "candidate_ranking"
    RESEARCH_SIGNAL = "research_signal"
    CANDIDATE_ACTION_FOR_REVIEW = "candidate_action_for_review"


@dataclass(frozen=True)
class CandidateRanking(ResearchResult):
    ranking_id: str = ""
    route_name: str = ""
    rank: int = 0
    score: float = 0.0
    action: CandidateAction = CandidateAction.RESEARCH_CANDIDATE


@dataclass(frozen=True)
class ShadowRunResult(ResearchResult):
    result_id: str = ""
    strategy_name: str = ""
    status: ShadowRunStatus = ShadowRunStatus.ACTIVE
    started_at_utc: str = ""
    elapsed_days: int = 0
    paper_pnl_eur: float = 0.0
    signal_count: int = 0
    candidates: list[CandidateRanking] = field(default_factory=list)


# --- LLM-assisted analysis ---------------------------------------------------


@dataclass(frozen=True)
class LlmMarketAnalysis(ResearchResult):
    analysis_id: str = ""
    topic: str = ""
    market_context: str = ""
    analysis_text: str = ""
    citations: list[str] = field(default_factory=list)
    llm_provider: str = ""
    llm_model: str = ""
    prompt_snapshot: str = ""


# --- Research brief ----------------------------------------------------------


@dataclass(frozen=True)
class ResearchBrief(ResearchResult):
    brief_id: str = ""
    title: str = ""
    summary: str = ""
    sections: list[dict] = field(default_factory=list)
    glossary_terms: list[str] = field(default_factory=list)
    author: str = ""
