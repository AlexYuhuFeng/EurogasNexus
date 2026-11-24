"""The gas day's operational checklist (Today, first for operations): status tracking only.

Per source the caller's gas day holds (``application/gas_day.gas_day_view``, so the same scope
from mandates and books), for today and tomorrow:

- **nomination** of each contract, upstream or scheduled line: its status as recorded (to send,
  sent, confirmed, renominated), by whom and when, and the agent the contract record names
  (``upstream_resource_contracts.nomination_agent``); the expected quantity (the contract's
  daily quantity or the schedule) against the nominated one, and a mismatch beyond the
  contract's nomination tolerance;
- **LNG terminal steps** of each send-out slot the firm holds: the unloading window, the
  send-out nomination, the inventory (only where a status records it) and the slot's end; a
  DES cargo confirmation whose window covers the day is listed with its terminal.

A status comes from, in order: the newest ``gas_day_nomination_events`` row (the scheduling
import, ``origin="import"``, or entered by hand, ``origin="manual"``, labelled and audited);
else the delivery record's nominated quantity (``sent``, as recorded by the import); else
``to_send``. Each open step carries its deadline from the hub's cut-offs; a step due within
:data:`DUE_SOON` or overdue is "needs me" and is queued to the notification outbox by the
worker (:func:`queue_deadline_notifications`). Nothing here nominates (AGENTS.md rule 8).

燃气日操作清单：按来源记录提名状态、偏差与 LNG 码头步骤；仅状态跟踪，不提交提名。
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

STEPS = ("nomination", "renomination", "lng_unloading", "lng_send_out", "lng_inventory")
STATUSES = ("to_send", "sent", "confirmed", "renominated", "mismatch_queried", "done")
OPEN = frozenset({"to_send", "sent", "mismatch_queried"})
#: A step whose deadline is this close (or past) and still open needs someone now.
DUE_SOON = timedelta(hours=3)
DEFAULT_TOLERANCE_PCT = 2.0
#: Lines the firm (or its agent) nominates; a customer's offtake is the customer's to nominate.
NOMINATED_KINDS = frozenset({"supply", "upstream", "sale", "import", "export",
                             "storage_injection", "storage_withdrawal"})


def _aware(moment):
    if moment is None:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def latest_events(session, days: list[date]) -> dict[tuple, Any]:
    """The newest recorded status per (gas day, line, step)."""

    from eurogas_nexus.db.models import GasDayNominationEventRecord

    out: dict[tuple, Any] = {}
    for row in (
        session.query(GasDayNominationEventRecord)
        .filter(GasDayNominationEventRecord.gas_day.in_(days))
        .order_by(GasDayNominationEventRecord.recorded_at_utc,
                  GasDayNominationEventRecord.event_id)
    ):
        out[(row.gas_day, row.line_ref, row.step)] = row
    return out


def _deadline(cutoffs: list[dict], keys: tuple[str, ...]) -> dict | None:
    for key in keys:
        found = next((cut for cut in cutoffs if cut["key"] == key), None)
        if found:
            return found
    held = [cut for cut in cutoffs if cut["key"] == "window"]
    return held[0] if held else None


def _status_payload(event, fallback: str, origin: str) -> dict[str, Any]:
    if event is None:
        return {"status": fallback, "origin": origin, "by": None, "at_utc": None, "note": None}
    return {
        "status": event.status,
        "origin": event.origin,
        "by": event.recorded_by,
        "at_utc": _aware(event.recorded_at_utc).isoformat(),
        "note": event.note,
    }


def _urgency(item: dict, now: datetime) -> str:
    deadline = item.get("deadline")
    if item["status"]["status"] not in OPEN or not deadline:
        return "none"
    at = datetime.fromisoformat(deadline["at_utc"])
    if at <= now:
        return "overdue"
    return "due_soon" if at - now <= DUE_SOON else "open"


def checklist(session, caller, *, now: datetime, view=None, inputs=None) -> dict[str, Any]:
    """The checklist row for this caller (Today ``rows[6]``)."""

    from eurogas_nexus.application.gas_day import cutoffs_for, gas_day_view, native_quantity

    view = view or gas_day_view(session, caller, now=now, inputs=inputs)
    events = latest_events(session, view.days)
    from eurogas_nexus.db.models import ContractDeliveryRecord

    contract_ids = list(view.contracts)
    nominated = {
        (row.contract_id, row.gas_day): row
        for row in session.query(ContractDeliveryRecord)
        .filter(ContractDeliveryRecord.contract_id.in_(contract_ids or [""]))
        .filter(ContractDeliveryRecord.gas_day.in_(view.days))
    }
    out_days = []
    for offset, day in enumerate(view.days):
        items: list[dict[str, Any]] = []
        for hub, balance in sorted(view.balances[day].items()):
            cutoffs = cutoffs_for(session, hub, day, now)
            seen: set[str] = set()
            for line in balance.lines:
                if line.ref in seen:
                    continue
                seen.add(line.ref)
                if line.ref.startswith("lng:"):
                    items += _lng_steps(session, line, day, cutoffs, events, now)
                    continue
                if not line.ref.startswith(("contract:", "schedule:")):
                    continue
                if line.kind not in NOMINATED_KINDS:
                    continue
                items.append(_nomination_item(line, day, cutoffs, events, nominated,
                                              view.contracts, native_quantity))
        items += _cargo_items(view, day)
        for item in items:
            item["urgency"] = _urgency(item, now)
        items.sort(key=lambda item: (
            {"overdue": 0, "due_soon": 1, "open": 3, "none": 4}[item["urgency"]]
            - (1.5 if (item.get("mismatch") or {}).get("over_tolerance") else 0),
            item["hub"], item["label"]))
        out_days.append({"gas_day": day.isoformat(),
                         "which": "today" if offset == 0 else "tomorrow", "items": items})
    populated = any(day["items"] for day in out_days)
    return {
        "key": "checklist",
        "title": "Gas day checklist",
        "scope": view.scope.payload(),
        "days": out_days,
        "statuses": list(STATUSES),
        "populated": populated,
        "empty": None if populated else {
            "code": "no_nominations",
            "reason": "No nominations or terminal steps in the books you hold",
            "action": "Contracts, the schedule and regas slots fill this",
        },
        "execution": "none: statuses are recorded here; nominations are made elsewhere",
    }


def _nomination_item(line, day, cutoffs, events, nominated, contracts, native_quantity):
    contract_id = line.ref.split(":", 1)[1] if line.ref.startswith("contract:") else None
    contract = contracts.get(contract_id) if contract_id else None
    delivery = nominated.get((contract_id, day)) if contract_id else None
    expected = (
        abs(float(contract.delivery_quantity_mwh_per_day)) if contract is not None
        else line.mwh
    )
    renom = events.get((day, line.ref, "renomination"))
    event = renom or events.get((day, line.ref, "nomination"))
    held = (event.quantity_mwh if event is not None and event.quantity_mwh is not None
            else delivery.nominated_mwh if delivery is not None else None)
    if event is not None:
        status = _status_payload(event, "", "")
    elif delivery is not None and delivery.nominated_mwh is not None:
        status = _status_payload(None, "sent", "delivery_record")
        status["at_utc"] = _aware(delivery.updated_at_utc).isoformat()
        status["by"] = delivery.source_system
    else:
        status = _status_payload(None, "to_send", "none")
    tolerance = (float(contract.nomination_tolerance_pct)
                 if contract is not None and contract.nomination_tolerance_pct is not None
                 else DEFAULT_TOLERANCE_PCT)
    mismatch = None
    if held is not None and expected:
        diff = float(held) - expected
        mismatch = {
            "quantity": native_quantity(line.hub, diff, day),
            "pct": round(100.0 * diff / expected, 2),
            "tolerance_pct": tolerance,
            "over_tolerance": abs(diff) > expected * tolerance / 100.0 + 0.5,
        }
    # Still to send: the nomination deadline, passed or not (missed is overdue, though a
    # renomination may still fix it); otherwise the last renomination still ahead.
    if status["status"] == "to_send":
        deadline = _deadline(cutoffs, ("nomination",))
    else:
        deadline = _deadline([cut for cut in cutoffs if not cut["passed"]],
                             ("last_renomination",))
    agent = getattr(contract, "nomination_agent", None) if contract is not None else None
    return {
        "ref": line.ref,
        "hub": line.hub,
        "book_id": line.book_id,
        "step": "renomination" if renom is not None else "nomination",
        "kind": line.kind,
        "label": line.label,
        "point": line.point,
        "agent": agent,
        "expected": native_quantity(line.hub, expected, day),
        "nominated": None if held is None else native_quantity(line.hub, float(held), day),
        "mismatch": mismatch,
        "status": status,
        "deadline": deadline,
        "simulated": line.simulated,
        # An outage at the line's source on the day (source and id), so the row links to it.
        "outages": [{"source": item.source, "id": item.ref, "asset": item.label,
                     "share_out_pct": round(item.share * 100.0, 2)}
                    for item in line.adjustments if item.kind == "outage"],
        "target": {"mode": "book", "task": "delivery",
                   "params": {"contract": contract_id} if contract_id else {}},
    }


def _lng_steps(session, line, day, cutoffs, events, now) -> list[dict[str, Any]]:
    from eurogas_nexus.db.models.lng_positions import RegasSlotRecord
    from eurogas_nexus.domain.market.gas_day import gas_day_start_for_date

    slot = session.get(RegasSlotRecord, line.ref.split(":", 1)[1])
    if slot is None:
        return []
    start, end = _aware(slot.window_start_utc), _aware(slot.window_end_utc)
    open_cuts = [cut for cut in cutoffs if not cut["passed"]]
    base = {"ref": line.ref, "hub": line.hub, "book_id": line.book_id, "kind": "lng",
            "label": line.label, "point": None, "agent": None, "expected": None,
            "nominated": None, "mismatch": None, "simulated": line.simulated,
            "target": {"mode": "book", "task": "planning", "params": {}}}
    steps = []
    unloading = events.get((day, line.ref, "lng_unloading"))
    steps.append({**base, "step": "lng_unloading",
                  "window": {"start_utc": start.isoformat(), "end_utc": end.isoformat()},
                  "status": _status_payload(unloading, "scheduled", "slot"),
                  "deadline": {"key": "slot_start", "name": None, "at_utc": start.isoformat(),
                               "basis": "held", "source": slot.source_reference,
                               "passed": start <= now}
                  if start >= gas_day_start_for_date(day) else None})
    send_out = events.get((day, line.ref, "lng_send_out"))
    # The cargo plan's send-out for the day where the slot holds a cargo (the gas-day line),
    # else the slot's rate.
    rate = (line.mwh if line.basis == "cargo_plan"
            else float(slot.send_out_gwh_d or 0) * 1000.0)
    # Still to send: the nomination cut-off, passed or not (a missed one is overdue, as for a
    # contract's nomination); once sent, the last renomination still ahead.
    to_send = send_out is None or send_out.status == "to_send"
    steps.append({**base, "step": "lng_send_out",
                  "expected": {"value": round(rate, 1), "unit": "MWh/d", "mwh": round(rate, 1),
                               "basis": line.basis, "source_ref": line.source_ref},
                  "status": _status_payload(send_out, "to_send", "none"),
                  "deadline": _deadline(cutoffs, ("nomination",)) if to_send
                  else _deadline(open_cuts, ("last_renomination",))})
    inventory = events.get((day, line.ref, "lng_inventory"))
    steps.append({**base, "step": "lng_inventory",
                  "status": _status_payload(inventory, "not_held", "none"),
                  "quantity": None if inventory is None or inventory.quantity_mwh is None
                  else {"value": inventory.quantity_mwh, "unit": "MWh",
                        "mwh": inventory.quantity_mwh},
                  "deadline": None})
    return steps


def _cargo_items(view, day: date) -> list[dict[str, Any]]:
    """A DES cargo confirmation whose window covers the day, from the contract record."""

    out = []
    for contract in view.contracts.values():
        if getattr(contract, "contract_kind", None) != "LNG_CARGO":
            continue
        terms = getattr(contract, "kind_terms", None) or {}
        if terms.get("delivery_term") != "DES":
            continue
        try:
            first = date.fromisoformat(terms.get("narrowed_start") or terms["window_start"])
            last = date.fromisoformat(terms.get("narrowed_end") or terms["window_end"])
        except (KeyError, TypeError, ValueError):
            continue
        if not first <= day <= last:
            continue
        if view.scope.owned_books is not None and contract.book_id not in view.scope.owned_books:
            continue
        out.append({
            "ref": f"contract:{contract.contract_id}", "hub": terms.get("terminal_hub") or "",
            "book_id": contract.book_id, "step": "lng_cargo_window", "kind": "lng",
            "label": contract.contract_name, "point": terms.get("discharge_terminal"),
            "agent": None, "expected": None, "nominated": None, "mismatch": None,
            "window": {"start": first.isoformat(), "end": last.isoformat()},
            "status": {"status": "confirmed", "origin": "contract", "by": None,
                       "at_utc": None, "note": None},
            "deadline": None, "simulated": False,
            "target": {"mode": "deals", "task": "contracts",
                       "params": {"contract": contract.contract_id}},
        })
    return out


# ------------------------------------------------------------------ write and notify


class ChecklistError(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def record_status(session, caller, *, gas_day: date, line_ref: str, step: str, status: str,
                  quantity_mwh: float | None, note: str | None, now: datetime) -> dict:
    """Record a status by hand for a step the caller's gas day holds; labelled and audited.

    Refused (``ChecklistError``) for a step or status outside the vocabulary, a gas day other
    than today or tomorrow, or a line the caller's scope does not hold. Sends nothing.
    """

    from eurogas_nexus.application.gas_day import gas_day_view
    from eurogas_nexus.db.models import GasDayNominationEventRecord
    from eurogas_nexus.db.repositories.audit import record_audit_event

    if step not in STEPS:
        raise ChecklistError("unknown_step", f"step must be one of {', '.join(STEPS)}")
    if status not in STATUSES:
        raise ChecklistError("unknown_status", f"status must be one of {', '.join(STATUSES)}")
    view = gas_day_view(session, caller, now=now)
    if gas_day not in view.days:
        raise ChecklistError("gas_day_out_of_range", "only today's or tomorrow's gas day")
    line = next((item for balance in view.balances[gas_day].values() for item in balance.lines
                 if item.ref == line_ref), None)
    if line is None:
        raise ChecklistError("line_not_in_scope",
                             "this line is not in the gas day of the books you hold")
    contract = view.contracts.get(line_ref.split(":", 1)[1]) if line_ref.startswith(
        "contract:") else None
    actor = str(getattr(caller.principal, "name", None) or caller.principal_id or "api")
    row = GasDayNominationEventRecord(
        event_id=uuid.uuid4().hex, gas_day=gas_day, line_ref=line_ref, hub=line.hub,
        book_id=line.book_id or None, step=step, status=status, quantity_mwh=quantity_mwh,
        agent=getattr(contract, "nomination_agent", None), origin="manual",
        recorded_by=actor, recorded_at_utc=now, note=note, source_system="manual",
    )
    session.add(row)
    record_audit_event(
        session, event_type="desk.gas_day", principal=actor, action="gas_day.status.record",
        resource=f"{line_ref}:{gas_day.isoformat()}:{step}", outcome=status, severity="info",
        detail=f"entered by hand; quantity={quantity_mwh}; note={(note or '')[:200]}",
    )
    return {"event_id": row.event_id, "status": status, "origin": "manual",
            "recorded_by": actor, "recorded_at_utc": now.isoformat()}


def needs_me_items(row: dict[str, Any]) -> list[dict[str, Any]]:
    """Checklist steps due soon or overdue, or nominated beyond tolerance, for "What needs me"."""

    out = []
    for day in row.get("days") or []:
        for item in day["items"]:
            over = bool((item.get("mismatch") or {}).get("over_tolerance"))
            if item["urgency"] not in {"due_soon", "overdue"} and not over:
                continue
            out.append({
                "kind": "nomination",
                "id": f"{day['gas_day']}:{item['ref']}:{item['step']}",
                "title": item["label"],
                "hub": item["hub"],
                "gas_day": day["gas_day"],
                "step": item["step"],
                "status": item["status"]["status"],
                "urgency": item["urgency"],
                "mismatch": item.get("mismatch") if over else None,
                "deadline_utc": (item.get("deadline") or {}).get("at_utc"),
                "simulated": bool(item.get("simulated")),
                "as_of": None,
                "target": item["target"],
            })
    return out


def queue_deadline_notifications(session, *, now: datetime) -> int:
    """Queue each open step due within ``DUE_SOON`` (or overdue) once, firm-wide.

    Runs in the monitoring worker beside the alert mirror, as a firm caller (every book), so
    the desk hears about a nomination still to send before its cut-off. Dedupe per gas day,
    line, step and deadline, so a step notifies once however often the worker runs.
    """

    from eurogas_nexus.application.caller import firm_caller
    from eurogas_nexus.application.notifications import queue_notification
    from eurogas_nexus.security.portfolio_scope import firm_wide_scope

    with firm_wide_scope():
        row = checklist(session, firm_caller(session=session), now=now)
    queued = 0
    for item in needs_me_items(row):
        if item["urgency"] not in {"due_soon", "overdue"}:
            continue
        queued += queue_notification(
            session,
            category="alert",
            severity="warning" if item["urgency"] == "due_soon" else "high",
            title=f"{item['hub']} {item['title']}: {item['step'].replace('_', ' ')} "
                  f"{item['status'].replace('_', ' ')}",
            body=(f"Gas day {item['gas_day']}, {item['hub']}: {item['title']} - "
                  f"{item['step'].replace('_', ' ')} is {item['status'].replace('_', ' ')}; "
                  f"deadline {item['deadline_utc']}. Recorded in Today's gas day checklist; "
                  "nominations are made in the scheduling system."),
            dedupe_key=f"gasday:{item['id']}:{item['deadline_utc']}",
            now=now,
        )
    return queued
