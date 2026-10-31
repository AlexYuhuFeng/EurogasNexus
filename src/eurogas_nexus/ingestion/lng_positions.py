"""LNG cargoes and regas slots from a vessel-tracking export or the ETRM.

Cargo positions, tracks and ETAs come from the customer's licensed vessel-tracking
service (a Kpler, Spire or MarineTraffic export under the firm's own subscription) or
from the ETRM for the firm's own cargoes. The product stores what the feed reported and
never extrapolates a position.

Cargo columns (case-insensitive; extra columns ignored)::

    cargo_id, vessel_name, status, load_port
    [, vessel_imo, load_country, load_lat, load_lon, departed_at, destination_terminal,
       destination_country, destination_lat, destination_lon, eta, position_lat,
       position_lon, position_at, track, volume_m3, energy_gwh, book_id]

``status`` is one of loading, laden, discharging, delivered, ballast. ``track`` is
``lon lat iso-time`` triples separated by ``;``. A cargo with a ``book_id`` is the firm's
own; without one it is market information.

Slot columns::

    slot_id, terminal_name, window_start, window_end
    [, terminal_country, terminal_lat, terminal_lon, send_out_gwh_d, energy_gwh,
       cargo_id, book_id]
"""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime
from typing import Any

MAX_ROWS = 50_000
CARGO_STATUSES = frozenset({"loading", "laden", "discharging", "delivered", "ballast"})
MAX_TRACK_POINTS = 2_000


class LngImportError(ValueError):
    """Malformed export; the whole file is refused."""


def _rows(text: str, required: tuple[str, ...]) -> list[tuple[int, dict[str, str]]]:
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    if reader.fieldnames is None:
        raise LngImportError("the file has no header row")
    header = {name.strip().lower() for name in reader.fieldnames}
    missing = [name for name in required if name not in header]
    if missing:
        raise LngImportError(f"missing columns: {', '.join(missing)}")
    rows = []
    for index, raw in enumerate(reader, start=2):
        if index - 1 > MAX_ROWS:
            raise LngImportError(f"more than {MAX_ROWS} rows")
        rows.append((index, {k.strip().lower(): (v or "").strip() for k, v in raw.items() if k}))
    return rows


def _text(row: dict[str, str], name: str, limit: int) -> str | None:
    value = row.get(name, "")
    return value[:limit] if value else None


def _float(row: dict[str, str], name: str, line: int) -> float | None:
    value = row.get(name, "").replace(",", "")
    if not value:
        return None
    try:
        return float(value)
    except ValueError as exc:
        raise LngImportError(f"line {line}: {name} {value!r} is not a number") from exc


def _coordinate(row: dict[str, str], prefix: str, line: int) -> tuple[float | None, float | None]:
    lat, lon = _float(row, f"{prefix}_lat", line), _float(row, f"{prefix}_lon", line)
    if (lat is None) != (lon is None):
        raise LngImportError(f"line {line}: {prefix}_lat and {prefix}_lon must be given together")
    if lat is not None and not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise LngImportError(f"line {line}: {prefix} position is outside the globe")
    return lat, lon


def _instant(value: str, line: int, name: str) -> datetime | None:
    if not value:
        return None
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise LngImportError(f"line {line}: {name} {value!r} is not an ISO time") from exc
    if moment.tzinfo is None:
        raise LngImportError(f"line {line}: {name} must carry a UTC offset")
    return moment.astimezone(UTC)


def _track(value: str, line: int) -> list[list[Any]] | None:
    if not value:
        return None
    points: list[list[Any]] = []
    for part in value.split(";"):
        bits = part.split()
        if not bits:
            continue
        if len(bits) != 3:
            raise LngImportError(f"line {line}: track point {part!r} is not 'lon lat time'")
        try:
            lon, lat = float(bits[0]), float(bits[1])
        except ValueError as exc:
            raise LngImportError(f"line {line}: track point {part!r} is not numeric") from exc
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise LngImportError(f"line {line}: track point {part!r} is outside the globe")
        when = _instant(bits[2], line, "track time")
        points.append([lon, lat, when.isoformat() if when else None])
    if len(points) > MAX_TRACK_POINTS:
        points = points[-MAX_TRACK_POINTS:]
    return points or None


def parse_lng_cargoes(
    text: str, *, source_system: str, source_reference: str, now_utc: datetime
) -> list[dict[str, Any]]:
    """Rows for ``lng_cargoes``; a malformed row refuses the file."""

    out = []
    for line, row in _rows(text, ("cargo_id", "vessel_name", "status", "load_port")):
        status = row["status"].lower()
        if status not in CARGO_STATUSES:
            raise LngImportError(
                f"line {line}: status {row['status']!r} is not one of "
                f"{', '.join(sorted(CARGO_STATUSES))}"
            )
        if not row["cargo_id"] or not row["vessel_name"] or not row["load_port"]:
            raise LngImportError(f"line {line}: cargo_id, vessel_name and load_port are required")
        load_lat, load_lon = _coordinate(row, "load", line)
        dest_lat, dest_lon = _coordinate(row, "destination", line)
        pos_lat, pos_lon = _coordinate(row, "position", line)
        out.append(
            {
                "cargo_id": row["cargo_id"][:96],
                "vessel_name": row["vessel_name"][:128],
                "vessel_imo": _text(row, "vessel_imo", 16),
                "status": status,
                "load_port": row["load_port"][:128],
                "load_country": (_text(row, "load_country", 2) or "").upper() or None,
                "load_lat": load_lat,
                "load_lon": load_lon,
                "departed_at_utc": _instant(row.get("departed_at", ""), line, "departed_at"),
                "destination_terminal": _text(row, "destination_terminal", 128),
                "destination_country": (_text(row, "destination_country", 2) or "").upper() or None,
                "destination_lat": dest_lat,
                "destination_lon": dest_lon,
                "eta_utc": _instant(row.get("eta", ""), line, "eta"),
                "position_lat": pos_lat,
                "position_lon": pos_lon,
                "position_at_utc": _instant(row.get("position_at", ""), line, "position_at"),
                "track": _track(row.get("track", ""), line),
                "volume_m3": _float(row, "volume_m3", line),
                "energy_gwh": _float(row, "energy_gwh", line),
                "book_id": _text(row, "book_id", 64),
                "source_system": source_system[:32],
                "source_reference": source_reference[:160],
                "updated_at_utc": now_utc,
            }
        )
    return out


def parse_regas_slots(
    text: str, *, source_system: str, source_reference: str, now_utc: datetime
) -> list[dict[str, Any]]:
    """Rows for ``regas_slots``; a malformed row refuses the file."""

    out = []
    for line, row in _rows(text, ("slot_id", "terminal_name", "window_start", "window_end")):
        start = _instant(row["window_start"], line, "window_start")
        end = _instant(row["window_end"], line, "window_end")
        if start is None or end is None or end <= start:
            raise LngImportError(f"line {line}: window_end must follow window_start")
        if not row["slot_id"] or not row["terminal_name"]:
            raise LngImportError(f"line {line}: slot_id and terminal_name are required")
        lat, lon = _coordinate(row, "terminal", line)
        out.append(
            {
                "slot_id": row["slot_id"][:96],
                "terminal_name": row["terminal_name"][:128],
                "terminal_country": (_text(row, "terminal_country", 2) or "").upper() or None,
                "terminal_lat": lat,
                "terminal_lon": lon,
                "window_start_utc": start,
                "window_end_utc": end,
                "send_out_gwh_d": _float(row, "send_out_gwh_d", line),
                "energy_gwh": _float(row, "energy_gwh", line),
                "cargo_id": _text(row, "cargo_id", 96),
                "book_id": _text(row, "book_id", 64),
                "source_system": source_system[:32],
                "source_reference": source_reference[:160],
                "updated_at_utc": now_utc,
            }
        )
    return out
