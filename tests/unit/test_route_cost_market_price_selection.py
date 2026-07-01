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


def test_route_cost_price_selection_accepts_simulated_source_as_runtime_price() -> None:
    rows = [
        SimpleNamespace(
            observation_id="ttf-sim-day",
            market_venue="EEX",
            product="TTF day-ahead",
            price=31.45,
            currency="EUR",
            unit="EUR/MWh",
            observed_at_utc="2026-07-01T10:15:00+00:00",
            source_system="EEX_Sim",
            freshness="simulated_live",
            quality_score=0.62,
            metadata_json={
                "hub": "TTF",
                "tenor": "day-ahead",
                "simulated": True,
                "source_family": "EEX",
            },
        ),
    ]

    prices = _latest_market_price_by_point(rows)

    assert prices["TTF"] == {
        "price": 31.45,
        "currency": "EUR",
        "unit": "EUR/MWh",
        "source_reference": "market_observation:ttf-sim-day",
        "source_system": "EEX_Sim",
        "observed_at_utc": "2026-07-01T10:15:00+00:00",
        "freshness": "simulated_live",
        "quality_score": 0.62,
        "simulated": True,
        "source_family": "EEX",
    }


def test_route_cost_price_selection_prefers_licensed_source_over_simulated_same_basis() -> None:
    rows = [
        SimpleNamespace(
            observation_id="ttf-sim-day",
            market_venue="EEX",
            product="TTF day-ahead",
            price=31.45,
            currency="EUR",
            unit="EUR/MWh",
            observed_at_utc="2026-07-01T10:15:00+00:00",
            source_system="EEX_Sim",
            freshness="simulated_live",
            quality_score=0.62,
            metadata_json={"hub": "TTF", "tenor": "day-ahead", "simulated": True},
        ),
        SimpleNamespace(
            observation_id="ttf-licensed-day",
            market_venue="EEX",
            product="TTF day-ahead",
            price=31.72,
            currency="EUR",
            unit="EUR/MWh",
            observed_at_utc="2026-07-01T10:14:30+00:00",
            source_system="EEX",
            freshness="live",
            quality_score=0.92,
            metadata_json={"hub": "TTF", "tenor": "day-ahead"},
        ),
    ]

    prices = _latest_market_price_by_point(rows)

    assert prices["TTF"]["price"] == 31.72
    assert prices["TTF"]["source_system"] == "EEX"
    assert prices["TTF"]["simulated"] is False
