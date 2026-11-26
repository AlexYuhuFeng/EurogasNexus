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
from eurogas_nexus.application.desk_text import breaches_text, money
from eurogas_nexus.application.position_inputs import is_simulated_marks_warning

KINDS = ("morning", "eod")
MAX_LINES = 6


@dataclass
class Section:
    key: str
    heading: str
    lines: list[str]
    sources: list[str] = field(default_factory=list)
    #: The one price behind each price line (``price_resolver.price_payload``); served once,
    #: as the brief's ``resolved_prices``.
    resolved_prices: list[dict[str, Any]] = field(default_factory=list)


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
        data["sections"] = [
            {k: v for k, v in section.__dict__.items() if k != "resolved_prices"}
            for section in self.sections
        ]
        # P-08: the price each price line states, as every other screen reads it (additive).
        data["resolved_prices"] = [
            item for section in self.sections for item in section.resolved_prices
        ]
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
    from eurogas_nexus.application.reports.lang import writing

    for build in (_alerts, _outages, _prices, _positions, _limits, _pnl):
        try:
            # The brief's rule lines are in the interface's language, like the model's lead.
            with writing(language):
                section, demo = build(session, caller, now, kind)
        except Exception as exc:  # noqa: BLE001 - one missing section must not lose the brief
            name = build.__name__.strip("_")
            warnings.append(f"{name}: not available ({exc.__class__.__name__})")
            continue
        simulated = simulated or demo
        if section is not None and section.lines:
            sections.append(section)
    if simulated:
        warnings.insert(0, "Simulated prices: not market prices.")
    zh = str(language).lower().startswith("zh")
    if zh:
        title = (f"天然气交易台晨报，{now.year}年{now.month}月{now.day}日" if kind == "morning"
                 else f"天然气交易台日终报告，{now.year}年{now.month}月{now.day}日")
    else:
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
        text=_as_text(title, lead, sections, simulated, zh),
        simulated=simulated,
        warnings=warnings,
        as_of=now.isoformat(),
    )


def _as_text(title: str, lead: str | None, sections: list[Section], simulated: bool,
             zh: bool = False) -> str:
    out = [title, ""]
    if simulated:
        out += ["来源：模拟价格。" if zh else "Source: simulated prices.", ""]
    if lead:
        out += [lead, ""]
    for section in sections:
        out.append(section.heading.upper())
        out += [f"- {line}" for line in section.lines]
        out.append("")
    if not sections:
        out.append("交易台数据中没有需要报告的内容。" if zh else "Nothing to report from the desk'"
                                                 "s data.")
    return "\n".join(out).rstrip() + "\n"


def lead_payload(kind: str, sections: list[Section], simulated: bool) -> dict[str, Any]:
    """Exactly what the brief sends to the model: the section lines, sources as ``S1``..."""

    from eurogas_nexus.application.ai_style import source_aliases

    sources = sorted({source for s in sections for source in s.sources})
    return {
        "brief": kind,
        "sections": {section.heading: section.lines for section in sections},
        "sources": list(source_aliases(sources)),
        "simulated_inputs": simulated,
    }


def lead_task(kind: str, simulated: bool) -> str:
    return (
        "Write the lead of the desk's "
        + ("morning brief: what matters for today's trading" if kind == "morning" else
           "end-of-day report: what changed today and what carries into tomorrow")
        + ", picking the two or three most important facts."
        + (" Name the source once as simulated prices." if simulated else "")
    )


def _lead(model, kind: str, sections: list[Section], simulated: bool, language: str):
    from eurogas_nexus.application.ai_style import checked_note, note_messages

    facts = lead_payload(kind, sections, simulated)
    content = model(note_messages(lead_task(kind, simulated), facts, language=language))
    note = checked_note(
        content,
        evidence_text=json.dumps(facts, ensure_ascii=False),
        sources=facts["sources"],
        simulated=simulated,
        language=language,
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
        T(f"{'Critical' if row.severity == 'critical' else 'Watch'}: {row.title_en}.",
          f"{'严重' if row.severity == 'critical' else '观察'}：{row.title_zh_cn or row.title_en}"
          f"。")
        for row in rows[:MAX_LINES]
    ]
    return (
        Section("alerts", T("Alerts", "预警"), lines,
                [f"alert:{row.alert_id}" for row in rows[:MAX_LINES]]),
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
        start = datetime.fromisoformat(str(row["start_utc"]))
        end = row.get("end_utc")
        stop = datetime.fromisoformat(str(end)) if end else None
        zone = row.get("balancing_zone") or "n/a"
        lines.append(T(
            f"{row['facility_name']} ({zone}): {float(gwh):,.0f} GWh/d "
            + ("out now" if row["status"] == "active" else f"from {start:%d %b %H:%M} UTC")
            + (f", until {stop:%d %b %H:%M}" if stop else ", no end date") + ".",
            f"{row['facility_name']}（{zone}）：{float(gwh):,.0f} GWh/d，"
            + ("目前停运" if row["status"] == "active"
               else f"自 UTC {start.month}月{start.day}日 {start:%H:%M}起")
            + (f"，至{stop.month}月{stop.day}日 {stop:%H:%M}" if stop
               else "，未给出结束日期") + "。"))
        sources.append(f"remit:{row['event_id']}:v{row.get('version')}")
        demo = demo or str(row.get("source_reference") or "").lower().startswith("demo")
    return Section("outages", T("Outages", "停运"), lines[:MAX_LINES], sources[:MAX_LINES]), demo


def _prices(session, caller, now, kind):
    """One line per hub: the front month where held, else day-ahead.

    The front month states the one price for its month (``price_resolver``, P-08), the price
    Today and the Prices board show, with its change against the previous close of the same
    month; day-ahead states its close.
    """

    from eurogas_nexus.application.price_resolver import open_price_book, resolve_close_series
    from eurogas_nexus.application.projections.daily_closes import daily_rows, in_native_unit
    from eurogas_nexus.domain.portfolio.position_ladder import MAX_VAR_GAP_DAYS

    book = open_price_book(session, caller, now=now)
    resolved_prices: list[dict[str, Any]] = []
    closes: dict[str, dict] = {}
    demo = False
    for row in daily_rows(caller, now.date() - timedelta(days=10), now.date()):
        if row["tenor"] not in {"month-ahead", "day-ahead"}:
            continue
        key = (row["hub"], row["tenor"])
        closes.setdefault(key, {})[row["day"]] = row
    lines, sources = [], []
    # TTF and NBP first: the desk's benchmarks, then the other hubs.
    for (hub, tenor), series in sorted(closes.items(),
                                       key=lambda kv: (kv[0][0] != "TTF", kv[0][0] != "NBP",
                                                       kv[0])):
        if tenor == "day-ahead" and (hub, "month-ahead") in closes:
            continue  # one line per hub: the front month when there is one
        days = sorted(series)
        last = series[days[-1]]
        # The desk's own quotation (NBP in p/th), through the unit authority.
        shown, unit = in_native_unit(hub, last["price"], last["unit"])
        product = T("front month" if tenor == "month-ahead" else "day-ahead",
                    "近月" if tenor == "month-ahead" else "日前")
        day = days[-1]
        change = None
        if len(days) > 1:
            change = shown - in_native_unit(hub, series[days[-2]]["price"], last["unit"])[0]
        source = f"{last['source_system']}:{hub}:{tenor}"
        simulated = bool(last["simulated"])
        one = None
        if tenor == "month-ahead":
            one = resolve_close_series(book, hub, series, max_gap_days=MAX_VAR_GAP_DAYS)
        if one is not None:
            resolved = one["resolved"]
            shown, unit, change = one["value"], one["unit"], one["change"]
            day = resolved.as_of_utc.date() if resolved.as_of_utc is not None else day
            simulated = resolved.simulated
            source = f"{resolved.source_system}:{hub}:{tenor}"
        demo = demo or simulated
        text = T(f"{hub} {product} {shown:.2f} {unit} ({day:%d %b})",
                 f"{hub}{product} {shown:.2f} {unit}（{day.month}月{day.day}日）")
        if change is not None:
            text += T(f", {change:+.2f} on the day", f"，日变化{change:+.2f}")
        lines.append(text + T(".", "。"))
        sources.append(source)
        resolved_prices.append(one["payload"] if one is not None else None)
    section = Section("prices", T("Prices", "价格"), lines[:MAX_LINES], sources[:MAX_LINES])
    section.resolved_prices = [item for item in resolved_prices[:MAX_LINES] if item]
    return section, demo


def _positions(session, caller, now, kind):
    from eurogas_nexus.application.desk_today import net_positions
    from eurogas_nexus.application.position_inputs import ladder_inputs

    today = now.date()
    month_start = today.replace(day=1)
    next_month = (month_start + timedelta(days=32)).replace(day=1)
    inputs = ladder_inputs(caller, today, today, next_month + timedelta(days=31))
    # The Today read's figures (one computation): the front month is the month's average.
    net = net_positions(inputs.legs, today)
    lines = []
    for hub in sorted(net):
        parts = [
            T(f"{'long' if value > 0 else 'short'} {abs(value):,.0f} MWh/d {label}",
              f"{label_zh}{'多头' if value > 0 else '空头'}{abs(value):,.0f} MWh/d")
            for label, label_zh, key in (("today", "今日", "today"),
                                         ("front month", "近月", "front_month"))
            if abs(value := net[hub][key]) > 1e-9
        ]
        if parts:
            lines.append(T(f"{hub}: {', '.join(parts)}.", f"{hub}：{'，'.join(parts)}。"))
    demo = any(is_simulated_marks_warning(w) for w in inputs.warnings)
    return Section("positions", T("Positions", "头寸"), lines[:MAX_LINES],
                   ["position-ladder"]), demo


def _limits(session, caller, now, kind):
    from eurogas_nexus.application.limits_service import credit_exposure_rows, mandate_usage_rows

    credit = credit_exposure_rows(caller, now.date())
    mandates = mandate_usage_rows(caller, now.date())
    rank = {"breach": 0, "expired": 1, "watch": 2}
    lines, sources = [], []
    for row in sorted(credit.rows, key=lambda r: rank.get(r["status"], 9)):
        if row["status"] in {"breach", "watch", "expired"}:
            lines.append(T(
                f"{row['counterparty']} credit {row['status']}: "
                f"{money(row['net_exposure'], row['currency'])} of "
                f"{money(row['limit'], row['currency'])} ({row['utilisation_pct']:.0f}%).",
                f"{row['counterparty']}信用额度{_STATUS_ZH.get(row['status'], row['status'])}："
                f"{money(row['net_exposure'], row['currency'])}，限额"
                f"{money(row['limit'], row['currency'])}（{row['utilisation_pct']:.0f}%）。"))
            sources.append(f"credit-line:{row['counterparty_id']}")
    for row in sorted(mandates.rows, key=lambda r: rank.get(r["status"], 9)):
        if row["status"] in {"breach", "watch", "expired"}:
            detail = breaches_text(row["breaches"], T("en", "zh") == "zh") or T(
                f"{row['utilisation_pct']:.0f}% of size limit",
                f"规模上限的{row['utilisation_pct']:.0f}%")
            lines.append(T(f"{row['name']} mandate {row['status']}: {detail}.",
                           f"{row['name']}授权{_STATUS_ZH.get(row['status'], row['status'])}："
                           f"{detail}。"))
            sources.append(f"mandate:{row['mandate_id']}")
    demo = any(is_simulated_marks_warning(w) for w in [*credit.warnings, *mandates.warnings])
    return Section("limits", T("Credit and mandates", "信用额度与授权"), lines[:MAX_LINES],
                   sources[:MAX_LINES]), demo


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
        text = T(f"{portfolio}: indicative {money(row.indicative_pnl_gbp, 'GBP')}",
                 f"{portfolio}：指示性{money(row.indicative_pnl_gbp, 'GBP')}")
        if portfolio in previous:
            moved = money(row.indicative_pnl_gbp - previous[portfolio].indicative_pnl_gbp, "GBP")
            text += T(f", {moved} since the previous valuation", f"，较上次估值变化{moved}")
        lines.append(text + T(".", "。"))
        sources.append(f"pnl:{row.pnl_snapshot_id}")
        demo = demo or str(row.source_system).endswith("_Sim")
    return Section("pnl", T("P&L", "损益"), lines[:MAX_LINES], sources[:MAX_LINES]), demo


_STATUS_ZH = {"breach": "超限", "watch": "观察", "expired": "已过期", "ok": "正常"}


def T(en: str, zh_text: str) -> str:  # noqa: N802 - the reports' template marker
    from eurogas_nexus.application.reports.lang import T as pick

    return pick(en, zh_text)


def _ts(value) -> float:
    return value.timestamp() if value else 0.0
