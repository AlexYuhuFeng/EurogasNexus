"""SCHED-1: each break kind, worked by hand (``domain/portfolio/nomination_reconciliation``).

Gas day 2026-11-25 (24 hours, 05:00 UTC to 05:00 UTC). Cut-offs at the network-code defaults:
nomination 2026-11-24 13:00 UTC, last renomination 2026-11-26 02:00 UTC.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from eurogas_nexus.domain.portfolio.nomination_reconciliation import (
    CutoffFact,
    NominationFact,
    TradeFact,
    counterparty_key,
    reconcile,
    unit_factor,
    urgency,
)

DAY = date(2026, 11, 25)
NOMINATION = datetime(2026, 11, 24, 13, tzinfo=UTC)
LAST_RENOM = datetime(2026, 11, 26, 2, tzinfo=UTC)
END = datetime(2026, 11, 26, 5, tzinfo=UTC)
CUTS = {
    hub: [CutoffFact("nomination", NOMINATION, "assumption", "default"),
          CutoffFact("last_renomination", LAST_RENOM, "assumption", "default"),
          CutoffFact("gas_day_end", END, "calendar", "calendar")]
    for hub in ("TTF", "NBP")
}
NOW = datetime(2026, 11, 25, 23, tzinfo=UTC)  # three hours before the last renomination


def trade(mwh=6_000.0, *, tid="t1", cpty="Aldermoor Energy plc", direction="out", hub="TTF",
          traded_at=datetime(2026, 11, 20, 9, tzinfo=UTC), **kw) -> TradeFact:
    return TradeFact(trade_id=tid, deal_ref=tid.upper(), hub=hub, counterparty=cpty,
                     direction=direction, mwh=mwh, first_day=date(2026, 11, 1),
                     last_day=date(2026, 11, 30), traded_at=traded_at, **kw)


def nom(mwh=6_000.0, *, ref="trade:t1", tid="t1", day=DAY, hub="TTF", **kw) -> NominationFact:
    return NominationFact(gas_day=day, line_ref=ref, hub=hub, trade_id=tid, nominated_mwh=mwh,
                          nominated_at=datetime(2026, 11, 24, 10, tzinfo=UTC), **kw)


def breaks(trades, noms, **kw):
    groups = reconcile(DAY, trades, noms, hours=24.0, cutoffs=CUTS, now=NOW, **kw)
    return [b for g in groups for b in g.breaks], groups


def test_matched_trade_and_nomination_have_no_break():
    found, groups = breaks([trade()], [nom(tso_mwh=6_000.0, tso_status="confirmed")])
    assert found == []
    (group,) = groups
    assert group.traded_mwh == -6_000 and group.nominated_mwh == -6_000
    assert group.tso_mwh == -6_000


def test_trade_not_nominated():
    (item,), _ = breaks([trade()], [])
    assert item.kind == "not_nominated"
    # Sale of 6,000 MWh, nothing nominated: the TSO will flow nothing, so the firm keeps the
    # gas it sold: 0 - (-6,000) = +6,000 long.
    assert item.mwh_at_risk == 6_000 and item.gap_mwh == 6_000
    assert "nothing nominated for gas day 2026-11-25" in item.text_en
    assert "long 6,000 MWh" in item.text_en
    assert "before the last renomination at 26 Nov 02:00 UTC" in item.next_en
    assert "未见提名" in item.text_zh


def test_nomination_without_a_trade():
    (item,), _ = breaks([], [nom(4_800.0, ref="counterparty:Brightwater", tid=None,
                                 counterparty="Brightwater", direction="in")])
    assert item.kind == "nomination_without_trade"
    assert item.counterparty == "Brightwater" and item.gap_mwh == 4_800


def test_quantity_mismatch_in_mwh_and_kwh_per_hour():
    (item,), _ = breaks([trade(6_000.0)], [nom(4_800.0, direction="out")])
    assert item.kind == "quantity_mismatch"
    # Nominated -4,800 against traded -6,000: -4,800 - (-6,000) = +1,200 MWh,
    # 1,200 MWh x 1,000 / 24 h = 50,000 kWh/h.
    assert item.gap_mwh == pytest.approx(1_200)
    assert item.figures["delta_kwh_h"] == 50_000
    assert "-4,800 − (-6,000) = +1,200 MWh (+50,000 kWh/h" in item.text_en


def test_counterparty_mismatch_is_one_break_not_two():
    found, groups = breaks([trade()], [nom(counterparty="Aldermoor Trading GmbH")])
    assert [b.kind for b in found] == ["counterparty_mismatch"]
    assert len(groups) == 1
    assert "names Aldermoor Trading GmbH" in found[0].text_en
    # The same company written differently is the same counterparty.
    found, _ = breaks([trade()], [nom(counterparty="ALDERMOOR ENERGY PLC")])
    assert found == []
    assert counterparty_key("Aldermoor Energy, plc") == counterparty_key("aldermoor energy plc")


def test_wrong_direction_moves_the_balance_twice():
    (item,), _ = breaks([trade()], [nom(direction="in")])
    assert item.kind == "wrong_direction"
    # Nominated +6,000 (IN) for a sale of 6,000: +6,000 - (-6,000) = +12,000 MWh.
    assert item.gap_mwh == 12_000 and item.mwh_at_risk == 12_000
    assert "+6,000 − (-6,000) = +12,000 MWh" in item.text_en


def test_lesser_rule_with_the_counterpartys_quantity():
    (item,), _ = breaks([trade()], [nom(direction="out", tso_mwh=4_800.0,
                                        tso_status="confirmed", counterparty_mwh=4_800.0)])
    assert item.kind == "lesser_rule_cut"
    # 6,000 nominated out, 4,800 confirmed: 1,200 MWh of the sale will not flow, long 1,200.
    assert item.mwh_at_risk == 1_200 and item.gap_mwh == 1_200
    assert "6,000 − 4,800 = 1,200 MWh cut" in item.text_en
    assert "nominated 4,800 MWh" in item.text_en


def test_shipper_code_mismatch_against_the_code_the_tso_matched():
    adjacent = [nom(day=date(2026, 11, 24), counterparty="Aldermoor Energy plc",
                    counterparty_shipper_code="21X-ALDER-A", tso_mwh=6_000.0,
                    tso_status="confirmed")]
    (item,), _ = breaks(
        [trade()],
        [nom(counterparty="Aldermoor Energy plc", counterparty_shipper_code="21X-ALDER-B",
             tso_mwh=0.0, tso_status="mismatch")],
        adjacent=adjacent)
    assert item.kind == "shipper_code_mismatch"
    assert item.mwh_at_risk == 6_000 and item.figures["matched_codes"] == ["21X-ALDER-A"]


def test_unit_slip_kwh_per_hour_read_as_mwh_per_day():
    # 6,000 MWh/d = 250,000 kWh/h; 250,000 typed as MWh/d is 6,000 x 1,000 / 24.
    (item,), _ = breaks([trade()], [nom(250_000.0, direction="out")])
    assert item.kind == "unit_mismatch" and "kWh/h read as MWh/d" in item.text_en
    assert unit_factor(6_000 * 34.1214163, 6_000, 24)[1] == "therms read as MWh"
    assert unit_factor(250.0, 6_000, 24)[3] is False  # MW sent where MWh/d was due


def test_deal_booked_after_the_last_nomination_is_late():
    early = trade(6_000.0)
    later = trade(1_200.0, tid="t2", traded_at=datetime(2026, 11, 25, 14, tzinfo=UTC))
    (item,), _ = breaks([early, later], [nom(6_000.0, direction="out")])
    assert item.kind == "late" and item.figures["flavour"] == "traded_after_nomination"
    assert item.trade_ids == ("t2",) and item.gap_mwh == pytest.approx(1_200)


def test_nomination_after_the_deadline_not_yet_confirmed():
    late = nom(direction="out")
    late = NominationFact(**{**late.__dict__,
                             "nominated_at": datetime(2026, 11, 24, 15, tzinfo=UTC)})
    (item,), _ = breaks([trade()], [late])
    assert item.kind == "late" and item.figures["flavour"] == "nominated_after_deadline"


def test_nominated_on_the_next_gas_day():
    shifted = nom(day=date(2026, 11, 26), direction="out")
    found, _ = breaks([TradeFact(
        trade_id="t1", deal_ref="T1", hub="TTF", counterparty="Aldermoor Energy plc",
        direction="out", mwh=6_000.0, first_day=DAY, last_day=DAY)], [], adjacent=[shifted])
    (item,) = found
    assert item.kind == "gas_day_misaligned" and item.figures["nominated_gas_day"] == "2026-11-26"


def test_deal_booked_in_calendar_days_is_misaligned():
    # A deal from midnight UTC: 19 of the gas day's 24 hours fall in it.
    t = trade(4_750.0, misaligned=True, hours_in_day=19.0)
    (item,), _ = breaks([t], [nom(6_000.0, direction="out")])
    assert item.kind == "gas_day_misaligned" and "only 19 of the gas day's 24 hours" in item.text_en


def test_unconfirmed_deal():
    found, _ = breaks([trade(confirmation="sent")], [nom(direction="out")])
    assert [b.kind for b in found] == ["not_confirmed"] and found[0].gap_mwh is None


def test_urgency_buckets():
    cuts = CUTS["TTF"]
    assert urgency(cuts, datetime(2026, 11, 25, 12, tzinfo=UTC))["bucket"] == "open"
    soon = urgency(cuts, datetime(2026, 11, 25, 23, 30, tzinfo=UTC))
    assert soon["bucket"] == "due_soon" and soon["minutes_left"] == 150
    assert soon["severity"] == "warning"
    assert urgency(cuts, datetime(2026, 11, 26, 1, 30, tzinfo=UTC))["severity"] == "critical"
    passed = urgency(cuts, datetime(2026, 11, 26, 3, tzinfo=UTC))
    assert passed["bucket"] == "passed" and passed["cutoff"] is None
    assert urgency(cuts, datetime(2026, 11, 26, 6, tzinfo=UTC))["bucket"] == "closed"
