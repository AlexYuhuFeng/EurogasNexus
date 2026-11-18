"""Scheduled reports: a daily or weekly report generated on the worker, delivered to roles.

An administrator keeps the schedules (``PUT /api/reports/schedules``); they live in the
organisation settings (``organisation_settings``, key ``report_schedules``), so no new store
is added. Each schedule names the report (kind, edition, sections, language), the time
(UTC, and the weekday for a weekly one) and the **distribution**: the roles that receive it.

The monitoring worker calls :func:`run_due` about once a minute. A schedule whose latest slot
has passed and has not run for that slot is generated **as the configured service principal**
(never an administrator; with its own data scopes), stored with the trigger
``{"type": "schedule", "schedule_id", "roles", "slot"}`` and:

- **in-app first**: the report appears in the Reports library of every principal in a
  distribution role (and administrators), and only theirs (``store.reader_may_see``);
- **by e-mail** when the schedule asks for it and an administrator has a notification channel
  for the ``report`` category: one outbox row per run (``notifications.queue_notification``),
  carrying the headline and key points, never the document or book figures.

A scheduled report is always **for distribution** (no book sections), so a recipient never
sees positions their own scope would hide. A slot older than :data:`CATCH_UP` is skipped
rather than generated late. Every run, refusal or skip is audited.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

SETTING_KEY = "report_schedules"
KINDS = ("daily", "weekly")
ROLES = ("VIEWER", "REVIEWER", "ANALYST", "OPERATOR", "ADMIN")
#: A slot missed by more than this (the worker was down) is skipped, not generated late.
CATCH_UP = timedelta(hours=6)
MAX_SCHEDULES = 20
_TIME = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


class ScheduleError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def validate_schedule(raw: dict[str, Any], *, now: datetime) -> dict[str, Any]:
    """One schedule from an administrator's input; raises :class:`ScheduleError`."""

    from eurogas_nexus.application.reports.catalogue import PlanError, validate_plan

    kind = str(raw.get("kind") or "daily")
    if kind not in KINDS:
        raise ScheduleError("bad_kind", f"A schedule is daily or weekly, not {kind!r}")
    at = str(raw.get("at_utc") or "06:30")
    if not _TIME.match(at):
        raise ScheduleError("bad_time", f"Time {at!r} is not HH:MM (UTC)")
    weekday = raw.get("weekday", 0)
    if kind == "weekly" and (not isinstance(weekday, int) or not 0 <= weekday <= 6):
        raise ScheduleError("bad_weekday", "A weekly schedule needs a weekday 0 (Monday) to 6")
    roles = [str(r).upper() for r in raw.get("roles") or []]
    if not roles or any(r not in ROLES for r in roles):
        raise ScheduleError("bad_roles", f"Distribution roles must be among {', '.join(ROLES)}")
    language = "zh-CN" if str(raw.get("language") or "en").lower().startswith("zh") else "en"
    plan_raw = {"kind": kind, "audience": "shareable", "variant": raw.get("variant")}
    if raw.get("sections"):
        plan_raw["sections"] = list(raw["sections"])
    try:
        plan = validate_plan(plan_raw, now=now)
    except PlanError as exc:
        raise ScheduleError("bad_plan", str(exc)) from exc
    return {
        "schedule_id": str(raw.get("schedule_id") or uuid.uuid4().hex[:12]),
        "name": str(raw.get("name") or f"{kind.capitalize()} report")[:80],
        "kind": kind,
        "variant": plan.variant,
        "sections": list(plan.sections),
        "language": language,
        "at_utc": at,
        "weekday": weekday if kind == "weekly" else None,
        "roles": sorted(set(roles)),
        "email": bool(raw.get("email")),
        "enabled": raw.get("enabled", True) is not False,
    }


def load(session) -> dict[str, Any]:
    from eurogas_nexus.db.models.settings import OrganisationSettingRecord

    row = session.get(OrganisationSettingRecord, SETTING_KEY)
    value = row.value_json if row is not None and isinstance(row.value_json, dict) else {}
    return {"schedules": list(value.get("schedules") or []),
            "last_slots": dict(value.get("last_slots") or {})}


def save(session, value: dict[str, Any], *, actor: str, now: datetime) -> None:
    from eurogas_nexus.db.models.settings import OrganisationSettingRecord

    row = session.get(OrganisationSettingRecord, SETTING_KEY)
    if row is None:
        row = OrganisationSettingRecord(setting_key=SETTING_KEY, value_json=value,
                                        updated_by=actor[:64], updated_at_utc=now)
        session.add(row)
    else:
        row.value_json = value
        row.updated_by = actor[:64]
        row.updated_at_utc = now


def replace_schedules(session, raws: list[dict[str, Any]], *, actor: str,
                      now: datetime) -> list[dict[str, Any]]:
    """Validate and store the whole list (an administrator's edit); audited by the caller."""

    if len(raws) > MAX_SCHEDULES:
        raise ScheduleError("too_many", f"At most {MAX_SCHEDULES} schedules")
    schedules = [validate_schedule(raw, now=now) for raw in raws]
    ids = [s["schedule_id"] for s in schedules]
    if len(ids) != len(set(ids)):
        raise ScheduleError("duplicate_id", "Two schedules share an id")
    current = load(session)
    # A schedule's last run is kept, so saving does not make a passed slot due again.
    slots = {k: v for k, v in current["last_slots"].items() if k in ids}
    for s in schedules:
        slots.setdefault(s["schedule_id"], latest_slot(s, now).isoformat())
    save(session, {"schedules": schedules, "last_slots": slots}, actor=actor, now=now)
    return schedules


def latest_slot(schedule: dict[str, Any], now: datetime) -> datetime:
    """The newest scheduled instant at or before ``now``."""

    hour, minute = (int(x) for x in schedule["at_utc"].split(":"))
    today: date = now.astimezone(UTC).date()
    slot = datetime.combine(today, time(hour, minute), tzinfo=UTC)
    if schedule["kind"] == "weekly":
        slot -= timedelta(days=(today.weekday() - schedule["weekday"]) % 7)
        if slot > now:
            slot -= timedelta(days=7)
    elif slot > now:
        slot -= timedelta(days=1)
    return slot


def run_due(session, *, now: datetime, caller=None, balance_reader=None) -> list[dict]:
    """Generate every schedule whose latest slot has not run; returns what happened."""

    from eurogas_nexus.application.caller import Caller
    from eurogas_nexus.application.reports.catalogue import PlanError
    from eurogas_nexus.application.reports.engine import ReportRefused, generate_report
    from eurogas_nexus.db.repositories.audit import record_audit_event

    value = load(session)
    outcomes: list[dict] = []
    for schedule in value["schedules"]:
        if not schedule.get("enabled", True):
            continue
        slot = latest_slot(schedule, now)
        last = value["last_slots"].get(schedule["schedule_id"])
        if last and datetime.fromisoformat(last) >= slot:
            continue
        value["last_slots"][schedule["schedule_id"]] = slot.isoformat()
        outcome: dict[str, Any] = {"schedule_id": schedule["schedule_id"],
                                   "slot": slot.isoformat()}
        if now - slot > CATCH_UP:
            outcome["status"] = "skipped_late"
        elif caller is None:
            outcome["status"] = "refused_no_service_principal"
        else:
            plan = {"kind": schedule["kind"], "audience": "shareable",
                    "variant": schedule.get("variant"), "sections": schedule.get("sections")}
            trigger = {"type": "schedule", "schedule_id": schedule["schedule_id"],
                       "roles": schedule["roles"], "slot": slot.isoformat()}
            try:
                report = generate_report(
                    session, caller if isinstance(caller, Caller) else Caller(caller), plan,
                    now=now, language=schedule.get("language", "en"),
                    generated_by_type="SERVICE", trigger=trigger,
                    balance_reader=balance_reader)
            except (PlanError, ReportRefused) as exc:
                session.rollback()
                outcome["status"] = f"refused: {exc}"
            else:
                outcome.update(status="generated", report_id=report.report_id)
                if schedule.get("email"):
                    outcome["email_queued"] = _queue_email(session, schedule, report, now)
        actor = getattr(getattr(caller, "principal", caller), "principal_id", None)
        record_audit_event(session, event_type="report.schedule", principal=actor or "service",
                           action="generate", resource=f"report-schedule:"
                           f"{schedule['schedule_id']}",
                           outcome=outcome["status"].split(":")[0], now_utc=now,
                           detail=f"slot {outcome['slot']}"
                           + (f"; report {outcome['report_id']}" if "report_id" in outcome else ""))
        outcomes.append(outcome)
    if outcomes:
        save(session, value, actor="report-scheduler", now=now)
        session.commit()
    return outcomes


def _queue_email(session, schedule: dict, report, now: datetime) -> bool:
    """One outbox row for the run: headline and key points, never the document."""

    from eurogas_nexus.application.notifications import queue_notification

    snapshot = report.snapshot
    points = [f"- {f['text']}" for f in snapshot.get("findings") or []][:5]
    body = "\n".join([snapshot["headline"], "", *points, "",
                      "Open it in Eurogas Nexus: Research → Reports "
                      f"(report {report.report_id}).",
                      "Decision support only: not advice to trade."])
    return queue_notification(
        session, category="report", severity="info", title=snapshot["title"], body=body,
        dedupe_key=f"report-schedule:{schedule['schedule_id']}:{report.report_id}", now=now)


def recipients_allowed(record, reader) -> bool:
    """A scheduled report reaches its distribution roles (and administrators) only."""

    trigger = record.trigger_json or {}
    if trigger.get("type") != "schedule":
        return True
    principal = reader.principal
    roles = {str(r).upper() for r in (getattr(principal, "roles", ()) or ())} | {
        str(getattr(principal, "role", "") or "").upper()}
    return "ADMIN" in roles or bool(roles & {str(r).upper() for r in trigger.get("roles") or []})


__all__ = ["CATCH_UP", "KINDS", "ROLES", "ScheduleError", "latest_slot", "load",
           "recipients_allowed", "replace_schedules", "run_due", "validate_schedule"]
