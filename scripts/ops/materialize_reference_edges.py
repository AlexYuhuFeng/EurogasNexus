"""Materialize map-ready reference edges from DB route candidates.

This operator-invoked script reads PostgreSQL route candidates and reference
nodes, then writes corridor edges into `reference_edges`. It does not call
external APIs, run migrations, or create client-side fallback geometry.
"""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from typing import Any

from eurogas_nexus.db.models import ReferenceEdge, ReferenceNode, RouteCandidateRecord
from eurogas_nexus.db.session import get_session_factory, resolve_database_url


def materialize_route_candidate_edges(
    *,
    database_url: str | None = None,
    replace_existing: bool = True,
) -> dict[str, Any]:
    """Create map-visible DB edges from active route candidates."""

    resolved_url = database_url or resolve_database_url()
    if not resolved_url:
        return {
            "database_url_present": False,
            "created_or_updated": 0,
            "skipped": 0,
            "warnings": ["RUNTIME_DB_NOT_CONFIGURED"],
        }

    session_factory = get_session_factory(database_url=resolved_url)
    now = datetime.now(UTC)
    with session_factory() as session:
        if replace_existing:
            session.query(ReferenceEdge).filter(
                ReferenceEdge.id.like("route-edge-%")
            ).delete(synchronize_session=False)

        nodes = session.query(ReferenceNode).all()
        node_lookup = _build_node_lookup(nodes)
        routes = (
            session.query(RouteCandidateRecord)
            .filter(RouteCandidateRecord.active.is_(True))
            .order_by(RouteCandidateRecord.route_id)
            .all()
        )

        created = 0
        skipped = 0
        warnings: list[str] = []
        for route in routes:
            start_key = _normalise_key(route.start_point_name)
            target_key = _normalise_key(route.target_point_name)
            if start_key == target_key:
                skipped += 1
                continue

            from_node = node_lookup.get(start_key)
            to_node = node_lookup.get(target_key)
            if from_node is None or to_node is None:
                skipped += 1
                warnings.append(f"NODE_MATCH_MISSING:{route.route_id}")
                continue

            session.merge(
                ReferenceEdge(
                    id=_edge_id(route.route_id),
                    from_node_id=from_node.id,
                    to_node_id=to_node.id,
                    edge_type="corridor",
                    length_km=None,
                    source_system="route_candidate",
                    source_dataset="route_candidates",
                    source_reference=f"route_candidate:{route.route_id}",
                    source_record_id=route.route_id,
                    data_quality="source_derived_candidate",
                    metadata_json={
                        "materialization": "route_candidate_edge",
                        "route_id": route.route_id,
                        "route_name": route.route_name,
                        "business_model": route.business_model,
                        "route_legs": route.route_legs,
                        "required_tso_access": route.required_tso_access,
                        "source_systems": route.source_systems,
                    },
                    created_at_utc=now,
                )
            )
            created += 1

        session.commit()

    return {
        "database_url_present": True,
        "created_or_updated": created,
        "skipped": skipped,
        "warnings": warnings,
    }


def _build_node_lookup(nodes: list[ReferenceNode]) -> dict[str, ReferenceNode]:
    lookup: dict[str, ReferenceNode] = {}
    for node in nodes:
        for value in [
            node.id,
            node.name,
            node.source_record_id,
            (node.metadata_json or {}).get("market_code"),
            (node.metadata_json or {}).get("point_key"),
            *_name_aliases(node.name),
        ]:
            key = _normalise_key(value)
            if key and key not in lookup:
                lookup[key] = node
    return lookup


def _edge_id(route_id: str) -> str:
    slug = re.sub(r"[^a-z0-9-]+", "-", route_id.lower()).strip("-")
    prefix = "route-edge-"
    if len(prefix + slug) <= 64:
        return prefix + slug
    digest = hashlib.sha1(route_id.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}{slug[: 63 - len(prefix) - len(digest)]}-{digest}"


def _normalise_key(value: object) -> str:
    if value is None:
        return ""
    return re.sub(r"[^a-z0-9]+", "", str(value).casefold())


def _name_aliases(name: str) -> list[str]:
    aliases = [name]
    for separator in ["(", "/", "-", "|"]:
        if separator in name:
            aliases.append(name.split(separator, 1)[0])
    first_token = name.split(maxsplit=1)[0]
    if 2 <= len(first_token) <= 8:
        aliases.append(first_token)
    return aliases


def main() -> int:
    summary = materialize_route_candidate_edges()
    if not summary["database_url_present"]:
        print("Runtime DB URL missing. Set RUNTIME_STORE_DATABASE_URL or DATABASE_URL.")
        return 2
    print(
        "Materialized route candidate edges: "
        f"{summary['created_or_updated']} created_or_updated, "
        f"{summary['skipped']} skipped."
    )
    if summary["warnings"]:
        print("Warnings: " + ", ".join(summary["warnings"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
