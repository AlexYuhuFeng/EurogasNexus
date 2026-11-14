"""ENTSOG append-or-verify persistence with append-only revision history.

Reuse the existing row-lock/ON CONFLICT algorithm with ENTSOG semantic columns.
Each call owns a savepoint, never a commit: a refused batch rolls back its
canonical writes while the caller's previously archived raw pages survive.

ENTSOG publishes provisional values and revises them. A change confined to the
value fields (:data:`ENTSOG_REVISABLE_FIELDS`, plus the ``flowStatus`` quality
flag) replaces the current row and writes the replaced version to
``observation_revisions`` in the same transaction; the row keeps its first
receipt in ``observed_at_utc`` and records the new receipt in
``revised_at_utc``. A change to anything else compared (source, point,
direction, period, kind/capacity type, unit, research flag, normalizer version,
``operatorKey``, ``periodType``) is not a revision of the same observation and
is still refused atomically.

**Open gas days (flows only).** ENTSOG publishes the running gas day; a flow row
received before its period ended is a partial-day snapshot. It is stored (a
reader that asks for within-day data can have it) and is replaced, with its own
history record, by the first receipt after the period end even when the value
is equal (reason ``period_closed``). Closed-day readers take only values
received at or after the period end (``pipeline_supply.published_after_close``),
so the snapshot never passes as the day's flow. Capacity is published ahead of
its period by nature and is not subject to this rule.

RFC0005 native rows add the version and exact native wire payload to the
semantic comparison. They remain additive: a native row must use its new
namespace, while both-NULL legacy rows stay replayable under their original ids.
Receipt, archive, run and hash churn remains ignored.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from sqlalchemy.orm import Session

from eurogas_nexus.db.repositories.capacity_ranges import reconfirm_resplit_ranges
from eurogas_nexus.db.repositories.public_ingestion_upsert import (
    GieRevisionIdentityConflictError,
    GieRevisionRaceError,
    GieRevisionRequiresHistoryError,
    GieStaleRevisionError,
    RevisionPolicy,
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
#: Provider identity/quality metadata that must not silently change under an
#: unchanged natural key. Unlisted receipt/archive/run/hash fields stay ignored.
_SEMANTIC_METADATA_KEYS = ("operatorKey", "flowStatus", "periodType")
#: Fields a provider revision may change: the published quantity and its native
#: payload, the descriptive point name and the ``flowStatus`` quality flag. The
#: unit is part of the ENTSOG record id, so a different unit is a different record.
ENTSOG_REVISABLE_FIELDS = {
    "flow_observations": ("original_value", "flow_mcm_d", "native_rate_json", "point_name"),
    "capacity_observations": (
        "original_value",
        "capacity_mcm_d",
        "native_rate_json",
        "point_name",
    ),
}
_REVISABLE_METADATA_KEYS = ("flowStatus",)


class EntsogObservationPersistenceError(RuntimeError):
    code = "entsog_observation_persistence_error"


class EntsogRevisionRequiresHistoryError(EntsogObservationPersistenceError):
    code = "entsog_revision_requires_history"


class EntsogRevisionIdentityConflictError(EntsogRevisionRequiresHistoryError):
    """An existing key differs in source, identity or period: not a revision."""

    code = "entsog_revision_identity_conflict"


class EntsogStaleRevisionError(EntsogRevisionRequiresHistoryError):
    """A changed value not received after the stored version (an old capture replayed)."""

    code = "entsog_revision_not_newer"


class EntsogRevisionRaceError(EntsogObservationPersistenceError):
    code = "entsog_revision_race_unresolved"


class EntsogInvalidObservationError(EntsogObservationPersistenceError):
    code = "entsog_invalid_observation"


def upsert_entsog_observation_rows(
    session: Session,
    model: Any,
    rows: list[dict[str, Any]],
) -> dict[str, int]:
    """Insert absent keys, verify unchanged keys, revise value changes with history.

    Returns ``inserted``/``updated``/``unchanged``/``revised`` counts; see the module
    docstring for what is revised and what is refused. Capacity also returns ``resplit``:
    stored ranges re-published after a later overlapping range had re-split them, each
    moved to this receipt with a ``range_resplit`` history record and counted in
    ``updated`` (``capacity_ranges.reconfirm_resplit_ranges``).
    """
    table_name = model.__table__.name
    fields = ENTSOG_SEMANTIC_FIELDS.get(table_name)
    if not rows or fields is None or table_name not in _NATIVE_NAMESPACES:
        raise EntsogInvalidObservationError("ENTSOG observation table and nonempty rows required.")
    prepared = []
    seen = set()
    for row in rows:
        key = row.get("observation_id")
        metadata = row.get("metadata_json")
        if metadata is None:
            metadata = {}
        elif not isinstance(metadata, Mapping):
            raise EntsogInvalidObservationError(
                "ENTSOG observation metadata_json must be a mapping, not a list or scalar."
            )
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
    policy = RevisionPolicy(
        revisable_fields=ENTSOG_REVISABLE_FIELDS[table_name],
        revisable_metadata_keys=_REVISABLE_METADATA_KEYS,
        close_open_periods=table_name == "flow_observations",
    )
    try:
        with session.begin_nested():
            outcome = upsert_revision_safe_observation_rows(
                session,
                model,
                prepared,
                semantic_fields=fields,
                semantic_metadata_keys=_SEMANTIC_METADATA_KEYS,
                revisions=policy,
            )
            if table_name == "capacity_observations":
                # A range re-published after a later overlapping range takes this receipt,
                # so readers resolving a day to the latest-received range see the provider's
                # current split (capacity_ranges, CAPACITY_RESOLUTION_RULE).
                moved = reconfirm_resplit_ranges(session, prepared)
                outcome["resplit"] = moved
                outcome["updated"] += moved
                outcome["unchanged"] -= moved
            return outcome
    except GieRevisionRequiresHistoryError as exc:
        changed = (
            f" Changed semantic field(s): [{', '.join(exc.changed_fields)}]."
            if exc.changed_fields
            else ""
        )
        if isinstance(exc, GieStaleRevisionError):
            raise EntsogStaleRevisionError(
                "ENTSOG changed value was not received after the stored version; original "
                f"rows kept.{changed}"
            ) from None
        if isinstance(exc, GieRevisionIdentityConflictError):
            raise EntsogRevisionIdentityConflictError(
                "ENTSOG row differs from the stored row in a field a revision may not "
                f"change; original rows kept.{changed}"
            ) from None
        raise EntsogRevisionRequiresHistoryError(
            "ENTSOG revised semantic content was refused; original rows kept."
            f"{changed}"
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
