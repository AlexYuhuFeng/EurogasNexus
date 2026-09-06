"""Repository serializer tests for persisted strategy history fields."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

from eurogas_nexus.db.models import StrategyRunRecord
from eurogas_nexus.db.repositories.strategy import strategy_run_payload


def _run(
    *,
    result_snapshot: dict,
    input_snapshot: dict | None = None,
    started_at_utc: datetime | None = None,
    finished_at_utc: datetime | None = None,
) -> StrategyRunRecord:
    return StrategyRunRecord(
        run_id="run-1",
        strategy_id="sap-icis-ocm",
        run_mode="SHADOW_RUN",
        status="SUCCESS",
        started_at_utc=started_at_utc or datetime(2026, 7, 22, 10, 0, 0, tzinfo=UTC),
        finished_at_utc=finished_at_utc,
        input_snapshot=(
            {"strategy_name": "Input Snapshot Name"}
            if input_snapshot is None
            else input_snapshot
        ),
        result_snapshot=result_snapshot,
        source_refs=["fixture:source-a", "fixture:source-b"],
        warnings=["WARNING_SAMPLE"],
        missing_inputs=["MISSING_SAMPLE"],
        research_only=True,
        human_review_required=True,
    )


def test_strategy_run_payload_preserves_snapshot_price_basis_and_review_fields() -> None:
    run = _run(
        result_snapshot={
            "strategy_name": "Persisted Strategy Name",
            "paper_pnl_gbp": 123.5,
            "cumulative_pnl_gbp": 456.0,
            "hit": True,
            "weighted_score": 0.5,
            "day_ahead_average_gbp_mwh": 0.0,
            "intraday_average_gbp_mwh": -2.25,
            "intraday_vs_day_ahead_spread_gbp_mwh": -2.25,
            "candidate_action_for_review": "REVIEW_HIGHER_DAY_AHEAD_ALLOCATION",
            "allocation_targets": [
                {
                    "market_bucket": "DAY_AHEAD",
                    "target_allocation_pct": 40.0,
                    "target_quantity_mwh_per_day": 4000.0,
                    "reference_price_gbp_mwh": -2.25,
                    "expected_margin_gbp_mwh": -1.0,
                    "rationale": ["fixture"],
                }
            ],
        }
    )

    payload = strategy_run_payload(run)

    assert payload["strategy_name"] == "Persisted Strategy Name"
    assert payload["day_ahead_average_gbp_mwh"] == 0.0
    assert payload["intraday_average_gbp_mwh"] == -2.25
    assert payload["intraday_vs_day_ahead_spread_gbp_mwh"] == -2.25
    assert payload["candidate_action_for_review"] == "REVIEW_HIGHER_DAY_AHEAD_ALLOCATION"
    assert payload["source_refs"] == ["fixture:source-a", "fixture:source-b"]
    assert payload["warnings"] == ["WARNING_SAMPLE"]
    assert payload["missing_inputs"] == ["MISSING_SAMPLE"]
    assert payload["research_only"] is True
    assert payload["human_review_required"] is True


def test_strategy_run_payload_preserves_zero_spread() -> None:
    payload = strategy_run_payload(
        _run(
            result_snapshot={
                "day_ahead_average_gbp_mwh": 30.0,
                "intraday_average_gbp_mwh": 30.0,
                "intraday_vs_day_ahead_spread_gbp_mwh": 0.0,
            }
        )
    )

    assert payload["day_ahead_average_gbp_mwh"] == 30.0
    assert payload["intraday_average_gbp_mwh"] == 30.0
    assert payload["intraday_vs_day_ahead_spread_gbp_mwh"] == 0.0


def test_legacy_run_returns_null_for_missing_history_fields_and_input_name_fallback() -> None:
    run = _run(
        input_snapshot={"strategy_name": "Input Snapshot Name"},
        result_snapshot={
            "paper_pnl_gbp": 10.0,
            "cumulative_pnl_gbp": 10.0,
            "hit": False,
            "weighted_score": 0.0,
        },
    )

    payload = strategy_run_payload(run)

    assert payload["strategy_name"] == "Input Snapshot Name"
    assert payload["day_ahead_average_gbp_mwh"] is None
    assert payload["intraday_average_gbp_mwh"] is None
    assert payload["intraday_vs_day_ahead_spread_gbp_mwh"] is None
    assert payload["candidate_action_for_review"] is None


def test_null_result_strategy_name_falls_back_to_input_snapshot() -> None:
    payload = strategy_run_payload(
        _run(
            input_snapshot={"strategy_name": "Input Snapshot Name"},
            result_snapshot={"strategy_name": None},
        )
    )

    assert payload["strategy_name"] == "Input Snapshot Name"


def test_empty_string_result_strategy_name_is_preserved() -> None:
    payload = strategy_run_payload(
        _run(
            input_snapshot={"strategy_name": "Input Snapshot Name"},
            result_snapshot={"strategy_name": ""},
        )
    )

    assert payload["strategy_name"] == ""


def test_missing_strategy_name_in_both_snapshots_returns_null() -> None:
    payload = strategy_run_payload(
        _run(
            input_snapshot={},
            result_snapshot={},
        )
    )

    assert payload["strategy_name"] is None


def test_strategy_run_payload_serializes_utc_timestamps() -> None:
    start = datetime(2026, 7, 22, 9, 30, 0, tzinfo=UTC)
    finish = start + timedelta(minutes=2)
    payload = strategy_run_payload(
        _run(
            result_snapshot={"strategy_name": "Name"},
            started_at_utc=start,
            finished_at_utc=finish,
        )
    )

    assert payload["started_at_utc"] == "2026-07-22T09:30:00+00:00"
    assert payload["finished_at_utc"] == "2026-07-22T09:32:00+00:00"


def test_strategy_run_payload_handles_naive_utc_timestamps() -> None:
    start = datetime(2026, 7, 22, 9, 30, 0)
    payload = strategy_run_payload(
        _run(
            result_snapshot={},
            input_snapshot={},
            started_at_utc=start,
        )
    )

    assert payload["started_at_utc"] == "2026-07-22T09:30:00+00:00"
    assert payload["strategy_name"] is None


def test_strategy_run_payload_converts_non_utc_timestamps_to_utc() -> None:
    start = datetime(2026, 7, 22, 11, 30, 0, tzinfo=timezone(timedelta(hours=2)))
    payload = strategy_run_payload(
        _run(
            result_snapshot={"strategy_name": "Name"},
            started_at_utc=start,
        )
    )

    assert payload["started_at_utc"] == "2026-07-22T09:30:00+00:00"
