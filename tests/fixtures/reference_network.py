"""Source-shaped reference-network fixtures for API tests.

These rows mimic normalized ENTSOG metadata. They are deliberately kept under
tests/fixtures so production code cannot import seeded topology as runtime truth.
"""

from __future__ import annotations

from typing import Any


def source_metadata(point_key: str, *, source_reference: str = "entsog-connectionpoints") -> dict:
    return {
        "source_system": "ENTSOG",
        "source_reference": source_reference,
        "point_key": point_key,
        "coordinate_quality": "display_approximation",
        "data_status": "live_source_metadata",
    }


def source_lineage(
    source_record_id: str,
    *,
    source_dataset: str = "connectionpoints",
    source_reference: str = "entsog-connectionpoints",
    data_quality: str = "display_approximation",
) -> dict[str, Any]:
    return {
        "source_system": "ENTSOG",
        "source_dataset": source_dataset,
        "source_reference": source_reference,
        "source_record_id": source_record_id,
        "data_quality": data_quality,
    }


def reference_nodes() -> list[dict[str, Any]]:
    return [
        {
            "id": "entsog-vtp-nl-ttf",
            "name": "TTF",
            "node_type": "hub",
            "country": "NL",
            "lat": 52.20,
            "lon": 5.30,
            "capacity_boe_d": None,
            **source_lineage("VTP-NL-TTF"),
            "metadata_json": source_metadata("VTP-NL-TTF"),
        },
        {
            "id": "entsog-vtp-gb-nbp",
            "name": "NBP",
            "node_type": "hub",
            "country": "GB",
            "lat": 52.90,
            "lon": -1.50,
            "capacity_boe_d": None,
            **source_lineage("VTP-GB-NBP"),
            "metadata_json": source_metadata("VTP-GB-NBP"),
        },
        {
            "id": "entsog-lng-nl-gate",
            "name": "Gate LNG",
            "node_type": "lng",
            "country": "NL",
            "lat": 51.96,
            "lon": 4.08,
            "capacity_boe_d": None,
            **source_lineage("LNG-NL-GATE"),
            "metadata_json": source_metadata("LNG-NL-GATE"),
        },
        {
            "id": "entsog-itp-gb-bbl",
            "name": "Bacton BBL",
            "node_type": "interconnection",
            "country": "GB",
            "lat": 52.85,
            "lon": 1.47,
            "capacity_boe_d": None,
            **source_lineage("ITP-GB-BBL"),
            "metadata_json": source_metadata("ITP-GB-BBL"),
        },
    ]


def reference_edges() -> list[dict[str, Any]]:
    return []


def reference_tso_access_points() -> list[dict[str, Any]]:
    return [
        {
            "access_id": "entsog-opd-bbl-ttf-entry",
            "point_id": "entsog-vtp-nl-ttf",
            "point_key": "VTP-NL-TTF",
            "point_name": "TTF",
            "country": "NL",
            "operator_key": "BBL",
            "operator_name": "BBL Company",
            "tso_eic_code": "21X-BBL-TTF----A",
            "direction": "entry",
            "adjacent_country": "GB",
            "adjacent_operator_key": "NGG",
            "connected_operators": "BBL,NGG",
            "booking_platform": "PRISMA",
            "booking_platform_url": "https://platform.example.test",
            "annual_contracts_available": True,
            "monthly_contracts_available": True,
            "daily_contracts_available": True,
            "day_ahead_contracts_available": True,
            "is_cam_relevant": True,
            "is_cmp_relevant": True,
            "last_update_utc": None,
            **source_lineage(
                "bbl-ttf-entry",
                source_dataset="operatorpointdirections",
                source_reference="entsog-operatorpointdirections",
                data_quality="source_metadata",
            ),
            "metadata_json": {
                **source_metadata(
                    "VTP-NL-TTF",
                    source_reference="entsog-operatorpointdirections",
                ),
                "operator_key": "BBL",
                "operator_label": "BBL Company",
                "direction_key": "entry",
                "booking_platform": "PRISMA",
            },
        }
    ]


def reference_facilities() -> list[dict[str, Any]]:
    return [
        {
            "id": "fac-entsog-lng-nl-gate",
            "name": "Gate LNG",
            "facility_type": "lng_terminal",
            "country": "NL",
            "lat": 51.96,
            "lon": 4.08,
            "capacity_boe_d": None,
            **source_lineage("LNG-NL-GATE"),
            "metadata_json": source_metadata("LNG-NL-GATE"),
        },
        {
            "id": "fac-entsog-itp-gb-bbl",
            "name": "Bacton BBL",
            "facility_type": "border_point",
            "country": "GB",
            "lat": 52.85,
            "lon": 1.47,
            "capacity_boe_d": None,
            **source_lineage("ITP-GB-BBL"),
            "metadata_json": source_metadata("ITP-GB-BBL"),
        },
    ]


def reference_market_hubs() -> list[dict[str, Any]]:
    return [
        {
            "id": "hub-vtp-nl-ttf",
            "name": "TTF",
            "hub_code": "TTF",
            "country": "NL",
            "description": "ENTSOG trading point TTF",
            **source_lineage("VTP-NL-TTF"),
            "metadata_json": source_metadata("VTP-NL-TTF"),
        },
        {
            "id": "hub-vtp-gb-nbp",
            "name": "NBP",
            "hub_code": "NBP",
            "country": "GB",
            "description": "ENTSOG trading point NBP",
            **source_lineage("VTP-GB-NBP"),
            "metadata_json": source_metadata("VTP-GB-NBP"),
        },
    ]
