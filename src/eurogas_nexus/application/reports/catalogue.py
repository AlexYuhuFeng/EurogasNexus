"""The report catalogue: report kinds, the typed sections a report is assembled from, and plans.

A market report is *assembled*, never written by a model. A report definition is an ordered
list of sections from :data:`SECTIONS`; each section type fixes where its data comes from
(an existing entitled read), how it is shown (the chart type is the catalogue's, not a
model's) and whether it may appear in a report shared outside the desk. A plan (from the
generate form, a schedule or an asked question) is validated here before anything is read.

Audience is structural: a ``shareable`` report never *gathers* an ``internal_only`` section,
so positions, P&L, limits, counterparties and contract terms cannot reach it by a styling
mistake.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

#: Bumped when the renderer's output changes; stored with every report.
TEMPLATE_VERSION = "market-report/3"

KINDS = ("daily", "weekly", "monthly", "situation", "ask")
DAILY_VARIANTS = ("morning", "eod")
AUDIENCES = ("internal", "shareable")
MAX_HUBS = 8
MAX_COUNTRIES = 7


@dataclass(frozen=True)
class SectionType:
    key: str
    title: str
    #: The house-style group the section is printed under.
    group: str
    #: Where the figures come from (named in the catalogue for the user and the docs).
    data_source: str
    #: The presentation the catalogue fixes for it.
    charts: tuple[str, ...]
    #: Only in an ``internal`` report: book data (positions, P&L, limits, contracts).
    internal_only: bool = False
    #: Parameters the section honours.
    params: tuple[str, ...] = ()
    description: str = ""
    #: Words a question may use for it (the deterministic plan fallback).
    keywords: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "title": self.title,
            "group": self.group,
            "data_source": self.data_source,
            "charts": list(self.charts),
            "internal_only": self.internal_only,
            "params": list(self.params),
            "description": self.description,
        }


GROUPS = (
    "What happened",
    "Prices",
    "Supply",
    "Demand",
    "Infrastructure and outages",
    "Balance and outlook",
    "Our book",
)

SECTIONS: tuple[SectionType, ...] = (
    SectionType(
        "situation_event", "The event", "What happened",
        "The alert or REMIT outage the report was opened from",
        ("table",), params=("alert_id", "outage_id"),
        description="What happened, where, how large, since when and until when.",
    ),
    SectionType(
        "prices", "Hub prices", "Prices",
        "Daily closes the caller is licensed for (front month, else day-ahead)",
        ("line", "table"), params=("hubs", "period"),
        description="Close, day change, change over the period, range and a year earlier.",
        keywords=("price", "prices", "close", "closes", "curve", "spread", "front month",
                  "价格", "收盘"),
    ),
    SectionType(
        "alerts", "Open alerts", "What happened",
        "Open monitoring alerts the caller may see",
        ("table",), params=(),
        description="Critical and watch alerts open now (market alerts only when shareable).",
        keywords=("alert", "alerts", "告警"),
    ),
    SectionType(
        "pipeline_supply", "Norwegian pipeline landings", "Supply",
        "ENTSOG physical flows at the registry's landing points",
        ("stacked_area", "table"), params=("period",),
        description="Landed energy per gas day: continental landings and UK terminals.",
        keywords=("norway", "norwegian", "pipeline", "landing", "landings", "gassco",
                  "supply", "挪威", "管道"),
    ),
    SectionType(
        "lng", "LNG send-out", "Supply",
        "GIE ALSI (and National Gas for GB) send-out by country",
        ("stacked_bar", "table"), params=("countries", "period"),
        description="Regasified LNG sent out per gas day, by country.",
        keywords=("lng", "regas", "send-out", "sendout", "terminal", "液化天然气"),
    ),
    SectionType(
        "storage", "Storage", "Supply",
        "GIE AGSI storage: facilities that publish a working capacity",
        ("line", "table"), params=("period",),
        description="NW Europe fill against the same days a year earlier and the EU target.",
        keywords=("storage", "stock", "inventory", "fill", "injection", "withdrawal",
                  "储气", "库存"),
    ),
    SectionType(
        "power_burn", "Gas-fired power", "Demand",
        "ENTSO-E and Elexon generation by fuel (gas)",
        ("stacked_bar", "table"), params=("countries", "period"),
        description="Electricity generated from gas per day, by bidding zone.",
        keywords=("power", "power burn", "gas-fired", "generation", "demand", "电力", "需求"),
    ),
    SectionType(
        "outages", "Outages", "Infrastructure and outages",
        "REMIT urgent market messages (latest version of each)",
        ("bar", "table"), params=("countries",),
        description="Active and upcoming unavailability with its size and dates.",
        keywords=("outage", "outages", "maintenance", "remit", "umm", "unavailable",
                  "停运", "检修"),
    ),
    SectionType(
        "balance", "NW Europe balance and outlook", "Balance and outlook",
        "The NW Europe balance read (/api/market/nwe-balance) and its forecast",
        ("stacked_bar", "line", "sankey", "table"), params=("period",),
        description="The supply call on Norway, LNG and storage, its sources and uses, and "
        "the forecast with its method and warnings.",
        keywords=("balance", "outlook", "forecast", "winter", "supply call", "平衡", "预测"),
    ),
    SectionType(
        "book_position", "Position", "Our book",
        "The position ladder over the books the caller may see",
        ("ladder", "table"), internal_only=True,
        description="Net position today and by delivery month, per hub.",
        keywords=("position", "positions", "our book", "exposure", "ladder", "头寸"),
    ),
    SectionType(
        "book_pnl", "P&L", "Our book",
        "Day P&L change on the open position; imported P&L valuations",
        ("table",), internal_only=True,
        description="Day P&L change per hub and the latest indicative P&L.",
        keywords=("p&l", "pnl", "profit", "loss", "损益"),
    ),
    SectionType(
        "book_limits", "Limits", "Our book",
        "Credit lines and trader mandates the caller may see in full",
        ("table",), internal_only=True,
        description="Utilisation and headroom; breaches and watches first.",
        keywords=("limit", "limits", "credit", "mandate", "限额"),
    ),
    SectionType(
        "book_contracts", "Contracts in effect", "Our book",
        "Upstream supply contracts in the caller's books, delivering today",
        ("table",), internal_only=True,
        description="Delivery point, gas year, quantity and price of each contract in effect.",
        keywords=("contract", "contracts", "合同"),
    ),
)
SECTION_BY_KEY = {section.key: section for section in SECTIONS}
BOOK_SECTIONS = tuple(s.key for s in SECTIONS if s.internal_only)

#: Each kind's default section list, in print order.
DEFAULT_SECTIONS: dict[str, tuple[str, ...]] = {
    "daily": ("prices", "alerts", "pipeline_supply", "lng", "storage", "power_burn", "outages",
              "balance", *BOOK_SECTIONS),
    "weekly": ("prices", "pipeline_supply", "lng", "storage", "power_burn", "outages",
               "balance", *BOOK_SECTIONS),
    "monthly": ("prices", "pipeline_supply", "lng", "storage", "power_burn", "outages",
                "balance", *BOOK_SECTIONS),
    "situation": ("situation_event", "outages", "pipeline_supply", "balance", "prices",
                  "book_position"),
    "ask": (),
}


class PlanError(ValueError):
    """A plan the catalogue refuses; ``code`` names why (shown to the user)."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass
class ReportPlan:
    """What will be generated: validated, so every reader can trust it."""

    kind: str
    audience: str
    sections: list[str]
    variant: str | None = None
    hubs: list[str] = field(default_factory=list)
    countries: list[str] = field(default_factory=list)
    period_start: date | None = None
    period_end: date | None = None
    alert_id: str | None = None
    outage_id: str | None = None
    question: str | None = None
    #: Print the data annex: ``None`` is the kind's default (weekly and monthly only).
    annex: bool | None = None
    #: Sections dropped while validating, with the reason (printed in Methodology).
    notes: list[str] = field(default_factory=list)
    #: Optional reporting currency and energy unit: prices keep their native unit and gain
    #: a converted column (``None``: native only).
    currency: str | None = None
    energy_unit: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "audience": self.audience,
            "variant": self.variant,
            "sections": list(self.sections),
            "hubs": list(self.hubs),
            "countries": list(self.countries),
            "period_start": self.period_start.isoformat() if self.period_start else None,
            "period_end": self.period_end.isoformat() if self.period_end else None,
            "alert_id": self.alert_id,
            "outage_id": self.outage_id,
            "question": self.question,
            "annex": self.annex,
            "notes": list(self.notes),
            "currency": self.currency,
            "energy_unit": self.energy_unit,
        }


def known_hubs() -> set[str]:
    from eurogas_nexus.domain.ontology.identity import _hub_names

    return {canonical for canonical, _ in _hub_names().values()}


def resolve_hub(text: str) -> str | None:
    """A hub code or alias as the ontology resolves it, exactly; ``None`` if unknown.

    ETF (Danish hub) and TTF are different hubs: nothing here is fuzzy.
    """

    from eurogas_nexus.domain.ontology.identity import _hub_names

    hit = _hub_names().get(str(text).strip().upper())
    return hit[0] if hit else None


def default_period(kind: str, now: datetime) -> tuple[date, date]:
    """The period a kind covers when none is given.

    Daily: the current gas day's date. Weekly: the seven days to yesterday. Monthly: the
    last full calendar month.
    """

    today = now.astimezone(UTC).date()
    if kind == "weekly":
        return today - timedelta(days=7), today - timedelta(days=1)
    if kind == "monthly":
        first_this = today.replace(day=1)
        last = first_this - timedelta(days=1)
        return last.replace(day=1), last
    if kind in {"situation", "ask"}:
        return today - timedelta(days=7), today
    return today, today


def validate_plan(raw: dict[str, Any], *, now: datetime) -> ReportPlan:
    """A :class:`ReportPlan` from user, schedule or model input; raises :class:`PlanError`."""

    kind = str(raw.get("kind") or "daily")
    if kind not in KINDS:
        raise PlanError("unknown_kind", f"Unknown report kind {kind!r}")
    audience = str(raw.get("audience") or "internal")
    if audience not in AUDIENCES:
        raise PlanError("unknown_audience", f"Unknown audience {audience!r}")
    variant = raw.get("variant")
    if kind == "daily":
        variant = variant or "morning"
        if variant not in DAILY_VARIANTS:
            raise PlanError("unknown_variant", f"Unknown daily variant {variant!r}")
    else:
        variant = None
    requested = raw.get("sections")
    explicit = requested is not None
    sections = list(requested) if explicit else list(DEFAULT_SECTIONS[kind])
    notes: list[str] = []
    seen: list[str] = []
    for key in sections:
        if key not in SECTION_BY_KEY:
            raise PlanError("unknown_section", f"Unknown section {key!r}")
        if key not in seen:
            seen.append(key)
    sections = seen
    if audience == "shareable":
        internal = [key for key in sections if SECTION_BY_KEY[key].internal_only]
        # Book sections are left out of a report for distribution (the form leaves them out
        # too); only a plan of nothing but book sections is refused, below, as empty.
        if internal and explicit and not raw.get("drop_internal") and not [
                key for key in sections if not SECTION_BY_KEY[key].internal_only]:
            raise PlanError(
                "internal_section_in_shareable",
                "A report for distribution cannot contain " + ", ".join(
                    SECTION_BY_KEY[key].title for key in internal
                ) + "; choose the internal audience",
            )
        if internal:
            notes.append("Our book is not part of a shareable report.")
        sections = [key for key in sections if not SECTION_BY_KEY[key].internal_only]
    if kind == "situation":
        if not (raw.get("alert_id") or raw.get("outage_id")):
            raise PlanError("situation_needs_subject", "A situation report needs an alert or "
                            "an outage")
        if "situation_event" not in sections:
            sections.insert(0, "situation_event")
    elif "situation_event" in sections:
        sections.remove("situation_event")
    if not sections:
        raise PlanError("no_sections", "The plan has no sections")
    hubs: list[str] = []
    for text in raw.get("hubs") or []:
        hub = resolve_hub(text)
        if hub is None:
            raise PlanError("unknown_hub", f"Unknown hub {text!r}")
        if hub not in hubs:
            hubs.append(hub)
    if len(hubs) > MAX_HUBS:
        raise PlanError("too_many_hubs", f"At most {MAX_HUBS} hubs")
    from eurogas_nexus.domain.fundamentals.balance import NWE_COUNTRIES

    countries: list[str] = []
    for text in raw.get("countries") or []:
        code = str(text).strip().upper()
        if code not in NWE_COUNTRIES:
            raise PlanError("unknown_country", f"Country {text!r} is not in the NW Europe scope "
                            f"({', '.join(NWE_COUNTRIES)})")
        if code not in countries:
            countries.append(code)
    start, end = default_period(kind, now)
    if raw.get("period_start") or raw.get("period_end"):
        try:
            start = _day(raw.get("period_start")) or start
            end = _day(raw.get("period_end")) or end
        except ValueError as exc:
            raise PlanError("bad_period", "Period dates must be YYYY-MM-DD") from exc
        if end < start:
            raise PlanError("bad_period", "The period ends before it starts")
        if (end - start).days > 400:
            raise PlanError("bad_period", "A report covers at most 400 days")
        if end > now.astimezone(UTC).date() + timedelta(days=1):
            raise PlanError("bad_period", "A report cannot cover days that have not come")
    return ReportPlan(
        kind=kind,
        audience=audience,
        sections=sections,
        variant=variant,
        hubs=hubs,
        countries=countries,
        period_start=start,
        period_end=end,
        alert_id=_text(raw.get("alert_id")),
        outage_id=_text(raw.get("outage_id")),
        question=_text(raw.get("question"), 500),
        annex=raw.get("annex") if isinstance(raw.get("annex"), bool) else None,
        notes=notes,
        currency=_choice(raw.get("currency"), REPORTING_CURRENCIES, "currency"),
        energy_unit=_choice(raw.get("energy_unit"), ENERGY_UNITS, "energy unit"),
    )


#: Reporting currencies and energy units a report may convert prices into.
REPORTING_CURRENCIES = ("EUR", "GBP", "USD")
ENERGY_UNITS = ("MWh", "th", "MMBtu")


def _choice(value: Any, allowed: tuple[str, ...], what: str) -> str | None:
    if value in (None, "", "native"):
        return None
    if value not in allowed:
        raise PlanError("bad_conversion", f"Unknown {what} {value!r}; one of {', '.join(allowed)}")
    return str(value)


def _day(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _text(value: Any, limit: int = 128) -> str | None:
    if value in (None, ""):
        return None
    return str(value).strip()[:limit]


def catalogue_payload() -> dict[str, Any]:
    """The catalogue as the API and the client read it."""

    return {
        "template_version": TEMPLATE_VERSION,
        "kinds": list(KINDS),
        "daily_variants": list(DAILY_VARIANTS),
        "audiences": list(AUDIENCES),
        "groups": list(GROUPS),
        "sections": [section.as_dict() for section in SECTIONS],
        "default_sections": {kind: list(keys) for kind, keys in DEFAULT_SECTIONS.items()},
        "hubs": sorted(known_hubs()),
    }
