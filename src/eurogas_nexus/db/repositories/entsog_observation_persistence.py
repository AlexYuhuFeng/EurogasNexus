"""ENTSOG append-or-verify persistence without inventing revision history.

Reuse the existing row-lock/ON CONFLICT algorithm with ENTSOG semantic columns.
The generic in-place upsert and GIE's field sets and error contract are unchanged.
Each call owns a savepoint, never a commit: mixed revised/new batches roll back
their canonical writes while the caller's previously archived raw pages survive.

RFC0005 native rows add the version and exact native wire payload to the semantic
comparison.  They remain additive: a native row must use its new namespace, while
both-NULL legacy rows stay replayable under their original ids.  A changed native
payload is therefore a typed revision refusal, never a silent overwrite.
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
from eurogas_nexus.ingestion.entsog_native_payloads import (
    NativeRateProjectionError,
    validate_native_rate_payload,
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
    "flow_observations": (
        *_COMMON_FIELDS,
        "kind",
        "normalizer_version",
        "native_rate_json",
        "flow_mcm_d",
    ),
    "capacity_observations": (
        *_COMMON_FIELDS,
        "capacity_type",
        "normalizer_version",
        "native_rate_json",
        "capacity_mcm_d",
    ),
}
_NATIVE_NAMESPACES = {
    "flow_observations": ("entsog-flow-n1-", "flow_mcm_d"),
    "capacity_observations": ("entsog-capacity-n1-", "capacity_mcm_d"),
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
    table_name = model.__table__.name
    fields = ENTSOG_SEMANTIC_FIELDS.get(table_name)
    if not rows or fields is None or table_name not in _NATIVE_NAMESPACES:
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
        _validate_native_payload(row, table_name)
        # SQLAlchemy's flow kind default must be explicit during equality checks.
        prepared_row = {"kind": "actual", **row} if "kind" in fields else dict(row)
        # Legacy replay carries both native columns as NULL explicitly, so the
        # expanded semantic comparison cannot mistake an absent key for a change.
        prepared_row.setdefault("normalizer_version", None)
        prepared_row.setdefault("native_rate_json", None)
        prepared.append(prepared_row)
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


def _validate_native_payload(row: dict[str, Any], table_name: str) -> None:
    """Strictly verify native columns and their exact float volume projection."""

    version = row.get("normalizer_version")
    payload = row.get("native_rate_json")
    if version is None and payload is None:
        return  # legacy row: replayable only as legacy
    if version is None or payload is None:
        raise EntsogInvalidObservationError(
            "ENTSOG native version and payload must both be present or both be NULL."
        )
    if not isinstance(version, str):
        raise EntsogInvalidObservationError("ENTSOG native normalizer version must be a string.")
    try:
        rate = validate_native_rate_payload(payload, version)
    except NativeRateProjectionError:
        raise EntsogInvalidObservationError(
            "ENTSOG native version/payload failed strict codec validation."
        ) from None

    namespace, volume_field = _NATIVE_NAMESPACES[table_name]
    key = row.get("observation_id")
    if not isinstance(key, str) or not key.startswith(namespace):
        raise EntsogInvalidObservationError(
            "ENTSOG native content requires its RFC0005 deterministic namespace."
        )

    stored_volume = row.get(volume_field)
    if rate.quantity_kind == "energy":
        if stored_volume is not None:
            raise EntsogInvalidObservationError(
                "ENTSOG native energy content must not carry a volume value."
            )
        return
    if rate.volume_mcm_per_day is None:
        raise EntsogInvalidObservationError("ENTSOG native volume content has no canonical volume.")
    try:
        canonical = float(rate.volume_mcm_per_day)
    except (OverflowError, ValueError):
        raise EntsogInvalidObservationError(
            "ENTSOG canonical native volume is not a finite float."
        ) from None
    if (
        isinstance(stored_volume, bool)
        or not isinstance(stored_volume, (int, float))
        or not math.isfinite(stored_volume)
        or not math.isfinite(canonical)
        or float(stored_volume) != canonical
    ):
        raise EntsogInvalidObservationError(
            "ENTSOG native volume disagrees with the canonical native volume."
        )
