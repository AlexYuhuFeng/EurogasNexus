"""Data adapters: each catalogue section's figures, from the reads the pages already use.

Every section reads through an existing entitled service, as the caller the report runs for:
licensed closes by data scope (``daily_rows``), books by the caller's book scope
(``ladder_inputs``, ``visible_book_ids``), alerts by ``alert_visibility``, outages by
``filter_rows_for_principal``, the balance only when every source behind it is licensed to
the caller (``derived_result_access``). Nothing here writes SQL a model wrote, and nothing
bypasses those checks.

Each builder returns a :class:`SectionResult`: rule commentary, tables, chart specs (the
type fixed by the catalogue), the evidence (sources with as-of time, freshness state,
simulated and licensed flags; method notes; revisions since the previous report) and an
empty state with the reason when there is nothing to show.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from eurogas_nexus.application.bounded_reads import read_bounded
from eurogas_nexus.application.caller import Caller
from eurogas_nexus.application.position_inputs import is_simulated_marks_warning
from eurogas_nexus.application.reports import commentary as rules
from eurogas_nexus.application.reports.catalogue import SECTION_BY_KEY, ReportPlan
from eurogas_nexus.application.reports.lang import T, zh

PUBLIC_DATA = "public"


@dataclass
class Ctx:
    """What every section builder reads."""

    session: Any
    caller: Caller
    now: datetime
    plan: ReportPlan
    previous_as_of: datetime | None = None
    balance_reader: Callable[[], dict | None] | None = None
    cache: dict[str, Any] = field(default_factory=dict)

    @property
    def today(self) -> date:
        return self.now.astimezone(UTC).date()

    @property
    def start(self) -> date:
        return self.plan.period_start or self.today

    @property
    def end(self) -> date:
        return self.plan.period_end or self.today

    @property
    def period_label(self) -> str | None:
        """``the week``/``October``: set when the report aggregates over a period."""

        if self.plan.kind == "weekly":
            return "the week"
        if self.plan.kind == "monthly":
            return f"{self.start:%B %Y}" if self.start.day == 1 else "the period"
        return None

    @property
    def chart_start(self) -> date:
        """The first day read for exhibits: the longest window an exhibit may show (13
        months), so the editor can choose a shorter one without another read."""

        return min(self.start, self.end - timedelta(days=394))

    @property
    def naive(self) -> bool:
        return self.session.get_bind().dialect.name == "sqlite"

    def bound(self, moment: datetime) -> datetime:
        return moment.replace(tzinfo=None) if self.naive else moment

    def day_bound(self, day: date) -> datetime:
        return self.bound(datetime.combine(day, time.min, tzinfo=UTC))


@dataclass
class SectionResult:
    key: str
    title: str
    group: str
    headline: str = ""
    bullets: list[str] = field(default_factory=list)
    tables: list[dict[str, Any]] = field(default_factory=list)
    charts: list[dict[str, Any]] = field(default_factory=list)
    sources: list[dict[str, Any]] = field(default_factory=list)
    methods: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    revisions: dict[str, Any] | None = None
    simulated: bool = False
    forecast: bool = False
    empty: dict[str, str] | None = None
    #: Book ids behind the figures (book sections), so a reader's scope can be re-checked.
    books: list[str] = field(default_factory=list)
    #: What the adapter read, for ``derive.py`` (not stored).
    raw: dict[str, Any] | None = None
    #: Candidate facts (``facts.fact``) for the fact sheet and the editor.
    facts: list[dict[str, Any]] = field(default_factory=list)
    #: Full series behind the exhibits, for the data annex and the CSV download.
    annex: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        rule = {"headline": self.headline, "bullets": list(self.bullets)}
        return {
            "key": self.key,
            "title": self.title,
            "group": self.group,
            "status": "empty" if self.empty else "ok",
            "empty": self.empty,
            "commentary": {**rule, "basis": "rule"},
            "rule_commentary": rule,
            "tables": self.tables,
            "charts": self.charts,
            "evidence": {
                "sources": self.sources,
                "methods": self.methods,
                "warnings": self.warnings,
                "revisions": self.revisions,
            },
            "simulated": self.simulated,
            "forecast": self.forecast,
            "books": sorted(set(self.books)),
            "facts": self.facts,
            "annex": self.annex,
        }


def _new(key: str) -> SectionResult:
    stype = SECTION_BY_KEY[key]
    return SectionResult(key=key, title=stype.title, group=stype.group)


def _empty(result: SectionResult, reason: str, action: str) -> SectionResult:
    result.empty = {"reason": reason, "action": action}
    result.headline = reason + "."
    result.bullets = []
    return result


def _apply(result: SectionResult, text: dict[str, Any]) -> SectionResult:
    result.headline = text["headline"]
    result.bullets = list(text["bullets"])
    return result


def _iso(value: datetime | date | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        moment = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
        return moment.isoformat()
    return value.isoformat()


def _aware(value: datetime | str | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def is_simulated_source(source_system: str | None) -> bool:
    from eurogas_nexus.domain.ontology.provenance import is_simulated

    return is_simulated(source_system)


def is_licensed_source(source_system: str | None) -> bool:
    """A licensed (commercial) family: not a public baseline family and not simulated."""

    from eurogas_nexus.security.identity import (
        PUBLIC_BASELINE_SOURCE_FAMILIES,
        source_family_for_entitlement,
    )

    value = str(source_system or "")
    if not value or is_simulated_source(value):
        return False
    return source_family_for_entitlement(value) not in PUBLIC_BASELINE_SOURCE_FAMILIES


def source(
    name: str,
    source_system: str | None,
    as_of: datetime | date | str | None,
    state: str,
    *,
    dataset: str | None = None,
) -> dict[str, Any]:
    from eurogas_nexus.security.identity import source_family_for_entitlement

    return {
        "name": name,
        "source_system": source_system,
        "family": source_family_for_entitlement(source_system or "") or None,
        "dataset": dataset,
        "as_of": as_of if isinstance(as_of, str) or as_of is None else _iso(as_of),
        "state": state,
        "simulated": is_simulated_source(source_system),
        "licensed": is_licensed_source(source_system),
    }


def table(caption: str, columns: list[tuple[str, str, str]], rows: list[dict]) -> dict:
    """``columns``: (key, label, unit-or-kind). ``kind`` ``num``/``text``/``date``."""

    return {
        "caption": caption,
        "columns": [{"key": k, "label": label, "kind": kind} for k, label, kind in columns],
        "rows": rows,
    }


def _avg(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _same_day_last_year(day: date) -> date:
    try:
        return day.replace(year=day.year - 1)
    except ValueError:
        return day - timedelta(days=365)


def covered_label(ctx: Ctx, measured: list[date]) -> str | None:
    """The period's label, saying so when fewer days were measured than the period has.

    "the week" over seven measured days; "the 4 measured days of the week (9 Nov to 12 Nov)"
    when the newest days are not yet published, so an average is never read as the period's.
    """

    label = ctx.period_label
    if not label or not measured:
        return label
    total = (ctx.end - ctx.start).days + 1
    if len(measured) >= total:
        return label
    first, last = min(measured), max(measured)
    return (f"the {len(measured)} measured days of {label} "
            f"({first.day} {first:%b} to {last.day} {last:%b})")


def revisions_since(ctx: Ctx, tables: tuple[str, ...], families: tuple[str, ...] = ()) -> dict:
    """Provider revisions to these observation tables since the previous report of the kind."""

    from sqlalchemy import func

    from eurogas_nexus.db.models.observation import ObservationRevisionRecord as Rev

    if ctx.previous_as_of is None:
        return {"count": None, "since": None,
                "note": "First report of this kind: no earlier report to compare with."}
    query = ctx.session.query(func.count(Rev.revision_id)).filter(
        Rev.observation_table.in_(tables),
        Rev.superseded_at_utc > ctx.bound(ctx.previous_as_of),
        Rev.superseded_at_utc <= ctx.bound(ctx.now),
    )
    if families:
        from sqlalchemy import or_

        query = query.filter(or_(*[Rev.source_system.like(f"{f}%") for f in families]))
    count = int(query.scalar() or 0)
    return {"count": count, "since": _iso(ctx.previous_as_of)}


# ================================================================================= prices


def prices(ctx: Ctx) -> SectionResult:
    from eurogas_nexus.application.freshness_contract import close_state
    from eurogas_nexus.application.projections.daily_closes import (
        ObservationWindowTooLarge,
        daily_rows,
        in_native_unit,
    )
    from eurogas_nexus.domain.portfolio.position_ladder import MAX_VAR_GAP_DAYS

    result = _new("prices")
    first = min(ctx.chart_start, _same_day_last_year(ctx.end) - timedelta(days=7))
    try:
        rows = daily_rows(ctx.caller, first, ctx.end)
    except ObservationWindowTooLarge:
        first = ctx.chart_start
        rows = daily_rows(ctx.caller, first, ctx.end)
    now = ctx.now
    series: dict[tuple[str, str, str], dict[date, dict]] = {}
    for row in rows:
        if row["tenor"] not in {"month-ahead", "day-ahead"} or not row.get("hub_resolved", True):
            continue
        observed = _aware(row.get("observed_at_utc"))
        if observed is not None and observed > now:
            continue  # as of the report's instant: nothing received later
        if ctx.plan.hubs and row["hub"] not in ctx.plan.hubs:
            continue
        series.setdefault((row["hub"], row["tenor"], row["source_system"]), {})[row["day"]] = row
    best: dict[str, tuple] = {}
    for (hub, tenor, source_system), closes in series.items():
        last_day = max(closes)
        last = closes[last_day]
        rank = (not last["simulated"], tenor == "month-ahead", last_day)
        if hub not in best or rank > best[hub][0]:
            best[hub] = (rank, tenor, source_system, closes)
    if not best:
        hubs = ", ".join(ctx.plan.hubs) if ctx.plan.hubs else "any hub"
        return _empty(result, f"No licensed close for {hubs} is held under your licences",
                      "Import settlements or connect a licensed price feed")
    out_rows = []
    chart_series: dict[str, list[dict]] = defaultdict(list)
    for hub in sorted(best, key=lambda h: (h != "TTF", h != "NBP", h)):
        _, tenor, source_system, closes = best[hub]
        days = sorted(closes)
        last = closes[days[-1]]
        unit = in_native_unit(hub, last["price"], last["unit"])[1]

        def shown(d: date, closes=closes, hub=hub, last=last) -> float:
            return round(in_native_unit(hub, closes[d]["price"], last["unit"])[0], 4)

        if tenor == "month-ahead":
            start = last.get("period_start_utc")
            product = f"{start:%b-%y}" if start else "MA"
        else:
            product = "DA"
        close = shown(days[-1])
        day_change = None
        if len(days) > 1 and (days[-1] - days[-2]).days <= MAX_VAR_GAP_DAYS:
            day_change = round(close - shown(days[-2]), 4)
        def contract(d: date, closes=closes) -> Any:
            # The delivery period a close prices: a front month rolls at each month end, so
            # closes of two different contracts are never compared or ranged together.
            start = closes[d].get("period_start_utc")
            return start.date() if isinstance(start, datetime) else start

        period_days = [d for d in days if ctx.start <= d <= ctx.end
                       and contract(d) == contract(days[-1])]
        before = [d for d in days if d < ctx.start and (ctx.start - d).days <= 10]
        period_change = high = low = average = None
        rolled = None
        if ctx.period_label and period_days:
            values = [shown(d) for d in period_days]
            high, low, average = max(values), min(values), round(sum(values) / len(values), 4)
            if before and contract(before[-1]) == contract(days[-1]):
                period_change = round(close - shown(before[-1]), 4)
            elif before:
                start = closes[before[-1]].get("period_start_utc")
                rolled = f"{start:%b-%y}" if isinstance(start, datetime) else None
        year_day = _same_day_last_year(days[-1])
        year_ago_days = [d for d in days if year_day - timedelta(days=5) <= d <= year_day]
        year_ago = shown(year_ago_days[-1]) if year_ago_days else None
        simulated = bool(last["simulated"])
        state = close_state(days[-1], ctx.today)
        out_rows.append(
            {
                "hub": hub,
                "product": product,
                "close": close,
                "unit": unit,
                "day_change": day_change,
                "period_change": period_change,
                "high": high,
                "low": low,
                "average": average,
                "year_ago": year_ago,
                "close_day": days[-1].isoformat(),
                "simulated": simulated,
                "state": state,
                "source": "Simulated price" if simulated else source_system,
                "rolled_from": rolled,
            }
        )
        result.simulated = result.simulated or simulated
        result.raw = result.raw or {"hubs": []}
        result.raw["hubs"].append({
            "hub": hub, "product": product, "unit": unit, "close": close,
            "close_day": days[-1], "day_change": day_change, "year_ago": year_ago,
            "simulated": simulated, "state": state, "rolled_from": rolled,
            "high": high, "low": low, "average": average, "period_change": period_change,
            "series": {d: shown(d) for d in days},
            "contract": {d: contract(d) for d in days},
        })
        result.sources.append(
            source(f"{hub} {'front month' if tenor == 'month-ahead' else 'day-ahead'} closes",
                   source_system, days[-1], state)
        )
        points = [[d.isoformat(), shown(d)] for d in days if ctx.chart_start <= d <= ctx.end]
        if points:
            chart_series[unit].append(
                {"name": f"{hub} {'front month' if tenor == 'month-ahead' else 'DA'}",
                 "points": points}
            )
    period = bool(ctx.period_label)
    columns = [("hub", "Hub", "text"), ("product", "Product", "text"),
               ("close", "Close", "num"), ("unit", "Unit", "text"),
               ("day_change", "Day change", "signed")]
    if period:
        columns += [("period_change", "Change over period", "signed"), ("high", "High", "num"),
                    ("low", "Low", "num"), ("average", "Average", "num")]
    columns += [("year_ago", "Year earlier", "num"), ("close_day", "Close day", "date"),
                ("source", "Source", "text"), ("state", "State", "state")]
    result.tables.append(table("Hub closes, each in its quoted unit", columns, out_rows))
    for unit, items in chart_series.items():
        result.charts.append(
            {"type": "line", "title": f"Front-month closes ({unit})", "unit": unit,
             "series": items,
             "note": "Front month rolls at each month end; closes as received."}
        )
    if result.simulated:
        result.warnings.append("Simulated prices: not market prices.")
    return _apply(result, rules.prices(out_rows, period_label=ctx.period_label))


# ================================================================================= alerts


def alerts(ctx: Ctx) -> SectionResult:
    from eurogas_nexus.application.alert_scope import alert_visibility
    from eurogas_nexus.db.models import MonitoringAlertRecord

    result = _new("alerts")
    visible = alert_visibility(ctx.session)
    rows = [
        row
        for row in ctx.session.query(MonitoringAlertRecord)
        .filter(MonitoringAlertRecord.status == "open")
        .filter(MonitoringAlertRecord.severity.in_(("critical", "warning")))
        .all()
        if visible(row)
        and row.alert_type != "outage"
        # Limits alerts are book figures, reported once, in Limits (one number, one place).
        and row.category not in {"limits"}
        and (ctx.plan.audience == "internal" or row.category == "physical")
        and (_aware(row.detected_at_utc) or ctx.now) <= ctx.now
    ]
    rows.sort(key=lambda r: (r.severity != "critical",
                             -(_aware(r.updated_at_utc or r.detected_at_utc) or ctx.now)
                             .timestamp()))
    items = [
        {
            "severity": row.severity,
            "category": row.category,
            # The alert's own title in the report's language (the scan writes both).
            "title": (row.title_zh_cn or row.title_en) if zh() else row.title_en,
            "as_of": _iso(row.updated_at_utc or row.detected_at_utc),
            "simulated": bool(row.simulated),
        }
        for row in rows[:8]
    ]
    counts = {
        "open": len(rows),
        "critical": sum(1 for r in rows if r.severity == "critical"),
        "warning": sum(1 for r in rows if r.severity == "warning"),
    }
    if not rows:
        return _empty(result, "No critical or watch alert is open", "Open Events")
    result.simulated = any(item["simulated"] for item in items)
    result.tables.append(table(
        "Open alerts, critical first",
        [("severity", "Severity", "text"), ("category", "Category", "text"),
         ("title", "Alert", "text"), ("as_of", "Updated", "datetime")],
        items,
    ))
    newest = max((_aware(r.updated_at_utc or r.detected_at_utc) for r in rows), default=None)
    result.sources.append(source("Eurogas Nexus monitoring", "operator-input", newest,
                                 "current" if rows else "never"))
    if ctx.plan.audience == "shareable":
        result.warnings.append("Shareable report: only physical-market alerts are listed.")
    return _apply(result, rules.alerts({"counts": counts, "items": items}))


# ================================================================================= supply


def _landed(ctx: Ctx):
    from eurogas_nexus.application.pipeline_supply import landed_supply

    key = "landed"
    if key not in ctx.cache:
        first = min(ctx.chart_start, _same_day_last_year(ctx.start) - timedelta(days=7))
        ctx.cache[key] = landed_supply(ctx.session, first, as_of=ctx.now)
    return ctx.cache[key]


def _sources_of(ctx: Ctx, model, *filters) -> set[str]:
    from eurogas_nexus.application.identity_resolution import identity_clause

    first = ctx.day_bound(ctx.chart_start)
    return {
        value
        for (value,) in ctx.session.query(model.source_system)
        .filter(*filters, model.period_start_utc >= first)
        .filter(identity_clause(ctx.session, model))
        .distinct()
        .all()
        if value
    }


def pipeline_supply(ctx: Ctx) -> SectionResult:
    from eurogas_nexus.application.freshness_contract import period_state
    from eurogas_nexus.application.pipeline_supply import (
        LANDING_POINTS,
        OPERATOR_SELECTION_RULE,
    )
    from eurogas_nexus.db.models import FlowObservationRecord as Flow
    from eurogas_nexus.domain.dataops.entitlement import derived_result_access
    from eurogas_nexus.domain.market.gas_day import gas_day_start_utc

    result = _new("pipeline_supply")
    points = sorted({p.point_id for p in LANDING_POINTS})
    systems = _sources_of(ctx, Flow, Flow.point_id.in_(points))
    if systems and derived_result_access(ctx.caller.principal, systems).outcome.value != "ALLOWED":
        return _empty(result, "The landings use data outside your licences",
                      "Ask your administrator for the data scope")
    supply = _landed(ctx)
    days = sorted(d for d in supply.by_day if d <= ctx.end)
    if not days:
        return _empty(result, "No complete gas day of Norwegian landings is held",
                      "Schedule the ENTSOG flows source")
    simulated = bool(systems) and all(is_simulated_source(s) for s in systems)
    latest = days[-1]
    norway = supply.by_scope.get("norway", {})
    uk = supply.by_scope.get("uk_terminal", {})
    window = [d for d in days if d >= ctx.chart_start]
    stats: dict[str, Any] = {
        "latest": supply.by_day[latest],
        "latest_day": latest.isoformat(),
        "previous": supply.by_day.get(latest - timedelta(days=1)),
        "avg_7": _avg([supply.by_day[d] for d in days if d > latest - timedelta(days=7)]),
        "continent": norway.get(latest),
        "uk_terminal": uk.get(latest),
        "simulated": simulated,
        "period_label": ctx.period_label,
    }
    if ctx.period_label:
        in_period = [supply.by_day[d] for d in days if ctx.start <= d <= ctx.end]
        length = (ctx.end - ctx.start).days + 1
        before = [supply.by_day[d] for d in days
                  if ctx.start - timedelta(days=length) <= d < ctx.start]
        stats["period_avg"] = _avg(in_period)
        stats["previous_avg"] = _avg(before)
        stats["period_label"] = covered_label(
            ctx, [d for d in days if ctx.start <= d <= ctx.end])
        last_year = [supply.by_day[d] for d in supply.by_day
                     if _same_day_last_year(ctx.start) <= d <= _same_day_last_year(ctx.end)]
        stats["year_ago"] = _avg(last_year)
        if stats["period_avg"] is None:
            return _empty(result, "No complete gas day of landings in the period",
                          "Schedule the ENTSOG flows source")
    else:
        last_year = [supply.by_day[d] for d in supply.by_day
                     if _same_day_last_year(latest) - timedelta(days=6) <= d
                     <= _same_day_last_year(latest)]
        stats["year_ago"] = _avg(last_year) if len(last_year) >= 5 else None
    start = gas_day_start_utc(datetime.combine(latest, time(12), tzinfo=UTC))
    state = period_state("ENTSOG flows", start, ctx.now)
    stats["state"] = state
    result.simulated = simulated
    result.charts.append({
        "type": "stacked_area",
        "title": "Norwegian pipeline landings by landing scope",
        "unit": "GWh/d",
        "series": [
            {"name": "Continental landings",
             "points": [[d.isoformat(), round(norway.get(d, 0.0), 1)] for d in window]},
            {"name": "UK terminals",
             "points": [[d.isoformat(), round(uk.get(d, 0.0), 1)] for d in window]},
        ],
    })
    result.tables.append(table(
        "Landed energy per gas day, newest first",
        [("day", "Gas day", "date"), ("continent", "Continental", "num"),
         ("uk_terminal", "UK terminals", "num"), ("total", "Total", "num"),
         ("unit", "Unit", "text")],
        [{"day": d.isoformat(), "continent": round(norway.get(d, 0.0), 1),
          "uk_terminal": round(uk.get(d, 0.0), 1), "total": round(supply.by_day[d], 1),
          "unit": "GWh/d"} for d in reversed(window[-10:])],
    ))
    for system in sorted(systems) or ["ENTSOG"]:
        result.sources.append(source("Physical flows at the landing points", system, latest,
                                     state, dataset="ENTSOG flows"))
    result.methods.append({"key": "landing_points", "title": "Landing points and operator",
                           "text": OPERATOR_SELECTION_RULE})
    if supply.incomplete_days:
        tail = [d for d in supply.incomplete_days if d > latest]
        if tail:
            result.warnings.append("Gas days only partly reported are left out: "
                                   + ", ".join(d.isoformat() for d in tail) + ".")
    result.revisions = revisions_since(ctx, ("flow_observations",))
    total = {d: supply.by_day[d] for d in days}
    ctx.cache["landings_latest"] = total[latest]
    result.raw = {"total": total, "norway": {d: v for d, v in norway.items() if d <= ctx.end},
                  "uk": {d: v for d, v in uk.items() if d <= ctx.end}, "latest": latest,
                  "state": state, "period_avg": stats.get("period_avg"),
                  "previous_avg": stats.get("previous_avg"),
                  "period_label": stats.get("period_label")}
    return _apply(result, rules.pipeline(stats))


def lng(ctx: Ctx) -> SectionResult:
    from eurogas_nexus.application.freshness_contract import period_state
    from eurogas_nexus.application.identity_resolution import identity_clause
    from eurogas_nexus.application.projections.market_reads import row_allowed
    from eurogas_nexus.db.models.observation import LngObservationRecord as Lng
    from eurogas_nexus.domain.fundamentals.balance import NWE_COUNTRIES

    result = _new("lng")
    # An asked report reads the whole region: its question join sets a country against the
    # NW Europe total (``joins.lng_country``).
    countries = (list(NWE_COUNTRIES) if ctx.plan.kind == "ask"
                 else ctx.plan.countries or list(NWE_COUNTRIES))
    first = min(ctx.chart_start, _same_day_last_year(ctx.start) - timedelta(days=7))
    records = read_bounded(
        ctx.session.query(Lng.period_start_utc, Lng.country, Lng.source_system,
                          Lng.send_out_twh_d, Lng.observed_at_utc)
        .filter(Lng.country.in_(countries), Lng.send_out_twh_d.isnot(None))
        .filter(identity_clause(ctx.session, Lng))
        .filter(Lng.period_start_utc >= ctx.day_bound(first))
        .filter(Lng.period_start_utc < ctx.day_bound(ctx.end + timedelta(days=1))),
        60_000,
        what="LNG observation",
    )
    allowed = [r for r in records if row_allowed(ctx.caller.principal, r.source_system)
               and (_aware(r.observed_at_utc) or ctx.now) <= ctx.now]
    real = [r for r in allowed if not is_simulated_source(r.source_system)]
    rows = real or allowed
    if not rows:
        return _empty(result, "No LNG send-out is held for the scope",
                      "Schedule the GIE ALSI source")
    simulated = not real
    by_day: dict[date, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for r in rows:
        by_day[_aware(r.period_start_utc).date()][r.country] += float(r.send_out_twh_d) * 1000
    coverage = max(len(v) for v in by_day.values())
    recent = [d for d in by_day if d >= ctx.end - timedelta(days=60)]
    coverage = max((len(by_day[d]) for d in recent), default=coverage)
    complete = sorted(d for d in by_day if len(by_day[d]) >= coverage)
    left_out = sorted(d for d in by_day if len(by_day[d]) < coverage and d > max(complete or [d]))
    if not complete:
        return _empty(result, "No complete gas day of LNG send-out", "Schedule GIE ALSI")
    total = {d: sum(by_day[d].values()) for d in complete}
    latest = complete[-1]
    stats: dict[str, Any] = {
        "latest": total[latest],
        "latest_day": latest.isoformat(),
        "avg_7": _avg([total[d] for d in complete if d > latest - timedelta(days=7)]),
        "simulated": simulated,
        "left_out": [d.isoformat() for d in left_out],
        "period_label": ctx.period_label,
    }
    by_country_basis = by_day[latest]
    if ctx.period_label:
        in_period = [d for d in complete if ctx.start <= d <= ctx.end]
        if not in_period:
            return _empty(result, "No complete gas day of LNG send-out in the period",
                          "Schedule GIE ALSI")
        length = (ctx.end - ctx.start).days + 1
        stats["period_avg"] = _avg([total[d] for d in in_period])
        stats["period_label"] = covered_label(ctx, in_period)
        stats["previous_avg"] = _avg([total[d] for d in complete
                                      if ctx.start - timedelta(days=length) <= d < ctx.start])
        sums: dict[str, float] = defaultdict(float)
        for d in in_period:
            for country, value in by_day[d].items():
                sums[country] += value / len(in_period)
        by_country_basis = sums
        last_year = [total[d] for d in complete
                     if _same_day_last_year(ctx.start) <= d <= _same_day_last_year(ctx.end)]
        stats["year_ago"] = _avg(last_year)
    stats["by_country"] = sorted(by_country_basis.items(), key=lambda kv: -kv[1])
    start = datetime.combine(latest, time(6), tzinfo=UTC)
    state = period_state("GIE LNG (ALSI)", start, ctx.now)
    stats["state"] = state
    window = [d for d in complete if d >= ctx.chart_start]
    names = sorted({c for d in window for c in by_day[d]},
                   key=lambda c: -sum(by_day[d].get(c, 0.0) for d in window))
    result.simulated = simulated
    result.charts.append({
        "type": "stacked_bar",
        "title": "LNG send-out by country",
        "unit": "GWh/d",
        "series": [{"name": c, "points": [[d.isoformat(), round(by_day[d].get(c, 0.0), 1)]
                                          for d in window]} for c in names],
    })
    result.tables.append(table(
        "Send-out by country" + (" (period average)" if ctx.period_label else
                                 f" on {latest:%d %b}"),
        [("country", "Country", "text"), ("value", "Send-out", "num"), ("unit", "Unit", "text")],
        [{"country": c, "value": round(v, 1), "unit": "GWh/d"} for c, v in stats["by_country"]],
    ))
    for system in sorted({r.source_system for r in rows}):
        result.sources.append(source("LNG send-out", system, latest, state,
                                     dataset="GIE LNG (ALSI)"))
    result.revisions = revisions_since(ctx, ("lng_observations",))
    result.raw = {"total": total, "by_day": {d: dict(by_day[d]) for d in complete},
                  "latest": latest, "state": state, "left_out": stats["left_out"]}
    return _apply(result, rules.lng(stats))


def _storage_data(ctx: Ctx) -> dict[str, Any] | None:
    """NW Europe storage from the storage fundamentals read (``fundamentals_storage``, the
    reads' one source for storage): the region's daily fill this gas year and last, its stock,
    sources and countries, and each country's stock and capacity now and a week ago. ``None``
    when no storage is held."""

    from eurogas_nexus.application.fundamentals_storage import storage_read
    from eurogas_nexus.domain.fundamentals.storage_history import gas_year_of
    from eurogas_nexus.domain.market.storage_targets import (
        DEFAULT_DEADLINE,
        DEFAULT_TARGET_PCT,
        DEFAULT_WINDOW_OPEN,
    )

    read = storage_read(ctx.session, ctx.caller.principal, region="nwe", season=["NWE"],
                        now=ctx.now)
    region = read.get("region")
    if not region or region.get("fill_pct") is None:
        return None
    series = region.get("season") or {}
    first_year = gas_year_of(date.fromisoformat(region["as_of"]))
    season: list[dict[str, Any]] = []
    last_year = (series.get("last_year") or {}).get("values") or []
    for index, key in enumerate(series.get("axis") or []):
        month, day_of_month = (int(x) for x in key.split("-"))
        year = first_year if month >= 10 else first_year + 1
        try:
            day = date(year, month, day_of_month)
        except ValueError:
            continue
        fill = (series.get("this_year") or [None] * 365)[index]
        if fill is None:
            continue
        season.append({"day": day.isoformat(), "fill_pct": fill,
                       "previous_year_fill_pct": last_year[index] if index < len(last_year)
                       else None})
    by_country = {c["code"]: (c["stock_twh"], c["working_capacity_twh"])
                  for c in read.get("countries") or []
                  if c.get("stock_twh") is not None and c.get("working_capacity_twh")}
    week = {c["code"]: (c["stock_twh"] - (c.get("week_change_twh") or 0.0),
                        c["working_capacity_twh"])
            for c in read.get("countries") or []
            if c.get("stock_twh") is not None and c.get("working_capacity_twh")
            and c.get("week_change_twh") is not None}
    return {
        "season": season,
        "inventory_twh": region.get("stock_twh"),
        "latest": {"simulated": bool(region.get("simulated")), "as_of": region["as_of"],
                   "state": "current", "source": ", ".join(region.get("sources") or []),
                   "countries": sorted(by_country)},
        "target": {"pct": DEFAULT_TARGET_PCT,
                   "window_open": f"{DEFAULT_WINDOW_OPEN[0]:02d}-{DEFAULT_WINDOW_OPEN[1]:02d}",
                   "deadline": f"{DEFAULT_DEADLINE[0]:02d}-{DEFAULT_DEADLINE[1]:02d}"},
        "by_country": by_country,
        "by_country_week": week,
    }


def storage(ctx: Ctx) -> SectionResult:
    result = _new("storage")
    data = _storage_data(ctx)
    if data is None:
        return _empty(result, "Storage data not connected", "Connect GIE AGSI in Sources")
    season = [p for p in data["season"] if p["day"] <= ctx.end.isoformat()]
    if not season:
        return _empty(result, "No storage day in the period is still in the season read",
                      "Choose a recent period")
    latest = season[-1]
    figure = data["latest"]
    stats: dict[str, Any] = {
        "fill": latest["fill_pct"],
        "day": latest["day"],
        "year_ago": latest["previous_year_fill_pct"],
        "simulated": figure["simulated"],
        "state": figure["state"] if latest["day"] == figure["as_of"] else "current",
        "target": data["target"]["pct"],
        "target_window": f"{data['target']['window_open']} and {data['target']['deadline']} "
                         "(month-day)",
        "period_label": ctx.period_label,
    }
    stats["inventory_twh"] = (data["inventory_twh"] if latest["day"] == figure["as_of"]
                              else None)
    by_day = {p["day"]: p["fill_pct"] for p in season}
    if ctx.period_label:
        before = (ctx.start - timedelta(days=1)).isoformat()
        if before in by_day and by_day[before] is not None:
            stats["period_change"] = round(latest["fill_pct"] - by_day[before], 2)
    else:
        week = (date.fromisoformat(latest["day"]) - timedelta(days=7)).isoformat()
        if week in by_day and by_day[week] is not None:
            stats["period_change"] = round(latest["fill_pct"] - by_day[week], 2)
    window = [p for p in season if p["day"] >= ctx.chart_start.isoformat()]
    if ctx.plan.kind in {"weekly", "monthly", "ask"} or len(window) < 20:
        window = season[-90:]
    result.simulated = figure["simulated"]
    result.charts.append({
        "type": "line",
        "title": "NW Europe storage fill against a year earlier",
        "unit": "%",
        "series": [
            {"name": "Fill", "points": [[p["day"], p["fill_pct"]] for p in window]},
            {"name": "Same day a year earlier",
             "points": [[p["day"], p["previous_year_fill_pct"]] for p in window]},
        ],
        "reference_lines": [{"label": f"EU target {data['target']['pct']:.0f}%",
                             "value": data["target"]["pct"]}],
    })
    result.tables.append(table(
        "Fill by day, newest first",
        [("day", "Gas day", "date"), ("fill_pct", "Fill", "num"),
         ("previous_year_fill_pct", "Year earlier", "num"), ("unit", "Unit", "text")],
        [{**p, "unit": "%"} for p in reversed(window[-10:])],
    ))
    for system in (figure["source"] or "").split(", "):
        result.sources.append(source("Storage inventory and working capacity",
                                     "DEMO_Sim" if system in {"Demo", ""} else system,
                                     latest["day"], stats["state"], dataset="GIE storage (AGSI)"))
    result.methods.append({
        "key": "storage_scope", "title": "Storage scope",
        "text": "Facilities in " + ", ".join(figure.get("countries") or [])
        + " that publish a working capacity; a day counts only when as many countries "
        "reported as on the best-covered day. GB publishes no working capacity and is not in "
        "the fill.",
    })
    result.revisions = revisions_since(ctx, ("storage_observations",))
    result.raw = {
        "fill": {date.fromisoformat(p["day"]): p["fill_pct"] for p in season
                 if p["fill_pct"] is not None},
        "previous": {date.fromisoformat(p["day"]): p["previous_year_fill_pct"] for p in season
                     if p["previous_year_fill_pct"] is not None},
        "latest": date.fromisoformat(latest["day"]), "state": stats["state"],
        "inventory": stats.get("inventory_twh"), "target": stats.get("target"),
        "by_country": data.get("by_country") or {},
        "by_country_week": data.get("by_country_week") or {},
    }
    return _apply(result, rules.storage(stats))


# ================================================================================= demand


#: Bidding zones for the NW Europe countries (Germany and Luxembourg share one zone).
POWER_ZONES = {"GB": "GB", "NL": "NL", "BE": "BE", "DE": "DE_LU", "LU": "DE_LU", "FR": "FR",
               "DK": "DK"}


def power_burn(ctx: Ctx) -> SectionResult:
    from eurogas_nexus.application.freshness_contract import period_state
    from eurogas_nexus.application.identity_resolution import identity_clause
    from eurogas_nexus.application.projections.market_reads import row_allowed
    from eurogas_nexus.db.models.power import PowerObservationRecord as Power
    from eurogas_nexus.domain.fundamentals.balance import NWE_COUNTRIES

    result = _new("power_burn")
    zones = sorted({POWER_ZONES[c] for c in (ctx.plan.countries or NWE_COUNTRIES)
                    if c in POWER_ZONES})
    first = ctx.chart_start
    records = read_bounded(
        ctx.session.query(Power.zone, Power.period_start_utc, Power.period_end_utc, Power.value,
                          Power.source_system, Power.published_at_utc)
        .filter(Power.metric == "gas_generation")
        .filter(identity_clause(ctx.session, Power))
        .filter(Power.zone.in_(zones + ["DK1", "DK2"]))
        .filter(Power.period_start_utc >= ctx.day_bound(first))
        .filter(Power.period_start_utc < ctx.day_bound(ctx.end + timedelta(days=1))),
        400_000,
        what="power generation",
    )
    rows = [r for r in records if row_allowed(ctx.caller.principal, r.source_system)
            and (_aware(r.published_at_utc) or ctx.now) <= ctx.now]
    if not rows:
        return _empty(result, "No gas-fired generation is held for the scope",
                      "Schedule the ENTSO-E or Elexon generation source")
    energy: dict[date, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    hours: dict[date, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for r in rows:
        start, end = _aware(r.period_start_utc), _aware(r.period_end_utc)
        span = (end - start).total_seconds() / 3600.0
        if span <= 0 or span > 25:
            continue
        zone = "DK" if r.zone.startswith("DK") else r.zone
        energy[start.date()][zone] += float(r.value) * span / 1000.0
        hours[start.date()][zone] += span
    complete: dict[date, dict[str, float]] = {}
    for d, per_zone in energy.items():
        full = {z: v for z, v in per_zone.items() if hours[d][z] >= 22.5}
        if full:
            complete[d] = full
    if not complete:
        return _empty(result, "No complete day of gas-fired generation", "Check the source")
    coverage = max(len(v) for v in complete.values())
    days = sorted(d for d, v in complete.items() if len(v) >= coverage)
    total = {d: sum(complete[d].values()) for d in days}
    latest = days[-1]
    simulated = all(is_simulated_source(r.source_system) for r in rows)
    stats: dict[str, Any] = {
        "latest": total[latest], "latest_day": latest.isoformat(),
        "avg_7": _avg([total[d] for d in days if d > latest - timedelta(days=7)]),
        "simulated": simulated, "period_label": ctx.period_label,
        "by_zone": sorted(complete[latest].items(), key=lambda kv: -kv[1]),
    }
    if ctx.period_label:
        in_period = [d for d in days if ctx.start <= d <= ctx.end]
        if not in_period:
            return _empty(result, "No complete day of gas-fired generation in the period",
                          "Check the source")
        stats["period_avg"] = _avg([total[d] for d in in_period])
        stats["period_label"] = covered_label(ctx, in_period)
    systems = sorted({r.source_system for r in rows})
    dataset = "Power (ENTSO-E)" if any(s.startswith("ENTSOE") for s in systems) \
        else "GB power (Elexon)"
    state = period_state(dataset, datetime.combine(latest, time(23), tzinfo=UTC), ctx.now)
    stats["state"] = state
    result.simulated = simulated
    window = [d for d in days if d >= ctx.chart_start]
    names = sorted({z for d in window for z in complete[d]})
    result.charts.append({
        "type": "stacked_bar", "title": "Electricity generated from gas, by bidding zone",
        "unit": "GWh/d",
        "series": [{"name": z, "points": [[d.isoformat(), round(complete[d].get(z, 0.0), 1)]
                                          for d in window]} for z in names],
    })
    result.tables.append(table(
        f"Gas-fired generation on {latest:%d %b} (UTC day)",
        [("zone", "Zone", "text"), ("value", "Generation", "num"), ("unit", "Unit", "text")],
        [{"zone": z, "value": round(v, 1), "unit": "GWh/d"} for z, v in stats["by_zone"]],
    ))
    for system in systems:
        result.sources.append(source("Generation by fuel (gas)", system, latest, state,
                                     dataset=dataset))
    result.methods.append({"key": "power_day", "title": "Days and coverage",
                           "text": "UTC days; a zone counts on a day only when its periods "
                                   "cover at least 22.5 hours, and a day only when as many "
                                   "zones as on the best-covered day reported."})
    result.revisions = revisions_since(ctx, ("power_observations",))
    result.raw = {"total": total, "by_day": {d: dict(complete[d]) for d in days},
                  "latest": latest, "state": state}
    return _apply(result, rules.power(stats))


# ================================================================================= outages


def _outage_rows(ctx: Ctx, horizon_days: int, ended_since: datetime | None = None) -> list[dict]:
    from eurogas_nexus.application.remit_outages import load_outage_rows
    from eurogas_nexus.domain.dataops.entitlement import filter_rows_for_principal
    from eurogas_nexus.domain.observations.remit_umm import outage_events

    key = f"outages:{horizon_days}:{ended_since}"
    if key not in ctx.cache:
        rows = load_outage_rows(ctx.session, now=ctx.now, horizon_days=horizon_days,
                                ended_since=ended_since)
        rows = [r for r in rows
                if datetime.fromisoformat(str(r["published_at_utc"])) <= ctx.now]
        # One row per outage event (the outage list's rule): the exit and entry sides of an
        # interconnection point, published by two operators, are one outage counted once.
        ctx.cache[key] = outage_events(filter_rows_for_principal(ctx.caller.principal, rows))
    return ctx.cache[key]


def _zone_match(zone: str | None, countries: list[str]) -> bool:
    if not countries:
        return True
    hubs = zone_hubs(zone)
    held = {HUB_COUNTRY.get(h) for h in hubs} | ({"NO"} if is_norway(zone) else set())
    return bool(held & set(countries)) or (is_norway(zone) and bool(countries))


def outages(ctx: Ctx) -> SectionResult:
    from sqlalchemy import func

    from eurogas_nexus.application.freshness_contract import definition_by_id, receipt_state
    from eurogas_nexus.db.models import RemitUmmRecord

    result = _new("outages")
    horizon = 14 if ctx.plan.kind in {"daily", "situation"} else 31
    # A period report also lists what ended during the period (the live view does not).
    since = (datetime.combine(ctx.start, time.min, tzinfo=UTC)
             if ctx.plan.kind in {"weekly", "monthly"} else None)
    rows = [r for r in _outage_rows(ctx, horizon, since)
            if _zone_match(r.get("balancing_zone"), ctx.plan.countries)]
    received = ctx.session.query(func.max(RemitUmmRecord.ingested_at_utc)).scalar()
    definition = definition_by_id("src-remit-umm")
    state = receipt_state(definition, received, ctx.now) if definition else "never"
    if received is None:
        return _empty(result, "No REMIT messages are held", "Import REMIT UMMs")
    # A message whose unavailable capacity is zero (a cancelled derate) removes nothing.
    rows = [r for r in rows if r.get("unavailable_gwh_d") is None
            or float(r["unavailable_gwh_d"]) > 0]
    active = [r for r in rows if r["status"] == "active"]
    ended_rows = [r for r in rows if r["status"] == "ended"]
    rows = [r for r in rows if r["status"] != "ended"]

    def gwh(row) -> float | None:
        value = row.get("unavailable_gwh_d")
        return None if value is None else float(value)

    simulated = any(is_simulated_source(r.get("source_reference")) for r in rows)
    ranked = sorted(rows, key=lambda r: (r["status"] != "active", -(gwh(r) or 0.0)))
    largest = next((r for r in ranked if r["status"] == "active" and gwh(r)), None)
    norway = [r for r in active if norwegian_basis(r)]
    stats = {
        "active": len(active), "total": len(rows), "horizon_days": horizon,
        "active_gwh": round(sum(gwh(r) or 0.0 for r in active), 1),
        "largest": {"facility": largest["facility_name"],
                    "zone": zone_label(largest.get("balancing_zone")),
                    "gwh": gwh(largest), "end": largest.get("end_utc")} if largest else None,
        "norway_active": len(norway),
        "norway_gwh": round(sum(gwh(r) or 0.0 for r in norway), 1),
        "unconverted": sum(1 for r in rows if gwh(r) is None),
        "simulated": simulated,
    }
    table_rows = [
        {
            "facility": r["facility_name"],
            "zone": zone_label(r.get("balancing_zone")),
            "type": r.get("event_type"),
            "status": r["status"],
            "unavailable": round(gwh(r), 1) if gwh(r) is not None else r.get(
                "unavailable_capacity"),
            "unit": "GWh/d" if gwh(r) is not None else r.get("unit"),
            "start": r["start_utc"],
            "end": r.get("end_utc") or "open",
            "published": r["published_at_utc"],
        }
        for r in ranked[:15]
    ]
    result.simulated = simulated
    result.tables.append(table(
        "Active and upcoming outages, largest active first",
        [("facility", "Facility", "text"), ("zone", "Zone", "text"), ("type", "Type", "text"),
         ("status", "Status", "text"), ("unavailable", "Unavailable", "num"),
         ("unit", "Unit", "text"), ("start", "Start (UTC)", "datetime"),
         ("end", "End (UTC)", "datetime"), ("published", "Published", "datetime")],
        table_rows,
    ))
    bars = [r for r in ranked if r["status"] == "active" and gwh(r)][:10]
    if bars:
        result.charts.append({
            "type": "bar", "title": "Largest active outages", "unit": "GWh/d",
            "series": [{"name": "Unavailable",
                        "points": [[f"{r['facility_name']} "
                                    f"({zone_label(r.get('balancing_zone')) or '-'})",
                                    round(gwh(r), 1)] for r in bars]}],
        })
    result.sources.append(source("REMIT urgent market messages", "REMIT", received, state,
                                 dataset="Outages (REMIT UMM)"))
    result.raw = {
        "state": state, "norway_active": len(norway),
        "rows": [{"facility": r["facility_name"],
                  "operator": r.get("market_participant") or "",
                  "zone": zone_label(r.get("balancing_zone")),
                  "start": r["start_utc"], "end": r.get("end_utc"), "gwh": gwh(r),
                  "status": r["status"], "messages": r.get("message_count") or 1,
                  "norway": norwegian_basis(r)} for r in [*rows, *ended_rows]],
    }
    result.methods.append({"key": "remit_daily", "title": "Unavailable capacity per day",
                           "text": "The latest version of each message; capacity converted to "
                                   "GWh/d where the message's unit allows, else shown in its "
                                   "own unit."})
    return _apply(result, rules.outages(stats))


# ================================================================================= balance


def _balance_data(ctx: Ctx) -> tuple[dict | None, dict | None]:
    """(balance read, empty reason) with the Today read's licence check."""

    from eurogas_nexus.application.desk_today import _balance, _Read

    if "balance" in ctx.cache:
        return ctx.cache["balance"]
    held: dict[str, Any] = {}

    def reader() -> dict | None:
        # The balance page's own read, passed in by the caller (the route or a worker), so
        # the report and the page cannot disagree and this layer does not import the API.
        held["data"] = ctx.balance_reader() if ctx.balance_reader is not None else None
        return held["data"]

    checked = _balance(ctx.session, ctx.caller, ctx.now,
                       reader if ctx.balance_reader is not None else None, _Read())
    out = (None, checked["empty"]) if "empty" in checked else (held.get("data"), None)
    ctx.cache["balance"] = out
    return out


def balance(ctx: Ctx) -> SectionResult:
    from eurogas_nexus.application.freshness_contract import period_state
    from eurogas_nexus.application.pipeline_supply import LANDING_POINTS
    from eurogas_nexus.db.models import FlowObservationRecord as Flow
    from eurogas_nexus.db.models.observation import LngObservationRecord as Lng
    from eurogas_nexus.db.models.observation import StorageObservationRecord as Storage
    from eurogas_nexus.domain.fundamentals.balance import NWE_COUNTRIES

    result = _new("balance")
    data, empty = _balance_data(ctx)
    if empty:
        return _empty(result, empty["reason"], empty["action"])
    history = [h for h in (data or {}).get("history") or [] if h["day"] <= ctx.end.isoformat()]
    if not history:
        return _empty(result, "The balance needs ENTSOG flows, GIE storage and LNG",
                      "Connect ENTSOG and GIE in Sources")
    systems = (_sources_of(ctx, Storage, Storage.country.in_(NWE_COUNTRIES))
               | _sources_of(ctx, Lng, Lng.country.in_(NWE_COUNTRIES))
               | _sources_of(ctx, Flow, Flow.point_id.in_(sorted({p.point_id
                                                                  for p in LANDING_POINTS}))))
    simulated = bool(systems) and all(is_simulated_source(s) for s in systems)
    latest = history[-1]
    forecast = [f for f in (data or {}).get("forecast") or [] if f["day"] > latest["day"]]
    stats: dict[str, Any] = {
        "call": latest["call_gwh"], "day": latest["day"], "norway": latest["norway_gwh"],
        "lng": latest["lng_gwh"], "storage": latest["storage_net_withdrawal_gwh"],
        "simulated": simulated, "period_label": ctx.period_label,
    }
    in_period = [h for h in history if ctx.start.isoformat() <= h["day"] <= ctx.end.isoformat()]
    if ctx.period_label:
        if not in_period:
            return _empty(result, "No measured balance day in the period",
                          "Choose a period with ENTSOG and GIE data")
        stats["period_avg"] = _avg([h["call_gwh"] for h in in_period])
        stats["period_label"] = covered_label(
            ctx, [date.fromisoformat(h["day"]) for h in in_period])
    show_forecast = ctx.plan.kind in {"daily", "situation", "ask"} or ctx.end >= ctx.today - \
        timedelta(days=1)
    horizon = forecast[:7] if show_forecast else []
    if horizon:
        last = horizon[-1]
        methods = last.get("methods") or {}
        stats["forecast_call"] = last["call_gwh"]
        stats["forecast_day"] = last["day"]
        stats["forecast_method"] = (str(methods.get("call") or "").replace("_", " ")
                                   or "method stated in Methodology")
        stats["forecast_fill"] = last.get("fill_pct")
        result.forecast = True
    warnings = [w for w in ((data or {}).get("warnings") or [])]
    if warnings:
        stats["warning"] = warnings[0]
    window = [h for h in history if h["day"] >= ctx.chart_start.isoformat()]

    def comp(name: str, key: str, rows: list[dict], forecast_rows: bool = False) -> dict:
        return {"name": name + (" (forecast)" if forecast_rows else ""), "forecast": forecast_rows,
                "points": [[r["day"], r[key]] for r in rows]}

    result.charts.append({
        "type": "stacked_bar",
        "title": "NW Europe supply call by component (measured)",
        "unit": "GWh/d",
        "series": [comp("Norway", "norway_gwh", window), comp("LNG", "lng_gwh", window),
                   comp("Storage net withdrawal", "storage_net_withdrawal_gwh", window)],
    })
    if horizon:
        result.charts.append({
            "type": "line",
            "title": "Supply call: measured and forecast",
            "unit": "GWh/d",
            "series": [comp("Measured call", "call_gwh", window[-21:]),
                       comp("Call", "call_gwh", [window[-1], *horizon], True)],
        })
    sankey = _sankey(ctx, in_period or [latest])
    if sankey:
        result.charts.append(sankey)
    result.tables.append(table(
        "Measured balance by gas day, newest first",
        [("day", "Gas day", "date"), ("norway_gwh", "Norway", "num"), ("lng_gwh", "LNG", "num"),
         ("storage_net_withdrawal_gwh", "Storage net withdrawal", "signed"),
         ("call_gwh", "Supply call", "num"), ("unit", "Unit", "text")],
        [{**h, "unit": "GWh/d"} for h in reversed(window[-10:])],
    ))
    if horizon:
        result.tables.append(table(
            "Forecast (not a measurement)",
            [("day", "Gas day", "date"), ("call_gwh", "Call", "num"),
             ("norway_gwh", "Norway", "num"), ("lng_gwh", "LNG", "num"),
             ("storage_net_withdrawal_gwh", "Storage", "signed"),
             ("fill_pct", "Fill %", "num"), ("unit", "Unit", "text")],
            [{**f, "unit": "GWh/d"} for f in horizon],
        ))
        for component, text in sorted((horizon[0].get("methods") or {}).items()):
            result.methods.append({"key": f"forecast_{component}",
                                   "title": f"Forecast method: {component.replace('_', ' ')}",
                                   "text": str(text).replace("_", " ")})
    assumptions = (data or {}).get("assumptions") or {}
    for key in ("pipeline_landings_note", "storage_inventory_basis", "outage_adjustment"):
        if assumptions.get(key):
            result.methods.append({"key": key, "title": key.replace("_", " ").capitalize(),
                                   "text": str(assumptions[key])})
    result.warnings.extend(warnings)
    start = datetime.combine(date.fromisoformat(latest["day"]), time(6), tzinfo=UTC)
    state = period_state("GIE storage (AGSI)", start, ctx.now)
    for system in sorted(systems):
        result.sources.append(source("NW Europe balance inputs", system, latest["day"], state))
    result.simulated = simulated
    result.revisions = revisions_since(ctx, ("flow_observations", "storage_observations",
                                             "lng_observations"))
    result.raw = {"history": history, "forecast": horizon, "state": state}
    return _apply(result, rules.balance(stats))


def _sankey(ctx: Ctx, days: list[dict]) -> dict | None:
    """Average sources and uses of the NW Europe supply call over ``days``.

    Sources: continental landings and UK terminals (from the landings read), LNG send-out,
    net storage withdrawal. Uses: the supply call net of storage (what demand, exports and
    other supply leave to these sources) and net injection when storage fills.
    """

    if not days:
        return None
    supply = _landed(ctx)
    picked = [date.fromisoformat(h["day"]) for h in days]
    norway = supply.by_scope.get("norway", {})
    uk = supply.by_scope.get("uk_terminal", {})
    n = len(days)
    continental = sum(norway.get(d, 0.0) for d in picked) / n
    terminals = sum(uk.get(d, 0.0) for d in picked) / n
    pipeline = sum(h["norway_gwh"] for h in days) / n
    if abs(continental + terminals - pipeline) > max(1.0, 0.02 * pipeline):
        continental, terminals = pipeline, 0.0  # the scopes do not add up: one pipeline node
    lng_value = sum(h["lng_gwh"] for h in days) / n
    storage_net = sum(h["storage_net_withdrawal_gwh"] for h in days) / n
    withdrawal = max(storage_net, 0.0)
    injection = max(-storage_net, 0.0)
    sources_ = [("continental", "Norway: continental landings", continental),
                ("terminals", "UK terminals (Norway and UK shelf)", terminals),
                ("lng", "LNG send-out", lng_value),
                ("withdrawal", "Storage net withdrawal", withdrawal)]
    sources_ = [s for s in sources_ if s[2] > 0]
    total = sum(v for _, _, v in sources_)
    if total <= 0:
        return None
    uses = [("demand", "Demand, exports and other flows", total - injection),
            ("injection", "Storage net injection", injection)]
    uses = [u for u in uses if u[2] > 0]
    links = [
        {"source": sid, "target": uid, "value": round(sv * uv / total, 1)}
        for sid, _, sv in sources_ for uid, _, uv in uses
    ]
    label = ctx.period_label or f"{days[-1]['day']}"
    return {
        "type": "sankey",
        "title": f"Where the supply call came from and went ({label}, average)",
        "unit": "GWh/d",
        "nodes": [{"id": s, "label": name, "side": "source"} for s, name, _ in sources_]
        + [{"id": u, "label": name, "side": "use"} for u, name, _ in uses],
        "links": links,
        "description": "Sources of the NW Europe supply call on the left, uses on the right; "
                       "each use is drawn from the sources in proportion. The table below "
                       "lists every flow.",
    }


# ================================================================================= book


def _book(ctx: Ctx):
    from eurogas_nexus.application.desk_today import _book as book_read
    from eurogas_nexus.application.desk_today import _Read

    if "book" not in ctx.cache:
        read = _Read()
        ctx.cache["book"] = (book_read(ctx.caller, ctx.today, read), read)
    return ctx.cache["book"]


def _hub_ok(ctx: Ctx, hub: str) -> bool:
    return not ctx.plan.hubs or hub in ctx.plan.hubs


def book_position(ctx: Ctx) -> SectionResult:
    from eurogas_nexus.application.desk_today import (
        BOOK_HORIZON_MONTHS,
        _month_start,
        front_month_label,
    )
    from eurogas_nexus.domain.portfolio.position_ladder import build_ladder
    from eurogas_nexus.domain.risk.method_notes import method_note

    result = _new("book_position")
    book, _ = _book(ctx)
    positions = {h: v for h, v in book.positions.items() if _hub_ok(ctx, h)}
    if not positions:
        return _empty(result, "No position is held in the books you may see", "Open Position")
    end = _month_start(ctx.today, BOOK_HORIZON_MONTHS + 1) - timedelta(days=1)
    legs = [leg for leg in book.inputs.legs if _hub_ok(ctx, leg.hub.upper())]
    ladder = build_ladder(legs, horizon_start=ctx.today, horizon_end=end)
    months = sorted({row.month for row in ladder})[:12]
    hubs = sorted(positions)
    cells: dict[tuple[str, str], float] = defaultdict(float)
    for row in ladder:
        cells[(row.month, row.hub)] += row.net_mwh
    rows = []
    for month in months:
        first = date.fromisoformat(month + "-01")
        days = (_month_start(first, 1) - first).days
        if first.year == ctx.today.year and first.month == ctx.today.month:
            days = (_month_start(first, 1) - ctx.today).days
        rows.append({"product": f"{first:%b-%y}",
                     **{hub: round(cells.get((month, hub), 0.0) / days, 0) for hub in hubs}})
    result.tables.append(table(
        T("Net position by delivery month, MWh/d (long positive)",
          "按交割月份的净头寸，MWh/d（多头为正）"),
        [("product", T("Product", "合约"), "text")] + [(hub, hub, "signed") for hub in hubs],
        rows,
    ))
    result.tables.append(table(
        T("Net position today and front month", "今日及近月净头寸"),
        [("hub", T("Hub", "枢纽"), "text"), ("today", T("Today", "今日"), "signed"),
         ("front_month", front_month_label(ctx.today), "signed"),
         ("unit", T("Unit", "单位"), "text")],
        [{"hub": h, "today": round(v["today"], 0), "front_month": round(v["front_month"], 0),
          "unit": "MWh/d"} for h, v in sorted(positions.items())],
    ))
    result.methods.append({"key": "net_position", "title": "Net position",
                           "text": method_note("net_position")["summary"]})
    result.sources.append(source("Contracts and filled trades in the books visible to the "
                                 "report", "operator-input", ctx.now, "current"))
    result.books = sorted({leg.book_id for leg in legs if leg.book_id})
    stats = {"hubs": [{"hub": h, **v} for h, v in sorted(
        positions.items(), key=lambda kv: -abs(kv[1]["today"]))],
        "front_month": front_month_label(ctx.today)}
    return _apply(result, rules.position(stats))


def book_pnl(ctx: Ctx) -> SectionResult:
    from eurogas_nexus.application.desk_today import _book_row, _prices, _Read
    from eurogas_nexus.application.projections.portfolio_reads import pnl_snapshots
    from eurogas_nexus.domain.ontology.markets import quote_currency
    from eurogas_nexus.domain.risk.method_notes import method_note

    result = _new("book_pnl")
    book, _ = _book(ctx)
    read = _Read()
    hubs_out = []
    if book.positions:
        prices = _prices(ctx.caller, ctx.now, book, read)
        row = _book_row(ctx.today, book, prices, read)
        for hub in row["hubs"]:
            if not _hub_ok(ctx, hub["hub"]):
                continue
            pnl = hub["day_pnl_change"]
            if "empty" in pnl:
                hubs_out.append({"hub": hub["hub"], "change": None,
                                 "currency": quote_currency(hub["hub"]),
                                 "reason": pnl["empty"]["reason"]})
            else:
                hubs_out.append({"hub": hub["hub"], "change": pnl["value"],
                                 "currency": pnl["unit"], "as_of": pnl["as_of"],
                                 "simulated": pnl["simulated"]})
                result.simulated = result.simulated or pnl["simulated"]
    latest: dict[str, Any] = {}
    previous: dict[str, Any] = {}
    for snap in pnl_snapshots(ctx.session, principal_id=ctx.caller.principal_id):
        valued = _aware(snap.valuation_time_utc)
        if valued is not None and valued > ctx.now:
            continue
        if snap.portfolio_id not in latest:
            latest[snap.portfolio_id] = snap
        elif snap.portfolio_id not in previous:
            previous[snap.portfolio_id] = snap
    snapshots = [
        {"portfolio": pid, "pnl": snap.indicative_pnl_gbp,
         "change": (snap.indicative_pnl_gbp - previous[pid].indicative_pnl_gbp)
         if pid in previous else None,
         "valued": _iso(snap.valuation_time_utc),
         "simulated": is_simulated_source(snap.source_system)}
        for pid, snap in sorted(latest.items())
    ]
    if not hubs_out and not snapshots:
        return _empty(result, "No P&L figure is held for the books you may see", "Open P&L")
    result.tables.append(table(
        "Day P&L change on the open position",
        [("hub", "Hub", "text"), ("change", "Day change", "signed"),
         ("currency", "Currency", "text"), ("reason", "Not valued because", "text")],
        hubs_out,
    ))
    if snapshots:
        result.tables.append(table(
            "Imported indicative P&L valuations",
            [("portfolio", "Portfolio", "text"), ("pnl", "Indicative P&L (GBP)", "num"),
             ("change", "Since previous (GBP)", "signed"), ("valued", "Valued", "datetime")],
            snapshots,
        ))
        result.simulated = result.simulated or any(s["simulated"] for s in snapshots)
    result.methods.append({"key": "day_pnl_change", "title": "Day P&L change",
                           "text": method_note("day_pnl_change")["summary"]})
    result.sources.append(source("Position ladder and daily closes", "operator-input", ctx.now,
                                 "current"))
    result.books = sorted({leg.book_id for leg in book.inputs.legs if leg.book_id}) \
        if book.inputs else []
    return _apply(result, rules.pnl({"hubs": hubs_out, "snapshots": snapshots,
                                     "simulated": result.simulated}))


def book_limits(ctx: Ctx) -> SectionResult:
    from eurogas_nexus.application.desk_today import _limits_visibility
    from eurogas_nexus.application.limits_service import credit_exposure_rows, mandate_usage_rows
    from eurogas_nexus.domain.risk.method_notes import method_note

    result = _new("book_limits")
    credit = credit_exposure_rows(ctx.caller, ctx.today)
    mandates = mandate_usage_rows(ctx.caller, ctx.today)
    visible = _limits_visibility()
    demo = any(is_simulated_marks_warning(w) for w in credit.warnings)
    rows, books = [], set()
    for kind, rows_in in (("credit", credit), ("mandate", mandates)):
        for row, row_books in zip(rows_in.rows, rows_in.books, strict=True):
            if not visible(row_books):
                continue
            books |= {b for b in row_books if b}
            if kind == "credit":
                rows.append({"name": row["counterparty"], "kind": "credit line",
                             "status": row["status"], "utilisation_pct": row["utilisation_pct"],
                             "headroom": row["headroom"], "unit": row["currency"],
                             "simulated": demo and credit.marks_as_of is not None})
            else:
                cap = row.get("max_net_mwh_per_month")
                rows.append({"name": row["name"], "kind": "mandate", "status": row["status"],
                             "utilisation_pct": row.get("utilisation_pct"),
                             "headroom": None if cap is None else round(
                                 float(cap) - float(row["largest_net_mwh"]), 1),
                             "unit": "MWh", "simulated": False})
    if not rows:
        return _empty(result, "No credit line or mandate is held that you may see",
                      "Risk adds them under Limits")
    rank = {"breach": 0, "expired": 1, "watch": 2}
    rows.sort(key=lambda r: (rank.get(r["status"], 9), -(r["utilisation_pct"] or 0)))
    result.tables.append(table(
        T("Limits, breaches and watches first", "限额（超限与观察在前）"),
        [("name", T("Limit", "限额"), "text"), ("kind_label", T("Kind", "类型"), "text"),
         ("status_label", T("Status", "状态"), "text"),
         ("utilisation_pct", T("Used %", "已使用 %"), "num"),
         ("headroom", T("Headroom", "余量"), "signed"), ("unit", T("Unit", "单位"), "text")],
        [{**r, "kind_label": _LIMIT_WORDS.get(r["kind"], (r["kind"],) * 2)[int(zh())],
          "status_label": _LIMIT_WORDS.get(r["status"], (r["status"],) * 2)[int(zh())]}
         for r in rows],
    ))
    result.simulated = any(r["simulated"] for r in rows)
    for key in ("credit_exposure", "mandate_usage"):
        result.methods.append({"key": key, "title": key.replace("_", " ").capitalize(),
                               "text": method_note(key)["summary"]})
    result.sources.append(source("Credit lines, mandates and the position ladder",
                                 "operator-input", ctx.now, "current"))
    result.books = sorted(books)
    return _apply(result, rules.limits({"rows": rows}))


_LIMIT_WORDS = {"credit line": ("credit line", "信用额度"), "mandate": ("mandate", "授权"),
                "breach": ("breach", "超限"), "watch": ("watch", "观察"), "ok": ("ok", "正常"),
                "expired": ("expired", "已到期")}


def book_contracts(ctx: Ctx) -> SectionResult:
    from eurogas_nexus.application.position_inputs import gas_year_window

    result = _new("book_contracts")
    book, _ = _book(ctx)
    contracts = list(getattr(book.inputs, "contracts", None) or [])
    rows, books = [], set()
    horizon = ctx.today + timedelta(days=800)
    for contract in contracts:
        window = gas_year_window(contract.gas_year, horizon)
        if window is None or not (window[0] <= ctx.today <= window[1]):
            continue
        rows.append({
            "name": contract.contract_name,
            "point": contract.delivery_point_name,
            "gas_year": contract.gas_year,
            "mwh_per_day": float(contract.delivery_quantity_mwh_per_day),
            "price": float(contract.contract_price_gbp_mwh),
            "unit": f"{contract.contract_price_currency or 'GBP'}/MWh",
            "book": contract.book_id or "",
        })
        if contract.book_id:
            books.add(contract.book_id)
    if not rows:
        return _empty(result, "No supply contract is in effect in the books you may see",
                      "Open Contracts")
    result.tables.append(table(
        "Contracts in effect today",
        [("name", "Contract", "text"), ("point", "Delivery point", "text"),
         ("gas_year", "Gas year", "text"), ("mwh_per_day", "MWh/d", "num"),
         ("price", "Price", "num"), ("unit", "Price unit", "text"), ("book", "Book", "text")],
        rows,
    ))
    result.sources.append(source("Contract register", "operator-input", ctx.now, "current"))
    result.books = sorted(books)
    return _apply(result, rules.contracts({"rows": rows}))


# ================================================================================= situation


#: Hubs a balancing zone's outage touches first (Norway lands into four markets).
ZONE_HUBS = {"NO": ("NBP", "TTF", "THE", "ZTP"), "NORWAY": ("NBP", "TTF", "THE", "ZTP"),
             "UK": ("NBP",), "GB": ("NBP",), "NL": ("TTF",), "DE": ("THE",), "BE": ("ZTP",),
             "FR": ("PEG",), "DK": ("ETF",)}
#: Balancing-zone and trading-point EIC codes REMIT messages give, to the zone's hub. From the
#: shipped ENTSOG reference network (VTPs) and the published market-area codes.
ZONE_EIC_HUBS = {
    "21YNL----TTF---1": "TTF", "37Y005053MH0000R": "THE", "37Z005053MH0000D": "THE",
    "21YGB-UKGASGRIDW": "NBP", "21Y0000000001278": "PEG", "21Z000000000248J": "ZTP",
    "21Y---A001A003-5": "ETF",
}
HUB_COUNTRY = {"TTF": "NL", "THE": "DE", "NBP": "GB", "PEG": "FR", "ZTP": "BE", "ETF": "DK"}


def _zone_tokens(zone: str | None) -> list[str]:
    return [t for t in str(zone or "").upper().replace(";", ",").replace("/", ",")
            .replace(" ", ",").split(",") if t]


def is_norway(zone: str | None) -> bool:
    return any(t in {"NO", "NORWAY"} or t.startswith("NO-") for t in _zone_tokens(zone))


#: Assets whose name ties an outage to Norwegian supply: Norwegian fields and processing
#: plants, the export pipelines and the landing terminals that take them (a UK terminal also
#: lands UK shelf gas, which the basis says).
NORWEGIAN_ASSETS = (
    "troll", "kollsnes", "karsto", "kårstø", "nyhamna", "ormen lange", "aasta hansteen",
    "oseberg", "heimdal", "gullfaks", "statfjord", "sleipner", "asgard", "åsgard", "kvitebjorn",
    "kvitebjørn", "gina krog", "martin linge", "johan sverdrup", "draugen", "snohvit",
    "snøhvit", "hammerfest", "langeled", "zeepipe", "europipe", "norpipe", "franpipe",
    "vesterled", "gassled", "polarled", "norwegian shelf", "norwegian continental shelf",
)
LANDING_TERMINALS = ("emden", "dornum", "zeebrugge zpt", "dunkerque", "easington", "st fergus")


def norwegian_basis(row: dict) -> str | None:
    """Why an outage counts as Norwegian supply, or ``None``: its balancing zone is Norway,
    its asset is a Norwegian field, plant or export pipeline, or it is a landing terminal for
    Norwegian gas. Deterministic and stated, so a report can say how it attributed."""

    if is_norway(row.get("balancing_zone")):
        return "zone"
    name = str(row.get("facility_name") or "").casefold()
    if any(word in name for word in NORWEGIAN_ASSETS):
        return "asset"
    if any(word in name for word in LANDING_TERMINALS):
        return "landing terminal"
    return None


def zone_hubs(zone: str | None) -> list[str]:
    """Hubs a REMIT balancing zone touches: by hub name, EIC code or country code."""

    from eurogas_nexus.application.reports.catalogue import resolve_hub

    hubs: list[str] = []
    for token in _zone_tokens(zone):
        found = ([ZONE_EIC_HUBS[token]] if token in ZONE_EIC_HUBS
                 else [resolve_hub(token)] if resolve_hub(token)
                 else list(ZONE_HUBS.get(token, ())))
        hubs += [h for h in found if h and h not in hubs]
    return hubs


def zone_label(zone: str | None) -> str | None:
    """``TTF (NL)`` for a zone the report can name; the zone as published otherwise."""

    if is_norway(zone):
        return "Norway"
    hubs = zone_hubs(zone)
    if hubs:
        return ", ".join(f"{h} ({HUB_COUNTRY[h]})" if h in HUB_COUNTRY else h for h in hubs)
    return zone


def situation_event(ctx: Ctx) -> SectionResult:
    result = _new("situation_event")
    if ctx.plan.outage_id:
        return _situation_outage(ctx, result)
    return _situation_alert(ctx, result)


def find_outage(ctx: Ctx, event_id: str) -> dict | None:
    """The outage event a situation report is about, by its message id or the id of any
    message grouped into the event (a link may carry either side's message)."""

    rows = _outage_rows(ctx, 400)
    wanted = str(event_id)
    return next((r for r in rows if str(r["event_id"]) == wanted
                 or wanted in {str(m) for m in r.get("messages") or []}), None)


def _situation_outage(ctx: Ctx, result: SectionResult) -> SectionResult:
    row = find_outage(ctx, ctx.plan.outage_id or "")
    if row is None:
        return _empty(result, "The outage is not open or upcoming, or is not visible to you",
                      "Open Outages")
    start = datetime.fromisoformat(str(row["start_utc"]))
    gwh = row.get("unavailable_gwh_d")
    stats: dict[str, Any] = {
        "facility": row["facility_name"], "zone": zone_label(row.get("balancing_zone")),
        "status": row["status"], "start": row["start_utc"], "end": row.get("end_utc"),
        "gwh": None if gwh is None else round(float(gwh), 1),
        "capacity": row.get("unavailable_capacity"), "unit": row.get("unit"),
        "published": row["published_at_utc"], "version": row.get("version"),
        "event_type": row.get("event_type"),
        "simulated": is_simulated_source(row.get("source_reference")),
    }
    if is_norway(row.get("balancing_zone")):
        supply = _landed(ctx)
        days = sorted(supply.by_day)
        before_days = [d for d in days if start.date() - timedelta(days=7) <= d < start.date()]
        after_days = [d for d in days if d >= start.date()]
        if len(before_days) >= 4:
            stats["before"] = round(_avg([supply.by_day[d] for d in before_days]), 1)
            stats["before_until"] = before_days[-1].isoformat()
            if after_days and row["status"] == "active":
                stats["after"] = round(_avg([supply.by_day[d] for d in after_days]), 1)
            if stats["gwh"] and stats["before"]:
                stats["share_pct"] = round(100 * stats["gwh"] / stats["before"], 0)
            result.charts.append({
                "type": "line", "unit": "GWh/d",
                "title": T("Norwegian landings around the outage", "停运前后的挪威到岸量"),
                "series": [{"name": T("Landed", "到岸量"),
                            "points": [[d.isoformat(), round(supply.by_day[d], 1)]
                                       for d in days if d >= start.date() - timedelta(days=14)]}],
            })
    hubs = zone_hubs(row.get("balancing_zone"))
    result.tables.append(table(
        "The message",
        [("field", "", "text"), ("value", "", "text")],
        [
            {"field": "Facility", "value": row["facility_name"]},
            {"field": "Zone", "value": f"{zone_label(row.get('balancing_zone'))} "
                                       f"({row.get('balancing_zone') or 'n/a'})"},
            {"field": "Type", "value": row.get("event_type") or "n/a"},
            {"field": "Unavailable", "value": f"{stats['gwh']} GWh/d" if stats["gwh"] is not None
             else f"{row.get('unavailable_capacity')} {row.get('unit') or ''}"},
            {"field": "Technical capacity", "value": f"{row.get('technical_capacity')} "
                                                     f"{row.get('unit') or ''}"},
            {"field": "Start (UTC)", "value": row["start_utc"]},
            {"field": "End (UTC)", "value": row.get("end_utc") or "open"},
            {"field": "Published", "value": row["published_at_utc"]},
            {"field": "Version", "value": str(row.get("version"))},
            {"field": "Reason", "value": row.get("description") or "not stated"},
            {"field": "Hubs it touches first", "value": ", ".join(hubs) or "n/a"},
        ],
    ))
    result.tables.append(table(
        "What to check",
        [("item", "", "text")],
        [{"item": text} for text in (
            T(f"The next REMIT version for {row['facility_name']}: end date and size can "
              "change.", f"{row['facility_name']}的下一版REMIT消息：结束日期与规模可能变化。"),
            T("Landings on the next complete gas day against the seven-day average above.",
              "下一个完整燃气日的到岸量与上文七日均值的对比。")
            if is_norway(row.get("balancing_zone")) else
            T("Flows at the affected points on the next complete gas day.",
              "下一个完整燃气日受影响点位的流量。"),
            T(f"Prices at {', '.join(hubs)} in the Prices section.",
              f"价格部分中{'、'.join(hubs)}的价格。") if hubs else
            T("Prices in the Prices section.", "价格部分中的价格。"),
        )],
    ))
    result.simulated = stats["simulated"]
    result.sources.append(source("REMIT urgent market message", "REMIT",
                                 row["published_at_utc"], "current",
                                 dataset="Outages (REMIT UMM)"))
    return _apply(result, rules.situation_outage(stats))


def _situation_alert(ctx: Ctx, result: SectionResult) -> SectionResult:
    from eurogas_nexus.application.alert_scope import alert_visibility
    from eurogas_nexus.db.models import MonitoringAlertRecord

    row = ctx.session.get(MonitoringAlertRecord, ctx.plan.alert_id)
    if row is None or not alert_visibility(ctx.session)(row):
        return _empty(result, "The alert does not exist or is not visible to you", "Open Events")
    if ctx.plan.audience == "shareable" and row.category != "physical":
        return _empty(result, "Only a physical-market alert can open a shareable report",
                      "Choose the internal audience")
    stats = {"severity": row.severity, "title": row.title_en, "message": row.message_en,
             "detected": _iso(row.detected_at_utc), "occurrences": row.occurrence_count or 1,
             "status": row.status, "simulated": bool(row.simulated)}
    evidence = {k: v for k, v in (row.evidence_snapshot or {}).items()
                if not str(k).endswith("_id") and not str(k).endswith("_ids")
                and isinstance(v, str | int | float)}
    result.tables.append(table(
        "The alert",
        [("field", "", "text"), ("value", "", "text")],
        [{"field": "Category", "value": row.category},
         {"field": "Type", "value": row.alert_type},
         {"field": "Severity", "value": row.severity},
         {"field": "Detected", "value": _iso(row.detected_at_utc)},
         *[{"field": str(k).replace("_", " "), "value": str(v)} for k, v in evidence.items()]],
    ))
    result.simulated = bool(row.simulated)
    result.sources.append(source("Eurogas Nexus monitoring", "operator-input",
                                 row.updated_at_utc or row.detected_at_utc, "current"))
    return _apply(result, rules.situation_alert(stats))


BUILDERS: dict[str, Callable[[Ctx], SectionResult]] = {
    "situation_event": situation_event,
    "prices": prices,
    "alerts": alerts,
    "pipeline_supply": pipeline_supply,
    "lng": lng,
    "storage": storage,
    "power_burn": power_burn,
    "outages": outages,
    "balance": balance,
    "book_position": book_position,
    "book_pnl": book_pnl,
    "book_limits": book_limits,
    "book_contracts": book_contracts,
}
