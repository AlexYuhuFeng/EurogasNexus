"""A supply contract priced in EUR or USD is valued against its hub and costed in GBP."""

from datetime import date
from types import SimpleNamespace

import pytest

from eurogas_nexus.application.position_inputs import contract_price_in_hub_currency
from eurogas_nexus.application.resource_pool import contracts_priced_in_gbp
from eurogas_nexus.db.repositories.route_cost import contract_price_currency

RATES = {"EUR": 1.0, "GBP": 0.85, "USD": 1.10}


def test_a_price_in_the_hub_currency_is_used_as_recorded() -> None:
    assert contract_price_in_hub_currency(34.0, "EUR", "EUR", RATES) == (34.0, None)


def test_a_foreign_currency_price_is_translated_at_the_ecb_rate_and_said_so() -> None:
    price, warning = contract_price_in_hub_currency(11.0, "USD", "EUR", RATES)
    assert price == pytest.approx(10.0)
    assert "USD price translated into EUR" in warning


def test_without_a_rate_the_leg_is_not_valued() -> None:
    price, warning = contract_price_in_hub_currency(30.0, "USD", "GBP", {"EUR": 1.0, "GBP": 0.85})
    assert price is None and "no ECB rate" in warning


def test_the_route_engines_get_gbp_and_a_contract_without_a_rate_is_left_out() -> None:
    fx = [
        SimpleNamespace(
            observation_id="ecb-1", pair="EURGBP", base_currency="EUR", quote_currency="GBP",
            rate=0.85, value_date="2026-11-03", observed_at_utc=None, source_system="ECB",
        )
    ]
    contracts = [
        {"contract_id": "nbp-1", "contract_price_gbp_mwh": 30.0, "contract_price_currency": "GBP"},
        {"contract_id": "ttf-1", "contract_price_gbp_mwh": 40.0, "contract_price_currency": "EUR"},
        {"contract_id": "lng-1", "contract_price_gbp_mwh": 35.0, "contract_price_currency": "USD"},
    ]
    priced, blockers, warnings = contracts_priced_in_gbp(contracts, fx, date(2026, 11, 4))
    assert [c["contract_id"] for c in priced] == ["nbp-1", "ttf-1"]
    assert priced[1]["contract_price_gbp_mwh"] == pytest.approx(34.0)
    assert contracts[1]["contract_price_gbp_mwh"] == 40.0  # the input is not changed
    assert blockers == ["CONTRACT_PRICE_FX_MISSING:lng-1:USD"]
    assert "CONTRACT_PRICE_FX_TRANSLATED:ttf-1:EUR->GBP" in warnings


def test_only_gbp_eur_and_usd_are_accepted() -> None:
    assert contract_price_currency(" eur ") == "EUR"
    with pytest.raises(ValueError):
        contract_price_currency("JPY")
