"""Live market mark-to-market decision-support models."""

from __future__ import annotations

from pydantic import BaseModel, Field


class LiveMarketMark(BaseModel):
    venue: str
    hub: str
    product: str
    bid_gbp_mwh: float | None = None
    ask_gbp_mwh: float | None = None
    last_gbp_mwh: float | None = None
    mark_time_utc: str
    source_system: str


class LiveStrategySignal(BaseModel):
    suggestion_type: str
    suggested_action: str
    rationale: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    human_review_required: bool = True


class LiveOptionMarkResult(BaseModel):
    option_id: str
    venue: str
    hub: str
    product: str
    status: str
    mark_price_gbp_mwh: float | None = None
    live_net_margin_gbp_mwh: float | None = None
    live_net_pnl_gbp_per_day: float | None = None
    missing_inputs: list[str] = Field(default_factory=list)
    signal: LiveStrategySignal
    human_review_required: bool = True


class RouteOptionPnl(BaseModel):
    option_id: str
    label: str
    business_model: str
    sale_price_gbp_mwh: float
    contract_cost_gbp_mwh: float
    total_charges_gbp_mwh: float
    net_margin_gbp_mwh: float
    net_pnl_gbp_per_day: float
    source_refs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    human_review_required: bool = True


def mark_option_to_live_market(
    option: RouteOptionPnl,
    mark: LiveMarketMark,
    *,
    delivery_quantity_mwh_per_day: float,
) -> LiveOptionMarkResult:
    """Mark one option to a live screen bid and emit decision-support guidance."""

    if mark.bid_gbp_mwh is None:
        return LiveOptionMarkResult(
            option_id=option.option_id,
            venue=mark.venue,
            hub=mark.hub,
            product=mark.product,
            status="PARTIAL",
            missing_inputs=["LIVE_BID_PRICE_MISSING"],
            signal=LiveStrategySignal(
                suggestion_type="DECISION_SUPPORT",
                suggested_action="WAIT_FOR_LIVE_BID",
                rationale=["A sellable bid is required to mark the option on a live basis."],
                warnings=["No order or execution action is generated."],
            ),
        )

    margin = round(
        mark.bid_gbp_mwh - option.contract_cost_gbp_mwh - option.total_charges_gbp_mwh,
        4,
    )
    pnl = round(margin * delivery_quantity_mwh_per_day, 4)
    action = "REVIEW_LIVE_OPTION" if pnl >= option.net_pnl_gbp_per_day else "REVIEW_ALTERNATIVES"
    return LiveOptionMarkResult(
        option_id=option.option_id,
        venue=mark.venue,
        hub=mark.hub,
        product=mark.product,
        status="SUCCESS",
        mark_price_gbp_mwh=mark.bid_gbp_mwh,
        live_net_margin_gbp_mwh=margin,
        live_net_pnl_gbp_per_day=pnl,
        signal=LiveStrategySignal(
            suggestion_type="DECISION_SUPPORT",
            suggested_action=action,
            rationale=[
                "Live PnL is marked from the available bid because the option is a sale.",
                "Compare this value against route availability, capacity, and contract tolerances.",
            ],
            warnings=["Human trader review required before any external action."],
        ),
        human_review_required=True,
    )
