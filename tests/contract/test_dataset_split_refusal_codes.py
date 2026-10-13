"""A rejected split specification must name the split problem, not a generic field.

Why this test exists
--------------------
`_dataset_spec_error` maps each `DatasetSpec` validation failure to a stable code and a
localised message. When split validation was added, every split fault fell through to the
`dataset_field_invalid` branch whose message is "The dataset specification contains an
invalid field" -- the same class of unhelpful refusal this round set out to remove. A
caller who mixed up a holdout window would be told that some field is invalid and would
have to guess which.

The order of the branches matters and is asserted here: split messages contain the words
"end must be after start" and name dates, so a later branch would classify a split fault as
a top-level one.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from pydantic import ValidationError

from eurogas_nexus.api.routes.public.research_data import _dataset_spec_error
from eurogas_nexus.domain.research.datasets import DatasetSpec, DatasetSplit

START = datetime(2026, 1, 1, tzinfo=UTC)
END = datetime(2026, 4, 1, tzinfo=UTC)


def _error_for(**overrides) -> dict:
    payload = {
        "dataset_spec_id": "spec-split-error",
        "name": "Split error fixture",
        "description": "Exercises the refusal mapping.",
        "target_ids": ["target-1"],
        "start": START,
        "end": END,
    }
    payload.update(overrides)
    try:
        DatasetSpec(**payload)
    except ValidationError as exc:
        error = _dataset_spec_error(exc)
        return error.detail
    raise AssertionError("the specification was accepted; this fixture must be refused")


def test_an_overlapping_split_names_the_overlap() -> None:
    detail = _error_for(
        split_specs=[
            DatasetSplit(name="train", start=START, end=datetime(2026, 3, 1, tzinfo=UTC)),
            DatasetSplit(name="holdout", start=datetime(2026, 2, 1, tzinfo=UTC), end=END),
        ]
    )
    issues = detail["issues"]
    assert issues[0]["code"] == "split_overlap", f"got {issues[0]}"
    assert issues[0]["field"] == "split_specs"
    assert "overlap" in issues[0]["message"].lower()


def test_a_split_outside_the_period_names_the_period_problem() -> None:
    detail = _error_for(
        split_specs=[
            DatasetSplit(
                name="holdout",
                start=datetime(2026, 6, 1, tzinfo=UTC),
                end=datetime(2026, 7, 1, tzinfo=UTC),
            )
        ]
    )
    assert detail["issues"][0]["code"] == "split_outside_period"


def test_an_inverted_split_is_not_reported_as_a_top_level_date_error() -> None:
    """The ordering trap: this message also contains "end must be after start"."""

    detail = _error_for(
        split_specs=[
            DatasetSplit(
                name="backwards",
                start=datetime(2026, 3, 1, tzinfo=UTC),
                end=datetime(2026, 2, 1, tzinfo=UTC),
            )
        ]
    )
    issue = detail["issues"][0]
    assert issue["code"] == "split_bounds_invalid", (
        f"a split fault was classified as {issue['code']!r}; the branch order lets a "
        "top-level date branch capture it"
    )
    assert issue["field"] == "split_specs"


def test_a_negative_embargo_is_reported() -> None:
    detail = _error_for(
        split_specs=[
            DatasetSplit(
                name="train",
                start=START,
                end=datetime(2026, 3, 1, tzinfo=UTC),
                embargo_before=timedelta(days=-1),
            )
        ]
    )
    assert detail["issues"][0]["code"] == "split_embargo_invalid"


def test_top_level_date_errors_are_still_classified_as_before() -> None:
    """The split branches must not capture an ordinary inverted period."""

    detail = _error_for(start=END, end=START)
    assert detail["issues"][0]["code"] == "date_bounds_invalid"
    assert detail["issues"][0]["field"] == "start/end"


def test_every_refusal_carries_at_least_one_issue() -> None:
    """An empty issues list is what renders as an empty panel in the client."""

    for overrides in (
        {
            "split_specs": [
                DatasetSplit(name="a", start=START, end=datetime(2026, 3, 1, tzinfo=UTC)),
                DatasetSplit(name="b", start=datetime(2026, 2, 1, tzinfo=UTC), end=END),
            ]
        },
        {"start": END, "end": START},
        {"history_lookback": timedelta(days=-1)},
    ):
        detail = _error_for(**overrides)
        assert detail["issues"], f"a refusal carried no issues for {overrides}"
        for issue in detail["issues"]:
            assert issue["field"] and issue["code"] and issue["message"]
