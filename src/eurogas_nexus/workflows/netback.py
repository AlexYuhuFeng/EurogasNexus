"""Indicative netback computation — research-only, no execution semantics."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(frozen=True)
class NetbackInput:
    """Input for indicative netback computation."""

    route_name: str
    from_market: str
    to_market: str
    market_price_eur_mwh: float
    route_cost_eur_mwh: float
    fx_rate: float = 1.0
    fx_pair: str = ""


@dataclass(frozen=True)
class NetbackOutput:
    """Computed indicative netback with required research metadata."""

    route_name: str
    from_market: str
    to_market: str
    market_price_eur_mwh: float
    route_cost_eur_mwh: float
    netback_eur_mwh: float
    netback_local_mwh: float
    fx_rate: float
    fx_pair: str = ""
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

    @property
    def is_partial(self) -> bool:
        return bool(self.missing_inputs or self.warnings)


def compute_netback(input_: NetbackInput) -> NetbackOutput:
    """Compute indicative netback: market_price - route_cost.

    Netback represents the upstream value after transport costs.
    When fx_rate != 1.0, netback is also computed in local currency.
    """
    missing: list[str] = []
    warnings: list[str] = []
    assumptions: list[str] = [
        "Netback = market_price - route_cost (linear subtraction).",
        "No volume or capacity constraints applied.",
        "Market price is taken as given (synthetic input).",
    ]

    if not input_.route_name:
        missing.append("route_name is required.")
    if input_.market_price_eur_mwh <= 0:
        missing.append("market_price_eur_mwh must be positive.")
    if input_.route_cost_eur_mwh < 0:
        missing.append("route_cost_eur_mwh must be non-negative.")

    netback_eur = input_.market_price_eur_mwh - input_.route_cost_eur_mwh
    netback_local = netback_eur * input_.fx_rate if input_.fx_rate != 1.0 else netback_eur

    if netback_eur <= 0:
        warnings.append(
            f"Netback is non-positive ({netback_eur:.2f} EUR/MWh). "
            f"Route may be uneconomical under current inputs."
        )

    return NetbackOutput(
        route_name=input_.route_name,
        from_market=input_.from_market,
        to_market=input_.to_market,
        market_price_eur_mwh=input_.market_price_eur_mwh,
        route_cost_eur_mwh=input_.route_cost_eur_mwh,
        netback_eur_mwh=round(netback_eur, 4),
        netback_local_mwh=round(netback_local, 4),
        fx_rate=input_.fx_rate,
        fx_pair=input_.fx_pair,
        assumptions=assumptions,
        missing_inputs=missing,
        warnings=warnings,
        source_references=["synthetic-input"],
        lineage=["netback-computation"],
        research_only=True,
        human_review_required=bool(missing or warnings),
    )
