"""Normalization helpers for public market and infrastructure sources.

These functions do not perform network I/O. Live fetch commands call them after
explicit operator invocation.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from xml.etree import ElementTree

KWH_PER_MCM = 10_550_000.0


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
                    "freshness": "live",
                    "quality_score": 1.0,
                    "research_only": True,
                }
            )

    return sorted(rows, key=lambda row: row["observation_id"])


def entsog_flow_observations_from_json(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize ENTSOG operational data JSON into flow observation rows."""

    records = _extract_records(payload, "operationaldatas")
    rows: list[dict[str, Any]] = []
    for record in records:
        record_id = str(record.get("id") or "").strip()
        value = _to_float(record.get("value"))
        if not record_id or value is None:
            continue
        period_start = _parse_datetime(record.get("periodFrom"))
        period_end = _parse_datetime(record.get("periodTo"))
        if period_start is None or period_end is None:
            continue
        unit = str(record.get("unit") or "").lower()
        flow_mcm_d = value / KWH_PER_MCM if unit in {"kwh/d", "kwh/day"} else value
        safe_id = _safe_observation_suffix(record_id, max_length=52)
        rows.append(
            {
                "observation_id": f"entsog-flow-{safe_id}",
                "point_id": str(record.get("pointKey") or record.get("pointLabel") or record_id),
                "point_name": str(record.get("pointLabel") or record.get("pointKey") or record_id),
                "direction": str(record.get("directionKey") or "unknown").lower()[:8],
                "flow_mcm_d": round(flow_mcm_d, 6),
                "period_start_utc": period_start,
                "period_end_utc": period_end,
                "observed_at_utc": _parse_datetime(record.get("lastUpdateDateTime"))
                or datetime.now(UTC),
                "source_system": "ENTSOG",
                "source_reference": "entsog-operationaldatas",
                "freshness": "live",
                "research_only": True,
            }
        )
    return rows


def gie_storage_observations_from_json(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize GIE AGSI records into storage observation rows."""

    rows: list[dict[str, Any]] = []
    for record in _extract_records(payload, "data"):
        code = str(record.get("code") or "").strip()
        gas_day = _parse_date(record.get("gasDayStart"))
        if not code or gas_day is None:
            continue
        period_start, period_end = _gas_day_period(record)
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
                "injection_twh_d": _to_float(record.get("injection")),
                "withdrawal_twh_d": _to_float(record.get("withdrawal")),
                "period_start_utc": period_start,
                "period_end_utc": period_end,
                "observed_at_utc": _parse_datetime(record.get("updatedAt")) or datetime.now(UTC),
                "source_system": "GIE",
                "source_reference": "gie-agsi-api",
                "freshness": "live",
                "research_only": True,
            }
        )
    return rows


def gie_lng_observations_from_json(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize GIE ALSI records into LNG observation rows."""

    rows: list[dict[str, Any]] = []
    for record in _extract_records(payload, "data"):
        code = str(record.get("code") or "").strip()
        gas_day = _parse_date(record.get("gasDayStart"))
        if not code or gas_day is None:
            continue
        period_start, period_end = _gas_day_period(record)
        rows.append(
            {
                "observation_id": f"gie-alsi-{code}-{gas_day.isoformat()}",
                "source_dataset": "ALSI",
                "terminal_id": code,
                "terminal_name": str(record.get("name") or code),
                "country": code,
                "inventory_twh": _to_float(record.get("inventory")),
                "send_out_twh_d": _to_float(record.get("sendOut")),
                "dtmi_pct": _to_float(record.get("dtmi")),
                "period_start_utc": period_start,
                "period_end_utc": period_end,
                "observed_at_utc": _parse_datetime(record.get("updatedAt")) or datetime.now(UTC),
                "source_system": "GIE",
                "source_reference": "gie-alsi-api",
                "freshness": "live",
                "research_only": True,
            }
        )
    return rows


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


def _gas_day_period(record: dict[str, Any]) -> tuple[datetime, datetime]:
    start_date = _parse_date(record.get("gasDayStart")) or date.today()
    end_date = _parse_date(record.get("gasDayEnd")) or (start_date + timedelta(days=1))
    return (
        datetime.combine(start_date, time.min, tzinfo=UTC),
        datetime.combine(end_date, time.min, tzinfo=UTC),
    )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _safe_observation_suffix(value: str, *, max_length: int) -> str:
    if len(value) <= max_length:
        return value
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:max_length]
