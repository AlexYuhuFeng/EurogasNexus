"""Shared stored ingestion-run status vocabulary tests (pure, deterministic)."""

from __future__ import annotations

import pytest

from eurogas_nexus.domain.dataops.contracts import IngestionRunStatus
from eurogas_nexus.domain.dataops.run_status import (
    FAILURE_RUN_STATUSES,
    LEGACY_RUN_STATUS_TO_CANONICAL,
    SUCCESS_RUN_STATUSES,
    canonical_run_status,
    is_failed_run_status,
    stored_statuses_for,
)


@pytest.mark.parametrize("stored", [status.value for status in IngestionRunStatus])
def test_canonical_spellings_classify_as_themselves(stored: str) -> None:
    assert canonical_run_status(stored) is IngestionRunStatus(stored)


def test_only_the_four_declared_legacy_spellings_map_to_canonical_peers() -> None:
    assert LEGACY_RUN_STATUS_TO_CANONICAL == {
        "queued": IngestionRunStatus.QUEUED,
        "running": IngestionRunStatus.RUNNING,
        "succeeded": IngestionRunStatus.SUCCEEDED,
        "failed": IngestionRunStatus.FAILED,
    }

    assert canonical_run_status("queued") is IngestionRunStatus.QUEUED
    assert canonical_run_status("running") is IngestionRunStatus.RUNNING
    assert canonical_run_status("succeeded") is IngestionRunStatus.SUCCEEDED
    assert canonical_run_status("failed") is IngestionRunStatus.FAILED


@pytest.mark.parametrize(
    "stored",
    [
        "Failed",
        "FAILURE",
        "SUCCESS",
        "Succeeded",
        "SUCCEEDED-WITH-WARNINGS",
        "succeeded_with_warnings",
        "BLOCKED",
        "MYSTERY",
        " failed",
        "failed ",
        "unknown",
        "",
        None,
    ],
)
def test_unknown_spellings_stay_unknown_and_are_not_failures(stored: str | None) -> None:
    assert canonical_run_status(stored) is None
    assert is_failed_run_status(stored) is False


def test_failed_and_legacy_failed_are_the_same_failure_outcome() -> None:
    assert is_failed_run_status("FAILED") is True
    assert is_failed_run_status("failed") is True

    for stored in (
        "SUCCEEDED",
        "succeeded",
        "SUCCEEDED_WITH_WARNINGS",
        "QUEUED",
        "queued",
        "RUNNING",
        "running",
        "CANCELLED",
        "BLOCKED",
        None,
    ):
        assert is_failed_run_status(stored) is False


def test_role_sets_declare_exactly_the_success_and_failure_outcomes() -> None:
    assert SUCCESS_RUN_STATUSES == (
        IngestionRunStatus.SUCCEEDED,
        IngestionRunStatus.SUCCEEDED_WITH_WARNINGS,
    )
    assert FAILURE_RUN_STATUSES == (IngestionRunStatus.FAILED,)


def test_stored_statuses_for_covers_canonical_and_legacy_spellings() -> None:
    assert stored_statuses_for(*FAILURE_RUN_STATUSES) == ("FAILED", "failed")
    assert stored_statuses_for(*SUCCESS_RUN_STATUSES) == (
        "SUCCEEDED",
        "SUCCEEDED_WITH_WARNINGS",
        "succeeded",
    )
    assert stored_statuses_for(*IngestionRunStatus) == (
        "QUEUED",
        "RUNNING",
        "SUCCEEDED",
        "SUCCEEDED_WITH_WARNINGS",
        "FAILED",
        "CANCELLED",
        "queued",
        "running",
        "succeeded",
        "failed",
    )
