"""TSO capacity tariffs from the ENTSOG Transparency Platform into the tariff register.

ENTSOG publishes, per point, operator, direction, capacity product and tariff period, the
applicable reserve price each TSO charges (dataset ``tariffsfulls``): in the operator's own
currency and capacity unit (``applicableTariffPerLocalCurrencyKWhH/D``), in EUR, and in one
common unit for every operator, EUR per kWh/h of capacity per day (per hour for within-day;
``applicableTariffInCommonUnitValue``). Route pricing walks the market-area graph
(``domain/route_cost/market_area_graph.py``) and prices each crossing's exit, pipeline and
entry legs; this module fills the register those legs are priced from.

What is stored, per row
-----------------------

- **Scope**: the points of the market-area graph (``tariff_points``) and the corridor, LNG and
  Norwegian landing points of ``reference_data/tariff_scope.py``; firm and interruptible; the
  standard capacity products (yearly, quarterly, monthly, daily, within-day; ``PRODUCTS``).
- **Names**: the operator and point by their names in the reference bundle (ENTSOG's own label
  for a point or operator the bundle does not hold), the direction (ENTRY/EXIT): exactly how a
  route leg names it, so a held tariff prices the leg and a missing one stays missing.
- **Value, unit, currency**: what the operator published, never converted here: the price per
  unit of capacity per period in the operator's currency and in the capacity unit the operator
  sells (``tariffCapacityUnit``: kWh/h or kWh/d), with ENTSOG's unit (``EUR/(kWh/h)/y``,
  ``GBP/(kWh/d)/y``, ``EUR/(kWh/h)/m`` ...). The product's multiplier and seasonal factor are
  already in the price and are kept in ``source_refs`` with the EUR and common-unit figures.
  The cost per MWh for a stated product and load factor is worked out when the tariff is read
  (``domain/route_cost/tariff_units.per_mwh``).
- **One figure checked against the other.** ENTSOG files each price four ways (per kWh/h and
  per kWh/d, local currency and EUR) plus its common unit. The operator's figure is stored only
  when they agree within 0.5 % (per kWh/h = 24 x per kWh/d; the EUR figure over the period's
  days = the common unit). Where they disagree (measured 2026-11-19 on about 10 % of rows,
  mostly within-day, monthly and daily products: a capacity unit filed as kWh/d for a kWh/h
  price, a per-day price filed per hour, a common unit far from the operator's figure), which
  one is right cannot be told from the row. When the operator's own figures disagree with each
  other (per kWh/h is not 24 x per kWh/d) the row is not stored (``figures_disagree``); when
  only ENTSOG's common unit disagrees, a yearly price is stored as INDICATIVE for review
  (``common_unit_disagrees``; a shorter product is not stored), unless the two differ by
  exactly 24 (a kWh/h-for-kWh/d or hour-for-day mislabel on one side): then it is not stored
  either. Nothing is rescaled by a guessed factor.
- **Refused operators** (``OPERATOR_REFUSALS``): an operator whose ENTSOG figures do not match
  its own publication is not stored; its legs stay "tariff not held" until an administrator
  enters the operator's published tariff (four-eyes, the register's admin path).
- **Period**: a yearly price is valid for its tariff period (``periodFrom``-``periodTo``), or,
  where the operator publishes two yearly prices in one tariff period (NaTran's April and
  October products), each for its product period inside it; a shorter product for the part of
  its product period inside the tariff period (one row per
  month where a seasonal factor makes months differ). ``effective_to`` is the last gas day
  (ENTSOG's end is exclusive). The gas-year column carries the tariff period's label
  (``2026`` calendar year, ``2026/27`` gas year).
- **Status**: the operator's own status where ENTSOG carries it (``operator_status``: a remark
  stating the price final or indicative); otherwise INDICATIVE when the period starts after
  the download date. Always INDICATIVE when ENTSOG's common unit disagrees with the operator's
  figure (also manual review); FINAL otherwise. Measured 19-11-2026: none of the 12,670
  ``tariffsfulls`` rows read for the 108 points carries a status, in any remark field, so a
  later period is INDICATIVE until it starts (THE's final 2027 prices included).
- **Provenance**: ``document_id`` ``entsog-tariffsfulls-<download date>``, the ENTSOG TP citation
  its terms require (``docs/legal/DATA_SOURCE_TERMS.md``), the row id and the as-of instant
  (``created_at_utc``, the receipt).

Nothing is estimated: a row without a value, archived, or for a product the operator does not
offer is skipped and counted. Two rows with the same identity and different values are both
refused (``conflicting``). A re-read upserts by ``tariff_id``: a changed publication replaces
the stored figure, the receipt instant and download date say when.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, date, datetime, timedelta
from typing import Any

from eurogas_nexus.domain.route_cost.tariff_units import KWH_PER_MWH

TARIFF_DATASET = "tariffsfulls"
COMMON_UNIT = "Euro/(kWh/h)/d"
#: ENTSOG product type -> register capacity product (CAM standard products).
PRODUCTS = {
    "Yearly": "ANNUAL",
    "Quarterly": "QUARTERLY",
    "Monthly": "MONTHLY",
    "Daily": "DAILY",
    "WithinDay": "WITHIN_DAY",
}
#: Kept for callers that read the yearly product only.
STORED_PRODUCTS = {"Yearly": "ANNUAL"}
FIRMNESS = {"Firm": "FIRM", "Interruptible": "INTERRUPTIBLE"}
DOCUMENT_PREFIX = "entsog-tariffsfulls-"
#: Relative agreement required between the operator's figure and ENTSOG's common unit.
AGREEMENT = 0.005

#: Operators whose ENTSOG tariff figures are not stored, and why (checked 2026-11-19).
OPERATOR_REFUSALS: dict[str, str] = {
    # National Gas publishes its IP reserve prices per day of capacity, in p/kWh/d ("Notice of
    # Annual Yearly Interconnection Point Reserve prices 2026": IP exit 0.0356 p/kWh/d for
    # 2026/27, 0.0299 for 2025/26). ENTSOG files them under a per-year unit
    # (Moffat exit 0.000356 GBP/(kWh/d)/y for 2026/27, 0.000299 for 2025/26) and derives its
    # common unit as if yearly (365 times too low); at Bacton IUK it holds 0.000211 for both
    # years, which matches neither. Read per MWh, every National Gas row would be wrong.
    "UK-TSO-0001": (
        "ENTSOG's National Gas figures match neither the unit nor the value of National "
        "Gas's own IP reserve price notices"
    ),
}
_NOT_OFFERED = (
    "not available",
    "not offer",
    "not applicable",
    "no product",
    "does not offer",
)


def per_mwh_at_full_load(eur_per_kwh_h_per_day: float) -> float:
    """EUR/(kWh/h)/d as EUR/MWh when the capacity is used every hour."""

    return eur_per_kwh_h_per_day * KWH_PER_MWH / 24.0


def tariff_points(bundle: Mapping[str, Any]) -> list[str]:
    """The interconnection points route pricing crosses (adjacency points of the bundle)."""

    points = {
        str(edge["point_key"])
        for edge in bundle.get("edges") or []
        if edge.get("type") == "market_area_link"
    }
    for edge in bundle.get("edges") or []:
        if edge.get("type") == "interconnector":
            points.update(str(point) for point in edge.get("point_keys") or [])
    return sorted(points)


def read_points(bundle: Mapping[str, Any]) -> list[str]:
    """Every point the tariff read covers: the graph's points and the scope's other points."""

    from eurogas_nexus.reference_data.tariff_scope import scope_points

    return sorted(set(tariff_points(bundle)) | set(scope_points()))


#: ENTSOG's free-text fields an operator may state its price's status in.
_STATUS_FIELDS = (
    "applicableTariffRemarks",
    "remarks",
    "tariffPeriodRemarks",
    "generalRemarks",
    "itemRemarks",
)


def operator_status(record: Mapping[str, Any]) -> str | None:
    """FINAL or INDICATIVE when the operator states it in the row, else None."""

    text = " ".join(str(record.get(key) or "") for key in _STATUS_FIELDS).lower()
    if "indicative" in text or "provisional" in text or "preliminary" in text:
        return "INDICATIVE"
    if "final" in text:
        return "FINAL"
    return None


def _period_label(start: date, end_exclusive: date) -> str:
    if start.month == 10 and start.day == 1 and end_exclusive == date(start.year + 1, 10, 1):
        return f"{start.year}/{(start.year + 1) % 100:02d}"
    if start.month == 1 and start.day == 1 and end_exclusive == date(start.year + 1, 1, 1):
        return str(start.year)
    # Another period (NaTran's April - March): its months, within the column's 16 characters.
    last = end_exclusive - timedelta(days=1)
    return f"{start:%Y-%m}..{last:%y-%m}"


def _gas_day(value: Any) -> date | None:
    """The gas day an ENTSOG period boundary opens (its local calendar date)."""

    if not isinstance(value, str) or len(value) < 10:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number >= 0 else None


def _unit(text: Any) -> str:
    return str(text or "").replace("Euro/", "EUR/").strip()


def _period_code(unit: str) -> str | None:
    tail = unit.rsplit("/", 1)[-1].strip().lower() if "/" in unit else ""
    return tail if tail in {"y", "q", "m", "d", "h"} else None


def _common_days(
    period: str, product: tuple[date, date], tariff: tuple[date, date]
) -> set[float]:
    """Day counts ENTSOG may divide a per-period price by for its per-day common unit.

    Measured 2026-11-19: the tariff period's length for a yearly price; for a quarterly or
    monthly price the product's own length when it is one quarter or month, else the year's
    days over 4 or 12, or a flat 30-day month (NaTran) or the calendar month (IUK).
    """

    tariff_days = (tariff[1] - tariff[0]).days
    product_days = (product[1] - product[0]).days
    year_days = tariff_days if 360 <= tariff_days <= 367 else 365
    if period == "y":
        return {float(year_days), 365.0, 366.0}
    if period == "q":
        out = {90.0, 91.0, 92.0, year_days / 4}
        return out | ({float(product_days)} if 88 <= product_days <= 93 else set())
    if period == "m":
        out = {28.0, 29.0, 30.0, 31.0, year_days / 12}
        return out | ({float(product_days)} if 27 <= product_days <= 32 else set())
    return {1.0}  # d (per day); h (the common unit is per hour too)


def _agrees(a: float, b: float) -> bool:
    return abs(a - b) <= AGREEMENT * max(abs(a), abs(b)) or abs(a - b) <= 1e-9


def _published_figure(
    record: Mapping[str, Any], product: tuple[date, date], tariff: tuple[date, date]
) -> tuple[float, str, str, bool] | str:
    """(value, unit, currency, common unit agrees) the operator published, or why not stored.

    The operator's per-kWh/h figure must equal 24 x its per-kWh/d one, else the row is not
    stored (which basis is right cannot be told). Its EUR twin is then checked against ENTSOG's
    common unit (EUR per kWh/h per day, or per hour for within-day); when they disagree the
    operator's figure is still stored, as indicative and for review (the fourth item is False),
    unless they differ by exactly 24 (a kWh/h-for-kWh/d or hour-for-day mislabel on one side
    that the row cannot resolve): then nothing is stored.
    Nothing is rescaled by a guessed factor.
    """

    common = _number(record.get("applicableTariffInCommonUnitValue"))
    basis = str(record.get("tariffCapacityUnit") or "kWh/h").strip()
    local_field = "KWhD" if basis == "kWh/d" else "KWhH"
    local = _number(record.get(f"applicableTariffPerLocalCurrency{local_field}Value"))
    local_unit = _unit(record.get(f"applicableTariffPerLocalCurrency{local_field}Unit"))
    local_h = _number(record.get("applicableTariffPerLocalCurrencyKWhHValue"))
    local_d = _number(record.get("applicableTariffPerLocalCurrencyKWhDValue"))
    eur_h = _number(record.get("applicableTariffPerEURKWhHValue"))
    eur_h_unit = _unit(record.get("applicableTariffPerEURKWhHUnit"))
    currency = str(record.get("operatorCurrency") or "").strip().upper()
    period = _period_code(local_unit)
    if local is None or not period or not currency:
        return "value_or_period_missing"
    if local_h is None or local_d is None or not _agrees(local_d * 24.0, local_h):
        return "figures_disagree"
    days = _common_days(_period_code(eur_h_unit) or period, product, tariff)
    if common is None or eur_h is None:
        return local, local_unit, currency, False
    if any(_agrees(eur_h / day, common) for day in days):
        return local, local_unit, currency, True
    if any(_agrees(eur_h / day, common * factor) for day in days for factor in (24.0, 1 / 24)):
        # Off by exactly the hours of a day: a kWh/h price filed as kWh/d or a per-day price
        # filed per hour. Which of the two figures carries the mislabel cannot be told.
        return "figures_disagree"
    return local, local_unit, currency, False


def _point_names(
    point: str, record: Mapping[str, Any], nodes: Mapping[str, Mapping[str, Any]]
) -> tuple[str, str]:
    node = nodes.get(point)
    if node is not None:
        return str(node.get("name") or point), str(node.get("country") or "")
    from eurogas_nexus.reference_data.tariff_scope import scope_points

    label = str(record.get("pointLabel") or "").strip() or scope_points().get(
        point, ("", point, ())
    )[1]
    return label or point, str(record.get("countryCode") or "")[:8]


def _annual_key(record: Mapping[str, Any]) -> tuple[str, ...]:
    return tuple(
        str(record.get(key) or "")
        for key in ("operatorKey", "pointKey", "directionKey", "tariffCapacityType", "periodFrom")
    )


def _split_annual_periods(records: Iterable[Mapping[str, Any]]) -> set[tuple[str, ...]]:
    """Yearly prices that change inside their tariff period, by product period.

    NaTran's April-March tariff period carries one yearly price for the product starting in
    April and another for the one starting in October (read 2026-11-19); each then holds for
    its own product period. A single yearly price holds for the whole tariff period.
    """

    seen: dict[tuple[str, ...], set[str]] = {}
    for record in records:
        if record.get("productType") != "Yearly" or record.get("isArchived"):
            continue
        value = record.get("applicableTariffPerLocalCurrencyKWhHValue")
        if _number(value) is None:
            continue
        seen.setdefault(_annual_key(record), set()).add(str(value))
    return {key for key, values in seen.items() if len(values) > 1}


def entsog_tariff_rows(
    records: Iterable[Mapping[str, Any]],
    *,
    bundle: Mapping[str, Any],
    downloaded: date,
    received_at: datetime,
    points: Iterable[str] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Register rows (``tso_tariffs`` columns) from ENTSOG ``tariffsfulls`` records."""

    nodes = {str(node["point_key"]): node for node in bundle.get("nodes") or []}
    operators = bundle.get("operators") or {}
    wanted = set(points) if points is not None else set(read_points(bundle))
    stamp = downloaded.strftime("%d-%m-%Y")
    citation = f"ENTSOG TP [{stamp}] https://transparency.entsog.eu/"
    skipped: Counter[str] = Counter()
    rows: dict[str, dict[str, Any]] = {}
    conflicting: set[str] = set()
    records = list(records)
    split_years = _split_annual_periods(records)
    for record in records:
        point = str(record.get("pointKey") or "")
        operator = str(record.get("operatorKey") or "")
        if record.get("isArchived"):
            skipped["archived"] += 1
            continue
        if point not in wanted:
            skipped["point_outside_adjacency"] += 1
            continue
        if operator in OPERATOR_REFUSALS:
            skipped["operator_refused"] += 1
            continue
        product = PRODUCTS.get(str(record.get("productType") or ""))
        if product is None:
            skipped["product_not_stored"] += 1
            continue
        firmness = FIRMNESS.get(str(record.get("tariffCapacityType") or ""))
        direction = str(record.get("directionKey") or "").upper()
        if firmness is None or direction not in {"ENTRY", "EXIT"}:
            skipped["firmness_or_direction_unknown"] += 1
            continue
        tariff_from = _gas_day(record.get("periodFrom"))
        tariff_to = _gas_day(record.get("periodTo"))
        product_from = _gas_day(record.get("productPeriodFrom")) or tariff_from
        product_to = _gas_day(record.get("productPeriodTo")) or tariff_to
        if (
            tariff_from is None
            or tariff_to is None
            or tariff_to <= tariff_from
            or product_from is None
            or product_to is None
        ):
            skipped["value_or_period_missing"] += 1
            continue
        remarks = " ".join(
            str(record.get(key) or "")
            for key in ("applicableTariffRemarks", "remarks", "tariffPeriodRemarks")
        ).strip()
        figure = _published_figure(
            record, (product_from, product_to), (tariff_from, tariff_to)
        )
        if isinstance(figure, str):
            not_offered = any(phrase in remarks.lower() for phrase in _NOT_OFFERED)
            skipped["product_not_offered" if not_offered else figure] += 1
            continue
        value, unit, currency, common_agrees = figure
        if not common_agrees and product != "ANNUAL":
            # A shorter product's price is the yearly one times its multiplier; with the common
            # unit disagreeing there is no second figure to check that against (measured: a
            # daily price filed 24 times too high beside a common unit 365 times too low).
            skipped["figures_disagree"] += 1
            continue
        if product == "ANNUAL" and _annual_key(record) not in split_years:
            start, end = tariff_from, tariff_to
        else:
            start, end = max(tariff_from, product_from), min(tariff_to, product_to)
            if end <= start:
                skipped["value_or_period_missing"] += 1
                continue
        stated = operator_status(record)
        indicative = (
            not common_agrees
            or stated == "INDICATIVE"
            or (stated is None and tariff_from > downloaded)
        )
        tariff_id = "-".join(
            ("entsog", operator, point, direction, firmness, product, start.isoformat())
        ).lower()
        point_name, country = _point_names(point, record, nodes)
        operator_name = str(
            (operators.get(operator) or {}).get("name") or record.get("operator") or operator
        ).strip()
        refs = [
            citation,
            f"entsog:tariffsfulls:{record.get('id')}",
            "published:"
            f" {record.get('applicableTariffPerLocalCurrencyKWhHValue')}"
            f" {record.get('applicableTariffPerLocalCurrencyKWhHUnit')};"
            f" {record.get('applicableTariffPerLocalCurrencyKWhDValue')}"
            f" {record.get('applicableTariffPerLocalCurrencyKWhDUnit')};"
            f" capacity unit {record.get('tariffCapacityUnit')}",
            f"eur: {record.get('applicableTariffPerEURKWhHValue')}"
            f" {record.get('applicableTariffPerEURKWhHUnit')}"
            f" (exchange rate of {record.get('exchangeRateReferenceDate')})",
            f"common: {record.get('applicableTariffInCommonUnitValue')}"
            f" {record.get('applicableTariffInCommonUnitUnit')}",
            f"product: {record.get('productType')} {record.get('tariffCapacityType')},"
            f" product period {product_from.isoformat()}..{product_to.isoformat()},"
            f" multiplier {record.get('multiplier')},"
            f" seasonal factor {record.get('seasonalFactor')},"
            f" interruptible discount {record.get('discountForInterruptibleCapacityValue')}",
        ]
        if not common_agrees:
            refs.append(
                "check: ENTSOG's common-unit figure disagrees with the operator's; stored as "
                "indicative for review"
            )
        if remarks:
            refs.append(f"remarks: {remarks[:200]}")
        row = {
            "tariff_id": tariff_id,
            "document_id": f"{DOCUMENT_PREFIX}{downloaded.isoformat()}",
            "country": country,
            "tso": operator_name[:128],
            "market_area": str(
                (record.get("fromBZ") if direction == "EXIT" else record.get("toBZ")) or "ENTSOG"
            )[:64],
            "gas_year": _period_label(tariff_from, tariff_to),
            "point_id": point,
            "source_point_name": point_name[:256],
            "direction": direction,
            "capacity_product": product,
            "firmness": firmness,
            "tariff_value": value,
            "currency": currency,
            "unit": unit,
            "effective_from": datetime.combine(start, datetime.min.time(), tzinfo=UTC),
            "effective_to": datetime.combine(
                end - timedelta(days=1), datetime.min.time(), tzinfo=UTC
            ),
            "tariff_status": "INDICATIVE" if indicative else "FINAL",
            "source_table": (
                f"ENTSOG TP tariffsfulls, {record.get('productType')} "
                f"{record.get('tariffCapacityType')}, {unit}"
            )[:256],
            "source_page": None,
            "source_refs": refs,
            "manual_review_required": indicative,
            "created_at_utc": received_at,
        }
        held = rows.get(tariff_id)
        if held is not None and (held["tariff_value"], held["unit"]) != (value, unit):
            conflicting.add(tariff_id)
        rows.setdefault(tariff_id, row)
    for tariff_id in conflicting:
        rows.pop(tariff_id, None)
    counts = dict(skipped)
    counts["conflicting"] = len(conflicting)
    counts["common_unit_disagrees"] = sum(
        1 for row in rows.values() if any(ref.startswith("check:") for ref in row["source_refs"])
    )
    return [rows[key] for key in sorted(rows)], counts


#: Skip reasons that are not a data problem (by design not stored).
NOT_A_PROBLEM = frozenset(
    {
        "product_not_stored",
        "product_not_offered",
        "archived",
        "point_outside_adjacency",
        "operator_refused",
        "common_unit_disagrees",
    }
)


def persist_entsog_tariffs(
    session: Any,
    *,
    results: Sequence[Any],
    run_id: str,
    bundle: Mapping[str, Any] | None = None,
    downloaded: date | None = None,
    points: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Archive the pages and upsert the normalized rows into ``tso_tariffs`` (by tariff id)."""

    from eurogas_nexus.db.models import TsoTariffRecord
    from eurogas_nexus.ingestion.entsog_ingestion import archive_entsog_pages
    from eurogas_nexus.reference_data.network_bundle import load_bundle

    bundle = bundle if bundle is not None else load_bundle()
    archive_entsog_pages(session, results)
    records = [
        record
        for result in results
        for page in result.pages
        for record in (page.payload.get(TARIFF_DATASET) or [])
    ]
    received = max((result.received_at_utc for result in results), default=datetime.now(UTC))
    day = downloaded or received.date()
    rows, counts = entsog_tariff_rows(
        records, bundle=bundle, downloaded=day, received_at=received, points=points
    )
    from eurogas_nexus.application.tariff_book import record_register_rows
    from eurogas_nexus.application.tso_tariff_entries import retire_superseded_entries

    with session.begin_nested():
        stored = [session.merge(TsoTariffRecord(**row)) for row in rows]
        session.flush()
        # An administrator's entry for a leg ENTSOG now publishes steps aside.
        retired = retire_superseded_entries(session) if rows else 0
        # TAR-1: a changed figure becomes a new tariff version and one ``tariff.changed``
        # event, committed with the figure itself.
        versions = record_register_rows(session, stored)
    return {
        "records": len(rows),
        "entries_retired": retired,
        "tariff_versions": versions.written,
        "tariff_events": versions.events,
        "received_records": len(records),
        # Not stored by design (other products, archived rows) is not a data problem.
        "skipped_records": sum(
            value for key, value in counts.items() if key not in NOT_A_PROBLEM
        ),
        "skipped_by_reason": counts,
        "run_id": run_id,
        "points": len({row["point_id"] for row in rows}),
    }
