"""Morning brief and end-of-day report drafts for a desk to edit and send.

Every desk writes these by hand: what moved, what is out, where the book stands, what is
near a limit. The draft is built from the same evidence the pages show, in fixed sections
with their sources, so it is right without the model. When the caller may use the model,
it adds a lead of at most three sentences on top, checked like every other note
(``ai_style``): only the given facts, only the given sources, no new numbers. Nothing is
sent from here; a person edits the text and sends it through the firm's own mail.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from eurogas_nexus.application.caller import Caller
from eurogas_nexus.application.desk_text import money

KINDS = ("morning", "eod")
MAX_LINES = 6


@dataclass
class Section:
    key: str
    heading: str
    lines: list[str]
    sources: list[str] = field(default_factory=list)


@dataclass
class Brief:
    kind: str
    title: str
    lead: str | None
    lead_basis: str  # "model", or "none" when no lead was written
    sections: list[Section]
    text: str
    simulated: bool
    warnings: list[str]
    as_of: str

    def as_dict(self) -> dict[str, Any]:
        data = dict(self.__dict__)
        data["sections"] = [section.__dict__ for section in self.sections]
        return data


def build_brief(
    session,
    caller: Caller,
    kind: str = "morning",
    *,
    now: datetime | None = None,
    model=None,
    language: str = "en",
) -> Brief:
    """A brief from the caller's own view of the desk."""

    if kind not in KINDS:
        raise ValueError(kind)
    now = now or datetime.now(UTC)
    warnings: list[str] = []
    simulated = False
    sections: list[Section] = []
    for build in (_alerts, _outages, _prices, _positions, _limits, _pnl):
        try:
            section, demo = build(session, caller, now, kind)
        except Exception as exc:  # noqa: BLE001 - one missing section must not lose the brief
            name = build.__name__.strip("_")
            warnings.append(f"{name}: not available ({exc.__class__.__name__})")
            continue
        simulated = simulated or demo
        if section is not None and section.lines:
            sections.append(section)
    if simulated:
        warnings.insert(0, "DEMO: figures use simulated demo prices, not market prices.")
    title = (
        f"Gas desk morning brief, {now:%a %d %b %Y}"
        if kind == "morning"
        else f"Gas desk end of day, {now:%a %d %b %Y}"
    )
    lead = _lead(model, kind, sections, simulated, language) if model and sections else None
    return Brief(
        kind=kind,
        title=title,
        lead=lead,
        lead_basis="model" if lead else "none",
        sections=sections,
        text=_as_text(title, lead, sections, simulated),
        simulated=simulated,
        warnings=warnings,
        as_of=now.isoformat(),
    )


def _as_text(title: str, lead: str | None, sections: list[Section], simulated: bool) -> str:
    out = [title, ""]
    if simulated:
        out += ["Demo figures: simulated prices, not market prices.", ""]
    if lead:
        out += [lead, ""]
    for section in sections:
        out.append(section.heading.upper())
        out += [f"- {line}" for line in section.lines]
        out.append("")
    if not sections:
        out.append("Nothing to report from the desk's data.")
    return "\n".join(out).rstrip() + "\n"


def _lead(model, kind: str, sections: list[Section], simulated: bool, language: str):
    from eurogas_nexus.application.ai_style import checked_note, note_messages

    facts = {
        "brief": kind,
        "sections": {section.heading: section.lines for section in sections},
        "sources": sorted({source for s in sections for source in s.sources}),
        "simulated_inputs": simulated,
    }
    task = (
        "Write the lead of the desk's "
        + ("morning brief: what matters for today's trading" if kind == "morning" else
           "end-of-day report: what changed today and what carries into tomorrow")
        + ", picking the two or three most important facts."
        + (" Say that the figures use simulated demo prices." if simulated else "")
    )
    content = model(note_messages(task, facts, language=language))
    note = checked_note(
        content,
        evidence_text=json.dumps(facts, ensure_ascii=False),
        sources=facts["sources"],
    )
    return note.text if note else None


# ---------------------------------------------------------------------------- sections


def _alerts(session, caller, now, kind):
    from eurogas_nexus.application.alert_scope import alert_visibility
    from eurogas_nexus.db.models import MonitoringAlertRecord

    visible = alert_visibility(session)
    rows = [
        row
        for row in session.query(MonitoringAlertRecord)
        .filter(MonitoringAlertRecord.status == "open")
        .filter(MonitoringAlertRecord.severity.in_(("critical", "warning")))
        .all()
        # Limits and outages have their own sections.
        if visible(row) and row.category != "limits" and row.alert_type != "outage"
    ]
    rows.sort(key=lambda row: (row.severity != "critical", -_ts(row.updated_at_utc)))
    lines = [
        f"{'Critical' if row.severity == 'critical' else 'Watch'}: {row.title_en}."
        for row in rows[:MAX_LINES]
    ]
    return (
        Section("alerts", "Alerts", lines, [f"alert:{row.alert_id}" for row in rows[:MAX_LINES]]),
        any(row.simulated for row in rows),
    )


def _outages(session, caller, now, kind):
    from eurogas_nexus.application.remit_outages import load_outage_rows

    lines, sources, demo = [], [], False
    horizon = now + timedelta(hours=36)
    for row in load_outage_rows(session, now=now, horizon_days=2):
        if datetime.fromisoformat(str(row["start_utc"])) > horizon:
            continue
        gwh = row.get("unavailable_gwh_d")
        if gwh is None or float(gwh) < 10:
            continue
        when = "out now" if row["status"] == "active" else (
            f"from {datetime.fromisoformat(str(row['start_utc'])):%d %b %H:%M} UTC"
        )
        end = row.get("end_utc")
        until = (
            f", until {datetime.fromisoformat(str(end)):%d %b %H:%M}" if end else ", no end date"
        )
        lines.append(
            f"{row['facility_name']} ({row.get('balancing_zone') or 'n/a'}): "
            f"{float(gwh):,.0f} GWh/d {when}{until}."
        )
        sources.append(f"remit:{row['event_id']}:v{row.get('version')}")
        demo = demo or str(row.get("source_reference") or "").lower().startswith("demo")
    return Section("outages", "Outages", lines[:MAX_LINES], sources[:MAX_LINES]), demo


def _prices(session, caller, now, kind):
    from eurogas_nexus.application.projections.daily_closes import daily_rows

    closes: dict[str, dict] = {}
    demo = False
    for row in daily_rows(caller, now.date() - timedelta(days=10), now.date()):
        if row["tenor"] not in {"month-ahead", "day-ahead"}:
            continue
        key = (row["hub"], row["tenor"])
        closes.setdefault(key, {})[row["day"]] = row
    lines, sources = [], []
    for (hub, tenor), series in sorted(closes.items()):
        if tenor == "day-ahead" and (hub, "month-ahead") in closes:
            continue  # one line per hub: the front month when there is one
        days = sorted(series)
        last = series[days[-1]]
        demo = demo or last["simulated"]
        text = f"{hub} {'front month' if tenor == 'month-ahead' else 'day-ahead'} " \
               f"{last['price']:.2f} {last['unit']} ({days[-1]:%d %b})"
        if len(days) > 1:
            change = last["price"] - series[days[-2]]["price"]
            text += f", {change:+.2f} on the day"
        lines.append(text + ".")
        sources.append(f"{last['source_system']}:{hub}:{tenor}")
    return Section("prices", "Prices", lines[:MAX_LINES], sources[:MAX_LINES]), demo


def _positions(session, caller, now, kind):
    from eurogas_nexus.application.position_inputs import ladder_inputs

    today = now.date()
    month_start = today.replace(day=1)
    next_month = (month_start + timedelta(days=32)).replace(day=1)
    inputs = ladder_inputs(caller, today, today, next_month + timedelta(days=31))
    net: dict[tuple[str, str], float] = {}
    for leg in inputs.legs:
        for label, day in (("today", today), ("front month", next_month)):
            if leg.first_gas_day <= day <= leg.last_gas_day:
                net[(leg.hub, label)] = net.get((leg.hub, label), 0.0) + leg.mwh_per_day
    lines = []
    for hub in sorted({hub for hub, _ in net}):
        parts = [
            f"{'long' if value > 0 else 'short'} {abs(value):,.0f} MWh/d {label}"
            for label in ("today", "front month")
            if (value := net.get((hub, label)))
        ]
        if parts:
            lines.append(f"{hub}: {', '.join(parts)}.")
    demo = any(w.startswith("DEMO") for w in inputs.warnings)
    return Section("positions", "Positions", lines[:MAX_LINES], ["position-ladder"]), demo


def _limits(session, caller, now, kind):
    from eurogas_nexus.application.limits_service import credit_exposure_rows, mandate_usage_rows

    credit = credit_exposure_rows(caller, now.date())
    mandates = mandate_usage_rows(caller, now.date())
    rank = {"breach": 0, "expired": 1, "watch": 2}
    lines, sources = [], []
    for row in sorted(credit.rows, key=lambda r: rank.get(r["status"], 9)):
        if row["status"] in {"breach", "watch", "expired"}:
            lines.append(
                f"{row['counterparty']} credit {row['status']}: "
                f"{money(row['net_exposure'], row['currency'])} of "
                f"{money(row['limit'], row['currency'])} ({row['utilisation_pct']:.0f}%)."
            )
            sources.append(f"credit-line:{row['counterparty_id']}")
    for row in sorted(mandates.rows, key=lambda r: rank.get(r["status"], 9)):
        if row["status"] in {"breach", "watch", "expired"}:
            detail = row["breaches"] or f"{row['utilisation_pct']:.0f}% of size limit"
            lines.append(f"{row['name']} mandate {row['status']}: {detail}.")
            sources.append(f"mandate:{row['mandate_id']}")
    demo = any(w.startswith("DEMO") for w in [*credit.warnings, *mandates.warnings])
    return Section("limits", "Credit and mandates", lines[:MAX_LINES], sources[:MAX_LINES]), demo


def _pnl(session, caller, now, kind):
    from eurogas_nexus.application.projections.portfolio_reads import pnl_snapshots

    rows = pnl_snapshots(session, principal_id=caller.principal_id)
    latest: dict[str, Any] = {}
    previous: dict[str, Any] = {}
    for row in rows:  # newest first
        if row.portfolio_id not in latest:
            latest[row.portfolio_id] = row
        elif row.portfolio_id not in previous:
            previous[row.portfolio_id] = row
    lines, sources, demo = [], [], False
    for portfolio, row in sorted(latest.items()):
        text = f"{portfolio}: indicative {money(row.indicative_pnl_gbp, 'GBP')}"
        if portfolio in previous:
            text += (
                f", {money(row.indicative_pnl_gbp - previous[portfolio].indicative_pnl_gbp, 'GBP')}"
                " since the previous valuation"
            )
        lines.append(text + ".")
        sources.append(f"pnl:{row.pnl_snapshot_id}")
        demo = demo or str(row.source_system).endswith("_Sim")
    return Section("pnl", "P&L", lines[:MAX_LINES], sources[:MAX_LINES]), demo


def _ts(value) -> float:
    return value.timestamp() if value else 0.0
