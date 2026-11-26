"""Role-aware discovery (CP-24): credit under price moves, ranking and phrasing per role."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from eurogas_nexus.domain.discovery.credit_moves import credit_under_moves
from eurogas_nexus.domain.discovery.findings import Finding, audience_of, phrase, rank
from eurogas_nexus.domain.risk.limits import CounterpartyLeg, CreditLine
from eurogas_nexus.domain.valuation.quality import InputClass

TODAY = date(2026, 11, 17)


def _moves(limit=150_000.0):
    leg = CounterpartyLeg(
        "c1", "supply_contract", "TTF", "EUR", date(2026, 12, 1), date(2027, 1, 31), 1_000.0, 30.0
    )
    line = CreditLine("CP1", "Aldermoor", limit, "EUR", receivable_days=0)
    return credit_under_moves(
        line, [leg], today=TODAY, mark=lambda hub, month: 32.0, fx=lambda a, b: 1.0
    )


def test_golden_credit_under_a_price_move() -> None:
    """1,000 MWh/d bought at 30.00 for Dec and Jan (62 days), marks 32.00, limit 150,000.

    Today 62,000 x 2.00 = EUR 124,000 (82.7 %). At +10 %: 62,000 x 5.20 = EUR 322,400, a
    breach whose tenor is December (31,000 x 5.20 = 161,200 > 150,000). The limit is reached
    at 62,000 x (32 (1 + s) - 30) = 150,000: s* = 1.3105 %, +0.42 EUR/MWh on 32.00.
    """

    moves = _moves()
    assert moves.net_exposure == pytest.approx(124_000.0)
    up10 = next(item for item in moves.moves if item.move == 0.10)
    assert up10.breach and up10.tenor == "2026-12"
    assert up10.net_exposure == pytest.approx(322_400.0)
    assert moves.projected is not None and moves.projected.move == 0.10
    assert moves.reach_move == pytest.approx(0.013105, abs=1e-6)
    assert moves.reach_price_move == pytest.approx(0.4194, abs=1e-4)
    assert (moves.front_hub, moves.front_month) == ("TTF", "2026-12")
    # Falling prices do not raise this exposure: no breach downwards.
    assert not any(item.breach for item in moves.moves if item.move < 0)


def test_a_line_already_over_reports_a_zero_reach() -> None:
    moves = _moves(limit=100_000.0)
    assert moves.status == "breach" and moves.reach_move == 0.0


def _finding(kind, severity, size, klass=InputClass.SOURCED, **facts):
    base = {
        "claim": f"{kind} claim",
        "period": "2027-01",
        "headline": "0.229 EUR/MWh",
        "value": "EUR 71,042",
        "counterparty": "Aldermoor",
        "exposure": "EUR 124,000",
        "limit": "EUR 150,000",
        "hub": "TTF",
        "move_pct": "+1.3 %",
        "move_price": "+0.42 EUR/MWh on 32.00",
        "shock": "+10 %",
        "tenor": "2026-12",
    }
    base.update(facts)
    return Finding(
        finding_id=kind,
        kind=kind,
        severity=severity,
        facts=base,
        input_class=klass,
        simulated=klass is InputClass.SIMULATED,
        size=Decimal(size),
    )


def test_the_same_findings_rank_differently_for_a_trader_and_for_risk() -> None:
    findings = [
        _finding("credit.projected", 2, "124000", InputClass.INDICATIVE),
        _finding("opportunity.locational", 2, "71042"),
        _finding("opportunity.hedge_gap", 3, "54000"),
    ]
    trader = [item.kind for item in rank(findings, audience_of("TRADER"))]
    risk = [item.kind for item in rank(findings, audience_of("RISK_MANAGER"))]
    assert trader[0] == "opportunity.locational"
    assert risk[0] == "opportunity.hedge_gap" and risk[1] == "credit.projected"
    assert trader != risk


def test_phrasing_per_role_language_and_input_class() -> None:
    projected = _finding("credit.projected", 2, "1", InputClass.INDICATIVE)
    en = phrase(projected, "risk", "en")
    assert en == (
        "Aldermoor reaches its EUR 150,000 credit line if TTF moves +1.3 % "
        "(+0.42 EUR/MWh on 32.00); at +10 % the line is crossed in 2026-12 "
        "(on indicative marks)."
    )
    zh = phrase(projected, "risk", "zh-CN")
    assert "信用" in zh and "基于参考价格" in zh
    demo = _finding("credit.breach", 3, "1", InputClass.SIMULATED)
    assert phrase(demo, "risk", "en").endswith("(on simulated prices).")
    spread = _finding("opportunity.locational", 2, "1")
    assert phrase(spread, "trader", "en") == "opportunity.locational claim"
    assert phrase(spread, "risk", "en").startswith("Location spread: ")
    assert phrase(spread, "trader", "zh").startswith("地点价差（2027-01）")


def test_a_reader_that_marks_simulated_itself_gets_no_second_mark() -> None:
    demo = _finding("credit.breach", 3, "1", InputClass.SIMULATED)
    assert "simulated" not in phrase(demo, "risk", "en", simulated_marked=True)
    assert "模拟" not in phrase(demo, "risk", "zh", simulated_marked=True)
    # Any other input class is still stated: only the duplicate simulated mark is dropped.
    projected = _finding("credit.projected", 2, "1", InputClass.INDICATIVE)
    assert phrase(projected, "risk", "en", simulated_marked=True).endswith("(on indicative marks).")
