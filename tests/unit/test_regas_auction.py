"""The regas auction desk's arithmetic against hand-worked examples (exact decimals).

Example A (worked in docs/user/REGAS_AUCTION.md): a TTF slot of 1,000 GWh sent out evenly over
10-13 January 2027 at 30.00, 30.40, 30.80 and 31.20 EUR/MWh; losses 1 %; regas fee 450,000;
berthing 120,000; entry 0.50 and margin 0.25 EUR/MWh sent out; hedging at half a bid/offer of
0.025 EUR/MWh; late-ship buffer 50,000; financing 4.0 % for 30 days (ACT/365) on a cargo bought
at 28.00 EUR/MWh. By hand:

    E_out    = 1,000,000 x 0.99                       =    990,000 MWh
    revenue  = 247,500 x (30.00 + 30.40 + 30.80 + 31.20) = 30,294,000.00
    cargo    = 1,000,000 x 28.00                      = 28,000,000.00
    costs    = 450,000 + 120,000 + 495,000 + 24,750 + 92,054.79 + 247,500 + 50,000
             = 1,479,304.79
    max bid  = 30,294,000 - 1,479,304.79 - 28,000,000 =    814,695.21  (0.8147 EUR/MWh)
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal as D

import pytest

from eurogas_nexus.domain.lng.cargo_economics import MMBTU_PER_MWH, Valued, missing
from eurogas_nexus.domain.lng.regas_auction import (
    THERM_PER_MWH,
    CargoTerms,
    CostLine,
    Market,
    RegasAuctionError,
    SlotCase,
    evaluate,
    serialise,
)
from eurogas_nexus.domain.market.units import UnitConversionError, slot_energy_mwh
from eurogas_nexus.domain.valuation.quality import InputClass

S = InputClass.SOURCED
DAYS = tuple(date(2027, 1, 10 + i) for i in range(4))
PRICES = ("30.00", "30.40", "30.80", "31.20")


def same(a: D, b: D) -> bool:
    """Equal in 28-digit decimal arithmetic: a non-terminating division (x / 365) rounds at the
    28th digit, so two orders of the same sum may differ there and nowhere else."""

    return abs(a - b) < D("1E-15")


def v(value, klass=S, source="test") -> Valued:
    return Valued(D(str(value)), klass, source)


def market(prices=PRICES, hub="TTF", extra=None) -> Market:
    held = {(hub, day.isoformat()): v(p) for day, p in zip(DAYS, prices, strict=True)}
    for i in range(1, 9):
        held[(hub, (DAYS[-1] + timedelta(days=i)).isoformat())] = v(prices[-1])
    held.update(extra or {})
    return Market(held)


def lines(**overrides) -> tuple[CostLine, ...]:
    base = {
        "regas_fee": ("per_slot", "450000"),
        "losses": ("percent_of_energy", "1"),
        "berthing": ("per_slot", "120000"),
        "storage": ("per_slot", "0"),
        "entry": ("per_mwh_sent_out", "0.50"),
        "hedging": ("hedge_spread", "0.025"),
        "financing": ("financing", "0"),
        "margin": ("per_mwh_sent_out", "0.25"),
        "late_buffer": ("per_slot", "50000"),
        "other": ("per_slot", "0"),
    }
    out = []
    for key, (basis, value) in base.items():
        valued = overrides.get(key, v(value))
        origin = "computed" if basis == "financing" else "hand"
        out.append(CostLine(key, key.replace("_", " "), basis, valued, origin=origin))
    return tuple(out)


def case(**overrides) -> SlotCase:
    base = {
        "hub": "TTF",
        "currency": "EUR",
        "energy_mwh": v(1_000_000),
        "days": DAYS,
        "weights": (D(1),) * 4,
        "cargo": CargoTerms(kind="fixed", fixed_price=v("28.00"), price_unit="EUR/MWh"),
        "cost_lines": lines(),
        "level": v("0.60"),
        "rate_pct": v("4.0"),
    }
    base.update(overrides)
    return SlotCase(**base)


FINANCING_A = D(28_000_000) * D("4.0") / 100 * D(30) / D(365)
COSTS_A = (D(450_000) + D(120_000) + D(495_000) + D(24_750) + FINANCING_A + D(247_500)
           + D(50_000))
MAX_BID_A = D(30_294_000) - COSTS_A - D(28_000_000)


def test_fixed_cargo_hand_worked():
    answer = evaluate(case(), market())
    core = answer.core
    assert answer.computed and answer.state == "room"
    assert core.e_out == D(990_000)
    assert core.revenue == D(30_294_000)
    assert core.gross == D(30_600_000)
    assert core.cargo_cost == D(28_000_000)
    assert dict(core.lines)["financing"] == FINANCING_A
    assert core.max_bid == MAX_BID_A
    out = serialise(case(), answer)
    assert out["max_bid_total"] == "814695.21"
    assert out["max_bid_quoted"] == "0.8147"
    assert out["headroom"] == "0.2147"
    # One hedge: sell what is sent out, in January.
    assert [(h["hub"], h["month"], h["side"], h["mwh"], h["cost"]) for h in out["hedges"]] == [
        ("TTF", "2027-01", "sell", "990000.000", "24750.00")]


def test_waterfall_adds_up_exactly_and_everything_is_decimal():
    answer = evaluate(case(), market())
    steps = [amount for key, _, amount in answer.waterfall if key != "max_bid"]
    assert sum(steps, D(0)) == answer.core.max_bid
    assert all(isinstance(amount, D) for _, _, amount in answer.waterfall)
    assert answer.waterfall[1] == ("losses", "losses", D(-306_000))
    for key, _, delta, _ in answer.sensitivities:
        assert delta is None or isinstance(delta, D), key


def test_sensitivities_and_break_even_by_hand():
    answer = evaluate(case(), market())
    sens = {key: delta for key, _, delta, _ in answer.sensitivities}
    assert sens["price:TTF"] == D(990_000)
    # One day late: the days slide to 11-14 Jan (+247,500 x 1.20) and one more day of money.
    assert same(sens["delay"], D(297_000) - D(28_000_000) * D("0.04") / D(365))
    # One point more losses: 10,000 MWh less at 30.60, less entry, margin and hedging on it.
    assert sens["losses"] == D(-306_000) + D(7_500) + D(250)
    # Break-even: the average hub price at which the max bid meets the 0.60 level.
    shift = (D(600_000) - MAX_BID_A) / D(990_000)
    assert answer.break_even == D("30.6") + shift
    assert str(answer.break_even.quantize(D("0.0001"))) == "30.3831"


@pytest.mark.parametrize(("level", "state"), [("0.60", "room"), ("0.80", "at_limit"),
                                              ("0.82", "stop"), (None, "no_level")])
def test_headroom_states(level, state):
    held = None if level is None else v(level)
    assert evaluate(case(level=held), market()).state == state


def test_nothing_to_bid_is_stop_whatever_the_level():
    answer = evaluate(case(cargo=CargoTerms(kind="fixed", fixed_price=v("31.00"),
                                            price_unit="EUR/MWh"), level=None), market())
    assert answer.core.max_bid < 0 and answer.state == "stop"


def test_formula_cargo_partly_offsets_and_the_residual_is_shown():
    terms = CargoTerms(kind="formula", index_hub="TTF", pricing="send_out_days",
                       slope=v("1.0"), constant=v("-2.50"))
    answer = evaluate(case(cargo=terms, cost_lines=lines()), market())
    core = answer.core
    assert core.index_value == D("30.60")
    assert core.cargo_price == D("28.10")
    financing = D(28_100_000) * D("0.04") * D(30) / D(365)
    expected = D(30_294_000) - (D(450_000) + D(120_000) + D(495_000) + D(250) + financing
                                + D(247_500) + D(50_000)) - D(28_100_000)
    assert core.max_bid == expected
    # The formula prices the unloaded energy, the hub pays for what is sent out: buy 10,000.
    exposure = core.exposures[0]
    assert (exposure.long_mwh, exposure.formula_mwh, exposure.covered_mwh) == (
        D(990_000), D(1_000_000), D(990_000))
    assert [(h.side, h.mwh) for h in core.hedges] == [("buy", D(10_000))]
    sens = {key: delta for key, _, delta, _ in answer.sensitivities}
    assert same(sens["price:TTF"], D(-10_000) - D(1_000_000) * D("0.04") * D(30) / D(365))
    # The formula carries the hub price: a break-even price would decide nothing, and is not given.
    assert answer.break_even is None and answer.break_even_note == "price_does_not_decide"


def test_formula_on_another_hub_and_a_named_month():
    terms = CargoTerms(kind="formula", index_hub="NBP", pricing="month",
                       pricing_month="2026-12", slope=v("1.0"), constant=v("0"))
    extra = {("NBP", "2026-12"): v("27.00")}
    answer = evaluate(case(cargo=terms, index_fx=v("1.18"), index_currency="GBP"),
                      market(extra=extra), price_steps={"NBP": (D("0.01") * THERM_PER_MWH,
                                                                "1 p/th")})
    core = answer.core
    assert core.cargo_price == D("27.00") * D("1.18")
    hubs = {(h.hub, h.month, h.side) for h in core.hedges}
    assert hubs == {("TTF", "2027-01", "sell"), ("NBP", "2026-12", "buy")}
    sens = {key: (delta, step) for key, _, delta, step in answer.sensitivities}
    nbp_delta, step = sens["price:NBP"]
    assert step == "1 p/th"
    move = D("0.01") * THERM_PER_MWH
    assert same(nbp_delta, -(D(1_000_000) * move * D("1.18")) * (1 + D("0.04") * 30 / 365))
    assert "fx" in sens


def test_currency_difference_fixed_usd_per_mmbtu():
    terms = CargoTerms(kind="fixed", fixed_price=v("9.50"), price_unit="USD/MMBtu")
    answer = evaluate(case(cargo=terms, cargo_fx=v("0.92")), market())
    cargo = D(1_000_000) * D("9.50") * MMBTU_PER_MWH * D("0.92")
    assert answer.core.cargo_cost == cargo
    sens = {key: delta for key, _, delta, _ in answer.sensitivities}
    # +1 % in USD/EUR: the cargo costs 1 % more, and so does its financing.
    assert same(sens["fx"], -(cargo * D("0.01")) * (1 + D("0.04") * 30 / 365))


def test_uneven_send_out():
    answer = evaluate(case(weights=(D(1), D(2), D(3), D(4))), market())
    assert answer.core.revenue == D(990_000) * (D("30.00") * 1 + D("30.40") * 2
                                                + D("30.80") * 3 + D("31.20") * 4) / 10


def test_a_delay_reads_the_later_days():
    late = evaluate(case(delay_days=2), market())
    assert late.core.days[0] == date(2027, 1, 12)
    assert late.core.revenue == D(247_500) * (D("30.80") + D("31.20") * 3)


def test_volume_tolerance_gives_a_range():
    terms = CargoTerms(kind="fixed", fixed_price=v("28.00"), tolerance_pct=D(5))
    answer = evaluate(case(cargo=terms), market())
    assert answer.quoted_low < answer.quoted < answer.quoted_high


def test_missing_input_is_named_and_nothing_is_computed():
    held = market()
    prices = dict(held.prices)
    prices[("TTF", "2027-01-12")] = missing("no price held")
    answer = evaluate(case(cost_lines=lines(berthing=missing())), Market(prices))
    assert not answer.computed and answer.state == "missing_inputs"
    assert answer.core is None
    assert set(answer.missing) == {"price:TTF:2027-01-12", "cost:berthing"}


def test_simulated_price_is_an_illustration_not_a_bid_level():
    held = market()
    prices = dict(held.prices)
    prices[("TTF", "2027-01-10")] = v("30.00", InputClass.SIMULATED, "demo")
    answer = evaluate(case(), Market(prices))
    assert answer.computed and answer.simulated and answer.state == "illustration"


def test_hand_entered_inputs_are_listed():
    entered = Valued(D("0.60"), InputClass.ASSUMPTION, "entered by hand by trader on 2026-11-28")
    answer = evaluate(case(level=entered), market())
    assert "auction_level" in answer.hand_entered
    assert "cost:berthing" in answer.hand_entered


def test_per_slot_quotation():
    answer = evaluate(case(quotation="per_slot", level=v("700000")), market())
    assert answer.quoted == MAX_BID_A and answer.state == "room"


def test_bad_inputs_are_refused():
    with pytest.raises(RegasAuctionError):
        replace(case(), quotation="per_cargo")
    with pytest.raises(RegasAuctionError):
        CargoTerms(kind="formula", index_hub="")


def test_lng_m3_conversion_states_its_factor():
    assert slot_energy_mwh(D(150_000), "m3_lng", D("6.5")) == (D(975_000), D("6.5"))
    assert slot_energy_mwh(D(1000), "GWh") == (D(1_000_000), D(1000))
    with pytest.raises(UnitConversionError):
        slot_energy_mwh(D(150_000), "m3_lng")
    with pytest.raises(UnitConversionError):
        slot_energy_mwh(D(150_000), "m3_lng", D("11"))


def test_the_shipped_definition_parses_and_a_bad_one_says_what_to_change(tmp_path):
    from eurogas_nexus.application.regas_auction import load_definition, parse_definition
    from eurogas_nexus.domain.deals.formats import FormatError

    definition = load_definition({})
    keys = [cost.key for cost in definition.costs]
    assert keys[:2] == ["regas_fee", "losses"] and "financing" in keys
    assert definition.auction_leads == (120, 30)
    with pytest.raises(FormatError, match="basis"):
        parse_definition('[[cost]]\nkey = "x"\nbasis = "per_ship"\n')
    with pytest.raises(FormatError, match="computed"):
        parse_definition('[[cost]]\nkey = "f"\nbasis = "financing"\nfrom = "hand"\n')
