"""Index-priced contracts: volume on the ladder, price exposure on the index (quant review 3.1).

A purchase priced at the TTF month-ahead index has no flat-price risk: the buyer pays what the
gas is worth. The ladder showed it as a 31,000 MWh long "0 % hedged", and a trader who "hedged"
it by selling futures created the open short the ladder then reported as flat.
"""

from datetime import date, timedelta

import pytest

from eurogas_nexus.domain.portfolio.position_ladder import (
    PositionLeg,
    build_ladder,
    historical_var,
    ladder_report,
    mark_to_market,
)
from eurogas_nexus.domain.risk.limits import (
    HedgeApproval,
    Mandate,
    MandateLeg,
    VolumeLeg,
    deal_hedge_usage,
    mandate_usage,
)

DEC, DEC_END = date(2026, 12, 1), date(2026, 12, 31)


def _indexed(hub="TTF", index="TTF", mwh=1_000.0, differential=0.5):
    return PositionLeg(
        "physical", hub, DEC, DEC_END, mwh, reference="ttf-ma-supply",
        index_hub=index, index_differential=differential,
    )


def test_an_index_priced_purchase_has_volume_but_no_flat_price_exposure():
    (row,) = build_ladder([_indexed()], horizon_start=DEC, horizon_end=DEC_END)
    assert row.physical_mwh == 31_000  # the physical volume stays visible
    assert row.net_mwh == 31_000  # net volume, as before
    assert row.index_mwh == -31_000
    assert row.price_exposure_mwh == 0
    assert row.hedge_ratio is None  # nothing to hedge, not "0 % hedged"
    data = ladder_report([_indexed()], horizon_start=DEC, horizon_end=DEC_END).as_dict()
    assert data["rows"][0]["price_exposure_mwh"] == 0
    assert data["totals"]["price_exposure_mwh"] == 0
    assert data["totals"]["net_mwh"] == 31_000


def test_selling_futures_against_an_indexed_purchase_is_an_open_short():
    hedge = PositionLeg("financial", "TTF", DEC, DEC_END, -1_000.0, price=30.0)
    (row,) = build_ladder([_indexed(), hedge], horizon_start=DEC, horizon_end=DEC_END)
    assert row.net_mwh == 0  # volume nets out ...
    assert row.price_exposure_mwh == -31_000  # ... but the book is short the flat price


def test_var_uses_price_exposure():
    closes = {date(2025, 1, 1) + timedelta(days=i): 30.0 + (i % 7) for i in range(300)}
    report = ladder_report(
        [_indexed()], horizon_start=DEC, horizon_end=DEC_END, daily_closes_by_hub={"TTF": closes}
    )
    assert report.var_95_1d == 0.0
    flat = PositionLeg("physical", "TTF", DEC, DEC_END, 1_000.0, price=30.0)
    assert historical_var({"TTF": 31_000}, {"TTF": closes})[0] > 0
    assert ladder_report(
        [flat], horizon_start=DEC, horizon_end=DEC_END, daily_closes_by_hub={"TTF": closes}
    ).var_95_1d > 0


def test_an_index_on_another_hub_is_a_basis_position():
    rows = build_ladder([_indexed(hub="NBP", index="TTF")], horizon_start=DEC,
                        horizon_end=DEC_END)
    by_hub = {row.hub: row for row in rows}
    assert by_hub["NBP"].price_exposure_mwh == 31_000
    assert by_hub["TTF"].price_exposure_mwh == -31_000
    assert by_hub["TTF"].physical_mwh == 0


def test_an_indexed_leg_is_valued_on_its_differential():
    marks = {("TTF", "2026-12"): 32.0}
    value, missing = mark_to_market(
        [_indexed(differential=0.5)], marks, horizon_start=DEC, horizon_end=DEC_END
    )
    # Pays TTF + 0.5 for gas worth TTF: -0.5 x 31,000.
    assert value == pytest.approx(-15_500) and missing == 0


def test_mandate_net_and_hedge_band_use_price_exposure():
    mandate = Mandate("m1", "trader", "T", book_ids=("b",), max_net_mwh_per_month=10_000,
                      min_hedge_ratio_pct=50, max_hedge_ratio_pct=100)
    leg = MandateLeg("c", "physical", "TTF", "b", "", DEC, DEC_END, 1_000.0, index_hub="TTF")
    usage = mandate_usage(mandate, [leg], today=date(2026, 11, 26))
    assert usage.largest_net_mwh == 0  # no size breach for a hedged-by-nature purchase
    assert usage.breaches == []  # and no "0 % hedged" breach
    sold = MandateLeg("h", "financial", "TTF", "b", "trader", DEC, DEC_END, -1_000.0)
    usage = mandate_usage(mandate, [leg, sold], today=date(2026, 11, 26))
    assert usage.largest_net_mwh == -31_000
    assert any("is over" in text for text in usage.breaches)


def test_a_deal_hedge_band_on_an_indexed_contract_has_no_flat_exposure_to_hedge():
    approval = HedgeApproval("c", 60, 80)
    contract = VolumeLeg("c", DEC, DEC_END, 1_000.0, floating=True)
    usage = deal_hedge_usage(approval, [contract], [], today=date(2026, 11, 26))
    (month,) = usage["months"]
    assert month["contract_mwh"] == 31_000
    assert month["price_exposure_mwh"] == 0
    assert month["hedge_pct"] is None
    assert usage["status"] == "ok"
    hedge = VolumeLeg("h", DEC, DEC_END, -1_000.0)
    usage = deal_hedge_usage(approval, [contract], [hedge], today=date(2026, 11, 26))
    assert usage["status"] == "breach"
    assert usage["breach_notes"][0]["code"] == "APPROVAL_INDEXED_HEDGE_OPEN"
