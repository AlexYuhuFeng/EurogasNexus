"""A declared dataset split must be validated and reported, not silently ignored.

Why this test exists
--------------------
`DatasetSpec.split_specs` was declared and never read anywhere in the codebase: no
validation, no effect on a build, and nothing in the API response. A time-series engineer
could name a training window and a held-back window, receive HTTP 200, and get a dataset in
which the holdout was not held back at all -- and no field said so. For someone building a
model that is worse than having no split control, because the specification looks like it
is in force.

What is checked here is the narrow thing that can be enforced honestly:

  - a split must lie inside the dataset period, and must not be inverted;
  - splits must not overlap, because an overlapping holdout is by definition not held back;
  - the build reports how many rows each split covers and how many belong to none, so a
    declaration that selects nothing is visible rather than assumed.

The engine still does not impose a training policy -- leakage control stays the caller's
responsibility and is reported through `leakage_issues`. This test does not claim
otherwise.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from eurogas_nexus.domain.research.datasets import (
    DatasetBuildResult,
    DatasetSpec,
    DatasetSplit,
)

START = datetime(2026, 1, 1, tzinfo=UTC)
END = datetime(2026, 4, 1, tzinfo=UTC)


def _spec(**overrides) -> DatasetSpec:
    payload = {
        "dataset_spec_id": "spec-splits",
        "name": "Split fixture",
        "description": "Exercises split validation.",
        "target_ids": ["target-1"],
        "start": START,
        "end": END,
    }
    payload.update(overrides)
    return DatasetSpec(**payload)


def test_a_spec_with_no_splits_is_still_valid() -> None:
    """The common case must not become harder."""

    assert _spec().split_specs == []


def test_a_well_formed_split_is_accepted() -> None:
    spec = _spec(
        split_specs=[
            DatasetSplit(name="train", start=START, end=datetime(2026, 3, 1, tzinfo=UTC)),
            DatasetSplit(
                name="holdout",
                start=datetime(2026, 3, 1, tzinfo=UTC),
                end=END,
            ),
        ]
    )
    assert [split.name for split in spec.split_specs] == ["train", "holdout"]


def test_a_split_outside_the_dataset_period_is_refused() -> None:
    """A split the build can never reach must not be accepted in silence."""

    with pytest.raises(ValidationError) as excinfo:
        _spec(
            split_specs=[
                DatasetSplit(
                    name="holdout",
                    start=datetime(2026, 6, 1, tzinfo=UTC),
                    end=datetime(2026, 7, 1, tzinfo=UTC),
                )
            ]
        )
    message = str(excinfo.value)
    assert "outside the dataset period" in message
    assert "holdout" in message


def test_an_inverted_split_is_refused() -> None:
    with pytest.raises(ValidationError) as excinfo:
        _spec(
            split_specs=[
                DatasetSplit(
                    name="backwards",
                    start=datetime(2026, 3, 1, tzinfo=UTC),
                    end=datetime(2026, 2, 1, tzinfo=UTC),
                )
            ]
        )
    assert "end must be after start" in str(excinfo.value)


def test_overlapping_splits_are_refused() -> None:
    """The ordinary way a holdout stops being held back."""

    with pytest.raises(ValidationError) as excinfo:
        _spec(
            split_specs=[
                DatasetSplit(name="train", start=START, end=datetime(2026, 3, 1, tzinfo=UTC)),
                DatasetSplit(
                    name="holdout",
                    start=datetime(2026, 2, 1, tzinfo=UTC),
                    end=END,
                ),
            ]
        )
    message = str(excinfo.value)
    assert "overlaps" in message
    assert "train" in message and "holdout" in message


def test_a_negative_embargo_is_refused() -> None:
    with pytest.raises(ValidationError) as excinfo:
        _spec(
            split_specs=[
                DatasetSplit(
                    name="train",
                    start=START,
                    end=datetime(2026, 3, 1, tzinfo=UTC),
                    embargo_before=timedelta(days=-1),
                )
            ]
        )
    assert "non-negative" in str(excinfo.value)


def _result(spec: DatasetSpec, rows: list[dict]) -> DatasetBuildResult:
    return DatasetBuildResult(
        dataset_snapshot_id="dataset-snapshot-fixture",
        spec=spec,
        rows=rows,
        columns=["observed_at"],
        quality_report={"coverage": 1.0, "temporal_integrity": "EXACT"},
        leakage_issues=[],
        lineage=[],
        content_hash="0" * 64,
    )


def test_the_build_reports_how_many_rows_each_split_covers() -> None:
    """The property that makes a declaration verifiable instead of assumed."""

    spec = _spec(
        split_specs=[
            DatasetSplit(name="train", start=START, end=datetime(2026, 3, 1, tzinfo=UTC)),
            DatasetSplit(name="holdout", start=datetime(2026, 3, 1, tzinfo=UTC), end=END),
        ]
    )
    rows = [
        {"observed_at": datetime(2026, 1, 15, tzinfo=UTC).isoformat()},
        {"observed_at": datetime(2026, 2, 15, tzinfo=UTC).isoformat()},
        {"observed_at": datetime(2026, 3, 15, tzinfo=UTC).isoformat()},
    ]

    coverage = {entry["name"]: entry["row_count"] for entry in _result(spec, rows).split_coverage()}

    assert coverage["train"] == 2
    assert coverage["holdout"] == 1
    assert coverage["(unassigned)"] == 0


def test_a_split_that_selects_nothing_is_visible_as_zero() -> None:
    """A holdout covering no rows is the failure a caller most needs to see."""

    spec = _spec(
        split_specs=[
            DatasetSplit(
                name="holdout",
                start=datetime(2026, 3, 1, tzinfo=UTC),
                end=datetime(2026, 3, 15, tzinfo=UTC),
            )
        ]
    )
    rows = [{"observed_at": datetime(2026, 1, 15, tzinfo=UTC).isoformat()}]

    coverage = {entry["name"]: entry["row_count"] for entry in _result(spec, rows).split_coverage()}

    assert coverage["holdout"] == 0, "a holdout over no rows must report zero, not be omitted"
    assert coverage["(unassigned)"] == 1


def test_rows_outside_every_split_are_counted_separately() -> None:
    spec = _spec(
        split_specs=[
            DatasetSplit(
                name="train",
                start=datetime(2026, 1, 1, tzinfo=UTC),
                end=datetime(2026, 1, 10, tzinfo=UTC),
            )
        ]
    )
    rows = [
        {"observed_at": datetime(2026, 1, 5, tzinfo=UTC).isoformat()},
        {"observed_at": datetime(2026, 2, 5, tzinfo=UTC).isoformat()},
        {"observed_at": datetime(2026, 2, 6, tzinfo=UTC).isoformat()},
    ]

    coverage = {entry["name"]: entry["row_count"] for entry in _result(spec, rows).split_coverage()}

    assert coverage["train"] == 1
    assert coverage["(unassigned)"] == 2


def test_no_splits_means_no_coverage_report() -> None:
    """A dataset with no declared split must not gain an empty report."""

    assert _result(_spec(), [{"observed_at": START.isoformat()}]).split_coverage() == []


def test_the_snapshot_metadata_carries_the_split_coverage() -> None:
    """The report must reach the persisted metadata, or a caller cannot see it."""

    spec = _spec(
        split_specs=[
            DatasetSplit(name="train", start=START, end=datetime(2026, 3, 1, tzinfo=UTC))
        ]
    )
    metadata = _result(spec, [{"observed_at": START.isoformat()}]).as_metadata()

    assert "split_coverage" in metadata, (
        "the split coverage is not in the snapshot metadata, so a caller has no way to "
        "check whether the split it declared selected anything"
    )
    assert metadata["split_coverage"][0]["name"] == "train"
    assert metadata["split_coverage"][0]["row_count"] == 1
