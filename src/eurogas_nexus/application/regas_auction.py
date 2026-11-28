"""The regas auction desk: "bid at most X for this slot", live, with what drives it.

A case is opened when a terminal announces a regas slot auction (from the operator's notice
when the tariff book holds one, otherwise entered by the trader): terminal and slot, auction
window, the cargo owner's offer, the send-out profile and the cost lines. The answer is
recomputed on every read from what is held at that moment, through the one valuation reader
(``application/valuation_snapshot``, the price rule every screen uses):

* hub prices for each send-out day: ``reader.price(hub, gas day)``, the contract that covers
  the day (day-ahead, balance of month, the month); the formula's index the same way, or for
  its named month;
* half the bid/offer per hedge month from executable quotes when held, else the desk default;
* FX ``reader.fx`` for the delivery month, the cost of money ``reader.rate`` plus the desk's
  spread;
* terminal figures from the desk engine (``lng_cargo_economics.terminal_charges``: the firm's
  terms, the reviewed tariff register, the published tariffs); a terminal whose operator's site
  may not be stored is entered by the desk from the operator's published tariff, with the link
  and "entered by hand by <who> on <date>";
* anything entered by hand is marked so in the answer; a missing input is named and the answer
  is not computed; a simulated price makes the answer an illustration, never a bid level.

The arithmetic is ``domain/lng/regas_auction``. The definitions (auction formats, offer kinds,
cost lines and their defaults, alert lead times) are the desk-editable file
``reference_data/desk/regas_auction.toml``.

Nothing here bids, orders, nominates or books (AGENTS.md rule 8): the case computes and
prepares; a trader acts in the execution tool and on the terminal's own platform.

再气化档期竞拍：每次读取时按当时持有的价格重新计算最高出价；手工录入均标注；缺失输入不计算；
模拟价格仅作示意。
"""

from __future__ import annotations

import tomllib
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from eurogas_nexus.domain.lng.cargo_economics import Valued, missing
from eurogas_nexus.domain.lng.regas_auction import (
    BASES,
    PRICE_UNITS,
    THERM_PER_MWH,
    CargoTerms,
    CostLine,
    Market,
    RegasAuctionError,
    SlotCase,
    energy,
    evaluate,
    money,
    serialise,
    shifted,
    unit,
)
from eurogas_nexus.domain.valuation.quality import InputClass

DEFINITION_FILE = "regas_auction.toml"
CASE_STATES = ("open", "won", "lost", "lapsed")
OUTCOMES = ("won", "lost", "lapsed")
MAX_SLOT_DAYS = 62
#: The phrase the screen and the pack show beside a simulated answer (rule 17).
ILLUSTRATION = "illustration, not a bid level"
#: The only affordance towards orders (rule 8): disabled, with its note.
HEDGE_ORDERS_NOTE = "later step; a trader confirms in the execution tool"


class RegasAuctionCaseError(ValueError):
    """A refused request, with a stable code."""

    def __init__(self, code: str, message: str, status: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status

    def detail(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message}


# ----------------------------------------------------------------------------- definition


@dataclass(frozen=True)
class CostDefinition:
    key: str
    label: str
    basis: str
    origin: str  # register | computed | hand
    default: Decimal | None = None


@dataclass(frozen=True)
class Definition:
    quotation: str
    formats: tuple[str, ...]
    default_format: str
    at_limit_within_pct: Decimal
    default_time_zone: str
    offer_kinds: tuple[str, ...]
    pricing_periods: tuple[str, ...]
    default_pricing: str
    default_tolerance_pct: Decimal
    price_units: tuple[str, ...]
    delay_horizon_days: int
    days_tied: Decimal
    day_count: Decimal
    spread_pp: Decimal
    auction_leads: tuple[int, ...]
    offer_leads: tuple[int, ...]
    costs: tuple[CostDefinition, ...]
    source_path: str = ""

    def describe(self) -> dict[str, Any]:
        return {
            "quotation": self.quotation,
            "formats": list(self.formats),
            "default_format": self.default_format,
            "at_limit_within_pct": str(self.at_limit_within_pct),
            "default_time_zone": self.default_time_zone,
            "offer_kinds": list(self.offer_kinds),
            "pricing_periods": list(self.pricing_periods),
            "default_pricing": self.default_pricing,
            "default_tolerance_pct": str(self.default_tolerance_pct),
            "price_units": list(self.price_units),
            "delay_horizon_days": self.delay_horizon_days,
            "financing": {"days_tied": str(self.days_tied), "day_count": str(self.day_count),
                          "spread_pp": str(self.spread_pp)},
            "alerts": {"auction_close_lead_minutes": list(self.auction_leads),
                       "offer_expiry_lead_minutes": list(self.offer_leads)},
            "costs": [{"key": c.key, "label": c.label, "basis": c.basis, "from": c.origin,
                       "default": None if c.default is None else str(c.default)}
                      for c in self.costs],
            "source_path": self.source_path,
        }


def _dec(value: Any, where: str) -> Decimal:
    try:
        out = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{where}: {value!r} is not a number") from exc
    if not out.is_finite():
        raise ValueError(f"{where}: {value!r} is not a number")
    return out


def parse_definition(text: str, *, source_path: str = "") -> Definition:
    """The desk's definition file; a file that cannot be used says what to change."""

    from eurogas_nexus.domain.deals.formats import FormatError

    name = source_path or DEFINITION_FILE
    try:
        data = tomllib.loads(text)
        auction = data.get("auction") or {}
        offer = data.get("offer") or {}
        profile = data.get("profile") or {}
        financing = data.get("financing") or {}
        alerts = data.get("alerts") or {}
        quotation = str(auction.get("quotation", "per_mwh"))
        if quotation not in ("per_mwh", "per_slot"):
            raise ValueError("auction.quotation is per_mwh or per_slot")
        formats = tuple(str(v) for v in auction.get("formats") or ("sealed_bid",))
        default_format = str(auction.get("default_format", formats[0]))
        if default_format not in formats:
            raise ValueError("auction.default_format must be one of auction.formats")
        kinds = tuple(str(v) for v in offer.get("kinds") or ("fixed", "formula"))
        if not set(kinds) <= {"fixed", "formula"}:
            raise ValueError("offer.kinds are fixed and formula")
        pricing = tuple(str(v) for v in offer.get("pricing_periods") or ("send_out_days",))
        if not set(pricing) <= {"send_out_days", "month"}:
            raise ValueError("offer.pricing_periods are send_out_days and month")
        units = tuple(str(v) for v in offer.get("price_units") or PRICE_UNITS)
        if not set(units) <= set(PRICE_UNITS):
            raise ValueError(f"offer.price_units must be among {', '.join(PRICE_UNITS)}")
        costs = []
        seen = set()
        for index, item in enumerate(data.get("cost") or [], start=1):
            where = f"cost {index}"
            unknown = set(item) - {"key", "label", "basis", "from", "default"}
            if unknown:
                raise ValueError(f"{where}: unknown field(s) {', '.join(sorted(unknown))}")
            key = str(item.get("key") or "").strip()
            if not key or not key.replace("_", "").isalnum() or key in seen:
                raise ValueError(f"{where}: key must be a new word (letters, digits, _)")
            seen.add(key)
            basis = str(item.get("basis") or "")
            if basis not in BASES:
                raise ValueError(f"{where}: basis must be one of {', '.join(BASES)}")
            origin = str(item.get("from") or "hand")
            if origin not in ("register", "computed", "hand"):
                raise ValueError(f"{where}: from is register, computed or hand")
            if basis in ("hedge_spread", "financing") and origin != "computed":
                raise ValueError(f"{where}: a {basis} line is computed")
            default = item.get("default")
            costs.append(CostDefinition(
                key=key, label=str(item.get("label") or key), basis=basis, origin=origin,
                default=None if default is None else _dec(default, f"{where} default"),
            ))
        if sum(c.basis == "hedge_spread" for c in costs) > 1 or sum(
                c.basis == "financing" for c in costs) > 1:
            raise ValueError("at most one hedging line and one financing line")
        leads = {}
        for field in ("auction_close_lead_minutes", "offer_expiry_lead_minutes"):
            values = tuple(int(v) for v in alerts.get(field) or (120, 30))
            if not values or any(v <= 0 for v in values):
                raise ValueError(f"alerts.{field}: positive minutes")
            leads[field] = tuple(sorted(values, reverse=True))
        return Definition(
            quotation=quotation,
            formats=formats,
            default_format=default_format,
            at_limit_within_pct=_dec(auction.get("at_limit_within_pct", 2),
                                     "auction.at_limit_within_pct"),
            default_time_zone=str(auction.get("default_time_zone", "Europe/Amsterdam")),
            offer_kinds=kinds,
            pricing_periods=pricing,
            default_pricing=str(offer.get("default_pricing", pricing[0])),
            default_tolerance_pct=_dec(offer.get("default_tolerance_pct", 0),
                                       "offer.default_tolerance_pct"),
            price_units=units,
            delay_horizon_days=int(profile.get("delay_horizon_days", 7)),
            days_tied=_dec(financing.get("days_tied", 30), "financing.days_tied"),
            day_count=_dec(financing.get("day_count", 365), "financing.day_count"),
            spread_pp=_dec(financing.get("spread_pp", 0), "financing.spread_pp"),
            auction_leads=leads["auction_close_lead_minutes"],
            offer_leads=leads["offer_expiry_lead_minutes"],
            costs=tuple(costs),
            source_path=source_path,
        )
    except tomllib.TOMLDecodeError as exc:
        raise FormatError(f"{name}: {exc}") from exc
    except (ValueError, TypeError) as exc:
        raise FormatError(f"{name}: {exc}") from exc


def load_definition(environ: dict[str, str] | None = None) -> Definition:
    from eurogas_nexus.domain.deals.formats import desk_file_path

    path = desk_file_path(DEFINITION_FILE, environ)
    return parse_definition(path.read_text(encoding="utf-8"), source_path=str(path))


# ----------------------------------------------------------------------------- inputs


def actor_of(caller) -> str:
    principal = getattr(caller, "principal", caller)
    return str(getattr(principal, "name", None) or getattr(principal, "principal_id", None)
               or "api")[:128]


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _iso(value: datetime | date | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return _aware(value).astimezone(UTC).isoformat().replace("+00:00", "Z")
    return value.isoformat()


def _instant(text: Any, where: str) -> datetime:
    try:
        moment = datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except ValueError as exc:
        raise RegasAuctionCaseError("instant_invalid", f"{where}: not a date and time") from exc
    return _aware(moment).astimezone(UTC)


def _day(text: Any, where: str) -> date:
    try:
        return date.fromisoformat(str(text))
    except ValueError as exc:
        raise RegasAuctionCaseError("day_invalid", f"{where}: not a date") from exc


def _number(text: Any, where: str, *, positive: bool = False, allow_negative: bool = True
            ) -> Decimal:
    try:
        value = Decimal(str(text).strip())
    except (InvalidOperation, ValueError) as exc:
        raise RegasAuctionCaseError("number_invalid", f"{where}: not a number") from exc
    if not value.is_finite():
        raise RegasAuctionCaseError("number_invalid", f"{where}: not a number")
    if positive and value <= 0:
        raise RegasAuctionCaseError("number_invalid", f"{where}: must be above zero")
    if not allow_negative and value < 0:
        raise RegasAuctionCaseError("number_invalid", f"{where}: must not be negative")
    return value


def _stamp(value: Decimal | None, previous: dict | None, actor: str, now: datetime,
           **extra: Any) -> dict | None:
    """A hand-entered value with who entered it and when (kept when the value is unchanged)."""

    if value is None:
        return None
    if previous and previous.get("value") is not None and Decimal(previous["value"]) == value:
        return {**previous, **{k: v for k, v in extra.items() if v is not None}}
    return {"value": str(value), "by": actor, "at": _iso(now),
            **{k: v for k, v in extra.items() if v is not None}}


def _hub_currency(hub: str) -> str:
    from eurogas_nexus.domain.ontology.markets import quote_currency

    return quote_currency(hub, "GBP" if hub == "NBP" else "EUR")


def normalise(values: dict[str, Any], *, definition: Definition, previous: dict | None,
              actor: str, now: datetime) -> dict[str, Any]:
    """A case's inputs as stored: checked, exact text, every hand value stamped.

    Raises:
        RegasAuctionCaseError: with a stable code for each value that cannot be used.
    """

    from eurogas_nexus.domain.market.units import (
        DESK_ASSUMED_LNG_MWH_PER_M3,
        SLOT_ENERGY_UNITS,
        UnitConversionError,
        slot_energy_mwh,
    )

    prev = previous or {}
    terminal = values.get("terminal") or {}
    hub = str(terminal.get("hub") or "").upper().strip()
    if not hub:
        raise RegasAuctionCaseError("hub_required", "choose the terminal (its hub is needed)")
    name = str(terminal.get("name") or "").strip()
    if not name:
        raise RegasAuctionCaseError("terminal_required", "choose the terminal")
    slot = values.get("slot") or {}
    first = _day(slot.get("first_day"), "first send-out day")
    last = _day(slot.get("last_day"), "last send-out day")
    if last < first:
        raise RegasAuctionCaseError("slot_days_invalid", "the last send-out day is before the "
                                    "first")
    days = (last - first).days + 1
    if days > MAX_SLOT_DAYS:
        raise RegasAuctionCaseError("slot_days_invalid",
                                    f"a slot sends out over at most {MAX_SLOT_DAYS} days")
    quantity = _number(slot.get("quantity"), "slot quantity", positive=True)
    slot_unit = str(slot.get("unit") or "MWh")
    if slot_unit not in SLOT_ENERGY_UNITS:
        raise RegasAuctionCaseError("slot_unit_invalid",
                                    f"the slot unit is one of {', '.join(SLOT_ENERGY_UNITS)}")
    factor = None
    factor_source = None
    if slot_unit == "m3_lng":
        if slot.get("factor") not in (None, ""):
            factor = _number(slot.get("factor"), "MWh per m3 of LNG", positive=True)
            factor_source = str(slot.get("factor_source") or "entered by hand")[:200]
        else:
            factor = DESK_ASSUMED_LNG_MWH_PER_M3
            factor_source = "desk default"
        try:
            slot_energy_mwh(quantity, slot_unit, factor)
        except UnitConversionError as exc:
            raise RegasAuctionCaseError("slot_factor_invalid", str(exc)) from exc

    auction = values.get("auction") or {}
    closes = _instant(auction.get("closes_at"), "auction close")
    opens = _instant(auction["opens_at"], "auction open") if auction.get("opens_at") else None
    if opens is not None and closes <= opens:
        raise RegasAuctionCaseError("window_invalid", "the auction closes after it opens")
    fmt = str(auction.get("format") or definition.default_format)
    if fmt not in definition.formats:
        raise RegasAuctionCaseError("format_invalid",
                                    f"the auction format is one of {', '.join(definition.formats)}")
    quotation = str(auction.get("quotation") or definition.quotation)
    if quotation not in ("per_mwh", "per_slot"):
        raise RegasAuctionCaseError("quotation_invalid", "the auction quotes per MWh or per slot")
    prev_auction = prev.get("auction") or {}
    level_value = auction.get("level")
    level = None if level_value in (None, "") else _number(level_value, "auction level")
    level_entry = _stamp(level, prev_auction.get("level"), actor, now)
    history = list(prev_auction.get("level_history") or [])
    if level_entry is not None and (not history or history[-1].get("value") !=
                                    level_entry["value"]):
        history.append(dict(level_entry))

    owner = values.get("owner") or {}
    owner_name = str(owner.get("name") or "").strip()
    if not owner_name:
        raise RegasAuctionCaseError("owner_required", "choose the cargo owner")
    offer = values.get("offer") or {}
    kind = str(offer.get("kind") or "fixed")
    if kind not in definition.offer_kinds:
        raise RegasAuctionCaseError("offer_kind_invalid", "the offer is fixed or formula")
    expires = _instant(offer["expires_at"], "offer expiry") if offer.get("expires_at") else None
    tolerance = (definition.default_tolerance_pct if offer.get("tolerance_pct") in (None, "")
                 else _number(offer.get("tolerance_pct"), "volume tolerance",
                              allow_negative=False))
    offer_out: dict[str, Any] = {"kind": kind, "tolerance_pct": str(tolerance),
                                 "expires_at": _iso(expires)}
    if kind == "fixed":
        price_unit = str(offer.get("price_unit") or f"{_hub_currency(hub)}/MWh")
        if price_unit not in definition.price_units:
            raise RegasAuctionCaseError("price_unit_invalid", f"price unit {price_unit!r} is not "
                                        "offered")
        offer_out.update({
            "price": str(_number(offer.get("price"), "offer price")),
            "price_unit": price_unit,
        })
    else:
        index_hub = str(offer.get("index_hub") or hub).upper()
        pricing = str(offer.get("pricing") or definition.default_pricing)
        if pricing not in definition.pricing_periods:
            raise RegasAuctionCaseError("pricing_invalid", "the pricing period is not offered")
        month = str(offer.get("pricing_month") or "")
        if pricing == "month":
            try:
                date.fromisoformat(f"{month}-01")
            except ValueError as exc:
                raise RegasAuctionCaseError("pricing_invalid", "name the pricing month") from exc
        offer_out.update({
            "index_hub": index_hub,
            "pricing": pricing,
            "pricing_month": month if pricing == "month" else "",
            "slope": str(_number(offer.get("slope"), "formula slope")),
            "constant": str(_number(offer.get("constant") or 0, "formula constant")),
        })

    profile = values.get("profile") or {}
    weights = profile.get("weights")
    if weights:
        if len(weights) != days:
            raise RegasAuctionCaseError("profile_invalid", "one send-out figure per day")
        weights = [str(_number(w, "send-out", allow_negative=False)) for w in weights]
        if sum(Decimal(w) for w in weights) <= 0:
            raise RegasAuctionCaseError("profile_invalid", "the send-out adds up to zero")
    delay = int(values.get("delay_days") or 0)
    if not 0 <= delay <= definition.delay_horizon_days:
        raise RegasAuctionCaseError("delay_invalid",
                                    f"a delay of 0 to {definition.delay_horizon_days} days")

    prev_costs = prev.get("costs") or {}
    costs: dict[str, Any] = {}
    known = {c.key: c for c in definition.costs}
    for key, entry in (values.get("costs") or {}).items():
        if key not in known:
            raise RegasAuctionCaseError("cost_unknown", f"no cost line {key!r}")
        if entry in (None, "") or (isinstance(entry, dict) and entry.get("value") in (None, "")):
            continue
        raw = entry.get("value") if isinstance(entry, dict) else entry
        value = _number(raw, known[key].label)
        if known[key].basis == "percent_of_energy" and not 0 <= value < 100:
            raise RegasAuctionCaseError("number_invalid", f"{known[key].label}: 0 to 100 %")
        link = str(entry.get("link") or "").strip()[:500] if isinstance(entry, dict) else ""
        if link and not link.startswith(("https://", "http://")):
            raise RegasAuctionCaseError("link_invalid", "a link starts with https://")
        costs[key] = _stamp(value, prev_costs.get(key), actor, now, link=link or None)

    prev_prices = prev.get("prices") or {}
    prices: dict[str, Any] = {}
    for price_hub, entry in (values.get("prices") or {}).items():
        price_hub = str(price_hub).upper()
        held = prev_prices.get(price_hub) or {}
        out_entry: dict[str, Any] = {}
        if entry.get("all") not in (None, ""):
            out_entry["all"] = _stamp(_number(entry["all"], f"{price_hub} price"),
                                      held.get("all"), actor, now)
        for day_text, raw in (entry.get("days") or {}).items():
            if raw in (None, ""):
                continue
            _day(day_text, f"{price_hub} price day")
            out_entry.setdefault("days", {})[day_text] = _stamp(
                _number(raw, f"{price_hub} {day_text}"), (held.get("days") or {}).get(day_text),
                actor, now)
        if out_entry:
            prices[price_hub] = out_entry

    def hand(name: str, label: str) -> dict | None:
        raw = values.get(name)
        if raw in (None, ""):
            return None
        return _stamp(_number(raw, label, positive=True), prev.get(name), actor, now)

    return {
        "schema": 1,
        "title": str(values.get("title") or f"{name} {first:%d %b}")[:200],
        "terminal": {"terminal_id": str(terminal.get("terminal_id") or "").strip()[:128]
                     or f"hand:{name.lower()[:100]}",
                     "name": name[:200], "hub": hub,
                     "by_hand": not terminal.get("terminal_id")},
        "slot": {"first_day": first.isoformat(), "last_day": last.isoformat(),
                 "quantity": str(quantity), "unit": slot_unit,
                 "factor": None if factor is None else str(factor),
                 "factor_source": factor_source,
                 "source": str(slot.get("source") or "")[:300]},
        "auction": {"format": fmt, "opens_at": _iso(opens), "closes_at": _iso(closes),
                    "time_zone": str(auction.get("time_zone") or definition.default_time_zone),
                    "quotation": quotation, "level": level_entry, "level_history": history,
                    "notice_key": auction.get("notice_key") or None,
                    "link": str(auction.get("link") or "")[:500] or None},
        "owner": {"counterparty_id": owner.get("counterparty_id") or None,
                  "name": owner_name[:200], "by_hand": not owner.get("counterparty_id")},
        "offer": offer_out,
        "profile": {"weights": weights} if weights else {"weights": None},
        "delay_days": delay,
        "costs": costs,
        "prices": prices,
        "fx": hand("fx", "FX rate"),
        "rate_pct": hand("rate_pct", "benchmark rate"),
    }


# ----------------------------------------------------------------------------- the answer


def _entered(entry: dict | None, label: str) -> Valued | None:
    if not entry or entry.get("value") is None:
        return None
    when = str(entry.get("at") or "")[:10]
    return Valued(Decimal(entry["value"]), InputClass.ASSUMPTION,
                  f"entered by hand by {entry.get('by')} on {when}: {label}")


def _from_input(item, label: str) -> Valued:
    if not item.held:
        return missing(f"{label}: {getattr(item, 'detail', {}).get('reason', 'not held')}"
                       if isinstance(getattr(item, "detail", None), dict) else label)
    return Valued(Decimal(str(item.value)), item.input_class, item.label or label)


@dataclass
class _Reads:
    """What one answer read: each price with its time and source, for the snapshot."""

    rows: list[dict[str, Any]]

    def add(self, key: str, valued: Valued, item=None, *, native: tuple[str, str] | None = None
            ) -> None:
        self.rows.append({
            "key": key,
            "value": None if valued.value is None else str(valued.value),
            "class": str(valued.input_class),
            "source": valued.source,
            "as_of_utc": _iso(getattr(item, "as_of_utc", None)) if item is not None else None,
            "native_value": native[0] if native else None,
            "native_unit": native[1] if native else None,
        })


def _native(item) -> tuple[str, str] | None:
    detail = getattr(item, "detail", None) or {}
    if detail.get("native_value") and detail.get("native_unit"):
        return str(detail["native_value"]), str(detail["native_unit"])
    return None


def _price(reader, reads: _Reads, inputs: dict, hub: str, label: str, period) -> Valued:
    """A hub price per MWh: entered by hand for this day or the whole slot, else the reader."""

    entry = (inputs.get("prices") or {}).get(hub) or {}
    hand = _entered((entry.get("days") or {}).get(label) or entry.get("all"),
                    f"{hub} {label}")
    if hand is not None:
        reads.add(f"price:{hub}:{label}", hand)
        return hand
    item = reader.price(hub, period)
    valued = _from_input(item, f"{hub} {label}")
    reads.add(f"price:{hub}:{label}", valued, item, native=_native(item))
    return valued


def _month_label(month: str) -> str:
    return date.fromisoformat(f"{month}-01").strftime("%b-%y")


def _contract_name(month: str, today: date) -> str:
    """The month as the screen names it (Trayport style): BOM for the current month."""

    return "BOM" if month == f"{today.year:04d}-{today.month:02d}" else _month_label(month)


def build(session, caller, inputs: dict[str, Any], *, book_id: str | None = None,
          now: datetime | None = None, reader=None, definition: Definition | None = None):
    """The domain case and market for a case's inputs, what was read, and the reader."""

    from eurogas_nexus.application.lng_cargo_economics import terminal_charges
    from eurogas_nexus.domain.market.units import slot_energy_mwh
    from eurogas_nexus.domain.valuation.periods import DeliveryPeriod

    definition = definition or load_definition()
    now = _aware(now) or datetime.now(UTC)
    if reader is None:
        from eurogas_nexus.application.valuation_snapshot import open_valuation_snapshot

        reader = open_valuation_snapshot(session, caller=caller, as_of_utc=now, book_id=book_id)
    reads = _Reads([])
    terminal = inputs["terminal"]
    hub = terminal["hub"]
    currency = _hub_currency(hub)
    slot = inputs["slot"]
    first = date.fromisoformat(slot["first_day"])
    last = date.fromisoformat(slot["last_day"])
    days = tuple(first + timedelta(days=i) for i in range((last - first).days + 1))
    quantity = Decimal(slot["quantity"])
    factor = Decimal(slot["factor"]) if slot.get("factor") else None
    e_mwh, used_factor = slot_energy_mwh(quantity, slot["unit"], factor)
    slot_source = (f"slot as announced: {quantity} {slot['unit']} x {used_factor} MWh per "
                   f"{slot['unit']}" + (f" ({slot.get('factor_source')})"
                                       if slot.get("factor_source") else ""))
    energy_valued = Valued(
        e_mwh,
        InputClass.ASSUMPTION if slot.get("factor_source") == "desk default"
        else InputClass.SOURCED if inputs["auction"].get("notice_key") else InputClass.ASSUMPTION,
        slot_source,
    )
    month = f"{first.year:04d}-{first.month:02d}"
    month_period = DeliveryPeriod.month(first.year, first.month)

    # Prices for every send-out day, the delay horizon included.
    horizon = definition.delay_horizon_days
    price_days = shifted(days, 0) + tuple(last + timedelta(days=i) for i in range(1, horizon + 2))
    prices: dict[tuple[str, str], Valued] = {}
    for day in price_days:
        prices[(hub, day.isoformat())] = _price(reader, reads, inputs, hub, day.isoformat(),
                                                DeliveryPeriod.gas_day(day))
    offer = inputs["offer"]
    index_currency = ""
    if offer["kind"] == "formula":
        index_hub = offer["index_hub"]
        index_currency = _hub_currency(index_hub)
        if offer["pricing"] == "month":
            year, number = (int(x) for x in offer["pricing_month"].split("-"))
            prices[(index_hub, offer["pricing_month"])] = _price(
                reader, reads, inputs, index_hub, offer["pricing_month"],
                DeliveryPeriod.month(year, number))
        elif index_hub != hub:
            for day in price_days:
                prices[(index_hub, day.isoformat())] = _price(
                    reader, reads, inputs, index_hub, day.isoformat(), DeliveryPeriod.gas_day(day))

    # Half the bid/offer per hedge month, from executable quotes only.
    spreads: dict[tuple[str, str], Valued] = {}
    hedge_hubs = {hub} | ({offer["index_hub"]} if offer["kind"] == "formula" else set())
    months = sorted({f"{d.year:04d}-{d.month:02d}" for d in price_days}
                    | ({offer["pricing_month"]} if offer.get("pricing_month") else set()))
    for hedge_hub in sorted(hedge_hubs):
        for label in months:
            year, number = (int(x) for x in label.split("-"))
            period = DeliveryPeriod.month(year, number)
            bid, ask = reader.price(hedge_hub, period, "bid"), reader.price(hedge_hub, period,
                                                                               "ask")
            if (bid.held and ask.held and bid.input_class == InputClass.SOURCED
                    and ask.input_class == InputClass.SOURCED and ask.value >= bid.value):
                half = (Decimal(str(ask.value)) - Decimal(str(bid.value))) / 2
                spreads[(hedge_hub, label)] = Valued(
                    half, InputClass.SOURCED, f"half of {hedge_hub} {_month_label(label)} "
                    f"bid {bid.value} / offer {ask.value} ({bid.label})")
                reads.add(f"spread:{hedge_hub}:{label}", spreads[(hedge_hub, label)], bid)

    # FX for the delivery month.
    def fx(base: str) -> Valued:
        if base == currency:
            return Valued(Decimal(1), InputClass.SOURCED, "same currency")
        hand = _entered(inputs.get("fx"), f"{base}/{currency}")
        if hand is not None:
            reads.add(f"fx:{base}/{currency}", hand)
            return hand
        item = reader.fx(base, currency, month_period)
        valued = _from_input(item, f"{base}/{currency} {month}")
        reads.add(f"fx:{base}/{currency}", valued, item)
        return valued

    cargo_fx = index_fx = Valued(Decimal(1), InputClass.SOURCED, "same currency")
    if offer["kind"] == "fixed":
        price_unit = offer["price_unit"]
        code = price_unit.split("/")[0]
        cargo_fx = fx("GBP" if code == "GBp" else code)
        cargo = CargoTerms(kind="fixed", price_unit=price_unit,
                           fixed_price=Valued(Decimal(offer["price"]), InputClass.FIRM_MARK,
                                              f"the cargo owner's offer ({price_unit})"),
                           tolerance_pct=Decimal(offer["tolerance_pct"]))
    else:
        if offer["index_hub"] != hub:
            index_fx = fx(index_currency)
        cargo = CargoTerms(
            kind="formula", index_hub=offer["index_hub"], pricing=offer["pricing"],
            pricing_month=offer.get("pricing_month") or "",
            slope=Valued(Decimal(offer["slope"]), InputClass.FIRM_MARK,
                         "the cargo owner's formula"),
            constant=Valued(Decimal(offer["constant"]), InputClass.FIRM_MARK,
                            "the cargo owner's formula"),
            tolerance_pct=Decimal(offer["tolerance_pct"]),
        )

    # The cost of money: the benchmark plus the desk's spread.
    rate_hand = _entered(inputs.get("rate_pct"), f"{currency} benchmark rate")
    if rate_hand is not None:
        benchmark = rate_hand
    else:
        item = reader.rate(currency)
        benchmark = _from_input(item, f"{currency} overnight benchmark")
        reads.add(f"rate:{currency}", benchmark, item)
    rate = (missing(benchmark.source) if not benchmark.held else Valued(
        benchmark.value + definition.spread_pp, benchmark.input_class,
        f"{benchmark.source} + {definition.spread_pp} pp desk spread"))

    # Terminal figures from the desk engine.
    charges = meta = None
    if not terminal.get("by_hand"):
        try:
            found = terminal_charges(session, reader, terminal["terminal_id"],
                                     arrival_month=month, energy_mwh=float(e_mwh))
        except Exception:  # noqa: BLE001 - a register problem leaves the lines to the desk
            found = None
        if found is not None:
            charges, meta = found

    def register_value(key: str) -> tuple[Valued, str] | None:
        if charges is None:
            return None
        if key == "regas_fee" and charges.regas_total.held:
            source = charges.regas_total.source
            origin = "publication" if source.startswith("published") else "register"
            return Valued(charges.regas_total.value, charges.regas_total.input_class,
                          f"{origin}: {source}"), origin
        if key == "losses" and charges.gas_in_kind_pct.held and "excluded" not in \
                charges.gas_in_kind_pct.source:
            source = charges.gas_in_kind_pct.source
            origin = "publication" if source.startswith("published") else "register"
            return charges.gas_in_kind_pct, origin
        if key == "entry" and charges.entry.held and "excluded" not in charges.entry.source:
            source = charges.entry.source
            origin = "publication" if source.startswith("published") else "register"
            return charges.entry, origin
        return None

    lines = []
    for spec in definition.costs:
        entry = (inputs.get("costs") or {}).get(spec.key)
        hand = _entered(entry, spec.label)
        if hand is not None:
            lines.append(CostLine(spec.key, spec.label, spec.basis, hand, origin="hand",
                                  entered_by=entry.get("by", ""), entered_at=entry.get("at", ""),
                                  link=entry.get("link") or ""))
            continue
        found = register_value(spec.key) if spec.origin == "register" else None
        if found is not None:
            lines.append(CostLine(spec.key, spec.label, spec.basis, found[0], origin=found[1]))
        elif spec.origin == "computed":
            value = (Valued(spec.default, InputClass.ASSUMPTION, "desk default")
                     if spec.default is not None else Valued(Decimal(0), InputClass.DERIVED,
                                                             "computed"))
            lines.append(CostLine(spec.key, spec.label, spec.basis, value, origin="computed"))
        elif spec.default is not None:
            lines.append(CostLine(spec.key, spec.label, spec.basis,
                                  Valued(spec.default, InputClass.ASSUMPTION,
                                         f"desk default ({DEFINITION_FILE})"), origin="default"))
        else:
            lines.append(CostLine(spec.key, spec.label, spec.basis,
                                  missing(f"{spec.label}: enter it from the operator's tariff"),
                                  origin=spec.origin))
    for item in getattr(charges, "other_items", ()) or ():
        lines.append(CostLine(item.key, item.label, "per_slot",
                              Valued(item.total, item.input_class, item.source),
                              origin="publication"))

    level_entry = inputs["auction"].get("level")
    level = _entered(level_entry, "auction level") if level_entry else None
    weights = inputs["profile"].get("weights")
    hedging = next((c for c in definition.costs if c.basis == "hedge_spread"), None)
    case = SlotCase(
        hub=hub,
        currency=currency,
        energy_mwh=energy_valued,
        days=days,
        weights=tuple(Decimal(w) for w in weights) if weights else tuple(Decimal(1) for _ in days),
        cargo=cargo,
        cost_lines=tuple(lines),
        quotation=inputs["auction"]["quotation"],
        level=level,
        at_limit_within_pct=definition.at_limit_within_pct,
        delay_days=int(inputs.get("delay_days") or 0),
        financing_days=definition.days_tied,
        day_count=definition.day_count,
        rate_pct=rate,
        cargo_fx=cargo_fx,
        index_fx=index_fx,
        index_currency=index_currency,
        hedge_default_half_spread=hedging.default if hedging and hedging.default is not None
        else Decimal("0.05"),
    )
    return case, Market(prices, spreads), reads, reader, meta


def price_steps(case: SlotCase) -> dict[str, tuple[Decimal, str]]:
    """Sensitivity steps in each hub's own quotation: 1 p/th at NBP, else 1 per MWh."""

    steps = {}
    for hub in {case.hub, case.cargo.index_hub} - {""}:
        currency = _hub_currency(hub)
        steps[hub] = ((Decimal("0.01") * THERM_PER_MWH, "1 p/th") if currency == "GBP"
                      else (Decimal(1), f"1 {currency}/MWh"))
    return steps


def answer(session, caller, inputs: dict[str, Any], *, book_id: str | None = None,
           now: datetime | None = None, reader=None, definition: Definition | None = None,
           closes_at: datetime | None = None) -> tuple[dict[str, Any], Any]:
    """The live answer for a case's inputs, and the reader it was read through."""

    from eurogas_nexus.domain.deals.position import desk_unit, in_desk_unit
    from eurogas_nexus.domain.lng.in_transit import last_trading_day

    definition = definition or load_definition()
    now = _aware(now) or datetime.now(UTC)
    case, market, reads, reader, meta = build(session, caller, inputs, book_id=book_id, now=now,
                                              reader=reader, definition=definition)
    result = evaluate(case, market, price_steps=price_steps(case))
    out = serialise(case, result)
    out["as_of_utc"] = _iso(now)
    out["illustration"] = ILLUSTRATION if result.simulated else None
    out["prepare_hedge_orders"] = {"enabled": False, "note": HEDGE_ORDERS_NOTE}
    out["definition_source"] = definition.source_path
    labels = {line.key: line.label for line in case.cost_lines}
    totals = {item["key"]: item for item in out.get("lines", [])}
    out["cost_lines"] = [
        {
            "key": line.key, "label": line.label, "basis": line.basis,
            "value": None if line.value.value is None else str(line.value.value),
            "input_class": str(line.value.input_class), "source": line.value.source,
            "origin": line.origin, "entered_by": line.entered_by or None,
            "entered_at": line.entered_at or None, "link": line.link or None,
            "held": line.value.held,
            "total": (totals.get(line.key) or {}).get("total"),
            "per_mwh": (totals.get(line.key) or {}).get("per_mwh"),
        }
        for line in case.cost_lines
    ]
    out["labels"] = labels
    out["reads"] = reads.rows
    out["missing_labels"] = [_missing_label(name, case) for name in result.missing]
    out["slot"] = {
        "energy_mwh": energy(case.energy_mwh.value), "source": case.energy_mwh.source,
        "days": len(case.days), "first_day": case.days[0].isoformat(),
        "last_day": case.days[-1].isoformat(),
    }
    out["terminal_meta"] = meta
    # Native quotation beside each day's price (rule 17).
    natives = {row["key"]: row for row in reads.rows}
    for row in out.get("days", []):
        found = natives.get(f"price:{case.hub}:{row['day']}") or {}
        row.update({"native_value": found.get("native_value"),
                    "native_unit": found.get("native_unit"),
                    "class": found.get("class"), "source": found.get("source"),
                    "as_of_utc": found.get("as_of_utc")})
    today = now.date()
    for leg in out.get("hedges", []):
        year, number = (int(x) for x in leg["month"].split("-"))
        start = date(year, number, 1)
        end = date(year + (number == 12), number % 12 + 1, 1) - timedelta(days=1)
        lead = max(start, today)
        mwh = Decimal(leg["mwh"])
        leg.update({
            "contract": _contract_name(leg["month"], today),
            "desk_unit": desk_unit(leg["hub"]),
            "desk_volume": str(in_desk_unit(leg["hub"], mwh, lead, end)) if lead <= end
            else None,
            "instrument": "future",
            "last_trading_day": last_trading_day(leg["month"]).isoformat(),
            "month_futures_stopped": last_trading_day(leg["month"]) < today,
        })
    if closes_at is not None:
        out["auction_closes_in_seconds"] = int((_aware(closes_at) - now).total_seconds())
    expires = inputs["offer"].get("expires_at")
    if expires:
        expiry = _instant(expires, "offer expiry")
        out["offer_expires_in_seconds"] = int((expiry - now).total_seconds())
        if closes_at is not None and expiry < _aware(closes_at):
            out["offer_lapses_before_close"] = True
    out["assumptions"] = _assumptions(case, definition, inputs)
    return out, reader


def _missing_label(name: str, case: SlotCase) -> dict[str, str]:
    kind, _, rest = name.partition(":")
    return {"key": name, "kind": kind, "what": rest or kind}


def _assumptions(case: SlotCase, definition: Definition, inputs: dict) -> list[dict[str, str]]:
    """Every default the answer stands on, said on the screen and in the pack."""

    out = [
        {"key": "revenue_at_mid", "text": "Hub revenue at each day's price (the contract that "
         "covers the day); crossing the bid/offer is the hedging line."},
        {"key": "financing", "text": f"Financing: {definition.days_tied} days at the benchmark "
         f"plus {definition.spread_pp} pp, ACT/{definition.day_count}, on the cargo payment."},
        {"key": "at_limit", "text": f"At the limit: headroom within "
         f"{definition.at_limit_within_pct} % of the maximum bid."},
    ]
    if not inputs["profile"].get("weights"):
        out.append({"key": "profile_even", "text": "Send-out even over the slot's days."})
    if inputs["slot"].get("factor_source") == "desk default":
        out.append({"key": "lng_factor", "text": f"{inputs['slot']['factor']} MWh per m3 of "
                    "LNG (desk default; the operator's own factor replaces it)."})
    if case.cargo.kind == "formula" and case.cargo.pricing == "send_out_days":
        out.append({"key": "formula_days", "text": "The formula's index is the average of the "
                    "send-out days' prices, each day weighted the same."})
    for line in case.cost_lines:
        if line.origin == "default":
            out.append({"key": f"default:{line.key}",
                        "text": f"{line.label}: desk default {line.value.value}."})
    return out


# ----------------------------------------------------------------------------- store


def _require_book(session, book_id: str | None) -> str:
    from eurogas_nexus.db.models import TradingBookRecord

    if not book_id:
        raise RegasAuctionCaseError("book_required", "choose the book the case belongs to")
    if session.get(TradingBookRecord, book_id) is None:
        raise RegasAuctionCaseError("book_not_in_scope", f"book {book_id!r} is not one of yours",
                                    status=404)
    return book_id


def _audit(session, *, actor: str, action: str, resource: str, detail: str, now: datetime,
           outcome: str = "recorded") -> None:
    from eurogas_nexus.db.repositories.audit import record_audit_event

    record_audit_event(session, event_type="desk.regas_auction", principal=actor, action=action,
                       resource=resource, outcome=outcome, detail=detail[:900], now_utc=now)


def _get(session, case_id: str):
    from eurogas_nexus.db.models import RegasAuctionCaseRecord

    row = session.get(RegasAuctionCaseRecord, case_id)
    if row is None:
        raise RegasAuctionCaseError("case_not_found", "no such case in your books", status=404)
    return row


def case_payload(row) -> dict[str, Any]:
    return {
        "case_id": row.case_id,
        "book_id": row.book_id,
        "title": row.title,
        "terminal_id": row.terminal_id,
        "terminal_name": row.terminal_name,
        "hub": row.hub,
        "counterparty_id": row.counterparty_id,
        "counterparty_name": row.counterparty_name,
        "state": row.state,
        "auction_opens_at_utc": _iso(row.auction_opens_at_utc),
        "auction_closes_at_utc": _iso(row.auction_closes_at_utc),
        "offer_expires_at_utc": _iso(row.offer_expires_at_utc),
        "notice_key": row.notice_key,
        "inputs": row.inputs,
        "version": row.version,
        "created_by": row.created_by,
        "created_at_utc": _iso(row.created_at_utc),
        "updated_by": row.updated_by,
        "updated_at_utc": _iso(row.updated_at_utc),
        "closed_by": row.closed_by,
        "closed_at_utc": _iso(row.closed_at_utc),
        "close_note": row.close_note,
        "position_seam": row.position_seam,
    }


def _apply(row, inputs: dict[str, Any]) -> None:
    row.title = inputs["title"]
    row.terminal_id = inputs["terminal"]["terminal_id"]
    row.terminal_name = inputs["terminal"]["name"]
    row.hub = inputs["terminal"]["hub"]
    row.counterparty_id = inputs["owner"]["counterparty_id"]
    row.counterparty_name = inputs["owner"]["name"]
    row.auction_opens_at_utc = (_instant(inputs["auction"]["opens_at"], "open")
                                if inputs["auction"].get("opens_at") else None)
    row.auction_closes_at_utc = _instant(inputs["auction"]["closes_at"], "close")
    row.offer_expires_at_utc = (_instant(inputs["offer"]["expires_at"], "expiry")
                                if inputs["offer"].get("expires_at") else None)
    row.notice_key = inputs["auction"].get("notice_key")
    row.inputs = inputs


def create_case(session, caller, book_id: str | None, values: dict[str, Any], *,
                now: datetime | None = None) -> dict[str, Any]:
    from eurogas_nexus.db.models import RegasAuctionCaseRecord

    now = _aware(now) or datetime.now(UTC)
    actor = actor_of(caller)
    book = _require_book(session, book_id)
    inputs = normalise(values, definition=load_definition(), previous=None, actor=actor, now=now)
    row = RegasAuctionCaseRecord(case_id=f"rac-{uuid.uuid4().hex[:20]}", book_id=book,
                                 state="open", version=1, created_by=actor, created_at_utc=now,
                                 updated_by=actor, updated_at_utc=now)
    _apply(row, inputs)
    session.add(row)
    session.flush()
    _audit(session, actor=actor, action="regas_auction.create",
           resource=f"regas-case:{row.case_id}", now=now,
           detail=f"{row.title}: {row.terminal_name} ({row.hub}), owner "
           f"{row.counterparty_name}, closes {_iso(row.auction_closes_at_utc)}")
    return case_payload(row)


def update_case(session, caller, case_id: str, values: dict[str, Any], *, version: int,
                now: datetime | None = None) -> dict[str, Any]:
    now = _aware(now) or datetime.now(UTC)
    actor = actor_of(caller)
    row = _get(session, case_id)
    if row.state != "open":
        raise RegasAuctionCaseError("case_closed", "the case is closed", status=409)
    if row.version != version:
        raise RegasAuctionCaseError("case_changed", "someone changed the case: reload it",
                                    status=409)
    inputs = normalise(values, definition=load_definition(), previous=row.inputs, actor=actor,
                       now=now)
    changed = sorted(key for key in inputs if inputs.get(key) != (row.inputs or {}).get(key))
    _apply(row, inputs)
    row.version += 1
    row.updated_by = actor
    row.updated_at_utc = now
    session.flush()
    _audit(session, actor=actor, action="regas_auction.update",
           resource=f"regas-case:{row.case_id}", now=now,
           detail=f"version {row.version}: {', '.join(changed) or 'no change'}")
    return case_payload(row)


def list_cases(session, *, state: str | None = None) -> list[dict[str, Any]]:
    from eurogas_nexus.db.models import RegasAuctionCaseRecord as R

    query = session.query(R)
    if state:
        query = query.filter(R.state == state)
    rows = query.order_by(R.state != "open", R.auction_closes_at_utc.desc()).all()
    return [{k: v for k, v in case_payload(row).items() if k != "inputs"} for row in rows]


def case_answer(session, caller, case_id: str, *, now: datetime | None = None, reader=None
                ) -> dict[str, Any]:
    row = _get(session, case_id)
    data, _reader = answer(session, caller, row.inputs, book_id=row.book_id, now=now,
                           reader=reader, closes_at=row.auction_closes_at_utc)
    return {"case": case_payload(row), "answer": data}


def save_snapshot(session, caller, case_id: str, *, note: str = "", now: datetime | None = None,
                  reader=None) -> dict[str, Any]:
    """Keep the answer as it is now: inputs, every price with its time and source, result."""

    from eurogas_nexus.application.valuation_snapshot import freeze_snapshot
    from eurogas_nexus.db.models import RegasAuctionSnapshotRecord

    now = _aware(now) or datetime.now(UTC)
    actor = actor_of(caller)
    row = _get(session, case_id)
    data, used = answer(session, caller, row.inputs, book_id=row.book_id, now=now, reader=reader,
                        closes_at=row.auction_closes_at_utc)
    manifest_id = None
    if hasattr(used, "manifest"):
        try:
            manifest_id = freeze_snapshot(session, used, purpose="regas_auction",
                                          created_by=actor).snapshot_id
        except Exception:  # noqa: BLE001 - the case snapshot holds every read itself
            manifest_id = None
    snap = RegasAuctionSnapshotRecord(
        snapshot_id=f"ras-{uuid.uuid4().hex[:20]}", case_id=row.case_id, book_id=row.book_id,
        case_version=row.version, saved_by=actor, saved_at_utc=now, note=note[:500],
        state=data["state"], inputs=row.inputs, prices=data["reads"],
        result={k: v for k, v in data.items() if k != "reads"},
        valuation_snapshot_id=manifest_id,
    )
    session.add(snap)
    session.flush()
    _audit(session, actor=actor, action="regas_auction.snapshot",
           resource=f"regas-case:{row.case_id}", now=now,
           detail=f"snapshot {snap.snapshot_id}: {data['state']}, max bid "
           f"{data.get('max_bid_quoted')} ({data.get('quotation')}), level {data.get('level')}"
           + (f"; {note[:200]}" if note else ""))
    return snapshot_payload(snap)


def snapshot_payload(row) -> dict[str, Any]:
    result = row.result or {}
    return {
        "snapshot_id": row.snapshot_id, "case_id": row.case_id, "case_version": row.case_version,
        "saved_by": row.saved_by, "saved_at_utc": _iso(row.saved_at_utc), "note": row.note,
        "state": row.state, "max_bid_quoted": result.get("max_bid_quoted"),
        "max_bid_total": result.get("max_bid_total"), "level": result.get("level"),
        "headroom": result.get("headroom"), "quotation": result.get("quotation"),
        "currency": result.get("currency"), "simulated": result.get("simulated"),
        "hand_entered": result.get("hand_entered") or [], "prices": row.prices,
        "valuation_snapshot_id": row.valuation_snapshot_id,
    }


def snapshots(session, case_id: str) -> list[dict[str, Any]]:
    from eurogas_nexus.db.models import RegasAuctionSnapshotRecord as S

    _get(session, case_id)
    rows = session.query(S).filter(S.case_id == case_id).order_by(S.saved_at_utc).all()
    return [snapshot_payload(row) for row in rows]


def position_seam(row, result: dict[str, Any]) -> dict[str, Any]:
    """What a won slot and its hedges would become in the one position source, later.

    The cargo-in-transit plan already reads a regas slot (``regas_slots``), its cargo and the
    hedges linked to it (``lng_cargo_hedges``) into the position ladder; booking a won slot is
    writing those rows, a later step a person confirms. This records exactly what they would
    hold; nothing is written to them here.
    """

    inputs = row.inputs
    days = int(result.get("slot", {}).get("days") or 0)
    sent = Decimal(result.get("energy_sent_out_mwh") or 0)
    return {
        "booked": False,
        "note": "recorded for the booking step; nothing is in the position yet",
        "regas_slot": {
            "terminal_name": row.terminal_name, "hub": row.hub, "book_id": row.book_id,
            "window_start": inputs["slot"]["first_day"], "window_end": inputs["slot"]["last_day"],
            "energy_gwh": str(Decimal(result.get("energy_unloaded_mwh") or 0) / 1000),
            "send_out_gwh_d": str(sent / days / 1000) if days else None,
            "source_system": "REGAS_AUCTION", "source_reference": row.case_id,
        },
        "hedges": [{"hub": leg["hub"], "delivery_month": leg["month"],
                    "mwh": ("-" if leg["side"] == "sell" else "") + leg["mwh"]}
                   for leg in result.get("hedges") or []],
        "cargo_purchase": {"counterparty": row.counterparty_name,
                           "counterparty_id": row.counterparty_id,
                           "energy_mwh": result.get("energy_unloaded_mwh"),
                           "price_per_mwh": result.get("cargo_price_per_mwh"),
                           "currency": result.get("currency")},
    }


def close_case(session, caller, case_id: str, *, outcome: str, note: str,
               now: datetime | None = None, reader=None) -> dict[str, Any]:
    now = _aware(now) or datetime.now(UTC)
    actor = actor_of(caller)
    if outcome not in OUTCOMES:
        raise RegasAuctionCaseError("outcome_invalid", "a case closes won, lost or lapsed")
    if len((note or "").strip()) < 3:
        raise RegasAuctionCaseError("note_required", "say in a few words how it ended")
    row = _get(session, case_id)
    if row.state != "open":
        raise RegasAuctionCaseError("case_closed", "the case is already closed", status=409)
    if outcome == "won":
        data, _ = answer(session, caller, row.inputs, book_id=row.book_id, now=now, reader=reader,
                         closes_at=row.auction_closes_at_utc)
        row.position_seam = position_seam(row, data)
    row.state = outcome
    row.closed_by = actor
    row.closed_at_utc = now
    row.close_note = note.strip()[:1000]
    row.version += 1
    session.flush()
    _audit(session, actor=actor, action="regas_auction.close",
           resource=f"regas-case:{row.case_id}", now=now, outcome=outcome,
           detail=f"{outcome}: {row.close_note[:300]}")
    return case_payload(row)


def choices(session) -> dict[str, Any]:
    """What a case is picked from: terminals, cargo owners, books, the operators' slot notices
    and the desk's definition (rule 19: the trader chooses from what exists)."""

    from eurogas_nexus.application.lng_cargo_economics import terminal_choices
    from eurogas_nexus.application.tariff_book import list_notices
    from eurogas_nexus.db.models import CreditLineRecord, TradingBookRecord

    definition = load_definition()
    try:
        notices = [n for n in list_notices(session, days=60, kind="lng_slot", include_past_days=3)
                   if n.get("state", "open") == "open"]
    except Exception:  # noqa: BLE001 - no notices held is the normal case
        notices = []
    return {
        "terminals": terminal_choices(session),
        "owners": [{"counterparty_id": row.counterparty_id, "name": row.name,
                    "currency": row.currency}
                   for row in session.query(CreditLineRecord).order_by(CreditLineRecord.name)],
        "books": [{"book_id": row.book_id, "name": row.name}
                  for row in session.query(TradingBookRecord).order_by(TradingBookRecord.name)
                  if row.active],
        "notices": notices,
        "definition": definition.describe(),
        "hedge_orders": {"enabled": False, "note": HEDGE_ORDERS_NOTE},
    }


# ----------------------------------------------------------------------------- what-if


def what_if(session, caller, case_id: str, *, now: datetime | None = None, reader=None
            ) -> dict[str, Any]:
    """The slot and its hedges put on, read-only: position by hub and month, each mandate and
    the cargo owner's credit line before and after. Nothing is booked."""

    from eurogas_nexus.application.limits_service import (
        credit_exposure_with,
        mandate_usage_with,
    )
    from eurogas_nexus.domain.risk.limits import CounterpartyLeg, MandateLeg

    now = _aware(now) or datetime.now(UTC)
    row = _get(session, case_id)
    data, _ = answer(session, caller, row.inputs, book_id=row.book_id, now=now, reader=reader,
                     closes_at=row.auction_closes_at_utc)
    if not data.get("computed"):
        return {"computed": False, "missing": data.get("missing", []), "booked": False}
    legs = []
    for day_row in data.get("days", []):
        day = date.fromisoformat(day_row["day"])
        legs.append(MandateLeg(reference=f"{row.case_id}:send-out:{day_row['day']}",
                               kind="physical", hub=row.hub, book_id=row.book_id, account="",
                               first_gas_day=day, last_gas_day=day,
                               mwh_per_day=float(Decimal(day_row["sent_out_mwh"])),
                               instrument="physical", label=f"{row.title} send-out"))
    for leg in data.get("hedges", []):
        year, number = (int(x) for x in leg["month"].split("-"))
        start = date(year, number, 1)
        end = date(year + (number == 12), number % 12 + 1, 1) - timedelta(days=1)
        days = (end - start).days + 1
        signed = Decimal(leg["mwh"]) * (-1 if leg["side"] == "sell" else 1)
        legs.append(MandateLeg(reference=f"{row.case_id}:hedge:{leg['hub']}:{leg['month']}",
                               kind="financial", hub=leg["hub"], book_id=row.book_id, account="",
                               first_gas_day=start, last_gas_day=end,
                               mwh_per_day=float(signed / days), instrument="future",
                               label=f"{row.title} hedge {leg['contract']}"))
    today = now.date()
    mandates = mandate_usage_with(caller, today, legs, books=(row.book_id,))
    credit = None
    if row.counterparty_id:
        purchase = CounterpartyLeg(
            reference=f"{row.case_id}:cargo", kind="otc_trade", hub=row.hub,
            currency=data["currency"], first_gas_day=date.fromisoformat(data["slot"]["first_day"]),
            last_gas_day=date.fromisoformat(data["slot"]["last_day"]),
            mwh_per_day=float(Decimal(data["energy_unloaded_mwh"]) / data["slot"]["days"]),
            price=float(Decimal(data["cargo_price_per_mwh"])),
        )
        credit = credit_exposure_with(caller, today, row.counterparty_id, [purchase])
    position: dict[tuple[str, str], Decimal] = {}
    for leg in legs:
        day = leg.first_gas_day
        while day <= leg.last_gas_day:
            key = (leg.hub, f"{day.year:04d}-{day.month:02d}")
            position[key] = position.get(key, Decimal(0)) + Decimal(str(leg.mwh_per_day))
            day += timedelta(days=1)
    return {
        "computed": True,
        "booked": False,
        "note": "A what-if: nothing is booked, ordered or nominated.",
        "added": [{"hub": hub, "month": month, "net_mwh": energy(value)}
                  for (hub, month), value in sorted(position.items())],
        "mandates": mandates,
        "credit": credit,
        "options_allowed": False,
        "instruments": sorted({leg.instrument for leg in legs}),
    }


# ----------------------------------------------------------------------------- deadlines


def calendar_items(session, *, now: datetime, days: int = 60) -> list[dict[str, Any]]:
    """Open cases' auction closes and offer expiries for the desk's calendar and events list."""

    from eurogas_nexus.db.models import RegasAuctionCaseRecord as R

    now = _aware(now)
    end = now + timedelta(days=days)
    items = []
    for row in session.query(R).filter(R.state == "open").all():
        source = {"basis": "desk_record", "publisher": "Regas auction case", "title": row.title,
                  "url": None}
        for kind, at, title in (
            ("regas_auction_close", row.auction_closes_at_utc,
             f"Regas auction closes: {row.terminal_name}"),
            ("regas_offer_expiry", row.offer_expires_at_utc,
             f"Cargo offer lapses: {row.counterparty_name} ({row.terminal_name})"),
        ):
            at = _aware(at)
            if at is None or not now - timedelta(days=1) <= at <= end:
                continue
            items.append({"key": f"{kind}:{row.case_id}", "kind": kind, "at": _iso(at),
                          "title": title, "hubs": [row.hub], "case_id": row.case_id,
                          "source": source})
    return items


def monitoring_candidates(session, now: datetime) -> list:
    """The auction close and the offer expiry, ahead by the definition's lead times."""

    from eurogas_nexus.db.models import RegasAuctionCaseRecord as R
    from eurogas_nexus.domain.monitoring import MonitoringCandidate

    try:
        definition = load_definition()
    except Exception:  # noqa: BLE001 - a broken desk file is reported where it is edited
        return []
    now = _aware(now)
    out = []
    for row in session.query(R).filter(R.state == "open").all():
        for kind, at, leads, en, zh in (
            ("regas_auction_close", row.auction_closes_at_utc, definition.auction_leads,
             "Regas auction closes", "再气化档期竞拍截止"),
            ("regas_offer_expiry", row.offer_expires_at_utc, definition.offer_leads,
             "Cargo offer lapses", "船货报价失效"),
        ):
            at = _aware(at)
            if at is None or not now < at <= now + timedelta(minutes=leads[0]):
                continue
            minutes = int((at - now).total_seconds() // 60)
            severity = "critical" if minutes <= leads[-1] else "warning"
            out.append(MonitoringCandidate(
                fingerprint=f"{kind}:{row.case_id}",
                category="regas_auction",
                alert_type=kind,
                severity=severity,
                title_en=f"{en} in {minutes} min: {row.terminal_name}",
                title_zh_cn=f"{zh}（{minutes} 分钟后）：{row.terminal_name}",
                message_en=(f"{row.title}: {en.lower()} at {_iso(at)} ({row.counterparty_name}). "
                            "Open Desk > Cargoes > Regas auctions for the limit."),
                message_zh_cn=(f"{row.title}：{_iso(at)} {zh}（{row.counterparty_name}）。"
                               "请在交易台 > 船货 > 再气化竞拍查看出价上限。"),
                entity_type="regas_auction_case",
                entity_id=row.case_id,
                event_time_utc=at,
                evidence_snapshot={"book_ids": [row.book_id], "case_id": row.case_id,
                                   "at": _iso(at), "kind": kind},
                source_refs=[f"regas-case:{row.case_id}"],
            ))
    return out


# ----------------------------------------------------------------------------- report


_TEXT: dict[str, tuple[str, str]] = {
    "title": ("Regas auction case", "再气化档期竞拍案例"),
    "answer": ("The answer", "结论"),
    "state.room": ("Room to bid", "仍有出价空间"),
    "state.at_limit": ("At the limit", "已到上限"),
    "state.stop": ("Stop", "停止出价"),
    "state.no_level": ("No auction level entered", "未录入竞拍价位"),
    "state.illustration": ("Illustration, not a bid level", "仅作示意，非出价水平"),
    "state.missing_inputs": ("Not computed: inputs missing", "未计算：缺少输入"),
    "max_bid": ("Maximum bid", "最高出价"),
    "level": ("Auction level", "竞拍当前价位"),
    "headroom": ("Headroom", "余量"),
    "total": ("Total", "合计"),
    "waterfall": ("From hub revenue to the maximum bid", "从枢纽收入到最高出价"),
    "sensitivities": ("What moves it", "敏感性"),
    "hedges": ("Hedges if the slot is won", "中标后的对冲"),
    "costs": ("Cost lines and where each came from", "成本项及来源"),
    "snapshots": ("Snapshots saved during the window", "竞拍期间保存的快照"),
    "assumptions": ("Defaults and assumptions", "默认值与假设"),
    "inputs": ("Prices read", "读取的价格"),
    "col.item": ("Item", "项目"), "col.amount": ("Amount", "金额"),
    "col.per_mwh": ("Per MWh", "每 MWh"), "col.source": ("Source", "来源"),
    "col.value": ("Value", "数值"), "col.basis": ("Basis", "计价基础"),
    "col.hub": ("Hub", "枢纽"), "col.contract": ("Contract", "合约"),
    "col.side": ("Side", "方向"), "col.mwh": ("MWh", "MWh"), "col.cost": ("Cost", "成本"),
    "col.per": ("Per", "每变动"), "col.change": ("Change in max bid", "最高出价变化"),
    "col.saved": ("Saved", "保存时间"), "col.by": ("By", "保存人"),
    "col.state": ("State", "状态"), "col.key": ("Input", "输入"), "col.time": ("As of", "时间"),
    "col.class": ("Class", "类别"),
    "closed": ("Closed {outcome} by {who} at {when}: {note}",
               "已于 {when} 由 {who} 结案（{outcome}）：{note}"),
    "open": ("Open; auction closes {when}", "进行中；竞拍截止 {when}"),
    "hand": ("Entered by hand: {items}", "手工录入：{items}"),
    "no_orders": ("Nothing here is a bid or an order; a trader acts in the execution tool.",
                  "本文件不构成出价或指令；交易员在执行工具中操作。"),
    "missing": ("Missing: {items}", "缺失：{items}"),
}


def _t(lang: str, key: str, **params: Any) -> str:
    en, zh = _TEXT[key]
    text = zh if lang == "zh-CN" else en
    return text.format(**params) if params else text


def report(session, caller, case_id: str, *, lang: str, now: datetime | None = None,
           reader=None) -> tuple[bytes, bytes, str]:
    """The case on one page as (PDF, XLSX, base file name), English or Chinese."""

    from eurogas_nexus.core.report_files import pdf_document, xlsx_workbook

    now = _aware(now) or datetime.now(UTC)
    lang = "zh-CN" if str(lang).lower().startswith("zh") else "en"
    row = _get(session, case_id)
    data, _ = answer(session, caller, row.inputs, book_id=row.book_id, now=now, reader=reader,
                     closes_at=row.auction_closes_at_utc)
    saved = snapshots(session, case_id)
    cur = data["currency"]
    quoted_unit = f"{cur}/MWh" if data["quotation"] == "per_mwh" else cur

    def d(value: Any) -> Decimal | None:
        return None if value in (None, "") else Decimal(str(value))

    state = _t(lang, f"state.{data['state']}")
    lines = [state]
    if data.get("computed"):
        lines.append(f"{_t(lang, 'max_bid')}: {data['max_bid_quoted']} {quoted_unit} "
                     f"({_t(lang, 'total')} {data['max_bid_total']} {cur})")
        if data.get("level") is not None:
            lines.append(f"{_t(lang, 'level')}: {data['level']} {quoted_unit}; "
                         f"{_t(lang, 'headroom')}: {data['headroom']} {quoted_unit}")
    else:
        lines.append(_t(lang, "missing", items=", ".join(data.get("missing", []))))
    if data.get("hand_entered"):
        lines.append(_t(lang, "hand", items=", ".join(data["hand_entered"])))
    if data.get("simulated"):
        lines.append(_t(lang, "state.illustration"))
    lines.append(_t(lang, "no_orders"))
    sections: list[dict[str, Any]] = [{"key": "answer", "heading": _t(lang, "answer"),
                                       "lines": lines}]
    if data.get("computed"):
        sections.append({
            "key": "waterfall", "heading": _t(lang, "waterfall"), "lines": [],
            "columns": [_t(lang, "col.item"), _t(lang, "col.amount"), _t(lang, "col.per_mwh")],
            "rows": [[item["label"], d(item["total"]), d(item["per_mwh"])]
                     for item in data["waterfall"]],
            "numeric": [False, True, True],
        })
        sections.append({
            "key": "sensitivities", "heading": _t(lang, "sensitivities"), "lines": [],
            "columns": [_t(lang, "col.item"), _t(lang, "col.per"), _t(lang, "col.change")],
            "rows": [[item["label"], item["per"], d(item["max_bid_quoted"])]
                     for item in data["sensitivities"]],
            "numeric": [False, False, True],
        })
        sections.append({
            "key": "hedges", "heading": _t(lang, "hedges"), "lines": [HEDGE_ORDERS_NOTE],
            "columns": [_t(lang, "col.hub"), _t(lang, "col.contract"), _t(lang, "col.side"),
                        _t(lang, "col.mwh"), _t(lang, "col.cost")],
            "rows": [[leg["hub"], leg["contract"], leg["side"], d(leg["mwh"]), d(leg["cost"])]
                     for leg in data["hedges"]],
            "numeric": [False, False, False, True, True],
        })
    sections.append({
        "key": "costs", "heading": _t(lang, "costs"), "lines": [],
        "columns": [_t(lang, "col.item"), _t(lang, "col.basis"), _t(lang, "col.value"),
                    _t(lang, "col.amount"), _t(lang, "col.source")],
        "rows": [[line["label"], line["basis"], d(line["value"]), d(line["total"]),
                  line["source"]] for line in data["cost_lines"]],
        "numeric": [False, False, True, True, False],
    })
    sections.append({
        "key": "snapshots", "heading": _t(lang, "snapshots"), "lines": [],
        "columns": [_t(lang, "col.saved"), _t(lang, "col.by"), _t(lang, "col.state"),
                    _t(lang, "max_bid"), _t(lang, "level"), _t(lang, "headroom")],
        "rows": [[snap["saved_at_utc"][:16], snap["saved_by"], snap["state"],
                  d(snap["max_bid_quoted"]), d(snap["level"]), d(snap["headroom"])]
                 for snap in saved],
        "numeric": [False, False, False, True, True, True],
    })
    sections.append({
        "key": "inputs", "heading": _t(lang, "inputs"), "lines": [],
        "columns": [_t(lang, "col.key"), _t(lang, "col.value"), _t(lang, "col.class"),
                    _t(lang, "col.time"), _t(lang, "col.source")],
        "rows": [[read["key"], d(read["value"]), read["class"], read["as_of_utc"] or "",
                  read["source"]] for read in data["reads"]
                 if read["key"].split(":")[0] != "price"
                 or read["key"].split(":")[2] <= data["slot"]["last_day"]],
        "numeric": [False, True, False, False, False],
    })
    sections.append({"key": "assumptions", "heading": _t(lang, "assumptions"),
                     "lines": [item["text"] for item in data["assumptions"]]})
    if row.state == "open":
        status = _t(lang, "open", when=_iso(row.auction_closes_at_utc))
    else:
        status = _t(lang, "closed", outcome=row.state, who=row.closed_by,
                    when=_iso(row.closed_at_utc)[:16], note=row.close_note or "")
    title = f"{_t(lang, 'title')}: {row.title}"
    subtitle = (f"{row.terminal_name} ({row.hub}) · {row.counterparty_name} · {status} · "
                f"{now:%Y-%m-%d %H:%M} UTC")
    banner = _t(lang, "state.illustration") if data.get("simulated") else ""
    pdf = pdf_document(title=title, subtitle=subtitle, sections=sections, footer=status,
                       banner=banner, cjk=lang == "zh-CN")
    sheets = []
    for section in sections:
        rows = [list(r) for r in section.get("rows") or []]
        notes = [[line] for line in section.get("lines") or []]
        if notes and not rows:
            sheets.append((section["heading"], [section["heading"]], notes))
        else:
            sheets.append((section["heading"], list(section.get("columns") or []),
                           rows + ([[]] + notes if notes else [])))
    about = [("Case", title), ("Status", status), ("Book", row.book_id),
             ("Generated", f"{now:%Y-%m-%d %H:%M} UTC"), ("Generated by", actor_of(caller))]
    xlsx = xlsx_workbook(sheets, about=about, caveat=banner or None)
    name = f"regas-auction-{row.case_id}-{'zh' if lang == 'zh-CN' else 'en'}"
    return pdf, xlsx, name


__all__ = [
    "CASE_STATES",
    "HEDGE_ORDERS_NOTE",
    "ILLUSTRATION",
    "OUTCOMES",
    "Definition",
    "RegasAuctionCaseError",
    "RegasAuctionError",
    "answer",
    "calendar_items",
    "case_answer",
    "choices",
    "close_case",
    "create_case",
    "list_cases",
    "load_definition",
    "monitoring_candidates",
    "normalise",
    "parse_definition",
    "position_seam",
    "report",
    "save_snapshot",
    "snapshots",
    "unit",
    "money",
    "update_case",
    "what_if",
]

