"""Live market mark-to-market decision-support models.

实时盯市决策支持：用可成交的实时买价（bid）对销售期权盯市，输出
决策支持信号——只建议"复核/观望"，绝不生成任何执行动作。
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class LiveMarketMark(BaseModel):
    """One live screen mark (bid/ask/last) at a venue.

    Attributes:
        venue: Screen venue (e.g. ``ICE OCM``, ``EEX``).
        hub: Hub the mark belongs to.
        product: Product label.
        bid_gbp_mwh: Executable bid, or None.
        ask_gbp_mwh: Executable ask, or None.
        last_gbp_mwh: Last traded mark, or None.
        mark_time_utc: Mark time (ISO, UTC).
        source_system: Source system of the mark.
    """

    venue: str
    hub: str
    product: str
    bid_gbp_mwh: float | None = None
    ask_gbp_mwh: float | None = None
    last_gbp_mwh: float | None = None
    mark_time_utc: str
    source_system: str


class LiveStrategySignal(BaseModel):
    """Decision-support guidance emitted with a live mark result.

    Attributes:
        suggestion_type: Always ``DECISION_SUPPORT`` (never execution).
        suggested_action: Machine-readable action tag for human review.
        rationale: Human-readable reasoning.
        warnings: Warnings (e.g. no execution action generated).
        human_review_required: Always True.
    """

    suggestion_type: str
    suggested_action: str
    rationale: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    human_review_required: bool = True


class LiveOptionMarkResult(BaseModel):
    """Result of marking one option against a live market mark.

    Attributes:
        option_id: The marked option.
        venue: Mark venue.
        hub: Mark hub.
        product: Mark product.
        status: SUCCESS or PARTIAL (missing bid).
        mark_price_gbp_mwh: Applied bid price, or None.
        live_net_margin_gbp_mwh: Live margin per MWh, or None.
        live_net_pnl_gbp_per_day: Live daily PnL, or None.
        missing_inputs: Missing inputs (e.g. ``LIVE_BID_PRICE_MISSING``).
        signal: Decision-support guidance.
        human_review_required: Always True.
    """

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
    """One sale option's static PnL profile for live marking.

    Attributes:
        option_id: Stable option id.
        label: Display label.
        business_model: Business model tag.
        sale_price_gbp_mwh: Static sale price.
        contract_cost_gbp_mwh: Upstream contract cost.
        total_charges_gbp_mwh: Route/other charges.
        net_margin_gbp_mwh: Static net margin.
        net_pnl_gbp_per_day: Static daily PnL.
        source_refs: Provenance references.
        warnings: Option warnings.
        human_review_required: Always True.
    """

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
    """Mark one option to a live screen bid and emit decision-support guidance.

    用实时买价对销售期权盯市并生成决策支持信号。

    Args:
        option: The sale option to mark.
        mark: Live screen mark (bid is the executable side for a sale).
        delivery_quantity_mwh_per_day: Volume for PnL scaling, MWh/d.

    Returns:
        SUCCESS with live margin/PnL and a review signal when a bid is
        available; PARTIAL with ``LIVE_BID_PRICE_MISSING`` and a
        WAIT_FOR_LIVE_BID signal otherwise. Signals never propose an
        execution action.

    Raises:
        No exceptions; missing bids degrade to PARTIAL.
    """

    if mark.bid_gbp_mwh is None:
        # 销售期权必须用买价盯市：无买价即无法盯市，明确降级为 PARTIAL。
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
    # 实时 PnL 优于静态 PnL 时建议复核该期权，否则建议复核替代方案。
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
