"""Backtest domain contracts.

These models are pure domain contracts for the temporally safe backtest
engine. They carry no SQLAlchemy or web-framework imports.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator

from eurogas_nexus.domain.market.gas_day import (
    DEFAULT_GAS_DAY_CALENDAR,
    EU_CAM_UTC_CALENDAR,
)
from eurogas_nexus.domain.ontology.vocabulary import (
    CostTreatment,
    DecisionClockBasis,
    FillPricePolicy,
    MissingDataPolicy,
    TemporalIntegrityStatus,
)

BACKTEST_ENGINE_VERSION = "backtest-engine/1"


class BacktestPeriod(BaseModel):
    """Half-open historical evaluation window ``[start_utc, end_utc)``."""

    start_utc: datetime
    end_utc: datetime

    @model_validator(mode="after")
    def _ordered(self) -> BacktestPeriod:
        if self.start_utc >= self.end_utc:
            raise ValueError("backtest period start must be before end")
        if (self.end_utc - self.start_utc).days > 3660:
            raise ValueError("backtest period must not exceed 3660 days")
        return self


class BacktestDecisionSchedule(BaseModel):
    """When the strategy evaluates during a historical period."""

    basis: DecisionClockBasis = DecisionClockBasis.GAS_DAY
    decision_time_utc: str = "05:00"
    timezone: str = "UTC"
    gas_day_calendar: str = DEFAULT_GAS_DAY_CALENDAR

    @model_validator(mode="after")
    def _validate(self) -> BacktestDecisionSchedule:
        if self.timezone != "UTC":
            raise ValueError(
                "CR-04 decision clock supports UTC only; no local-time ambiguity"
            )
        if self.gas_day_calendar not in {DEFAULT_GAS_DAY_CALENDAR, EU_CAM_UTC_CALENDAR}:
            raise ValueError(
                f"Unsupported gas-day calendar: {self.gas_day_calendar!r}"
            )
        return self


class BacktestCostComponent(BaseModel):
    """One explicit cost assumption or modeled cost line."""

    code: str = Field(min_length=1, max_length=64)
    treatment: CostTreatment
    amount_gbp_mwh: float | None = Field(default=None, ge=0)
    currency: str = "GBP"
    unit: str = "GBP/MWh"
    source_refs: list[str] = Field(default_factory=list)
    rationale: str = ""

    @model_validator(mode="after")
    def _validate(self) -> BacktestCostComponent:
        if self.treatment in {CostTreatment.KNOWN_COST, CostTreatment.MODELED_COST}:
            if self.amount_gbp_mwh is None:
                raise ValueError(
                    f"cost component {self.code} is {self.treatment.value} "
                    "and requires amount_gbp_mwh"
                )
        return self


class BacktestEconomicAssumptions(BaseModel):
    """Explicit fill, FX, missing-data and cost policies for one run."""

    fill_price_policy: FillPricePolicy = FillPricePolicy.NEXT_ELIGIBLE
    missing_data_policy: MissingDataPolicy = MissingDataPolicy.FAIL
    carry_forward_max_age_seconds: int = Field(default=86_400, ge=0, le=31_536_000)
    require_historical_fx: bool = True
    fallback_sources: dict[str, str] = Field(default_factory=dict)
    cost_components: list[BacktestCostComponent] = Field(
        default_factory=lambda: _default_cost_components()
    )

    @model_validator(mode="after")
    def _validate(self) -> BacktestEconomicAssumptions:
        if (
            self.missing_data_policy == MissingDataPolicy.USE_APPROVED_FALLBACK_SOURCE
            and not self.fallback_sources
        ):
            raise ValueError(
                "USE_APPROVED_FALLBACK_SOURCE requires fallback_sources"
            )
        codes = [item.code for item in self.cost_components]
        if len(codes) != len(set(codes)):
            raise ValueError("duplicate cost component code")
        return self

    def cost_by_code(self, code: str) -> BacktestCostComponent:
        return next(item for item in self.cost_components if item.code == code)

    def modeled_cost_components(self) -> list[BacktestCostComponent]:
        return [
            item
            for item in self.cost_components
            if item.treatment
            in {CostTreatment.KNOWN_COST, CostTreatment.MODELED_COST}
        ]


class BacktestObservation(BaseModel):
    """One normalized historical price observation eligible for the engine."""

    observation_id: str
    source_system: str
    venue: str = ""
    hub: str = ""
    product: str = ""
    tenor: str = ""
    price_name: str
    price: float
    currency: str
    unit: str
    observed_at_utc: datetime
    received_at_utc: datetime | None = None
    delivery_start_utc: datetime | None = None
    delivery_end_utc: datetime | None = None
    bar_minutes: int | None = None
    price_type: str = "mid"
    source_reference: str = ""
    simulated: bool = False
    temporal_integrity: TemporalIntegrityStatus = TemporalIntegrityStatus.APPROXIMATE


class BacktestFxRate(BaseModel):
    """One historical FX rate row."""

    observation_id: str
    pair: str
    base_currency: str
    quote_currency: str
    rate: float
    observed_at_utc: datetime
    received_at_utc: datetime | None = None
    source_system: str = ""
    source_reference: str = ""
    temporal_integrity: TemporalIntegrityStatus = TemporalIntegrityStatus.APPROXIMATE


class BacktestCostObservation(BaseModel):
    """One time-windowed cost evidence row."""

    observation_id: str
    scope_type: str
    scope_id: str
    observation_type: str
    value: float
    currency: str
    unit: str
    effective_from_utc: datetime
    effective_to_utc: datetime | None = None
    source_system: str = ""
    source_reference: str = ""
    created_at_utc: datetime | None = None


class BacktestResourceEvidence(BaseModel):
    """Frozen resource context reused by the strategy evaluator."""

    resource_id: str
    resource_name: str = ""
    available_quantity_mwh_per_day: float
    all_in_cost_gbp_mwh: float
    delivery_tolerance_pct: float | None = None
    nomination_tolerance_pct: float | None = None
    booked_entry_capacity_mwh_per_day: float | None = None
    balancing_allowance_gbp_mwh: float = 0.0
    required_tso_access: list[str] = Field(default_factory=list)
    company_accessible_tsos: list[str] | None = None


class BacktestEvidencePool(BaseModel):
    """All rows batch-loaded for one run; the engine filters per decision."""

    observations: list[BacktestObservation] = Field(default_factory=list)
    fx_rates: list[BacktestFxRate] = Field(default_factory=list)
    cost_observations: list[BacktestCostObservation] = Field(default_factory=list)
    resources: list[BacktestResourceEvidence] = Field(default_factory=list)

    def observation_refs(self) -> list[str]:
        return sorted(
            {
                item.source_reference
                for item in self.observations
                if item.source_reference
            }
        )

    def fx_refs(self) -> list[str]:
        return sorted({item.source_reference for item in self.fx_rates if item.source_reference})

    def cost_refs(self) -> list[str]:
        return sorted(
            {item.source_reference for item in self.cost_observations if item.source_reference}
        )

    def resource_refs(self) -> list[str]:
        return sorted({item.resource_id for item in self.resources})


class BacktestDecisionEvent(BaseModel):
    """One structured simulated decision event."""

    event_id: str
    run_id: str
    experiment_id: str | None = None
    decision_sequence: int
    decision_time_utc: datetime
    gas_day: str
    gas_day_start_utc: datetime
    gas_day_end_utc: datetime
    outcome: str
    candidate_action_for_review: str | None = None
    weighted_score: float | None = None
    day_ahead_average_gbp_mwh: float | None = None
    intraday_average_gbp_mwh: float | None = None
    intraday_vs_day_ahead_spread_gbp_mwh: float | None = None
    allocation_targets: list[dict[str, Any]] = Field(default_factory=list)
    gross_indicative_pnl_gbp: float = 0.0
    modeled_costs_gbp: float = 0.0
    net_indicative_pnl_gbp: float = 0.0
    cumulative_net_indicative_pnl_gbp: float = 0.0
    ending_exposure_mwh_per_day: float = 0.0
    missing_inputs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    price_evidence_refs: list[str] = Field(default_factory=list)
    fx_evidence_refs: list[str] = Field(default_factory=list)
    cost_evidence_refs: list[str] = Field(default_factory=list)
    resource_evidence_refs: list[str] = Field(default_factory=list)
    cost_trace: list[dict[str, Any]] = Field(default_factory=list)
    attribution: list[dict[str, Any]] = Field(default_factory=list)
    research_only: bool = True
    human_review_required: bool = True


class BacktestSeriesPoint(BaseModel):
    """One point of the persisted net PnL/exposure series."""

    run_id: str
    decision_sequence: int
    decision_time_utc: datetime
    gas_day: str
    gross_indicative_pnl_gbp: float
    modeled_costs_gbp: float
    net_indicative_pnl_gbp: float
    cumulative_net_indicative_pnl_gbp: float
    ending_exposure_mwh_per_day: float
    drawdown_gbp: float = 0.0


class BacktestMetricSet(BaseModel):
    """Backend-generated backtest metrics."""

    evaluation_count: int = 0
    candidate_decision_count: int = 0
    blocked_decision_count: int = 0
    skipped_decision_count: int = 0
    data_coverage: float = 0.0
    gross_indicative_pnl_gbp: float = 0.0
    modeled_costs_gbp: float = 0.0
    net_indicative_pnl_gbp: float = 0.0
    max_drawdown_gbp: float = 0.0
    peak_timestamp_utc: str | None = None
    trough_timestamp_utc: str | None = None
    recovery_timestamp_utc: str | None = None
    pnl_volatility_gbp: float | None = None
    worst_event_pnl_gbp: float | None = None
    best_event_pnl_gbp: float | None = None
    max_exposure_mwh_per_day: float = 0.0
    average_exposure_mwh_per_day: float = 0.0
    hit_ratio: float | None = None
    turnover: float | None = None
    average_margin_gbp_mwh: float | None = None
    average_modeled_cost_gbp_mwh: float | None = None
    sharpe_ratio: float | None = None
    sortino_ratio: float | None = None
    risk_metric_not_applicable_reasons: list[str] = Field(default_factory=list)
    warning_counts: dict[str, int] = Field(default_factory=dict)
    temporal_integrity: str = "INSUFFICIENT"


class BacktestRunDefinition(BaseModel):
    """Effective-input definition for one backtest run."""

    strategy_version_id: str
    period: BacktestPeriod
    schedule: BacktestDecisionSchedule = Field(default_factory=BacktestDecisionSchedule)
    economic_assumptions: BacktestEconomicAssumptions = Field(
        default_factory=BacktestEconomicAssumptions
    )
    parameter_values: dict[str, Any] = Field(default_factory=dict)
    deterministic_seed: str | None = None
    experiment_id: str | None = None

    @model_validator(mode="after")
    def _parameters_frozen(self) -> BacktestRunDefinition:
        if self.parameter_values:
            raise ValueError(
                "CR-04 executes only the frozen parameter values of the "
                "strategy version; parameter override runs are reserved for "
                "the parameter-comparison milestone"
            )
        return self


class BacktestResult(BaseModel):
    """Complete semantic result of one backtest run."""

    run_id: str
    strategy_id: str
    strategy_version_id: str
    experiment_id: str | None = None
    backtest_engine_version: str = BACKTEST_ENGINE_VERSION
    temporal_integrity: TemporalIntegrityStatus = TemporalIntegrityStatus.INSUFFICIENT
    status: str = "BLOCKED"
    events: list[BacktestDecisionEvent] = Field(default_factory=list)
    series: list[BacktestSeriesPoint] = Field(default_factory=list)
    metrics: BacktestMetricSet = Field(default_factory=BacktestMetricSet)
    attribution: list[dict[str, Any]] = Field(default_factory=list)
    missing_inputs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    research_only: bool = True
    human_review_required: bool = True


def _default_cost_components() -> list[BacktestCostComponent]:
    """Return the no-silent-zero default cost contract."""

    return [
        BacktestCostComponent(
            code="TRANSACTION_COST",
            treatment=CostTreatment.UNAVAILABLE,
            rationale="No transaction cost evidence was supplied for this run.",
        ),
        BacktestCostComponent(
            code="SLIPPAGE",
            treatment=CostTreatment.UNAVAILABLE,
            rationale="No historical slippage model was supplied for this run.",
        ),
        BacktestCostComponent(
            code="BROKER_EXCHANGE_FEE",
            treatment=CostTreatment.UNAVAILABLE,
            rationale="No broker/exchange fee schedule was supplied for this run.",
        ),
        BacktestCostComponent(
            code="TRANSPORT_TARIFF",
            treatment=CostTreatment.EXCLUDED,
            rationale="Current OCM/day-ahead component has no route transport leg.",
        ),
        BacktestCostComponent(
            code="CAPACITY_COST",
            treatment=CostTreatment.UNAVAILABLE,
            rationale="No capacity cost evidence was supplied for this run.",
        ),
        BacktestCostComponent(
            code="BALANCING_ALLOWANCE",
            treatment=CostTreatment.RESOURCE_DEFINED,
            rationale=(
                "Balancing allowance is embedded in the frozen resource "
                "all-in cost used by the strategy evaluator."
            ),
        ),
        BacktestCostComponent(
            code="STORAGE_COST",
            treatment=CostTreatment.EXCLUDED,
            rationale="Current strategy component does not use storage.",
        ),
    ]
