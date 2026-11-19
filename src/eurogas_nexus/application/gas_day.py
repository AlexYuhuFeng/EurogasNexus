"""My gas day (Today, first row for trader and operations): what to clear, by when, at what cost.

Per hub, for today's and tomorrow's gas day, from the firm's own records only (AGENTS.md rule 19):

- **IN**: contract and upstream deliveries by delivery point (nominated quantity where the
  delivery record holds one, else the contract quantity, said so), LNG send-out from the
  regas slots the firm holds, storage withdrawal and imports on held capacity from the
  schedule, purchases booked (ETRM and exchange, spread over their delivery days);
- **OUT**: sales booked, customer offtake, storage injection and exports from the schedule;
- **net to clear** in the hub's own unit (NBP in therms per day, continental hubs in MWh per
  day with the MW figure beside it), long positive;
- **done today**: the within-day and day-ahead trades booked during today's gas day;
- **time left**: the nomination deadline and last renomination of each gas day, from a window
  the firm declares for the market area, else the network-code default labelled as an
  assumption (``domain/market/hub_cutoffs``, the calendar the prompt signals use too);
- **cost of doing nothing**: the net left open at the cash-out premium (short) or discount
  (long) from the approved assumption set in force for the book, labelled as an assumption;
  no published imbalance price is read (``docs/legal/DATA_SOURCE_TERMS.md``, "Imbalance
  prices": the terms of the National Gas and THE publications could not be verified).

**Scope** comes from books and mandates, never from the persona (AGENTS.md rule 7): a caller
named by a mandate sees the books that mandate lists (within the books portfolio isolation
lets him see) less what is delegated to others, plus what is delegated to him; a caller with
no mandate sees every book he may see, each delegated part attributed. Nothing here
nominates, trades or settles (rule 8).

我的燃气日：按枢纽列出今日/明日流入、流出、待平衡净头寸、截止时间与不平衡成本（假设已标注）。
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from eurogas_nexus.domain.portfolio.gas_day_balance import (
    IN,
    OUT,
    Delegation,
    GasDayLine,
    HubBalance,
    balance_for,
)

#: Kinds in the order a desk reads them, IN first.
IN_KINDS = ("supply", "upstream", "lng_send_out", "storage_withdrawal", "import", "purchase")
OUT_KINDS = ("sale", "customer_offtake", "storage_injection", "export")
#: Resource types of a contract that are producer gas landed at a beach terminal.
UPSTREAM_TYPES = frozenset({"UPSTREAM", "UPSTREAM_TENDER", "EQUITY_GAS", "BEACH"})


# ------------------------------------------------------------------ scope


@dataclass(frozen=True)
class Scope:
    """Whose gas day this is: one trader's mandated books, or every book the caller sees."""

    trader: str | None
    owned_books: frozenset[str] | None
    mandates: tuple[dict[str, Any], ...]
    visible: frozenset[str] | None  # None: every book

    def payload(self) -> dict[str, Any]:
        if self.trader is None:
            return {"kind": "all_books", "mandates": [], "books": None}
        return {
            "kind": "mandate",
            "mandates": list(self.mandates),
            "books": sorted(self.owned_books or ()),
        }


def caller_keys(caller) -> set[str]:
    principal = caller.principal
    return {
        str(value).strip().lower()
        for value in (getattr(principal, "principal_id", None), getattr(principal, "name", None))
        if value
    }


def mandates_of(session, caller, today: date) -> list:
    """The mandates in force that name this caller (by sign-in id or name)."""

    from eurogas_nexus.db.models import TraderMandateRecord

    keys = caller_keys(caller)
    return [
        row
        for row in session.query(TraderMandateRecord).order_by(TraderMandateRecord.mandate_id)
        if str(row.trader).strip().lower() in keys
        and (row.valid_until is None or row.valid_until >= today)
    ]


def scope_of(session, caller, today: date) -> Scope:
    from eurogas_nexus.security.portfolio_scope import visible_book_ids

    allowed = visible_book_ids(session)
    visible = None if allowed is None else frozenset(allowed)
    mandates = mandates_of(session, caller, today)
    if not mandates:
        return Scope(None, None, (), visible)
    books: set[str] = set()
    for row in mandates:
        if row.book_ids:
            books.update(row.book_ids)
        elif visible is not None:
            books.update(visible)
    if visible is not None:
        books &= visible
    return Scope(
        trader=str(mandates[0].trader),
        owned_books=frozenset(books),
        mandates=tuple(
            {"id": row.mandate_id, "name": row.display_name, "hubs": list(row.hubs or [])}
            for row in mandates
        ),
        visible=visible,
    )


# ------------------------------------------------------------------ units


def gas_day_hours(day: date) -> float:
    from eurogas_nexus.domain.market.gas_day import gas_day_start_for_date

    start = gas_day_start_for_date(day)
    end = gas_day_start_for_date(day + timedelta(days=1))
    return (end - start).total_seconds() / 3600.0


def native_quantity(hub: str, mwh: float, day: date) -> dict[str, Any]:
    """A day's quantity in the hub's desk unit: NBP th/d; continental MWh/d with its MW."""

    from eurogas_nexus.domain.market.units import convert_energy

    if hub.upper() == "NBP":
        return {"value": round(convert_energy(mwh, "MWh", "therm")), "unit": "th/d",
                "mwh": round(mwh, 1)}
    return {"value": round(mwh, 1), "unit": "MWh/d", "mwh": round(mwh, 1),
            "mw": round(mwh / gas_day_hours(day), 1)}


# ------------------------------------------------------------------ lines


def _aware(moment) -> datetime | None:
    if moment is None:
        return None
    if not isinstance(moment, datetime):
        moment = datetime.fromisoformat(str(moment))
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def _point(contract) -> str | None:
    """The sub-terminal or point the contract delivers at, without the hub's own name."""

    text = str(getattr(contract, "delivery_point_name", "") or "").strip()
    words = text.split()
    if len(words) > 1 and words[0].upper() in {"NBP", "TTF", "THE", "PEG", "ZTP", "CEGH", "PVB",
                                               "PSV", "ZEE", "ETF"}:
        return " ".join(words[1:])
    return text or None


def contract_lines(
    inputs, days: Iterable[date], nominations: dict
) -> list[tuple[date, GasDayLine]]:
    """Physical legs (contracts) delivering on each day: nominated where held, else DCQ."""

    contracts = {row.contract_id: row for row in inputs.contracts}
    out = []
    for leg in inputs.legs:
        if leg.kind != "physical":
            continue
        contract = contracts.get(leg.reference)
        for day in days:
            if not leg.first_gas_day <= day <= leg.last_gas_day:
                continue
            held = nominations.get((leg.reference, day))
            mwh, basis = (held, "nominated") if held is not None else (leg.mwh_per_day,
                                                                         "contract_quantity")
            resource = str(getattr(contract, "resource_type", "") or "").upper()
            kind = "upstream" if resource in UPSTREAM_TYPES else "supply"
            if mwh < 0:
                kind = "sale"
            out.append((day, GasDayLine(
                ref=f"contract:{leg.reference}",
                hub=leg.hub,
                book_id=leg.book_id or "",
                direction=IN if mwh >= 0 else OUT,
                kind=kind,
                label=str(getattr(contract, "contract_name", None) or leg.reference),
                mwh=abs(float(mwh)),
                basis=basis,
                point=_point(contract) if contract is not None else None,
            )))
    return out


def trade_lines(inputs, days: list[date], today: date) -> list[tuple[date, GasDayLine]]:
    """Booked trades delivering on each day; today's WD/DA trades summed per book and side."""

    from eurogas_nexus.domain.market.gas_day import gas_day_label, gas_day_start_for_date

    orders = {order.order_observation_id: order for order in inputs.orders}
    prompt_starts = {gas_day_start_for_date(day) for day in days}
    out: list[tuple[date, GasDayLine]] = []
    prompt: dict[tuple, dict] = {}
    for leg in inputs.legs:
        if leg.kind != "financial":
            continue
        order = orders.get(leg.reference)
        simulated = bool(order is not None and str(order.source_system).endswith("_Sim"))
        start = _aware(getattr(order, "delivery_start_utc", None))
        end = _aware(getattr(order, "delivery_end_utc", None))
        booked = _aware(getattr(order, "observed_at_utc", None))
        is_prompt = bool(
            start in prompt_starts and end is not None and (end - start) <= timedelta(hours=25)
            and booked is not None and gas_day_label(booked) == today.isoformat()
        )
        direction = IN if leg.mwh_per_day > 0 else OUT
        for day in days:
            if not leg.first_gas_day <= day <= leg.last_gas_day:
                continue
            if is_prompt:
                key = (day, leg.hub, leg.book_id or "", direction)
                entry = prompt.setdefault(key, {"mwh": 0.0, "count": 0, "simulated": False})
                entry["mwh"] += abs(leg.mwh_per_day)
                entry["count"] += 1
                entry["simulated"] = entry["simulated"] or simulated
                continue
            provider = str(getattr(order, "provider_id", "") or "").upper()
            label = (str(order.account_label) if provider == "ETRM" and order is not None
                     else str(getattr(order, "venue", None) or "Exchange"))
            out.append((day, GasDayLine(
                ref=f"trade:{leg.reference}",
                hub=leg.hub,
                book_id=leg.book_id or "",
                direction=direction,
                kind="purchase" if direction == IN else "sale",
                label=label,
                mwh=abs(leg.mwh_per_day),
                basis="booked",
                point=str(getattr(order, "contract_code", "") or "") or None,
                simulated=simulated,
            )))
    for (day, hub, book, direction), entry in sorted(prompt.items()):
        out.append((day, GasDayLine(
            ref=f"prompt:{book}:{hub}:{direction}:{day.isoformat()}",
            hub=hub,
            book_id=book,
            direction=direction,
            kind="purchase" if direction == IN else "sale",
            label=f"{entry['count']}",
            mwh=entry["mwh"],
            basis="booked_today",
            simulated=entry["simulated"],
            prompt_trade=True,
        )))
    return out


def _terminal_hubs(session) -> dict[str, str]:
    from eurogas_nexus.db.models import LngTerminalTermsRecord

    return {str(row.name).lower(): str(row.hub).upper()
            for row in session.query(LngTerminalTermsRecord).all()}


def lng_lines(session, days: list[date], visible) -> list[tuple[date, GasDayLine]]:
    """Send-out from the regas slots the firm holds, on each gas day the window covers."""

    from eurogas_nexus.db.models.lng_positions import RegasSlotRecord
    from eurogas_nexus.domain.market.gas_day import gas_day_start_for_date
    from eurogas_nexus.domain.ontology.identity import resolve_hub

    first = gas_day_start_for_date(days[0])
    last = gas_day_start_for_date(days[-1] + timedelta(days=1))
    terminals = _terminal_hubs(session)
    out = []
    rows = session.query(RegasSlotRecord).filter(RegasSlotRecord.book_id.is_not(None)).all()
    for slot in rows:
        if visible is not None and slot.book_id not in visible:
            continue
        start, end = _aware(slot.window_start_utc), _aware(slot.window_end_utc)
        if start is None or end is None or end <= first or start >= last:
            continue
        if not slot.send_out_gwh_d:
            continue
        hub = terminals.get(str(slot.terminal_name).lower()) or resolve_hub(slot.terminal_name).hub
        if hub is None:
            continue
        for day in days:
            day_start = gas_day_start_for_date(day)
            day_end = gas_day_start_for_date(day + timedelta(days=1))
            overlap = (min(end, day_end) - max(start, day_start)).total_seconds()
            if overlap <= 0:
                continue
            share = overlap / (day_end - day_start).total_seconds()
            out.append((day, GasDayLine(
                ref=f"lng:{slot.slot_id}",
                hub=hub,
                book_id=slot.book_id or "",
                direction=IN,
                kind="lng_send_out",
                label=str(slot.terminal_name),
                mwh=float(slot.send_out_gwh_d) * 1000.0 * share,
                basis="slot",
                simulated=str(slot.source_system).endswith("_Sim"),
            )))
    return out


def schedule_lines(session, days: list[date], visible) -> list[tuple[date, GasDayLine]]:
    from eurogas_nexus.db.models import GasDayScheduleLineRecord

    rows = (
        session.query(GasDayScheduleLineRecord)
        .filter(GasDayScheduleLineRecord.gas_day.in_(days))
        .order_by(GasDayScheduleLineRecord.line_id)
        .all()
    )
    out = []
    for row in rows:
        if visible is not None and row.book_id not in visible:
            continue
        out.append((row.gas_day, GasDayLine(
            ref=f"schedule:{row.line_id}",
            hub=row.hub.upper(),
            book_id=row.book_id or "",
            direction=IN if row.direction == IN else OUT,
            kind=row.kind,
            label=row.label,
            mwh=abs(float(row.quantity_mwh)),
            basis="scheduled",
            point=row.point,
            simulated=bool(row.simulated),
        )))
    return out


def nominations_for(session, contract_ids: list[str], days: list[date]) -> dict:
    from eurogas_nexus.db.models import ContractDeliveryRecord

    if not contract_ids:
        return {}
    rows = (
        session.query(ContractDeliveryRecord)
        .filter(ContractDeliveryRecord.contract_id.in_(contract_ids))
        .filter(ContractDeliveryRecord.gas_day.in_(days))
        .all()
    )
    return {(row.contract_id, row.gas_day): float(row.nominated_mwh)
            for row in rows if row.nominated_mwh is not None}


def delegations_for(session, day: date, now: datetime, visible) -> list[Delegation]:
    from eurogas_nexus.db.models import GasDayDelegationRecord, TraderMandateRecord

    names = {row.mandate_id: row.display_name for row in session.query(TraderMandateRecord)}
    out = []
    for row in (
        session.query(GasDayDelegationRecord)
        .filter(GasDayDelegationRecord.revoked_at_utc.is_(None))
        .filter(GasDayDelegationRecord.gas_day_from <= day)
        .filter(GasDayDelegationRecord.gas_day_to >= day)
        .order_by(GasDayDelegationRecord.assigned_at_utc, GasDayDelegationRecord.delegation_id)
    ):
        until = _aware(row.until_utc)
        if until is not None and day == row.gas_day_to and until <= now:
            continue
        if visible is not None and row.book_id not in visible:
            continue
        out.append(Delegation(
            trader=row.trader, book_id=row.book_id, hub=row.hub.upper(), ref=row.line_ref,
            mwh=row.mwh_per_day, trader_name=names.get(row.mandate_id) or row.trader,
            delegation_id=row.delegation_id,
        ))
    return out


# ------------------------------------------------------------------ cut-offs and cost


def cutoffs_for(session, hub: str, day: date, now: datetime) -> list[dict[str, Any]]:
    """The day's cut-offs at the hub: declared windows for its country, else the defaults."""

    from eurogas_nexus.domain.market.hub_cutoffs import default_cutoffs, gas_day_end
    from eurogas_nexus.domain.market.nomination_windows import resolve_window_occurrence
    from eurogas_nexus.domain.ontology.markets import find_market

    market = find_market(hub)
    country = (market.country if market else "") or ""
    held: list[dict[str, Any]] = []
    if country:
        try:
            from eurogas_nexus.db.repositories.storage_nomination import (
                active_nomination_windows,
            )

            for row in active_nomination_windows(session, at_utc=now):
                if str(row.country).upper() != country.upper():
                    continue
                occurrence = resolve_window_occurrence(
                    gas_day=day, opens_at=row.opens_at, closes_at=row.closes_at)
                held.append({"key": "window", "name": row.name,
                             "at_utc": occurrence.closes_at_utc.isoformat(),
                             "basis": "held", "source": row.source_reference})
        except Exception:  # noqa: BLE001 - a malformed window must not lose the row
            held = []
    if held:
        held.append({"key": "gas_day_end", "name": None,
                     "at_utc": gas_day_end(day).isoformat(), "basis": "calendar",
                     "source": "Gas-day calendar"})
        items = held
    else:
        items = [{"key": cut.key, "name": None, "at_utc": cut.at_utc.isoformat(),
                  "basis": cut.basis, "source": cut.source} for cut in default_cutoffs(day)]
    for item in items:
        item["passed"] = datetime.fromisoformat(item["at_utc"]) <= now
    return sorted(items, key=lambda item: item["at_utc"])


def cash_out_assumption(session, books: list[str], hub: str, day: date) -> dict[str, Any] | None:
    """The approved cash-out premium and discount in the hub's currency for the hub's books."""

    from eurogas_nexus.db.repositories.commercial_assumptions import resolve_assumption_version
    from eurogas_nexus.domain.ontology.markets import quote_currency

    currency = quote_currency(hub)
    reasons = []
    for book in [*books, None]:
        try:
            resolved = resolve_assumption_version(session, day=day, book_id=book)
        except Exception:  # noqa: BLE001 - no assumption store: not estimated
            return None
        if resolved is None:
            continue
        _version_id, version = resolved
        short = version.value("balancing.short_premium")
        long_ = version.value("balancing.long_discount")
        if short is None and long_ is None:
            continue
        if any(item is not None and (item.currency or currency) != currency
               for item in (short, long_)):
            reasons.append(f"{version.name} v{version.version} is not in {currency}")
            continue
        return {
            "set": version.name,
            "version": version.version,
            "currency": currency,
            "short_premium": None if short is None else float(short.value),
            "long_discount": None if long_ is None else float(long_.value),
        }
    return {"reasons": reasons} if reasons else None


def cost_of_nothing(net_mwh: float, assumption: dict[str, Any] | None, hub: str) -> dict:
    """The net left open at the assumed cash-out premium (short) or discount (long)."""

    from eurogas_nexus.domain.ontology.markets import quote_currency

    if abs(net_mwh) <= 0.5:
        return {"value": 0.0, "currency": quote_currency(hub), "basis": "balanced"}
    if not assumption or "reasons" in assumption:
        return {"value": None, "currency": quote_currency(hub), "basis": "missing",
                "reason": "; ".join((assumption or {}).get("reasons") or [])
                or "no cash-out premium in the assumption set in force"}
    rate = assumption["long_discount"] if net_mwh > 0 else assumption["short_premium"]
    if rate is None:
        return {"value": None, "currency": assumption["currency"], "basis": "missing",
                "reason": "no cash-out premium in the assumption set in force"}
    return {
        "value": round(abs(net_mwh) * rate, 2),
        "currency": assumption["currency"],
        "rate": rate,
        "rate_unit": f"{assumption['currency']}/MWh",
        "basis": "assumption",
        "side": "long_discount" if net_mwh > 0 else "short_premium",
        "assumption_set": assumption["set"],
        "assumption_version": assumption["version"],
    }


# ------------------------------------------------------------------ the row


def _target(line: GasDayLine) -> dict[str, Any]:
    if line.prompt_trade:
        return {"mode": "desk", "task": "prices", "params": {"hub": line.hub, "view": "prompt"}}
    if line.ref.startswith("contract:"):
        return {"mode": "book", "task": "delivery",
                "params": {"contract": line.ref.split(":", 1)[1]}}
    if line.ref.startswith(("lng:",)) or line.kind.startswith("storage"):
        return {"mode": "book", "task": "planning", "params": {}}
    if line.ref.startswith("trade:"):
        return {"mode": "book", "task": "position", "params": {}}
    return {"mode": "book", "task": "delivery", "params": {}}


def _line_payload(line: GasDayLine, day: date) -> dict[str, Any]:
    return {
        "ref": line.ref,
        "direction": line.direction,
        "kind": line.kind,
        "label": line.label,
        "point": line.point,
        "basis": line.basis,
        "book_id": line.book_id,
        "quantity": native_quantity(line.hub, line.mwh, day),
        "simulated": line.simulated,
        "prompt_trade": line.prompt_trade,
        "target": _target(line),
    }


def _order(line: GasDayLine) -> tuple:
    kinds = IN_KINDS if line.direction == IN else OUT_KINDS
    return (kinds.index(line.kind) if line.kind in kinds else 99, line.prompt_trade, -line.mwh)


def hub_payload(session, balance: HubBalance, day: date, now: datetime,
                book_names: dict[str, str]) -> dict[str, Any]:
    hub = balance.hub
    lines = sorted(balance.lines, key=_order)
    done = [line for line in lines if line.prompt_trade]
    books = sorted({line.book_id for line in lines if line.book_id},
                   key=lambda book: -sum(line.mwh for line in lines if line.book_id == book))
    assumption = cash_out_assumption(session, books, hub, day)
    delegated = [
        {
            "ref": line.ref,
            "label": line.label,
            "direction": line.direction,
            "quantity": native_quantity(hub, mwh, day),
            "trader": item.trader,
            "trader_name": item.trader_name,
            "delegation_id": item.delegation_id,
            "book": book_names.get(item.book_id, item.book_id),
        }
        for line, mwh, item in balance.delegated
    ]
    return {
        "hub": hub,
        "state": balance.state,
        "in": native_quantity(hub, balance.in_mwh, day),
        "out": native_quantity(hub, balance.out_mwh, day),
        "net": native_quantity(hub, balance.net_mwh, day),
        "lines": [_line_payload(line, day) for line in lines],
        "done_today": {
            "trades": sum(int(line.label) for line in done if line.label.isdigit()),
            "bought": native_quantity(hub, sum(x.mwh for x in done if x.direction == IN), day),
            "sold": native_quantity(hub, sum(x.mwh for x in done if x.direction == OUT), day),
            "target": {"mode": "desk", "task": "prices", "params": {"hub": hub,
                                                                     "view": "prompt"}},
        },
        "delegated": delegated,
        "cutoffs": cutoffs_for(session, hub, day, now),
        "cost_of_nothing": cost_of_nothing(balance.net_mwh, assumption, hub),
        "books": [book_names.get(book, book) for book in books],
        "simulated": any(line.simulated for line in lines),
    }


def my_gas_day(session, caller, *, now: datetime, inputs=None) -> dict[str, Any]:
    """The "My gas day" row for this caller: today's and tomorrow's gas day per hub."""

    from eurogas_nexus.domain.market.gas_day import gas_day_label

    today = date.fromisoformat(gas_day_label(now))
    days = [today, today + timedelta(days=1)]
    if inputs is None:
        from eurogas_nexus.application.position_inputs import ladder_inputs

        inputs = ladder_inputs(caller, today, today, days[-1])
    scope = scope_of(session, caller, today)
    contract_ids = [leg.reference for leg in inputs.legs if leg.kind == "physical"]
    dated = [
        *contract_lines(inputs, days, nominations_for(session, contract_ids, days)),
        *trade_lines(inputs, days, today),
        *lng_lines(session, days, scope.visible),
        *schedule_lines(session, days, scope.visible),
    ]
    book_names = {book_id: book.name for book_id, book in (inputs.books or {}).items()}
    out_days = []
    for offset, day in enumerate(days):
        lines = [line for when, line in dated if when == day]
        delegations = delegations_for(session, day, now, scope.visible)
        balances = balance_for(lines, delegations, trader=scope.trader,
                               owned_books=scope.owned_books)
        hubs = [hub_payload(session, balances[hub], day, now, book_names)
                for hub in sorted(balances, key=lambda h: -abs(balances[h].net_mwh))]
        out_days.append({
            "gas_day": day.isoformat(),
            "which": "today" if offset == 0 else "tomorrow",
            "hours": gas_day_hours(day),
            "hubs": hubs,
        })
    populated = any(item["hubs"] for item in out_days)
    simulated = any(hub["simulated"] for item in out_days for hub in item["hubs"])
    return {
        "key": "gas_day",
        "title": "My gas day",
        "scope": scope.payload(),
        "days": out_days,
        "simulated": simulated,
        "populated": populated,
        "empty": None if populated else {
            "code": "no_gas_day_lines",
            "reason": "Nothing to clear today or tomorrow in the books you hold",
            "action": "Deliveries appear once contracts, trades or the schedule are imported",
        },
        "execution": "none: decision support only; nominations and trades are made elsewhere",
    }
