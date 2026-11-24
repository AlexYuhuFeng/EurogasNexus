"""LNG terminals and storage sites on the map, with their published figures (MAP-1).

Each site is a reference network point of type ``lng`` or ``storage`` (ENTSOG's map position,
a display approximation). Nothing here is estimated: every figure is one a publisher stated,
returned with its source, its gas day and when the platform received it, so the map can label
each figure's source and freshness.

- ``capacity``: the newest firm technical capacity ENTSOG publishes at the point for the
  current gas day or before, per direction (``capacity_observations``). At an LNG entry point
  that is the send-out capacity into the grid; at a storage point entry is withdrawal into the
  grid and exit is injection from it. Energy as published only; a volume is not turned into
  energy at a guessed calorific value.
- ``flow``: the physical flow the map already shows at the point (the newest closed gas day,
  one operator's report; :data:`map_situation.FLOW_DAY_RULE`).
- ``stock``: GIE's inventory. AGSI+ and ALSI are read by country, so a country's figure is
  returned as ``country_aggregate`` and never as the site's; a row whose GIE code is the
  point's own EIC is the site's (``site``).

Every row passes the caller's data scopes (``entitled``) before it is used.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import UTC, datetime, timedelta
from typing import Any

RowFilter = Callable[[Iterable[dict[str, Any]]], list[dict[str, Any]]]

ASSET_KINDS = {"lng": "lng_terminal", "storage": "storage"}
#: Gas days back from the current one in which a published capacity is still the newest.
CAPACITY_LOOKBACK_DAYS = 40
#: Gas days back in which a GIE inventory row is still shown (it says its own gas day).
STOCK_LOOKBACK_DAYS = 10

ASSET_RULE = (
    "Terminals and storage sites are the reference network's LNG and storage points at "
    "ENTSOG's map position (a display approximation). Capacity is ENTSOG's newest firm "
    "technical capacity at the point per direction, as published in energy; flow is the "
    "point's newest closed gas day; inventory is GIE AGSI+ or ALSI, by country unless GIE "
    "publishes the site under the point's own EIC. Each figure carries its source, gas day "
    "and receipt time; a figure the platform does not hold is absent, never estimated."
)


def _aware(moment: datetime | None) -> datetime | None:
    if moment is None:
        return None
    return moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment.astimezone(UTC)


def _iso(moment: datetime | None) -> str | None:
    value = _aware(moment)
    return value.isoformat() if value else None


def _eic_of(node: Any) -> str | None:
    meta = node.metadata_json or {}
    for key in ("point_eic_code", "eic_code", "eic"):
        value = meta.get(key)
        if value and str(value).strip() not in {"", "?"}:
            return str(value).strip().upper()
    return None


def build_map_assets(
    session,
    *,
    nodes: list[Any],
    node_location: Callable[[str], dict[str, Any] | None],
    flows: list[dict[str, Any]],
    entitled: RowFilter,
    now: datetime,
) -> list[dict[str, Any]]:
    """The map's terminals and storage sites with the figures the platform holds for them.

    ``node_location`` resolves a flow or capacity row's point id to its located reference
    point (the map's own locator), ``flows`` are the map's located, entitled point flows.
    """

    from eurogas_nexus.application.identity_resolution import identity_clause
    from eurogas_nexus.application.pipeline_supply import row_energy_gwh, row_operator
    from eurogas_nexus.db.models import (
        CapacityObservationRecord,
        LngObservationRecord,
        StorageObservationRecord,
    )
    from eurogas_nexus.domain.market.gas_day import gas_day_label, gas_day_start_utc

    sites = [node for node in nodes if node.node_type in ASSET_KINDS]
    if not sites:
        return []
    site_ids = {node.id for node in sites}
    naive = session.get_bind().dialect.name == "sqlite"

    def bound(moment: datetime) -> datetime:
        return moment.replace(tzinfo=None) if naive else moment

    open_day = gas_day_start_utc(now)

    # Published capacity: newest firm technical per point and direction, for the current gas
    # day or before (ENTSOG also publishes days ahead; those are not "now").
    capacity_rows = (
        session.query(CapacityObservationRecord)
        .filter(identity_clause(session, CapacityObservationRecord))
        .filter(CapacityObservationRecord.capacity_type == "firm_technical")
        .filter(
            CapacityObservationRecord.period_start_utc
            >= bound(open_day - timedelta(days=CAPACITY_LOOKBACK_DAYS))
        )
        .filter(CapacityObservationRecord.period_start_utc <= bound(open_day))
        .order_by(CapacityObservationRecord.period_start_utc.desc())
        .limit(20_000)
        .all()
    )
    capacities: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for record in capacity_rows:
        location = node_location(record.point_id)
        if location is None or location.get("ref_id") not in site_ids:
            continue
        key = (location["ref_id"], record.direction)
        if key in seen:
            continue
        energy, from_volume = row_energy_gwh(record)
        if energy is None or from_volume:
            continue
        seen.add(key)
        capacities.append(
            {
                "ref_id": location["ref_id"],
                "direction": record.direction,
                "capacity_type": "firm_technical",
                "gwh_d": round(energy, 3),
                "gas_day": gas_day_label(_aware(record.period_start_utc)),
                "operator_key": row_operator(record) or None,
                "source_system": record.source_system,
                "observed_at_utc": _iso(record.observed_at_utc),
                "basis": "published",
            }
        )
    capacity_by_site: dict[str, list[dict[str, Any]]] = {}
    for item in entitled(capacities):
        ref_id = item.pop("ref_id")
        capacity_by_site.setdefault(ref_id, []).append(item)

    flow_by_site: dict[str, list[dict[str, Any]]] = {}
    for flow in flows:
        ref_id = (flow.get("location") or {}).get("ref_id")
        if ref_id in site_ids and flow.get("gwh_d") is not None:
            flow_by_site.setdefault(ref_id, []).append(
                {
                    "direction": flow["direction"],
                    "gwh_d": flow["gwh_d"],
                    "gas_day": flow.get("gas_day"),
                    "operator_key": flow.get("operator_key"),
                    "source_system": flow["source_system"],
                }
            )

    # GIE inventory: newest row per code. AGSI+ and ALSI are read by country here; a code
    # that is a site's own EIC is that site's figure.
    stock_since = bound(open_day - timedelta(days=STOCK_LOOKBACK_DAYS))
    stocks: dict[tuple[str, str], dict[str, Any]] = {}
    for model, kind, code_column in (
        (StorageObservationRecord, "storage", "facility_id"),
        (LngObservationRecord, "lng_terminal", "terminal_id"),
    ):
        rows = (
            session.query(model)
            .filter(identity_clause(session, model))
            .filter(model.period_start_utc >= stock_since)
            .order_by(model.period_start_utc.desc())
            .limit(5_000)
            .all()
        )
        candidates = []
        for record in rows:
            code = str(getattr(record, code_column) or "").strip().upper()
            if not code:
                continue
            item: dict[str, Any] = {
                "kind": kind,
                "scope": code,
                "dataset": record.source_dataset,
                "gas_day": gas_day_label(_aware(record.period_start_utc)),
                "inventory_twh": record.inventory_twh,
                "source_system": record.source_system,
                "observed_at_utc": _iso(record.observed_at_utc),
                "freshness": record.freshness,
            }
            if kind == "storage":
                item.update(
                    working_capacity_twh=record.working_capacity_twh,
                    fill_pct=record.fill_pct,
                    injection_twh_d=record.injection_twh_d,
                    withdrawal_twh_d=record.withdrawal_twh_d,
                )
            else:
                item.update(
                    dtmi_twh=record.dtmi_twh,
                    send_out_twh_d=record.send_out_twh_d,
                )
            candidates.append(item)
        # Newest first already; the first entitled row per code is the one shown.
        for item in entitled(candidates):
            stocks.setdefault((kind, item["scope"]), item)

    assets: list[dict[str, Any]] = []
    for node in sorted(sites, key=lambda item: (item.node_type, item.name)):
        location = node_location(node.id)
        if location is None:
            continue
        kind = ASSET_KINDS[node.node_type]
        country = str(node.country or "").upper()
        eic = _eic_of(node)
        stock = None
        if eic and (held := stocks.get((kind, eic))):
            stock = {**held, "basis": "site"}
        elif country and (held := stocks.get((kind, country))):
            stock = {**held, "basis": "country_aggregate"}
        if stock is not None:
            stock.pop("kind", None)
        assets.append(
            {
                "asset_id": node.id,
                "kind": kind,
                "name": node.name,
                "country": country or None,
                "eic": eic,
                "location": location,
                "capacity": sorted(
                    capacity_by_site.get(node.id, []), key=lambda item: item["direction"]
                ),
                "flow": sorted(flow_by_site.get(node.id, []), key=lambda item: item["direction"]),
                "stock": stock,
            }
        )
    return assets


def flow_days(
    rows: Iterable[Any],
    *,
    node_location: Callable[[str], dict[str, Any] | None],
    entitled: RowFilter,
) -> list[dict[str, Any]]:
    """Each closed gas day the map read, oldest first, with every located point's flow.

    ``rows`` are the operator-selected, published-after-close flow rows the map already reads
    (one operator per point and gas day). Energy as published only. The newest day here is
    not necessarily every point's newest (a point that has not reported keeps its last day in
    ``flows``); the time scrubber says which day it shows.
    """

    from eurogas_nexus.application.pipeline_supply import (
        gas_day as flow_gas_day,
    )
    from eurogas_nexus.application.pipeline_supply import (
        row_energy_gwh,
        row_operator,
    )
    from eurogas_nexus.domain.market.gas_day import gas_day_label

    items: list[dict[str, Any]] = []
    seen: set[tuple[Any, str, str]] = set()
    for record in rows:
        location = node_location(record.point_id)
        if location is None:
            continue
        key = (flow_gas_day(record), record.point_id, record.direction)
        if key in seen:
            continue
        energy, from_volume = row_energy_gwh(record)
        if energy is None or from_volume:
            continue
        seen.add(key)
        items.append(
            {
                "day": flow_gas_day(record),
                "gas_day": gas_day_label(_aware(record.period_start_utc)),
                "point_id": record.point_id,
                "ref_id": location.get("ref_id"),
                "direction": record.direction,
                "gwh_d": round(energy, 3),
                "operator_key": row_operator(record) or None,
                "source_system": record.source_system,
            }
        )
    by_day: dict[Any, dict[str, Any]] = {}
    for item in entitled(items):
        day = item.pop("day")
        held = by_day.setdefault(day, {"gas_day": item["gas_day"], "flows": []})
        item.pop("gas_day")
        held["flows"].append(item)
    return [by_day[day] for day in sorted(by_day)]
