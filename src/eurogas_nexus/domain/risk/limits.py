"""Counterparty credit exposure against approved lines, and trader mandate usage.

Credit (per counterparty, in the line's currency)
    * **Replacement exposure**: what the firm would lose replacing the undelivered volume if
      the counterparty defaulted today. Per leg ``remaining MWh x (mark - price)`` for gas
      bought from them and ``(price - mark)`` for gas sold to them; legs are netted across the
      counterparty, as an EFET master agreement with close-out netting allows, and floored at
      zero. An open-ended (evergreen) contract counts only to the end of the current gas year:
      it renews annually and either side can end it on notice, so later years are not volume
      the firm is owed. The row reports how many legs were cut this way.
    * **Receivable exposure**: gas already delivered to them and not yet paid for, taken as
      the last ``receivable_days`` gas days of sales at the contract price (the delivery
      month plus the payment term; 50 days fits monthly invoicing paid on the 20th).
      Payables are not netted against it.
    * **Net exposure** = replacement + receivable - collateral held (letters of credit,
      parent guarantees, cash), floored at zero; utilisation is net exposure over the limit.

    Exchange-cleared screen trades carry clearing-house risk, not bilateral credit, and are
    not part of any line. A leg without a mark or a price, or in a currency with no ECB rate
    to the line's currency, is left out of the figure and counted as unvalued, so a line
    never looks safer because a number is missing without saying so.

Mandates (per trader)
    The trader's legs are the legs in the mandate's books plus the screen trades on the
    trader's own account. A mandate is breached by a hub outside its list, a product kind it
    does not allow, a delivery beyond its tenor, or a net hub-month position beyond its size.

    Hedge policy (per hub-month with a physical position): financial cover as a share of the
    physical position must stay within ``min_hedge_ratio_pct``..``max_hedge_ratio_pct``. A
    legal cap such as "hedge at most 80 %" stops a hedge turning into a speculative short;
    a floor makes the desk lock in a minimum. The headroom to the cap is reported so the
    trader knows how much more can be hedged. Instruments outside the allowed list (for
    example options where the firm's policy forbids them) are breaches.

Statuses: ``ok`` under 75 % used, ``watch`` 75-100 %, ``breach`` above 100 % or on any rule
breach, ``expired`` once the approval's ``valid_until`` has passed.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta

from eurogas_nexus.domain.ontology.notes import Note, declare, note

# Breaches as declared notes (domain/ontology/notes.py); the English text is unchanged, so the
# alerts and briefs that read ``breaches`` (application/desk_text.py) keep working.
MANDATE_HUB_OUTSIDE = declare("MANDATE_HUB_OUTSIDE", "{hub} is outside the mandate ({ref})")
MANDATE_PHYSICAL_NOT_ALLOWED = declare(
    "MANDATE_PHYSICAL_NOT_ALLOWED", "physical supply is not allowed ({ref})"
)
MANDATE_FINANCIAL_NOT_ALLOWED = declare(
    "MANDATE_FINANCIAL_NOT_ALLOWED", "financial trades are not allowed ({ref})"
)
MANDATE_INSTRUMENT_NOT_ALLOWED = declare(
    "MANDATE_INSTRUMENT_NOT_ALLOWED", "{instrument} is not an allowed instrument ({ref})"
)
MANDATE_BEYOND_TENOR = declare(
    "MANDATE_BEYOND_TENOR", "delivery to {month} is beyond {months} months ({ref})"
)
MANDATE_NET_OVER = declare("MANDATE_NET_OVER", "net {net} MWh in {at} is over {limit} MWh")
MANDATE_HEDGED_ABOVE = declare("MANDATE_HEDGED_ABOVE", "{at} hedged {pct}%, above {limit}%")
MANDATE_HEDGED_BELOW = declare("MANDATE_HEDGED_BELOW", "{at} hedged {pct}%, below {limit}%")
APPROVAL_HEDGED_OVER = declare(
    "APPROVAL_HEDGED_OVER", "{at} hedged {pct}%, over the approved {limit}%"
)
APPROVAL_HEDGED_UNDER = declare(
    "APPROVAL_HEDGED_UNDER", "{at} hedged {pct}%, under the approved {limit}%"
)
APPROVAL_INDEXED_HEDGE_OPEN = declare(
    "APPROVAL_INDEXED_HEDGE_OPEN",
    "{at}: the contract is index-priced, so it has no flat-price exposure to hedge; "
    "{mwh} MWh of linked trades is an open position",
)

WATCH_AT = 0.75


@dataclass(frozen=True)
class CounterpartyLeg:
    """One contract or OTC trade facing a counterparty; MWh per gas day, bought positive."""

    reference: str
    kind: str  # "supply_contract" or "otc_trade"
    hub: str
    currency: str
    first_gas_day: date
    last_gas_day: date
    mwh_per_day: float
    price: float | None
    open_ended: bool = False  # evergreen: committed only to the end of the current gas year


def gas_year_end(day: date) -> date:
    """Last gas day (30 September) of the gas year containing ``day``."""

    return date(day.year if day.month < 10 else day.year + 1, 9, 30)


@dataclass(frozen=True)
class CreditLine:
    counterparty_id: str
    name: str
    limit_amount: float
    currency: str
    collateral_amount: float = 0.0
    receivable_days: int = 50
    valid_until: date | None = None
    legal_entity: str | None = None
    rating: str | None = None


@dataclass
class CreditExposure:
    counterparty_id: str
    name: str
    currency: str
    limit_amount: float
    replacement_exposure: float = 0.0
    receivable_exposure: float = 0.0
    collateral_amount: float = 0.0
    legs: int = 0
    unvalued_legs: int = 0
    remaining_mwh: float = 0.0
    open_ended_legs: int = 0
    legal_entity: str | None = None
    rating: str | None = None
    valid_until: date | None = None
    status: str = "ok"

    @property
    def gross_exposure(self) -> float:
        return self.replacement_exposure + self.receivable_exposure

    @property
    def net_exposure(self) -> float:
        return max(0.0, self.gross_exposure - self.collateral_amount)

    @property
    def utilisation(self) -> float | None:
        return None if self.limit_amount <= 0 else self.net_exposure / self.limit_amount

    def as_row(self) -> dict[str, object]:
        used = self.utilisation
        return {
            "counterparty_id": self.counterparty_id,
            "counterparty": self.name,
            "legal_entity": self.legal_entity,
            "rating": self.rating,
            "currency": self.currency,
            "limit": round(self.limit_amount, 2),
            "replacement_exposure": round(self.replacement_exposure, 2),
            "receivable_exposure": round(self.receivable_exposure, 2),
            "collateral": round(self.collateral_amount, 2),
            "net_exposure": round(self.net_exposure, 2),
            "headroom": round(self.limit_amount - self.net_exposure, 2),
            "utilisation_pct": None if used is None else round(100 * used, 1),
            "remaining_mwh": round(self.remaining_mwh, 1),
            "legs": self.legs,
            "unvalued_legs": self.unvalued_legs,
            "open_ended_legs": self.open_ended_legs,
            "valid_until": self.valid_until.isoformat() if self.valid_until else None,
            "status": self.status,
        }


def _status(utilisation: float | None, *, expired: bool, breached: bool = False) -> str:
    if expired:
        return "expired"
    if breached or (utilisation is not None and utilisation > 1.0 + 1e-9):
        return "breach"
    if utilisation is not None and utilisation >= WATCH_AT:
        return "watch"
    return "ok"


def _month(day: date) -> str:
    return f"{day.year:04d}-{day.month:02d}"


def _days_by_month(first: date, last: date) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    day = first
    while day <= last:
        month_end = (day.replace(day=1) + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        chunk_end = min(month_end, last)
        counts[_month(day)] += (chunk_end - day).days + 1
        day = chunk_end + timedelta(days=1)
    return counts


def credit_exposure(
    line: CreditLine,
    legs: Iterable[CounterpartyLeg],
    *,
    today: date,
    mark: Callable[[str, str], float | None],
    fx: Callable[[str, str], float | None],
) -> CreditExposure:
    """Exposure to one counterparty. ``mark(hub, month)``; ``fx(from, to)`` multiplier."""

    result = CreditExposure(
        counterparty_id=line.counterparty_id,
        name=line.name,
        currency=line.currency,
        limit_amount=line.limit_amount,
        collateral_amount=line.collateral_amount,
        legal_entity=line.legal_entity,
        rating=line.rating,
        valid_until=line.valid_until,
    )
    net_replacement = 0.0
    receivable_from = today - timedelta(days=max(0, line.receivable_days))
    for leg in legs:
        result.legs += 1
        rate = fx(leg.currency, line.currency)
        if leg.price is None or rate is None:
            result.unvalued_legs += 1
            continue
        valued = True
        replacement = 0.0
        start = max(leg.first_gas_day, today)
        committed_last = leg.last_gas_day
        if leg.open_ended:
            result.open_ended_legs += 1
            committed_last = min(committed_last, gas_year_end(today))
        if start <= committed_last:
            for month, days in _days_by_month(start, committed_last).items():
                price = mark(leg.hub, month)
                if price is None:
                    valued = False
                    break
                volume = leg.mwh_per_day * days
                result.remaining_mwh += abs(volume)
                replacement += volume * (price - leg.price)
        receivable = 0.0
        if leg.mwh_per_day < 0:  # sold to the counterparty: delivered, unpaid gas
            first = max(leg.first_gas_day, receivable_from)
            last = min(leg.last_gas_day, today - timedelta(days=1))
            if first <= last:
                receivable = -leg.mwh_per_day * ((last - first).days + 1) * leg.price
        if not valued:
            result.unvalued_legs += 1
            continue
        net_replacement += replacement * rate
        result.receivable_exposure += receivable * rate
    result.replacement_exposure = max(0.0, net_replacement)
    expired = line.valid_until is not None and line.valid_until < today
    result.status = _status(result.utilisation, expired=expired)
    if result.status == "ok" and result.unvalued_legs:
        result.status = "incomplete"
    return result


def _pct_range(low: float, high: float) -> str:
    """ "12% to 87%" (an en dash after a negative number reads as a double minus)."""

    low_pct, high_pct = round(low) + 0, round(high) + 0  # + 0 turns -0 into 0
    return f"{low_pct}%" if low_pct == high_pct else f"{low_pct}% to {high_pct}%"


@dataclass(frozen=True)
class MandateLeg:
    reference: str
    kind: str  # "physical" or "financial"
    hub: str
    book_id: str
    account: str
    first_gas_day: date
    last_gas_day: date
    mwh_per_day: float
    instrument: str = ""  # physical, future, forward, swap, option
    #: The leg as a person names it; a breach names it by this, never by ``reference`` alone.
    label: str = ""
    #: For a contract priced at a European hub index: the index's hub, which carries the
    #: leg's flat-price exposure (``position_ladder.PositionLeg.index_hub``).
    index_hub: str | None = None


@dataclass(frozen=True)
class Mandate:
    mandate_id: str
    trader: str
    display_name: str
    book_ids: Sequence[str] = ()
    hubs: Sequence[str] = ()
    max_net_mwh_per_month: float | None = None
    max_tenor_months: int | None = None
    physical_allowed: bool = True
    financial_allowed: bool = True
    valid_until: date | None = None
    min_hedge_ratio_pct: float | None = None
    max_hedge_ratio_pct: float | None = None
    instruments: Sequence[str] = ()


@dataclass
class MandateUsage:
    mandate: Mandate
    legs: int = 0
    largest_net_mwh: float = 0.0
    largest_at: str = ""
    furthest_month: str = ""
    breaches: list[str] = field(default_factory=list)
    #: The same breaches as declared notes (code, params with the leg's name, text).
    breach_notes: list[Note] = field(default_factory=list)
    status: str = "ok"
    lowest_hedge_pct: float | None = None
    highest_hedge_pct: float | None = None
    hedge_room_mwh: float | None = None

    @property
    def utilisation(self) -> float | None:
        limit = self.mandate.max_net_mwh_per_month
        return None if not limit else abs(self.largest_net_mwh) / limit

    def as_row(self) -> dict[str, object]:
        used = self.utilisation
        return {
            "mandate_id": self.mandate.mandate_id,
            "trader": self.mandate.trader,
            "name": self.mandate.display_name,
            "books": ", ".join(self.mandate.book_ids) or "own account",
            "hubs": ", ".join(self.mandate.hubs) or "any",
            "max_net_mwh_per_month": self.mandate.max_net_mwh_per_month,
            "largest_net_mwh": round(self.largest_net_mwh, 1),
            "largest_at": self.largest_at,
            "utilisation_pct": None if used is None else round(100 * used, 1),
            "max_tenor_months": self.mandate.max_tenor_months,
            "furthest_month": self.furthest_month,
            "legs": self.legs,
            "hedge_policy": _policy_text(self.mandate),
            "hedge_ratio_range": None
            if self.lowest_hedge_pct is None
            else _pct_range(self.lowest_hedge_pct, self.highest_hedge_pct),
            "hedge_room_mwh": None
            if self.hedge_room_mwh is None
            else round(self.hedge_room_mwh, 0),
            "instruments": ", ".join(self.mandate.instruments) or "any",
            "breaches": "; ".join(self.breaches),
            "breach_notes": [item.as_dict() for item in self.breach_notes],
            "valid_until": self.mandate.valid_until.isoformat()
            if self.mandate.valid_until
            else None,
            "status": self.status,
        }


def _policy_text(mandate: Mandate) -> str:
    low, high = mandate.min_hedge_ratio_pct, mandate.max_hedge_ratio_pct
    if low is None and high is None:
        return ""
    if low is None:
        return f"at most {high:.0f}%"
    if high is None:
        return f"at least {low:.0f}%"
    return f"{low:.0f}-{high:.0f}%"


def _add_months(day: date, months: int) -> date:
    index = day.year * 12 + day.month - 1 + months
    return date(index // 12, index % 12 + 1, 1)


def mandate_usage(
    mandate: Mandate,
    legs: Iterable[MandateLeg],
    *,
    today: date,
    books_elsewhere: frozenset[str] = frozenset(),
) -> MandateUsage:
    """How much of one mandate the trader's open legs use, and any rule they break.

    A leg belongs to the mandate when it sits in one of the mandate's books, or when the
    trader dealt it on their own account in a book none of their *other* mandates cover
    (``books_elsewhere``): a trader with an NBP mandate and a TTF mandate is not told their
    NBP-book trade breaches the TTF one, while a trade booked outside all their books is
    still caught.
    """

    usage = MandateUsage(mandate=mandate)
    books = set(mandate.book_ids)
    hubs = {hub.upper() for hub in mandate.hubs}
    net: dict[tuple[str, str], float] = defaultdict(float)
    physical: dict[tuple[str, str], float] = defaultdict(float)
    financial: dict[tuple[str, str], float] = defaultdict(float)
    allowed_instruments = {item.casefold() for item in mandate.instruments}
    tenor_end = (
        _add_months(today, mandate.max_tenor_months + 1) - timedelta(days=1)
        if mandate.max_tenor_months is not None
        else None
    )
    seen_rules: set[str] = set()

    def breach(rule: str, item: Note) -> None:
        if rule not in seen_rules:
            seen_rules.add(rule)
            usage.breaches.append(item.text)
            usage.breach_notes.append(item)

    def ref(leg: MandateLeg) -> dict[str, str]:
        # The record a breach is about, by id and by the name a person knows.
        return {"ref": leg.reference, "ref_name": leg.label or leg.reference}

    for leg in legs:
        mine = (leg.book_id and leg.book_id in books) or (
            leg.kind == "financial"
            and leg.account
            and leg.account == mandate.trader
            and leg.book_id not in books_elsewhere
        )
        if not mine or leg.last_gas_day < today:
            continue
        usage.legs += 1
        hub = leg.hub.upper()
        if hubs and hub not in hubs:
            breach(f"hub:{hub}", note(MANDATE_HUB_OUTSIDE, hub=hub, **ref(leg)))
        if leg.kind == "physical" and not mandate.physical_allowed:
            breach("physical", note(MANDATE_PHYSICAL_NOT_ALLOWED, **ref(leg)))
        if leg.kind == "financial" and not mandate.financial_allowed:
            breach("financial", note(MANDATE_FINANCIAL_NOT_ALLOWED, **ref(leg)))
        if allowed_instruments and leg.instrument and leg.instrument not in allowed_instruments:
            breach(
                f"instrument:{leg.instrument}",
                note(MANDATE_INSTRUMENT_NOT_ALLOWED, instrument=leg.instrument, **ref(leg)),
            )
        if tenor_end is not None and leg.last_gas_day > tenor_end:
            breach(
                "tenor",
                note(
                    MANDATE_BEYOND_TENOR,
                    month=_month(leg.last_gas_day),
                    months=mandate.max_tenor_months,
                    **ref(leg),
                ),
            )
        months = _days_by_month(max(leg.first_gas_day, today), leg.last_gas_day)
        # Net size and hedge cover are measured in flat-price exposure: an index-priced
        # contract's exposure is on its index, equal and opposite to its volume.
        index = leg.index_hub.upper() if leg.index_hub else None
        for month, days in months.items():
            mwh = leg.mwh_per_day * days
            net[(hub, month)] += mwh
            side = physical if leg.kind == "physical" else financial
            side[(hub, month)] += mwh
            if index:
                net[(index, month)] -= mwh
                side[(index, month)] -= mwh
            usage.furthest_month = max(usage.furthest_month, month)
    if net:
        (hub, month), value = max(net.items(), key=lambda item: abs(item[1]))
        usage.largest_net_mwh, usage.largest_at = value, f"{hub} {month}"
    limit = mandate.max_net_mwh_per_month
    if limit and abs(usage.largest_net_mwh) > limit:
        breach(
            "size",
            note(
                MANDATE_NET_OVER,
                net=f"{usage.largest_net_mwh:,.0f}",
                at=usage.largest_at,
                limit=f"{limit:,.0f}",
            ),
        )
    _check_hedge_policy(mandate, usage, physical, financial, breach)
    expired = mandate.valid_until is not None and mandate.valid_until < today
    usage.status = _status(usage.utilisation, expired=expired, breached=bool(usage.breaches))
    return usage


def _whole(pct: float) -> int:
    """A percentage to the whole number, never "-0" for a zero (or near-zero) hedge."""

    return round(pct) + 0


def _check_hedge_policy(mandate, usage, physical, financial, breach) -> None:
    """Hedge ratio per hub-month against the policy band, and the room left to the cap."""

    low, high = mandate.min_hedge_ratio_pct, mandate.max_hedge_ratio_pct
    ratios = []
    room = 0.0
    for key, position in physical.items():
        if abs(position) < 1e-6:
            continue
        cover = -financial.get(key, 0.0)  # a sale hedges a long, a purchase hedges a short
        ratio = 100 * cover / position
        ratios.append(ratio)
        hub_month = f"{key[0]} {key[1]}"
        if high is not None:
            room += max(0.0, abs(position) * high / 100 - abs(cover) * (1 if ratio >= 0 else -1))
            if ratio > high + 1e-9:
                breach(
                    f"over-hedged:{hub_month}",
                    note(
                        MANDATE_HEDGED_ABOVE, at=hub_month, pct=_whole(ratio), limit=f"{high:.0f}"
                    ),
                )
        if low is not None and ratio < low - 1e-9:
            breach(
                f"under-hedged:{hub_month}",
                note(MANDATE_HEDGED_BELOW, at=hub_month, pct=_whole(ratio), limit=f"{low:.0f}"),
            )
    if ratios:
        usage.lowest_hedge_pct, usage.highest_hedge_pct = min(ratios), max(ratios)
    if high is not None and ratios:
        usage.hedge_room_mwh = room


def fx_lookup(eur_rates: Mapping[str, float]) -> Callable[[str, str], float | None]:
    """``fx(from, to)`` from ECB rates quoted as units of currency per EUR."""

    def fx(source: str, target: str) -> float | None:
        if source == target:
            return 1.0
        a, b = eur_rates.get(source), eur_rates.get(target)
        if not a or not b:
            return None
        return b / a

    return fx


@dataclass(frozen=True)
class HedgeApproval:
    """Risk's approved hedge band for one contract, in percent of its monthly volume."""

    contract_id: str
    min_hedge_ratio_pct: float | None = None
    max_hedge_ratio_pct: float | None = None
    approval_ref: str | None = None
    valid_until: date | None = None


@dataclass(frozen=True)
class VolumeLeg:
    """A flat daily volume over a gas-day window (long positive, short negative)."""

    reference: str
    first_gas_day: date
    last_gas_day: date
    mwh_per_day: float
    #: Priced at a hub index: the volume has no flat-price exposure to hedge.
    floating: bool = False


def _monthly(legs: Iterable[VolumeLeg], today: date) -> dict[str, float]:
    volumes: dict[str, float] = defaultdict(float)
    for leg in legs:
        start = max(leg.first_gas_day, today)
        if start > leg.last_gas_day:
            continue
        for month, days in _days_by_month(start, leg.last_gas_day).items():
            volumes[month] += leg.mwh_per_day * days
    return volumes


def deal_hedge_usage(
    approval: HedgeApproval,
    physical: Iterable[VolumeLeg],
    hedges: Iterable[VolumeLeg],
    *,
    today: date,
) -> dict:
    """How far each remaining month of a contract is hedged against its approved band.

    The hedge ratio of a month is the linked trades' volume offsetting the contract's
    flat-price exposure, as a share of it: selling forward 80 % of a long fixed-price supply
    contract is 80 %. A trade pointing the same way adds to the position and counts as
    negative cover. An index-priced contract (``VolumeLeg.floating``) has no flat-price
    exposure: its months show the volume with ``price_exposure_mwh`` 0 and no ratio, and any
    linked trade is an open position, said as a breach.
    """

    physical = list(physical)
    supply = _monthly(physical, today)
    exposed = _monthly([leg for leg in physical if not leg.floating], today)
    cover = _monthly(hedges, today)
    months = []
    breach_notes: list[Note] = []
    low, high = approval.min_hedge_ratio_pct, approval.max_hedge_ratio_pct
    for month in sorted(supply):
        volume = supply[month]
        if abs(volume) < 1e-9:
            continue
        exposure = exposed.get(month, 0.0)
        if abs(exposure) < 1e-9:
            held = -cover.get(month, 0.0)
            months.append(
                {
                    "month": month,
                    "contract_mwh": round(volume, 1),
                    "price_exposure_mwh": 0.0,
                    "hedged_mwh": round(held, 1),
                    "hedge_pct": None,
                    "room_mwh": None,
                }
            )
            if abs(held) > 1e-6:
                breach_notes.append(
                    note(APPROVAL_INDEXED_HEDGE_OPEN, at=month, mwh=f"{abs(held):,.0f}")
                )
            continue
        pct = 100.0 * -cover.get(month, 0.0) / exposure
        room = (
            None if high is None else high / 100.0 * abs(exposure) - abs(cover.get(month, 0.0))
        )
        months.append(
            {
                "month": month,
                "contract_mwh": round(volume, 1),
                "price_exposure_mwh": round(exposure, 1),
                "hedged_mwh": round(-cover.get(month, 0.0), 1),
                "hedge_pct": round(pct, 1) + 0.0,  # + 0.0 turns -0.0 into 0.0
                "room_mwh": None if room is None else round(room, 1),
            }
        )
        if high is not None and pct > high + 1e-6:
            breach_notes.append(
                note(APPROVAL_HEDGED_OVER, at=month, pct=_whole(pct), limit=f"{high:.0f}")
            )
        if low is not None and pct < low - 1e-6:
            breach_notes.append(
                note(APPROVAL_HEDGED_UNDER, at=month, pct=_whole(pct), limit=f"{low:.0f}")
            )
    breaches = [item.text for item in breach_notes]
    expired = approval.valid_until is not None and approval.valid_until < today
    pcts = [row["hedge_pct"] for row in months if row["hedge_pct"] is not None]
    return {
        "contract_id": approval.contract_id,
        "min_hedge_ratio_pct": low,
        "max_hedge_ratio_pct": high,
        "approval_ref": approval.approval_ref,
        "valid_until": approval.valid_until.isoformat() if approval.valid_until else None,
        "hedge_range": _pct_range(min(pcts), max(pcts)) if pcts else None,
        "months": months,
        "breaches": breaches,
        "breach_notes": [item.as_dict() for item in breach_notes],
        "status": "expired" if expired else "breach" if breaches else "ok",
    }
