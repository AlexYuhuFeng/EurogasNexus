"""A change to one of the firm's cargoes reaches each role that has to act on it (LNG-2).

:class:`CargoChangeConsumer` is a consumer of the market event outbox
(``application/market_events.py``). For each ``cargo.changed`` event it:

1. rebuilds the cargo's plan from the event's payload and the baseline each role was last told
   about (the baseline of the role's open alert, else the last revision this consumer
   processed, else the revision before), so a burst of changes and a change that undoes an
   earlier one are both judged against what the role already knows;
2. derives one message per role (``domain/lng/consequences.py``): the trader's hedge proposal
   with its arithmetic and due time, the scheduler's berth, send-out and the nomination
   cut-offs it hits, risk's exposure by month and the mandates it moves, and the desk head's
   summary only when the change is material by the firm's ``lng.material_change_mwh``
   (approved assumption; the desk standard otherwise, named as such);
3. raises, updates or withdraws one monitoring alert per role (fingerprint
   ``cargo:<id>:<role>``, routed by ``alert_routing``) and queues its notification: once per
   content (dedupe), not again within :data:`COOLDOWN` unless the severity rises or something
   new is in it, and a withdrawal notice when an alert that was notified becomes moot.

Every message ends with how current its inputs are: the ETA's source, basis, confidence and
time, the slot's source and time, who recorded the hedges and when, and the event revision the
plan was rebuilt from. Nothing is traded, nominated or booked; the trader approves.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from eurogas_nexus.application.alert_routing import CARGO_ROLE_CATEGORIES, addressed_line, route_for
from eurogas_nexus.domain.lng.consequences import (
    ROLES,
    CargoFacts,
    MandateCheck,
    MandateMove,
    RoleMessage,
    Threshold,
    derive,
)

CONSUMER_NAME = "cargo_roles"
#: A role is not notified again about the same cargo within this time unless the severity
#: rises or the message holds something it did not (the in-app alert updates regardless).
COOLDOWN = timedelta(minutes=30)
MATERIAL_KEY = "lng.material_change_mwh"
#: Used, and named, when the firm has approved no threshold: about a tenth of a standard
#: cargo (1 TWh), the size at which a desk head expects to hear about one change.
STANDARD_MATERIAL_MWH = 100_000.0
#: Cargo statuses whose plan can still change; any other ends the cargo's open messages.
OPEN_STATUSES = ("loading", "laden", "discharging")
#: The job functions each role's message is for (``security.capabilities``).
ROLE_FUNCTIONS: dict[str, tuple[str, ...]] = {
    "trader": ("TRADER",),
    "scheduler": ("OPERATIONS",),
    "risk": ("RISK_MANAGER",),
    "desk_head": ("MANAGEMENT", "REVIEWER_MANAGEMENT"),
}
ALERT_TYPES = {
    "trader": "cargo_hedge_proposal",
    "scheduler": "cargo_schedule",
    "risk": "cargo_exposure",
    "desk_head": "cargo_material",
}
_WITHDRAWN = {
    "trader": "the plan no longer needs a hedge action that was proposed",
    "scheduler": "berth and send-out are back to what was planned",
    "risk": "exposure by month and the mandates are back where they were",
    "desk_head": "the change is no longer material",
}
_WITHDRAWN_ZH = {
    "trader": "计划已不再需要此前建议的套保调整",
    "scheduler": "靠泊与外输已恢复原计划",
    "risk": "按月敞口与授权已恢复",
    "desk_head": "变化已不再重大",
}
_SEVERITY_RANK = {"info": 0, "warning": 1, "critical": 2}


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def fingerprint(cargo_id: str, role: str) -> str:
    return f"cargo:{cargo_id}:{role}"


def role_of(category: str | None) -> str | None:
    """The cargo role whose alert category this is (``None`` for any other category)."""

    for role, held in CARGO_ROLE_CATEGORIES.items():
        if held == category:
            return role
    return None


def roles_for(job_functions) -> tuple[str, ...]:
    """The cargo roles a person's job functions make theirs; a person who declared none is
    shown the trader's (the default owner of an alert)."""

    held = {str(item).upper() for item in job_functions or ()}
    mine = tuple(role for role in ROLES if held & set(ROLE_FUNCTIONS[role]))
    return mine or ("trader",)


# --------------------------------------------------------------------------- the consumer


class CargoChangeConsumer:
    """Rebuilds a changed cargo's plan and tells each role what it has to do."""

    name = CONSUMER_NAME

    def accepts(self, record) -> bool:
        return record.event_type == "cargo.changed"

    def handle(self, session, records, *, now_utc: datetime) -> dict[str, Any]:
        latest: dict[str, Any] = {}
        for record in records:
            cargo_id = (record.payload_json or {}).get("cargo_id")
            if not cargo_id:
                continue
            held = latest.get(cargo_id)
            if held is None or record.revision > held.revision:
                latest[cargo_id] = record
        results = [react(session, record, now=now_utc) for _, record in sorted(latest.items())]
        return {
            "cargoes": results,
            "notified": any(result.get("queued") for result in results),
        }


def register() -> CargoChangeConsumer:
    """Subscribe the consumer to the outbox (idempotent)."""

    from eurogas_nexus.application import market_events

    try:
        return market_events.consumer(CONSUMER_NAME)  # type: ignore[return-value]
    except KeyError:
        return market_events.register_consumer(CargoChangeConsumer())  # type: ignore[return-value]


# ------------------------------------------------------------------------------- reaction


def _open_alerts(session, cargo_id: str) -> dict[str, Any]:
    from eurogas_nexus.db.models import MonitoringAlertRecord

    rows = (
        session.query(MonitoringAlertRecord)
        .filter(MonitoringAlertRecord.fingerprint.in_([fingerprint(cargo_id, r) for r in ROLES]))
        .all()
    )
    return {role_of(row.category): row for row in rows if row.resolved_at_utc is None}


def _default_baseline(session, record) -> tuple[int, dict[str, Any]] | None:
    """The cargo's state the roles last heard about: the newest revision this consumer
    processed before ``record``, else the revision just before it."""

    from eurogas_nexus.application.market_events import PROCESSED
    from eurogas_nexus.db.models import MarketEventDeliveryRecord, MarketEventRecord

    processed = (
        session.query(MarketEventRecord)
        .join(
            MarketEventDeliveryRecord,
            MarketEventDeliveryRecord.event_seq == MarketEventRecord.seq,
        )
        .filter(MarketEventDeliveryRecord.consumer == CONSUMER_NAME)
        .filter(MarketEventDeliveryRecord.status == PROCESSED)
        .filter(MarketEventRecord.event_key == record.event_key)
        .filter(MarketEventRecord.revision < record.revision)
        .order_by(MarketEventRecord.revision.desc())
        .first()
    )
    if processed is None:
        processed = (
            session.query(MarketEventRecord)
            .filter(MarketEventRecord.event_key == record.event_key)
            .filter(MarketEventRecord.revision == record.revision - 1)
            .first()
        )
    if processed is None:
        return None
    return processed.revision, dict(processed.payload_json or {})


def _instant(text: str | None) -> datetime | None:
    if not text:
        return None
    return _aware(datetime.fromisoformat(text))


def _change_kinds(before: dict[str, Any], after: dict[str, Any]) -> tuple[str, ...]:
    from eurogas_nexus.application.lng_in_transit import _CHANGE_KINDS

    return tuple(name for field, name in _CHANGE_KINDS if before.get(field) != after.get(field))


def _inputs_as_of(session, row, state: dict[str, Any], record, now: datetime) -> dict[str, Any]:
    """How current each input of the rebuilt plan is, in one line and as fields."""

    from eurogas_nexus.application.lng_in_transit import eta_provenance
    from eurogas_nexus.db.models import LngCargoHedgeRecord, RegasSlotRecord

    eta = eta_provenance(row)
    parts = [f"{eta['text']}, stored {_short(eta['recorded_at_utc'])}"]
    slot_info = None
    held_slot = state.get("slot") or {}
    if held_slot.get("slot_id"):
        slot = session.get(RegasSlotRecord, held_slot["slot_id"])
        if slot is not None:
            at = _aware(slot.updated_at_utc)
            slot_info = {"slot_id": slot.slot_id, "source": slot.source_system,
                         "updated_at_utc": None if at is None else at.isoformat()}
            parts.append(f"slot {slot.slot_id} from {slot.source_system}, {_short(at)}")
    else:
        parts.append("no slot linked")
    newest = (
        session.query(LngCargoHedgeRecord)
        .filter(LngCargoHedgeRecord.cargo_id == row.cargo_id)
        .filter(LngCargoHedgeRecord.retired_at_utc.is_(None))
        .order_by(LngCargoHedgeRecord.created_at_utc.desc())
        .first()
    )
    hedges = None
    if newest is not None:
        at = _aware(newest.created_at_utc)
        hedges = {"by": newest.created_by, "at_utc": None if at is None else at.isoformat()}
        parts.append(f"hedges recorded by {newest.created_by}, {_short(at)}")
    else:
        parts.append("no hedges recorded")
    committed = _aware(record.ingested_at_utc)
    parts.append(
        f"plan rebuilt {_short(now)} from cargo.changed revision {record.revision} "
        f"({_short(committed)})"
    )
    return {
        "eta": eta,
        "slot": slot_info,
        "hedges": hedges,
        "event_id": record.event_id,
        "revision": record.revision,
        "event_at_utc": None if committed is None else committed.isoformat(),
        "rebuilt_at_utc": now.isoformat(),
        "line": "Inputs: " + "; ".join(parts) + ".",
    }


def _short(value: Any) -> str:
    if value is None:
        return "time unknown"
    moment = value if isinstance(value, datetime) else _instant(str(value))
    return "time unknown" if moment is None else f"{moment:%d %b %H:%M} UTC"


def _threshold(session, book_id: str, day) -> Threshold:
    try:
        from eurogas_nexus.db.repositories.commercial_assumptions import (
            resolve_assumption_version,
        )

        resolved = resolve_assumption_version(session, day=day, book_id=book_id)
    except Exception:  # noqa: BLE001 - no assumption store: the desk standard, named as such
        resolved = None
    if resolved is not None:
        version_id, version = resolved
        value = version.value(MATERIAL_KEY)
        if value is not None and value.value is not None:
            return Threshold(
                float(value.value), f"approved assumption {MATERIAL_KEY} ({version_id})"
            )
    return Threshold(STANDARD_MATERIAL_MWH, f"desk standard, no approved {MATERIAL_KEY}")


def _cutoffs(session, hub: str | None, now: datetime):
    from eurogas_nexus.application.gas_day import cutoffs_for

    cache: dict[Any, list[dict]] = {}

    def read(day):
        if hub is None:
            return []
        if day not in cache:
            try:
                cache[day] = cutoffs_for(session, hub, day, now)
            except Exception:  # noqa: BLE001 - a day without cut-offs says so in the message
                cache[day] = []
        return cache[day]

    return read


def _cargo_mandate_legs(cargo_id: str, book_id: str, cargo, plan, *, physical: bool,
                        financial: bool) -> list:
    """The cargo's own legs, as the ladder holds them, for one plan: send-out per gas day at
    the hub (physical) and the recorded hedges over their months (financial)."""

    from calendar import monthrange
    from datetime import date

    from eurogas_nexus.domain.risk.limits import MandateLeg

    reference = f"cargo:{cargo_id}"
    legs = []
    hub = cargo.slot.hub if cargo.slot is not None else None
    if physical and hub is not None:
        for label, mwh in plan.send_out:
            day = date.fromisoformat(label)
            legs.append(MandateLeg(reference, "physical", hub, book_id, "", day, day, mwh,
                                   "physical"))
    if financial:
        for leg in cargo.hedges:
            year, month = (int(part) for part in leg.month.split("-"))
            days = monthrange(year, month)[1]
            legs.append(MandateLeg(reference, "financial", leg.hub.upper(), book_id, "",
                                   date(year, month, 1), date(year, month, days),
                                   leg.mwh / days, "future"))
    return legs


def _mandates(session, row, before, after, now: datetime) -> MandateCheck:
    """Every mandate over the cargo's book, with the cargo's legs from the baseline plan and
    from the new one; the rest of the book is the ladder as it stands."""

    from eurogas_nexus.db.models import TraderMandateRecord

    records = session.query(TraderMandateRecord).order_by(TraderMandateRecord.trader).all()
    relevant = [record for record in records if row.book_id in (record.book_ids or [])]
    if not relevant:
        return MandateCheck()
    try:
        from eurogas_nexus.application.caller import firm_caller
        from eurogas_nexus.application.limits_service import (
            books_elsewhere,
            horizon,
            mandate_legs,
            mandate_of,
        )
        from eurogas_nexus.application.position_inputs import ladder_inputs
        from eurogas_nexus.domain.risk.limits import mandate_usage

        today = now.date()
        start, end = horizon(today)
        inputs = ladder_inputs(firm_caller(None, session), today, start, end)
        base = mandate_legs(inputs, today)
        reference = f"cargo:{row.cargo_id}"
        others = [leg for leg in base if leg.reference != reference]
        # A cargo a DES contract on the ladder names keeps that contract's physical; the
        # plan's send-out is then added for neither plan (the ladder's own rule).
        from eurogas_nexus.application.lng_in_transit import _cargo_contract

        physical = _cargo_contract(session, row.cargo_id) is None
        legs_before = others + _cargo_mandate_legs(row.cargo_id, row.book_id, *before,
                                                   physical=physical, financial=True)
        legs_after = others + _cargo_mandate_legs(row.cargo_id, row.book_id, *after,
                                                  physical=physical, financial=True)
        moves = []
        for record in relevant:
            mandate = mandate_of(record)
            elsewhere = books_elsewhere(records, record)
            was = mandate_usage(mandate, legs_before, today=today, books_elsewhere=elsewhere)
            now_usage = mandate_usage(mandate, legs_after, today=today, books_elsewhere=elsewhere)
            was_row, now_row = was.as_row(), now_usage.as_row()
            moves.append(
                MandateMove(
                    mandate_id=record.mandate_id,
                    name=record.display_name or record.trader,
                    status_before=str(was_row["status"]),
                    status_after=str(now_row["status"]),
                    utilisation_before=was_row["utilisation_pct"],
                    utilisation_after=now_row["utilisation_pct"],
                    largest_at=str(now_row["largest_at"] or ""),
                    breaches_after=tuple(now_usage.breaches),
                )
            )
        return MandateCheck(moves=tuple(moves), checked=len(relevant))
    except Exception as exc:  # noqa: BLE001 - said in the risk message, never a silent all-clear
        return MandateCheck(checked=len(relevant), error=f"{type(exc).__name__}")


def react(session, record, *, now: datetime) -> dict[str, Any]:
    """Rebuild one cargo's plan from ``record`` and update each role's alert."""

    from eurogas_nexus.application.lng_in_transit import (
        CargoPlanError,
        eta_provenance,
        plan_of_state,
    )
    from eurogas_nexus.db.models import LngCargoRecord

    moment = _aware(now) or datetime.now(UTC)
    state = dict(record.payload_json or {})
    cargo_id = state.get("cargo_id")
    row = session.get(LngCargoRecord, cargo_id)
    open_alerts = _open_alerts(session, cargo_id)
    result: dict[str, Any] = {"cargo_id": cargo_id, "revision": record.revision, "roles": {}}
    if row is None or row.book_id is None or row.status not in OPEN_STATUSES:
        status = "removed" if row is None else ("out of book" if row.book_id is None
                                                 else row.status)
        for role, alert in open_alerts.items():
            result["queued"] = _withdraw(
                session, alert, role, record, moment,
                reason=f"the cargo is no longer open in the firm's book ({status})",
                reason_zh=f"货物已不在公司账簿中处于未结状态（{status}）",
            ) or result.get("queued", False)
            result["roles"][role] = "withdrawn"
        return result
    try:
        after_cargo, after_plan = plan_of_state(session, cargo_id, state, now=moment)
    except CargoPlanError as exc:
        for alert in open_alerts.values():
            note = f"Plan could not be rebuilt at {_short(moment)}: {exc.message}"
            alert.warnings = list(dict.fromkeys([*(alert.warnings or []), note]))
            alert.updated_at_utc = moment
        session.flush()
        result["error"] = exc.code
        return result

    default = _default_baseline(session, record)
    baselines: dict[str, tuple[int, dict[str, Any]] | None] = {}
    for role in ROLES:
        alert = open_alerts.get(role)
        held = (alert.evidence_snapshot or {}).get("baseline") if alert is not None else None
        baselines[role] = (held["revision"], held["state"]) if held else default
    inputs = _inputs_as_of(session, row, state, record, moment)
    eta = eta_provenance(row)
    threshold = _threshold(session, row.book_id, moment.date())
    hub = after_cargo.slot.hub if after_cargo.slot is not None else None
    derived: dict[int, dict[str, RoleMessage | None]] = {}
    plans: dict[int, Any] = {}
    for role in ROLES:
        baseline = baselines[role]
        if baseline is None:
            result["roles"][role] = "first_recorded"
            continue
        revision, before_state = baseline
        if revision not in derived:
            try:
                before_cargo, before_plan = plan_of_state(
                    session, cargo_id, before_state, now=moment
                )
            except CargoPlanError:
                derived[revision] = {}
                continue
            plans[revision] = before_plan
            facts = CargoFacts(
                cargo_id=cargo_id,
                vessel=row.vessel_name,
                book_id=row.book_id,
                terminal=(state.get("slot") or {}).get("terminal") or row.destination_terminal,
                eta_before_utc=_instant(before_state.get("eta_utc")),
                eta_after_utc=_instant(state.get("eta_utc")),
                change_kinds=_change_kinds(before_state, state),
                eta_basis_text=eta["text"].split("(", 1)[-1].rstrip(")"),
                eta_low_confidence=eta["confidence"] in (None, "low"),
            )
            derived[revision] = derive(
                facts,
                before_plan,
                after_plan,
                now=moment,
                cutoffs_for=_cutoffs(session, hub or (before_cargo.slot.hub
                                                      if before_cargo.slot else None), moment),
                mandates=_mandates(session, row, (before_cargo, before_plan),
                                   (after_cargo, after_plan), moment),
                threshold=threshold,
            )
        message = derived[revision].get(role)
        alert = open_alerts.get(role)
        if message is None:
            if alert is not None:
                result["queued"] = _withdraw(
                    session, alert, role, record, moment, reason=_WITHDRAWN[role],
                    reason_zh=_WITHDRAWN_ZH[role],
                ) or result.get("queued", False)
                result["roles"][role] = "withdrawn"
            else:
                result["roles"][role] = "nothing"
            continue
        outcome, queued = _raise(session, row, role, message, alert, baseline, inputs, record,
                                 moment, threshold)
        result["roles"][role] = outcome
        result["queued"] = queued or result.get("queued", False)
    session.flush()
    return result


def _body(message: RoleMessage, inputs: dict[str, Any], role: str) -> str:
    route = route_for(CARGO_ROLE_CATEGORIES[role])
    return "\n".join([*message.lines_en, "", inputs["line"], "", addressed_line(route)])


def _raise(session, row, role: str, message: RoleMessage, alert, baseline, inputs, record,
           now: datetime, threshold: Threshold) -> tuple[str, bool]:
    from eurogas_nexus.application.notifications import queue_notification
    from eurogas_nexus.db.repositories.monitoring import upsert_monitoring_alert
    from eurogas_nexus.domain.monitoring import MonitoringCandidate

    held = dict(alert.evidence_snapshot or {}) if alert is not None else {}
    notified = held.get("notified")
    category = CARGO_ROLE_CATEGORIES[role]
    route = route_for(category)
    evidence = {
        "cargo_id": row.cargo_id,
        "vessel": row.vessel_name,
        "role": role,
        "for": list(ROLE_FUNCTIONS[role]),
        "book_ids": [row.book_id],
        "baseline": {"revision": baseline[0], "state": baseline[1]},
        "message": message.as_dict(),
        "inputs_as_of": inputs,
        "threshold": {"mwh": threshold.mwh, "source": threshold.source},
        "notified": notified,
        "advisory": "For a person to decide; nothing is traded, nominated or booked.",
    }
    decision = "notified"
    if notified and notified.get("digest") == message.digest:
        decision = "duplicate"
    elif notified and (
        now - (_instant(notified.get("at_utc")) or now) < COOLDOWN
        and _SEVERITY_RANK.get(message.severity, 0)
        <= _SEVERITY_RANK.get(str(notified.get("severity")), 0)
        and set(message.keys) <= set(notified.get("keys") or [])
    ):
        decision = "cooldown"
    queued = False
    if decision == "notified":
        queued = queue_notification(
            session,
            category=route.notification_category,
            severity=message.severity,
            title=message.title_en,
            body=_body(message, inputs, role),
            dedupe_key=f"cargo:{row.cargo_id}:{role}:{message.digest}",
            now=now,
        )
        evidence["notified"] = {
            "digest": message.digest,
            "at_utc": now.isoformat(),
            "severity": message.severity,
            "keys": list(message.keys),
            "revision": record.revision,
            "category": route.notification_category,
        }
    else:
        evidence["held_back"] = {"reason": decision, "at_utc": now.isoformat(),
                                 "revision": record.revision}
    candidate = MonitoringCandidate(
        fingerprint=fingerprint(row.cargo_id, role),
        category=category,
        alert_type=ALERT_TYPES[role],
        severity=message.severity,
        title_en=message.title_en,
        title_zh_cn=message.title_zh,
        message_en=" ".join(message.lines_en) + " " + inputs["line"],
        message_zh_cn="".join(message.lines_zh),
        entity_type="lng_cargo",
        entity_id=row.cargo_id,
        event_time_utc=_aware(record.ingested_at_utc) or now,
        evidence_snapshot=evidence,
        source_refs=[f"cargo:{row.cargo_id}", f"market_event:{record.event_id}"],
        warnings=[],
        simulated=str(row.source_system or "").endswith("_Sim"),
        human_review_required=True,
    )
    upsert_monitoring_alert(session, candidate, now_utc=now)
    return decision, queued


def _withdraw(
    session, alert, role: str, record, now: datetime, *, reason: str, reason_zh: str
) -> bool:
    """Resolve a role's alert that a later change made moot; tell the role if it was told."""

    from eurogas_nexus.application.notifications import queue_notification

    evidence = dict(alert.evidence_snapshot or {})
    evidence["withdrawn"] = {"reason": reason, "reason_zh": reason_zh,
                             "at_utc": now.isoformat(), "revision": record.revision}
    alert.evidence_snapshot = evidence
    alert.status = "resolved"
    alert.resolved_at_utc = now
    alert.updated_at_utc = now
    alert.message_en = f"Withdrawn: {reason}. Was: {alert.title_en}."
    alert.message_zh_cn = f"已撤回：{reason_zh}。原为：{alert.title_zh_cn}。"
    session.flush()
    notified = evidence.get("notified")
    if not notified:
        return False
    route = route_for(alert.category)
    return queue_notification(
        session,
        category=route.notification_category,
        severity=str(notified.get("severity") or alert.severity),
        title=f"Withdrawn: {alert.title_en}"[:256],
        body=(
            f"Withdrawn at {_short(now)} after cargo.changed revision {record.revision}: "
            f"{reason}. Nothing further is needed for what was sent before.\n\n"
            f"{addressed_line(route)}"
        ),
        dedupe_key=f"cargo:{alert.entity_id}:{role}:withdrawn:{notified.get('digest')}",
        now=now,
    )


# ------------------------------------------------------------------------------ readers


def open_messages(session, *, cargo_id: str | None = None, include_withdrawn_since=None,
                  visible=None) -> list[dict[str, Any]]:
    """The cargo role alerts a reader may see, open (and withdrawn since a time, if asked),
    each as the role, its message and how current its inputs are."""

    from eurogas_nexus.db.models import MonitoringAlertRecord

    query = session.query(MonitoringAlertRecord).filter(
        MonitoringAlertRecord.category.in_(sorted(CARGO_ROLE_CATEGORIES.values()))
    )
    if cargo_id is not None:
        query = query.filter(MonitoringAlertRecord.entity_id == cargo_id)
    out = []
    since = _aware(include_withdrawn_since)
    for row in query.order_by(MonitoringAlertRecord.updated_at_utc.desc()).limit(500):
        if row.resolved_at_utc is not None and (
            since is None or (_aware(row.resolved_at_utc) or since) < since
        ):
            continue
        if visible is not None and not visible(row):
            continue
        evidence = row.evidence_snapshot or {}
        message = evidence.get("message") or {}
        withdrawn = evidence.get("withdrawn")
        out.append(
            {
                "alert_id": row.alert_id,
                "cargo_id": row.entity_id,
                "role": role_of(row.category),
                "category": row.category,
                "for": evidence.get("for") or [],
                "status": "withdrawn" if row.resolved_at_utc is not None else row.status,
                "severity": row.severity,
                "title": row.title_en,
                "title_zh": row.title_zh_cn,
                "lines": message.get("lines_en") or [],
                "lines_zh": message.get("lines_zh") or [],
                "items": message.get("items") or [],
                "due_utc": message.get("due_utc"),
                "inputs_as_of": evidence.get("inputs_as_of"),
                "withdrawn": withdrawn,
                "notified_at_utc": (evidence.get("notified") or {}).get("at_utc"),
                "updated_at_utc": (_aware(row.updated_at_utc) or datetime.now(UTC)).isoformat(),
                "simulated": bool(row.simulated),
            }
        )
    return out


def messages_for_reader(session, *, cargo_id: str | None = None, withdrawn_since=None
                        ) -> list[dict[str, Any]]:
    """:func:`open_messages` as the current request's caller may see them (the cargo's book),
    each marked ``mine`` when it is for one of the caller's job functions."""

    from eurogas_nexus.application.alert_scope import alert_visibility, request_principal

    principal = request_principal()
    mine = set(roles_for(getattr(principal, "job_functions", ()) or ()))
    rows = open_messages(session, cargo_id=cargo_id, include_withdrawn_since=withdrawn_since,
                         visible=alert_visibility(session))
    for row in rows:
        row["mine"] = row["role"] in mine
    return rows


def needs_me_items(session, job_functions, *, now: datetime) -> list[dict[str, Any]]:
    """Today's "What needs me" items: the open cargo messages for the caller's roles, the
    most severe and the soonest due first."""

    roles = set(roles_for(job_functions))
    rows = [row for row in messages_for_reader(session) if row["role"] in roles]
    rows.sort(key=lambda row: (row["severity"] != "critical", row["due_utc"] or "9999"))
    return [
        {
            "kind": "cargo",
            "id": row["alert_id"],
            "title": row["title"],
            "title_zh": row["title_zh"],
            "role": row["role"],
            "status": "breach" if row["severity"] == "critical" else "watch",
            "simulated": row["simulated"],
            "as_of": (row.get("inputs_as_of") or {}).get("rebuilt_at_utc"),
            "since_utc": (row.get("inputs_as_of") or {}).get("event_at_utc"),
            "deadline_utc": row["due_utc"],
            "cargo_id": row["cargo_id"],
            "target": {"mode": "desk", "task": "cargoes", "params": {"cargo": row["cargo_id"]}},
            "why": {"subject": "alert", "id": row["alert_id"]},
        }
        for row in rows
    ]


__all__ = [
    "COOLDOWN",
    "CONSUMER_NAME",
    "CargoChangeConsumer",
    "MATERIAL_KEY",
    "ROLE_FUNCTIONS",
    "STANDARD_MATERIAL_MWH",
    "fingerprint",
    "messages_for_reader",
    "needs_me_items",
    "open_messages",
    "react",
    "register",
    "role_of",
    "roles_for",
]
