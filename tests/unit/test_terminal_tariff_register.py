"""Golden cases for pricing a cargo at an LNG terminal (CP-11, design C.5 resolution order).

Every expected figure is hand-computed in the test's docstring; the figures are synthetic
(no operator document is reproduced here).
"""

from __future__ import annotations

from datetime import date

import pytest

from eurogas_nexus.domain.portfolio.lng_bid import TerminalTerms
from eurogas_nexus.domain.route_cost.terminal_tariff_register import (
    PublicTariff,
    resolve_terminal_charge,
)

CARGO = 900_000.0  # MWh, a "standard" cargo (<= 1,000,000 * 1.05)


def _row(tariff_id, status, basis, amount, *, product="spot", by_class=None,
         valid_from=date(2026, 10, 1), valid_to=None, terminal="t1", excludes=()):
    return PublicTariff(
        tariff_id=tariff_id, terminal_id=terminal, product=product, charge_basis=basis,
        amount=amount, currency="EUR", review_status=status, valid_from=valid_from,
        valid_to=valid_to, by_cargo_class=by_class, excludes=excludes,
    )


def test_reviewed_fixed_plus_per_mwh():
    """Fixed 500,000 EUR per cargo + 0.80 EUR/MWh * 900,000 MWh = 500,000 + 720,000
    = 1,220,000 EUR, reviewed, not indicative."""
    rows = [_row("a", "REVIEWED", "per_cargo", 500_000.0, excludes=("port fees",)),
            _row("b", "REVIEWED", "per_mwh_unloaded", 0.80)]
    charge = resolve_terminal_charge("t1", arrival_month="2026-12", cargo_mwh=CARGO,
                                     firm_terms=None, public=rows)
    assert charge.basis == "reviewed_public" and not charge.indicative
    assert charge.charge == pytest.approx(1_220_000.0)
    assert charge.tariff_ids == ("a", "b") and charge.excludes == ("port fees",)


def test_cargo_class_total_and_a_class_not_offered():
    """By class: a 900,000 MWh cargo is "standard" (<= 1,050,000) -> 1,350,000 EUR.
    A 1,600,000 MWh cargo exceeds q_flex (1,400,000 * 1.05 = 1,470,000) and fits q_max
    (1,700,000 * 1.05 = 1,785,000), which this terminal does not list -> left out."""
    rows = [_row("c", "REVIEWED", "per_cargo_class", None,
                 by_class={"med_max": 900_000.0, "standard": 1_350_000.0})]
    ok = resolve_terminal_charge("t1", arrival_month="2026-12", cargo_mwh=CARGO,
                                 firm_terms=None, public=rows)
    assert ok.charge == pytest.approx(1_350_000.0)
    big = resolve_terminal_charge("t1", arrival_month="2026-12", cargo_mwh=1_600_000.0,
                                  firm_terms=None, public=rows)
    assert big.basis == "missing" and big.reason == "cargo_class_not_offered"


def test_firm_terms_win_over_public():
    """Firm terms: fixed 100,000 + 0.50 * 900,000 = 550,000 EUR, even with a public tariff."""
    terms = TerminalTerms(terminal_id="t1", name="T1", country="BE", hub="ZTP", currency="EUR",
                          regas_tariff_per_mwh=0.50, fixed_per_cargo=100_000.0)
    rows = [_row("a", "REVIEWED", "per_cargo", 500_000.0)]
    charge = resolve_terminal_charge("t1", arrival_month="2026-12", cargo_mwh=CARGO,
                                     firm_terms=terms, public=rows)
    assert charge.basis == "firm_terms" and charge.charge == pytest.approx(550_000.0)


def test_candidate_prices_indicative_only_and_reviewed_wins():
    """Candidate only: 600,000 EUR, indicative. With a reviewed 500,000 also in force, the
    reviewed figure is used and the result is not indicative."""
    candidate = [_row("x", "CANDIDATE", "per_cargo", 600_000.0)]
    only = resolve_terminal_charge("t1", arrival_month="2026-12", cargo_mwh=CARGO,
                                   firm_terms=None, public=candidate)
    assert only.basis == "candidate_public" and only.indicative and only.charge == 600_000.0
    both = resolve_terminal_charge(
        "t1", arrival_month="2026-12", cargo_mwh=CARGO, firm_terms=None,
        public=[*candidate, _row("y", "REVIEWED", "per_cargo", 500_000.0)],
    )
    assert both.basis == "reviewed_public" and both.charge == 500_000.0


def test_validity_and_missing_reasons():
    """A tariff valid from 2027-01-01 is not in force for a December 2026 arrival; a tariff
    that ended 2026-11-30 neither. With no row at all and the operator's terms not recorded,
    the reason is needs_firm_terms."""
    rows = [_row("f", "REVIEWED", "per_cargo", 1.0, valid_from=date(2027, 1, 1)),
            _row("g", "REVIEWED", "per_cargo", 1.0, valid_from=date(2026, 1, 1),
                 valid_to=date(2026, 11, 30))]
    missing = resolve_terminal_charge("t1", arrival_month="2026-12", cargo_mwh=CARGO,
                                      firm_terms=None, public=rows)
    assert missing.basis == "missing" and missing.reason == "no_tariff_in_force"
    gated = resolve_terminal_charge("t1", arrival_month="2026-12", cargo_mwh=CARGO,
                                    firm_terms=None, public=[], operator_needs_terms=True)
    assert gated.reason == "needs_firm_terms"


def test_product_preference_spot_then_term():
    """Asked for spot with only a term tariff in force: the term tariff prices it (750,000)."""
    rows = [_row("t", "REVIEWED", "per_cargo", 750_000.0, product="term")]
    charge = resolve_terminal_charge("t1", arrival_month="2026-12", cargo_mwh=CARGO,
                                     firm_terms=None, public=rows, product="spot")
    assert charge.charge == 750_000.0
