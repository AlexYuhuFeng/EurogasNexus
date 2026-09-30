"""Stored ingestion-run status compatibility shared by data-operations consumers.

``IngestionRunStatus`` in :mod:`eurogas_nexus.domain.dataops.contracts` is the
canonical ingestion-run vocabulary written by the CR-09 scheduler. The
pre-CR-09 public-source ingestor and the simulated market-price writer stored
lowercase ``queued`` / ``running`` / ``succeeded`` / ``failed`` rows, so every
read of the persisted ``ingestion_runs.status`` column needs the same
compatibility interpretation.

This module owns that interpretation once: the source read, the monitoring
alert scanner, pipeline health and the Prometheus exporter classify a stored
status identically instead of each re-deriving its own rule. Only the canonical
vocabulary and the four declared legacy spellings classify; any other stored
value stays unknown. Raw stored values are never rewritten - classification is
a read-side concern, not a migration.
"""

from __future__ import annotations

from eurogas_nexus.domain.dataops.contracts import IngestionRunStatus

__all__ = [
    "FAILURE_RUN_STATUSES",
    "LEGACY_RUN_STATUS_TO_CANONICAL",
    "SUCCESS_RUN_STATUSES",
    "canonical_run_status",
    "is_failed_run_status",
    "stored_statuses_for",
]

#: Stored run statuses written by the pre-CR-09 writers (the public-source
#: ingestor and the simulated market price writer). Canonical rows written by
#: the CR-09 scheduler always use the ``IngestionRunStatus`` spelling; this is
#: the only legacy compatibility mapping, and any other stored value stays
#: unknown instead of being coerced into a lifecycle state.
LEGACY_RUN_STATUS_TO_CANONICAL: dict[str, IngestionRunStatus] = {
    "queued": IngestionRunStatus.QUEUED,
    "running": IngestionRunStatus.RUNNING,
    "succeeded": IngestionRunStatus.SUCCEEDED,
    "failed": IngestionRunStatus.FAILED,
}

#: Canonical statuses that count as a success. ``SUCCEEDED_WITH_WARNINGS`` is a
#: success that stays visibly qualified through its raw stored status.
SUCCESS_RUN_STATUSES: tuple[IngestionRunStatus, ...] = (
    IngestionRunStatus.SUCCEEDED,
    IngestionRunStatus.SUCCEEDED_WITH_WARNINGS,
)

#: Canonical statuses that count as a failure. Pending (``QUEUED`` /
#: ``RUNNING``), ``CANCELLED`` and unknown stored values are neither successes
#: nor failures.
FAILURE_RUN_STATUSES: tuple[IngestionRunStatus, ...] = (IngestionRunStatus.FAILED,)


def canonical_run_status(stored_status: str | None) -> IngestionRunStatus | None:
    """Classify one stored run status; ``None`` means unknown.

    Unknown is neither success nor failure and must stay visibly unknown: only
    the canonical vocabulary and the explicit legacy mapping are recognised,
    never broad case/alias coercion.
    """

    if not isinstance(stored_status, str) or not stored_status:
        return None
    try:
        return IngestionRunStatus(stored_status)
    except ValueError:
        return LEGACY_RUN_STATUS_TO_CANONICAL.get(stored_status)


def is_failed_run_status(stored_status: str | None) -> bool:
    """Return whether a stored run status classifies as canonical ``FAILED``.

    ``FAILED`` and the legacy ``failed`` spelling are the same outcome; pending,
    cancelled and unknown stored values are not failures.
    """

    return canonical_run_status(stored_status) in FAILURE_RUN_STATUSES


def stored_statuses_for(*canonical_statuses: IngestionRunStatus) -> tuple[str, ...]:
    """Every stored spelling that classifies as the given canonical statuses."""

    canonical = frozenset(canonical_statuses)
    return tuple(
        [status.value for status in canonical_statuses]
        + [
            stored
            for stored, mapped in LEGACY_RUN_STATUS_TO_CANONICAL.items()
            if mapped in canonical
        ]
    )
