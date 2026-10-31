"""Infrastructure locations (platforms, fields, terminals, storage) from open GeoJSON.

The map's infrastructure comes from published, commercially reusable datasets, each
recorded with its licence and attribution:

- Norwegian Offshore Directorate (Sodir) FactMaps: fields, facilities, pipelines (NLOD 2.0)
- UK North Sea Transition Authority open data: offshore installations, pipelines (OGL v3)
- Global Energy Monitor Global Gas Infrastructure / LNG terminal trackers (CC BY 4.0)
- OpenStreetMap ``man_made=petroleum_well``/``offshore_platform`` extracts (ODbL 1.0)
- ENTSOG connection points, imported separately (Transparency Platform terms)

A licence outside :data:`COMMERCIAL_LICENCES` is refused unless the operator declares it
the customer's own licence, so data whose terms exclude commercial use never enters.
Only ``Point`` features are loaded; the product does not move or snap a location.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

COMMERCIAL_LICENCES = frozenset(
    {"CC0-1.0", "CC-BY-4.0", "ODbL-1.0", "NLOD-2.0", "OGL-UK-3.0", "PUBLIC-DOMAIN", "CUSTOMER"}
)
FACILITY_TYPES = frozenset(
    {
        "production_platform",
        "field",
        "lng_terminal",
        "liquefaction",
        "storage",
        "compressor",
        "processing_plant",
        "power_plant",
        "border_point",
    }
)
MAX_FEATURES = 50_000
_NAME_KEYS = ("name", "Name", "NAME", "facility_name", "fclName", "fldName", "unit_name")
_COUNTRY_KEYS = ("country", "iso2", "country_code", "ISO2", "Country")


class InfrastructureImportError(ValueError):
    """The file or its licence is not acceptable; nothing is loaded."""


def _first(props: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = props.get(key)
        if value not in (None, ""):
            return str(value).strip()
    return ""


def parse_infrastructure(
    text: str,
    *,
    dataset: str,
    licence: str,
    attribution: str,
    facility_type: str | None = None,
    default_country: str | None = None,
) -> list[dict[str, Any]]:
    """Rows for ``reference_facilities`` from a GeoJSON FeatureCollection."""

    normalised = {item.upper(): item for item in COMMERCIAL_LICENCES}
    licence_id = licence.strip().upper()
    if licence_id not in normalised:
        raise InfrastructureImportError(
            f"licence {licence!r} is not one cleared for commercial use "
            f"({', '.join(sorted(COMMERCIAL_LICENCES))})"
        )
    licence_id = normalised[licence_id]
    if not attribution.strip():
        raise InfrastructureImportError("an attribution is required")
    if facility_type and facility_type not in FACILITY_TYPES:
        raise InfrastructureImportError(f"facility type {facility_type!r} is not known")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise InfrastructureImportError(f"not GeoJSON: {exc.msg}") from exc
    features = payload.get("features") if isinstance(payload, dict) else None
    if not isinstance(features, list):
        raise InfrastructureImportError("expected a GeoJSON FeatureCollection")
    if len(features) > MAX_FEATURES:
        raise InfrastructureImportError(f"more than {MAX_FEATURES} features")
    rows: list[dict[str, Any]] = []
    for index, feature in enumerate(features):
        geometry = (feature or {}).get("geometry") or {}
        if geometry.get("type") != "Point":
            continue
        coordinates = geometry.get("coordinates") or []
        try:
            lon, lat = float(coordinates[0]), float(coordinates[1])
        except (IndexError, TypeError, ValueError):
            continue
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            continue
        props = feature.get("properties") or {}
        name = _first(props, _NAME_KEYS)
        kind = facility_type or str(props.get("facility_type") or "").strip()
        country = (_first(props, _COUNTRY_KEYS) or default_country or "").upper()[:2]
        if not name or kind not in FACILITY_TYPES or len(country) != 2:
            continue
        record_id = str(feature.get("id") or props.get("id") or f"{name}|{lon:.5f}|{lat:.5f}")
        digest = hashlib.sha256(f"{dataset}|{record_id}".encode()).hexdigest()[:20]
        rows.append(
            {
                "id": f"infra-{digest}",
                "name": name[:128],
                "facility_type": kind,
                "country": country,
                "lat": lat,
                "lon": lon,
                "capacity_boe_d": None,
                "source_system": dataset[:64],
                "source_dataset": dataset[:128],
                "source_reference": attribution[:256],
                "source_record_id": record_id[:128],
                "data_quality": "published_location",
                "metadata_json": {
                    "licence": licence_id,
                    "attribution": attribution,
                    "operator": _first(props, ("operator", "Operator", "fclCurrentOperatorName")),
                    "status": _first(props, ("status", "Status", "fclPhase", "fldCurrentActivity")),
                    "feature_index": index,
                },
            }
        )
    return rows
