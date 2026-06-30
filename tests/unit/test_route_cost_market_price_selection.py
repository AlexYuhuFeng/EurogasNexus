"""Route-cost market price basis tests."""

from types import SimpleNamespace

from eurogas_nexus.api.routes.public.route_cost import _latest_market_price_by_point


def test_route_cost_price_selection_prefers_day_ahead_over_month_ahead_for_resource_pool() -> None:
    rows = [
        SimpleNamespace(
            observation_id="ttf-month",
            market_venue="EEX",
            product="TTF month-ahead",
            price=34.5,
            currency="EUR",
            unit="EUR/MWh",
            metadata_json={"hub": "TTF", "tenor": "month-ahead"},
        ),
        SimpleNamespace(
            observation_id="ttf-day",
            market_venue="ICIS Heren",
            product="TTF day-ahead assessment",
            price=31.2,
            currency="EUR",
            unit="EUR/MWh",
            metadata_json={"hub": "TTF", "tenor": "day-ahead"},
        ),
    ]

    prices = _latest_market_price_by_point(rows)

    assert prices["TTF"]["price"] == 31.2
    assert prices["TTF"]["source_reference"] == "market_observation:ttf-day"
