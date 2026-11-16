"""Stored market reports: written once, listed, reopened, and re-checked for each reader.

A report carries figures its generating principal was entitled to. Reading it later is a new
read of those figures, so :func:`reader_may_see` re-checks the reader: every source system
behind the report must be licensed to the reader (``derived_result_access``), and an
internal report with book figures needs a reader who sees every book behind them. A
shareable report has no book figures by construction. ``rerender`` draws the stored snapshot
again: the same snapshot gives the same HTML, so a stored report can be verified against its
hashes.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from eurogas_nexus.application.caller import Caller


def store_report(session, report, *, caller: Caller, generated_by_type: str,
                 trigger: dict[str, Any], now: datetime) -> None:
    from eurogas_nexus.db.models import MarketReportRecord

    principal = caller.principal
    plan = report.plan
    session.add(
        MarketReportRecord(
            report_id=report.report_id,
            kind=plan.kind,
            variant=plan.variant,
            title=report.snapshot["title"][:256],
            audience=plan.audience,
            headline=report.snapshot["headline"],
            plan_json=plan.as_dict(),
            period_start=plan.period_start,
            period_end=plan.period_end,
            as_of_utc=now,
            snapshot_json=report.snapshot,
            snapshot_sha256=report.snapshot_sha256,
            html=report.html,
            html_sha256=report.html_sha256,
            template_version=report.snapshot["template_version"],
            generated_by=caller.principal_id or "unknown",
            generated_by_type=generated_by_type,
            data_scopes=list(getattr(principal, "data_scopes", ()) or ()),
            source_systems=report.source_systems,
            licensed_families=report.licensed_families,
            book_ids=report.book_ids,
            simulated=bool(report.snapshot["simulated"]),
            model_use=report.snapshot["model_use"],
            trigger_json=trigger,
            created_at_utc=now,
        )
    )
    session.commit()


def reader_may_see(session, record, reader: Caller) -> tuple[bool, str]:
    """Whether ``reader`` may open ``record``; the reason when not."""

    from eurogas_nexus.domain.dataops.entitlement import derived_result_access
    from eurogas_nexus.security import portfolio_scope

    decision = derived_result_access(reader.principal, record.source_systems or [])
    if decision.outcome.value != "ALLOWED":
        return False, "report_contains_unlicensed_source"
    if record.audience == "internal" and record.book_ids:
        scope = portfolio_scope.scope_for_principal(getattr(reader.principal, "data_scopes", ()))
        allowed = portfolio_scope.visible_book_ids(session, scope)
        if allowed is not None and not set(record.book_ids) <= allowed:
            return False, "report_contains_books_outside_scope"
    return True, ""


def list_reports(session, reader: Caller, *, kind: str | None = None, limit: int = 50) -> list:
    from eurogas_nexus.db.models import MarketReportRecord

    query = session.query(MarketReportRecord).order_by(MarketReportRecord.created_at_utc.desc())
    if kind:
        query = query.filter(MarketReportRecord.kind == kind)
    out = []
    for record in query.limit(max(1, min(limit, 200)) * 3):
        if reader_may_see(session, record, reader)[0]:
            out.append(summary(record))
        if len(out) >= limit:
            break
    return out


def summary(record) -> dict[str, Any]:
    created = record.created_at_utc
    if created is not None and created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    return {
        "report_id": record.report_id,
        "kind": record.kind,
        "variant": record.variant,
        "title": record.title,
        "audience": record.audience,
        "headline": record.headline,
        "period_start": record.period_start.isoformat() if record.period_start else None,
        "period_end": record.period_end.isoformat() if record.period_end else None,
        "as_of": _iso(record.as_of_utc),
        "created_at": created.isoformat() if created else None,
        "generated_by_type": record.generated_by_type,
        "simulated": record.simulated,
        "licensed_families": list(record.licensed_families or []),
        "model_use": {k: v for k, v in (record.model_use or {}).items() if k != "sections"},
        "trigger": {k: v for k, v in (record.trigger_json or {}).items()
                    if k in {"type", "alert_id", "outage_id", "schedule"}},
    }


def _iso(value) -> str | None:
    if value is None:
        return None
    return (value.replace(tzinfo=UTC) if value.tzinfo is None else value).isoformat()


def metadata(record) -> dict[str, Any]:
    from eurogas_nexus.application.reports.engine import report_metadata_from

    return {
        **report_metadata_from(record.snapshot_json, record.snapshot_sha256, record.html_sha256),
        "created_at": summary(record)["created_at"],
        "generated_by_type": record.generated_by_type,
        "trigger": summary(record)["trigger"],
    }


def rerender(record) -> str:
    from eurogas_nexus.application.reports.render import render_report

    return render_report(record.snapshot_json)
