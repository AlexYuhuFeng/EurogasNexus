"""LNG-2: what a cargo change means to the trader, scheduler, risk and desk head (pure)."""

from datetime import UTC, date, datetime, timedelta

import pytest

from eurogas_nexus.domain.lng.consequences import (
    CargoFacts,
    MandateCheck,
    MandateMove,
    Threshold,
    derive,
)
from eurogas_nexus.domain.lng.in_transit import CargoInTransit, HedgeLeg, SlotWindow, build_plan

#: Dec and Jan both still trade: a delay across the month end is a roll.
NOW = datetime(2026, 10, 20, 9, tzinfo=UTC)
ETA = datetime(2026, 12, 27, 9, tzinfo=UTC)
SLOT = SlotWindow(
    slot_id="gate-1", terminal="Gate", hub="TTF",
    window_start_utc=datetime(2026, 12, 20, tzinfo=UTC),
    window_end_utc=datetime(2027, 1, 10, tzinfo=UTC),
    send_out_mwh_per_day=100_000.0,
)


def _cargo(eta: datetime, hedges=()) -> CargoInTransit:
    return CargoInTransit(
        cargo_id="c1", loaded_mwh=1_000_000.0,
        loaded_at_utc=datetime(2026, 12, 10, tzinfo=UTC), eta_utc=eta,
        boil_off_pct_per_day=0.1, slot=SLOT, hedges=tuple(hedges),
    )


def _hedged(eta: datetime) -> tuple[HedgeLeg, ...]:
    plan = build_plan(_cargo(eta), now=NOW)
    return tuple(HedgeLeg(cover.hub, cover.month, -cover.physical_mwh) for cover in plan.months)


def _facts(before: datetime, after: datetime) -> CargoFacts:
    return CargoFacts(
        cargo_id="c1", vessel="Aurora", book_id="lng-nwe", terminal="Gate",
        eta_before_utc=before, eta_after_utc=after, change_kinds=("eta",),
        eta_basis_text="the master's notice, high confidence",
    )


def _cutoffs(day: date) -> list[dict]:
    at = datetime(day.year, day.month, day.day, 13, tzinfo=UTC) - timedelta(days=1)
    return [{"key": "nomination", "at_utc": at.isoformat(), "basis": "assumption"}]


NO_MANDATES = MandateCheck()


def _derive(late: datetime, *, threshold: float = 100_000.0, mandates=NO_MANDATES):
    hedges = _hedged(ETA)
    before = build_plan(_cargo(ETA, hedges), now=NOW)
    after = build_plan(_cargo(late, hedges), now=NOW)
    return derive(_facts(ETA, late), before, after, now=NOW, cutoffs_for=_cutoffs,
                  mandates=mandates, threshold=Threshold(threshold, "test"))


def test_a_delay_across_the_month_end_proposes_a_roll_with_its_arithmetic():
    messages = _derive(ETA + timedelta(days=5))
    trader = messages["trader"]
    roll, rest = trader.items
    # Five more days at sea boil off 5,000 MWh: the hedge left over in Dec is bought back.
    assert (rest["kind"], rest["from_month"], rest["mwh"]) == ("buy_back", "2026-12", -5000.0)
    assert (roll["kind"], roll["from_month"], roll["to_month"]) == ("roll", "2026-12", "2027-01")
    # The roll is due before the first of the two months stops trading (Dec, 27 Nov).
    assert roll["due_utc"] == "2026-11-28T00:00:00+00:00"
    assert "buy back 2026-12, sell 2027-01" in roll["arithmetic"]
    assert roll["arithmetic"].startswith("TTF 2026-12: physical 0 + hedge −")
    assert trader.title_en.startswith("Hedges no longer match Aurora (c1): roll ")
    assert trader.severity == "warning"  # due in more than a day
    assert trader.due_utc == datetime(2026, 11, 28, tzinfo=UTC)

    risk = messages["risk"]
    moves = {item["month"]: item for item in risk.items}
    assert moves["2026-12"]["net_after_mwh"] == pytest.approx(-roll["mwh"] + rest["mwh"], abs=1)
    assert "No mandate covers book lng-nwe." in risk.lines_en

    scheduler = messages["scheduler"]
    assert scheduler.items[0]["key"] == "berth"
    assert scheduler.due_utc == datetime(2026, 12, 26, 13, tzinfo=UTC)  # gas day 27 Dec

    head = messages["desk_head"]
    assert head is not None and "hedge actions of" in head.material_reasons[1]


def test_below_the_threshold_the_desk_head_hears_nothing():
    messages = _derive(ETA + timedelta(hours=6), threshold=10_000_000.0)
    assert messages["desk_head"] is None
    assert messages["scheduler"] is not None  # the berth still moved six hours


def test_a_plan_that_did_not_change_tells_nobody():
    assert set(_derive(ETA).values()) == {None}


def test_a_mandate_newly_in_breach_is_material_and_critical_for_risk():
    breach = MandateMove("m1", "LNG desk", "watch", "breach", 90.0, 130.0, "TTF 2027-01",
                         ("net 1,300,000 MWh in TTF 2027-01 is over 1,000,000 MWh",))
    messages = _derive(ETA + timedelta(hours=6), threshold=10_000_000.0,
                       mandates=MandateCheck(moves=(breach,), checked=1))
    assert messages["risk"].severity == "critical"
    assert messages["desk_head"].material_reasons == ("mandate breach (LNG desk)",)


def test_digest_is_stable_for_the_same_content():
    first = _derive(ETA + timedelta(days=5))["trader"]
    second = _derive(ETA + timedelta(days=5))["trader"]
    assert first.digest == second.digest
    assert first.digest != _derive(ETA + timedelta(days=6))["trader"].digest
