"""TSO capacity tariffs from the ENTSOG Transparency Platform into the tariff register.

ENTSOG publishes, per interconnection point, operator, direction, capacity product and
tariff period, the applicable reserve price each TSO charges (dataset ``tariffsfulls``),
including in one common unit for every operator: EUR per kWh/h of capacity per day
(``applicableTariffInCommonUnitValue``, ``Euro/(kWh/h)/d``). The route pricing walks the
market-area graph (``domain/route_cost/market_area_graph.py``) and prices each crossing's exit,
pipeline and entry legs; this module fills the register those legs are priced from.

What is stored, per row
-----------------------

- **Scope**: the interconnection points of the reference bundle's market-area adjacency (the
  points route pricing crosses), firm and interruptible, the yearly product. Other products are
  counted, not stored: the route legs book the annual product by default.
- **Names**: the operator by its name in the reference bundle, the point by its bundle name and
  country, the direction (ENTRY/EXIT): exactly how a route leg names it, so a held tariff prices
  the leg and a missing one stays missing.
- **Value and unit**: EUR/MWh at a 100 % load factor: one kWh/h of capacity held for one gas day
  carries 24 kWh, so ``EUR/(kWh/h)/d`` x 1000 (kWh per MWh, the unit authority) / 24. This is the
  unit the register's other corridor rows and the route engine sum in. The published value,
  its unit, the operator's local-currency value and ENTSOG's row id are kept in
  ``source_refs``. ENTSOG converts other currencies to EUR at its own reference rate; the
  local-currency figure stays alongside for audit.
- **Period**: ``effective_from`` is the first gas day of the tariff period, ``effective_to``
  its last (ENTSOG's end is exclusive). The gas-year column carries the period's own label
  (``2026`` for a calendar-year tariff, ``2025/26`` for a gas-year one); route legs select by
  the period covering the delivery gas day (``TARIFF_GAS_YEAR_BY_PERIOD``).
- **Status**: FINAL when the period had started on the download date (an applicable tariff),
  INDICATIVE for a later period, which also requires manual review.
- **Provenance**: ``document_id`` ``entsog-tariffsfulls-<download date>``, the ENTSOG TP citation
  its terms require (``docs/legal/DATA_SOURCE_TERMS.md``), the row id and the as-of instant
  (``created_at_utc``, the receipt).

Nothing is estimated: a row without a common-unit value, in another unit, archived, or whose
operator or point is not in the reference bundle is skipped and counted. Two rows with the
same identity and different values are both refused (``conflicting``).
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, date, datetime, timedelta
from typing import Any

from eurogas_nexus.domain.ontology.quantity import convert

TARIFF_DATASET = "tariffsfulls"
COMMON_UNIT = "Euro/(kWh/h)/d"
STORED_UNIT = "EUR/MWh"
STORED_PRODUCTS = {"Yearly": "ANNUAL"}
FIRMNESS = {"Firm": "FIRM", "Interruptible": "INTERRUPTIBLE"}
DOCUMENT_PREFIX = "entsog-tariffsfulls-"

#: kWh per MWh from the unit authority; 24 kWh flow through one kWh/h in one gas day.
_KWH_PER_MWH = convert(1.0, "MWh", "kWh")
_HOURS_PER_GAS_DAY = 24.0


def per_mwh_at_full_load(eur_per_kwh_h_per_day: float) -> float:
    """EUR/(kWh/h)/d as EUR/MWh when the capacity is used every hour."""

    return eur_per_kwh_h_per_day * _KWH_PER_MWH / _HOURS_PER_GAS_DAY


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


def _period_label(start: date, end_exclusive: date) -> str:
    if start.month == 10 and start.day == 1 and end_exclusive == date(start.year + 1, 10, 1):
        return f"{start.year}/{(start.year + 1) % 100:02d}"
    if start.month == 1 and start.day == 1 and end_exclusive == date(start.year + 1, 1, 1):
        return str(start.year)
    return f"{start.isoformat()}..{(end_exclusive - timedelta(days=1)).isoformat()}"


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


def entsog_tariff_rows(
    records: Iterable[Mapping[str, Any]],
    *,
    bundle: Mapping[str, Any],
    downloaded: date,
    received_at: datetime,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Register rows (``tso_tariffs`` columns) from ENTSOG ``tariffsfulls`` records."""

    nodes = {str(node["point_key"]): node for node in bundle.get("nodes") or []}
    operators = bundle.get("operators") or {}
    wanted = set(tariff_points(bundle))
    stamp = downloaded.strftime("%d-%m-%Y")
    citation = f"ENTSOG TP [{stamp}] https://transparency.entsog.eu/"
    skipped: Counter[str] = Counter()
    rows: dict[str, dict[str, Any]] = {}
    conflicting: set[str] = set()
    for record in records:
        point = str(record.get("pointKey") or "")
        operator = str(record.get("operatorKey") or "")
        if record.get("isArchived"):
            skipped["archived"] += 1
            continue
        if point not in wanted or point not in nodes:
            skipped["point_outside_adjacency"] += 1
            continue
        if operator not in operators:
            skipped["operator_not_in_bundle"] += 1
            continue
        product = STORED_PRODUCTS.get(str(record.get("productType") or ""))
        if product is None:
            skipped["product_not_stored"] += 1
            continue
        firmness = FIRMNESS.get(str(record.get("tariffCapacityType") or ""))
        direction = str(record.get("directionKey") or "").upper()
        if firmness is None or direction not in {"ENTRY", "EXIT"}:
            skipped["firmness_or_direction_unknown"] += 1
            continue
        if record.get("applicableTariffInCommonUnitUnit") != COMMON_UNIT:
            skipped["unit_not_common"] += 1
            continue
        value = _number(record.get("applicableTariffInCommonUnitValue"))
        start, end = _gas_day(record.get("periodFrom")), _gas_day(record.get("periodTo"))
        if value is None or start is None or end is None or end <= start:
            skipped["value_or_period_missing"] += 1
            continue
        final = start <= downloaded
        tariff_id = "-".join(
            ("entsog", operator, point, direction, firmness, product, start.isoformat())
        ).lower()
        row = {
            "tariff_id": tariff_id,
            "document_id": f"{DOCUMENT_PREFIX}{downloaded.isoformat()}",
            "country": str(nodes[point].get("country") or ""),
            "tso": str(operators[operator].get("name") or operator),
            "market_area": str(
                (record.get("fromBZ") if direction == "EXIT" else record.get("toBZ")) or "ENTSOG"
            )[:64],
            "gas_year": _period_label(start, end),
            "point_id": point,
            "source_point_name": str(nodes[point].get("name") or point),
            "direction": direction,
            "capacity_product": product,
            "firmness": firmness,
            "tariff_value": round(per_mwh_at_full_load(value), 8),
            "currency": "EUR",
            "unit": STORED_UNIT,
            "effective_from": datetime.combine(start, datetime.min.time(), tzinfo=UTC),
            "effective_to": datetime.combine(
                end - timedelta(days=1), datetime.min.time(), tzinfo=UTC
            ),
            "tariff_status": "FINAL" if final else "INDICATIVE",
            "source_table": (
                f"ENTSOG TP tariffsfulls, applicable tariff in {COMMON_UNIT}, "
                f"{record.get('productType')} {record.get('tariffCapacityType')}"
            ),
            "source_page": None,
            "source_refs": [
                citation,
                f"entsog:tariffsfulls:{record.get('id')}",
                f"published:{value} {COMMON_UNIT}",
                "local:"
                f"{record.get('applicableTariffPerLocalCurrencyKWhDValue')} "
                f"{record.get('applicableTariffPerLocalCurrencyKWhDUnit')}",
                "converted: EUR/MWh at 100% load factor (x1000/24)",
            ],
            "manual_review_required": not final,
            "created_at_utc": received_at,
        }
        held = rows.get(tariff_id)
        if held is not None and held["tariff_value"] != row["tariff_value"]:
            conflicting.add(tariff_id)
        rows.setdefault(tariff_id, row)
    for tariff_id in conflicting:
        rows.pop(tariff_id, None)
    counts = dict(skipped)
    counts["conflicting"] = len(conflicting)
    return [rows[key] for key in sorted(rows)], counts


def persist_entsog_tariffs(
    session: Any,
    *,
    results: Sequence[Any],
    run_id: str,
    bundle: Mapping[str, Any] | None = None,
    downloaded: date | None = None,
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
    rows, counts = entsog_tariff_rows(records, bundle=bundle, downloaded=day, received_at=received)
    with session.begin_nested():
        for row in rows:
            session.merge(TsoTariffRecord(**row))
    return {
        "records": len(rows),
        "received_records": len(records),
        # Not stored by design (other products, archived rows) is not a data problem.
        "skipped_records": sum(
            value
            for key, value in counts.items()
            if key not in {"product_not_stored", "archived", "point_outside_adjacency"}
        ),
        "skipped_by_reason": counts,
        "run_id": run_id,
        "points": len({row["point_id"] for row in rows}),
    }
