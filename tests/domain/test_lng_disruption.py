"""LNG-3: a disrupted cargo re-optimised across the portfolio, against hand-worked numbers.

The scenario is the owner's (docs/engineering/Commercial-Intelligence-V3/
06_ACCEPTANCE_SCENARIOS.md, "LNG-3 a disruption re-optimises the portfolio"); every price,
tariff and offer in it is illustrative, not a terminal's published figure.

Judged on 20 Jan 2027 09:00 UTC: the January contract stopped trading on 30 Dec, February
trades until 28 Jan; gas days to 21 Jan are nominated. Cargo ZEE-1 (1,000,000 MWh) held the
Zeebrugge slot from 26 Jan (10 days, 100,000 MWh/d send-out, 1,000,000 MWh storage declining
linearly) and is now due on 28 Jan (medium confidence: the ETA may be a day either way).
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from eurogas_nexus.domain.lng.disruption import (
    CapacityOffer,
    DeskTerms,
    DisruptionError,
    Market,
    Obligation,
    Portfolio,
    SlotTerms,
    Supply,
    disrupted,
    optimise,
    option_dict,
    result_dict,
)

NOW = datetime(2027, 1, 20, 9, tzinfo=UTC)
PRICES = {
    ("ZTP", "2027-01"): 30.00,
    ("ZTP", "2027-02"): 29.00,
    ("TTF", "2027-01"): 30.40,
    ("TTF", "2027-02"): 29.40,
    ("PEG", "2027-01"): 30.20,
    ("PEG", "2027-02"): 29.40,
    ("PVB", "2027-01"): 31.00,
    ("PVB", "2027-02"): 30.00,
}


def jan(day: int) -> date:
    return date(2027, 1, day)


def feb(day: int) -> date:
    return date(2027, 2, day)


def portfolio(
    eta: date = date(2027, 1, 28),
    *,
    curtailed: tuple[tuple[date, float], ...] = (),
    can_divert: bool = True,
    cepsa_firm: bool = True,
) -> Portfolio:
    cargo = {
        "energy_mwh": 1_000_000,
        "laytime_hours": 36,
        "demurrage_eur_per_day": 70_000,
        "boil_off_mwh_per_day": 1_000,
    }
    return Portfolio(
        supplies=(
            Supply(
                "A",
                "ZEE-1",
                arrival=eta,
                slot_id="Z",
                terminal="Zeebrugge",
                eta_confidence="medium",
                can_divert=can_divert,
                **cargo,
            ),
            Supply(
                "B",
                "GATE-1",
                arrival=jan(26),
                slot_id="G",
                terminal="Gate",
                eta_confidence="high",
                **cargo,
            ),
            Supply(
                "C",
                "HUE-1",
                arrival=jan(24),
                slot_id="H",
                terminal="Huelva",
                eta_confidence="high",
                **cargo,
            ),
            Supply(
                "P",
                "Pipeline ZTP",
                kind="pipeline",
                hub="ZTP",
                point="ZTP",
                daily_mwh=30_000,
                start=jan(20),
                end=feb(28),
                curtailed=curtailed,
                cost_eur_mwh=28.0,
            ),
        ),
        slots=(
            SlotTerms(
                "Z",
                "Zeebrugge",
                "ZTP",
                jan(26),
                10,
                100_000,
                1_000_000,
                release_value_eur_mwh=0.10,
                holder="A",
            ),
            SlotTerms("G", "Gate", "TTF", jan(28), 10, 100_000, 1_000_000, holder="B"),
            SlotTerms("H", "Huelva", "PVB", jan(24), 20, 50_000, 1_000_000, holder="C"),
            SlotTerms("D", "Dunkerque", "PEG", jan(30), 10, 100_000, 1_000_000),
        ),
        obligations=(
            Obligation(
                "cepsa",
                "Cepsa",
                "Huelva",
                "PVB",
                jan(24),
                feb(12),
                50_000,
                firm=cepsa_firm,
                penalty_eur_mwh=0.0 if cepsa_firm else 2.0,
            ),
        ),
        offers=(
            CapacityOffer(
                "z-borrow", "Zeebrugge", "borrow", jan(26), jan(27), 0.10, max_mwh_per_day=100_000
            ),
            CapacityOffer(
                "z-send", "Zeebrugge", "send_out", jan(26), feb(10), 0.15, max_mwh_per_day=50_000
            ),
            CapacityOffer(
                "z-store", "Zeebrugge", "storage", jan(26), feb(10), 0.02, max_mwh=300_000
            ),
            CapacityOffer(
                "z-int",
                "Zeebrugge",
                "interruptible",
                jan(26),
                feb(20),
                0.05,
                max_mwh_per_day=100_000,
                storage_price_eur_mwh_day=0.01,
            ),
        ),
        sailing_days={"Zeebrugge": 0, "Gate": 0, "Dunkerque": 0, "Huelva": -3},
    )


MARKET = Market(PRICES, NOW)


def by_key(result):
    return {option.key: option for option in result.options}


def test_only_the_late_cargo_is_disrupted():
    assert [s.supply_id for s in disrupted(portfolio())] == ["A"]
    assert disrupted(portfolio(eta=jan(26))) == []


def test_two_day_delay_values_each_option_against_the_plan():
    result = optimise(portfolio(), MARKET)
    options = by_key(result)
    expected = {
        # key: (expected, worst, cost, flexibility MWh, disrupted MWh)
        "A:stay+absorb": (-279_000, -417_000, 79_000, 800_000, 0),
        "A:stay+borrow": (-20_000, -158_000, 20_000, 1_000_000, 0),
        "A:stay+buy": (-36_000, -249_000, 36_000, 1_000_000, 0),
        "A:swap:B+absorb": (95_800, -330_200, -35_000, 1_000_000, 1_000_000),
        "A:divert:D+absorb": (-247_400, -347_600, 247_000, 0, 0),
    }
    for key, (pnl, worst, cost, flex, moved) in expected.items():
        o = options[key].objectives
        assert (o["pnl_expected"], o["pnl_worst"], o["cost"]) == (pnl, worst, cost), key
        assert (o["flexibility_mwh"], o["disrupted_mwh"]) == (flex, moved), key


def test_wait_and_absorb_breaks_down_as_worked_by_hand():
    option = by_key(optimise(portfolio(), MARKET))["A:stay+absorb"]
    parts = option.base.components()
    # 200,000 MWh moves from ZTP Jan (30.00) to ZTP Feb (29.00).
    assert parts["physical_moved"] == -200_000
    # Jan has stopped trading (short notice 0.25), Feb trades (0.01).
    assert parts["hedge_cost"] == -(200_000 * 0.25 + 200_000 * 0.01)
    # 200,000 MWh over the declining storage right for 8 days, 100,000 for one more, at
    # 0.01 per MWh-day interruptible; the 200,000 MWh tail on interruptible send-out at 0.05.
    assert parts["capacity_fees"] == -(1_700_000 * 0.01 + 200_000 * 0.05)
    assert [
        (s["scenario_id"], s["pnl"]) for s in option_dict(portfolio(), option)["scenarios"]
    ] == [
        ("base", -279_000),
        ("early", -140_000),
        ("late", -417_000),
        ("prices_up", -299_000),
        ("prices_down", -259_000),
    ]
    assert any("interruptible" in note for note in option.notes)


def test_borrow_keeps_the_planned_send_out_and_returns_the_gas_after_berthing():
    p = portfolio()
    option = by_key(optimise(p, MARKET))["A:stay+borrow"]
    leg = option_dict(p, option)["legs"][0]
    assert leg["borrowed"] == [
        {"gas_day": "2027-01-26", "mwh": 100_000.0},
        {"gas_day": "2027-01-27", "mwh": 100_000.0},
    ]
    assert leg["returned"] == {"gas_day": "2027-01-28", "mwh": 200_000.0}
    assert [d["mwh"] for d in leg["send_out"]] == [100_000.0] * 10
    assert option.base.components()["physical_moved"] == 0
    assert option.base.hedge_legs == []


def test_swap_with_the_normal_cargo_is_penalised_for_disturbing_it():
    result = optimise(portfolio(), MARKET)
    swap = by_key(result)["A:swap:B+absorb"]
    assert swap.feasible and swap.on_frontier
    assert swap.disrupted_supplies == ["B"]
    # GATE-1 would have waited 2 days at Gate: 12 h over laytime (35,000) and 2,000 MWh
    # boil-off at TTF Jan 30.40 (60,800); the swap saves it, and the book's hub-months match.
    assert swap.objectives["pnl_expected"] == 95_800
    # Score: 95,800 - 0.5 x (95,800 + 330,200) - 0.5 EUR/MWh x 1,000,000 MWh moved.
    assert round(swap.score) == -617_200


def test_swap_that_breaks_the_spanish_obligation_is_infeasible():
    option = by_key(optimise(portfolio(), MARKET))["A:swap:C+absorb"]
    assert not option.feasible
    assert not option.on_frontier
    assert any(
        "firm delivery to Cepsa at Huelva: 50,000 MWh short on 24 Jan" in r for r in option.reasons
    )
    cepsa = next(o for o in option.obligations if o["obligation_id"] == "cepsa")
    assert cepsa["short"][0] == {"gas_day": "2027-01-24", "mwh": 50_000.0}


def test_a_soft_obligation_costs_its_penalty_instead():
    option = by_key(optimise(portfolio(cepsa_firm=False), MARKET))["A:swap:C+absorb"]
    assert option.base.components()["obligation_penalty"] == -100_000
    # Still infeasible: ZEE-1 cannot fit at Huelva.
    assert not option.feasible
    assert not any("Cepsa" in r for r in option.reasons)


def test_frontier_and_recommendation_for_a_two_day_delay():
    result = optimise(portfolio(), MARKET)
    options = by_key(result)
    assert {o.key for o in result.frontier} == {"A:stay+borrow", "A:swap:B+absorb"}
    assert result.recommended.key == "A:stay+borrow"
    assert round(result.recommended.score) == -89_000
    borrow = options["A:stay+borrow"].option_id
    for key in ("A:stay+absorb", "A:stay+buy", "A:divert:D+absorb"):
        assert options[key].dominated_by == borrow
        assert "a better worst case" in options[key].dominated_why
    assert round(options["A:divert:D+absorb"].score) == -297_500


def test_divert_arithmetic_releases_the_slot_and_re_hedges():
    option = by_key(optimise(portfolio(), MARKET))["A:divert:D+absorb"]
    parts = option.base.components()
    assert parts == {
        "physical_moved": -40_000,
        "hedge_cost": -212_000,
        "cash_out": 0,
        "capacity_fees": 0,
        "demurrage": -35_000,
        "boil_off": -60_400,
        "stranded": 0,
        "release": 100_000,
        "swap_cost": 0,
        "obligation_penalty": 0,
    }
    legs = {
        (leg["hub"], leg["month"]): (leg["action"], leg["mwh"]) for leg in option.base.hedge_legs
    }
    assert legs == {
        ("ZTP", "2027-01"): ("buy back", 600_000),
        ("PEG", "2027-01"): ("sell", 200_000),
        ("ZTP", "2027-02"): ("buy back", 400_000),
        ("PEG", "2027-02"): ("sell", 800_000),
    }


def test_divert_is_infeasible_when_the_contract_forbids_it():
    option = by_key(optimise(portfolio(can_divert=False), MARKET))["A:divert:D+absorb"]
    assert not option.feasible
    assert any("diversion" in r for r in option.reasons)


def test_a_later_eta_flips_the_recommendation():
    first = optimise(portfolio(), MARKET)
    later = optimise(portfolio(eta=jan(30)), MARKET)
    options = by_key(later)
    assert later.recommended.key == "A:stay+borrow_buy"
    assert first.digest() != later.digest()
    assert {o.key for o in later.frontier} == {"A:stay+borrow_buy", "A:divert:D+absorb"}
    o = options["A:stay+borrow_buy"].objectives
    assert (o["pnl_expected"], o["pnl_worst"], o["cost"]) == (-182_000, -395_000, 82_000)
    o = options["A:divert:D+absorb"].objectives
    assert (o["pnl_expected"], o["pnl_worst"]) == (-152_000, -508_000)
    assert round(options["A:divert:D+absorb"].score) == -330_000
    assert round(later.recommended.score) == -288_500
    # A 4-day delay leaves 200,000 MWh to absorb after borrowing all the window allows.
    assert options["A:stay+borrow"].objectives["pnl_expected"] == -295_000
    assert options["A:stay+absorb"].objectives["pnl_expected"] == -554_000
    # GATE-1's slot cannot house ZEE-1 any longer.
    swap = options["A:swap:B+absorb"]
    assert not swap.feasible
    assert any("over the storage right" in r for r in swap.reasons)


def test_late_divert_strands_what_the_slot_cannot_hold():
    option = by_key(optimise(portfolio(eta=jan(30)), MARKET))["A:divert:D+absorb"]
    late = next(v for v in option.scenarios if v.scenario.scenario_id == "late")
    assert late.landings["A"].stranded_mwh == 100_000
    assert late.components()["stranded"] == -300_000


def test_same_inputs_same_answer():
    a = result_dict(portfolio(), optimise(portfolio(), MARKET))
    b = result_dict(portfolio(), optimise(portfolio(), MARKET))
    assert a == b
    assert a["recommended"] == a["frontier"][0]


def test_preference_weights_change_the_default_not_the_frontier():
    risk_neutral = DeskTerms(risk_weight=0.0, disruption_eur_per_mwh=0.0)
    result = optimise(portfolio(), MARKET, risk_neutral)
    assert {o.key for o in result.frontier} == {"A:stay+borrow", "A:swap:B+absorb"}
    assert result.recommended.key == "A:swap:B+absorb"


def test_pipeline_curtailment_absorbed_or_covered_from_a_cargo():
    p = portfolio(eta=jan(26), curtailed=((jan(28), 30_000), (jan(29), 30_000)))
    result = optimise(p, MARKET)
    options = by_key(result)
    absorb = options["P:absorb"]
    # 60,000 MWh of ZTP Jan not delivered: worth 30.00, not paid at 28.00; bought back short
    # notice at 0.25.
    assert absorb.objectives["pnl_expected"] == -60_000 * 2.0 - 60_000 * 0.25
    cover = options["P:cover:A"]
    # ZEE-1 sends 30,000 MWh more on 28 and 29 Jan on bought send-out (0.15) and 60,000 less
    # on its last day: ZTP Jan nets out, Feb is short 60,000 at 29.00 (trading, 0.01).
    assert cover.objectives["pnl_expected"] == (
        -60_000 * 29.0 + 60_000 * 28.0 - 60_000 * 0.01 - 60_000 * 0.15
    )
    assert cover.disrupted_supplies == ["A"]
    assert cover.objectives["disrupted_mwh"] == 60_000


def test_nominated_days_settle_at_cash_out():
    p = portfolio(eta=jan(26), curtailed=((jan(21), 30_000),))
    absorb = by_key(optimise(p, MARKET))["P:absorb"]
    parts = absorb.base.components()
    # 21 Jan is nominated: 30,000 MWh at 3 % of 30.00, no hedge trade.
    assert parts["cash_out"] == -27_000
    assert parts["hedge_cost"] == 0


def test_bad_inputs_are_refused():
    with pytest.raises(DisruptionError):
        SlotTerms("X", "T", "ZTP", jan(1), 0, 1, 1)
    with pytest.raises(DisruptionError):
        Supply("X", "X", arrival=None, energy_mwh=1)
    with pytest.raises(DisruptionError):
        CapacityOffer("o", "T", "lend", jan(1), jan(2), 0.1)
