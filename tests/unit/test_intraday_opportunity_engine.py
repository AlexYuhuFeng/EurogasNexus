"""Deterministic intraday opportunity evaluation tests."""

from datetime import UTC, datetime, timedelta

from eurogas_nexus.domain.market_intelligence.opportunity_engine import (
    AccessStatus,
    MarketQuote,
    OpportunityScanPolicy,
    OpportunityStatus,
    RouteEconomics,
    evaluate_route_opportunity,
)

NOW = datetime(2026, 7, 18, 9, 30, tzinfo=UTC)


def _quote(
    quote_id: str,
    hub: str,
    *,
    bid: float,
    ask: float,
    bid_quantity: float = 900,
    ask_quantity: float = 800,
    observed_at: datetime = NOW,
) -> MarketQuote:
    return MarketQuote(
        quote_id=quote_id,
        source_system="EEX_Sim",
        venue="EEX",
        instrument_id=f"EEX-{hub}-DAY-AHEAD",
        hub=hub,
        product="day-ahead",
        delivery_start_utc=datetime(2026, 7, 19, 5, tzinfo=UTC),
        delivery_end_utc=datetime(2026, 7, 20, 5, tzinfo=UTC),
        bid_price=bid,
        ask_price=ask,
        last_price=99.0,
        bid_quantity_mwh=bid_quantity,
        ask_quantity_mwh=ask_quantity,
        currency="EUR",
        unit="MWh",
        observed_at_utc=observed_at,
        received_at_utc=observed_at,
        source_reference=f"sim:{quote_id}",
        freshness="simulated_live",
        quality_score=0.8,
        simulated=True,
    )


def _route(access: AccessStatus = AccessStatus.CONFIRMED) -> RouteEconomics:
    return RouteEconomics(
        route_id="ttf-bbl-nbp",
        route_name="TTF -> BBL -> NBP",
        from_hub="TTF",
        to_hub="NBP",
        total_cost=1.0,
        currency="EUR",
        unit="MWh",
        available_capacity_mwh=500,
        access_status=access,
        required_tso_access=["BBL Company"],
        cost_components=[{"component_type": "EXIT_CAPACITY", "amount": 1.0}],
        source_refs=["tariff:bbl-forward"],
    )


def test_opportunity_uses_buy_ask_sell_bid_and_quantity_bottleneck() -> None:
    result = evaluate_route_opportunity(
        _quote("buy", "TTF", bid=30.9, ask=31.0, ask_quantity=800),
        _quote("sell", "NBP", bid=32.5, ask=32.6, bid_quantity=700),
        _route(),
        scan_id="scan-1",
        detected_at_utc=NOW,
        policy=OpportunityScanPolicy(
            trading_cost_per_mwh=0.02,
            risk_buffer_per_mwh=0.03,
            minimum_net_margin_per_mwh=0.05,
        ),
    )

    assert result is not None
    assert result.status == OpportunityStatus.ACTIONABLE_REVIEW
    assert result.buy_ask == 31.0
    assert result.sell_bid == 32.5
    assert result.gross_spread == 1.5
    assert result.net_margin == 0.45
    assert result.max_quantity_mwh == 500
    assert result.indicative_net_value == 225.0
    assert "SIMULATED_MARKET_DATA" in result.warnings
    assert result.human_review_required is True


def test_unconfirmed_tso_access_blocks_positive_spread() -> None:
    result = evaluate_route_opportunity(
        _quote("buy", "TTF", bid=30.9, ask=31.0),
        _quote("sell", "NBP", bid=32.5, ask=32.6),
        _route(AccessStatus.UNCONFIRMED),
        scan_id="scan-2",
        detected_at_utc=NOW,
    )

    assert result is not None
    assert result.status == OpportunityStatus.BLOCKED
    assert "TSO_ACCESS_UNCONFIRMED" in result.missing_inputs


def test_stale_quote_blocks_positive_spread() -> None:
    stale = NOW - timedelta(seconds=31)
    result = evaluate_route_opportunity(
        _quote("buy", "TTF", bid=30.9, ask=31.0, observed_at=stale),
        _quote("sell", "NBP", bid=32.5, ask=32.6),
        _route(),
        scan_id="scan-3",
        detected_at_utc=NOW,
        policy=OpportunityScanPolicy(quote_max_age_seconds=30),
    )

    assert result is not None
    assert result.status == OpportunityStatus.BLOCKED
    assert "QUOTE_STALE" in result.missing_inputs


def test_future_dated_quote_blocks_positive_spread() -> None:
    future = NOW + timedelta(seconds=10)
    result = evaluate_route_opportunity(
        _quote("buy", "TTF", bid=30.9, ask=31.0, observed_at=future),
        _quote("sell", "NBP", bid=32.5, ask=32.6),
        _route(),
        scan_id="scan-future",
        detected_at_utc=NOW,
    )

    assert result is not None
    assert result.status == OpportunityStatus.BLOCKED
    assert "QUOTE_EVENT_TIME_IN_FUTURE" in result.missing_inputs


def test_mismatched_delivery_window_is_not_compared() -> None:
    sell = _quote("sell", "NBP", bid=32.5, ask=32.6)
    sell.delivery_end_utc += timedelta(days=1)

    result = evaluate_route_opportunity(
        _quote("buy", "TTF", bid=30.9, ask=31.0),
        sell,
        _route(),
        scan_id="scan-4",
        detected_at_utc=NOW,
    )

    assert result is None


def test_last_price_cannot_create_opportunity_without_executable_sides() -> None:
    buy = _quote("buy", "TTF", bid=30.9, ask=31.0)
    sell = _quote("sell", "NBP", bid=32.5, ask=32.6)
    buy.ask_price = None

    assert (
        evaluate_route_opportunity(
            buy,
            sell,
            _route(),
            scan_id="scan-5",
            detected_at_utc=NOW,
        )
        is None
    )
