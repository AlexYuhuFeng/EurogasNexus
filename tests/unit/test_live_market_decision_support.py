"""Live market decision-support model tests."""

from eurogas_nexus.domain.route_cost.live_markets import (
    LiveMarketMark,
    LiveStrategySignal,
    RouteOptionPnl,
    mark_option_to_live_market,
)


def test_live_mark_to_market_uses_bid_for_sellable_option() -> None:
    option = RouteOptionPnl(
        option_id="ttf_to_nbp_bbl_sale",
        label="TTF to NBP via BBL sale",
        business_model="VIRTUAL_HUB_SALE",
        sale_price_gbp_mwh=28.0,
        contract_cost_gbp_mwh=25.0,
        total_charges_gbp_mwh=1.392,
        net_margin_gbp_mwh=1.608,
        net_pnl_gbp_per_day=16080.0,
        source_refs=["BBL published tariff"],
        warnings=[],
        human_review_required=False,
    )
    mark = LiveMarketMark(
        venue="ICE OCM",
        hub="NBP",
        product="Within-day",
        bid_gbp_mwh=28.2,
        ask_gbp_mwh=28.4,
        last_gbp_mwh=28.3,
        mark_time_utc="2026-05-31T08:30:00Z",
        source_system="operator-entered-live-mark",
    )

    result = mark_option_to_live_market(option, mark, delivery_quantity_mwh_per_day=10_000)

    assert result.mark_price_gbp_mwh == 28.2
    assert result.live_net_margin_gbp_mwh == 1.808
    assert result.live_net_pnl_gbp_per_day == 18080.0
    assert isinstance(result.signal, LiveStrategySignal)
    assert result.signal.suggestion_type == "DECISION_SUPPORT"
    assert result.signal.suggested_action == "REVIEW_LIVE_OPTION"
    assert result.human_review_required is True


def test_live_market_mark_without_bid_is_partial() -> None:
    option = RouteOptionPnl(
        option_id="ttf_to_nbp_bbl_sale",
        label="TTF to NBP via BBL sale",
        business_model="VIRTUAL_HUB_SALE",
        sale_price_gbp_mwh=28.0,
        contract_cost_gbp_mwh=25.0,
        total_charges_gbp_mwh=1.392,
        net_margin_gbp_mwh=1.608,
        net_pnl_gbp_per_day=16080.0,
        source_refs=["BBL published tariff"],
        warnings=[],
        human_review_required=False,
    )
    mark = LiveMarketMark(
        venue="EEX",
        hub="NBP",
        product="Within-day",
        mark_time_utc="2026-05-31T08:30:00Z",
        source_system="operator-entered-live-mark",
    )

    result = mark_option_to_live_market(option, mark, delivery_quantity_mwh_per_day=10_000)

    assert result.status == "PARTIAL"
    assert "LIVE_BID_PRICE_MISSING" in result.missing_inputs
