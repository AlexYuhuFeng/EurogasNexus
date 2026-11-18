"""Golden cases for the LNG cargo chain (CP-12): design section C.3, to the cent.

Inputs (illustrative, design C.3): HH Dec-26 3.50 USD/MMBtu; formula 115 % HH + 2.50;
Q_load 3,800,000 MMBtu; 4,900 nm at 17 kn; hire 45,000 USD/d; boil-off 0.10 %/d; ballast fuel
2,000 MMBtu/d; ports 2 x 150,000 USD; insurance 0.05 %; EUR/USD Jan-27 1.1600. The MWh factor
is the ontology's (1 MWh = 3.412141633 MMBtu; the design rounds it to 3.41214).
"""

from __future__ import annotations

from decimal import Decimal as D

import pytest

from eurogas_nexus.domain.lng.cargo_economics import (
    MMBTU_PER_MWH,
    CargoOffer,
    TerminalOption,
    Valued,
    evaluate_cargo,
    missing,
    serialise,
)
from eurogas_nexus.domain.lng.voyage import Voyage, sailing_days
from eurogas_nexus.domain.valuation.quality import InputClass

A = InputClass.ASSUMPTION
S = InputClass.SOURCED
F = InputClass.FIRM_MARK


def _fob(**overrides) -> CargoOffer:
    fields = {
        "cargo_id": "us-gulf",
        "label": "US Gulf, lift 18 Dec",
        "term": "FOB",
        "q_load_mmbtu": Valued(D(3_800_000), A, "174,000 m3 x 98.5 % x 22.2"),
        "hh": Valued(D("3.50"), S, "EIA futures contract 1"),
        "slope": Valued(D("1.15"), A, "example, not a market value"),
        "fee": Valued(D("2.50"), A, "example, not a market value"),
        "voyage": Voyage(distance_nm=D(4_900)),
        "route_label": "Sabine Pass -> Rotterdam",
        "hire_per_day": Valued(D(45_000), A, "your assumption"),
        "boil_off_pct_per_day": Valued(D("0.10"), A),
        "ballast_fuel_mmbtu_per_day": Valued(D(2_000), A),
        "port_load": Valued(D(150_000), A),
        "port_discharge": Valued(D(150_000), A),
        "insurance_pct": Valued(D("0.05"), A),
    }
    fields.update(overrides)
    return CargoOffer(**fields)


def _terminal(tid, hub, price, gik, entry, regas_per_mwh, q_del_mwh, basis, **kw):
    return TerminalOption(
        terminal_id=tid,
        name=tid.title(),
        hub=hub,
        currency="EUR",
        arrival_month="2027-01",
        hub_price=Valued(D(price), F, f"{hub} Jan-27 mark"),
        entry=Valued(D(entry), S, "ENTSOG"),
        gas_in_kind_pct=Valued(D(gik), S),
        regas_total=Valued(D(regas_per_mwh) * q_del_mwh, S if basis != "firm_terms" else F),
        regas_basis=basis,
        fx_usd_per_unit=Valued(D("1.1600"), InputClass.DERIVED, "interest parity"),
        **kw,
    )


def test_sailing_days_to_a_tenth():
    """4,900 nm / (17 kn x 24) = 12.0098 days -> 12.0 days, as a voyage estimate states it."""
    assert sailing_days(D(4_900), D(17)) == D("12.0")


def test_cost_at_the_ships_rail_to_the_cent():
    """FOB price 1.15 x 3.50 + 2.50 = 6.525 USD/MMBtu; FOB cost 6.525 x 3,800,000 =
    24,795,000.00 USD. Boil-off 3,800,000 x 0.10 % x 12.0 = 45,600 MMBtu; delivered 3,754,400
    MMBtu. Hire 45,000 x (12.0 + 12.0 + 2) = 1,170,000.00; ballast fuel 2,000 x 12.0 x 6.525 =
    156,600.00; ports 300,000.00; insurance 0.05 % x 24,795,000 = 12,397.50 (the design shows
    12,400); freight 1,638,997.50 (design 1,639,000). Cost (24,795,000 + 1,638,997.50) /
    3,754,400 = 7.0408 USD/MMBtu (design 7.041); boil-off effect 24,795,000 / 3,754,400 - 6.525
    = 6.60425 - 6.525 = 0.0793 (design 0.079).
    In EUR/MWh: 7.040805 x 3.412141633 / 1.16 = 20.7107 (design 20.71)."""
    result = evaluate_cargo(_fob(), [])
    assert result.blocked is None
    assert result.fob_price == D("6.525")
    assert result.q_del_mmbtu == D(3_754_400)
    f = result.freight
    assert (f.hire, f.ballast_fuel, f.port_load + f.port_discharge) == (
        D(1_170_000),
        D("156600.000"),
        D(300_000),
    )
    assert f.insurance == D("12397.50")
    assert f.total == D("1638997.50")
    assert round(result.cost_usd_mmbtu, 4) == D("7.0408")
    assert round(D(24_795_000) / result.q_del_mmbtu - result.fob_price, 4) == D("0.0793")
    assert round(result.cost_usd_mmbtu * MMBTU_PER_MWH, 3) == D("24.024")
    assert round(result.cost_usd_mmbtu * MMBTU_PER_MWH / D("1.16"), 2) == D("20.71")
    assert round(result.q_del_mwh) == D(1_100_306)


def test_three_terminals_rank_without_declaring_a_winner():
    """Netback = (hub - entry) x (1 - gas in kind) - regas (per MWh delivered):
    Gate (30.00 - 0.45) x 0.995 - 0.95 = 28.4523; Zeebrugge (29.70 - 0.30) x 0.99 - 0.62 =
    28.4860; Montoir (29.10 - 0.25) x 0.994 - 0.78 = 27.8969. Margins against 20.7107: 7.7416,
    7.7753, 7.1862 (design 7.74, 7.78, 7.19). Zeebrugge leads Gate by 0.034 < 0.10: no winner.
    Zeebrugge in USD/MMBtu 7.7753 x 1.16 / 3.412141633 = 2.6433 (design 2.64); total
    7.7753 x 1,100,306.07 = 8.56 m EUR. Lifting cost basis (fee sunk): 2.50 x 3,800,000 /
    3,754,400 = 2.5304 USD/MMBtu = 7.4430 EUR/MWh lower cost, margin 15.2183. The design's
    table prints "+10.3" there, which its own C.4 figure (+5.15 USD/MMBtu = 15.15 EUR/MWh)
    contradicts; this test follows the arithmetic."""
    q_del_mwh = D(3_754_400) / MMBTU_PER_MWH
    terminals = [
        _terminal("gate", "TTF", "30.00", "0.5", "0.45", "0.95", q_del_mwh, "firm_terms"),
        _terminal("zeebrugge", "ZTP", "29.70", "1.0", "0.30", "0.62", q_del_mwh, "reviewed_public"),
        _terminal("montoir", "PEG", "29.10", "0.6", "0.25", "0.78", q_del_mwh, "reviewed_public"),
    ]
    result = evaluate_cargo(_fob(), terminals)
    by_id = {row.terminal_id: row for row in result.terminals}
    assert [row.terminal_id for row in result.terminals] == ["zeebrugge", "gate", "montoir"]
    assert round(by_id["gate"].netback_per_mwh, 4) == D("28.4523")
    assert round(by_id["zeebrugge"].netback_per_mwh, 4) == D("28.4860")
    assert round(by_id["montoir"].netback_per_mwh, 4) == D("27.8969")
    assert [round(by_id[t].margin_per_mwh, 2) for t in ("gate", "zeebrugge", "montoir")] == [
        D("7.74"),
        D("7.78"),
        D("7.19"),
    ]
    zee = by_id["zeebrugge"]
    assert round(zee.margin_usd_mmbtu, 2) == D("2.64")
    assert round(zee.margin_total / 1_000_000, 2) == D("8.56")
    assert round(zee.lifting_margin_per_mwh, 2) == D("15.22")
    assert result.no_winner is True and result.best_terminal_id == "zeebrugge"
    # Assumptions on the value path: cargo size, slope, fee, hire, boil-off, ballast fuel,
    # two port calls, insurance = 9; the result is graded "assumption".
    assert result.assumptions == 9 and str(result.grade) == "assumption"
    payload = serialise(result)
    assert payload["freight_usd"] == 1_638_997.5
    assert payload["terminals"][0]["margin_total"] == pytest.approx(
        float(round(zee.margin_total, 2))
    )


def test_des_offer_lands_in_the_same_table():
    """DES at TTF Dec-26 - 0.40 with TTF Dec-26 30.40: 30.00 EUR/MWh. Netback at Gate for
    December 29.95 x 0.995 - 0.95 = 29.80025 - 0.95 = 28.85025; margin -1.14975 (design -1.15).
    With a held slot (variable 0.10): 29.80025 - 0.10 = 29.70025, margin -0.29975 (design
    -0.30)."""
    offer = CargoOffer(
        cargo_id="des-ara",
        label="Offered DES ARA",
        term="DES",
        q_load_mmbtu=Valued(D(3_400_000), A),
        des_price=Valued(D("30.00"), F, "offer: TTF Dec-26 - 0.40"),
    )
    q_mwh = D(3_400_000) / MMBTU_PER_MWH
    gate = _terminal("gate", "TTF", "30.40", "0.5", "0.45", "0.95", q_mwh, "firm_terms")
    held = _terminal("gate-held", "TTF", "30.40", "0.5", "0.45", "0.10", q_mwh, "firm_terms")
    result = evaluate_cargo(offer, [gate, held])
    rows = {row.terminal_id: row for row in result.terminals}
    assert rows["gate"].margin_per_mwh == pytest.approx(D("-1.14975"), abs=D("1e-12"))
    assert rows["gate-held"].margin_per_mwh == pytest.approx(D("-0.29975"), abs=D("1e-12"))
    assert round(rows["gate"].margin_per_mwh, 2) == D("-1.15")


def test_missing_inputs_block_with_the_reason_never_zero():
    """No charter hire -> the FOB cargo is blocked (no_charter_hire); no route distance ->
    no_distance; a terminal without a regas tariff is left out with no_regas_tariff."""
    assert evaluate_cargo(_fob(hire_per_day=missing()), []).blocked == "no_charter_hire"
    assert evaluate_cargo(_fob(voyage=None), []).blocked == "no_distance"
    q_del_mwh = D(3_754_400) / MMBTU_PER_MWH
    gap = _terminal("gate", "TTF", "30.00", "0.5", "0.45", "0.95", q_del_mwh, "firm_terms")
    gap = TerminalOption(**{**gap.__dict__, "regas_total": missing("needs_firm_terms")})
    result = evaluate_cargo(_fob(), [gap])
    assert result.terminals[0].reason == "no_regas_tariff" and result.best_terminal_id is None


def test_lifting_and_full_cost_are_both_reported():
    """Full cost 7.0408 USD/MMBtu; lifting cost = 7.0408 - 2.50 x 3,800,000 / 3,754,400 =
    7.0408 - 2.5304 = 4.5104 USD/MMBtu."""
    result = evaluate_cargo(_fob(), [])
    assert round(result.lifting_cost_usd_mmbtu, 4) == D("4.5104")
    assert result.lifting_price == D("4.025")


def test_legs_reconcile_to_the_headline_for_random_cargoes():
    """K.0 gate 2: for 200 seeded random FOB cargoes, FOB cost + the freight legs = the cost at
    the ship's rail x Q_del, and per terminal (hub - entry) x (1 - gas in kind) - regas / Q_del
    - cost = margin, and margin x Q_del = the total."""
    import random

    rng = random.Random(20261118)
    for _ in range(200):
        q = D(rng.randrange(2_500_000, 4_200_000))
        offer = _fob(
            q_load_mmbtu=Valued(q, A),
            hh=Valued(D(str(round(rng.uniform(1.5, 9), 3))), S),
            voyage=Voyage(distance_nm=D(rng.randrange(800, 12_000))),
            hire_per_day=Valued(D(rng.randrange(10_000, 200_000)), A),
            canal=Valued(D(rng.randrange(0, 900_000)), A),
        )
        q_del_guess = q / MMBTU_PER_MWH
        option = _terminal(
            "t", "TTF", str(round(rng.uniform(5, 80), 2)), "0.7", "0.4", "0.8", q_del_guess, "x"
        )
        result = evaluate_cargo(offer, [option])
        f = result.freight
        legs = {leg.key: leg.amount for leg in result.legs}
        assert legs["fob_cost"] + f.total == pytest.approx(
            result.cost_usd_mmbtu * result.q_del_mmbtu, abs=D("1e-6")
        )
        assert f.total == f.hire + f.ballast_fuel + f.canal + f.port_load + f.port_discharge + (
            f.insurance
        )
        row = result.terminals[0]
        t = {leg.key: leg.amount for leg in row.legs}
        expected = (t["hub"] - t["entry"]) * (1 - t["gas_in_kind"] / 100) - t["regas"] - t["cost"]
        assert row.margin_per_mwh == pytest.approx(expected, abs=D("1e-9"))
        assert row.margin_total == pytest.approx(
            row.margin_per_mwh * result.q_del_mwh, abs=D("1e-6")
        )
