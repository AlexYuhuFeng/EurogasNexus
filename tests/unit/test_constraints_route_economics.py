"""Route economics netback constraint tests."""

from eurogas_nexus.domain.constraints.route_economics import netback


def test_netback_subtracts_route_cost_from_sale_price() -> None:
    assert netback(
        29.0,
        3.5,
        price_currency="GBP",
        cost_currency="GBP",
        price_unit="MWh",
        cost_unit="MWh",
    ) == 25.5


def test_netback_none_when_sale_price_missing() -> None:
    assert netback(None, 3.5, price_currency="GBP", cost_currency="GBP") is None


def test_netback_none_when_route_cost_missing() -> None:
    assert netback(29.0, None, price_currency="GBP", cost_currency="GBP") is None


def test_netback_none_on_currency_mismatch() -> None:
    assert netback(
        29.0,
        3.5,
        price_currency="EUR",
        cost_currency="GBP",
        price_unit="MWh",
        cost_unit="MWh",
    ) is None


def test_netback_none_on_unit_mismatch() -> None:
    assert netback(
        29.0,
        3.5,
        price_currency="GBP",
        cost_currency="GBP",
        price_unit="MWh",
        cost_unit="boe",
    ) is None
