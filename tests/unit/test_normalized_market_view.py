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
    convert_with_edges,
    is_gas_price_observation,
    normalize_observation,
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


def test_build_normalized_market_view_builds_the_latest_rate_graph_once(monkeypatch) -> None:
    """The graph is a pure function of the rate list, so the view builds it once.

    The values are the per-row reference's (asserted against ``convert_currency``
    below); only the number of graph builds changes, which is what makes the
    per-row rebuild avoidable rather than load-bearing.
    """

    from eurogas_nexus.domain.market_intelligence import normalized_view as module

    calls: list[list[FxRateInput]] = []
    original = module.latest_fx_edges

    def counting(rates):
        calls.append(rates)
        return original(rates)

    monkeypatch.setattr(module, "latest_fx_edges", counting)
    observations = [
        _observation(unit="EUR/MWh", currency="EUR", price=30.0 + index)
        for index in range(25)
    ]
    view = build_normalized_market_view(observations, [EUR_GBP, EUR_USD, USD_GBP])

    assert len(calls) == 1
    assert len(view["rows"]) == 25
    assert view["rows"][0]["price_gbp_mwh"] == convert_currency(
        30.0, "EUR", "GBP", [EUR_GBP, EUR_USD, USD_GBP]
    )


def test_build_normalized_market_view_matches_the_per_row_reference_path() -> None:
    """Reusing one graph must not move a single value or warning.

    The reference is :func:`normalize_observation`, which builds the graph for
    each row exactly as the view did before the graph was hoisted out of the
    row loop.
    """

    zero_rate = FxRateInput(
        pair="EURGBP", base_currency="EUR", quote_currency="GBP", rate=0.0
    )
    rates = [EUR_GBP, EUR_GBP_NEWER, EUR_USD, USD_GBP, zero_rate]
    observations = [
        _observation(unit="GBP/MWh", currency="GBP", price=20.0),
        _observation(unit="EUR/MWh", currency="EUR", price=30.0),
        _observation(unit="EUR/MWh", currency="EUR", price=31.0, market_venue="EEX"),
        _observation(unit="USD/MWh", currency="USD", price=105.0, market_venue="ICE OCM"),
        _observation(unit="PLN/MWh", currency="PLN", price=200.0, market_venue="TGE"),
        _observation(unit="p/therm", currency="GBP", price=55.0),
    ]

    view = build_normalized_market_view(observations, rates)
    reference = [normalize_observation(observation, rates) for observation in observations]
    expected_warnings = [
        f"FX conversion unavailable for observation {row['market_venue']}/{row['product']} "
        f"({row['currency']}->GBP)."
        for row in reference
        if row["is_gas_price"] and row["price_gbp_mwh"] is None
    ]

    assert view["rows"] == reference
    assert view["warnings"] == expected_warnings
    assert any("PLN->GBP" in warning for warning in view["warnings"])


def test_convert_currency_settles_cheap_cases_without_building_the_rate_graph(monkeypatch) -> None:
    """Invalid input and same-currency conversion never read the rate list.

    Those checks are a number test and two string comparisons, so the graph is
    built only for a conversion that needs one; the value is the graph path's
    either way.
    """

    from eurogas_nexus.domain.market_intelligence import normalized_view as module

    builds: list[list[FxRateInput]] = []
    original = module.latest_fx_edges

    def counting(rates):
        builds.append(rates)
        return original(rates)

    monkeypatch.setattr(module, "latest_fx_edges", counting)

    assert convert_currency(10.0, "GBP", "GBP", [EUR_GBP]) == 10.0
    assert convert_currency(float("nan"), "EUR", "GBP", [EUR_GBP]) is None
    assert convert_currency(10.0, "  ", "GBP", [EUR_GBP]) is None
    assert builds == []

    rates = [EUR_GBP, EUR_USD, USD_GBP]
    assert convert_currency(10.0, "EUR", "GBP", rates) == convert_with_edges(
        10.0, "EUR", "GBP", original(rates)
    )
    assert builds == [rates]


def test_normalize_observation_builds_the_rate_graph_only_for_a_gas_price_row(
    monkeypatch,
) -> None:
    """A non-gas row is never converted, so it never builds the latest-rate graph.

    The returned rows are compared to the view's - the graph reuse path - so the
    cost change cannot move a value: only the number of graph builds changes.
    """

    from eurogas_nexus.domain.market_intelligence import normalized_view as module

    builds: list[list[FxRateInput]] = []
    original = module.latest_fx_edges
    monkeypatch.setattr(
        module,
        "latest_fx_edges",
        lambda rates: (builds.append(rates), original(rates))[1],
    )

    rates = [EUR_GBP, EUR_USD, USD_GBP]
    non_gas = _observation(unit="p/therm", currency="GBP", price=55.0)
    gas = _observation(unit="USD/MWh", currency="USD", price=105.0, market_venue="ICE OCM")

    view = build_normalized_market_view([non_gas, gas], rates)
    assert len(builds) == 1

    assert normalize_observation(non_gas, rates) == view["rows"][0]
    assert len(builds) == 1  # the non-gas row built nothing
    assert normalize_observation(gas, rates) == view["rows"][1]
    assert len(builds) == 2  # the gas row converts, so it builds one
