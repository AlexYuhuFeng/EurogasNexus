"""How captured deals count in the position: physical or financial, exactly, in desk units.

Three pieces the one position source (``application/captured_position``) reads:

- **Physical or financial** (:func:`classify`): a person's choice for the deal first (recorded
  as entered by hand), then the deal's own physical flag, then the first rule of the rule file
  (``reference_data/desk/position_kinds.toml``, editable, a desk copy replaces it) whose
  conditions hold, then its default. ``financial_until_delivery`` (an exchange future) is
  financial until its first delivery gas day and physical from then on.
- **Exact volumes** (:func:`delivered_mwh`): the MWh a deal delivers inside a window of gas
  days, in :class:`~decimal.Decimal` from the deal's exact total (a MW deal by the hours of the
  gas days, so a clock-change day carries 23 or 25 hours; a daily or total quantity by days).
- **Desk units** (:func:`desk_unit`): therms per day at NBP and MW at the continental hubs,
  with the MWh beside them.

The trading calendar (:func:`load_trading_calendar`) says which weekdays an exchange is shut,
from a hand-maintained file with its source.

捕获交易在头寸中的计法：实物或金融（规则文件、可手工指定）、精确小数、
交易台单位（NBP 撇姆/日，欧陆 MW）。
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from eurogas_nexus.domain.deals.formats import FormatError, desk_file_path

KINDS_FILE = "position_kinds.toml"
CALENDAR_FILE = "trading_calendars.toml"
POSITION_KINDS = ("physical", "financial", "financial_until_delivery")
#: How a deal's kind was decided, for the screen and the packs.
BASES = ("entered_by_hand", "stated_on_deal", "rule", "default")


@dataclass(frozen=True)
class KindRule:
    name: str
    kind: str
    venue: tuple[str, ...] = ()
    instrument: tuple[str, ...] = ()
    cleared: bool | None = None
    prompt: bool | None = None

    def holds(self, deal: Any, prompt_days: int) -> bool:
        if self.venue and str(deal.venue).upper() not in self.venue:
            return False
        if self.instrument and str(deal.instrument).casefold() not in self.instrument:
            return False
        if self.cleared is not None and bool(deal.cleared) != self.cleared:
            return False
        if self.prompt is not None:
            days = (deal.delivery_end - deal.delivery_start).days + 1
            if (days <= prompt_days) != self.prompt:
                return False
        return True


@dataclass(frozen=True)
class KindRules:
    default: str
    prompt_gas_days: int
    rules: tuple[KindRule, ...]
    source_path: str

    def describe(self) -> dict[str, Any]:
        return {
            "default": self.default,
            "prompt_gas_days": self.prompt_gas_days,
            "rules": [
                {"name": r.name, "kind": r.kind, "venue": list(r.venue),
                 "instrument": list(r.instrument), "cleared": r.cleared, "prompt": r.prompt}
                for r in self.rules
            ],
            "source_path": self.source_path,
        }


def _kind(value: Any, where: str) -> str:
    text = str(value or "").strip()
    if text not in POSITION_KINDS:
        raise FormatError(f"{where}: kind {text!r} is not one of {', '.join(POSITION_KINDS)}")
    return text


def parse_position_kinds(text: str, *, source_path: str = "") -> KindRules:
    """The rule file as rules; a file that cannot be used says what to change."""

    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise FormatError(f"{source_path or KINDS_FILE}: {exc}") from exc
    rules = []
    for index, item in enumerate(data.get("rule") or [], start=1):
        where = f"{source_path or KINDS_FILE} rule {index}"
        unknown = set(item) - {"name", "kind", "venue", "instrument", "cleared", "prompt"}
        if unknown:
            raise FormatError(f"{where}: unknown condition(s) {', '.join(sorted(unknown))}")
        for flag in ("cleared", "prompt"):
            if flag in item and not isinstance(item[flag], bool):
                raise FormatError(f"{where}: {flag} must be true or false")
        rules.append(KindRule(
            name=str(item.get("name") or f"rule {index}"),
            kind=_kind(item.get("kind"), where),
            venue=tuple(str(v).upper() for v in item.get("venue") or ()),
            instrument=tuple(str(v).casefold() for v in item.get("instrument") or ()),
            cleared=item.get("cleared"),
            prompt=item.get("prompt"),
        ))
    days = data.get("prompt_gas_days", 3)
    if not isinstance(days, int) or not 1 <= days <= 9:
        raise FormatError(f"{source_path or KINDS_FILE}: prompt_gas_days must be 1 to 9")
    return KindRules(default=_kind(data.get("default", "financial"), "default"),
                     prompt_gas_days=days, rules=tuple(rules), source_path=source_path)


def load_position_kinds(environ: dict[str, str] | None = None) -> KindRules:
    path = desk_file_path(KINDS_FILE, environ)
    return parse_position_kinds(path.read_text(encoding="utf-8"), source_path=str(path))


@dataclass(frozen=True)
class Classification:
    """A deal's kind in the position on a day, and how it was decided."""

    kind: str  # physical | financial (on the day asked)
    rule_kind: str  # physical | financial | financial_until_delivery
    basis: str  # one of BASES
    rule: str | None = None  # the rule's name, or who chose it by hand

    def as_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "rule_kind": self.rule_kind, "basis": self.basis,
                "rule": self.rule}


def classify(deal: Any, today: date, rules: KindRules, override: Any = None) -> Classification:
    """Physical or financial on ``today``: the person's choice, the deal's flag, the rules.

    ``deal`` has ``venue``, ``instrument``, ``cleared``, ``physical``, ``delivery_start`` and
    ``delivery_end``; ``override`` (a choice made by hand) has ``kind`` and ``entered_by``.
    """

    if override is not None:
        kind = _kind(override.kind, "override")
        return Classification(kind, kind, "entered_by_hand", str(override.entered_by))
    if getattr(deal, "physical", False):
        return Classification("physical", "physical", "stated_on_deal")
    for rule in rules.rules:
        if rule.holds(deal, rules.prompt_gas_days):
            return Classification(_on_day(rule.kind, deal, today), rule.kind, "rule", rule.name)
    return Classification(_on_day(rules.default, deal, today), rules.default, "default")


def _on_day(kind: str, deal: Any, today: date) -> str:
    if kind == "financial_until_delivery":
        return "physical" if today >= deal.delivery_start else "financial"
    return kind


# ----------------------------------------------------------------------------- volumes


def _calendar(hub: str) -> str:
    from eurogas_nexus.domain.ontology.boundary import check_boundary

    market = check_boundary(market=hub, gas_hub_required=True).market
    return market.calendar if market else "EU-CAM-UTC-2025"


def window_hours(hub: str, first: date, last: date) -> Decimal:
    """Hours of the gas days ``first``..``last`` at ``hub`` (23 or 25 on a clock change)."""

    from eurogas_nexus.domain.deals.parse import period_hours

    return period_hours(first, last, _calendar(hub))


def delivered_mwh(deal: Any, first: date, last: date) -> Decimal:
    """Signed MWh the deal delivers in the gas days ``first``..``last`` (exact).

    ``deal`` has ``total_mwh`` (exact, positive), ``side``, ``hub``, ``volume_unit``,
    ``delivery_start`` and ``delivery_end``. A deal in MW (or kWh/h) is spread by hours, any
    other quantity by gas days; outside its delivery period it delivers nothing.
    """

    start, end = max(first, deal.delivery_start), min(last, deal.delivery_end)
    if end < start:
        return Decimal(0)
    total = Decimal(deal.total_mwh) * (1 if deal.side == "buy" else -1)
    if (start, end) == (deal.delivery_start, deal.delivery_end):
        return total
    if deal.volume_unit in {"MW", "kWh/h"}:
        whole = window_hours(deal.hub, deal.delivery_start, deal.delivery_end)
        part = window_hours(deal.hub, start, end)
    else:
        whole = Decimal((deal.delivery_end - deal.delivery_start).days + 1)
        part = Decimal((end - start).days + 1)
    return total * part / whole


def desk_unit(hub: str) -> str:
    """The unit the desk reads a hub's position in: th/d at NBP, MW elsewhere."""

    from eurogas_nexus.domain.ontology.markets import quote_currency

    return "th/d" if quote_currency(hub) == "GBP" else "MW"


def in_desk_unit(hub: str, mwh: Decimal, first: date, last: date) -> Decimal:
    """``mwh`` over the gas days ``first``..``last`` as a flat rate in the hub's desk unit."""

    from eurogas_nexus.domain.deals.parse import factor

    if desk_unit(hub) == "th/d":
        days = Decimal((last - first).days + 1)
        return (mwh / days / factor("th", "MWh")).quantize(Decimal(1))
    hours = window_hours(hub, first, last)
    return (mwh / hours).quantize(Decimal("0.001"))


def months_between(first: date, last: date) -> list[tuple[str, date, date]]:
    """(``YYYY-MM``, first gas day, last gas day) of each month ``first``..``last`` touches."""

    out = []
    day = first
    while day <= last:
        end = (day.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        stop = min(end, last)
        out.append((f"{day.year:04d}-{day.month:02d}", day, stop))
        day = stop + timedelta(days=1)
    return out


# ----------------------------------------------------------------------------- calendar


@dataclass(frozen=True)
class Venue:
    code: str
    title: str
    source: str
    checked: bool
    closed: frozenset[date]


@dataclass(frozen=True)
class TradingCalendar:
    years: frozenset[int]
    venues: tuple[Venue, ...]
    source_path: str = ""
    notes: list[str] = field(default_factory=list)

    def is_trading_day(self, day: date) -> bool:
        """A weekday on which at least one listed venue is open."""

        if day.weekday() >= 5:
            return False
        if not self.venues or day.year not in self.years:
            return True
        return any(day not in venue.closed for venue in self.venues)

    def covers(self, day: date) -> bool:
        return day.year in self.years

    def closed_venues(self, day: date) -> list[str]:
        return [venue.code for venue in self.venues if day in venue.closed]


def parse_trading_calendar(text: str, *, source_path: str = "") -> TradingCalendar:
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise FormatError(f"{source_path or CALENDAR_FILE}: {exc}") from exc
    venues = []
    for code, item in sorted((data.get("venue") or {}).items()):
        try:
            closed = frozenset(date.fromisoformat(str(v)) for v in item.get("non_trading_days")
                               or ())
        except ValueError as exc:
            raise FormatError(f"{source_path or CALENDAR_FILE} venue {code}: {exc}") from exc
        venues.append(Venue(code=str(code).upper(), title=str(item.get("title") or code),
                            source=str(item.get("source") or ""),
                            checked=bool(item.get("checked", False)), closed=closed))
    years = frozenset(int(y) for y in data.get("years") or ())
    return TradingCalendar(years=years, venues=tuple(venues), source_path=source_path)


def load_trading_calendar(environ: dict[str, str] | None = None) -> TradingCalendar:
    path = desk_file_path(CALENDAR_FILE, environ)
    return parse_trading_calendar(path.read_text(encoding="utf-8"), source_path=str(path))
