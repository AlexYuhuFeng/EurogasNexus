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

from dataclasses import replace
from datetime import UTC, date, datetime

import pytest

from eurogas_nexus.domain.lng.disruption import (
    BerthCall,
    BerthRule,
    CapacityOffer,
    DeskTerms,
    DisruptionError,
    Market,
    Obligation,
    Portfolio,
    SlotTerms,
    SubstituteSource,
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
    liquidated_damages: float | None = None,
    huelva_interruptible: bool = True,
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
                penalty_eur_mwh=liquidated_damages if cepsa_firm else 2.0,
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
        )
        + (
            # LNG-4: interruptible send-out and storage at Huelva, so ZEE-1 can physically land
            # there and the Huelva swap is judged on the contract it breaks.
            (
                CapacityOffer(
                    "h-int",
                    "Huelva",
                    "interruptible",
                    jan(24),
                    feb(20),
                    0.05,
                    max_mwh_per_day=50_000,
                    storage_price_eur_mwh_day=0.01,
                ),
            )
            if huelva_interruptible
            else ()
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


def test_swap_that_breaks_the_spanish_obligation_is_an_option_flagged_as_a_breach():
    """LNG-4: the Huelva swap is listed, possible and choosable, flagged as breaking the Cepsa
    firm delivery, with the penalty said not to be held (it is not in the contract data)."""

    result = optimise(portfolio(), MARKET)
    option = by_key(result)["A:swap:C+absorb"]
    assert option.feasible and option.reasons == []
    # 2026-11-26: a swap among the book's own cargoes is flagged as needing the terminals'
    # approval (the berth rule's default); it needs no counterparty quote.
    assert option.flags == {
        "physically_possible": True,
        "contract_breach": True,
        "disrupts_normal_cargo": True,
        "needs_terminal_approval": True,
        "counterparty_quote_pending": False,
    }
    assert option.approvals == [
        "Huelva to accept ZEE-1 in place of the ship nominated for the slot",
        "Zeebrugge to accept HUE-1 in place of the ship nominated for the slot",
    ]
    (breach,) = option.breaches
    assert breach["kind"] == "short_delivery"
    assert breach["text"].startswith(
        "breaks the firm delivery to Cepsa at Huelva: 50,000 MWh short on 24 Jan"
    )
    assert "penalty is not held" in breach["text"]
    assert (breach["shortfall_mwh"], breach["penalty_held"], breach["exposure_eur"]) == (
        50_000,
        False,
        None,
    )
    assert option.disrupts == [
        {
            "supply_id": "C",
            "label": "HUE-1",
            "kind": "lng",
            "mwh": 1_000_000,
            "from": "Huelva",
            "to": "Zeebrugge",
            "cause": "placed elsewhere by the option",
        }
    ]
    o = option.objectives
    assert (o["pnl_expected"], o["pnl_worst"], o["cost"]) == (-215_000, -289_500, 65_000)
    assert option.rank == 6 and not option.on_frontier
    cepsa = next(o for o in option.obligations if o["obligation_id"] == "cepsa")
    assert cepsa["short"][0] == {"gas_day": "2027-01-24", "mwh": 50_000.0}


def test_a_breach_is_valued_at_liquidated_damages_where_the_contract_holds_them():
    option = by_key(optimise(portfolio(liquidated_damages=2.5), MARKET))["A:swap:C+absorb"]
    assert option.base.components()["contract_exposure"] == -125_000
    assert option.objectives["pnl_expected"] == -340_000
    assert "liquidated damages 2.50 EUR/MWh = 125,000 EUR" in option.breaches[0]["text"]


def test_without_capacity_at_huelva_the_swap_is_not_possible_but_its_breach_is_still_named():
    option = by_key(optimise(portfolio(huelva_interruptible=False), MARKET))["A:swap:C+absorb"]
    assert not option.feasible and option.rank is None
    assert any("over the storage right" in r for r in option.reasons)
    assert option.flags["contract_breach"]


def test_a_soft_obligation_costs_its_penalty_instead():
    option = by_key(optimise(portfolio(cepsa_firm=False), MARKET))["A:swap:C+absorb"]
    assert option.base.components()["obligation_penalty"] == -100_000
    assert option.feasible and option.breaches == []


def test_frontier_and_recommended_set_for_a_two_day_delay():
    result = optimise(portfolio(), MARKET)
    options = by_key(result)
    assert {o.key for o in result.frontier} == {"A:stay+borrow", "A:swap:B+absorb"}
    assert [(r.basis, r.option.key) for r in result.recommended_set] == [
        ("clean", "A:stay+borrow"),
        ("best_expected", "A:swap:B+absorb"),
    ]
    assert result.recommended.key == "A:stay+borrow"
    swap = options["A:swap:B+absorb"]
    assert swap.recommended_why[0].startswith("Highest expected P&L that breaks no contract")
    assert "GATE-1 1,000,000 MWh" in swap.recommended_why[0]
    assert round(result.recommended.score) == -89_000
    assert [o.key for o in result.options if o.rank] == [
        "A:stay+borrow",
        "A:stay+buy",
        "A:divert:D+absorb",
        "A:stay+absorb",
        "A:swap:B+absorb",
        "A:swap:C+absorb",
    ]
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
        "contract_exposure": 0,
        "substitute_cost": 0,
        "counterparty_quote": 0,
        "knock_on": 0,
        "capacity_forgone": 0,
        "storage_forgone": 0,
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
    # The spare Dunkerque slot holds no release value and the desk holds no other use for it:
    # the value forgone is stated as not known, not as zero.
    forgone = next(line for line in option.base.lines if line["label"] == "forgone D")
    assert forgone["basis"] == "opportunity" and "not known" in forgone["text"]


def test_every_cost_line_names_its_sources():
    p = portfolio()
    option = by_key(optimise(p, MARKET))["A:divert:D+absorb"]
    lines = option_dict(p, option, detail=True)["arithmetic"]
    assert lines and all(line["sources"] for line in lines)
    by_label = {line["label"]: line for line in lines}
    assert by_label["hedge ZTP 2027-01"]["sources"] == [
        "short_notice_premium_eur_mwh: desk standard"
    ]
    assert by_label["physical PEG 2027-01"]["sources"] == ["PEG 2027-01 price: month mark"]
    assert by_label["demurrage A"]["sources"] == ["voyage terms"]


def test_divert_without_the_right_is_kept_as_a_breach():
    option = by_key(optimise(portfolio(can_divert=False), MARKET))["A:divert:D+absorb"]
    assert option.feasible
    (breach,) = option.breaches
    assert breach["kind"] == "no_diversion_right" and "diversion" in breach["text"]


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
    assert a["recommended_set"][0]["basis"] == "clean"


def test_preference_weights_reorder_the_options_not_the_frontier():
    risk_neutral = DeskTerms(risk_weight=0.0, disruption_eur_per_mwh=0.0)
    result = optimise(portfolio(), MARKET, risk_neutral)
    assert {o.key for o in result.frontier} == {"A:stay+borrow", "A:swap:B+absorb"}
    assert [(r.basis, r.option.key) for r in result.recommended_set] == [
        ("clean", "A:stay+borrow"),
        ("best_expected", "A:swap:B+absorb"),
    ]
    swap = by_key(result)["A:swap:B+absorb"]
    assert swap.rank == 1 and swap.recommended_as == ["best_expected"]


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


# ------------------------------------------------------------- LNG-4: opportunity cost

#: The owner's scenario as LNG-4 extends it (2026-11-25): the book's long-term Dunkerque slot
#: is worth 0.05 EUR/MWh released, another company's ship is due at the Dunkerque berth on
#: 30 Jan, a Dunkerque call holds the berth two gas days, Montoir offers a spot slot from 29 Jan
#: at 0.15 EUR/MWh of send-out right, and PEG gas can reach PVB over VIP Pirineos at
#: 1.20 EUR/MWh. Illustrative figures. Since 2026-11-26 the call's own laytime, demurrage and
#: boil-off are not engine inputs: another company's demurrage is never in the book's P&L.
DUNKERQUE_CALL = BerthCall(
    "dk-1",
    "Dunkerque",
    "another user's carrier",
    jan(30),
    hub="PEG",
    berth_days=2,
    counterparty="Other Shipper (illustrative)",
    source="Dunkerque line-up (illustrative)",
)
MONTOIR_SPOT = CapacityOffer(
    "m-spot",
    "Montoir",
    "slot",
    jan(29),
    feb(7),
    0.15,
    max_mwh_per_day=100_000,
    max_mwh=1_000_000,
    hub="PEG",
    basis="quoted",
    source="Montoir spot slot quote (illustrative)",
)
PEG_TO_PVB = SubstituteSource(
    "peg-hub",
    "hub",
    "PEG gas over VIP Pirineos",
    "PVB",
    jan(20),
    feb(28),
    60_000,
    price_hub="PEG",
    premium_eur_mwh=0.25,
    transport_eur_mwh=1.20,
    sources={"gas": "PEG 2027-01 mark", "transport": "VIP Pirineos tariff (illustrative)"},
)


def extended(base: Portfolio | None = None, *, call: bool = True, **changes) -> Portfolio:
    p = base or portfolio(**changes)
    return replace(
        p,
        slots=tuple(
            replace(s, release_value_eur_mwh=0.05) if s.slot_id == "D" else s for s in p.slots
        ),
        berth_calls=(DUNKERQUE_CALL,) if call else (),
        berth_days={"Dunkerque": 2},
        offers=p.offers + (MONTOIR_SPOT,),
        sailing_days={**p.sailing_days, "Montoir": 0},
        substitutes=(PEG_TO_PVB,),
    )


def test_another_companys_wait_is_stated_and_its_demurrage_is_not_in_the_books_pnl():
    """The owner, 2026-11-26: another company's demurrage is never counted in the book's P&L.
    (Until then the carrier's 48 h against 24 h laytime at 65,000 EUR/day and its boil-off,
    125,400 EUR, were an opportunity cost of the diversion.)"""

    result = optimise(extended(), MARKET)
    options = by_key(result)
    divert = options["A:divert:D+absorb"]
    # ZEE-1 reaches Dunkerque on 28 Jan, inside its arrival window (the spare slot from 30 Jan),
    # so it is berthed in turn; the carrier due on 30 Jan is ready the same day and arrived
    # later, so it berths after ZEE-1. Using the spare slot forgoes 1,000,000 MWh x 0.05.
    parts = divert.base.components()
    assert (parts["counterparty_quote"], parts["capacity_forgone"]) == (0, -50_000)
    assert "displaced_calls" not in parts
    assert divert.base.split() == {
        "direct_pnl": -247_400,
        "opportunity_cost": 50_000,
        "pnl": -297_400,
    }
    (forgone,) = divert.base.opportunity
    assert forgone["kind"] == "capacity_forgone" and forgone["value_eur"] == -50_000
    (call,) = divert.base.counterparty
    assert (call["kind"], call["owner"], call["label"], call["delay_days"]) == (
        "berth_delay",
        "third_party",
        "another user's carrier",
        2,
    )
    assert (call["in_pnl"], call["value_eur"], call["held_by"]) == (False, None, "ZEE-1")
    assert "not in the P&L" in call["text"]
    assert not any(line["label"].startswith("displaced") for line in divert.base.lines)
    assert not divert.quotes and not divert.flags["counterparty_quote_pending"]
    o = divert.objectives
    assert (o["direct_pnl_expected"], o["opportunity_cost"], o["pnl_expected"]) == (
        -247_400,
        50_000,
        -297_400,
    )
    leg = option_dict(extended(), divert)["legs"][0]
    assert (leg["on_time"], leg["berth_priority"], leg["berth"]) == (True, "in_turn", "2027-01-30")
    assert option_dict(extended(), divert)["counterparty_effects"][0]["call_id"] == "dk-1"


def test_contracted_or_spot_terminal_comes_out_of_the_full_valuation():
    """Without the value it forgoes the long-term Dunkerque slot ranks above the Montoir spot
    slot; with the slot's release value forgone, the spot slot ranks above it. (2026-11-26:
    the carrier's demurrage at Dunkerque is no longer counted, so the diversion now ranks above
    staying and absorbing.)"""

    def ranks(result):
        return {o.key: o.rank for o in result.options}

    plain = ranks(optimise(extended(call=False, base=portfolio()), MARKET))
    full = optimise(extended(), MARKET)
    spot = by_key(full)["A:spot:m-spot+absorb"]
    assert spot.objectives["pnl_expected"] == -276_200
    assert spot.base.components()["capacity_fees"] == -150_000
    assert spot.base.opportunity == []
    full_ranks = ranks(full)
    assert full_ranks["A:spot:m-spot+absorb"] < full_ranks["A:divert:D+absorb"]
    assert [o.key for o in full.options if o.rank][:5] == [
        "A:stay+borrow",
        "A:stay+buy",
        "A:spot:m-spot+absorb",
        "A:divert:D+absorb",
        "A:stay+absorb",
    ]
    # Without the call and with no release value held, the contracted slot is the better one.
    no_release = optimise(replace(extended(call=False), slots=portfolio().slots), MARKET)
    plain = ranks(no_release)
    assert plain["A:divert:D+absorb"] < plain["A:spot:m-spot+absorb"]


def test_displacing_an_own_cargo_flags_it_and_costs_its_knock_on():
    p = portfolio()
    own = Supply(
        "E",
        "DUN-2",
        arrival=jan(30),
        slot_id="D2",
        terminal="Dunkerque",
        eta_confidence="high",
        energy_mwh=1_000_000,
        laytime_hours=36,
        demurrage_eur_per_day=70_000,
        boil_off_mwh_per_day=1_000,
    )
    p = replace(
        p,
        supplies=p.supplies + (own,),
        slots=p.slots
        + (SlotTerms("D2", "Dunkerque", "PEG", jan(30), 12, 100_000, 1_000_000, holder="E"),),
        berth_days={"Dunkerque": 2},
    )
    divert = by_key(optimise(p, MARKET))["A:divert:D+absorb"]
    assert divert.flags["disrupts_normal_cargo"]
    (moved,) = divert.disrupts
    assert moved["label"] == "DUN-2" and moved["cause"].startswith("waits 2 gas day(s)")
    (hit,) = divert.base.opportunity[:1]
    assert (hit["kind"], hit["owner"], hit["label"], hit["delay_days"]) == (
        "berth_delay",
        "own",
        "DUN-2",
        2,
    )
    # DUN-2 waits 48 h against 36 h laytime at 70,000 EUR/day and boils off 2,000 MWh, priced
    # at PEG Feb 29.40 (it now berths on 1 Feb).
    assert hit["demurrage_eur"] == -35_000 and hit["boil_off_eur"] == -58_800
    assert divert.base.knock_on > 93_800
    assert divert.base.direct_pnl == -247_400


def test_shared_send_out_taken_by_the_late_cargo_is_a_knock_on_on_the_next():
    """Two cargoes at Zeebrugge share the interruptible send-out (50,000 MWh/d): the late one
    takes it first, so the other sends its excess out later and holds it in tank longer."""

    sibling = Supply(
        "Y",
        "ZEE-2",
        arrival=jan(26),
        slot_id="Z2",
        terminal="Zeebrugge",
        eta_confidence="high",
        energy_mwh=1_100_000,
        laytime_hours=36,
    )
    p = portfolio()
    p = replace(
        p,
        supplies=p.supplies + (sibling,),
        slots=p.slots
        + (SlotTerms("Z2", "Zeebrugge", "ZTP", jan(26), 10, 100_000, 1_000_000, holder="Y"),),
        offers=tuple(
            replace(o, max_mwh_per_day=50_000) if o.offer_id == "z-int" else o for o in p.offers
        ),
    )
    absorb = by_key(optimise(p, MARKET))["A:stay+absorb"]
    (squeezed,) = [x for x in absorb.base.opportunity if x["label"] == "ZEE-2"]
    assert squeezed["kind"] == "capacity_squeezed" and squeezed["mwh_moved"] > 0
    assert absorb.base.knock_on > 0
    assert absorb.base.pnl == absorb.base.direct_pnl - absorb.base.opportunity_cost


# ----------------------------------------------- berth priority (the owner, 2026-11-26)

#: A Zeebrugge line-up for the berth rule: ZEE-2, a cargo of the book, holds a Zeebrugge slot
#: from 28 Jan and arrives on time that day; and/or another company's carrier is due at the
#: Zeebrugge berth on 28 Jan. A call holds the Zeebrugge berth two gas days. ZEE-1 (slot from
#: 26 Jan) arrives on 28 Jan, after its one-day arrival window. Illustrative figures.
OTHER_SHIPPER = "Other Shipper (illustrative)"


def zeebrugge_line_up(
    *, own: bool = True, call: bool = False, quote: float | None = None, rule=None
) -> Portfolio:
    p = portfolio()
    supplies, slots, calls = list(p.supplies), list(p.slots), []
    if own:
        supplies.append(
            Supply(
                "E",
                "ZEE-2",
                arrival=jan(28),
                slot_id="Z2",
                terminal="Zeebrugge",
                eta_confidence="high",
                energy_mwh=1_000_000,
                laytime_hours=36,
                demurrage_eur_per_day=70_000,
                boil_off_mwh_per_day=1_000,
            )
        )
        slots.append(
            SlotTerms("Z2", "Zeebrugge", "ZTP", jan(28), 10, 100_000, 1_000_000, holder="E")
        )
    if call:
        calls.append(
            BerthCall(
                "zb-1",
                "Zeebrugge",
                "Other Shipper's carrier",
                jan(28),
                hub="ZTP",
                berth_days=2,
                counterparty=OTHER_SHIPPER,
                quote_eur=quote,
                quote_source="" if quote is None else "Other Shipper quote (illustrative)",
                source="Zeebrugge line-up (illustrative)",
            )
        )
    return replace(
        p,
        supplies=tuple(supplies),
        slots=tuple(slots),
        berth_calls=tuple(calls),
        berth_days={"Zeebrugge": 2},
        berth_rules={} if rule is None else {"Zeebrugge": rule},
    )


def test_an_on_time_ship_keeps_its_slot_and_the_late_one_takes_the_next_free_gap():
    p = zeebrugge_line_up()
    stay = by_key(optimise(p, MARKET))["A:stay+absorb"]
    landed = stay.base.landings
    # ZEE-2 arrives within its window and is berthed in turn, as planned.
    assert (landed["E"].berth, landed["E"].hold_days, landed["E"].priority) == (
        jan(28),
        0,
        "in_turn",
    )
    assert not landed["E"].late
    # ZEE-1 is late: it loses priority and berths in the first free gap after ZEE-2's two days.
    a = landed["A"]
    assert (a.berth, a.hold_days, a.priority, a.late, a.held_by) == (
        jan(30),
        2,
        "next_free_gap",
        True,
        "ZEE-2",
    )
    assert not [x for x in stay.base.opportunity if x["kind"] == "berth_delay"]
    assert not any(d["supply_id"] == "E" and "waits" in d["cause"] for d in stay.disrupts)
    assert any("after its arrival window at Zeebrugge" in note for note in stay.notes)
    leg = option_dict(p, stay)["legs"][0]
    assert (leg["on_time"], leg["berth_priority"], leg["berth"]) == (
        False,
        "next_free_gap",
        "2027-01-30",
    )
    assert leg["berth_rule"]["basis"] == "default" and leg["berth_rule"]["citation"] is None


def test_a_late_ships_laytime_starts_at_berthing():
    stay = by_key(optimise(zeebrugge_line_up(), MARKET))["A:stay+absorb"]
    a = stay.base.landings["A"]
    # 48 h at anchor against 36 h laytime, but laytime starts at berthing: no demurrage; the
    # 2,000 MWh boiled off while waiting is still a cost.
    assert (a.wait_days, a.laytime_wait_days, a.laytime_from) == (2, 0, "berthing")
    assert a.demurrage_eur == 0 and a.boil_off_mwh == 2_000
    assert stay.base.components()["demurrage"] == 0
    # A rule that starts a late ship's laytime at its arrival counts the wait: 12 h over
    # laytime at 70,000 EUR/day.
    at_arrival = BerthRule("Zeebrugge", late_laytime_from="arrival", basis="assumption")
    stay = by_key(optimise(zeebrugge_line_up(rule=at_arrival), MARKET))["A:stay+absorb"]
    assert stay.base.landings["A"].demurrage_eur == 35_000
    assert stay.base.components()["demurrage"] == -35_000


def test_a_swap_with_an_own_cargo_carries_its_cost_and_needs_terminal_approval():
    p = zeebrugge_line_up()
    result = optimise(p, MARKET)
    swap = by_key(result)["A:stay/berth_swap:E+absorb"]
    assert swap.kind == "berth_swap" and swap.feasible
    assert swap.flags["needs_terminal_approval"] and not swap.flags["counterparty_quote_pending"]
    assert swap.approvals == [
        "Zeebrugge to accept the change of berth order between ZEE-1 and ZEE-2"
    ]
    assert swap.quotes == []
    landed = swap.base.landings
    assert (landed["A"].berth, landed["A"].priority) == (jan(28), "swap")
    assert (landed["E"].berth, landed["E"].priority, landed["E"].hold_days) == (
        jan(30),
        "next_free_gap",
        2,
    )
    # ZEE-2 was on time, so its wait counts from its arrival: 48 h against 36 h at 70,000
    # EUR/day, and 2,000 MWh boils off at ZTP Jan 30.00. The book pays it: a knock-on.
    (hit,) = [x for x in swap.base.opportunity if x["kind"] == "berth_delay"]
    assert (hit["owner"], hit["label"], hit["delay_days"], hit["held_by"]) == (
        "own",
        "ZEE-2",
        2,
        "ZEE-1",
    )
    assert (hit["demurrage_eur"], hit["boil_off_eur"]) == (-35_000, -60_000)
    assert swap.base.knock_on > 95_000
    assert [d["supply_id"] for d in swap.disrupts] == ["E"]
    # A change of slot among the book's own cargoes says so in the recommended reason too.
    best = next(r for r in result.recommended_set if r.basis == "best_expected")
    assert best.option.key == "A:swap:B+absorb"
    assert best.reason.endswith("needs the terminal's approval.")


def test_a_swap_with_another_companys_slot_carries_a_quote_and_no_demurrage_line():
    p = zeebrugge_line_up(own=False, call=True)
    result = optimise(p, MARKET)
    options = by_key(result)
    # Staying: ZEE-1 is late and waits for the carrier's two gas days, without displacing it.
    a = options["A:stay+absorb"].base.landings["A"]
    assert (a.berth, a.held_by, a.demurrage_eur) == (jan(30), "Other Shipper's carrier", 0)
    swap = options["A:stay/counterparty_swap:zb-1+absorb"]
    assert swap.kind == "counterparty_swap" and swap.feasible
    assert swap.flags["counterparty_quote_pending"] and swap.flags["needs_terminal_approval"]
    (quote,) = swap.quotes
    assert (quote["status"], quote["amount_eur"], quote["counterparty"]) == (
        "pending",
        None,
        OTHER_SHIPPER,
    )
    assert swap.base.landings["A"].berth == jan(28)
    # No demurrage line for the other company's ship: one quote line, pending, not in the P&L.
    labels = [line["label"] for line in swap.base.lines]
    assert "quote zb-1" in labels and not any("zb-1" in x and x != "quote zb-1" for x in labels)
    assert swap.base.components()["counterparty_quote"] == 0
    assert swap.base.components()["demurrage"] == 0
    (effect,) = swap.base.counterparty
    assert (effect["call_id"], effect["delay_days"], effect["swapped"], effect["in_pnl"]) == (
        "zb-1",
        2,
        True,
        False,
    )
    assert "its cost is their quote, not their demurrage" in effect["text"]
    # Its cost is not known yet: not compared on the frontier, ranked after every option whose
    # cost is known, and not recommended.
    assert not swap.on_frontier and swap.dominated_why == [
        f"its cost waits on a quote from {OTHER_SHIPPER}"
    ]
    assert swap.rank > max(o.rank for o in result.options if o.rank and not o.quote_pending)
    assert swap.option_id not in {r.option.option_id for r in result.recommended_set}

    pending, pending_cost = swap.base.pnl, swap.objectives["cost"]
    entered = by_key(optimise(zeebrugge_line_up(own=False, call=True, quote=40_000), MARKET))
    swap = entered["A:stay/counterparty_swap:zb-1+absorb"]
    (quote,) = swap.quotes
    assert (quote["status"], quote["amount_eur"]) == ("entered", 40_000)
    assert swap.base.components()["counterparty_quote"] == -40_000
    assert swap.base.pnl == pending - 40_000
    assert swap.objectives["cost"] == pending_cost + 40_000
    assert not swap.flags["counterparty_quote_pending"]
    line = next(x for x in swap.base.lines if x["label"] == "quote zb-1")
    assert line["value"] == -40_000 and line["sources"] == ["Other Shipper quote (illustrative)"]


def test_a_terminal_specific_rule_is_used_and_cited():
    rule = BerthRule(
        "Zeebrugge",
        arrival_window_days=3,
        basis="example",
        citation="example access code, berthing clause (illustrative, not a published code)",
    )
    p = zeebrugge_line_up(rule=rule)
    result = optimise(p, MARKET)
    options = by_key(result)
    stay = options["A:stay+absorb"]
    # Under this rule ZEE-1's window runs to 28 Jan: it is on time and berthed in turn (its slot
    # starts first), so ZEE-2 waits; no swap of berth turn is offered, none being needed.
    a, e = stay.base.landings["A"], stay.base.landings["E"]
    assert (a.berth, a.late, a.priority) == (jan(28), False, "in_turn")
    assert (e.berth, e.hold_days) == (jan(30), 2)
    assert not [key for key in options if "berth_swap" in key]
    leg = option_dict(p, stay)["legs"][0]
    assert leg["berth_rule"]["basis"] == "example"
    assert leg["berth_rule"]["citation"] == rule.citation
    assert rule.citation in leg["berth_rule"]["rule"]
    assert "not a published code" in leg["berth_rule"]["rule"]
    zeebrugge = next(
        r for r in result_dict(p, result)["berth_rules"] if r["terminal"] == "Zeebrugge"
    )
    assert zeebrugge["arrival_window_days"] == 3
    gate = next(r for r in result_dict(p, result)["berth_rules"] if r["terminal"] == "Gate")
    assert gate["basis"] == "default" and gate["rule"].startswith("default berth rule")
    with pytest.raises(DisruptionError):
        BerthRule("Zeebrugge", basis="terminal_code")  # a code's rule must be cited


# ------------------------------------------------------- LNG-4: substitute supply


def test_hub_gas_plus_transport_covers_the_cepsa_shortfall_and_is_compared():
    result = optimise(extended(), MARKET)
    options = by_key(result)
    covered = options["A:swap:C+absorb + cover:peg-hub"]
    assert covered.kind == "substitute" and covered.feasible
    assert covered.breaches == [] and covered.flags["contract_breach"] is False
    assert covered.flags["disrupts_normal_cargo"]
    (cover,) = covered.covers
    assert cover.days == ((jan(24), 50_000),)
    # 50,000 MWh at PEG Jan 30.20 + 0.25 short notice + 1.20 transport = 31.65 EUR/MWh.
    assert covered.base.components()["substitute_cost"] == -1_582_500
    line = next(x for x in covered.base.lines if x["label"] == "substitute peg-hub")
    assert line["sources"] == ["PEG 2027-01 mark", "VIP Pirineos tariff (illustrative)"]
    assert covered.objectives["pnl_expected"] == -235_000
    # The breach option and the covered one sit in the same ranked list.
    assert options["A:swap:C+absorb"].rank < covered.rank
    rows = result_dict(extended(), result)["options"]
    row = next(r for r in rows if r["key"] == covered.key)
    assert row["covers"][0]["mwh"] == 50_000
    assert {"direct_pnl_expected", "opportunity_cost_expected", "flags"} <= set(row)


def test_upstream_storage_and_hub_cover_cheapest_first():
    prices = {**PRICES, ("PVB", "2027-03"): 31.00}
    market = Market(prices, NOW)
    upstream = SubstituteSource(
        "medgaz",
        "upstream",
        "supply contract swing at PVB",
        "PVB",
        jan(20),
        feb(28),
        20_000,
        price_eur_mwh=29.50,
        sources={"gas": "upstream_resource_contract:medgaz price"},
    )
    storage = SubstituteSource(
        "yela",
        "storage",
        "storage withdrawal at Yela",
        "PVB",
        jan(20),
        feb(28),
        20_000,
        price_hub="PVB",
        fee_eur_mwh=0.30,
        value_month="2027-03",
        sources={"fee": "storage fee assumption", "value": "PVB 2027-03 mark"},
    )
    p = replace(portfolio(), substitutes=(PEG_TO_PVB, upstream, storage))
    options = by_key(optimise(p, market))
    merit = options["A:swap:C+absorb + cover:merit"]
    # Per MWh: upstream 29.50; storage 0.30 now + 31.00 forgone = 31.30; hub 31.65.
    assert [(c.source_id, c.mwh) for c in merit.covers] == [
        ("medgaz", 20_000),
        ("yela", 20_000),
        ("peg-hub", 10_000),
    ]
    assert merit.breaches == []
    yela = options["A:swap:C+absorb + cover:yela"]
    # Storage gas: the 0.30 fee is paid now; the gas is not there to sell in March at 31.00.
    assert yela.base.components()["substitute_cost"] == -20_000 * 0.30
    assert yela.base.components()["storage_forgone"] == -20_000 * 31.00
    assert yela.base.opportunity[0]["kind"] == "storage_used"
    assert yela.flags["contract_breach"]  # 30,000 MWh still short
    upstream_only = options["A:swap:C+absorb + cover:medgaz"]
    assert upstream_only.base.components()["substitute_cost"] == -20_000 * 29.50
