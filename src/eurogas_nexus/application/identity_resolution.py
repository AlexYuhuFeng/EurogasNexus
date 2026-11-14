"""One identity resolver, backed by ``source_entity_mappings`` and the ontology (ONT-02).

Every place that turns a provider's or a person's identifier into a canonical entity goes
through here: provider keys at ingest (ENTSOG points and operators, GIE countries, National
Gas publications, power zones) and hubs named in free text at contract save and in prices
(``resolve_hub`` with the deployment's ``delivery_point`` mappings). An identifier that does
not resolve is quarantined: counted and listed with its reason on the Sources page
(``/api/sources``, ``unresolved_identifiers`` per source), never guessed.

ENTSOG point and operator keys are written to ``source_entity_mappings`` by the ENTSOG
reference ingest (:func:`record_identities`, called from ``ingest_public_sources.py``), the
provider's own complete list of what exists; the short published lists of the other
built-in sources are code (``ontology.source_identity.BUILTIN_SOURCE_IDENTITIES``).
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from eurogas_nexus.domain.ontology.identity import HubResolution, resolve_hub
from eurogas_nexus.domain.ontology.source_identity import (
    IdentifierResolution,
    MappingKey,
    SourceIdentity,
    canonical_id,
    resolve_identifier,
)

logger = logging.getLogger(__name__)

#: Mappings written by a provider's own reference read are valid from this instant, so an
#: as-of resolution of any stored history finds them.
REFERENCE_VALID_FROM = datetime(2000, 1, 1, tzinfo=UTC)


@dataclass
class IdentityResolver:
    """The deployment's mappings, loaded once; resolution is then pure."""

    mappings: dict[MappingKey, set[str]] = field(default_factory=dict)
    #: Upper-cased delivery-point name -> hub code (``delivery_point`` mappings).
    points: dict[str, str] = field(default_factory=dict)

    def resolve(
        self, source_id: str, entity_type: str, identifier: str | None
    ) -> IdentifierResolution:
        return resolve_identifier(source_id, entity_type, identifier, mappings=self.mappings)

    def hub(self, text: str | None) -> HubResolution:
        """The hub a delivery point, product or hub field names; no default hub."""

        return resolve_hub(text, points=self.points)


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def load_resolver(session, *, at_utc: datetime | None = None) -> IdentityResolver:
    """The resolver for this store; an empty one when the table is not there."""

    from sqlalchemy import inspect, select

    from eurogas_nexus.db.models import SourceEntityMappingRecord

    try:
        if not inspect(session.connection()).has_table("source_entity_mappings"):
            return IdentityResolver()
        rows = session.execute(
            select(
                SourceEntityMappingRecord.source_id,
                SourceEntityMappingRecord.source_entity_type,
                SourceEntityMappingRecord.source_identifier,
                SourceEntityMappingRecord.canonical_entity_id,
                SourceEntityMappingRecord.valid_from_utc,
                SourceEntityMappingRecord.valid_to_utc,
            ).where(SourceEntityMappingRecord.mapping_status == "ACTIVE")
        ).all()
    except Exception as exc:  # noqa: BLE001 - no table, no mappings: built-ins still resolve
        logger.warning("identity mappings unavailable: %s", type(exc).__name__)
        return IdentityResolver()
    moment = _as_utc(at_utc or datetime.now(UTC))
    mappings: dict[MappingKey, set[str]] = {}
    points: dict[str, str] = {}
    for source_id, entity_type, identifier, canonical, valid_from, valid_to in rows:
        if valid_from is not None and _as_utc(valid_from) > moment:
            continue
        if valid_to is not None and _as_utc(valid_to) < moment:
            continue
        mappings.setdefault((source_id, entity_type, identifier), set()).add(canonical)
        if entity_type == "delivery_point" and str(canonical).startswith("ent:market_hub:"):
            points[str(identifier).upper()] = str(canonical).rsplit(":", 1)[-1]
    return IdentityResolver(mappings=mappings, points=points)


def entsog_reference_identities(
    nodes: Iterable[Mapping[str, Any]], access_points: Iterable[Mapping[str, Any]]
) -> list[SourceIdentity]:
    """ENTSOG point and operator keys from one complete reference read."""

    points: dict[str, str] = {}
    operators: dict[str, str] = {}
    for node in nodes:
        if str(node.get("source_system") or "ENTSOG") != "ENTSOG":
            continue
        key = str(node.get("source_record_id") or "").strip()
        if key:
            points[key] = str(node.get("name") or key)
    for access in access_points:
        key = str(access.get("point_key") or "").strip()
        if key:
            points.setdefault(key, str(access.get("point_name") or key))
        operator = str(access.get("operator_key") or "").strip()
        if operator:
            operators[operator] = str(access.get("operator_name") or operator)
    identities = [
        SourceIdentity("src-entsog", "entsog_point", key, canonical_id("entsog_point", key),
                       f"ENTSOG reference: {name}"[:512])
        for key, name in sorted(points.items())
    ]
    identities += [
        SourceIdentity("src-entsog", "entsog_operator", key,
                       canonical_id("entsog_operator", key),
                       f"ENTSOG reference: {name}"[:512])
        for key, name in sorted(operators.items())
    ]
    return identities


def record_identities(session, identities: Iterable[SourceIdentity]) -> dict[str, int]:
    """Upsert canonical entities and their source mappings; idempotent, never commits."""

    from sqlalchemy import select

    from eurogas_nexus.db.models import CanonicalEntityRecord, SourceEntityMappingRecord

    items = list(identities)
    known_entities = set(session.scalars(select(CanonicalEntityRecord.canonical_entity_id)))
    known_mappings = set(session.scalars(select(SourceEntityMappingRecord.mapping_id)))
    now = datetime.now(UTC)
    added_entities = added_mappings = 0
    for item in items:
        if item.canonical_entity_id not in known_entities:
            _, entity_type, code = item.canonical_entity_id.split(":", 2)
            session.add(
                CanonicalEntityRecord(
                    canonical_entity_id=item.canonical_entity_id[:128],
                    entity_type=entity_type[:64],
                    canonical_code=code[:64],
                    display_name=(item.evidence.removeprefix("ENTSOG reference: ") or code)[:128],
                    description=item.evidence[:512],
                    created_at_utc=now,
                )
            )
            known_entities.add(item.canonical_entity_id)
            added_entities += 1
        mapping_id = f"map:{item.source_id}:{item.entity_type}:{item.identifier}"[:128]
        if mapping_id in known_mappings:
            continue
        session.add(
            SourceEntityMappingRecord(
                mapping_id=mapping_id,
                canonical_entity_id=item.canonical_entity_id[:128],
                source_id=item.source_id[:64],
                source_entity_type=item.entity_type[:64],
                source_identifier=item.identifier[:160],
                valid_from_utc=REFERENCE_VALID_FROM,
                mapping_status="ACTIVE",
                confidence="CONFIRMED",
                evidence=item.evidence[:512],
                created_at_utc=now,
            )
        )
        known_mappings.add(mapping_id)
        added_mappings += 1
    session.flush()
    return {"identities": len(items), "entities_added": added_entities,
            "mappings_added": added_mappings}


#: What each built-in source stores as an identifier: (source id, entity type, SQL).
#: Each query returns (identifier, rows).
_STORED_IDENTIFIERS: tuple[tuple[str, str, str], ...] = (
    ("src-entsog", "entsog_point",
     "SELECT point_id, COUNT(*) FROM flow_observations WHERE source_system = 'ENTSOG' "
     "GROUP BY point_id UNION ALL SELECT point_id, COUNT(*) FROM capacity_observations "
     "WHERE source_system = 'ENTSOG' GROUP BY point_id"),
    ("src-entsog", "entsog_operator",
     "SELECT {operator}, COUNT(*) FROM flow_observations WHERE source_system = 'ENTSOG' "
     "GROUP BY 1 UNION ALL SELECT {operator}, COUNT(*) FROM capacity_observations "
     "WHERE source_system = 'ENTSOG' GROUP BY 1"),
    ("src-gie", "gie_storage_country",
     "SELECT facility_id, COUNT(*) FROM storage_observations WHERE source_system = 'GIE' "
     "GROUP BY facility_id"),
    ("src-gie", "gie_lng_country",
     "SELECT terminal_id, COUNT(*) FROM lng_observations WHERE source_system = 'GIE' "
     "GROUP BY terminal_id"),
    ("src-national-gas-supply", "national_gas_storage",
     "SELECT facility_id, COUNT(*) FROM storage_observations "
     "WHERE source_system = 'NATIONAL_GAS' GROUP BY facility_id"),
    ("src-national-gas-supply", "national_gas_lng",
     "SELECT terminal_id, COUNT(*) FROM lng_observations "
     "WHERE source_system = 'NATIONAL_GAS' GROUP BY terminal_id"),
    ("src-national-gas-demand", "national_gas_publication",
     "SELECT provider_item_id, COUNT(*) FROM national_gas_actual_demand "
     "GROUP BY provider_item_id"),
    ("src-entsoe", "bidding_zone",
     "SELECT zone, COUNT(*) FROM power_observations WHERE source_system = 'ENTSOE' "
     "GROUP BY zone"),
    ("src-elexon", "bidding_zone",
     "SELECT zone, COUNT(*) FROM power_observations WHERE source_system = 'ELEXON' "
     "GROUP BY zone"),
)


def identity_report(
    session, resolver: IdentityResolver | None = None
) -> dict[str, dict[str, Any]]:
    """Per source: identifiers checked and resolved, and every quarantined one with counts.

    Read-only. A table that is missing in this store is skipped.
    """

    from sqlalchemy import inspect, text

    resolver = resolver or load_resolver(session)
    inspector = inspect(session.connection())
    dialect = session.get_bind().dialect.name
    operator = (
        "metadata_json->>'operatorKey'"
        if dialect == "postgresql"
        else "json_extract(metadata_json, '$.operatorKey')"
    )
    report: dict[str, dict[str, Any]] = {}
    for source_id, entity_type, query in _STORED_IDENTIFIERS:
        tables = [word for word in query.split() if word.endswith("_observations")
                  or word == "national_gas_actual_demand"]
        if not all(inspector.has_table(table) for table in tables):
            continue
        counts: dict[str, int] = {}
        for identifier, rows in session.execute(text(query.format(operator=operator))):
            key = "" if identifier is None else str(identifier)
            counts[key] = counts.get(key, 0) + int(rows)
        entry = report.setdefault(
            source_id, {"checked": 0, "resolved": 0, "rows_unresolved": 0, "unresolved": []}
        )
        for identifier, rows in sorted(counts.items()):
            resolution = resolver.resolve(source_id, entity_type, identifier)
            entry["checked"] += 1
            if resolution.resolved:
                entry["resolved"] += 1
                continue
            entry["rows_unresolved"] += rows
            entry["unresolved"].append(
                {
                    "entity_type": entity_type,
                    "identifier": identifier,
                    "reason": resolution.reason,
                    "count": rows,
                }
            )
    return report


def check_identifiers(
    source_id: str,
    entity_type: str,
    identifiers: Iterable[str | None],
    resolver: IdentityResolver | None = None,
) -> dict[str, Any]:
    """An ingest's identity check: distinct identifiers resolved, and those quarantined.

    Used by the ingest scripts before they store (dry runs included). Built-in identities
    resolve without a database; pass a loaded ``resolver`` for table mappings.
    """

    resolver = resolver or IdentityResolver()
    rows: dict[str, int] = {}
    for identifier in identifiers:
        key = "" if identifier is None else str(identifier)
        rows[key] = rows.get(key, 0) + 1
    quarantined = []
    for identifier, count in sorted(rows.items()):
        resolution = resolver.resolve(source_id, entity_type, identifier)
        if not resolution.resolved:
            quarantined.append(
                {"entity_type": entity_type, "identifier": identifier,
                 "reason": resolution.reason, "rows": count}
            )
    return {
        "checked": len(rows),
        "resolved": len(rows) - len(quarantined),
        "quarantined": quarantined,
    }
