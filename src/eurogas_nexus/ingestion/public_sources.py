"""Normalization helpers for public market and infrastructure sources.

These functions do not perform network I/O. Live fetch commands call them after
explicit operator invocation.
"""

from __future__ import annotations

import hashlib
import math
import re
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from xml.etree import ElementTree

from eurogas_nexus.domain.ingestion.source_timezone import (
    SourceTimezoneError,
    contract_for,
    parse_source_instant,
    resolve_payload_zone,
)
from eurogas_nexus.domain.market.gas_day import EU_CAM_UTC_CALENDAR


def entsog_reference_nodes_from_connectionpoints(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize ENTSOG connection points into DB reference-node rows.

    ENTSOG publishes topology point coordinates as Transparency Platform map
    coordinates rather than WGS84. The client stores both the original ENTSOG
    coordinates and a bounded approximate lon/lat transform for map display.
    """

    rows: list[dict[str, Any]] = []
    for record in _extract_records(payload, "connectionpoints"):
        point_key = str(record.get("pointKey") or "").strip()
        point_label = str(record.get("pointLabel") or point_key).strip()
        if not point_key or not point_label or _as_bool(record.get("isInvalid")):
            continue

        lon, lat = _entsog_map_to_lon_lat(record.get("tpMapX"), record.get("tpMapY"))
        if lon is None or lat is None:
            continue

        node_type = _entsog_node_type(record)
        country = _infer_country(record)
        rows.append(
            {
                "id": f"entsog-{point_key.lower()}",
                "name": point_label,
                "node_type": node_type,
                "country": country,
                "lat": lat,
                "lon": lon,
                "capacity_boe_d": None,
                "source_system": "ENTSOG",
                "source_dataset": "connectionpoints",
                "source_reference": "entsog-connectionpoints",
                "source_record_id": point_key,
                "data_quality": "display_approximation",
                "metadata_json": {
                    "source_system": "ENTSOG",
                    "source_reference": "entsog-connectionpoints",
                    "point_key": point_key,
                    "point_eic_code": record.get("pointEicCode"),
                    "point_type": record.get("pointType"),
                    "commercial_type": record.get("commercialType"),
                    "infrastructure_key": record.get("infrastructureKey"),
                    "infrastructure_label": record.get("infrastructureLabel"),
                    "control_point_type": record.get("controlPointType"),
                    "has_data": _as_bool(record.get("hasData")),
                    "is_interconnection": _as_bool(record.get("isInterconnection")),
                    "is_import": _as_bool(record.get("isImport")),
                    "is_cross_border": _as_bool(record.get("isCrossBorder")),
                    "is_cam_relevant": _as_bool(record.get("isCAMRelevant")),
                    "is_cmp_relevant": _as_bool(record.get("isCMPRelevant")),
                    "has_virtual_point": _as_bool(record.get("hasVirtualPoint")),
                    "virtual_point_key": record.get("virtualPointKey"),
                    "virtual_point_label": record.get("virtualPointLabel"),
                    "entsog_map_x": _to_float(record.get("tpMapX")),
                    "entsog_map_y": _to_float(record.get("tpMapY")),
                    "coordinate_source": "entsog-tp-map-transform",
                    "coordinate_quality": "display_approximation",
                    "data_status": "live_source_metadata",
                },
            }
        )
    return rows


def entsog_reference_facilities_from_connectionpoints(
    payload: dict[str, Any],
) -> list[dict[str, Any]]:
    """Normalize ENTSOG physical point families into reference facilities."""

    rows: list[dict[str, Any]] = []
    for node in entsog_reference_nodes_from_connectionpoints(payload):
        node_type = node["node_type"]
        if node_type not in {"lng", "storage", "entry_point", "interconnection"}:
            continue
        rows.append(
            {
                "id": f"fac-{node['id']}",
                "name": node["name"],
                "facility_type": {
                    "lng": "lng_terminal",
                    "storage": "storage",
                    "entry_point": "entry_point",
                    "interconnection": "border_point",
                }[node_type],
                "country": node["country"],
                "lat": node["lat"],
                "lon": node["lon"],
                "capacity_boe_d": None,
                "source_system": "ENTSOG",
                "source_dataset": "connectionpoints",
                "source_reference": "entsog-connectionpoints",
                "source_record_id": str(node["metadata_json"].get("point_key") or node["id"]),
                "data_quality": "display_approximation",
                "metadata_json": node["metadata_json"],
            }
        )
    return rows


def entsog_market_hubs_from_connectionpoints(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize ENTSOG trading points into market-hub rows."""

    hubs: list[dict[str, Any]] = []
    seen_codes: set[str] = set()
    for node in entsog_reference_nodes_from_connectionpoints(payload):
        if node["node_type"] != "hub":
            continue
        hub_code = _market_hub_code(node["name"], str(node["metadata_json"].get("point_key", "")))
        if hub_code in seen_codes:
            hub_code = f"{hub_code[:11]}-{node['metadata_json']['point_key'][-4:]}"[:16]
        seen_codes.add(hub_code)
        hubs.append(
            {
                "id": f"hub-{str(node['metadata_json']['point_key']).lower()}",
                "name": node["name"],
                "hub_code": hub_code,
                "country": node["country"],
                "description": f"ENTSOG trading point {node['name']}",
                "source_system": "ENTSOG",
                "source_dataset": "connectionpoints",
                "source_reference": "entsog-connectionpoints",
                "source_record_id": str(node["metadata_json"].get("point_key") or node["id"]),
                "data_quality": "display_approximation",
                "metadata_json": node["metadata_json"],
            }
        )
    return hubs


def entsog_tso_access_points_from_json(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize ENTSOG operator point directions into TSO access metadata.

    The dataset's own timestamps go through the ENTSOG timezone declaration too: this read carries
    ``lastUpdateDateTime`` on the same Central European clock as the operational data.
    """

    contract = contract_for("ENTSOG", "operatorpointdirections")
    zone = resolve_payload_zone(contract, payload)
    rows: list[dict[str, Any]] = []
    for record in _extract_records(payload, "operatorpointdirections"):
        point_key = str(record.get("pointKey") or "").strip()
        direction = str(record.get("directionKey") or "unknown").strip().lower()
        operator_key = str(record.get("operatorKey") or "").strip()
        if not point_key or not operator_key or _as_bool(record.get("isInvalid")):
            continue
        node_id = f"entsog-{point_key.lower()}"
        last_update = parse_source_instant(
            record.get("lastUpdateDateTime"), contract=contract, zone=zone
        )
        record_key = _safe_record_key(
            str(
                record.get("id")
                or (
                    f"{operator_key}-{point_key}-{direction}-"
                    f"{record.get('adjacentOperatorKey') or ''}"
                )
            ),
            max_length=52,
        )
        source_record_id = str(record.get("id") or record_key)
        rows.append(
            {
                "access_id": f"entsog-opd-{record_key}",
                "point_id": node_id,
                "point_key": point_key,
                "point_name": str(record.get("pointLabel") or point_key),
                "country": str(record.get("tSOCountry") or record.get("adjacentCountry") or "EU")[
                    :8
                ],
                "operator_key": operator_key,
                "operator_name": str(record.get("operatorLabel") or operator_key),
                "tso_eic_code": record.get("tsoEicCode"),
                "direction": direction[:16],
                "adjacent_country": record.get("adjacentCountry"),
                "adjacent_operator_key": record.get("adjacentOperatorKey"),
                "connected_operators": record.get("connectedOperators"),
                "booking_platform": record.get("bookingPlatformLabel"),
                "booking_platform_url": record.get("bookingPlatformURL"),
                "annual_contracts_available": _as_bool(record.get("annualContractsIsAvailable")),
                "monthly_contracts_available": _as_bool(
                    record.get("monthlyContractsIsAvailable")
                ),
                "daily_contracts_available": _as_bool(record.get("dailyContractsIsAvailable")),
                "day_ahead_contracts_available": _as_bool(
                    record.get("dayAheadContractsIsAvailable")
                ),
                "is_cam_relevant": _as_bool(record.get("isCAMRelevant")),
                "is_cmp_relevant": _as_bool(record.get("isCMPRelevant")),
                "last_update_utc": last_update,
                "source_system": "ENTSOG",
                "source_dataset": "operatorpointdirections",
                "source_reference": "entsog-operatorpointdirections",
                "source_record_id": source_record_id,
                "data_quality": "source_metadata",
                "metadata_json": {
                    "source_system": "ENTSOG",
                    "source_reference": "entsog-operatorpointdirections",
                    "point_key": point_key,
                    "point_label": record.get("pointLabel"),
                    "operator_key": operator_key,
                    "operator_label": record.get("operatorLabel"),
                    "tso_eic_code": record.get("tsoEicCode"),
                    "direction_key": direction,
                    "tso_country": record.get("tSOCountry"),
                    "adjacent_country": record.get("adjacentCountry"),
                    "adjacent_operator_key": record.get("adjacentOperatorKey"),
                    "connected_operators": record.get("connectedOperators"),
                    "booking_platform": record.get("bookingPlatformLabel"),
                    "booking_platform_url": record.get("bookingPlatformURL"),
                    "annual_contracts_available": _as_bool(
                        record.get("annualContractsIsAvailable")
                    ),
                    "monthly_contracts_available": _as_bool(
                        record.get("monthlyContractsIsAvailable")
                    ),
                    "daily_contracts_available": _as_bool(record.get("dailyContractsIsAvailable")),
                    "day_ahead_contracts_available": _as_bool(
                        record.get("dayAheadContractsIsAvailable")
                    ),
                    "is_cam_relevant": _as_bool(record.get("isCAMRelevant")),
                    "is_cmp_relevant": _as_bool(record.get("isCMPRelevant")),
                    "data_status": "live_source_metadata",
                },
            }
        )
    return rows


def ecb_market_observations_from_xml(
    xml_text: str,
    *,
    observed_at_utc: datetime | None = None,
    currencies: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Normalize ECB daily euro FX XML into market observation rows."""

    root = ElementTree.fromstring(xml_text)
    ns = {"ecb": "http://www.ecb.int/vocabulary/2002-08-01/eurofxref"}
    observed_at = _as_utc(observed_at_utc or datetime.now(UTC))
    rows: list[dict[str, Any]] = []

    for day_cube in root.findall(".//ecb:Cube[@time]", ns):
        day = date.fromisoformat(day_cube.attrib["time"])
        period_start = datetime.combine(day, time.min, tzinfo=UTC)
        period_end = period_start + timedelta(days=1)
        for rate_cube in day_cube.findall("ecb:Cube", ns):
            currency = rate_cube.attrib.get("currency", "").upper()
            if not currency or (currencies is not None and currency not in currencies):
                continue
            rate = _to_float(rate_cube.attrib.get("rate"))
            if rate is None:
                continue
            rows.append(
                {
                    "observation_id": f"ecb-fx-{day.isoformat()}-{currency}",
                    "market_venue": "ECB",
                    "product": f"EUR/{currency}",
                    "price": rate,
                    "unit": f"{currency} per EUR",
                    "currency": currency,
                    "period_start_utc": period_start,
                    "period_end_utc": period_end,
                    "observed_at_utc": observed_at,
                    "source_system": "ECB",
                    "source_reference": "ecb-eurofxref-daily",
                    "source_record_id": f"{day.isoformat()}-{currency}",
                    "freshness": "live",
                    "quality_score": 1.0,
                    "research_only": True,
                    "metadata_json": {
                        "source_system": "ECB",
                        "dataset": "eurofxref-daily",
                        "value_date": day.isoformat(),
                        "base_currency": "EUR",
                        "quote_currency": currency,
                    },
                }
            )

    return sorted(rows, key=lambda row: row["observation_id"])


def ecb_fx_observations_from_xml(
    xml_text: str,
    *,
    observed_at_utc: datetime | None = None,
    currencies: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Normalize ECB daily euro FX XML into dedicated FX observation rows."""

    market_rows = ecb_market_observations_from_xml(
        xml_text,
        observed_at_utc=observed_at_utc,
        currencies=currencies,
    )
    rows: list[dict[str, Any]] = []
    for row in market_rows:
        quote = row["currency"]
        rows.append(
            {
                "observation_id": row["observation_id"].replace("ecb-fx-", "ecb-fxrate-"),
                "pair": row["product"].replace("/", ""),
                "base_currency": "EUR",
                "quote_currency": quote,
                "rate": row["price"],
                "rate_type": "reference",
                "value_date": row["period_start_utc"].date().isoformat(),
                "observed_at_utc": row["observed_at_utc"],
                "source_system": "ECB",
                "source_reference": row["source_reference"],
                "source_record_id": row["source_record_id"],
                "freshness": row["freshness"],
                "research_only": row["research_only"],
                "metadata_json": row["metadata_json"],
            }
        )
    return rows


def _entsog_native_time_context(payload: dict[str, Any]) -> tuple[Any, Any]:
    """The ENTSOG timezone declaration shared by the native flow/capacity adapters."""

    contract = contract_for("ENTSOG", "operationaldatas")
    return contract, resolve_payload_zone(contract, payload)


def _entsog_native_parse_instant(
    value: object,
    *,
    contract: Any,
    zone: Any,
) -> datetime | None:
    """Read one ENTSOG provider instant without guessing an unproven zone."""

    return parse_source_instant(value, contract=contract, zone=zone)


def entsog_flow_observations_from_json(
    payload: dict[str, Any],
    *,
    observed_at_utc: datetime | None = None,
) -> list[dict[str, Any]]:
    """Delegate ENTSOG flow normalization to the RFC0005 native adapter.

    The native representation is additive: its deterministic namespace is distinct from the
    legacy ``entsog-flow-<record>`` rows, so old rows are never rewritten or backfilled.
    """

    from eurogas_nexus.ingestion.entsog_native_observations import (
        native_entsog_flow_observations_from_json,
    )

    return native_entsog_flow_observations_from_json(
        payload,
        observed_at_utc=observed_at_utc,
    )


def entsog_capacity_observations_from_json(
    payload: dict[str, Any],
    *,
    observed_at_utc: datetime | None = None,
) -> list[dict[str, Any]]:
    """Delegate ENTSOG capacity normalization to the RFC0005 native adapter."""

    from eurogas_nexus.ingestion.entsog_native_observations import (
        native_entsog_capacity_observations_from_json,
    )

    return native_entsog_capacity_observations_from_json(
        payload,
        observed_at_utc=observed_at_utc,
    )


def gie_storage_observations_from_json(
    payload: dict[str, Any],
    *,
    observed_at_utc: datetime | None = None,
) -> list[dict[str, Any]]:
    """Normalize GIE AGSI records into storage observation rows.

    The gas-day dates go through the frozen CAM calendar (period boundaries); the feed's `updatedAt`
    freshness stamp has no proven zone in this repository, so the GIE declaration refuses a value
    without an offset rather than reading it as UTC (item M1-P0).

    ``observed_at_utc`` is the response-receipt instant supplied by a live caller. It is used as the
    availability instant **only** when the provider stamp cannot be placed in time, and the row then
    records ``availability_basis="response_receipt"`` plus ``provider_updated_at_zone="unproven"``
    so the substitution stays visible. A caller that supplies no receipt keeps the M1-P0 refusal.
    """

    contract = contract_for("GIE", "agsi")
    zone = resolve_payload_zone(contract, payload)
    gie_contract, gie_zone = contract, zone
    rows: list[dict[str, Any]] = []
    for record in _extract_records(payload, "data"):
        code = str(record.get("code") or "").strip()
        gas_day = _parse_date(record.get("gasDayStart"))
        if not code or gas_day is None:
            continue
        period_start, period_end = _gas_day_period(record)
        observed_at, availability_basis = _gie_observed_instant(
            record,
            contract=gie_contract,
            zone=gie_zone,
            fallback=observed_at_utc,
        )
        rows.append(
            {
                "observation_id": f"gie-agsi-{code}-{gas_day.isoformat()}",
                "source_dataset": "AGSI",
                "facility_id": code,
                "facility_name": str(record.get("name") or code),
                "country": code,
                "inventory_twh": _to_float(record.get("gasInStorage")),
                "working_capacity_twh": _to_float(record.get("workingGasVolume")),
                "fill_pct": _to_float(record.get("full")),
                "injection_twh_d": _gwh_to_twh(record.get("injection")),
                "withdrawal_twh_d": _gwh_to_twh(record.get("withdrawal")),
                "period_start_utc": period_start,
                "period_end_utc": period_end,
                "observed_at_utc": observed_at,
                "source_system": "GIE",
                "source_reference": "gie-agsi-api",
                "source_record_id": f"{code}-{gas_day.isoformat()}",
                "freshness": "live",
                "research_only": True,
                "metadata_json": {
                    **_metadata_subset(
                        record,
                        [
                            "code",
                            "name",
                            "url",
                            "gasDayStart",
                            "gasDayEnd",
                            "updatedAt",
                            "status",
                            "country",
                            "countryCode",
                            "operator",
                            "operatorKey",
                        ],
                    ),
                    "calendar_version": EU_CAM_UTC_CALENDAR,
                    "availability_basis": availability_basis,
                    "provider_updated_at_zone": _provider_zone_label(availability_basis),
                },
            }
        )
    return rows


def gie_lng_observations_from_json(
    payload: dict[str, Any],
    *,
    observed_at_utc: datetime | None = None,
) -> list[dict[str, Any]]:
    """Normalize GIE ALSI records into LNG observation rows.

    The reviewed GIE API manual v007 (4 October 2022) documents ``inventory`` and ``dtmi`` as LNG
    volume in 10**3 m3, and ``sendOut`` as GWh/d. DTMI is the Declared Total Maximum Inventory, not
    a days-to-monitor figure. Only an explicit nested ``gwh`` member is converted to TWh (/1000);
    a scalar or ``lng``-only inventory/DTMI stays raw provenance with the energy field ``None``.
    No calorific factor or volume-to-energy inference is applied. A malformed, boolean or non-finite
    explicit ``gwh`` also fails closed to ``None`` and records a unit warning.

    Same declaration as AGSI: the CAM calendar owns the gas-day boundaries and the `updatedAt`
    freshness stamp is refused when it carries no offset. ``observed_at_utc`` is the live caller's
    response-receipt instant, used only when the provider stamp cannot be placed in time, with the
    substitution recorded in ``metadata_json``. The source-unit contract above is the reviewed v007
    contract; later GIE versions are not asserted here.
    """

    contract = contract_for("GIE", "alsi")
    zone = resolve_payload_zone(contract, payload)
    gie_contract, gie_zone = contract, zone
    rows: list[dict[str, Any]] = []
    for record in _extract_records(payload, "data"):
        code = str(record.get("code") or "").strip()
        gas_day = _parse_date(record.get("gasDayStart"))
        if not code or gas_day is None:
            continue
        period_start, period_end = _gas_day_period(record)
        observed_at, availability_basis = _gie_observed_instant(
            record,
            contract=gie_contract,
            zone=gie_zone,
            fallback=observed_at_utc,
        )
        inventory_twh, inventory_provenance, inventory_warnings = _alsi_volume_energy(
            record.get("inventory"), "inventory"
        )
        dtmi_twh, dtmi_provenance, dtmi_warnings = _alsi_volume_energy(
            record.get("dtmi"), "dtmi"
        )
        send_out_twh_d, send_out_provenance, send_out_warnings = _alsi_send_out_energy(
            record.get("sendOut")
        )
        rows.append(
            {
                "observation_id": f"gie-alsi-{code}-{gas_day.isoformat()}",
                "source_dataset": "ALSI",
                "terminal_id": code,
                "terminal_name": str(record.get("name") or code),
                "country": code,
                "inventory_twh": inventory_twh,
                "send_out_twh_d": send_out_twh_d,
                "dtmi_twh": dtmi_twh,
                "period_start_utc": period_start,
                "period_end_utc": period_end,
                "observed_at_utc": observed_at,
                "source_system": "GIE",
                "source_reference": "gie-alsi-api",
                "source_record_id": f"{code}-{gas_day.isoformat()}",
                "freshness": "live",
                "research_only": True,
                "metadata_json": {
                    **_metadata_subset(
                        record,
                        [
                            "code",
                            "name",
                            "url",
                            "gasDayStart",
                            "gasDayEnd",
                            "updatedAt",
                            "status",
                            "country",
                            "countryCode",
                            "operator",
                            "operatorKey",
                        ],
                    ),
                    "calendar_version": EU_CAM_UTC_CALENDAR,
                    "availability_basis": availability_basis,
                    "provider_updated_at_zone": _provider_zone_label(availability_basis),
                    "unit_contract": (
                        "GIE ALSI API v007 (2022-10-04); later versions unverified"
                    ),
                    "measurement_provenance": {
                        "inventory": inventory_provenance,
                        "dtmi": dtmi_provenance,
                        "send_out": send_out_provenance,
                    },
                    "unit_warnings": [
                        *inventory_warnings,
                        *dtmi_warnings,
                        *send_out_warnings,
                    ],
                },
            }
        )
    return rows


def _gie_observed_instant(
    record: dict[str, Any],
    *,
    contract: Any,
    zone: Any,
    fallback: datetime | None,
) -> tuple[datetime, str]:
    """Place a GIE row in time without ever guessing an unproven zone.

    Returns:
        ``(instant, basis)`` where basis is ``provider_updated_at`` when the provider stamp carried
        a usable offset, ``response_receipt`` when the live caller's receipt substitutes for an
        unprovable/absent provider stamp, or ``ingest_clock`` when neither is available.

    Raises:
        SourceTimezoneError: The provider stamp has no proven zone and the caller supplied no
            receipt instant -- the original M1-P0 refusal, preserved for direct normalizer callers.
    """

    unprovable: SourceTimezoneError | None = None
    try:
        provider = parse_source_instant(record.get("updatedAt"), contract=contract, zone=zone)
    except SourceTimezoneError as exc:
        if exc.code != "unprovable_source_timezone":
            raise
        provider = None
        unprovable = exc
    if provider is not None:
        return provider, "provider_updated_at"
    if fallback is not None:
        return fallback, "response_receipt"
    if unprovable is not None:
        raise unprovable
    return datetime.now(UTC), "ingest_clock"


def _provider_zone_label(availability_basis: str) -> str:
    """Whether the provider freshness stamp's zone was proven for this row."""

    return "provider_offset" if availability_basis == "provider_updated_at" else "unproven"


def _extract_records(payload: dict[str, Any], preferred_key: str) -> list[dict[str, Any]]:
    value = payload.get(preferred_key) or payload.get("data") or []
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def _to_float(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", ""))
    except ValueError:
        return None


def _gwh_to_twh(value: object) -> float | None:
    if isinstance(value, dict):
        value = value.get("gwh")
    numeric = _to_float(value)
    return numeric / 1000 if numeric is not None else None


_ALSI_RAW_TEXT_LIMIT = 80


def _alsi_finite_float(value: object) -> float | None:
    """Read an explicit energy scalar without accepting booleans or non-finite values."""

    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    try:
        numeric = float(str(value).replace(",", ""))
    except (TypeError, ValueError, OverflowError):
        return None
    return numeric if math.isfinite(numeric) else None


def _alsi_bounded_raw_scalar(value: object) -> object:
    """Keep raw provenance JSON-safe and bounded instead of echoing an arbitrary payload."""

    if isinstance(value, str):
        if len(value) <= _ALSI_RAW_TEXT_LIMIT:
            return value
        return f"{value[:_ALSI_RAW_TEXT_LIMIT]}..."
    if isinstance(value, bool | int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else repr(value)
    if value is None:
        return None
    return {"unsupported_type": type(value).__name__}


def _alsi_bounded_raw_measurement(raw: object) -> object:
    if isinstance(raw, dict):
        return {
            key: _alsi_bounded_raw_scalar(raw.get(key))
            for key in ("lng", "gwh")
            if key in raw
        }
    return _alsi_bounded_raw_scalar(raw)


def _alsi_measurement_absent(raw: object) -> bool:
    return raw is None or (isinstance(raw, str) and not raw.strip())


def _alsi_volume_energy(
    raw: object,
    field: str,
) -> tuple[float | None, dict[str, Any], list[str]]:
    """Map inventory/DTMI to energy only through an explicit nested ``gwh`` member.

    A scalar or ``lng``-only value is the provider's LNG volume (10**3 m3 in the reviewed v007
    contract), not GWh, so it is retained as provenance and the canonical energy field stays
    ``None``. Booleans, non-finite numbers and malformed explicit ``gwh`` values fail closed too.
    """

    provenance: dict[str, Any] = {
        "raw": _alsi_bounded_raw_measurement(raw),
        "shape": "absent",
        "energy_basis": "absent",
    }
    if _alsi_measurement_absent(raw):
        provenance["raw"] = None
        return None, provenance, []
    if isinstance(raw, dict):
        provenance["shape"] = "nested"
        if "gwh" in raw:
            numeric = _alsi_finite_float(raw.get("gwh"))
            if numeric is None:
                provenance["energy_basis"] = "malformed_explicit_gwh"
                return None, provenance, [f"{field}_explicit_gwh_invalid"]
            provenance["energy_basis"] = "explicit_gwh"
            return numeric / 1000, provenance, []
        if "lng" in raw:
            provenance["energy_basis"] = "literal_lng_volume"
            return (
                None,
                provenance,
                [f"{field}_lng_volume_without_explicit_gwh"],
            )
        provenance["energy_basis"] = "unrecognized_nested"
        return (
            None,
            provenance,
            [f"{field}_nested_measurement_without_explicit_gwh"],
        )
    if isinstance(raw, list | tuple | set):
        provenance["shape"] = "unsupported"
        provenance["energy_basis"] = "unsupported"
        return None, provenance, [f"{field}_measurement_unsupported"]
    provenance["shape"] = "scalar"
    provenance["energy_basis"] = "scalar_volume_not_energy"
    return None, provenance, [f"{field}_scalar_volume_not_converted"]


def _alsi_send_out_energy(
    raw: object,
) -> tuple[float | None, dict[str, Any], list[str]]:
    """Read send-out as GWh/d; an optional nested object still needs an explicit ``gwh`` member."""

    provenance: dict[str, Any] = {
        "raw": _alsi_bounded_raw_measurement(raw),
        "shape": "absent",
        "energy_basis": "absent",
    }
    if _alsi_measurement_absent(raw):
        provenance["raw"] = None
        return None, provenance, []
    if isinstance(raw, dict):
        provenance["shape"] = "nested"
        if "gwh" in raw:
            numeric = _alsi_finite_float(raw.get("gwh"))
            if numeric is None:
                provenance["energy_basis"] = "malformed_explicit_gwh"
                return None, provenance, ["send_out_explicit_gwh_invalid"]
            provenance["energy_basis"] = "explicit_gwh"
            return numeric / 1000, provenance, []
        if "lng" in raw:
            provenance["energy_basis"] = "literal_lng_volume"
            return None, provenance, ["send_out_lng_volume_without_explicit_gwh"]
        provenance["energy_basis"] = "unrecognized_nested"
        return None, provenance, ["send_out_nested_measurement_without_explicit_gwh"]
    if isinstance(raw, list | tuple | set):
        provenance["shape"] = "unsupported"
        provenance["energy_basis"] = "unsupported"
        return None, provenance, ["send_out_measurement_unsupported"]
    numeric = _alsi_finite_float(raw)
    if numeric is None:
        provenance["shape"] = "scalar"
        provenance["energy_basis"] = "malformed_scalar_gwh"
        return None, provenance, ["send_out_scalar_gwh_invalid"]
    provenance["shape"] = "scalar"
    provenance["energy_basis"] = "scalar_gwh_per_day"
    return numeric / 1000, provenance, []


def _parse_date(value: object) -> date | None:
    if value in (None, ""):
        return None
    return date.fromisoformat(str(value)[:10])


def _parse_datetime(value: object) -> datetime | None:
    if value in (None, ""):
        return None
    text = str(value).strip().replace("Z", "+00:00")
    if " " in text and "T" not in text:
        text = text.replace(" ", "T")
    parsed = datetime.fromisoformat(text)
    return _as_utc(parsed)


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _entsog_node_type(record: dict[str, Any]) -> str:
    point_key = str(record.get("pointKey") or "").upper()
    infrastructure = str(record.get("infrastructureKey") or "").upper()
    point_type = str(record.get("pointType") or "").lower()
    if point_key.startswith("VTP") or infrastructure == "VTP" or "trading point" in point_type:
        return "hub"
    if point_key.startswith("LNG") or infrastructure == "LNG" or "lng" in point_type:
        return "lng"
    if point_key.startswith("UGS") or infrastructure == "UGS" or "storage" in point_type:
        return "storage"
    if point_key.startswith("PRD") or "production" in point_type:
        return "entry_point"
    if point_key.startswith("ITP") or _as_bool(record.get("isInterconnection")):
        return "interconnection"
    return "network_point"


def _is_entsog_physical_flow_indicator(indicator: str) -> bool:
    key = indicator.strip().lower().replace("-", " ")
    return re.sub(r"\s+", " ", key) in {"physical flow", "physical flows"}


def _capacity_indicator_type(indicator: str) -> str | None:
    key = indicator.strip().lower().replace("-", " ")
    if "technical" in key and "firm" in key:
        return "firm_technical"
    if "technical" in key and "interruptible" in key:
        return "interruptible_technical"
    if "booked" in key and "firm" in key:
        return "firm_booked"
    if "booked" in key and "interruptible" in key:
        return "interruptible_booked"
    if "available" in key:
        return "firm_available" if "firm" in key else "interruptible_available"
    if "nomination" in key:
        return "nomination"
    return None


def _infer_country(record: dict[str, Any]) -> str:
    direct = str(record.get("importFromCountryKey") or "").strip().upper()
    if re.fullmatch(r"[A-Z]{2}", direct):
        return direct
    label = str(record.get("pointLabel") or "")
    match = re.search(r"\(([A-Z]{2})\)", label)
    if match:
        return match.group(1)
    return "EU"


def _entsog_map_to_lon_lat(x_value: object, y_value: object) -> tuple[float | None, float | None]:
    x = _to_float(x_value)
    y = _to_float(y_value)
    if x is None or y is None:
        return None, None
    lon = (0.18 * x) + 15.04
    lat = (0.12 * y) + 52.71
    if y < -20:
        lat -= 0.0021 * ((-20 - y) ** 2)
    return round(max(-12.5, min(42.5, lon)), 5), round(max(34.5, min(63.5, lat)), 5)


def _market_hub_code(label: str, fallback: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9 -]", " ", label).strip()
    if not cleaned:
        return fallback[:16].upper()
    first = cleaned.split()[0].upper()
    if first in {"VIP", "VIRTUAL"} and len(cleaned.split()) > 1:
        first = cleaned.split()[1].upper()
    return first[:16]


def _gas_day_period(record: dict[str, Any]) -> tuple[datetime, datetime]:
    """Map a GIE ``gasDayStart`` date to a CAM gas-day UTC interval.

    GIE reports the calendar date of the gas day; the interval runs from that
    date's CAM Article 3(16) start (05:00 UTC winter / 04:00 UTC during DST)
    to the following gas day, using the corrected versioned calendar
    ``EU-CAM-UTC-2025``.
    """
    from eurogas_nexus.domain.market.gas_day import gas_day_start_for_date

    start_date = _parse_date(record.get("gasDayStart")) or date.today()
    end_date = _parse_date(record.get("gasDayEnd")) or (start_date + timedelta(days=1))
    return (
        gas_day_start_for_date(start_date, calendar=EU_CAM_UTC_CALENDAR),
        gas_day_start_for_date(end_date, calendar=EU_CAM_UTC_CALENDAR),
    )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _safe_observation_suffix(value: str, *, max_length: int) -> str:
    if len(value) <= max_length:
        return value
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:max_length]


def _safe_record_key(value: str, *, max_length: int) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    if not slug:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()[:max_length]
    if len(slug) <= max_length:
        return slug
    digest = hashlib.sha256(slug.encode("utf-8")).hexdigest()[:12]
    return f"{slug[: max_length - 13]}-{digest}"


def _metadata_subset(record: dict[str, Any], keys: list[str]) -> dict[str, Any]:
    return {key: record.get(key) for key in keys if record.get(key) not in (None, "")}
