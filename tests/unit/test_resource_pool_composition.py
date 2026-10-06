"""Resource-pool composition tests: declared cash lags, never invented ones.

``compose_resource_pool_options`` composes each sale option's declared
screen-sale cash lag from the eligible upstream contracts. The audited defect:
the helper returned an implicit one-day default when no eligible contract
declared a lag, and it counted a boolean as a whole day. The helper now reports
an unknown lag as ``None`` (carried into the optimiser request as an explicit
unknown that refuses the pair) and never counts a boolean, negative, float or
string as a declared lag.
"""

from types import SimpleNamespace

from eurogas_nexus.application.resource_pool import (
    compose_resource_pool_options,
    screen_cash_lag_days,
)


def _contract(**overrides: object) -> dict:
    contract = {
        "contract_id": "c1",
        "contract_name": "TTF supply",
        "resource_type": "PIPELINE_IMPORT",
        "delivery_point_name": "TTF",
        "gas_year": "2025+",
        "delivery_quantity_mwh_per_day": 10_000,
        "contract_price_gbp_mwh": 25.0,
        "settlement_frequency": "monthly",
        "upstream_payment_lag_days": 20,
        "screen_sale_cash_lag_days": 1,
        "delivery_tolerance_pct": 2.0,
        "nomination_tolerance_pct": 1.0,
        "tolerance_risk_allowance_gbp_mwh": None,
        "annual_financing_rate_pct": 6.0,
        "owned_entry_capacity_mwh_per_day": None,
        "owned_exit_capacity_mwh_per_day": None,
        "allowed_exit_points": ["TTF"],
        "eligible_sale_modes": [],
        "notes": None,
    }
    return {**contract, **overrides}


def _market_row(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "observation_id": "ttf-gbp-day",
        "market_venue": "ICE_OCM_Sim",
        "product": "TTF day-ahead",
        "price": 30.0,
        "currency": "GBP",
        "unit": "GBP/MWh",
        "observed_at_utc": "2026-07-01T10:00:00+00:00",
        "source_system": "ICE_OCM_Sim",
        "source_reference": "sim:ICE_OCM:TTF:day-ahead:20260701",
        "freshness": "simulated_live",
        "quality_score": 0.62,
        "metadata_json": {
            "hub": "TTF",
            "tenor": "day-ahead",
            "simulated": True,
            "source_family": "ICE_OCM",
        },
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _local_candidate() -> dict:
    return {
        "route_id": "ttf-local",
        "route_name": "TTF local sale",
        "start_point_name": "TTF",
        "target_point_name": "TTF",
        "business_model": "VIRTUAL_HUB_SALE",
        "route_legs": [],
        "required_tso_access": [],
        "source_systems": [],
    }


def _compose(contracts: list[dict]) -> dict:
    return compose_resource_pool_options(
        contracts=contracts,
        candidates=[_local_candidate()],
        tariffs=[],
        market_rows=[_market_row()],
        fx_rows=[],
    )


def test_screen_cash_lag_days_is_unknown_when_nothing_declares_it() -> None:
    """Unknown is ``None``, never the removed one-day default."""

    assert screen_cash_lag_days([]) is None
    assert screen_cash_lag_days([{}]) is None
    assert screen_cash_lag_days([{"screen_sale_cash_lag_days": None}]) is None


def test_screen_cash_lag_days_does_not_count_booleans() -> None:
    """``isinstance(True, int)`` must not turn a boolean into one day."""

    assert screen_cash_lag_days([{"screen_sale_cash_lag_days": True}]) is None
    assert screen_cash_lag_days([{"screen_sale_cash_lag_days": False}]) is None


def test_screen_cash_lag_days_does_not_count_negative_days() -> None:
    """A negative value is not a receipt lag and stays out of the candidates."""

    assert screen_cash_lag_days([{"screen_sale_cash_lag_days": -1}]) is None
    assert (
        screen_cash_lag_days(
            [
                {"screen_sale_cash_lag_days": -5},
                {"screen_sale_cash_lag_days": 3},
            ]
        )
        == 3
    )


def test_screen_cash_lag_days_does_not_parse_floats_or_strings() -> None:
    """Only a declared whole number of days is a candidate."""

    assert screen_cash_lag_days([{"screen_sale_cash_lag_days": 1.0}]) is None
    assert screen_cash_lag_days([{"screen_sale_cash_lag_days": "1"}]) is None


def test_screen_cash_lag_days_returns_the_shortest_declared_whole_day() -> None:
    assert (
        screen_cash_lag_days(
            [
                {"screen_sale_cash_lag_days": 3},
                {"screen_sale_cash_lag_days": 1},
                {"screen_sale_cash_lag_days": 2},
            ]
        )
        == 1
    )


def test_screen_cash_lag_days_preserves_an_explicit_zero() -> None:
    """Zero days is a declared lag, not "unknown"."""

    lag = screen_cash_lag_days(
        [
            {"screen_sale_cash_lag_days": 0},
            {"screen_sale_cash_lag_days": 4},
        ]
    )

    assert lag == 0
    assert lag is not None


def test_compose_reports_an_unknown_declared_option_lag_as_null() -> None:
    """The composed option carries the unknown explicitly, not a default."""

    data = _compose([_contract(screen_sale_cash_lag_days=None)])

    assert data["blockers"] == []
    assert len(data["sale_options"]) == 1
    assert data["sale_options"][0]["screen_sale_cash_lag_days"] is None


def test_compose_carries_the_shortest_declared_sale_lag() -> None:
    """Two eligible contracts compose the shortest declared lag."""

    data = _compose(
        [
            _contract(contract_id="slow", screen_sale_cash_lag_days=5),
            _contract(contract_id="fast", screen_sale_cash_lag_days=2),
        ]
    )

    assert data["sale_options"][0]["screen_sale_cash_lag_days"] == 2


def test_compose_does_not_count_a_boolean_contract_lag_as_a_day() -> None:
    """A boolean declaration cannot shorten the composed lag."""

    data = _compose(
        [
            _contract(contract_id="bool", screen_sale_cash_lag_days=True),
            _contract(contract_id="real", screen_sale_cash_lag_days=4),
        ]
    )

    assert data["sale_options"][0]["screen_sale_cash_lag_days"] == 4
