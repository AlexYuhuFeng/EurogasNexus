"""Captured deals in the one position source: what counts, once, and how.

``position_inputs.ladder_inputs`` builds the legs every position and P&L screen reads (the
position ladder, Today, limits and credit exposure, the alerts the monitoring worker raises,
the opportunity stream, the reports, the daily pack). It calls :func:`captured_book` on every
read, so a deal captured a second ago is in all of them, and no two of them can disagree.

**The same deal counted once.** The ETRM's trades are loaded into the book as screen-order
observations (provider ``ETRM``) whenever the desk loads its extract, before or after the day's
close. At read time the captured deals and those ETRM trades are paired by the end-of-day
check's own rule (``domain/deals/eod.pair_deals``): a pair recorded at a close, else the
exchange reference, else the terms. For each pair exactly one side counts:

- the captured deal, while its trade day is not closed for its book (the desk's latest word:
  a correction or a cancellation entered since the ETRM was loaded shows at once);
- the ETRM trade, once the day is closed (the official record), with the captured deal's
  physical or financial classification.

Because the rule is applied when the position is read, from what is stored at that moment,
the order in which deals are captured, the extract is loaded and the day is closed does not
matter.

**Physical or financial** comes from ``domain/deals/position.classify`` (a choice by hand,
the deal's own flag, the rule file). **Estimate**: while a counted captured deal's day is not
closed, every figure built from it is the desk's estimate (:data:`ESTIMATE_LABEL`).

捕获交易并入唯一头寸来源：同一笔交易只计一次（日结前计捕获记录，日结后计 ETRM），
实物/金融按规则文件。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

ESTIMATE_LABEL = "desk estimate, before ETRM close"
#: The provider id captured deals carry as screen-order-shaped observations.
CAPTURE_PROVIDER = "DEAL_CAPTURE"


@dataclass
class CapturedBook:
    """What the captured deals add to one position read, and what they take away."""

    #: Captured deals that count, shaped as screen orders (provider ``DEAL_CAPTURE``).
    orders: list = field(default_factory=list)
    #: Order id -> book, for the captured orders.
    books: dict[str, str] = field(default_factory=dict)
    #: Order id -> counterparty, for captured bilateral deals (credit exposure faces it).
    counterparties: dict[str, str] = field(default_factory=dict)
    #: Order id -> ``physical`` or ``financial``: captured orders, and ETRM trades that count
    #: for a captured deal after the close (the captured deal's classification).
    kinds: dict[str, str] = field(default_factory=dict)
    #: ETRM order ids that do not count: their captured twin counts (its day is open).
    suppressed: set[str] = field(default_factory=set)
    #: Every current captured deal with how it counts (``deal_view``).
    deals: list[dict[str, Any]] = field(default_factory=list)
    #: The counted captured deal records with their classification (exact position).
    counted: list[tuple[Any, Any]] = field(default_factory=list)
    #: Whether any counted captured deal is on a day not yet closed.
    estimate: bool = False
    warnings: list[str] = field(default_factory=list)

    @property
    def label(self) -> str | None:
        return ESTIMATE_LABEL if self.estimate else None

    def order_id(self, deal_key: str) -> str:
        return f"capture-{deal_key}"[:128]


def _gas_days(order) -> tuple[date, date]:
    from eurogas_nexus.domain.market.gas_day import gas_day_label

    start_at, end_at = (
        value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
        for value in (order.delivery_start_utc, order.delivery_end_utc)
    )
    first = date.fromisoformat(gas_day_label(start_at))
    days = max(1, round((end_at - start_at).total_seconds() / 86_400))
    return first, first + timedelta(days=days - 1)


def etrm_sides(orders, order_books: dict[str, str]) -> tuple[list, dict[str, str]]:
    """The ETRM trades in the book as the pairing rule reads them, and trade id -> order id."""

    from eurogas_nexus.domain.deals.eod import EtrmSide

    sides, ids = [], {}
    for order in orders:
        if str(order.provider_id).upper() != "ETRM":
            continue
        first, last = _gas_days(order)
        sides.append(EtrmSide(
            trade_id=str(order.external_order_id),
            reference=str(getattr(order, "exchange_reference", None) or ""),
            hub=str(order.hub).upper(),
            side="buy" if str(order.side).lower() in {"buy", "bid", "b"} else "sell",
            first_day=first,
            last_day=last,
            total_mwh=Decimal(repr(float(order.filled_quantity_mwh or 0.0))),
            price_per_mwh=Decimal(repr(float(order.price))),
            counterparty=str(order.account_label or ""),
            book_id=order_books.get(order.order_observation_id),
            line=0,
        ))
        ids[str(order.external_order_id)] = order.order_observation_id
    return sides, ids


def _closes(session) -> tuple[set[tuple[date, str]], dict[str, str]]:
    """Closed (day, book) pairs and the pairs each current close recorded (deal -> trade id)."""

    from eurogas_nexus.db.models import DealDayCloseRecord

    closed: set[tuple[date, str]] = set()
    pairs: dict[str, str] = {}
    for row in (
        session.query(DealDayCloseRecord)
        .filter(DealDayCloseRecord.superseded_at_utc.is_(None))
        .order_by(DealDayCloseRecord.business_date, DealDayCloseRecord.closed_at_utc)
        .all()
    ):
        closed.add((row.business_date, row.book_id or ""))
        pairs.update({str(k): str(v) for k, v in ((row.figures or {}).get("pairs") or {}).items()})
    return closed, pairs


def overrides(session, keys: list[str] | None = None) -> dict[str, Any]:
    """The current physical-or-financial choice made by hand, per deal key."""

    from eurogas_nexus.db.models import DealPositionKindRecord

    query = session.query(DealPositionKindRecord).filter(
        DealPositionKindRecord.superseded_at_utc.is_(None))
    if keys is not None:
        if not keys:
            return {}
        query = query.filter(DealPositionKindRecord.deal_key.in_(keys))
    return {row.deal_key: row for row in query.all()}


def kind_rules():
    """The rule file, or the stated default with a warning when the file cannot be read."""

    from eurogas_nexus.domain.deals.formats import FormatError
    from eurogas_nexus.domain.deals.position import KindRules, load_position_kinds

    try:
        return load_position_kinds(), None
    except (OSError, FormatError) as exc:
        return (KindRules(default="financial", prompt_gas_days=3, rules=(), source_path=""),
                f"position kinds file not usable ({exc}); every captured deal counts as financial")


def as_order(record):
    """A captured deal shaped as a screen order (so every reader of orders reads it)."""

    from eurogas_nexus.application.deal_capture import price_per_mwh, source_text
    from eurogas_nexus.domain.market.gas_day import gas_day_start_for_date
    from eurogas_nexus.domain.market_positioning import ScreenOrderObservation
    from eurogas_nexus.domain.ontology.boundary import check_boundary

    market = check_boundary(market=record.hub, gas_hub_required=True).market
    calendar = market.calendar if market else "EU-CAM-UTC-2025"
    start = gas_day_start_for_date(record.delivery_start, calendar)
    end = gas_day_start_for_date(record.delivery_end + timedelta(days=1), calendar)
    observed = record.trade_time_utc or record.recorded_at_utc
    return ScreenOrderObservation(
        order_observation_id=f"capture-{record.deal_key}"[:128], provider_id=CAPTURE_PROVIDER,
        venue=record.venue, account_label=record.trader,
        external_order_id=record.venue_trade_id,
        side="BUY" if record.side == "buy" else "SELL", order_type=record.instrument,
        hub=record.hub, product=record.product, contract_code=record.deal_key[:128],
        delivery_start_utc=start.isoformat(), delivery_end_utc=end.isoformat(),
        price=float(price_per_mwh(record)), currency=record.price_currency,
        unit=f"{record.price_currency}/MWh", quantity_mwh=float(record.total_mwh),
        filled_quantity_mwh=float(record.total_mwh), remaining_quantity_mwh=0.0,
        status="FILLED", observed_at_utc=observed.isoformat(),
        source_system=CAPTURE_PROVIDER, source_reference=source_text(record)[:128],
        exchange_reference=record.venue_trade_id,
    )


def captured_book(session, today: date, horizon_start: date, orders, order_books
                  ) -> CapturedBook:
    """The captured deals one position read counts, and the ETRM trades they stand for.

    ``orders`` and ``order_books`` are the book's screen orders as the caller may see them
    (the ETRM trades among them). Captured deals are read in the caller's book scope (the ORM
    applies it): the current version of each deal traded on or before ``today`` that still
    delivers on or after ``horizon_start``.
    """

    from eurogas_nexus.application.deal_capture import captured_side
    from eurogas_nexus.db.models import CapturedDealRecord
    from eurogas_nexus.domain.deals.eod import pair_deals
    from eurogas_nexus.domain.deals.position import classify

    book = CapturedBook()
    records = (
        session.query(CapturedDealRecord)
        .filter(CapturedDealRecord.superseded_at_utc.is_(None),
                CapturedDealRecord.trade_date <= today,
                CapturedDealRecord.delivery_end >= horizon_start)
        .order_by(CapturedDealRecord.trade_date, CapturedDealRecord.trade_time_utc,
                  CapturedDealRecord.deal_key)
        .all()
    )
    if not records:
        return book
    rules, warning = kind_rules()
    if warning:
        book.warnings.append(warning)
    chosen = overrides(session, [record.deal_key for record in records])
    closed, recorded = _closes(session)
    sides, order_of = etrm_sides(orders, order_books)
    pairing = pair_deals([captured_side(record) for record in records], sides, recorded)
    for record in records:
        kind = classify(record, today, rules, chosen.get(record.deal_key))
        twin = pairing.pairs.get(record.deal_key)
        twin_order = order_of.get(twin.trade_id) if twin is not None else None
        day_closed = (record.trade_date, record.book_id or "") in closed
        if twin_order is not None and day_closed:
            counted_as = "etrm"
            book.kinds[twin_order] = kind.kind
        else:
            if twin_order is not None:
                book.suppressed.add(twin_order)
            counted_as = "captured" if record.status == "live" else "none"
        if counted_as == "captured":
            order = as_order(record)
            book.orders.append(order)
            book.books[order.order_observation_id] = record.book_id or ""
            book.kinds[order.order_observation_id] = kind.kind
            if record.counterparty and not record.cleared:
                book.counterparties[order.order_observation_id] = record.counterparty
            book.counted.append((record, kind))
            book.estimate = book.estimate or not day_closed
        book.deals.append({
            "deal_key": record.deal_key,
            "status": record.status,
            "counted_as": counted_as,
            "etrm_trade_id": twin.trade_id if twin is not None and twin_order else None,
            "matched_by": pairing.matched_by.get(record.deal_key) if twin_order else None,
            "day_closed": day_closed,
            "position_kind": kind.as_dict(),
        })
    return book


# ----------------------------------------------------------------------------- exact position


def exact_position(book: CapturedBook, horizon_start: date, horizon_end: date
                   ) -> list[dict[str, Any]]:
    """Per hub and delivery month: the counted captured deals' physical, financial and net.

    Exact decimals from each deal's stored total to the row (no float anywhere): MWh over the
    month's gas days inside the horizon, and the same as a flat rate in the hub's desk unit
    (therms per day at NBP, MW at the continental hubs).
    """

    from eurogas_nexus.domain.deals.position import (
        delivered_mwh,
        desk_unit,
        in_desk_unit,
        months_between,
    )

    if horizon_end < horizon_start:
        return []
    cells: dict[tuple[str, str], dict[str, Any]] = {}
    for record, kind in book.counted:
        if record.status != "live":
            continue
        first = max(record.delivery_start, horizon_start)
        last = min(record.delivery_end, horizon_end)
        for month, start, stop in months_between(first, last) if first <= last else []:
            mwh = delivered_mwh(record, start, stop)
            cell = cells.setdefault((record.hub, month), {
                "physical": Decimal(0), "financial": Decimal(0), "deals": set()})
            cell[kind.kind] += mwh
            cell["deals"].add(record.deal_key)
    out = []
    months = {month: (start, stop) for month, start, stop in months_between(horizon_start,
                                                                           horizon_end)}
    for (hub, month), cell in sorted(cells.items(), key=lambda item: (item[0][1], item[0][0])):
        start, stop = months[month]
        physical, financial = cell["physical"], cell["financial"]
        net = physical + financial
        out.append({
            "hub": hub, "month": month,
            "first_gas_day": start.isoformat(), "last_gas_day": stop.isoformat(),
            "unit": desk_unit(hub),
            "physical": _txt(in_desk_unit(hub, physical, start, stop)),
            "financial": _txt(in_desk_unit(hub, financial, start, stop)),
            "net": _txt(in_desk_unit(hub, net, start, stop)),
            "physical_mwh": _txt(physical.quantize(Decimal("0.001"))),
            "financial_mwh": _txt(financial.quantize(Decimal("0.001"))),
            "net_mwh": _txt(net.quantize(Decimal("0.001"))),
            "deals": len(cell["deals"]),
        })
    return out


def _txt(value: Decimal) -> str:
    text = format(value.normalize(), "f")
    return "0" if text in {"-0", ""} else text


def not_valued(book: CapturedBook, marks: dict) -> list[dict[str, Any]]:
    """Counted captured deals the marks do not value: listed, never counted as zero."""

    from eurogas_nexus.application.deal_capture import deal_value

    out = []
    for record, _kind in book.counted:
        value, reason = deal_value(record, marks)
        if value is None:
            out.append({"deal_key": record.deal_key, "hub": record.hub,
                        "product": record.product, "reason": reason})
    return out


def summary(book: CapturedBook | None, *, horizon_start: date, horizon_end: date,
            marks: dict | None = None) -> dict[str, Any] | None:
    """What a position screen says about the captured deals in it (``None`` when none)."""

    if book is None or not book.deals:
        return None
    counted = [deal for deal in book.deals if deal["counted_as"] == "captured"]
    return {
        "label": book.label,
        "deals_counted": len(counted),
        "deals_counted_from_etrm": sum(1 for d in book.deals if d["counted_as"] == "etrm"),
        "etrm_trades_not_counted": len(book.suppressed),
        "kinds": {
            "physical": sum(1 for d in counted if d["position_kind"]["kind"] == "physical"),
            "financial": sum(1 for d in counted if d["position_kind"]["kind"] == "financial"),
            "entered_by_hand": sum(1 for d in counted
                                   if d["position_kind"]["basis"] == "entered_by_hand"),
        },
        "rows": exact_position(book, horizon_start, horizon_end),
        "not_valued": not_valued(book, marks) if marks is not None else [],
        "method": ("Captured deals not yet represented by their ETRM trade, in exact "
                   "decimals; a deal and its ETRM trade count once (the captured deal until "
                   "the day is closed, then the ETRM trade)."),
        "warnings": list(book.warnings),
    }
