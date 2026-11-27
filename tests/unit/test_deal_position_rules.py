"""How a captured deal counts in the position: the rule file, the deal's flag, a choice by hand,
exact volumes in desk units, and the hand-maintained exchange calendar."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import pytest

from eurogas_nexus.domain.deals.formats import FormatError
from eurogas_nexus.domain.deals.position import (
    classify,
    delivered_mwh,
    in_desk_unit,
    load_position_kinds,
    parse_position_kinds,
    parse_trading_calendar,
)


@dataclass
class Deal:
    venue: str = "ICE"
    instrument: str = "future"
    cleared: bool = True
    physical: bool = False
    delivery_start: date = date(2026, 12, 1)
    delivery_end: date = date(2026, 12, 31)
    hub: str = "TTF"
    side: str = "buy"
    volume_unit: str = "MW"
    total_mwh: Decimal = Decimal(3720)


@dataclass
class Choice:
    kind: str
    entered_by: str = "trader.a"


RULES = load_position_kinds()
TRADED = date(2026, 11, 26)


@pytest.mark.parametrize(
    ("deal", "kind", "basis"),
    [
        (Deal(), "financial", "rule"),  # a future before delivery
        (Deal(instrument="spot", delivery_start=TRADED, delivery_end=TRADED), "physical", "rule"),
        (Deal(instrument="future", delivery_start=date(2026, 11, 27),
              delivery_end=date(2026, 11, 27)), "physical", "rule"),  # prompt
        (Deal(instrument="forward", cleared=False), "physical", "rule"),
        (Deal(instrument="forward", cleared=True), "financial", "default"),
        (Deal(instrument="swap", cleared=False), "financial", "rule"),
        (Deal(instrument="option"), "financial", "rule"),
        (Deal(physical=True, instrument="swap"), "physical", "stated_on_deal"),
    ],
)
def test_the_rule_file_classifies_by_venue_instrument_and_period(deal, kind, basis):
    result = classify(deal, TRADED, RULES)
    assert (result.kind, result.basis) == (kind, basis)


def test_a_future_is_physical_from_its_first_delivery_day_and_a_choice_by_hand_wins():
    assert classify(Deal(), date(2026, 11, 30), RULES).kind == "financial"
    assert classify(Deal(), date(2026, 12, 1), RULES).kind == "physical"
    by_hand = classify(Deal(), TRADED, RULES, Choice("physical"))
    assert (by_hand.kind, by_hand.basis, by_hand.rule) == ("physical", "entered_by_hand",
                                                           "trader.a")


def test_a_rule_file_that_cannot_be_used_says_what_to_change():
    with pytest.raises(FormatError, match="kind 'phys'"):
        parse_position_kinds('[[rule]]\nkind = "phys"\n')
    with pytest.raises(FormatError, match="unknown condition"):
        parse_position_kinds('[[rule]]\nkind = "physical"\nhub = "NBP"\n')
    with pytest.raises(FormatError, match="cleared must be true or false"):
        parse_position_kinds('[[rule]]\nkind = "physical"\ncleared = "no"\n')
    custom = parse_position_kinds('default = "physical"\n')
    assert classify(Deal(), TRADED, custom).kind == "physical"


def test_volumes_are_exact_by_hours_for_mw_and_by_days_for_daily_quantities():
    year = Deal(delivery_start=date(2027, 1, 1), delivery_end=date(2027, 12, 31),
                total_mwh=Decimal(8760), side="sell")
    march = delivered_mwh(year, date(2027, 3, 1), date(2027, 3, 31))
    assert march == Decimal(-743)  # a 23-hour day at the clock change
    assert in_desk_unit("TTF", march, date(2027, 3, 1), date(2027, 3, 31)) == Decimal(-1)
    daily = Deal(hub="NBP", volume_unit="th/d", delivery_start=date(2027, 1, 1),
                 delivery_end=date(2027, 3, 31), total_mwh=Decimal("5275.279263"))
    january = delivered_mwh(daily, date(2027, 1, 1), date(2027, 1, 31))
    assert january == Decimal("5275.279263") * 31 / 90
    assert in_desk_unit("NBP", january, date(2027, 1, 1), date(2027, 1, 31)) == Decimal(2000)
    assert delivered_mwh(daily, date(2027, 4, 1), date(2027, 4, 30)) == 0


def test_the_calendar_reads_venues_and_refuses_a_bad_date():
    calendar = parse_trading_calendar(
        'years = [2026]\n[venue.EEX]\nnon_trading_days = ["2026-05-01"]\n'
        '[venue.ICE]\nnon_trading_days = []\n')
    assert calendar.is_trading_day(date(2026, 5, 1))  # ICE open
    assert calendar.closed_venues(date(2026, 5, 1)) == ["EEX"]
    assert not calendar.covers(date(2027, 5, 3)) and calendar.is_trading_day(date(2027, 5, 3))
    with pytest.raises(FormatError):
        parse_trading_calendar('[venue.EEX]\nnon_trading_days = ["1 May"]\n')
