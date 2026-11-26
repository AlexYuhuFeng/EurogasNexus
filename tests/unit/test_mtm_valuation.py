"""MtM at the forward FX for each delivery month, discounted to its payment date.

Quant review 2026-11-26 (3.3): the ladder's MtM was undiscounted and converted at spot FX
although a forward-FX module exists. Rates here are illustrative fixings, not market data.
"""

from datetime import date

import pytest

from eurogas_nexus.domain.market.fx_forward import FxHoldings
from eurogas_nexus.domain.portfolio.mtm_valuation import ForwardValuation, payment_date
from eurogas_nexus.domain.portfolio.position_ladder import PositionLeg, mark_to_market

TODAY = date(2026, 11, 26)


def _holdings(estr=3.0, sonia=4.0):
    return FxHoldings.from_rows(
        [{"pair": "EURGBP", "rate": 0.85, "rate_type": "reference",
          "value_date": TODAY.isoformat(), "source_system": "ECB"}],
        [{"benchmark_id": "ESTR", "value_date": TODAY.isoformat(), "rate_pct": estr,
          "source_system": "ECB"},
         {"benchmark_id": "SONIA", "value_date": TODAY.isoformat(), "rate_pct": sonia,
          "source_system": "BOE"}],
    )


def test_payment_date_is_the_20th_of_the_month_after_delivery():
    assert payment_date("2026-12") == date(2027, 1, 20)


def test_a_far_month_is_discounted_and_a_gbp_hub_converts_at_the_forward():
    legs = [PositionLeg("physical", "TTF", date(2028, 10, 1), date(2028, 10, 31), 1_000.0,
                        price=30.0)]
    marks = {("TTF", "2028-10"): 32.0}
    undiscounted, _ = mark_to_market(legs, marks, horizon_start=TODAY,
                                     horizon_end=date(2028, 10, 31))
    assert undiscounted == pytest.approx(62_000.0)  # before: 2 x 31,000, as it is paid today
    valuation = ForwardValuation(_holdings(), "EUR", TODAY)
    value, missing = mark_to_market(legs, marks, horizon_start=TODAY,
                                    horizon_end=date(2028, 10, 31), valuation=valuation)
    days = (date(2028, 11, 20) - TODAY).days
    assert missing == 0
    assert value == pytest.approx(62_000.0 / (1.03 ** (days / 360)))  # about 5.6 % less
    # An NBP month reported in EUR: at the forward GBP->EUR for the month, not spot.
    nbp = [PositionLeg("physical", "NBP", date(2027, 6, 1), date(2027, 6, 30), 1_000.0,
                       price=30.0)]
    value, _ = mark_to_market(nbp, {("NBP", "2027-06"): 31.0}, horizon_start=TODAY,
                              horizon_end=date(2027, 6, 30), valuation=valuation)
    forward = valuation.fx("GBP", "EUR", "2027-06")
    assert forward != pytest.approx(1 / 0.85, rel=1e-6)  # GBP rates above EUR: not spot
    assert value == pytest.approx(30_000.0 * forward * valuation.discount("2027-06"))
    assert valuation.notes() == []


def test_a_price_agreed_in_another_currency_converts_at_the_forward():
    valuation = ForwardValuation(_holdings(), "EUR", TODAY)
    leg = PositionLeg("physical", "TTF", date(2027, 6, 1), date(2027, 6, 30), 1_000.0,
                      price=30.0 / 0.85 * 0.85, price_native=25.5, price_currency="GBP")
    value, _ = mark_to_market([leg], {("TTF", "2027-06"): 32.0}, horizon_start=TODAY,
                              horizon_end=date(2027, 6, 30), valuation=valuation)
    price = 25.5 * valuation.fx("GBP", "EUR", "2027-06")
    assert value == pytest.approx((32.0 - price) * 30_000.0 * valuation.discount("2027-06"))


def test_without_a_benchmark_the_month_is_undiscounted_and_said():
    holdings = FxHoldings.from_rows([], [])
    valuation = ForwardValuation(holdings, "EUR", TODAY)
    assert valuation.discount("2027-06") == 1.0
    assert valuation.notes() == [
        "1 delivery month(s) not discounted: no EUR benchmark fixing held"
    ]


def test_credit_replacement_value_is_discounted_as_the_ladder_mtm():
    from eurogas_nexus.domain.risk.limits import CounterpartyLeg, CreditLine, credit_exposure

    line = CreditLine("CP", "Counterparty", 10_000_000.0, "EUR")
    leg = CounterpartyLeg(reference="c", kind="supply_contract", hub="TTF", currency="EUR",
                          first_gas_day=date(2028, 10, 1), last_gas_day=date(2028, 10, 31),
                          mwh_per_day=1_000.0, price=30.0)
    spot = credit_exposure(line, [leg], today=TODAY, mark=lambda hub, month: 32.0,
                           fx=lambda a, b: 1.0)
    valuation = ForwardValuation(_holdings(), "EUR", TODAY)
    present = credit_exposure(line, [leg], today=TODAY, mark=lambda hub, month: 32.0,
                              fx=lambda a, b: 1.0, valuation=valuation)
    assert spot.replacement_exposure == pytest.approx(62_000.0)
    assert present.replacement_exposure == pytest.approx(62_000.0 * valuation.discount("2028-10"))
