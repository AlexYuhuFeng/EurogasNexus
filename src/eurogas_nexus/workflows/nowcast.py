"""Weather-adjusted demand nowcast — research-only."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(frozen=True)
class NowcastInput:
    market: str
    period_start_utc: str = ""
    period_end_utc: str = ""
    base_demand_boe_d: float = 0.0
    hdd: float = 0.0
    cdd: float = 0.0
    hdd_sensitivity_boe_per_deg: float = 150000.0
    cdd_sensitivity_boe_per_deg: float = 50000.0


@dataclass(frozen=True)
class NowcastOutput:
    market: str
    period_start_utc: str
    period_end_utc: str
    base_demand_boe_d: float
    hdd_adjustment_boe_d: float
    cdd_adjustment_boe_d: float
    weather_adjustment_boe_d: float
    adjusted_demand_boe_d: float
    hdd: float
    cdd: float
    assumptions: list[str] = field(default_factory=list)
    missing_inputs: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    source_references: list[str] = field(default_factory=list)
    lineage: list[str] = field(default_factory=list)
    research_only: bool = True
    human_review_required: bool = True
    generated_at_utc: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )


def compute_nowcast(input_: NowcastInput) -> NowcastOutput:
    """Adjust base demand by HDD/CDD weather sensitivity.

    Higher HDD → more heating demand → upward adjustment.
    Higher CDD → more cooling demand → upward adjustment.
    """
    missing: list[str] = []
    warnings: list[str] = []

    if not input_.market:
        missing.append("market is required.")
    if input_.base_demand_boe_d <= 0:
        missing.append("base_demand_boe_d must be positive.")

    hdd_adj = input_.hdd * input_.hdd_sensitivity_boe_per_deg
    cdd_adj = input_.cdd * input_.cdd_sensitivity_boe_per_deg
    weather_adj = hdd_adj + cdd_adj
    adjusted = input_.base_demand_boe_d + weather_adj

    if adjusted < 0:
        warnings.append("Adjusted demand is negative — check inputs.")

    return NowcastOutput(
        market=input_.market,
        period_start_utc=input_.period_start_utc,
        period_end_utc=input_.period_end_utc,
        base_demand_boe_d=input_.base_demand_boe_d,
        hdd_adjustment_boe_d=hdd_adj,
        cdd_adjustment_boe_d=cdd_adj,
        weather_adjustment_boe_d=weather_adj,
        adjusted_demand_boe_d=adjusted,
        hdd=input_.hdd,
        cdd=input_.cdd,
        assumptions=[
            "HDD sensitivity: 150k boe/d per degree-day (configurable).",
            "CDD sensitivity: 50k boe/d per degree-day (configurable).",
            "Linear adjustment model — real demand response is non-linear.",
        ],
        missing_inputs=missing,
        warnings=warnings,
        source_references=["synthetic-input"],
        lineage=["nowcast-computation"],
    )
