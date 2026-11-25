"""The standard capacity auctions the CAM network code schedules (Regulation (EU) 2017/459).

At every interconnection point in the EU, bundled firm capacity is sold in auctions on a
calendar the network code sets "unless otherwise specified in the auction calendar" that
ENTSOG publishes by January of each year (Art. 3). The default dates:

* **annual yearly** (Art. 11(4)): the first Monday of July, for the yearly products of the
  coming gas years (at least the next five);
* **annual quarterly** (Art. 12(4)): the first Monday of August (quarters October-December to
  July-September), November (January-March onwards), February (April-June onwards) and May
  (July-September);
* **rolling monthly** (Art. 13(4)): the third Monday of each month, for the following month.

Bidding rounds run 08:00 to 17:00 UTC in winter and 07:00 to 16:00 UTC under daylight saving
(Art. 11(9), 12(7), 13(7)): 09:00 to 18:00 Brussels time either way. An auction runs in
rounds until it clears, so the network code fixes its start, not its close: a window here has
an opening instant and no closing one.

Day-ahead (every day, 15:30 UTC winter) and within-day (hourly) auctions are left out: they
are continuous and a desk does not plan around a notice of them.

These are **rule-derived** dates, labelled so wherever they are shown. ENTSOG's published
calendar and the booking platform (PRISMA, RBP, GSA) are authoritative; a TSO may move a date
(a public holiday), and the Hungarian TSO FGSZ's 2026/27 calendar was checked against this
rule on 2026-11-24 (``tests/fixtures/tariffs/cam_auction_calendar_2026_27.json``).

CAM 网络规范的标准容量拍卖日历（年度、季度、月度），按规则推导并如此标注。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

REGULATION_URL = "https://eur-lex.europa.eu/eli/reg/2017/459/oj"
#: Bidding opens at 09:00 Brussels time: 08:00 UTC in winter, 07:00 UTC in summer.
_BRUSSELS = ZoneInfo("Europe/Brussels")
_OPENS_LOCAL = time(9, 0)

YEARLY = "ANNUAL"
QUARTERLY = "QUARTERLY"
MONTHLY = "MONTHLY"

#: Quarterly auction month -> the first quarter (by start month) it offers.
_QUARTERLY_ROUNDS = ((8, 10), (11, 1), (2, 4), (5, 7))


@dataclass(frozen=True)
class AuctionWindow:
    """One standard auction: what it offers and when bidding opens."""

    notice_key: str
    product: str
    opens_at_utc: datetime
    offers_from: date
    offers_to: date
    label: str
    article: str

    def to_json(self) -> dict:
        return {
            "notice_key": self.notice_key,
            "product": self.product,
            "opens_at_utc": self.opens_at_utc.isoformat(),
            "offers_from": self.offers_from.isoformat(),
            "offers_to": self.offers_to.isoformat(),
            "label": self.label,
            "article": self.article,
        }


def nth_monday(year: int, month: int, n: int) -> date:
    """The ``n``-th Monday of a month (1 = first)."""

    first = date(year, month, 1)
    return first + timedelta(days=(7 - first.weekday()) % 7 + 7 * (n - 1))


def opening_instant(day: date) -> datetime:
    """09:00 Brussels time on ``day``, in UTC (08:00 UTC winter, 07:00 UTC summer)."""

    return datetime.combine(day, _OPENS_LOCAL, tzinfo=_BRUSSELS).astimezone(UTC)


def _month_end(year: int, month: int) -> date:
    nxt = date(year + (month == 12), month % 12 + 1, 1)
    return nxt - timedelta(days=1)


def _yearly(year: int) -> AuctionWindow:
    day = nth_monday(year, 7, 1)
    return AuctionWindow(
        notice_key=f"cam:yearly:{year}",
        product=YEARLY,
        opens_at_utc=opening_instant(day),
        offers_from=date(year, 10, 1),
        # At least the next five gas years (Art. 11(3)); TSOs offer up to 15.
        offers_to=date(year + 5, 9, 30),
        label=f"Annual yearly auction: gas years {year}/{(year + 1) % 100:02d} onwards",
        article="Art. 11(4)",
    )


def _quarterly(year: int, month: int, first_quarter_month: int) -> AuctionWindow:
    day = nth_monday(year, month, 1)
    gas_year = year if month >= 8 else year - 1
    start_year = gas_year if first_quarter_month >= 10 else gas_year + 1
    return AuctionWindow(
        notice_key=f"cam:quarterly:{day.isoformat()}",
        product=QUARTERLY,
        opens_at_utc=opening_instant(day),
        offers_from=date(start_year, first_quarter_month, 1),
        offers_to=date(gas_year + 1, 9, 30),
        label=(
            f"Annual quarterly auction: quarters from {first_quarter_month:02d}/{start_year} "
            f"to the end of gas year {gas_year}/{(gas_year + 1) % 100:02d}"
        ),
        article="Art. 12(4)",
    )


def _monthly(year: int, month: int) -> AuctionWindow:
    day = nth_monday(year, month, 3)
    offered_year, offered_month = (year + 1, 1) if month == 12 else (year, month + 1)
    return AuctionWindow(
        notice_key=f"cam:monthly:{offered_year}-{offered_month:02d}",
        product=MONTHLY,
        opens_at_utc=opening_instant(day),
        offers_from=date(offered_year, offered_month, 1),
        offers_to=_month_end(offered_year, offered_month),
        label=f"Rolling monthly auction: {offered_year}-{offered_month:02d}",
        article="Art. 13(4)",
    )


def standard_auctions(start: date, end: date) -> list[AuctionWindow]:
    """Every yearly, quarterly and monthly auction whose bidding opens in [start, end]."""

    if end < start:
        return []
    out: list[AuctionWindow] = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        if month == 7:
            out.append(_yearly(year))
        for round_month, first_quarter in _QUARTERLY_ROUNDS:
            if month == round_month:
                out.append(_quarterly(year, month, first_quarter))
        out.append(_monthly(year, month))
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return sorted(
        (item for item in out if start <= item.opens_at_utc.date() <= end),
        key=lambda item: (item.opens_at_utc, item.product),
    )


__all__ = [
    "MONTHLY",
    "QUARTERLY",
    "REGULATION_URL",
    "YEARLY",
    "AuctionWindow",
    "nth_monday",
    "opening_instant",
    "standard_auctions",
]
