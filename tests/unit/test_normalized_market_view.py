"""Backend normalized market view tests.

These pin the backend normalization semantics to the legacy frontend
`marketPriceNormalization.ts` behavior so the Web client can migrate onto
`GET /api/market/normalized` without value drift.
"""

from eurogas_nexus.domain.market_intelligence.normalized_view import (
    FxRateInput,
    MarketObservationInput,
    build_normalized_market_view,
    convert_currency,
    is_gas_price_observation,
    observation_hub,
    observation_tenor,
)

EUR_GBP = FxRateInput(
    pair="EURGBP",
    base_currency="EUR",
    quote_currency="GBP",
    rate=0.85,
    observed_at_utc="2026-05-29T15:00:00+00:00",
)
EUR_GBP_NEWER = FxRateInput(
    pair="EURGBP",
    base_currency="EUR",
    quote_currency="GBP",
    rate=0.90,
    observed_at_utc="2026-05-29T16:00:00+00:00",
)
EUR_USD = FxRateInput(
    pair="EURUSD",
    base_currency="EUR",
    quote_currency="USD",
    rate=1.08,
    observed_at_utc="2026-05-29T15:00:00+00:00",
)
USD_GBP = FxRateInput(
    pair="USDGBP",
    base_currency="USD",
    quote_currency="GBP",
    rate=0.79,
    observed_at_utc="2026-05-29T15:00:00+00:00",
)


def _observation(**overrides) -> MarketObservationInput:
    fields = {
        "market_venue": "ICE OCM",
        "product": "NBP within-day",
        "price": 10.0,
        "currency": "GBP",
        "unit": "p/therm",
        "observed_at_utc": "2026-05-29T15:30:00+00:00",
        "period_start_utc": "2026-05-29T06:00:00+00:00",
        "metadata_json": {},
    }
    fields.update(overrides)
    return MarketObservationInput(**fields)


def test_convert_currency_returns_value_for_same_currency() -> None:
    assert convert_currency(12.5, "GBP", "GBP", [EUR_GBP]) == 12.5


def test_convert_currency_direct_pair() -> None:
    assert convert_currency(100.0, "EUR", "GBP", [EUR_GBP]) == 85.0


def test_convert_currency_inverse_pair() -> None:
    assert round(convert_currency(85.0, "GBP", "EUR", [EUR_GBP]) or 0, 6) == 100.0


def test_convert_currency_cross_pair_within_three_edges() -> None:
    assert round(convert_currency(100.0, "EUR", "GBP", [EUR_USD, USD_GBP]) or 0, 6) == round(
        100.0 * 1.08 * 0.79, 6
    )


def test_convert_currency_returns_none_beyond_three_edges() -> None:
    # EUR -> USD -> CHF -> NOK -> GBP needs four edges: no result by contract
    usd_chf = FxRateInput(
        pair="USDCHF", base_currency="USD", quote_currency="CHF", rate=0.92
    )
    chf_nok = FxRateInput(
        pair="CHFNOK", base_currency="CHF", quote_currency="NOK", rate=11.4
    )
    nok_gbp = FxRateInput(
        pair="NOKGBP", base_currency="NOK", quote_currency="GBP", rate=0.076
    )
    assert (
        convert_currency(
            100.0, "EUR", "GBP", [EUR_USD, usd_chf, chf_nok, nok_gbp]
        )
        is None
    )


def test_convert_currency_uses_latest_rate_per_pair() -> None:
    assert convert_currency(100.0, "EUR", "GBP", [EUR_GBP, EUR_GBP_NEWER]) == 90.0


def test_convert_currency_skips_non_positive_rates() -> None:
    bad_rate = FxRateInput(
        pair="EURGBP", base_currency="EUR", quote_currency="GBP", rate=0.0
    )
    assert convert_currency(100.0, "EUR", "GBP", [bad_rate]) is None


def test_observation_hub_prefers_metadata_then_product_then_venue() -> None:
    assert observation_hub(_observation()) == "NBP"
    with_hub = _observation(metadata_json={"hub": "TTF"})
    assert observation_hub(with_hub) == "TTF"
    with_empty_hub = _observation(metadata_json={"hub": "  "})
    assert observation_hub(with_empty_hub) == "NBP"
    no_product = _observation(product="", market_venue="ECB")
    assert observation_hub(no_product) == "ECB"


def test_observation_tenor_prefers_metadata_then_product() -> None:
    assert observation_tenor(_observation()) == "nbp within-day"
    with_tenor = _observation(metadata_json={"tenor": "Day-Ahead"})
    assert observation_tenor(with_tenor) == "day-ahead"


def test_is_gas_price_observation_requires_mwh_unit_and_three_letter_currency() -> None:
    assert is_gas_price_observation(_observation(unit="GBP/MWh"))
    assert not is_gas_price_observation(_observation(unit="p/therm"))
    assert not is_gas_price_observation(_observation(currency="GBX"))


def test_build_normalized_market_view_converts_prices_and_reports_failures() -> None:
    gas_ok = _observation(unit="GBP/MWh", currency="GBP", price=20.0)
    gas_missing_fx = _observation(
        unit="GBP/MWh", currency="PLN", price=100.0, market_venue="TGE"
    )
    non_gas = _observation(unit="p/therm", price=55.0)

    view = build_normalized_market_view([gas_ok, gas_missing_fx, non_gas], [EUR_GBP])

    assert len(view["rows"]) == 3
    assert view["rows"][0]["price_gbp_mwh"] == 20.0
    assert view["rows"][0]["is_gas_price"] is True
    assert view["rows"][1]["is_gas_price"] is True
    assert view["rows"][1]["price_gbp_mwh"] is None
    assert view["rows"][2]["price_gbp_mwh"] is None
    assert any("PLN->GBP" in warning for warning in view["warnings"])
