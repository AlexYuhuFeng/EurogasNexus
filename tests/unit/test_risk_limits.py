"""Counterparty credit exposure and trader mandate usage."""

from __future__ import annotations

from datetime import date

from eurogas_nexus.domain.risk.limits import (
    CounterpartyLeg,
    CreditLine,
    Mandate,
    MandateLeg,
    credit_exposure,
    fx_lookup,
    mandate_usage,
)

TODAY = date(2026, 11, 1)
MARKS = {("TTF", "2026-11"): 32.0, ("TTF", "2026-12"): 34.0, ("NBP", "2026-11"): 80.0}


def mark(hub, month):
    return MARKS.get((hub, month))


FX = fx_lookup({"EUR": 1.0, "GBP": 0.8})


def line(**kw):
    base = dict(counterparty_id="EQN", name="Equinor ASA", limit_amount=1_000_000, currency="EUR")
    return CreditLine(**{**base, **kw})


def test_bought_below_market_is_replacement_exposure():
    leg = CounterpartyLeg(
        "C1", "supply_contract", "TTF", "EUR", date(2026, 11, 1), date(2026, 11, 30), 1000.0, 30.0
    )
    result = credit_exposure(line(), [leg], today=TODAY, mark=mark, fx=FX)
    assert result.replacement_exposure == 30 * 1000 * 2.0
    assert result.receivable_exposure == 0
    assert result.status == "ok"
    assert result.as_row()["headroom"] == 1_000_000 - 60_000


def test_netting_and_receivables_for_gas_sold():
    bought = CounterpartyLeg(
        "C1", "supply_contract", "TTF", "EUR", date(2026, 11, 1), date(2026, 11, 30), 1000.0, 30.0
    )  # +60k in our favour
    sold = CounterpartyLeg(
        "T1", "otc_trade", "TTF", "EUR", date(2026, 10, 1), date(2026, 11, 30), -2000.0, 31.0
    )  # -2000*30*(32-31) = -60k remaining
    result = credit_exposure(
        line(receivable_days=31), [bought, sold], today=TODAY, mark=mark, fx=FX
    )
    assert result.replacement_exposure == 0.0  # netted
    # October delivered and unpaid: 31 days x 2000 MWh x 31 EUR
    assert result.receivable_exposure == 31 * 2000 * 31.0


def test_collateral_status_and_fx():
    leg = CounterpartyLeg(
        "C2", "supply_contract", "NBP", "GBP", date(2026, 11, 1), date(2026, 11, 30), 10_000.0, 50.0
    )  # 30*10000*30 = 9.0m GBP
    result = credit_exposure(
        line(collateral_amount=1_000_000, limit_amount=10_000_000),
        [leg],
        today=TODAY,
        mark=mark,
        fx=FX,
    )
    assert round(result.replacement_exposure) == round(9_000_000 / 0.8)
    assert result.status == "breach"
    watch = credit_exposure(
        line(limit_amount=13_000_000, collateral_amount=1_000_000),
        [leg],
        today=TODAY,
        mark=mark,
        fx=FX,
    )
    assert watch.status == "watch"
    expired = credit_exposure(
        line(valid_until=date(2026, 10, 31)), [], today=TODAY, mark=mark, fx=FX
    )
    assert expired.status == "expired"


def test_missing_mark_or_fx_is_counted_not_hidden():
    no_mark = CounterpartyLeg(
        "C3", "supply_contract", "THE", "EUR", date(2026, 11, 1), date(2026, 11, 30), 1000.0, 30.0
    )
    no_fx = CounterpartyLeg(
        "C4", "supply_contract", "TTF", "USD", date(2026, 11, 1), date(2026, 11, 30), 1000.0, 30.0
    )
    result = credit_exposure(line(), [no_mark, no_fx], today=TODAY, mark=mark, fx=FX)
    assert result.unvalued_legs == 2 and result.status == "incomplete"


def mleg(
    ref,
    kind="financial",
    hub="TTF",
    book="",
    account="jdoe",
    first=date(2026, 11, 1),
    last=date(2026, 11, 30),
    q=1000.0,
):
    return MandateLeg(ref, kind, hub, book, account, first, last, q)


def test_mandate_size_hub_tenor_and_kind():
    mandate = Mandate(
        "M1",
        "jdoe",
        "J. Doe",
        book_ids=("NWE-PHYS",),
        hubs=("TTF", "THE"),
        max_net_mwh_per_month=40_000,
        max_tenor_months=6,
        physical_allowed=True,
        financial_allowed=True,
    )
    ok = mandate_usage(mandate, [mleg("O1", q=900.0)], today=TODAY)
    assert ok.status == "ok" and ok.largest_net_mwh == 27_000 and ok.largest_at == "TTF 2026-11"
    watch = mandate_usage(mandate, [mleg("O1")], today=TODAY)
    assert watch.status == "watch" and watch.as_row()["utilisation_pct"] == 75.0
    big = mandate_usage(mandate, [mleg("O1"), mleg("O2", q=500.0)], today=TODAY)
    assert big.status == "breach" and "over 40,000 MWh" in big.breaches[0]
    nbp = mandate_usage(mandate, [mleg("O3", hub="NBP")], today=TODAY)
    assert any("NBP is outside" in b for b in nbp.breaches)
    far = mandate_usage(
        mandate,
        [mleg("C1", kind="physical", book="NWE-PHYS", account="", last=date(2027, 6, 1), q=10.0)],
        today=TODAY,
    )
    assert any("beyond 6 months" in b for b in far.breaches)
    other = mandate_usage(mandate, [mleg("X", account="someone-else")], today=TODAY)
    assert other.legs == 0


def test_mandate_product_kind_and_expiry():
    mandate = Mandate(
        "M2", "jdoe", "J. Doe", financial_allowed=False, valid_until=date(2026, 12, 31)
    )
    usage = mandate_usage(mandate, [mleg("O1")], today=TODAY)
    assert usage.status == "breach" and "financial trades are not allowed" in usage.breaches[0]
    expired = Mandate("M3", "jdoe", "J. Doe", valid_until=date(2026, 10, 1))
    assert mandate_usage(expired, [], today=TODAY).status == "expired"


def test_hedge_policy_band_room_and_instruments():
    mandate = Mandate(
        "M4",
        "jdoe",
        "J. Doe",
        book_ids=("UK",),
        max_hedge_ratio_pct=80,
        min_hedge_ratio_pct=20,
        instruments=("physical", "future"),
    )
    supply = mleg("C1", kind="physical", book="UK", account="", q=1000.0, hub="NBP")
    hedge = mleg("H1", hub="NBP", q=-700.0, book="UK")  # 70 % hedged
    ok = mandate_usage(mandate, [supply, hedge], today=TODAY)
    assert ok.status == "ok", ok.breaches
    row = ok.as_row()
    assert row["hedge_ratio_range"] == "70-70%" and row["hedge_policy"] == "20-80%"
    assert row["hedge_room_mwh"] == 30 * 1000 * 0.10  # 10 % of a 30-day month left to the cap
    over = mandate_usage(mandate, [supply, mleg("H2", hub="NBP", q=-900.0, book="UK")], today=TODAY)
    assert over.status == "breach" and "above 80%" in over.breaches[0]
    under = mandate_usage(
        mandate, [supply, mleg("H3", hub="NBP", q=-100.0, book="UK")], today=TODAY
    )
    assert "below 20%" in under.breaches[0]
    option = MandateLeg(
        "O1",
        "financial",
        "NBP",
        "UK",
        "",
        date(2026, 11, 1),
        date(2026, 11, 30),
        -500.0,
        instrument="option",
    )
    banned = mandate_usage(mandate, [supply, option], today=TODAY)
    assert any("option is not an allowed instrument" in b for b in banned.breaches)
