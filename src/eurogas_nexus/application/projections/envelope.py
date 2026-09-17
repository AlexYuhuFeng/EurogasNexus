"""The uniform projection envelope and slice contract (Architecture V2 Wave 5).

Both the public route module and the application tests build payloads through
these two helpers, so the shape a client renders is declared in exactly one
place:

``{"data": {...}, "meta": {...}}``
    The repository's public envelope convention (``docs/api/API_CONVENTIONS.md``).
    ``meta`` always carries ``research_only``, ``human_review_required``,
    ``source_references``, ``warnings`` - plus the projection's ``as_of_utc``,
    ``time_basis``, ``projection`` identity and the canonical tables read.

``projection_slice``
    Every named slice of ``data["slices"]`` has the same keys: ``available``,
    ``source_references``, ``row_count``, ``rows`` or ``payload``, ``freshness``,
    ``entitlement``, ``context_filter`` and ``warnings``. A key that does not
    apply is present and ``None``, never missing, so a consumer never has to
    branch on key presence.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

#: Provenance labels already used across the public read surface.
SOURCE_RUNTIME_POSTGRESQL = "runtime-postgresql"
SOURCE_RUNTIME_DB_NOT_CONFIGURED = "runtime-db-not-configured"

#: Warning codes already used by the runtime/postgres read surfaces.
WARNING_RUNTIME_DB_NOT_CONFIGURED = "RUNTIME_DB_NOT_CONFIGURED"
WARNING_ENTITLEMENT_FILTERED = "ENTITLEMENT_FILTERED"
WARNING_EVIDENCE_INCOMPLETE = "REVIEW_EVIDENCE_INCOMPLETE"
WARNING_DECISION_NEEDS_ATTENTION = "REVIEW_DECISION_NEEDS_ATTENTION"
WARNING_CONTEXT_FILTER_UNSUPPORTED = "CONTEXT_FILTER_NOT_APPLIED"
WARNING_SOURCE_STALE = "SOURCE_STALE"
WARNING_NO_MEASUREMENT = "NO_MEASUREMENT"


def dedupe(values: Iterable[str | None]) -> list[str]:
    """Return non-empty values, de-duplicated, keeping first-seen order."""

    ordered: list[str] = []
    for value in values:
        if value and value not in ordered:
            ordered.append(value)
    return ordered


def projection_slice(
    *,
    source: str,
    freshness: dict[str, Any],
    rows: Sequence[Any] | None = None,
    payload: dict[str, Any] | None = None,
    entitlement: dict[str, Any] | None = None,
    context_filter: dict[str, Any] | None = None,
    limits: dict[str, Any] | None = None,
    warnings: Iterable[str] = (),
    notes: Iterable[str] = (),
) -> dict[str, Any]:
    """Build one slice of a projection payload.

    Args:
        source: Provenance label of the read that produced the slice
            (``runtime-postgresql`` or ``runtime-db-not-configured``).
        freshness: The slice's freshness block.
        rows: Collection payload, for list-shaped slices.
        payload: Singleton payload, for object-shaped slices.
        entitlement: Row-filter record, or ``None`` when this slice carries no
            commercial rows.
        context_filter: Which Active Context dimensions the backend applied.
        limits: Applied bound (``row_limit``/``truncated``) when the slice is
            bounded by the caller.
        warnings: Non-fatal condition codes raised by this slice.
        notes: Human-readable statements about what the slice does not contain.

    Returns:
        The slice dict, with every contract key present.
    """

    available = source == SOURCE_RUNTIME_POSTGRESQL
    slice_payload: dict[str, Any] = {
        "available": available,
        "source_references": [source],
        "row_count": len(rows) if rows is not None else 0,
        "rows": list(rows) if rows is not None else None,
        "payload": payload,
        "freshness": freshness,
        "entitlement": entitlement,
        "context_filter": context_filter,
        "limits": limits,
        "warnings": dedupe(warnings),
        "notes": dedupe(notes),
    }
    return slice_payload


def projection_envelope(
    data: dict[str, Any],
    *,
    projection: str,
    projection_version: str,
    as_of_utc: str,
    time_basis: dict[str, Any],
    source_references: Iterable[str],
    warnings: Iterable[str],
    table_lineage: Iterable[str] = (),
) -> dict[str, Any]:
    """Wrap a projection payload in the repository's public envelope.

    Args:
        data: The projection payload.
        projection: Stable projection id (also carried inside ``data``).
        projection_version: Versioned projection contract id.
        as_of_utc: The single as-of instant, mirrored from the context.
        time_basis: The declared time basis block, mirrored from the context.
        source_references: Provenance labels of every slice read.
        warnings: Non-fatal condition codes for the whole payload.
        table_lineage: Canonical runtime tables the payload was composed from.

    Returns:
        ``{"data": ..., "meta": {...}}`` with honest, de-duplicated meta. The
        decision-support markers are always ``True``: a projection is a
        read model over decision support, never an execution surface.
    """

    return {
        "data": data,
        "meta": {
            "projection": projection,
            "projection_version": projection_version,
            "as_of_utc": as_of_utc,
            "time_basis": time_basis,
            "research_only": True,
            "human_review_required": True,
            "source_references": dedupe(source_references),
            "warnings": dedupe(warnings),
            "table_lineage": dedupe(table_lineage),
        },
    }


def entitlement_block(
    *,
    applied: bool,
    filtered_out: int,
    reason: str,
) -> dict[str, Any]:
    """Describe the commercial row filtering applied to one slice.

    Args:
        applied: Whether a row-level filter ran on this slice.
        filtered_out: Rows the filter removed (``0`` when it did not run).
        reason: Stable statement of the rule, or of why no rule applies.

    Returns:
        The entitlement record. ``applied=False`` is only ever used where the
        underlying route returns the same rows unfiltered, so a projection is
        never laxer than the endpoint it composes.
    """

    return {
        "row_filter_applied": applied,
        "filtered_out": filtered_out,
        "reason": reason,
    }


def context_filter_block(
    *,
    applied: Sequence[str],
    rule: str,
) -> dict[str, Any]:
    """Describe which Active Context dimensions the backend filtered on.

    Args:
        applied: Context dimensions actually applied (``hub``, ``product``).
        rule: Stable statement of the matching rule, or of why none applies.

    Returns:
        The context-filter record for one slice.
    """

    return {
        "applied": list(applied),
        "rule": rule,
    }
