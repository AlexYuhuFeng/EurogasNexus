"""GIE facility identity in the identity tables (``canonical_entities``, mappings).

GIE's AGSI+/ALSI listing names each storage site and LNG terminal by EIC with its country and
operator, but no coordinates. The reference facility table requires a position, so a
facility without one is held as identity: one canonical entity ``ent:gas_facility:<EIC>``
(name, country, operator, GIE type in its metadata) and one ``src-gie``/``gie_facility``
mapping from the EIC. A refresh updates attributes in place; a facility the listing no
longer carries is **retired, never deleted** (mapping ``RETIRED`` with ``valid_to_utc``,
``retired_at_utc`` in the entity's metadata) and restored if it comes back. An empty listing
changes nothing. Runs in the caller's transaction and never commits.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from eurogas_nexus.db.models import CanonicalEntityRecord, SourceEntityMappingRecord
from eurogas_nexus.domain.ontology.source_identity import canonical_id
from eurogas_nexus.ingestion.gie_facilities import GieFacility

SOURCE_ID = "src-gie"
ENTITY_TYPE = "gie_facility"
#: Mappings written from GIE's own listing are valid for any stored history.
VALID_FROM = datetime(2000, 1, 1, tzinfo=UTC)


def _mapping_id(eic: str) -> str:
    return f"map:{SOURCE_ID}:{ENTITY_TYPE}:{eic}"[:128]


def upsert_gie_facilities(
    session: Session, facilities: Iterable[GieFacility], *, now: datetime
) -> dict[str, int]:
    items = {facility.eic: facility for facility in facilities}
    counts = {"inserted": 0, "updated": 0, "unchanged": 0, "retired": 0, "restored": 0}
    if not items:
        return counts
    entities = {
        row.canonical_entity_id: row
        for row in session.scalars(
            select(CanonicalEntityRecord).where(
                CanonicalEntityRecord.entity_type == ENTITY_TYPE
            )
        )
    }
    mappings = {
        row.source_identifier: row
        for row in session.scalars(
            select(SourceEntityMappingRecord).where(
                SourceEntityMappingRecord.source_id == SOURCE_ID,
                SourceEntityMappingRecord.source_entity_type == ENTITY_TYPE,
            )
        )
    }
    for eic, facility in items.items():
        entity_id = canonical_id(ENTITY_TYPE, eic)
        metadata: dict[str, Any] = facility.metadata()
        description = (
            f"GIE {'AGSI+' if facility.kind == 'storage' else 'ALSI'} listing: "
            f"{facility.name}, {facility.country}, {facility.operator_name}"
        )[:512]
        entity = entities.get(entity_id)
        if entity is None:
            session.add(CanonicalEntityRecord(
                canonical_entity_id=entity_id[:128], entity_type=ENTITY_TYPE,
                canonical_code=eic[:64], display_name=facility.name[:128],
                description=description, metadata_json=metadata, created_at_utc=now,
            ))
            counts["inserted"] += 1
        elif (entity.display_name, entity.description, entity.metadata_json) != (
            facility.name[:128], description, metadata
        ):
            entity.display_name = facility.name[:128]
            entity.description = description
            entity.metadata_json = metadata
            counts["updated"] += 1
        else:
            counts["unchanged"] += 1
        mapping = mappings.get(eic)
        if mapping is None:
            session.add(SourceEntityMappingRecord(
                mapping_id=_mapping_id(eic), canonical_entity_id=entity_id[:128],
                source_id=SOURCE_ID, source_entity_type=ENTITY_TYPE,
                source_identifier=eic[:160], valid_from_utc=VALID_FROM,
                mapping_status="ACTIVE", confidence="CONFIRMED",
                evidence=f"GIE facility listing: {facility.name}"[:512], created_at_utc=now,
            ))
        elif mapping.mapping_status != "ACTIVE":
            mapping.mapping_status = "ACTIVE"
            mapping.valid_to_utc = None
            counts["restored"] += 1
    for eic, mapping in mappings.items():
        if eic in items or mapping.mapping_status != "ACTIVE":
            continue
        mapping.mapping_status = "RETIRED"
        mapping.valid_to_utc = now
        entity = entities.get(canonical_id(ENTITY_TYPE, eic))
        if entity is not None:
            entity.metadata_json = {**(entity.metadata_json or {}),
                                    "retired_at_utc": now.isoformat()}
        counts["retired"] += 1
    session.flush()
    return counts


def load_gie_facilities(session: Session) -> list[dict[str, Any]]:
    """Facilities with an active GIE mapping, as their stored metadata (empty without tables)."""

    from sqlalchemy import inspect

    connection = session.connection()
    if not (inspect(connection).has_table("canonical_entities")
            and inspect(connection).has_table("source_entity_mappings")):
        return []
    rows = session.execute(
        select(CanonicalEntityRecord.metadata_json)
        .join(
            SourceEntityMappingRecord,
            SourceEntityMappingRecord.canonical_entity_id
            == CanonicalEntityRecord.canonical_entity_id,
        )
        .where(
            SourceEntityMappingRecord.source_id == SOURCE_ID,
            SourceEntityMappingRecord.source_entity_type == ENTITY_TYPE,
            SourceEntityMappingRecord.mapping_status == "ACTIVE",
        )
    ).scalars()
    return [dict(row) for row in rows if row]
