"""Assemble a market report from a validated plan, as the caller it runs for, and record it.

1. The plan is validated against the catalogue (``catalogue.validate_plan``).
2. The caller's book scope is applied for the whole build (a scheduled report runs as its
   declared service principal, so its scope is that principal's, never an administrator's).
3. Each section is read through its adapter (``sections.BUILDERS``); a failing section
   becomes an omitted one with the reason, never a lost report.
4. Audience and licences: a ``shareable`` report never gathers a book section, and a report
   that read a licensed source is ``internal`` unless every such source's licence allows
   redistribution (``market_data_licences.redistribution_allowed``); otherwise generating it
   as shareable is refused with the sections that carry the licensed data.
5. Optionally the model rewords each section's commentary under the checked-note path
   (``rewrite.py``); a refused rewrite leaves the rule text.
6. The snapshot (everything the HTML is drawn from) is hashed, rendered and stored once.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from eurogas_nexus.application.caller import Caller
from eurogas_nexus.application.reports.catalogue import (
    SECTION_BY_KEY,
    TEMPLATE_VERSION,
    ReportPlan,
    validate_plan,
)
from eurogas_nexus.application.reports.render import render_report
from eurogas_nexus.application.reports.sections import BUILDERS, Ctx, zone_hubs

#: The order sections feed the Key points box (market first, book last).
KEY_POINT_ORDER = ("situation_event", "prices", "balance", "storage", "pipeline_supply",
                   "outages", "lng", "power_burn", "alerts", "book_position", "book_pnl",
                   "book_limits", "book_contracts")
KIND_LABELS = {"daily": "Daily", "weekly": "Weekly", "monthly": "Monthly",
               "situation": "Situation report", "ask": "Asked report"}


class ReportRefused(Exception):
    """The report cannot be generated as asked; ``code`` and ``detail`` say why."""

    def __init__(self, code: str, message: str, detail: dict | None = None):
        super().__init__(message)
        self.code = code
        self.detail = detail or {}


@dataclass
class GeneratedReport:
    report_id: str
    plan: ReportPlan
    snapshot: dict[str, Any]
    html: str
    snapshot_sha256: str
    html_sha256: str
    source_systems: list[str] = field(default_factory=list)
    licensed_families: list[str] = field(default_factory=list)
    book_ids: list[str] = field(default_factory=list)

    def metadata(self) -> dict[str, Any]:
        return report_metadata_from(self.snapshot, self.snapshot_sha256, self.html_sha256)


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
                      default=str)


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@contextmanager
def book_scope_of(caller: Caller):
    """The caller's book scope for the duration of the build (restored afterwards)."""

    from eurogas_nexus.security import portfolio_scope

    token = portfolio_scope._current.set(
        portfolio_scope.scope_for_principal(getattr(caller.principal, "data_scopes", ()))
    )
    try:
        yield
    finally:
        portfolio_scope._current.reset(token)


def redistributable_families(session, families: set[str], today) -> set[str]:
    """Families whose current licence allows redistribution of derived figures."""

    from eurogas_nexus.db.models import MarketDataLicenceRecord

    allowed: set[str] = set()
    if not families:
        return allowed
    for row in session.query(MarketDataLicenceRecord).filter(
        MarketDataLicenceRecord.source_family.in_(sorted(families))
    ):
        current = row.valid_from <= today and (row.valid_to is None or row.valid_to >= today)
        if current and bool(getattr(row, "redistribution_allowed", False)):
            allowed.add(row.source_family)
    return allowed


def _title(plan: ReportPlan, now: datetime) -> str:
    from eurogas_nexus.application.reports.lang import zh

    if zh():
        d = f"{now.year}年{now.month}月{now.day}日"
        if plan.kind == "daily":
            return f"西北欧天然气{'晨报' if plan.variant == 'morning' else '收盘报告'}，{d}"
        if plan.kind == "weekly":
            return (f"西北欧天然气周报，{plan.period_start.month}月{plan.period_start.day}日至"
                    f"{plan.period_end.year}年{plan.period_end.month}月{plan.period_end.day}日")
        if plan.kind == "monthly":
            return f"西北欧天然气月报，{plan.period_start.year}年{plan.period_start.month}月"
        if plan.kind == "situation":
            return f"事件报告，{d} {now:%H:%M} UTC"
        return f"专题报告，{d}"
    if plan.kind == "daily":
        word = "morning report" if plan.variant == "morning" else "end-of-day report"
        return f"NW Europe gas {word}, {now:%a %d %b %Y}"
    if plan.kind == "weekly":
        return (f"NW Europe gas weekly, {plan.period_start:%d %b} to "
                f"{plan.period_end:%d %b %Y}")
    if plan.kind == "monthly":
        return f"NW Europe gas monthly, {plan.period_start:%B %Y}"
    if plan.kind == "situation":
        return f"Situation report, {now:%d %b %Y %H:%M} UTC"
    return f"Asked report, {now:%d %b %Y}"


def _generate_report(
    session,
    caller: Caller,
    raw_plan: dict[str, Any] | ReportPlan,
    *,
    now: datetime | None = None,
    model=None,
    editor=None,
    language: str = "en",
    generated_by_type: str = "USER",
    trigger: dict[str, Any] | None = None,
    store: bool = True,
    balance_reader=None,
) -> GeneratedReport:
    """Build, render and (by default) store one report. Raises ``PlanError``/``ReportRefused``."""

    now = (now or datetime.now(UTC)).astimezone(UTC)
    plan = raw_plan if isinstance(raw_plan, ReportPlan) else validate_plan(raw_plan, now=now)
    previous = _previous_as_of(session, plan, caller, now)
    ctx = Ctx(session=session, caller=caller, now=now, plan=plan, previous_as_of=previous,
              balance_reader=balance_reader)
    omitted: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    raws: dict[str, Any] = {}
    with book_scope_of(caller):
        from eurogas_nexus.security.portfolio_scope import visible_book_ids

        books_visible = visible_book_ids(session)
        if plan.kind == "situation" and not plan.hubs and plan.outage_id:
            from eurogas_nexus.application.reports.sections import find_outage

            row = find_outage(ctx, plan.outage_id)
            if row is not None:
                plan.hubs = zone_hubs(row.get("balancing_zone"))
        for key in plan.sections:
            stype = SECTION_BY_KEY[key]
            if stype.internal_only:
                if plan.audience != "internal":  # validate_plan already removed them
                    continue
                if books_visible is not None and not books_visible:
                    omitted.append({"key": key, "title": stype.title,
                                    "reason": "the generating principal may see no book",
                                    "action": "Ask for a BOOKS scope"})
                    continue
            try:
                built = BUILDERS[key](ctx)
                from eurogas_nexus.application.reports.derive import derive

                derive(built, ctx)
                raws[key] = built.raw
                result = built.as_dict()
            except Exception as exc:  # noqa: BLE001 - one failing read must not lose the report
                omitted.append({"key": key, "title": stype.title,
                                "reason": f"not available ({exc.__class__.__name__})",
                                "action": None})
                continue
            if result["status"] == "empty":
                omitted.append({"key": key, "title": stype.title,
                                "reason": result["empty"]["reason"],
                                "action": result["empty"]["action"]})
            results.append(result)
    source_systems = sorted({
        item["source_system"]
        for section in results if section["status"] == "ok"
        for item in section["evidence"]["sources"] if item.get("source_system")
    })
    licensed: dict[str, list[str]] = {}
    for section in results:
        if section["status"] != "ok":
            continue
        for item in section["evidence"]["sources"]:
            if item.get("licensed"):
                licensed.setdefault(item["family"] or item["source_system"], []).append(
                    section["title"])
    if plan.audience == "shareable" and licensed:
        allowed = redistributable_families(session, set(licensed), now.date())
        blocked = {family: titles for family, titles in licensed.items() if family not in allowed}
        if blocked:
            raise ReportRefused(
                "licensed_data_not_redistributable",
                "This report contains licensed data that may not leave the firm: "
                + "; ".join(f"{family} in {', '.join(sorted(set(titles)))}"
                            for family, titles in sorted(blocked.items()))
                + ". Generate it for the internal audience or remove those sections.",
                {"families": sorted(blocked),
                 "sections": sorted({t for titles in blocked.values() for t in titles})},
            )
    model_use: dict[str, Any] = {"attempted": 0, "passed": 0, "sections": {}}
    if model is not None and editor is None:
        from eurogas_nexus.application.reports.rewrite import rewrite_sections

        model_use = rewrite_sections(results, model, language=language)
    shown = [s for s in results if s["status"] == "ok"]
    from eurogas_nexus.application.reports import answer as asked
    from eurogas_nexus.application.reports import findings as page_one

    question_info = None
    if plan.kind == "ask" and plan.question:
        from eurogas_nexus.application.reports.plan import _not_held

        # The question's own facts (joins and engine-declared relations) and what the data
        # cannot tell, before the facts are numbered.
        question_info = asked.build(plan, results, raws, today=ctx.today,
                                    missing=_not_held(plan.question), ctx=ctx)
    sheet = page_one.assign_ids(results)
    editorial = page_one.rule_plan(sheet, results)
    if question_info is not None:
        editorial["answer"] = asked.rule_answer(sheet, question_info, plan)
        editorial["cannot_tell"] = question_info["cannot_tell"]
        editorial["sections"] = [
            {"key": key} for key in asked.relevance_order(
                sheet, editorial["answer"], [s["key"] for s in shown])]
    if plan.kind == "situation":
        # A situation report leads with the event whatever the other facts weigh.
        event = [f for f in sheet if f["section"] == "situation_event"]
        if event:
            editorial["findings"] = [{"fact_ids": [event[0]["id"]], "text": event[0]["sentence"],
                                      "implication": None, "why": "the report's subject",
                                      "score": event[0]["score"]}] + [
                x for x in editorial["findings"] if event[0]["id"] not in x["fact_ids"]][:4]
            editorial["headline"] = event[0]["sentence"]
    editorial["record"] = {"basis": "rule", "model": None, "directive": None, "elements": {}}
    if editor is not None:
        from eurogas_nexus.application.reports.editor import edit_report

        editorial = edit_report(editor, sheet, results, editorial, plan, language=language)
        elements = editorial["record"].get("elements") or {}
        model_use = {"attempted": len(elements),
                     "passed": sum(1 for v in elements.values() if v.get("ok")),
                     "sections": {}, "editor": True}
    headline = editorial["headline"]
    key_points = [x["text"] for x in editorial["findings"]]
    report_id = f"mr-{uuid.uuid4().hex[:20]}"
    book_ids = sorted({b for s in shown for b in s.get("books") or []})
    principal = caller.principal
    snapshot = {
        "report_id": report_id,
        "title": _title(plan, now),
        "kind": plan.kind,
        "kind_label": KIND_LABELS[plan.kind] + (f" ({plan.variant})" if plan.variant else ""),
        "variant": plan.variant,
        "audience": plan.audience,
        "question": plan.question,
        "plan": plan.as_dict(),
        "period": {"start": plan.period_start.isoformat() if plan.period_start else None,
                   "end": plan.period_end.isoformat() if plan.period_end else None},
        "as_of": now.isoformat(),
        "generated_at": now.isoformat(),
        "generated_by": getattr(principal, "name", None) or caller.principal_id or "unknown",
        "headline": headline,
        "key_points": key_points,
        "standfirst": editorial["standfirst"],
        "findings": editorial["findings"],
        "glance": page_one.glance_rows(sheet, editorial.get("glance")),
        "watch": editorial["watch"],
        "answer": editorial.get("answer"),
        "cannot_tell": (question_info or {}).get("cannot_tell") or [],
        "editorial": editorial["record"],
        "dropped": editorial.get("dropped", []),
        "section_order": [x["key"] for x in editorial.get("sections", [])],
        "fact_sheet": sheet,
        "issue": _issue_number(session, plan),
        "sections": results,
        "omitted": omitted + list(editorial.get("dropped") or [])
        + [{"key": "", "title": "Our book", "reason": note, "action": None}
                              for note in plan.notes],
        "simulated": any(s["simulated"] for s in shown),
        "licensed": {"sources": sorted(licensed)},
        "previous_report_as_of": previous.isoformat() if previous else None,
        "model_use": model_use,
        "template_version": TEMPLATE_VERSION,
        "language": language,
    }
    html = render_report(snapshot)
    snapshot_hash = sha256(canonical_json(snapshot))
    report = GeneratedReport(
        report_id=report_id, plan=plan, snapshot=snapshot, html=html,
        snapshot_sha256=snapshot_hash, html_sha256=sha256(html),
        source_systems=source_systems, licensed_families=sorted(licensed), book_ids=book_ids,
    )
    if store:
        from eurogas_nexus.application.reports.store import store_report

        store_report(session, report, caller=caller, generated_by_type=generated_by_type,
                     trigger=trigger or {"type": "user"}, now=now)
    return report


def generate_report(session, caller: Caller, raw_plan: dict[str, Any] | ReportPlan, *,
                    language: str = "en", **kwargs) -> GeneratedReport:
    """Build, render and (by default) store one report in ``language`` (English or Chinese:
    every rule-written sentence, label and table head follows it). Raises ``PlanError`` or
    ``ReportRefused``."""

    from eurogas_nexus.application.reports.lang import writing

    if isinstance(raw_plan, dict) and raw_plan.get("language"):
        language = str(raw_plan["language"])
    with writing(language):
        return _generate_report(session, caller, raw_plan, language=language, **kwargs)


def _issue_number(session, plan: ReportPlan) -> int:
    """A stable sequence per report kind: the stored reports of this kind, plus one."""

    from sqlalchemy import func
    from sqlalchemy.exc import SQLAlchemyError

    from eurogas_nexus.db.models import MarketReportRecord

    try:
        count = (session.query(func.count(MarketReportRecord.report_id))
                 .filter(MarketReportRecord.kind == plan.kind).scalar())
    except SQLAlchemyError:
        session.rollback()
        return 1
    return int(count or 0) + 1


def _previous_as_of(session, plan: ReportPlan, caller: Caller, now: datetime):
    """The data instant of the previous stored report of this kind (for revisions)."""

    from sqlalchemy.exc import SQLAlchemyError

    from eurogas_nexus.db.models import MarketReportRecord

    try:
        row = (
            session.query(MarketReportRecord.as_of_utc)
            .filter(MarketReportRecord.kind == plan.kind,
                    MarketReportRecord.as_of_utc < (now.replace(tzinfo=None)
                                                    if session.get_bind().dialect.name ==
                                                    "sqlite" else now))
            .order_by(MarketReportRecord.as_of_utc.desc())
            .first()
        )
    except SQLAlchemyError:
        session.rollback()
        return None
    if row is None:
        return None
    moment = row[0]
    return moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment


def report_metadata_from(snapshot: dict, snapshot_hash: str, html_hash: str) -> dict[str, Any]:
    return {
        "report_id": snapshot["report_id"],
        "title": snapshot["title"],
        "kind": snapshot["kind"],
        "variant": snapshot.get("variant"),
        "audience": snapshot["audience"],
        "headline": snapshot["headline"],
        "key_points": snapshot["key_points"],
        "period": snapshot["period"],
        "as_of": snapshot["as_of"],
        "question": snapshot.get("question"),
        "plan": snapshot["plan"],
        "sections": [
            {"key": s["key"], "title": s["title"], "status": s["status"],
             "commentary_basis": s["commentary"].get("basis", "rule"),
             "simulated": s["simulated"], "forecast": s["forecast"]}
            for s in snapshot["sections"]
        ],
        "omitted": snapshot["omitted"],
        "standfirst": snapshot.get("standfirst"),
        "answer": snapshot.get("answer"),
        "findings": snapshot.get("findings") or [],
        "editorial": {k: v for k, v in (snapshot.get("editorial") or {}).items()
                      if k != "plan"},
        "editorial_plan": (snapshot.get("editorial") or {}).get("plan"),
        "issue": snapshot.get("issue"),
        "simulated": snapshot["simulated"],
        "licensed": snapshot["licensed"],
        "model_use": snapshot["model_use"],
        "template_version": snapshot["template_version"],
        "snapshot_sha256": snapshot_hash,
        "html_sha256": html_hash,
    }
