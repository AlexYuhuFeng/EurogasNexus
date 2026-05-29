"""Seed V1 synthetic runtime data into the configured runtime DB.

This script writes only synthetic fixtures. It never fetches vendor data and
never prints the full database URL.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.exc import SQLAlchemyError

from eurogas_nexus.db.models import (
    AuditEventRecord,
    EntitlementDecisionRecord,
    FlowObservationRecord,
    LngObservationRecord,
    MarketObservationRecord,
    ProviderCredentialRecord,
    StorageObservationRecord,
)
from eurogas_nexus.db.models.reference_network import (
    NodeFacilityMapping,
    ReferenceEdge,
    ReferenceFacility,
    ReferenceMarketHub,
    ReferenceNode,
    TopologyMarketMapping,
)
from eurogas_nexus.db.session import (
    create_session_factory,
    get_engine,
    redact_database_url,
    resolve_database_url,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replace", action="store_true", help="Replace existing synthetic rows.")
    parser.add_argument("--json", action="store_true", help="Print a JSON report.")
    args = parser.parse_args()

    database_url = resolve_database_url()
    if not database_url:
        return _emit(
            {
                "ok": False,
                "error": "Database URL is missing.",
                "redacted_database_url": None,
            },
            as_json=args.json,
        )

    engine = None
    try:
        engine = get_engine(database_url)
        session_factory = create_session_factory(engine)
        with session_factory() as session:
            if args.replace:
                for model in (
                    EntitlementDecisionRecord,
                    ProviderCredentialRecord,
                    AuditEventRecord,
                    LngObservationRecord,
                    StorageObservationRecord,
                    FlowObservationRecord,
                    MarketObservationRecord,
                    TopologyMarketMapping,
                    NodeFacilityMapping,
                    ReferenceEdge,
                    ReferenceMarketHub,
                    ReferenceFacility,
                    ReferenceNode,
                ):
                    session.query(model).delete()
                session.flush()

            now = datetime.now(UTC)
            for payload in _nodes(now):
                session.merge(ReferenceNode(**payload))
            session.flush()
            for payload in _facilities(now):
                session.merge(ReferenceFacility(**payload))
            session.flush()
            for payload in _market_hubs(now):
                session.merge(ReferenceMarketHub(**payload))
            session.flush()
            for payload in _edges(now):
                session.merge(ReferenceEdge(**payload))
            session.flush()
            for payload in _node_facility_mappings(now):
                session.merge(NodeFacilityMapping(**payload))
            session.flush()
            for payload in _topology_market_mappings(now):
                session.merge(TopologyMarketMapping(**payload))
            session.flush()
            for payload in _market_observations():
                session.merge(MarketObservationRecord(**payload))
            session.flush()
            for payload in _flow_observations():
                session.merge(FlowObservationRecord(**payload))
            session.flush()
            for payload in _storage_observations():
                session.merge(StorageObservationRecord(**payload))
            session.flush()
            for payload in _lng_observations():
                session.merge(LngObservationRecord(**payload))
            session.flush()
            for payload in _audit_events(now):
                session.merge(AuditEventRecord(**payload))
            session.flush()
            for payload in _entitlement_decisions(now):
                session.merge(EntitlementDecisionRecord(**payload))
            session.flush()

            session.commit()

        return _emit(
            {
                "ok": True,
                "redacted_database_url": redact_database_url(database_url),
                "replace": args.replace,
                "seeded": {
                    "reference_nodes": len(_nodes(now)),
                    "reference_edges": len(_edges(now)),
                    "reference_facilities": len(_facilities(now)),
                    "reference_market_hubs": len(_market_hubs(now)),
                    "node_facility_mappings": len(_node_facility_mappings(now)),
                    "topology_market_mappings": len(_topology_market_mappings(now)),
                    "market_observations": len(_market_observations()),
                    "flow_observations": len(_flow_observations()),
                    "storage_observations": len(_storage_observations()),
                    "lng_observations": len(_lng_observations()),
                    "audit_events": len(_audit_events(now)),
                    "entitlement_decisions": len(_entitlement_decisions(now)),
                },
                "source": "synthetic-fixture",
            },
            as_json=args.json,
        )
    except SQLAlchemyError as exc:
        return _emit(
            {
                "ok": False,
                "redacted_database_url": redact_database_url(database_url),
                "error": exc.__class__.__name__,
            },
            as_json=args.json,
        )
    finally:
        if engine is not None:
            engine.dispose()


def _emit(payload: dict[str, Any], *, as_json: bool) -> int:
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    elif payload["ok"]:
        seeded = payload.get("seeded", {})
        print(
            "synthetic reference data seeded: "
            + ", ".join(f"{name}={count}" for name, count in seeded.items())
        )
    else:
        print(f"synthetic reference data seed failed: {payload.get('error')}")
    return 0 if payload["ok"] else 1


def _nodes(now: datetime) -> list[dict[str, Any]]:
    return [
        _node("node-ttf", "TTF Hub", "hub", "NL", 52.37, 4.90, None, now),
        _node("node-nbp", "NBP Hub", "hub", "GB", 52.63, -1.14, None, now),
        _node("node-peg", "PEG Nord", "hub", "FR", 49.26, 2.47, None, now),
        _node("node-ncg", "NCG Hub", "hub", "DE", 51.34, 6.56, None, now),
        _node("node-psv", "PSV Hub", "hub", "AT", 48.21, 16.37, None, now),
        _node("node-zeebrugge", "Zeebrugge", "interconnection", "BE", 51.33, 3.20, 1.2e6, now),
        _node("node-emden", "Emden Entry", "entry_point", "DE", 53.37, 7.20, 2.5e6, now),
        _node("node-bacton", "Bacton Terminal", "entry_point", "GB", 52.85, 1.47, 1.8e6, now),
        _node("node-dunkerque", "Dunkerque LNG", "lng", "FR", 51.04, 2.38, 1.5e6, now),
        _node("node-gate", "Gate LNG", "lng", "NL", 51.90, 4.30, 1.3e6, now),
        _node("node-mallnow", "Mallnow", "interconnection", "DE", 52.54, 14.28, 0.8e6, now),
        _node("node-tarvisio", "Tarvisio", "interconnection", "IT", 46.51, 13.58, 1.0e6, now),
    ]


def _node(
    id_: str,
    name: str,
    node_type: str,
    country: str,
    lat: float,
    lon: float,
    capacity_boe_d: float | None,
    now: datetime,
) -> dict[str, Any]:
    return {
        "id": id_,
        "name": name,
        "node_type": node_type,
        "country": country,
        "lat": lat,
        "lon": lon,
        "capacity_boe_d": capacity_boe_d,
        "metadata_json": {"fixture": True},
        "created_at_utc": now,
    }


def _edges(now: datetime) -> list[dict[str, Any]]:
    return [
        _edge("edge-1", "node-ttf", "node-ncg", 200, now),
        _edge("edge-2", "node-ncg", "node-psv", 750, now),
        _edge("edge-3", "node-zeebrugge", "node-ttf", 180, now),
        _edge("edge-4", "node-nbp", "node-zeebrugge", 220, now),
        _edge("edge-5", "node-peg", "node-ncg", 500, now),
        _edge("edge-6", "node-emden", "node-ncg", 250, now),
        _edge("edge-7", "node-bacton", "node-zeebrugge", 200, now),
        _edge("edge-8", "node-dunkerque", "node-peg", 260, now),
        _edge("edge-9", "node-gate", "node-ttf", 100, now),
        _edge("edge-10", "node-mallnow", "node-ncg", 150, now),
    ]


def _edge(
    id_: str,
    from_node_id: str,
    to_node_id: str,
    length_km: float,
    now: datetime,
) -> dict[str, Any]:
    return {
        "id": id_,
        "from_node_id": from_node_id,
        "to_node_id": to_node_id,
        "edge_type": "pipeline",
        "length_km": length_km,
        "metadata_json": {"fixture": True},
        "created_at_utc": now,
    }


def _facilities(now: datetime) -> list[dict[str, Any]]:
    return [
        _facility("fac-zee-lng", "Zeebrugge LNG", "lng_terminal", "BE", 51.33, 3.20, 1.0e6, now),
        _facility("fac-gate-lng", "Gate LNG", "lng_terminal", "NL", 51.90, 4.30, 1.3e6, now),
        _facility("fac-dunk-lng", "Dunkerque LNG", "lng_terminal", "FR", 51.04, 2.38, 1.5e6, now),
        _facility("fac-bacton", "Bacton Terminal", "border_point", "GB", 52.85, 1.47, 1.8e6, now),
        _facility("fac-emden", "Emden Entry", "border_point", "DE", 53.37, 7.20, 2.5e6, now),
        _facility("fac-mallnow", "Mallnow Comp.", "compressor", "DE", 52.54, 14.28, 0.8e6, now),
        _facility("fac-haidach", "Haidach", "storage", "AT", 47.95, 13.22, 0.5e6, now),
    ]


def _facility(
    id_: str,
    name: str,
    facility_type: str,
    country: str,
    lat: float,
    lon: float,
    capacity_boe_d: float | None,
    now: datetime,
) -> dict[str, Any]:
    return {
        "id": id_,
        "name": name,
        "facility_type": facility_type,
        "country": country,
        "lat": lat,
        "lon": lon,
        "capacity_boe_d": capacity_boe_d,
        "metadata_json": {"fixture": True},
        "created_at_utc": now,
    }


def _market_hubs(now: datetime) -> list[dict[str, Any]]:
    return [
        _hub("hub-ttf", "TTF", "TTF", "NL", "Primary European gas trading hub", now),
        _hub("hub-nbp", "NBP", "NBP", "GB", "UK gas trading hub", now),
        _hub("hub-peg", "PEG", "PEG", "FR", "French gas trading hub", now),
        _hub("hub-ncg", "NCG", "NCG", "DE", "German gas trading hub", now),
        _hub("hub-psv", "PSV", "PSV", "AT", "Austrian gas trading hub", now),
        _hub("hub-eex", "EEX", "EEX", "DE", "Power and gas exchange", now),
        _hub("hub-ice", "ICE OCM", "ICE-OCM", "GB", "ICE Endex OCM gas trading", now),
    ]


def _hub(
    id_: str,
    name: str,
    hub_code: str,
    country: str,
    description: str,
    now: datetime,
) -> dict[str, Any]:
    return {
        "id": id_,
        "name": name,
        "hub_code": hub_code,
        "country": country,
        "description": description,
        "metadata_json": {"fixture": True},
        "created_at_utc": now,
    }


def _node_facility_mappings(now: datetime) -> list[dict[str, Any]]:
    return [
        _mapping("nfm-gate", "node-gate", "fac-gate-lng", 0.95, "confirmed", now),
        _mapping("nfm-dunk", "node-dunkerque", "fac-dunk-lng", 0.95, "confirmed", now),
        _mapping("nfm-bacton", "node-bacton", "fac-bacton", 0.9, "confirmed", now),
        _mapping("nfm-emden", "node-emden", "fac-emden", 0.9, "confirmed", now),
        _mapping("nfm-mallnow", "node-mallnow", "fac-mallnow", 0.85, "confirmed", now),
    ]


def _topology_market_mappings(now: datetime) -> list[dict[str, Any]]:
    return [
        _market_mapping("tmm-ttf", "node-ttf", "hub-ttf", 1.0, "confirmed", now),
        _market_mapping("tmm-nbp", "node-nbp", "hub-nbp", 1.0, "confirmed", now),
        _market_mapping("tmm-peg", "node-peg", "hub-peg", 1.0, "confirmed", now),
        _market_mapping("tmm-ncg", "node-ncg", "hub-ncg", 1.0, "confirmed", now),
        _market_mapping("tmm-psv", "node-psv", "hub-psv", 1.0, "confirmed", now),
    ]


def _mapping(
    id_: str,
    node_id: str,
    facility_id: str,
    confidence: float,
    eligibility: str,
    now: datetime,
) -> dict[str, Any]:
    return {
        "id": id_,
        "node_id": node_id,
        "facility_id": facility_id,
        "confidence": confidence,
        "eligibility": eligibility,
        "metadata_json": {"fixture": True},
        "created_at_utc": now,
    }


def _market_mapping(
    id_: str,
    node_id: str,
    market_hub_id: str,
    confidence: float,
    eligibility: str,
    now: datetime,
) -> dict[str, Any]:
    return {
        "id": id_,
        "node_id": node_id,
        "market_hub_id": market_hub_id,
        "confidence": confidence,
        "eligibility": eligibility,
        "metadata_json": {"fixture": True},
        "created_at_utc": now,
    }


def _market_observations() -> list[dict[str, Any]]:
    return [
        _market_observation(
            "mkt-001",
            "TTF",
            "month-ahead",
            42.50,
            "EUR/MWh",
            "EUR",
            "2026-06-01T00:00:00+00:00",
            "2026-07-01T00:00:00+00:00",
        ),
        _market_observation(
            "mkt-002",
            "NBP",
            "day-ahead",
            105.20,
            "p/th",
            "GBP",
            "2026-05-30T06:00:00+00:00",
            "2026-05-31T06:00:00+00:00",
        ),
        _market_observation(
            "mkt-003",
            "PEG",
            "month-ahead",
            41.00,
            "EUR/MWh",
            "EUR",
            "2026-06-01T00:00:00+00:00",
            "2026-07-01T00:00:00+00:00",
        ),
    ]


def _market_observation(
    observation_id: str,
    market_venue: str,
    product: str,
    price: float,
    unit: str,
    currency: str,
    period_start_utc: str,
    period_end_utc: str,
) -> dict[str, Any]:
    return {
        "observation_id": observation_id,
        "market_venue": market_venue,
        "product": product,
        "price": price,
        "unit": unit,
        "currency": currency,
        "period_start_utc": datetime.fromisoformat(period_start_utc),
        "period_end_utc": datetime.fromisoformat(period_end_utc),
        "observed_at_utc": datetime(2026, 5, 29, 12, 0, tzinfo=UTC),
        "source_system": "synthetic-fixture",
        "source_reference": "seed-v1-synthetic-runtime-data",
        "freshness": "fresh",
        "quality_score": 1.0,
        "research_only": True,
    }


def _flow_observations() -> list[dict[str, Any]]:
    return [
        _flow_observation("flw-001", "node-zeebrugge", "Zeebrugge", "entry", 85.0),
        _flow_observation("flw-002", "node-emden", "Emden", "entry", 120.0),
        _flow_observation("flw-003", "node-mallnow", "Mallnow", "entry", 45.0),
    ]


def _flow_observation(
    observation_id: str,
    point_id: str,
    point_name: str,
    direction: str,
    flow_mcm_d: float,
) -> dict[str, Any]:
    return {
        "observation_id": observation_id,
        "point_id": point_id,
        "point_name": point_name,
        "direction": direction,
        "flow_mcm_d": flow_mcm_d,
        "period_start_utc": datetime(2026, 5, 29, 6, 0, tzinfo=UTC),
        "period_end_utc": datetime(2026, 5, 30, 6, 0, tzinfo=UTC),
        "observed_at_utc": datetime(2026, 5, 29, 12, 0, tzinfo=UTC),
        "source_system": "synthetic-fixture",
        "source_reference": "seed-v1-synthetic-runtime-data",
        "freshness": "fresh",
        "research_only": True,
    }


def _storage_observations() -> list[dict[str, Any]]:
    return [
        {
            "observation_id": "sto-001",
            "source_dataset": "AGSI",
            "facility_id": "stor-haidach",
            "facility_name": "Haidach",
            "country": "AT",
            "inventory_twh": 17.50,
            "working_capacity_twh": 28.00,
            "fill_pct": 62.5,
            "injection_twh_d": 0.20,
            "withdrawal_twh_d": 0.30,
            "period_start_utc": datetime(2026, 5, 29, tzinfo=UTC),
            "period_end_utc": datetime(2026, 5, 30, tzinfo=UTC),
            "observed_at_utc": datetime(2026, 5, 29, 12, 0, tzinfo=UTC),
            "source_system": "synthetic-fixture",
            "source_reference": "seed-v1-synthetic-runtime-data",
            "freshness": "fresh",
            "research_only": True,
        },
        {
            "observation_id": "sto-002",
            "source_dataset": "AGSI",
            "facility_id": "stor-bergermeer",
            "facility_name": "Bergermeer",
            "country": "NL",
            "inventory_twh": 22.08,
            "working_capacity_twh": 46.00,
            "fill_pct": 48.0,
            "injection_twh_d": 0.35,
            "withdrawal_twh_d": 0.55,
            "period_start_utc": datetime(2026, 5, 29, tzinfo=UTC),
            "period_end_utc": datetime(2026, 5, 30, tzinfo=UTC),
            "observed_at_utc": datetime(2026, 5, 29, 12, 0, tzinfo=UTC),
            "source_system": "synthetic-fixture",
            "source_reference": "seed-v1-synthetic-runtime-data",
            "freshness": "fresh",
            "research_only": True,
        },
    ]


def _lng_observations() -> list[dict[str, Any]]:
    return [
        {
            "observation_id": "lng-001",
            "source_dataset": "ALSI",
            "terminal_id": "lng-gate",
            "terminal_name": "Gate LNG",
            "country": "NL",
            "inventory_twh": 5.40,
            "send_out_twh_d": 0.28,
            "dtmi_pct": 52.0,
            "period_start_utc": datetime(2026, 5, 29, tzinfo=UTC),
            "period_end_utc": datetime(2026, 5, 30, tzinfo=UTC),
            "observed_at_utc": datetime(2026, 5, 29, 12, 0, tzinfo=UTC),
            "source_system": "synthetic-fixture",
            "source_reference": "seed-v1-synthetic-runtime-data",
            "freshness": "fresh",
            "research_only": True,
        },
        {
            "observation_id": "lng-002",
            "source_dataset": "ALSI",
            "terminal_id": "lng-zeebrugge",
            "terminal_name": "Zeebrugge LNG",
            "country": "BE",
            "inventory_twh": 3.80,
            "send_out_twh_d": 0.14,
            "dtmi_pct": 44.0,
            "period_start_utc": datetime(2026, 5, 29, tzinfo=UTC),
            "period_end_utc": datetime(2026, 5, 30, tzinfo=UTC),
            "observed_at_utc": datetime(2026, 5, 29, 12, 0, tzinfo=UTC),
            "source_system": "synthetic-fixture",
            "source_reference": "seed-v1-synthetic-runtime-data",
            "freshness": "fresh",
            "research_only": True,
        },
    ]


def _audit_events(now: datetime) -> list[dict[str, Any]]:
    return [
        {
            "event_id": "audit-seed-001",
            "event_type": "runtime.seed",
            "severity": "info",
            "principal": "local-operator",
            "action": "seed-synthetic-runtime-data",
            "resource": "runtime-store",
            "outcome": "succeeded",
            "detail": "Synthetic V1 runtime fixtures seeded for local validation.",
            "event_ts_utc": now,
            "source_system": "synthetic-fixture",
            "human_review_required": True,
        }
    ]


def _entitlement_decisions(now: datetime) -> list[dict[str, Any]]:
    return [
        {
            "decision_id": "ent-seed-001",
            "source_system": "synthetic-fixture",
            "source_dataset": "v1-local-fixtures",
            "granted": True,
            "scope": "internal-research",
            "reason": "Synthetic local fixtures contain no real vendor or operator data.",
            "evaluated_at_utc": now,
            "human_review_required": True,
        }
    ]


if __name__ == "__main__":
    raise SystemExit(main())
