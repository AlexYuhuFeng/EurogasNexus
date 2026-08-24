"""Research workflow result models — all research-only, no execution semantics.

研究工作流的结果模型：全部为 frozen 数据类，继承 ResearchResult 信封
（research_only/human_review_required/assumptions/missing_inputs/warnings/
source_references/lineage），任何结果都不得携带执行语义。
"""

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
    """Cost component kinds accepted by the route-cost workflow."""

    TARIFF = "tariff"
    FUEL = "fuel"
    TRANSPORT = "transport"
    REGAS = "regas"
    STORAGE = "storage"
    FX = "fx"
    OTHER = "other"


@dataclass(frozen=True)
class CostComponent(ResearchResult):
    """One cost component of a route-cost research result.

    Attributes:
        component_id: Stable component id.
        component_type: Cost kind.
        amount: Component amount.
        unit: Unit (e.g. ``EUR/MWh``).
        currency: ISO 4217 code.
        description: Free description.
    """

    component_id: str = ""
    component_type: CostComponentType = CostComponentType.OTHER
    amount: float = 0.0
    unit: str = "EUR/MWh"
    currency: str = "EUR"
    description: str = ""


@dataclass(frozen=True)
class RouteCostResult(ResearchResult):
    """Route-cost research result.

    Attributes:
        result_id: Stable result id.
        route_name: Route display name.
        from_node_id / to_node_id: Route endpoints.
        total_cost_eur_mwh: Total cost per MWh.
        total_cost_boe: Total cost per barrel-equivalent.
        cost_components: Component breakdown.
        route_km: Route length in km, or None.
    """

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
    """Indicative netback research result.

    Attributes:
        result_id: Stable result id.
        route_name: Route display name.
        from_market / to_market: Route markets.
        market_price_eur_mwh: Destination market price.
        route_cost_eur_mwh: Route cost.
        netback_eur_mwh: Computed netback.
        fx_rate: Applied FX multiplier.
        unit_conversions_applied: Conversion notes.
    """

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
    """Feasibility classification of a route scenario."""

    FEASIBLE = "feasible"
    INFEASIBLE = "infeasible"
    CONDITIONAL = "conditional"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class FeasibilityResult(ResearchResult):
    """Feasibility research result.

    Attributes:
        result_id: Stable result id.
        route_name: Route display name.
        status: Feasibility classification.
        blockers: Blocking conditions.
        conditions: Conditional requirements.
    """

    result_id: str = ""
    route_name: str = ""
    status: FeasibilityStatus = FeasibilityStatus.UNKNOWN
    blockers: list[str] = field(default_factory=list)
    conditions: list[str] = field(default_factory=list)


# --- Allocation scenario -----------------------------------------------------


@dataclass(frozen=True)
class AllocationCandidate(ResearchResult):
    """One allocated candidate in an allocation research result.

    Attributes:
        candidate_id: Stable candidate id.
        route_name: Route display name.
        allocated_volume_boe_d: Allocated volume, boe/d.
        price_eur_mwh: Price per MWh.
        rank: Candidate rank.
    """

    candidate_id: str = ""
    route_name: str = ""
    allocated_volume_boe_d: float = 0.0
    price_eur_mwh: float = 0.0
    rank: int = 0


@dataclass(frozen=True)
class AllocationScenarioResult(ResearchResult):
    """Allocation scenario research result.

    Attributes:
        result_id: Stable result id.
        scenario_name: Scenario display name.
        total_demand_boe_d: Total demand, boe/d.
        total_allocated_boe_d: Allocated volume, boe/d.
        unallocated_boe_d: Unallocated volume, boe/d.
        candidates: Allocated candidates.
    """

    result_id: str = ""
    scenario_name: str = ""
    total_demand_boe_d: float = 0.0
    total_allocated_boe_d: float = 0.0
    unallocated_boe_d: float = 0.0
    candidates: list[AllocationCandidate] = field(default_factory=list)


# --- Monitoring and alerts ---------------------------------------------------


class AlertSeverity(StrEnum):
    """Monitoring alert severity levels."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass(frozen=True)
class MonitoringAlert(ResearchResult):
    """One monitoring alert research result.

    Attributes:
        alert_id: Stable alert id.
        alert_type: Alert kind tag.
        severity: Alert severity.
        message: Alert message.
        related_entity_id: Related entity, or empty.
        triggered_at_utc: Trigger time (ISO).
    """

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
    """Weather-adjusted demand nowcast research result.

    Attributes:
        result_id: Stable result id.
        market: Market label.
        period_start_utc / period_end_utc: Forecast window (ISO).
        base_demand_boe_d: Base demand.
        weather_adjustment_boe_d: Weather delta.
        adjusted_demand_boe_d: Final demand.
        hdd / cdd: Weather inputs.
    """

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
    """Strategy backtest research result.

    Attributes:
        result_id: Stable result id.
        strategy_name: Strategy display name.
        start_utc / end_utc: Backtest window (ISO).
        total_return_eur: Total return in EUR.
        sharpe_ratio: Sharpe ratio, or None.
        max_drawdown_pct: Max drawdown percent, or None.
        trade_count: Trade count.
        win_rate_pct: Win rate percent, or None.
    """

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
    """Lifecycle status of a shadow run."""

    ACTIVE = "active"
    COMPLETED = "completed"
    PAUSED = "paused"


class CandidateAction(StrEnum):
    """Research-only action tags attached to shadow-run candidates."""

    RESEARCH_CANDIDATE = "research_candidate"
    CANDIDATE_RANKING = "candidate_ranking"
    RESEARCH_SIGNAL = "research_signal"
    CANDIDATE_ACTION_FOR_REVIEW = "candidate_action_for_review"


@dataclass(frozen=True)
class CandidateRanking(ResearchResult):
    """One ranked candidate in a shadow-run result.

    Attributes:
        ranking_id: Stable ranking id.
        route_name: Route display name.
        rank: Rank position.
        score: Signal score.
        action: Research-only action tag.
    """

    ranking_id: str = ""
    route_name: str = ""
    rank: int = 0
    score: float = 0.0
    action: CandidateAction = CandidateAction.RESEARCH_CANDIDATE


@dataclass(frozen=True)
class ShadowRunResult(ResearchResult):
    """Shadow-run (paper evaluation) research result.

    Attributes:
        result_id: Stable result id.
        strategy_name: Strategy display name.
        status: Run lifecycle status.
        started_at_utc: Run start (ISO).
        elapsed_days: Days since start.
        paper_pnl_eur: Paper PnL in EUR.
        signal_count: Signal count.
        candidates: Ranked candidates.
    """

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
    """LLM-assisted market analysis research result.

    Attributes:
        analysis_id: Stable analysis id.
        topic: Analysis topic.
        market_context: Context provided to the LLM.
        analysis_text: Generated analysis text.
        citations: Source citations.
        llm_provider / llm_model: Provider identity.
        prompt_snapshot: Prompt snapshot for audit.
    """

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
    """Research brief result.

    Attributes:
        brief_id: Stable brief id.
        title: Brief title.
        summary: Executive summary.
        sections: Structured sections.
        glossary_terms: Referenced glossary terms.
        author: Brief author.
    """

    brief_id: str = ""
    title: str = ""
    summary: str = ""
    sections: list[dict] = field(default_factory=list)
    glossary_terms: list[str] = field(default_factory=list)
    author: str = ""
