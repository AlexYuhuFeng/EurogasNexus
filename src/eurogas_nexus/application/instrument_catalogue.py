"""The instrument catalogue: hub → product kind → tenor, built from what the store holds.

The flat spread-series list (every hub × tenor × source) is unreadable once a desk holds a
curve. This read groups the caller's entitled daily series into the picker's levels (design
basis 2, D.2): level 1 the hub, level 2 the product kind (spot, rolling, month, quarter, season,
year), level 3 the tenors of that kind. Source is not a level: each instrument names its best
entitled source and lists the others.

Every instrument has a stable id (``TTF:M+1``, ``NBP:Jan-27``), the hub's native unit and
currency, the stored unit, a source class (``simulated`` for a demo source, ``indicative`` for a
settlement or close that is not executable, ``sourced`` otherwise), the number of days held and
the last as-of. Only outright hub prices are stored; spreads are computed from them, so every
instrument's ``instrument_kind`` is ``outright``.

本模块把调用者有权访问的日度序列按“枢纽→产品类型→期限”分组，供合约选择器使用；来源不是
层级，每个合约给出最佳来源、原生单位、来源类别（模拟/参考/来源）与最新时间。
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime
from typing import Any

from eurogas_nexus.domain.market.products import ProductCodeError, resolve_product
from eurogas_nexus.domain.market.units import HUB_NATIVE_PRICE_UNIT
from eurogas_nexus.domain.ontology.markets import find_market

#: Product kinds in the order the picker shows them (level 2).
PRODUCT_KINDS: tuple[str, ...] = ("spot", "rolling", "month", "quarter", "season", "year", "other")
#: Source classes from weakest to strongest.
SOURCE_CLASSES: tuple[str, ...] = ("simulated", "indicative", "sourced")
#: Hubs in the order a NW European desk scans them; any other hub follows alphabetically.
HUB_ORDER: tuple[str, ...] = (
    "TTF", "NBP", "THE", "PEG", "ZTP", "PSV", "CEGH", "PVB", "ETF", "GTF", "HH", "JKM",
)
#: Fewer observations than this and the instrument is shown greyed with its count (D.2).
THIN_SERIES_DAYS = 30

_PROMPT = {
    "within-day": ("WD", 0), "wd": ("WD", 0),
    "day-ahead": ("DA", 1), "da": ("DA", 1),
    "weekend": ("WE", 2), "we": ("WE", 2),
    "bom": ("BOM", 3), "balance-of-month": ("BOM", 3),
    "spot": ("Spot", 4),
}
_ROLLING = re.compile(r"^(m|q|s|gy|cal)\+(\d{1,2})$")
_ROLLING_WORDS = {
    "month-ahead": "M+1", "ma": "M+1", "quarter-ahead": "Q+1", "season-ahead": "S+1",
    "year-ahead": "Cal+1",
}
_ROLLING_FAMILY_ORDER = {"M": 0, "Q": 1, "S": 2, "GY": 3, "CAL": 4}
_ISO_MONTH = re.compile(r"^(\d{4})-(\d{2})$")
_KIND_OF_PRODUCT = {
    "month": "month",
    "quarter": "quarter",
    "season": "season",
    "gas_year": "year",
    "calendar_year": "year",
}


def classify_tenor(tenor: str, today: date) -> dict[str, Any]:
    """The product kind, desk code, sort key and delivery of a stored tenor key.

    ``month-ahead`` is the rolling ``M+1``; ``2026-12`` and ``dec-26`` are the month
    ``Dec-26``; ``q1-27`` a quarter; ``sum-27`` a season; ``cal-27``/``gy-27`` a year; the
    prompt products are spot. Anything else is ``other`` under its own name.
    """

    key = (tenor or "").strip().lower()
    if key in _PROMPT:
        code, order = _PROMPT[key]
        return {"product_kind": "spot", "code": code, "sort": (order,), "delivery": None}
    rolling = _ROLLING_WORDS.get(key)
    match = _ROLLING.match(key)
    if rolling or match:
        code = rolling or f"{match.group(1).upper()}+{match.group(2)}"
        family, number = code.upper().split("+")
        code = code if family != "CAL" else f"Cal+{number}"
        return {
            "product_kind": "rolling",
            "code": code,
            "sort": (_ROLLING_FAMILY_ORDER.get(family, 9), int(number)),
            "delivery": None,
        }
    iso = _ISO_MONTH.match(key)
    product = key
    if iso:
        product = f"{datetime(int(iso.group(1)), int(iso.group(2)), 1):%b-%y}"
    try:
        # Anchored far back so a delivered period still resolves (it is flagged expired).
        period = resolve_product(product, date(2000, 1, 1))
    except ProductCodeError:
        return {"product_kind": "other", "code": tenor, "sort": (tenor,), "delivery": None}
    kind = _KIND_OF_PRODUCT.get(period.kind)
    if kind is None:
        return {"product_kind": "other", "code": tenor, "sort": (tenor,), "delivery": None}
    return {
        "product_kind": kind,
        "code": period.label,
        "sort": (period.first_gas_day.toordinal(), period.last_gas_day.toordinal()),
        "delivery": {
            "first_gas_day": period.first_gas_day.isoformat(),
            "last_gas_day": period.last_gas_day.isoformat(),
        },
        "expired": period.last_gas_day < today,
    }


def source_class(source_system: str, *, simulated: bool, settlement: bool) -> str:
    """``simulated`` (a demo source), ``indicative`` (a settlement or close), else ``sourced``."""

    if simulated or source_system.lower().endswith("_sim"):
        return "simulated"
    if settlement:
        return "indicative"
    return "sourced"


def _hub_rank(hub: str) -> tuple[int, str]:
    return (HUB_ORDER.index(hub), hub) if hub in HUB_ORDER else (len(HUB_ORDER), hub)


def build_catalogue(rows: list[dict[str, Any]], *, today: date | None = None) -> dict[str, Any]:
    """Group daily-close rows (``application.projections.daily_closes``) into the catalogue."""

    today = today or datetime.now(UTC).date()
    series: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows:
        if not row.get("hub_resolved", True):
            continue  # an unresolved product is not a hub instrument
        key = (row["hub"], row["tenor"], row["source_system"])
        entry = series.setdefault(
            key,
            {
                "source_system": row["source_system"],
                "unit": row["unit"],
                "currency": row["currency"],
                "days": set(),
                "first": row["day"],
                "last": row["day"],
                "last_observed": row["observed_at_utc"],
                "simulated": False,
                "settlement": False,
            },
        )
        entry["days"].add(row["day"])
        entry["first"] = min(entry["first"], row["day"])
        entry["last"] = max(entry["last"], row["day"])
        if row["observed_at_utc"] >= entry["last_observed"]:
            entry["last_observed"] = row["observed_at_utc"]
            entry["unit"] = row["unit"]
        entry["simulated"] = entry["simulated"] or bool(row.get("simulated"))
        entry["settlement"] = entry["settlement"] or bool(row.get("settlement"))

    instruments: dict[tuple[str, str], dict[str, Any]] = {}
    for (hub, tenor, source), entry in series.items():
        klass = source_class(source, simulated=entry["simulated"], settlement=entry["settlement"])
        source_row = {
            "source_system": source,
            "source_class": klass,
            "simulated": klass == "simulated",
            "days": len(entry["days"]),
            "first": entry["first"].isoformat(),
            "last": entry["last"].isoformat(),
            "last_as_of": _iso(entry["last_observed"]),
            "stored_unit": entry["unit"],
        }
        item = instruments.setdefault((hub, tenor), {"hub": hub, "tenor": tenor, "sources": []})
        item["sources"].append(source_row)

    hubs: dict[str, dict[str, Any]] = {}
    for (hub, tenor), item in instruments.items():
        sources = sorted(
            item["sources"],
            key=lambda s: (
                -SOURCE_CLASSES.index(s["source_class"]),
                -s["days"],
                s["source_system"],
            ),
        )
        best = sources[0]
        shape = classify_tenor(tenor, today)
        market = find_market(hub)
        native = HUB_NATIVE_PRICE_UNIT.get(hub) or best["stored_unit"]
        instrument = {
            "id": f"{hub}:{shape['code']}",
            "hub": hub,
            "instrument_kind": "outright",
            "product_kind": shape["product_kind"],
            "code": shape["code"],
            "label": f"{hub} {shape['code']}",
            "tenor": tenor,
            "native_unit": native,
            "currency": market.currency if market else native.split("/")[0],
            "stored_unit": best["stored_unit"],
            "source_class": best["source_class"],
            "simulated": best["simulated"],
            "best_source": best["source_system"],
            "sources": sources,
            "observations": best["days"],
            "thin": best["days"] < THIN_SERIES_DAYS,
            "first": best["first"],
            "last": best["last"],
            "last_as_of": best["last_as_of"],
            "delivery": shape["delivery"],
            "expired": bool(shape.get("expired")),
            "_sort": shape["sort"],
        }
        hub_entry = hubs.setdefault(
            hub,
            {
                "hub": hub,
                "name": market.name if market else hub,
                "country": market.country if market else "",
                "native_unit": native,
                "currency": market.currency if market else native.split("/")[0],
                "kinds": {},
            },
        )
        hub_entry["kinds"].setdefault(shape["product_kind"], []).append(instrument)

    result = []
    for hub in sorted(hubs, key=_hub_rank):
        entry = hubs[hub]
        kinds = []
        everything: list[dict[str, Any]] = []
        for kind in PRODUCT_KINDS:
            items = entry["kinds"].get(kind)
            if not items:
                continue
            items.sort(key=lambda i: (i["expired"], i["_sort"] if not i["expired"] else _neg(i)))
            for item in items:
                item.pop("_sort", None)
            kinds.append({"kind": kind, "count": len(items), "instruments": items})
            everything.extend(items)
        classes = {item["source_class"] for item in everything}
        result.append(
            {
                "hub": entry["hub"],
                "name": entry["name"],
                "country": entry["country"],
                "native_unit": entry["native_unit"],
                "currency": entry["currency"],
                "instrument_count": len(everything),
                "source_class": min(classes, key=SOURCE_CLASSES.index) if classes else None,
                "simulated": "simulated" in classes,
                "last_as_of": max((i["last_as_of"] for i in everything), default=None),
                "kinds": kinds,
            }
        )
    return {
        "levels": ["hub", "product_kind", "tenor"],
        "product_kinds": list(PRODUCT_KINDS),
        "thin_series_days": THIN_SERIES_DAYS,
        "as_of": max((h["last_as_of"] for h in result if h["last_as_of"]), default=None),
        "hubs": result,
    }


def _neg(item: dict[str, Any]) -> tuple:
    return tuple(-value if isinstance(value, int) else value for value in item["_sort"])


def _iso(moment: Any) -> str | None:
    if isinstance(moment, datetime):
        aware = moment if moment.tzinfo else moment.replace(tzinfo=UTC)
        return aware.astimezone(UTC).isoformat()
    if isinstance(moment, date):
        return moment.isoformat()
    return None
