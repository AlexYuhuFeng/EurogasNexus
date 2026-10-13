"""ENTSOG append-or-verify persistence without inventing revision history.

Reuse the existing row-lock/ON CONFLICT algorithm with ENTSOG semantic columns.
The generic in-place upsert and GIE's field sets and error contract are unchanged.
Each call owns a savepoint, never a commit: mixed revised/new batches roll back
their canonical writes while the caller's previously archived raw pages survive.
"""

from __future__ import annotations

import math
from typing import Any

from sqlalchemy.orm import Session

from eurogas_nexus.db.repositories.public_ingestion_upsert import (
    GieRevisionRaceError,
    GieRevisionRequiresHistoryError,
    upsert_revision_safe_observation_rows,
)

_COMMON_FIELDS = (
    "source_system",
    "source_record_id",
    "point_id",
    "point_name",
    "direction",
    "original_value",
    "original_unit",
    "period_start_utc",
    "period_end_utc",
    "research_only",
)
ENTSOG_SEMANTIC_FIELDS = {
    "flow_observations": (*_COMMON_FIELDS, "kind", "flow_mcm_d"),
    "capacity_observations": (*_COMMON_FIELDS, "capacity_type", "capacity_mcm_d"),
}


class EntsogObservationPersistenceError(RuntimeError):
    code = "entsog_observation_persistence_error"


class EntsogRevisionRequiresHistoryError(EntsogObservationPersistenceError):
    code = "entsog_revision_requires_history"


class EntsogRevisionRaceError(EntsogObservationPersistenceError):
    code = "entsog_revision_race_unresolved"


class EntsogInvalidObservationError(EntsogObservationPersistenceError):
    code = "entsog_invalid_observation"


def upsert_entsog_observation_rows(
    session: Session,
    model: Any,
    rows: list[dict[str, Any]],
) -> dict[str, int]:
    """Insert absent keys; verify unchanged keys; refuse revisions atomically."""
    fields = ENTSOG_SEMANTIC_FIELDS.get(model.__table__.name)
    if not rows or fields is None:
        raise EntsogInvalidObservationError("ENTSOG observation table and nonempty rows required.")
    prepared = []
    seen = set()
    for row in rows:
        key = row.get("observation_id")
        metadata = row.get("metadata_json") or {}
        if (
            row.get("source_system") != "ENTSOG"
            or not isinstance(key, str)
            or not key
            or key.startswith(("sim-", "mock-"))
            or key in seen
            or metadata.get("simulated")
            or metadata.get("mock")
        ):
            raise EntsogInvalidObservationError(
                "ENTSOG rows must have distinct real provider identities."
            )
        seen.add(key)
        if any(
            isinstance(row.get(name), (int, float)) and not math.isfinite(row[name])
            for name in fields
        ):
            raise EntsogInvalidObservationError("ENTSOG observation contains a nonfinite value.")
        # SQLAlchemy's flow kind default must be explicit during equality checks.
        prepared.append({"kind": "actual", **row} if "kind" in fields else dict(row))
    try:
        with session.begin_nested():
            return upsert_revision_safe_observation_rows(
                session,
                model,
                prepared,
                semantic_fields=fields,
            )
    except GieRevisionRequiresHistoryError:
        raise EntsogRevisionRequiresHistoryError(
            "ENTSOG revised semantic content requires append-only history; original rows kept."
        ) from None
    except GieRevisionRaceError:
        raise EntsogRevisionRaceError("ENTSOG concurrent insert could not be verified.") from None
