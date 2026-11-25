"""The scheduler's reconciliation of one gas day: trades, confirmations, nominations, TSO (SCHED-1).

For one gas day, per hub (point) and counterparty, from the firm's own records only (AGENTS.md
rule 19):

- **traded**: the bilateral deals the ETRM import holds (``screen_order_observations``,
  provider ``ETRM``) delivering on the gas day, their quantity for the day (a delivery that
  does not start and end on the 06:00 CET gas-day boundary is pro-rated by hours and said so);
  exchange trades are counted per hub but not reconciled, since the exchange's clearing house
  notifies them to the TSO;
- **confirmed**: the counterparty's confirmation of each deal, where the scheduling import
  carries ``trade_confirmation`` statuses (``etrm.nominations.v1``);
- **nominated** and **TSO**: the newest statuses of the gas day's trade and counterparty
  nominations (``gas_day_nomination_events`` with ``line_ref`` ``trade:<id>`` or
  ``counterparty:<name>``): the nominated quantity, the TSO's matched quantity after it, the
  counterparty's own quantity and shipper codes where the import gives them (migration 0085).

Every difference is explained by ``domain/portfolio/nomination_reconciliation`` with its
arithmetic and the next thing to check, ordered by the time left to the hub's next cut-off
(``gas_day.cutoffs_for``: a declared window, else the network-code default, labelled) and the
MWh at risk. The cash-out exposure is the MWh at risk at the approved cash-out premium (short)
or discount (long) of the hub's books (``gas_day.cash_out_assumption``), labelled indicative:
no published imbalance price is read.

Scope is the gas day's own (``gas_day.scope_of``): a caller a mandate names sees the books it
lists, anyone else every book they may see. A new or worse break near a cut-off reaches the
scheduler as a monitoring alert in the ``nomination`` channel (:func:`queue_break_alerts`),
deduplicated, held back for :data:`COOLDOWN` unless it worsens, and withdrawn when it clears.

Read only: nothing is nominated, confirmed or sent (AGENTS.md rule 8).

调度对账：按燃气日、枢纽与交易对手核对交易、对手确认、提名与 TSO 匹配，逐项解释差异与下一步；
按截止时间与风险量排序，指示性不平衡成本；
临近截止的新增或恶化差异按 nomination 渠道提醒，消除后撤回。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta
from typing import Any

from eurogas_nexus.domain.portfolio.nomination_reconciliation import (
    BUCKET_RANK,
    IN,
    KINDS,
    OUT,
    Break,
    CutoffFact,
    Group,
    NominationFact,
    TradeFact,
    reconcile,
    urgency,
)

#: Steps that nominate (the reconciliation reads these and the confirmations).
NOMINATION_STEPS = ("nomination", "renomination")
CONFIRMATION_STEP = "trade_confirmation"
#: The line references a trade nomination uses.
LINE_PREFIXES = ("trade:", "counterparty:")
#: A break's alert is not notified again within this time unless it worsens (LNG-2's rule).
COOLDOWN = timedelta(minutes=30)
ALERT_CATEGORY = "gas_day_break"
ALERT_TYPE = "nomination_break"
#: Buckets in which a break is "near a cut-off": alerted, and on Today's "What needs me".
NEAR = frozenset({"due_soon", "passed"})
_SEVERITY_RANK = {"info": 0, "warning": 1, "critical": 2}


class ReconciliationError(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def _aware(moment) -> datetime | None:
    if moment is None:
        return None
    if not isinstance(moment, datetime):
        moment = datetime.fromisoformat(str(moment))
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def _simulated(source_system: str | None, reference: str | None = None) -> bool:
    return str(source_system or "").endswith("_Sim") or str(reference or "").lower().startswith(
        "demo")


# ------------------------------------------------------------------------------ scope


def scope_books(session, caller, today: date) -> tuple[frozenset[str] | None, dict[str, Any]]:
    """The books of the caller's gas day (``gas_day.scope_of``) and the scope's payload."""

    from eurogas_nexus.application.gas_day import scope_of

    scope = scope_of(session, caller, today)
    books = scope.owned_books if scope.trader is not None else scope.visible
    return books, scope.payload()


# ------------------------------------------------------------------------------ facts


def _trade_days(start: datetime, end: datetime) -> tuple[date, date, bool]:
    """First and last gas day a delivery touches, and whether both ends sit on a gas-day
    boundary (06:00 CET)."""

    from eurogas_nexus.domain.market.gas_day import gas_day_label, gas_day_start_for_date

    first = date.fromisoformat(gas_day_label(start))
    last = date.fromisoformat(gas_day_label(end - timedelta(seconds=1)))
    aligned = (gas_day_start_for_date(first) == start
               and gas_day_start_for_date(last + timedelta(days=1)) == end)
    return first, last, aligned


def trade_fact(order, day: date, confirmation=None) -> TradeFact | None:
    """One deal's share of ``day``: total over its gas days when it is aligned to them, else
    pro-rated by the hours of the day it covers (and marked so); None when it misses the day."""

    from eurogas_nexus.domain.market.gas_day import gas_day_start_for_date

    start, end = _aware(order.delivery_start_utc), _aware(order.delivery_end_utc)
    if start is None or end is None or end <= start:
        return None
    first, last, aligned = _trade_days(start, end)
    day_start = gas_day_start_for_date(day)
    day_end = gas_day_start_for_date(day + timedelta(days=1))
    overlap = (min(end, day_end) - max(start, day_start)).total_seconds()
    if overlap <= 0:
        return None
    total = float(order.quantity_mwh or 0.0)
    full = overlap >= (day_end - day_start).total_seconds() - 60
    if aligned:
        mwh = total / ((last - first).days + 1)
    else:
        mwh = total * overlap / (end - start).total_seconds()
    return TradeFact(
        trade_id=order.order_observation_id,
        deal_ref=str(order.external_order_id or order.order_observation_id),
        hub=str(order.hub).upper(),
        counterparty=str(order.account_label or "counterparty not held"),
        direction=IN if str(order.side).upper() in {"BUY", "B"} else OUT,
        mwh=round(mwh, 3),
        first_day=first,
        last_day=last,
        traded_at=_aware(order.observed_at_utc),
        book_id=order.book_id or "",
        misaligned=not full,
        hours_in_day=round(overlap / 3600.0, 2),
        confirmation=None if confirmation is None else confirmation.status,
        confirmation_at=None if confirmation is None else _aware(confirmation.recorded_at_utc),
        confirmation_by=None if confirmation is None else confirmation.recorded_by,
        simulated=_simulated(order.source_system, order.source_reference),
    )


def _orders(session, days: list[date], books, hub: str | None) -> list:
    from eurogas_nexus.db.models import ScreenOrderObservationRecord as Order
    from eurogas_nexus.domain.market.gas_day import gas_day_start_for_date

    start = gas_day_start_for_date(days[0])
    end = gas_day_start_for_date(days[-1] + timedelta(days=1))
    query = (session.query(Order)
             .filter(Order.delivery_start_utc < end)
             .filter(Order.delivery_end_utc > start))
    if hub:
        query = query.filter(Order.hub == hub.upper())
    if books is not None:
        query = query.filter(Order.book_id.in_(sorted(books) or [""]))
    return query.order_by(Order.observed_at_utc, Order.order_observation_id).all()


def _orders_by_ref(session, refs: Iterable[str], books) -> dict[str, Any]:
    """The ETRM deals that trade line references name, by either id."""

    from sqlalchemy import or_

    from eurogas_nexus.db.models import ScreenOrderObservationRecord as Order

    refs = sorted(set(refs))
    if not refs:
        return {}
    query = session.query(Order).filter(Order.provider_id == "ETRM").filter(
        or_(Order.order_observation_id.in_(refs), Order.external_order_id.in_(refs)))
    if books is not None:
        query = query.filter(Order.book_id.in_(sorted(books) or [""]))
    out: dict[str, Any] = {}
    for row in query:
        out[row.order_observation_id] = row
        out.setdefault(str(row.external_order_id), row)
    return out


def _events(session, days: list[date], hub: str | None) -> list:
    from sqlalchemy import or_

    from eurogas_nexus.db.models import GasDayNominationEventRecord as Event

    query = (session.query(Event)
             .filter(Event.gas_day.in_(days))
             .filter(Event.step.in_(NOMINATION_STEPS))
             .filter(or_(*[Event.line_ref.like(f"{prefix}%") for prefix in LINE_PREFIXES])))
    if hub:
        query = query.filter(Event.hub == hub.upper())
    return query.order_by(Event.recorded_at_utc, Event.event_id).all()


def _confirmations(session, refs: list[str]) -> dict[str, Any]:
    """The newest counterparty confirmation per ``trade:<id>`` line."""

    from eurogas_nexus.db.models import GasDayNominationEventRecord as Event

    if not refs:
        return {}
    out: dict[str, Any] = {}
    for row in (session.query(Event)
                .filter(Event.step == CONFIRMATION_STEP)
                .filter(Event.line_ref.in_(sorted(set(refs))))
                .order_by(Event.recorded_at_utc, Event.event_id)):
        out[row.line_ref] = row
    return out


def nomination_fact(day: date, line_ref: str, events: list, order=None,
                    trade_days: tuple[date, date] | None = None) -> NominationFact:
    """One line's state from its statuses in time order: the newest nomination sent, the
    TSO's response recorded after it, and the matching fields the newest row holding them
    gives."""

    sent = [e for e in events if e.status in ("sent", "renominated") and e.quantity_mwh is not None]
    last_nom = sent[-1] if sent else None
    after = _aware(last_nom.recorded_at_utc) if last_nom is not None else None
    replies = [e for e in events if e.status in ("confirmed", "done", "mismatch_queried")
               and (after is None or _aware(e.recorded_at_utc) >= after)]
    reply = replies[-1] if replies else None
    newest = events[-1]
    nominated = (float(last_nom.quantity_mwh) if last_nom is not None
                 else float(reply.quantity_mwh) if reply is not None
                 and reply.status != "mismatch_queried" and reply.quantity_mwh is not None
                 else None)
    tso = None
    tso_status = "awaiting"
    if reply is not None:
        tso_status = "mismatch" if reply.status == "mismatch_queried" else "confirmed"
        tso = (float(reply.quantity_mwh) if reply.quantity_mwh is not None
               else 0.0 if reply.status == "mismatch_queried" else nominated)
        if last_nom is None and reply.status != "mismatch_queried":
            nominated = tso  # only the TSO's figure is held: it stands for the nomination
    if newest.status == "to_send":
        nominated, tso, tso_status = None, None, "not_sent"

    def held(name: str):
        for row in reversed(events):
            value = getattr(row, name, None)
            if value not in (None, ""):
                return value
        return None

    counterparty = held("counterparty")
    if counterparty is None and line_ref.startswith("counterparty:"):
        counterparty = line_ref.split(":", 1)[1]
    other = reply.counterparty_quantity_mwh if reply is not None else None
    return NominationFact(
        gas_day=day,
        line_ref=line_ref,
        hub=str(newest.hub).upper(),
        trade_id=None if order is None else order.order_observation_id,
        trade_days=trade_days,
        counterparty=counterparty,
        direction=held("direction"),
        point=held("point"),
        shipper_code=held("shipper_code"),
        counterparty_shipper_code=held("counterparty_shipper_code"),
        step=(last_nom or newest).step,
        status=newest.status,
        nominated_mwh=nominated,
        nominated_at=_aware((last_nom or reply or newest).recorded_at_utc),
        tso_mwh=tso,
        tso_status=tso_status,
        tso_at=None if reply is None else _aware(reply.recorded_at_utc),
        counterparty_mwh=None if other is None else float(other),
        book_id=newest.book_id,
        recorded_by=newest.recorded_by,
        source_system=newest.source_system,
        simulated=_simulated(newest.source_system),
    )


def _cutoffs(session, hub: str, day: date, now: datetime) -> list[CutoffFact]:
    from eurogas_nexus.application.gas_day import cutoffs_for

    return [CutoffFact(key=item["key"], at_utc=datetime.fromisoformat(item["at_utc"]),
                       basis=item["basis"], source=item["source"], name=item.get("name"))
            for item in cutoffs_for(session, hub, day, now)]


# ------------------------------------------------------------------------------ the read


def reconciliation(
    session,
    caller,
    gas_day: date,
    *,
    now: datetime,
    hub: str | None = None,
    counterparty: str | None = None,
    kind: str | None = None,
    book_id: str | None = None,
    breaks_only: bool = False,
) -> dict[str, Any]:
    """The gas day's reconciliation for this caller, filtered as asked."""

    from eurogas_nexus.application.gas_day import gas_day_hours
    from eurogas_nexus.domain.market.gas_day import gas_day_label

    if kind is not None and kind not in KINDS:
        raise ReconciliationError("unknown_kind", f"kind must be one of {', '.join(KINDS)}")
    today = date.fromisoformat(gas_day_label(now))
    if abs((gas_day - today).days) > 31:
        raise ReconciliationError("gas_day_out_of_range",
                                  "only gas days within 31 days of today")
    books, scope = scope_books(session, caller, today)
    if book_id is not None:
        if books is not None and book_id not in books:
            raise ReconciliationError("book_not_in_scope",
                                      "this book is not in the gas day of the books you hold")
        books = frozenset({book_id})
    days = [gas_day - timedelta(days=1), gas_day, gas_day + timedelta(days=1)]
    hours = gas_day_hours(gas_day)

    orders = _orders(session, [gas_day], books, hub)
    bilateral = [o for o in orders if str(o.provider_id).upper() == "ETRM"]
    exchange = [o for o in orders if str(o.provider_id).upper() != "ETRM"]

    rows = _events(session, days, hub)
    by_line: dict[tuple[date, str], list] = {}
    for row in rows:
        by_line.setdefault((row.gas_day, row.line_ref), []).append(row)
    trade_refs = {ref.split(":", 1)[1] for _day, ref in by_line if ref.startswith("trade:")}
    named = _orders_by_ref(session, trade_refs, None)  # the scope applies to the deal below
    confirmations = _confirmations(
        session, [f"trade:{o.order_observation_id}" for o in bilateral]
        + [f"trade:{o.external_order_id}" for o in bilateral])

    def visible(book: str | None, order=None) -> bool:
        if books is None:
            return True
        if order is not None:
            return order.book_id in books
        return book is not None and book in books

    trades: list[TradeFact] = []
    for order in bilateral:
        confirmation = (confirmations.get(f"trade:{order.order_observation_id}")
                        or confirmations.get(f"trade:{order.external_order_id}"))
        fact = trade_fact(order, gas_day, confirmation)
        if fact is not None and fact.mwh > 0:
            trades.append(fact)
    on_day: list[NominationFact] = []
    adjacent: list[NominationFact] = []
    for (day, ref), events in sorted(by_line.items(), key=lambda item: (item[0][0], item[0][1])):
        order = named.get(ref.split(":", 1)[1]) if ref.startswith("trade:") else None
        if not visible(events[-1].book_id, order):
            continue
        trade_days = None
        if order is not None:
            start, end = _aware(order.delivery_start_utc), _aware(order.delivery_end_utc)
            first, last, _aligned = _trade_days(start, end)
            if not first <= day <= last:
                trade_days = (first, last)
        fact = nomination_fact(day, ref, events, order, trade_days)
        (on_day if day == gas_day else adjacent).append(fact)

    hubs = sorted({t.hub for t in trades} | {n.hub for n in on_day})
    cutoffs = {h: _cutoffs(session, h, gas_day, now) for h in hubs}
    groups = reconcile(gas_day, trades, on_day, hours=hours, cutoffs=cutoffs,
                       adjacent=adjacent, now=now)
    return _payload(session, gas_day, groups, cutoffs, exchange, hours, now, scope,
                    filters={"hub": hub, "counterparty": counterparty, "kind": kind,
                             "book_id": book_id, "breaks_only": breaks_only})


def _cash_out(session, hub: str, books: list[str], day: date, gap: float | None) -> dict:
    from eurogas_nexus.application.gas_day import cash_out_assumption, cost_of_nothing

    if gap is None:
        return {"value": None, "basis": "not_an_imbalance",
                "reason": "an open confirmation is a risk to the match, not an imbalance yet"}
    assumption = cash_out_assumption(session, books, hub, day)
    cost = cost_of_nothing(gap, assumption, hub)
    if cost.get("basis") == "assumption":
        cost["basis"] = "indicative"
        cost["note"] = ("Indicative: the MWh at risk at the approved cash-out "
                        f"{'premium' if gap < 0 else 'discount'} ({cost['assumption_set']} "
                        f"v{cost['assumption_version']}); no published imbalance price is read")
    return cost


def _quantity(hub: str, mwh: float | None, day: date, hours: float) -> dict | None:
    from eurogas_nexus.application.gas_day import native_quantity

    if mwh is None:
        return None
    out = native_quantity(hub, mwh, day)
    out["kwh_h"] = round(mwh * 1000.0 / hours) if hours else None
    return out


def _break_id(day: date, item: Break) -> str:
    return f"{day.isoformat()}:{item.key}"


def _payload(session, day: date, groups: list[Group], cutoffs: dict, exchange: list,
             hours: float, now: datetime, scope: dict, *, filters: dict) -> dict[str, Any]:
    hub_urgency = {hub: urgency(cuts, now) for hub, cuts in cutoffs.items()}
    out_groups: list[dict[str, Any]] = []
    out_breaks: list[dict[str, Any]] = []
    wanted_cpty = (filters.get("counterparty") or "").casefold().strip()
    for group in groups:
        if wanted_cpty and wanted_cpty not in group.counterparty.casefold():
            continue
        breaks = [b for b in group.breaks if filters.get("kind") in (None, b.kind)]
        if filters.get("kind") and not breaks:
            continue
        if filters.get("breaks_only") and not breaks:
            continue
        when = hub_urgency.get(group.hub) or {"bucket": "open", "cutoff": None,
                                               "minutes_left": None, "severity": "info"}
        books = sorted({t.book_id for t in group.trades if t.book_id}
                       | {n.book_id for n in group.nominations if n.book_id})
        items = []
        for item in breaks:
            payload = {
                "id": _break_id(day, item),
                "gas_day": day.isoformat(),
                **item.as_dict(),
                "quantity": _quantity(group.hub, item.mwh_at_risk, day, hours),
                "urgency": when["bucket"],
                "severity": when["severity"] if item.mwh_at_risk > 0 else "info",
                "cutoff": when["cutoff"],
                "minutes_left": when["minutes_left"],
                "cash_out": _cash_out(session, group.hub, books, day, item.gap_mwh),
                "book_ids": books,
                "simulated": any(t.simulated for t in group.trades)
                or any(n.simulated for n in group.nominations),
            }
            items.append(payload)
        out_breaks += items
        out_groups.append({
            "hub": group.hub,
            "point": group.point,
            "counterparty": group.counterparty,
            "shipper_codes": group.shipper_codes,
            "traded": _quantity(group.hub, group.traded_mwh, day, hours),
            "confirmed": _quantity(group.hub, group.confirmed_mwh, day, hours),
            "nominated": _quantity(group.hub, group.nominated_mwh, day, hours),
            "tso": _quantity(group.hub, group.tso_mwh, day, hours),
            "held": {
                "confirmation": group.confirmed_mwh is not None,
                "nomination": group.nominated_mwh is not None,
                "tso": group.tso_mwh is not None,
            },
            "state": "break" if items else "matched",
            "urgency": when["bucket"],
            "cutoff": when["cutoff"],
            "minutes_left": when["minutes_left"],
            "mwh_at_risk": round(max((b["mwh_at_risk"] for b in items), default=0.0), 1),
            "break_ids": [b["id"] for b in items],
            "book_ids": books,
            "trades": [_trade_payload(t, day, hours) for t in group.trades],
            "nominations": [_nomination_payload(n, day, hours) for n in group.nominations],
            "simulated": any(t.simulated for t in group.trades)
            or any(n.simulated for n in group.nominations),
        })

    def order(item: dict) -> tuple:
        return (BUCKET_RANK.get(item["urgency"], 9),
                item["minutes_left"] if item["minutes_left"] is not None else 10**9,
                -item["mwh_at_risk"])

    out_breaks.sort(key=lambda b: (*order(b), KINDS.index(b["kind"])))
    out_groups.sort(key=lambda g: (g["state"] != "break", *order(g), g["hub"], g["counterparty"]))
    exchange_by_hub: dict[str, dict[str, Any]] = {}
    for order_row in exchange:
        if filters.get("hub") and str(order_row.hub).upper() != filters["hub"].upper():
            continue
        fact = trade_fact(order_row, day)
        if fact is None:
            continue
        entry = exchange_by_hub.setdefault(fact.hub, {"hub": fact.hub, "trades": 0, "mwh": 0.0})
        entry["trades"] += 1
        entry["mwh"] = round(entry["mwh"] + fact.signed, 1)
    counts = {kind: sum(1 for b in out_breaks if b["kind"] == kind) for kind in KINDS}
    return {
        "gas_day": day.isoformat(),
        "hours": hours,
        "as_of_utc": now.isoformat(),
        "scope": scope,
        "filters": filters,
        "hubs": [{"hub": hub, **hub_urgency[hub],
                  "cutoffs": [{"key": c.key, "name": c.name, "at_utc": c.at_utc.isoformat(),
                               "basis": c.basis, "source": c.source,
                               "passed": c.at_utc <= now} for c in cutoffs[hub]]}
                 for hub in sorted(hub_urgency)],
        "groups": out_groups,
        "breaks": out_breaks,
        "counts": {kind: n for kind, n in counts.items() if n},
        "kinds": list(KINDS),
        "mwh_at_risk": round(sum(b["mwh_at_risk"] for b in out_breaks if b["gap_mwh"] is not None),
                             1),
        "exchange_trades": [{**entry, "note": "Notified by the exchange's clearing house; not "
                             "reconciled here"} for entry in exchange_by_hub.values()],
        "populated": bool(out_groups),
        "empty": None if out_groups else {
            "code": "nothing_to_reconcile",
            "reason": "No bilateral deal or trade nomination for this gas day in the books you "
                      "hold",
            "action": "Deals come from the ETRM import, nominations and confirmations from the "
                      "scheduling import (etrm.nominations.v1)",
        },
        "simulated": any(g["simulated"] for g in out_groups),
        "execution": "none: decision support only; nothing is nominated, confirmed or sent",
    }


def _trade_payload(t: TradeFact, day: date, hours: float) -> dict[str, Any]:
    return {
        "trade_id": t.trade_id,
        "deal_ref": t.deal_ref,
        "direction": t.direction,
        "quantity": _quantity(t.hub, t.mwh, day, hours),
        "traded_at_utc": None if t.traded_at is None else t.traded_at.isoformat(),
        "delivery": {"first_gas_day": t.first_day.isoformat(),
                     "last_gas_day": t.last_day.isoformat(),
                     "aligned": not t.misaligned, "hours_in_day": t.hours_in_day},
        "confirmation": t.confirmation,
        "confirmation_at_utc": None if t.confirmation_at is None else t.confirmation_at.isoformat(),
        "book_id": t.book_id,
        "simulated": t.simulated,
    }


def _nomination_payload(n: NominationFact, day: date, hours: float) -> dict[str, Any]:
    return {
        "line_ref": n.line_ref,
        "step": n.step,
        "status": n.status,
        "trade_id": n.trade_id,
        "counterparty": n.counterparty,
        "direction": n.direction,
        "point": n.point,
        "shipper_code": n.shipper_code,
        "counterparty_shipper_code": n.counterparty_shipper_code,
        "nominated": _quantity(n.hub, n.nominated_mwh, day, hours),
        "nominated_at_utc": None if n.nominated_at is None else n.nominated_at.isoformat(),
        "tso": _quantity(n.hub, n.tso_mwh, day, hours),
        "tso_status": n.tso_status,
        "tso_at_utc": None if n.tso_at is None else n.tso_at.isoformat(),
        "counterparty_mwh": n.counterparty_mwh,
        "recorded_by": n.recorded_by,
        "source_system": n.source_system,
        "simulated": n.simulated,
    }


#: ``format=csv`` columns, one row per break, in order (additions go at the end).
CSV_COLUMNS: tuple[str, ...] = (
    "gas_day", "hub", "point", "counterparty", "kind", "urgency", "cutoff_key", "cutoff_utc",
    "minutes_left", "mwh_at_risk", "kwh_h", "gap_mwh", "cash_out_value", "cash_out_currency",
    "cash_out_basis", "explanation", "next_step", "trade_ids", "line_refs", "book_ids",
    "simulated",
)


def csv_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """One flat row per break, in the read's order."""

    out = []
    for item in payload["breaks"]:
        cut = item.get("cutoff") or {}
        cost = item.get("cash_out") or {}
        out.append({
            "gas_day": item["gas_day"], "hub": item["hub"], "point": item["point"],
            "counterparty": item["counterparty"], "kind": item["kind"],
            "urgency": item["urgency"], "cutoff_key": cut.get("key"),
            "cutoff_utc": cut.get("at_utc"), "minutes_left": item["minutes_left"],
            "mwh_at_risk": item["mwh_at_risk"],
            "kwh_h": (item.get("quantity") or {}).get("kwh_h"), "gap_mwh": item["gap_mwh"],
            "cash_out_value": cost.get("value"), "cash_out_currency": cost.get("currency"),
            "cash_out_basis": cost.get("basis"), "explanation": item["explanation"],
            "next_step": item["next_step"], "trade_ids": ";".join(item["trade_ids"]),
            "line_refs": ";".join(item["line_refs"]), "book_ids": ";".join(item["book_ids"]),
            "simulated": item["simulated"],
        })
    return out


# ------------------------------------------------------------------------------ Today


def needs_me_items(payloads: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Breaks near a cut-off (due soon, or no renomination left on a running gas day) for
    Today's "What needs me": the soonest and largest first."""

    out = []
    for payload in payloads:
        for item in payload.get("breaks") or []:
            if item["urgency"] not in NEAR:
                continue
            cut = item.get("cutoff") or {}
            out.append({
                "kind": "reconciliation",
                "id": item["id"],
                "title": f"{item['hub']} · {item['counterparty']}",
                "title_zh": f"{item['hub']} · {item['counterparty']}",
                "break_kind": item["kind"],
                "hub": item["hub"],
                "gas_day": item["gas_day"],
                "urgency": "overdue" if item["urgency"] == "passed" else "due_soon",
                "status": "breach" if item["severity"] == "critical" else "watch",
                "explanation": item["explanation"],
                "explanation_zh": item["explanation_zh"],
                "quantity": item.get("quantity"),
                "deadline_utc": cut.get("at_utc"),
                "simulated": item["simulated"],
                "as_of": payload.get("as_of_utc"),
                "target": {"mode": "today", "task": "reconciliation",
                           "params": {"gas_day": item["gas_day"], "hub": item["hub"]}},
            })
    out.sort(key=lambda item: (item["urgency"] != "overdue", item["status"] != "breach",
                               item["deadline_utc"] or "9999"))
    return out


# ------------------------------------------------------------------------------ alerts


def fingerprint(break_id: str) -> str:
    return f"recon:{break_id}"


def _digest(item: dict[str, Any]) -> str:
    content = {"kind": item["kind"], "mwh": round(item["mwh_at_risk"]),
               "text": item["explanation"], "severity": item["severity"]}
    return hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()[:24]


def queue_break_alerts(session, *, now: datetime) -> dict[str, int]:
    """Raise, update or withdraw one alert per break of today's and tomorrow's gas day,
    firm-wide (the worker's caller), routed to scheduling (``nomination``).

    A break is alerted while its hub's next cut-off is within three hours, or no
    renomination is left on a running gas day. Its notification is queued once per content
    (dedupe), not again within :data:`COOLDOWN` unless its severity rises or its MWh at risk
    grows; a break that clears (or a gas day that ends) resolves the alert and, if it was
    notified, tells the scheduler it is withdrawn.
    """

    from eurogas_nexus.application.caller import firm_caller
    from eurogas_nexus.db.models import MonitoringAlertRecord
    from eurogas_nexus.domain.market.gas_day import gas_day_label
    from eurogas_nexus.security.portfolio_scope import firm_wide_scope

    today = date.fromisoformat(gas_day_label(now))
    counts = {"raised": 0, "notified": 0, "held_back": 0, "withdrawn": 0}
    current: dict[str, dict[str, Any]] = {}
    with firm_wide_scope():
        caller = firm_caller(session=session)
        for day in (today, today + timedelta(days=1)):
            payload = reconciliation(session, caller, day, now=now)
            for item in payload["breaks"]:
                if item["urgency"] in NEAR and item["mwh_at_risk"] > 0:
                    current[fingerprint(item["id"])] = item
    open_rows = {
        row.fingerprint: row
        for row in session.query(MonitoringAlertRecord)
        .filter(MonitoringAlertRecord.category == ALERT_CATEGORY)
        .filter(MonitoringAlertRecord.resolved_at_utc.is_(None))
    }
    for key, item in current.items():
        decision = _raise(session, key, item, open_rows.get(key), now)
        counts["raised"] += 1
        counts["notified" if decision == "notified" else "held_back"] += 1
    for key, row in open_rows.items():
        if key not in current:
            counts["withdrawn"] += int(_withdraw(session, row, now))
    session.flush()
    return counts


def _raise(session, key: str, item: dict[str, Any], alert, now: datetime) -> str:
    from eurogas_nexus.application.alert_routing import addressed_line, route_for
    from eurogas_nexus.application.notifications import queue_notification
    from eurogas_nexus.db.repositories.monitoring import upsert_monitoring_alert
    from eurogas_nexus.domain.monitoring import MonitoringCandidate

    route = route_for(ALERT_CATEGORY)
    held = dict(alert.evidence_snapshot or {}) if alert is not None else {}
    notified = held.get("notified")
    digest = _digest(item)
    decision = "notified"
    if notified and notified.get("digest") == digest:
        decision = "duplicate"
    elif notified and (
        now - (_aware(notified.get("at_utc")) or now) < COOLDOWN
        and _SEVERITY_RANK.get(item["severity"], 0)
        <= _SEVERITY_RANK.get(str(notified.get("severity")), 0)
        and item["mwh_at_risk"] <= float(notified.get("mwh_at_risk") or 0.0) + 1.0
    ):
        decision = "cooldown"
    cut = item.get("cutoff") or {}
    title = (f"{item['hub']} {item['counterparty']}: {item['kind'].replace('_', ' ')}, "
             f"{item['mwh_at_risk']:,.0f} MWh at risk")
    kind_zh = _KIND_ZH.get(item["kind"], item["kind"])
    title_zh = (f"{item['hub']} {item['counterparty']}：{kind_zh}，"
                f"风险 {item['mwh_at_risk']:,.0f} MWh")
    evidence = {
        "break": item,
        "book_ids": item["book_ids"],
        "for": ["OPERATIONS"],
        "notified": notified,
        "advisory": "For a person to decide; nothing is nominated, confirmed or sent.",
    }
    if decision == "notified":
        cost = item.get("cash_out") or {}
        cost_line = (f"Indicative cash-out {cost['value']:,.0f} {cost.get('currency')}"
                     f" ({cost.get('note')})." if cost.get("value") is not None else "")
        due = (f"Next cut-off: {cut.get('key', '').replace('_', ' ')} at {cut.get('at_utc')}."
               if cut else "No renomination is left for this gas day.")
        body = "\n".join(filter(None, [
            f"Gas day {item['gas_day']}, {item['hub']}, {item['counterparty']}.",
            item["explanation"], f"Next: {item['next_step']}", due, cost_line, "",
            "From Today's gas-day reconciliation; nominations are made in the scheduling "
            "system.", "", addressed_line(route)]))
        queue_notification(
            session, category=route.notification_category, severity=item["severity"],
            title=title, body=body, dedupe_key=f"recon:{item['id']}:{digest}", now=now)
        evidence["notified"] = {"digest": digest, "at_utc": now.isoformat(),
                                "severity": item["severity"],
                                "mwh_at_risk": item["mwh_at_risk"]}
    else:
        evidence["held_back"] = {"reason": decision, "at_utc": now.isoformat()}
    upsert_monitoring_alert(session, MonitoringCandidate(
        fingerprint=key,
        category=ALERT_CATEGORY,
        alert_type=ALERT_TYPE,
        severity=item["severity"],
        title_en=title,
        title_zh_cn=title_zh,
        message_en=f"{item['explanation']} Next: {item['next_step']}",
        message_zh_cn=f"{item['explanation_zh']} 下一步：{item['next_step_zh']}",
        entity_type="gas_day_break",
        entity_id=item["id"],
        event_time_utc=now,
        evidence_snapshot=evidence,
        source_refs=[*(f"trade:{t}" for t in item["trade_ids"]), *item["line_refs"]],
        warnings=[],
        simulated=bool(item["simulated"]),
        human_review_required=True,
    ), now_utc=now)
    return decision


def _withdraw(session, alert, now: datetime) -> bool:
    from eurogas_nexus.application.alert_routing import addressed_line, route_for
    from eurogas_nexus.application.notifications import queue_notification

    evidence = dict(alert.evidence_snapshot or {})
    reason = "the break is no longer there: trades, nominations and the TSO now agree, or the " \
             "gas day has ended"
    evidence["withdrawn"] = {"reason": reason, "reason_zh": "差异已消除或燃气日已结束",
                             "at_utc": now.isoformat()}
    alert.evidence_snapshot = evidence
    alert.status = "resolved"
    alert.resolved_at_utc = now
    alert.updated_at_utc = now
    alert.message_en = f"Withdrawn: {reason}. Was: {alert.title_en}."
    alert.message_zh_cn = f"已撤回：差异已消除或燃气日已结束。原为：{alert.title_zh_cn}。"
    session.flush()
    notified = evidence.get("notified")
    if not notified:
        return True
    route = route_for(ALERT_CATEGORY)
    queue_notification(
        session, category=route.notification_category,
        severity=str(notified.get("severity") or alert.severity),
        title=f"Withdrawn: {alert.title_en}"[:256],
        body=f"Withdrawn at {now:%d %b %H:%M} UTC: {reason}. Nothing further is needed for "
             f"what was sent before.\n\n{addressed_line(route)}",
        dedupe_key=f"recon:{alert.entity_id}:withdrawn:{notified.get('digest')}", now=now)
    return True


_KIND_ZH = {
    "not_nominated": "未提名",
    "nomination_without_trade": "有提名无交易",
    "quantity_mismatch": "数量不符",
    "counterparty_mismatch": "对手不符",
    "shipper_code_mismatch": "托运人代码不符",
    "wrong_direction": "方向错误",
    "lesser_rule_cut": "较小值规则削减",
    "late": "迟于截止或提名",
    "unit_mismatch": "单位错误",
    "gas_day_misaligned": "燃气日错位",
    "not_confirmed": "对手未确认",
}
