"""What is happening on the network now, located on the map.

One read composes the live picture a desk head or manager scans: outages, today's
physical flows at points, the firm's upstream contracts at their delivery points, LNG
cargoes at sea and the firm's regas slots. Every item is placed only where a source
locates it:

- outages by the asset's EIC code on a network point (the REMIT key), else by exact name;
- contracts by their delivery point's name on a network point;
- cargoes and slots by the coordinates the vessel feed or ETRM supplied, else the
  terminal's network point.

Items that cannot be located are counted, never placed at a guessed position. That includes
network points themselves: ENTSOG publishes some points (Dornum, Emden) in its operator point
directions with no map position, so they are reference access rows with no node; they are
counted in ``unlocated.network_points`` and listed, as are flows at points with no position
(``unlocated.flows``). Book-held items follow portfolio isolation; market items follow the
caller's data scopes.
"""

from __future__ import annotations

import re
import unicodedata
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


LOCATION_MATCH_RULE = (
    "Outages, contracts and cargoes are placed by EIC exactly; else by exact name when it "
    "names one place; else by site name without bracketed notes or generic words (UGS, "
    "storage, LNG) when it names one place. An ambiguous or unknown name stays unlocated "
    "with the reason."
)


def _key(text: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").casefold()).strip()


def _aware(moment: datetime | None) -> datetime | None:
    if moment is None:
        return None
    return moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment.astimezone(UTC)


def _iso(moment: datetime | None) -> str | None:
    value = _aware(moment)
    return value.isoformat() if value else None


# Words that name the kind of site, not the site: dropped for the facility-name step.
_GENERIC_NAME_WORDS = frozenset(
    {"ugs", "vgs", "cugs", "gas", "storage", "speicher", "gasspeicher", "lng", "terminal",
     "fsru", "de", "nl", "h", "l"}
)


def _facility_keys(text: str | None) -> set[str]:
    """Normalised site names: the whole name and each ``A / B`` side of an ENTSOG point,
    without accents, bracketed operator notes or generic words (UGS, storage, LNG...)."""

    keys: set[str] = set()
    raw = text or ""
    for part in [raw, *raw.split(" / ")]:
        ascii_text = unicodedata.normalize("NFKD", part).encode("ascii", "ignore").decode()
        cleaned = re.sub(r"\([^)]*\)", " ", ascii_text.casefold())
        words = [w for w in re.split(r"[^a-z0-9]+", cleaned) if w and w not in _GENERIC_NAME_WORDS]
        if words:
            keys.add(" ".join(words))
    return keys


class _Locator:
    """Network points and facilities indexed by EIC code and by normalised name.

    Matching, in order of reliability (``LOCATION_MATCH_RULE``):

    1. ``eic``: the EIC code exactly (point or facility EIC in the reference metadata);
    2. ``name``: the exact name (case and punctuation ignored), when it names one place;
    3. ``facility_name``: the site name without bracketed notes or generic words (UGS,
       storage, LNG...), compared with the whole name and each side of an ``A / B``
       ENTSOG point, when it names one place.

    A node and a facility at the same coordinates are one place.  Nothing fuzzy: a name
    that names several places, or none, stays unlocated and ``explain`` says why.
    """

    def __init__(self, nodes: list[Any], facilities: list[Any]) -> None:
        self.by_eic: dict[str, dict[str, Any]] = {}
        self.by_name: dict[str, list[dict[str, Any]]] = {}
        self.by_facility_key: dict[str, list[dict[str, Any]]] = {}
        self.by_node_id: dict[str, dict[str, Any]] = {}
        for item, kind in [(n, "node") for n in nodes] + [(f, "facility") for f in facilities]:
            meta = item.metadata_json or {}
            location = {
                "lon": item.lon,
                "lat": item.lat,
                "ref_id": item.id,
                "ref_kind": kind,
                "ref_name": item.name,
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
            self.by_name.setdefault(_key(item.name), []).append(location)
            for facility_key in _facility_keys(item.name):
                self.by_facility_key.setdefault(facility_key, []).append(location)

    @staticmethod
    def _places(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """One entry per coordinate; ``points_at_place`` counts the reference points there
        (Etzel's operators' points share one site), so the named point is not over-read."""

        unique: dict[tuple[float, float], dict[str, Any]] = {}
        counts: dict[tuple[float, float], set[str]] = {}
        for location in candidates:
            place = (round(location["lat"], 5), round(location["lon"], 5))
            unique.setdefault(place, location)
            counts.setdefault(place, set()).add(location["ref_id"])
        return [
            {**location, "points_at_place": len(counts[place])}
            for place, location in unique.items()
        ]

    def explain(
        self, *, eic: str | None = None, name: str | None = None
    ) -> tuple[dict[str, Any] | None, str]:
        """The location and how it was found, or None and why not."""

        if eic and (hit := self.by_eic.get(eic.strip().upper())):
            return {**hit, "match": "eic"}, "eic"
        if not name:
            return None, "no_eic_match_and_no_name"
        exact = self._places(self.by_name.get(_key(name), []))
        if len(exact) == 1:
            return {**exact[0], "match": "name"}, "name"
        if len(exact) > 1:
            return None, f"ambiguous_name:{len(exact)}_places"
        pooled = [
            location
            for facility_key in _facility_keys(name)
            for location in self.by_facility_key.get(facility_key, [])
        ]
        candidates = {
            (round(location["lat"], 5), round(location["lon"], 5)): location
            for location in self._places(pooled)
        }
        if len(candidates) == 1:
            return {**next(iter(candidates.values())), "match": "facility_name"}, "facility_name"
        if candidates:
            names = sorted({c["ref_name"] for c in candidates.values()})[:4]
            return None, f"ambiguous_facility_name:{len(candidates)}_places:" + "; ".join(names)
        return None, "no_reference_match"

    def find(self, *, eic: str | None = None, name: str | None = None) -> dict[str, Any] | None:
        return self.explain(eic=eic, name=name)[0]


KNOWN_FACILITY_RULE = (
    "An outage the reference network cannot place is matched to GIE's facility listing by "
    "EIC, else by the exact facility name (case, accents and punctuation ignored) when it "
    "names one facility, else when its asset EIC is the GIE operator EIC of exactly one "
    "current facility of that kind, else through the reviewed alias table (a site of a "
    "virtual storage group maps to the group; each entry cites both publishers' records). "
    "A facility whose EIC is an ENTSOG point EIC, or that the alias table ties to an ENTSOG "
    "point, is placed at that point; otherwise it is a known facility with no published "
    "position (name, EIC, country, operator), counted apart from unlocated outages. GIE "
    "publishes no coordinates, and no position is derived from a name."
)


def _ascii_key(text: str | None) -> str:
    folded = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    return _key(folded)


def _current_facility(facility: dict[str, Any], today: str) -> bool:
    """Not a GIE 'historical data prior to …' entry, and not past its operational end."""

    if "historical data" in str(facility.get("name") or "").casefold():
        return False
    end = str(facility.get("operational_end_date") or "")
    return not end or end >= today


class _KnownFacilities:
    """GIE facility identity (``db/repositories/gie_facilities``) by EIC, exact name and
    operator EIC, and the reviewed alias table (``reference_data/outage_aliases``)."""

    def __init__(
        self, facilities: list[dict[str, Any]], *, today: str = "", aliases: Any = None
    ) -> None:
        self.by_eic = {str(f.get("eic") or "").upper(): f for f in facilities if f.get("eic")}
        self.by_name: dict[str, list[dict[str, Any]]] = {}
        self.by_operator: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for facility in facilities:
            self.by_name.setdefault(_ascii_key(facility.get("name")), []).append(facility)
            if facility.get("operator_eic") and _current_facility(facility, today):
                key = (str(facility["operator_eic"]).upper(), str(facility.get("kind") or ""))
                self.by_operator.setdefault(key, []).append(facility)
        self.aliases = aliases

    def find(
        self, *, eic: str | None, name: str | None, kind: str | None = None
    ) -> tuple[dict[str, Any] | None, str]:
        if eic and (hit := self.by_eic.get(eic.strip().upper())):
            return hit, "eic"
        named = self.by_name.get(_ascii_key(name), []) if name else []
        if len(named) == 1:
            return named[0], "name"
        # A message that names its operator's EIC as the asset: unambiguous only when that
        # operator runs one current facility of the asset's kind (Adriatic LNG → Rovigo).
        if eic and kind:
            operated = self.by_operator.get((eic.strip().upper(), kind.casefold()), [])
            if len(operated) == 1:
                return operated[0], "operator_eic"
        if self.aliases is not None:
            entry = self.aliases.facility_for(eic=eic, name=name)
            if entry and (hit := self.by_eic.get(str(entry["gie_facility_eic"]).upper())):
                return {**hit, "alias_site": entry.get("site")}, "alias"
        return None, ""

    def point_key(self, facility_eic: str | None) -> str | None:
        """The ENTSOG point the alias table ties this facility to, if any."""

        if self.aliases is None:
            return None
        entry = self.aliases.point_for(facility_eic)
        return str(entry["reference_point_key"]) if entry else None


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
    vessel_feed_entitled: bool | None = None,
    principal: Any = None,
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
        ReferenceTsoAccessPoint,
        RegasSlotRecord,
        UpstreamResourceContractRecord,
    )
    from eurogas_nexus.db.models.reference_network import REFERENCE_RETIRED_QUALITY
    from eurogas_nexus.domain.market.gas_day import gas_day_label, gas_day_start_utc

    reference_nodes = [
        node
        for node in session.query(ReferenceNode).all()
        if node.data_quality != REFERENCE_RETIRED_QUALITY
    ]
    locator = _Locator(reference_nodes, session.query(ReferenceFacility).all())
    reference_countries = {
        str(node.country).upper()
        for node in reference_nodes
        if node.country and node.lat is not None and node.lon is not None
    }
    from eurogas_nexus.db.repositories.gie_facilities import load_gie_facilities
    from eurogas_nexus.reference_data.outage_aliases import shipped_aliases

    known_facilities = _KnownFacilities(
        load_gie_facilities(session), today=now.date().isoformat(), aliases=shipped_aliases()
    )
    known_outages: dict[str, dict[str, Any]] = {}
    unlocated = {
        "outages": 0,
        "contracts": 0,
        "cargoes": 0,
        "regas_slots": 0,
        "network_points": 0,
        "flows": 0,
    }

    # Network points the reference knows (an operator publishes a direction at them) but no
    # source gives a position for: counted and listed, never placed.
    unlocated_points: dict[str, dict[str, Any]] = {}
    for access in session.query(ReferenceTsoAccessPoint).all():
        if access.data_quality == REFERENCE_RETIRED_QUALITY or access.point_key is None:
            continue
        if access.point_id and access.point_id in locator.by_node_id:
            continue
        if locator.by_node_id.get(f"entsog-{access.point_key.lower()}") is not None:
            continue
        held = unlocated_points.setdefault(
            access.point_key,
            {
                "point_key": access.point_key,
                "point_name": access.point_name,
                "countries": set(),
                "operators": set(),
                "reason": "no_position_published",
            },
        )
        held["countries"].add((access.country or "").upper())
        held["operators"].add(access.operator_name)
    unlocated_network_points = [
        {
            **item,
            "countries": sorted(c for c in item["countries"] if c),
            "operators": sorted(o for o in item["operators"] if o),
        }
        for _, item in sorted(unlocated_points.items())
    ]
    unlocated["network_points"] = len(unlocated_network_points)

    outages = []
    # Counts are of every outage the caller may see, placed on the map or not: a count that
    # dropped the unplaced ones would contradict the ticker and the events table.
    outage_counts = {"active": 0, "scheduled": 0}
    unlocated_outages: list[dict[str, Any]] = []
    from eurogas_nexus.domain.observations.remit_umm import outage_unit_summary

    visible_outages = list(
        entitled(load_outage_rows(session, now=now, horizon_days=outage_horizon_days))
    )
    for row in visible_outages:
        outage_counts["active" if row.get("status") == "active" else "scheduled"] += 1
        location, how = locator.explain(
            eic=str(row["facility_id"]), name=str(row["facility_name"])
        )
        if location is None:
            facility, identified_by = known_facilities.find(
                eic=str(row["facility_id"]),
                name=str(row["facility_name"]),
                kind=str(row.get("asset_type") or "") or None,
            )
            if facility is not None:
                at_point = locator.by_eic.get(str(facility["eic"]).upper())
                match = f"gie_facility_{identified_by}"
                if at_point is None and (key := known_facilities.point_key(facility["eic"])):
                    at_point = locator.by_node_id.get(key)
                    match = f"{match}_alias_point"
                if at_point is not None:
                    location = {**at_point, "match": match}
                else:
                    held = known_outages.setdefault(
                        str(facility["eic"]),
                        {
                            "facility_eic": facility["eic"],
                            "facility_name": facility.get("name"),
                            "country": facility.get("country"),
                            "operator": facility.get("operator_name"),
                            "kind": facility.get("kind"),
                            "identified_by": identified_by,
                            # The reference network holds no point at all in that country (the
                            # shipped bundle covers NW Europe until ENTSOG's reference is read).
                            "reason": (
                                "no_published_position"
                                if str(facility.get("country") or "").upper() in reference_countries
                                else "outside_reference_network"
                            ),
                            "outages": 0,
                            "event_ids": [],
                            "message_names": [],
                            "sites": [],
                        },
                    )
                    held["outages"] += 1
                    site = facility.get("alias_site")
                    if site and site not in held["sites"]:
                        held["sites"].append(site)
                    held["event_ids"].append(row["event_id"])
                    if row["facility_name"] not in held["message_names"]:
                        held["message_names"].append(row["facility_name"])
                    continue
        if location is None:
            unlocated["outages"] += 1
            unlocated_outages.append(
                {
                    "event_id": row["event_id"],
                    "facility_name": row["facility_name"],
                    "facility_id": row["facility_id"],
                    "market_participant": row.get("market_participant"),
                    "reason": how,
                    # Enough for the book view to place it at its zone's hub, said as such.
                    "balancing_zone": row.get("balancing_zone"),
                    "status": row.get("status"),
                    "start_utc": row.get("start_utc"),
                    "end_utc": row.get("end_utc"),
                    "unavailable_gwh_d": row.get("unavailable_gwh_d"),
                    "source_system": row.get("source_system"),
                    "source_reference": row.get("source_reference"),
                }
            )
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
                        "daily_basis",
                        "description",
                        "market_participant",
                        "source_system",
                    )
                },
                # A demo message says so here (its platform field is "REMIT").
                "source_reference": row.get("source_reference"),
                # The platform and the credit its terms ask for (ENTSOG: with the date).
                "platform": row.get("platform", ""),
                "attribution": row.get("attribution", ""),
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
    from eurogas_nexus.application.identity_resolution import identity_clause

    flow_rows = (
        session.query(FlowObservationRecord)
        .filter(identity_clause(session, FlowObservationRecord))
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
    unplaced_flows: list[dict[str, Any]] = []
    for (point_id, direction), record in latest.items():
        location = locator.by_node_id.get(point_id) or locator.by_node_id.get(
            f"entsog-{point_id.lower()}"
        )
        if location is None:
            unplaced_flows.append(
                {
                    "point_id": point_id,
                    "direction": direction,
                    "source_system": record.source_system,
                }
            )
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
    # Counted after the scope filter, like the placed ones: a count must not reveal rows the
    # caller may not see.
    unlocated["flows"] = len(entitled(unplaced_flows))

    contracts: list[dict[str, Any]] = []
    cargoes: list[dict[str, Any]] = []
    slots: list[dict[str, Any]] = []
    # Market LNG vessels come only from the customer's licensed vessel feed (Kpler or an AIS
    # provider, docs/legal/DATA_SOURCE_TERMS.md): the map says when the caller holds no such
    # entitlement instead of showing an empty sea.
    vessel_feed: dict[str, Any] = {
        "entitled": vessel_feed_entitled,
        "market_cargoes": 0,
        "simulated": 0,
        "families": ["Kpler"],
    }
    # Every active contract on the caller's books, placed or not, for the "Our book" view.
    book_contracts: list[dict[str, Any]] = []
    confirmations: list[Any] = []
    if include_positions:
        allowed = visible_book_ids(session)
        for record in (
            session.query(UpstreamResourceContractRecord)
            .filter(UpstreamResourceContractRecord.retired_at_utc.is_(None))
            .all()
        ):
            if not _own(record.book_id, allowed):
                continue
            # Contract kinds: a master is not on the map; a cargo confirmation is drawn as an
            # expected cargo below (DES at its terminal), not as a delivery point.
            if (record.contract_kind or "SUPPLY_GSA") in {"LNG_MSPA", "LNG_CARGO"}:
                if record.contract_kind == "LNG_CARGO":
                    confirmations.append(record)
                continue
            location = locator.find(name=record.delivery_point_name)
            book_contracts.append(
                {
                    "contract_id": record.contract_id,
                    "contract_name": record.contract_name,
                    "delivery_point": record.delivery_point_name,
                    "delivery_mwh_d": record.delivery_quantity_mwh_per_day,
                    "entry_capacity_mwh_d": record.owned_entry_capacity_mwh_per_day,
                    "allowed_exit_points": list(record.allowed_exit_points or []),
                    "gas_year": record.gas_year,
                    "location": location,
                }
            )
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
        cargoes.extend(_confirmed_cargoes(confirmations, cargoes, locator, now))
        visible_market = entitled(market_cargoes)
        cargoes.extend(visible_market)
        vessel_feed["market_cargoes"] = len(visible_market)
        vessel_feed["simulated"] = sum(
            1 for item in visible_market if str(item.get("source_system", "")).endswith("_Sim")
        )

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

    # The "Our book" view (design basis 2, J.5): what on the network relates to the deals.
    book_relevance = None
    if include_positions:
        from eurogas_nexus.application.map_book import build_book_relevance

        book_relevance = build_book_relevance(
            session,
            now=now,
            contracts=book_contracts,
            cargoes=cargoes,
            slots=slots,
            outages=outages,
            unlocated_outages=unlocated_outages,
            locate=lambda name: locator.find(name=name),
            entitled=entitled,
            book_ids=allowed,
            principal=principal,
        )

    return {
        "as_of_utc": now.isoformat(),
        "outages": outages,
        "flows": flows,
        "flow_rule": FLOW_DAY_RULE,
        "contracts": contracts,
        "cargoes": cargoes,
        "regas_slots": slots,
        "unlocated": unlocated,
        "outage_units": outage_unit_summary(visible_outages),
        "unlocated_outages": unlocated_outages,
        # Outages at facilities GIE identifies but no accepted source positions.
        "known_facility_outages": sorted(
            known_outages.values(), key=lambda item: (-item["outages"], item["facility_eic"])
        ),
        "outage_placement": {
            "placed": len(outages),
            "known_facility_no_position": sum(
                item["outages"] for item in known_outages.values()
            ),
            "unlocated": unlocated["outages"],
            "rule": KNOWN_FACILITY_RULE,
        },
        "unlocated_network_points": unlocated_network_points,
        "location_match_rule": LOCATION_MATCH_RULE,
        "totals": {
            "network_points": len(reference_nodes) + unlocated["network_points"],
            "outages_active": outage_counts["active"],
            "outages_scheduled": outage_counts["scheduled"],
            "contracts": len(contracts) + unlocated["contracts"],
            "cargoes": len(cargoes) + unlocated["cargoes"],
            "regas_slots": len(slots) + unlocated["regas_slots"],
        },
        "positions_included": include_positions,
        "vessel_feed": vessel_feed,
        "book_relevance": book_relevance,
    }


def _confirmed_cargoes(
    confirmations: list[Any], held: list[dict[str, Any]], locator: Any, now: datetime
) -> list[dict[str, Any]]:
    """Cargo confirmations (CONTRACT_TYPES.md) the vessel feed does not hold yet, as expected
    cargoes: the terminal is the destination and the delivery window's first day the ETA.

    A confirmation whose vessel is already in the feed (``lng_cargo_id``) is drawn there, not
    twice. An FOB cargo has no European destination yet and is not drawn; a window that has
    passed is history, not an expected arrival.
    """

    from eurogas_nexus.domain.contracts import kinds

    known = {item["cargo_id"] for item in held}
    out: list[dict[str, Any]] = []
    for record in confirmations:
        terms = kinds.terms_of(record.contract_kind, record.kind_terms)
        if not isinstance(terms, kinds.LngCargoTerms) or terms.delivery_term != "DES":
            continue
        if terms.lng_cargo_id and terms.lng_cargo_id in known:
            continue
        first, last = terms.delivery_days()
        if last < now.date():
            continue
        destination = locator.find(name=terms.discharge_terminal)
        if destination is None:
            continue
        out.append(
            {
                "cargo_id": f"contract:{record.contract_id}",
                "vessel_name": terms.vessel_name or record.contract_name,
                "vessel_imo": None,
                "status": "contracted",
                "load_port": terms.load_port or "",
                "departed_at_utc": None,
                "destination_terminal": terms.discharge_terminal,
                "eta_utc": datetime.combine(first, datetime.min.time(), tzinfo=UTC).isoformat(),
                "position_at_utc": None,
                "volume_m3": None,
                "energy_gwh": round(terms.energy_mwh() / 1000, 1),
                "own": True,
                "book_id": record.book_id,
                "source_system": "CONTRACT",
                "contract_id": record.contract_id,
                "origin": None,
                "position": None,
                "destination": destination,
                "track": [],
                "track_times": [],
            }
        )
    return out
