"""What is happening on the network now, located on the map.

One read composes the live picture a desk head or manager scans: outages, today's
physical flows at points, the firm's upstream contracts at their delivery points, LNG
cargoes at sea and the firm's regas slots. Every item is placed only where a source
locates it:

- outages by the asset's EIC code on a network point (the REMIT key), else by exact name;
- contracts by their delivery point's name on a network point;
- cargoes and slots by the coordinates the vessel feed or ETRM supplied, else the
  terminal's network point.

Items that cannot be located are counted, never placed at a guessed position. Book-held
items follow portfolio isolation; market items follow the caller's data scopes.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from datetime import UTC, datetime, timedelta
from typing import Any

from eurogas_nexus.security.portfolio_scope import visible_book_ids

FLOW_LOOKBACK_DAYS = 3
SLOT_HORIZON_DAYS = 45
CARGO_HISTORY_DAYS = 7

RowFilter = Callable[[Iterable[dict[str, Any]]], list[dict[str, Any]]]


def _key(text: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").casefold()).strip()


def _aware(moment: datetime | None) -> datetime | None:
    if moment is None:
        return None
    return moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment.astimezone(UTC)


def _iso(moment: datetime | None) -> str | None:
    value = _aware(moment)
    return value.isoformat() if value else None


class _Locator:
    """Network points and facilities indexed by EIC code and by normalised name."""

    def __init__(self, nodes: list[Any], facilities: list[Any]) -> None:
        self.by_eic: dict[str, dict[str, Any]] = {}
        self.by_name: dict[str, dict[str, Any]] = {}
        self.by_node_id: dict[str, dict[str, Any]] = {}
        for item, kind in [(n, "node") for n in nodes] + [(f, "facility") for f in facilities]:
            meta = item.metadata_json or {}
            location = {
                "lon": item.lon,
                "lat": item.lat,
                "ref_id": item.id,
                "ref_kind": kind,
                "coordinate_quality": item.data_quality or "unknown",
            }
            if kind == "node":
                self.by_node_id[item.id] = location
                if item.source_record_id:
                    self.by_node_id[str(item.source_record_id)] = location
            for eic in (meta.get("point_eic_code"), meta.get("eic_code"), meta.get("eic")):
                if eic:
                    self.by_eic.setdefault(str(eic).strip().upper(), location)
            self.by_name.setdefault(_key(item.name), location)

    def find(self, *, eic: str | None = None, name: str | None = None) -> dict[str, Any] | None:
        if eic and (hit := self.by_eic.get(eic.strip().upper())):
            return {**hit, "match": "eic"}
        if name and (hit := self.by_name.get(_key(name))):
            return {**hit, "match": "name"}
        return None


def _own(book_id: str | None, allowed: set[str] | None) -> bool:
    if allowed is None:
        return True
    return bool(book_id) and book_id in allowed


def build_map_situation(
    session,
    *,
    now: datetime,
    entitled: RowFilter,
    include_positions: bool = True,
    outage_horizon_days: int = 14,
) -> dict[str, Any]:
    """The live map payload. ``entitled`` filters market rows by the caller's data scopes."""

    from eurogas_nexus.application.remit_outages import load_outage_rows
    from eurogas_nexus.db.models import (
        FlowObservationRecord,
        LngCargoRecord,
        ReferenceFacility,
        ReferenceNode,
        RegasSlotRecord,
        UpstreamResourceContractRecord,
    )

    locator = _Locator(session.query(ReferenceNode).all(), session.query(ReferenceFacility).all())
    unlocated = {"outages": 0, "contracts": 0, "cargoes": 0, "regas_slots": 0}

    outages = []
    for row in entitled(load_outage_rows(session, now=now, horizon_days=outage_horizon_days)):
        location = locator.find(eic=str(row["facility_id"]), name=str(row["facility_name"]))
        if location is None:
            unlocated["outages"] += 1
            continue
        technical = row.get("technical_capacity") or 0
        unavailable = row.get("unavailable_capacity") or 0
        outages.append(
            {
                **{
                    k: row[k]
                    for k in (
                        "event_id",
                        "facility_name",
                        "asset_type",
                        "event_type",
                        "status",
                        "start_utc",
                        "end_utc",
                        "balancing_zone",
                        "unit",
                        "technical_capacity",
                        "unavailable_capacity",
                        "unavailable_gwh_d",
                        "description",
                        "market_participant",
                        "source_system",
                    )
                },
                "unavailable_share": round(unavailable / technical, 3) if technical else None,
                "location": location,
            }
        )

    naive = session.get_bind().dialect.name == "sqlite"

    def bound(moment: datetime) -> datetime:
        return moment.replace(tzinfo=None) if naive else moment

    flow_rows = (
        session.query(FlowObservationRecord)
        .filter(
            FlowObservationRecord.period_start_utc
            >= bound(now - timedelta(days=FLOW_LOOKBACK_DAYS))
        )
        .filter(FlowObservationRecord.kind == "actual")
        .order_by(FlowObservationRecord.period_start_utc.desc())
        .limit(20_000)
        .all()
    )
    latest: dict[tuple[str, str], Any] = {}
    for record in flow_rows:
        latest.setdefault((record.point_id, record.direction), record)
    flows = []
    for (point_id, direction), record in latest.items():
        location = locator.by_node_id.get(point_id) or locator.by_node_id.get(
            f"entsog-{point_id.lower()}"
        )
        if location is None:
            continue
        gwh_d = None
        unit = record.original_unit or ""
        if record.original_value is not None and unit.lower().startswith("kwh"):
            gwh_d = round(record.original_value / 1_000_000, 3)
        flows.append(
            {
                "point_id": point_id,
                "point_name": record.point_name,
                "direction": direction,
                "gas_day_start_utc": _iso(record.period_start_utc),
                "value": record.original_value
                if record.original_value is not None
                else record.flow_mcm_d,
                "unit": unit or "mcm/d",
                "gwh_d": gwh_d,
                "source_system": record.source_system,
                "location": location,
            }
        )
    flows = entitled(flows)

    contracts: list[dict[str, Any]] = []
    cargoes: list[dict[str, Any]] = []
    slots: list[dict[str, Any]] = []
    if include_positions:
        allowed = visible_book_ids(session)
        for record in session.query(UpstreamResourceContractRecord).all():
            if not _own(record.book_id, allowed):
                continue
            location = locator.find(name=record.delivery_point_name)
            if location is None:
                unlocated["contracts"] += 1
                continue
            contracts.append(
                {
                    "contract_id": record.contract_id,
                    "contract_name": record.contract_name,
                    "resource_type": record.resource_type,
                    "delivery_point": record.delivery_point_name,
                    "gas_year": record.gas_year,
                    "delivery_mwh_d": record.delivery_quantity_mwh_per_day,
                    "entry_capacity_mwh_d": record.owned_entry_capacity_mwh_per_day,
                    "book_id": record.book_id,
                    "location": location,
                }
            )

        history_cutoff = now - timedelta(days=CARGO_HISTORY_DAYS)
        market_cargoes = []
        for record in session.query(LngCargoRecord).all():
            eta = _aware(record.eta_utc)
            if record.status == "delivered" and (eta is None or eta < history_cutoff):
                continue
            own = record.book_id is not None
            if own and not _own(record.book_id, allowed):
                continue
            position = (
                {"lon": record.position_lon, "lat": record.position_lat}
                if record.position_lat is not None
                else None
            )
            destination = (
                {"lon": record.destination_lon, "lat": record.destination_lat, "match": "feed"}
                if record.destination_lat is not None
                else locator.find(name=record.destination_terminal)
            )
            origin = (
                {"lon": record.load_lon, "lat": record.load_lat}
                if record.load_lat is not None
                else None
            )
            if position is None and destination is None and origin is None:
                unlocated["cargoes"] += 1
                continue
            item = {
                "cargo_id": record.cargo_id,
                "vessel_name": record.vessel_name,
                "vessel_imo": record.vessel_imo,
                "status": record.status,
                "load_port": record.load_port,
                "departed_at_utc": _iso(record.departed_at_utc),
                "destination_terminal": record.destination_terminal,
                "eta_utc": _iso(record.eta_utc),
                "position_at_utc": _iso(record.position_at_utc),
                "volume_m3": record.volume_m3,
                "energy_gwh": record.energy_gwh,
                "own": own,
                "book_id": record.book_id,
                "source_system": record.source_system,
                "origin": origin,
                "position": position,
                "destination": destination,
                "track": [point[:2] for point in (record.track or [])],
            }
            (cargoes if own else market_cargoes).append(item)
        cargoes.extend(entitled(market_cargoes))

        slot_cutoff = now + timedelta(days=SLOT_HORIZON_DAYS)
        for record in session.query(RegasSlotRecord).all():
            start, end = _aware(record.window_start_utc), _aware(record.window_end_utc)
            if end is None or end < now or start is None or start > slot_cutoff:
                continue
            # Slots are always the firm's; an unbooked one is head-office only.
            if not (_own(record.book_id, allowed) if record.book_id else allowed is None):
                continue
            location = (
                {"lon": record.terminal_lon, "lat": record.terminal_lat, "match": "feed"}
                if record.terminal_lat is not None
                else locator.find(name=record.terminal_name)
            )
            if location is None:
                unlocated["regas_slots"] += 1
                continue
            slots.append(
                {
                    "slot_id": record.slot_id,
                    "terminal_name": record.terminal_name,
                    "window_start_utc": start.isoformat(),
                    "window_end_utc": end.isoformat(),
                    "active": start <= now,
                    "send_out_gwh_d": record.send_out_gwh_d,
                    "energy_gwh": record.energy_gwh,
                    "cargo_id": record.cargo_id,
                    "book_id": record.book_id,
                    "location": location,
                }
            )
        slots.sort(key=lambda item: item["window_start_utc"])

    return {
        "as_of_utc": now.isoformat(),
        "outages": outages,
        "flows": flows,
        "contracts": contracts,
        "cargoes": cargoes,
        "regas_slots": slots,
        "unlocated": unlocated,
        "positions_included": include_positions,
    }
