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

#: Closed gas days read for flows: the newest one shown per point, the earlier ones only so
#: the operator choice can follow the previous day (pipeline_supply.select_operator_rows).
FLOW_LOOKBACK_DAYS = 5
#: How the map chooses the flow it shows at a point; returned with the payload.
FLOW_DAY_RULE = (
    "Each point shows its newest closed gas day (the period ended before the current gas "
    "day began, EU-CAM calendar) from rows received after that day closed; a snapshot "
    "taken while the day was open is not a day's flow. One operator's report per point "
    "and gas day, kept on the previous day's operator while it reports; direction is "
    "relative to that operator's system."
)
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
                "country": (item.country or "").upper() or None,
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
    history_days: int = 0,
) -> dict[str, Any]:
    """The live map payload. ``entitled`` filters market rows by the caller's data scopes.

    ``history_days`` also returns the firm's own cargoes delivered and regas slots ended in
    that many past days, so a completed deal can be looked back at (and replayed along its
    timed track); market cargoes keep the short ``CARGO_HISTORY_DAYS`` tail.
    """

    from eurogas_nexus.application.pipeline_supply import gas_day as flow_gas_day
    from eurogas_nexus.application.pipeline_supply import (
        published_after_close,
        row_energy_gwh,
        row_operator,
        select_operator_rows,
    )
    from eurogas_nexus.application.remit_outages import load_outage_rows
    from eurogas_nexus.db.models import (
        FlowObservationRecord,
        LngCargoRecord,
        ReferenceFacility,
        ReferenceNode,
        RegasSlotRecord,
        UpstreamResourceContractRecord,
    )
    from eurogas_nexus.domain.market.gas_day import gas_day_label, gas_day_start_utc

    locator = _Locator(session.query(ReferenceNode).all(), session.query(ReferenceFacility).all())
    unlocated = {"outages": 0, "contracts": 0, "cargoes": 0, "regas_slots": 0}

    outages = []
    # Counts are of every outage the caller may see, placed on the map or not: a count that
    # dropped the unplaced ones would contradict the ticker and the events table.
    outage_counts = {"active": 0, "scheduled": 0}
    for row in entitled(load_outage_rows(session, now=now, horizon_days=outage_horizon_days)):
        outage_counts["active" if row.get("status") == "active" else "scheduled"] += 1
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

    # Closed gas days only, by the calendar every reader uses: the open day (and the next,
    # which ENTSOG also publishes) is still being reported and would read as a low flow.
    open_day_start = gas_day_start_utc(now)
    flow_rows = (
        session.query(FlowObservationRecord)
        .filter(
            FlowObservationRecord.period_start_utc
            >= bound(open_day_start - timedelta(days=FLOW_LOOKBACK_DAYS))
        )
        .filter(FlowObservationRecord.period_end_utc <= bound(open_day_start))
        .filter(FlowObservationRecord.kind == "actual")
        .order_by(FlowObservationRecord.period_start_utc.desc())
        .limit(20_000)
        .all()
    )
    # One operator's report per point and gas day (pipeline_supply.OPERATOR_SELECTION_RULE):
    # both sides of an interconnection publish the point, each from its own side. The
    # helper keeps the previous day's operator while it reports, so the side the direction
    # is read from does not flip between days.
    selected = select_operator_rows(row for row in flow_rows if published_after_close(row))
    newest_day: dict[str, Any] = {}
    for record in selected:
        if row_energy_gwh(record)[0] is None:
            continue
        day = flow_gas_day(record)
        held = newest_day.get(record.point_id)
        if held is None or day > held:
            newest_day[record.point_id] = day
    latest: dict[tuple[str, str], Any] = {}
    for record in selected:
        if newest_day.get(record.point_id) == flow_gas_day(record):
            latest.setdefault((record.point_id, record.direction), record)
    flows = []
    for (point_id, direction), record in latest.items():
        location = locator.by_node_id.get(point_id) or locator.by_node_id.get(
            f"entsog-{point_id.lower()}"
        )
        if location is None:
            continue
        unit = record.original_unit or ""
        energy, from_volume = row_energy_gwh(record)
        # Energy as published only; a volume is not turned into energy at a guessed GCV.
        gwh_d = round(energy, 3) if energy is not None and not from_volume else None
        flows.append(
            {
                "point_id": point_id,
                "point_name": record.point_name,
                "direction": direction,
                "gas_day": gas_day_label(_aware(record.period_start_utc)),
                "gas_day_start_utc": _iso(record.period_start_utc),
                "gas_day_end_utc": _iso(record.period_end_utc),
                "value": record.original_value
                if record.original_value is not None
                else record.flow_mcm_d,
                "unit": unit or "mcm/d",
                "gwh_d": gwh_d,
                "source_system": record.source_system,
                "operator_key": row_operator(record) or None,
                "location": location,
            }
        )
    flows = entitled(flows)

    contracts: list[dict[str, Any]] = []
    cargoes: list[dict[str, Any]] = []
    slots: list[dict[str, Any]] = []
    if include_positions:
        allowed = visible_book_ids(session)
        for record in (
            session.query(UpstreamResourceContractRecord)
            .filter(UpstreamResourceContractRecord.retired_at_utc.is_(None))
            .all()
        ):
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
        own_history_cutoff = now - timedelta(days=max(CARGO_HISTORY_DAYS, history_days))
        market_cargoes = []
        for record in session.query(LngCargoRecord).all():
            eta = _aware(record.eta_utc)
            own = record.book_id is not None
            cutoff = own_history_cutoff if own else history_cutoff
            if record.status == "delivered" and (eta is None or eta < cutoff):
                continue
            if own and not _own(record.book_id, allowed):
                continue
            position = (
                {"lon": record.position_lon, "lat": record.position_lat}
                if record.position_lat is not None
                else None
            )
            destination = (
                {
                    "lon": record.destination_lon,
                    "lat": record.destination_lat,
                    "match": "feed",
                    "country": record.destination_country,
                }
                if record.destination_lat is not None
                else locator.find(name=record.destination_terminal)
            )
            if destination is not None and not destination.get("country"):
                named = locator.find(name=record.destination_terminal)
                destination["country"] = named.get("country") if named else None
            origin = (
                {"lon": record.load_lon, "lat": record.load_lat, "country": record.load_country}
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
                # When the vessel was at each track point (ISO, or null when not reported).
                "track_times": [
                    point[2] if len(point) > 2 else None for point in (record.track or [])
                ],
            }
            (cargoes if own else market_cargoes).append(item)
        cargoes.extend(entitled(market_cargoes))

        slot_cutoff = now + timedelta(days=SLOT_HORIZON_DAYS)
        for record in session.query(RegasSlotRecord).all():
            start, end = _aware(record.window_start_utc), _aware(record.window_end_utc)
            if (
                end is None
                or end < now - timedelta(days=history_days)
                or start is None
                or start > slot_cutoff
            ):
                continue
            # Slots are always the firm's; an unbooked one is head-office only.
            if not (_own(record.book_id, allowed) if record.book_id else allowed is None):
                continue
            location = (
                {
                    "lon": record.terminal_lon,
                    "lat": record.terminal_lat,
                    "match": "feed",
                    "country": record.terminal_country,
                }
                if record.terminal_lat is not None
                else locator.find(name=record.terminal_name)
            )
            if location is not None and not location.get("country"):
                named = locator.find(name=record.terminal_name)
                location["country"] = named.get("country") if named else None
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
        "flow_rule": FLOW_DAY_RULE,
        "contracts": contracts,
        "cargoes": cargoes,
        "regas_slots": slots,
        "unlocated": unlocated,
        "totals": {
            "outages_active": outage_counts["active"],
            "outages_scheduled": outage_counts["scheduled"],
            "contracts": len(contracts) + unlocated["contracts"],
            "cargoes": len(cargoes) + unlocated["cargoes"],
            "regas_slots": len(slots) + unlocated["regas_slots"],
        },
        "positions_included": include_positions,
    }
