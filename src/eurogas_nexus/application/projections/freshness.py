"""Per-slice freshness and source provenance for projections (Wave 5).

The vocabulary is the repository's existing one and is not re-invented:

- ``domain.monitoring.freshness.evaluate_freshness`` owns the read-side
  three-state judgement (live / stale / unknown) used by the Source Center;
- ``domain.dataops.contracts.FreshnessState`` owns the backend state names;
- ``domain.ingestion.source_registry.registered_sources`` owns the declared
  freshness expectation (minutes) per source system;
- ``governance.entitlement.entitlement_scope_for_source`` owns the
  per-row entitlement annotation the market endpoints already return.

The mapping from ``FreshnessStatus`` to ``FreshnessState`` follows
``application.data_products`` exactly (LIVE -> FRESH, STALE -> STALE, and
UNKNOWN -> MISSING when nothing was measured at all, else UNKNOWN), so a client
reads one state vocabulary across the Data Product catalogue and the
projections.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from eurogas_nexus.domain.dataops.contracts import FreshnessState
from eurogas_nexus.domain.monitoring.freshness import (
    FreshnessStatus,
    evaluate_freshness,
)
from eurogas_nexus.governance.entitlement import entitlement_scope_for_source
from eurogas_nexus.security.identity import source_family_for_entitlement

#: Basis string reported for freshness measured against an observation instant.
OBSERVED_AT_BASIS = "observed_at_utc"
#: Basis string reported for freshness measured against a detection instant.
DETECTED_AT_BASIS = "detected_at_utc"

#: Distinct source systems seen in one slice scan.
_ROW_SOURCE_KEY = "source_system"


def source_freshness_expectations() -> dict[str, int]:
    """Return the declared freshness expectation per source entitlement family.

    Returns:
        Mapping of entitlement family (``EEX_Sim`` -> ``EEX``) to the
        expectation in minutes declared by the source registry. Families
        without a declared expectation are absent, which reads as "unknown"
        rather than "fresh" (fail-closed).
    """

    from eurogas_nexus.domain.ingestion.source_registry import registered_sources

    expectations: dict[str, int] = {}
    for source in registered_sources():
        minutes = source.get("freshness_expectation_minutes")
        if not isinstance(minutes, int) or minutes <= 0:
            continue
        family = source_family_for_entitlement(str(source.get("source_system") or ""))
        if not family:
            continue
        expectations[family] = min(minutes, expectations.get(family, minutes))
    return expectations


def expectation_for_source(source_system: str | None) -> int | None:
    """Return the declared expectation (minutes) for one source system."""

    if not source_system:
        return None
    family = source_family_for_entitlement(str(source_system))
    return source_freshness_expectations().get(family)


def strictest_expectation(source_systems: Iterable[str | None]) -> int | None:
    """Return the strictest declared expectation across several sources.

    The strictest (smallest) window is used so a slice is never reported
    fresher than its least forgiving contributing source allows.
    """

    expectations = [
        expectation
        for expectation in (expectation_for_source(source) for source in source_systems)
        if expectation is not None
    ]
    return min(expectations) if expectations else None


def row_source_systems(rows: Iterable[Mapping[str, Any]]) -> list[str]:
    """Return the distinct source systems present in a slice, ordered."""

    seen: list[str] = []
    for row in rows:
        value = row.get(_ROW_SOURCE_KEY)
        if isinstance(value, str) and value and value not in seen:
            seen.append(value)
    return sorted(seen)


def latest_iso(values: Iterable[str | datetime | None]) -> str | None:
    """Return the newest ISO-8601 timestamp from an iterable, or ``None``.

    Values may be ISO strings or ``datetime`` instances: the quote repository
    returns raw datetimes while the observation shapers return ISO strings, and
    both must be comparable on one axis.
    """

    candidates = [_iso_value(value) for value in values]
    present = [value for value in candidates if value]
    if not present:
        return None
    return max(present, key=_sort_key)


def latest_iso_for_keys(
    rows: Iterable[Mapping[str, Any]],
    keys: Sequence[str],
) -> str | None:
    """Return the newest timestamp in ``rows`` across the given candidate keys.

    The first key that carries a value on a row wins, so a slice can declare an
    ordered preference (for example ``detected_at_utc`` then
    ``observed_at_utc``) without any guessing inside the projection.
    """

    values: list[str | datetime | None] = []
    for row in rows:
        for key in keys:
            value = row.get(key)
            if value:
                values.append(value)
                break
    return latest_iso(values)


def _iso_value(value: str | datetime | None) -> str | None:
    """Normalize one timestamp value to an ISO-8601 UTC string.

    Values may be ``datetime`` instances (the quote repository returns raw
    datetimes) or ISO strings (the observation shapers). A timestamp without an
    offset - what a driver returns for a timezone-aware column on SQLite - is
    reported as UTC, so every slice's freshness block is on one explicit basis.
    """

    if value is None:
        return None
    if isinstance(value, datetime):
        return _as_utc(value).isoformat()
    text = str(value)
    parsed = parse_iso_utc(text)
    if parsed is None:
        return text
    return parsed.isoformat()


def _as_utc(value: datetime) -> datetime:
    """Normalize a datetime to aware UTC (naive values are UTC)."""

    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def parse_iso_utc(value: str | None) -> datetime | None:
    """Parse an ISO-8601 timestamp, returning ``None`` when it is unusable."""

    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def freshness_state(
    *,
    row_count: int,
    last_observed_at_utc: str | None,
    expectation_minutes: int | None,
    now_utc: datetime,
) -> FreshnessState:
    """Map the shared freshness evaluation onto the backend state vocabulary."""

    status = evaluate_freshness(
        expectation_minutes or 0,
        parse_iso_utc(last_observed_at_utc),
        now_utc=now_utc,
    )
    if status is FreshnessStatus.LIVE:
        return FreshnessState.FRESH
    if status is FreshnessStatus.STALE:
        return FreshnessState.STALE
    return FreshnessState.MISSING if row_count == 0 else FreshnessState.UNKNOWN


def freshness_block(
    *,
    row_count: int,
    last_observed_at_utc: str | None,
    expectation_minutes: int | None,
    now_utc: datetime,
    basis: str = OBSERVED_AT_BASIS,
    derived_from: str | None = None,
) -> dict[str, Any]:
    """Build the freshness block every projection slice carries.

    Args:
        row_count: Rows the slice actually returned (after entitlement and
            context filtering).
        last_observed_at_utc: Newest observation instant in the slice, or
            ``None`` when the slice is empty.
        expectation_minutes: Declared expectation window, or ``None`` when no
            contributing source declares one.
        now_utc: The projection's as-of instant, used as the evaluation clock.
        basis: Timestamp field the age was measured against.
        derived_from: Name of the slice this one is composed from, when the
            slice carries no timestamp of its own.

    Returns:
        A block with the backend ``state``, the ``basis``, the evaluated
        instant, the measured instant, the declared expectation and whether a
        measurement exists at all. An absent measurement is never reported as
        fresh.
    """

    state = freshness_state(
        row_count=row_count,
        last_observed_at_utc=last_observed_at_utc,
        expectation_minutes=expectation_minutes,
        now_utc=now_utc,
    )
    return {
        "state": state.value,
        "basis": basis,
        "evaluated_at_utc": now_utc.isoformat(),
        "last_observed_at_utc": last_observed_at_utc,
        "expected_within_minutes": expectation_minutes,
        "expectation_source": "source_registry" if expectation_minutes else "none",
        "measured": last_observed_at_utc is not None,
        "derived_from": derived_from,
    }


def source_provenance_rows(
    rows_by_slice: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    timestamp_keys: Mapping[str, Sequence[str]],
    now_utc: datetime,
) -> list[dict[str, Any]]:
    """Build the per-source freshness/provenance rows of the ``data_sources`` slice.

    Only rows that survived entitlement and context filtering are passed in, so
    the summary can never name a source family the caller may not see.

    Args:
        rows_by_slice: Slice name -> returned rows.
        timestamp_keys: Slice name -> ordered timestamp keys to measure.
        now_utc: The projection's as-of instant.

    Returns:
        One entry per source system with its family, simulated marker, row
        count, newest observation, declared expectation, freshness state,
        entitlement annotation and the slices it contributed to.
    """

    by_source: dict[str, dict[str, Any]] = {}
    for slice_name, rows in rows_by_slice.items():
        keys = timestamp_keys.get(slice_name, ())
        for row in rows:
            source = row.get(_ROW_SOURCE_KEY)
            if not isinstance(source, str) or not source:
                continue
            entry = by_source.setdefault(
                source,
                {
                    "source_system": source,
                    "row_count": 0,
                    "observed": [],
                    "slices": [],
                },
            )
            entry["row_count"] += 1
            if slice_name not in entry["slices"]:
                entry["slices"].append(slice_name)
            entry["observed"].append(latest_iso_for_keys([row], keys))

    summary: list[dict[str, Any]] = []
    for source, entry in sorted(by_source.items()):
        family = source_family_for_entitlement(source)
        expectation = expectation_for_source(source)
        last_observed = latest_iso(entry["observed"])
        summary.append(
            {
                "source_system": source,
                "source_family": family,
                "simulated": bool(family) and family != source,
                "row_count": entry["row_count"],
                "last_observed_at_utc": last_observed,
                "freshness_expectation_minutes": expectation,
                "freshness": freshness_block(
                    row_count=entry["row_count"],
                    last_observed_at_utc=last_observed,
                    expectation_minutes=expectation,
                    now_utc=now_utc,
                ),
                "entitlement_scope": entitlement_scope_for_source(source),
                "declared_in_source_registry": expectation is not None,
                "slices": sorted(entry["slices"]),
            }
        )
    return summary


def freshness_state_summary(rows: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    """Count the per-source freshness states of the ``data_sources`` slice."""

    counts = {
        FreshnessState.FRESH.value: 0,
        FreshnessState.STALE.value: 0,
        FreshnessState.MISSING.value: 0,
        FreshnessState.UNKNOWN.value: 0,
    }
    for row in rows:
        block = row.get("freshness")
        state = block.get("state") if isinstance(block, Mapping) else None
        if state in counts:
            counts[state] += 1
    return {
        "source_count": sum(counts.values()),
        "fresh_sources": counts[FreshnessState.FRESH.value],
        "stale_sources": counts[FreshnessState.STALE.value],
        "missing_sources": counts[FreshnessState.MISSING.value],
        "unknown_sources": counts[FreshnessState.UNKNOWN.value],
    }


def _sort_key(value: str) -> datetime:
    """Return a sortable instant for an ISO string (unparsable sorts first)."""

    parsed = parse_iso_utc(value)
    return parsed if parsed is not None else datetime.min.replace(tzinfo=UTC)
