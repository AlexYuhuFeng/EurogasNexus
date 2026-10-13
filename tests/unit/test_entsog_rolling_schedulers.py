"""Frozen retry/replay policy through real script entrypoints; no live ingestion."""

import json
import subprocess
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from eurogas_nexus.domain.dataops.contracts import FailureCategory
from eurogas_nexus.ingestion.entsog_transport import EntsogWindowError
from scripts.ops import run_dataops_scheduler as scheduler
from scripts.ops import run_public_ingestion_worker as worker


def _success(complete=True):
    return SimpleNamespace(
        returncode=0,
        stderr="",
        stdout=json.dumps(
            {
                "ok": True,
                "sources": {
                    "ENTSOG": {
                        "records": 2,
                        "received_records": 2,
                        "inserted": 1,
                        "unchanged": 1,
                        "complete": complete,
                    }
                },
            }
        ),
    )


def test_worker_freezes_policy_across_retry_then_rolls_at_exact_gas_day_boundary(capsys):
    anchors = iter([datetime(2026, 1, 2, 4, 59, tzinfo=UTC), datetime(2026, 1, 2, 5, tzinfo=UTC)])
    codes = iter([1, 0, 0])
    commands = []

    def run(command, **kwargs):
        commands.append(command)
        return subprocess.CompletedProcess(command, next(codes))

    assert (
        worker.run_worker(
            sources=["entsog"],
            limit=20,
            interval_seconds=60,
            max_iterations=2,
            entsog_lookback_gas_days=2,
            clock=lambda: next(anchors),
            retry_max=1,
            runner=run,
            sleeper=lambda seconds: None,
        )
        == 0
    )
    assert commands[0] == commands[1] and commands[1] != commands[2]
    assert "--entsog-from" not in commands[0]
    assert commands[0][commands[0].index("--entsog-window-anchor") + 1].startswith(
        "2026-01-02T04:59"
    )
    windows = [json.loads(line)["window"] for line in capsys.readouterr().out.splitlines()]
    assert windows[0]["from"] == "2025-12-30" and windows[1]["from"] == "2025-12-31"
    assert windows[0]["open_gas_day_at_anchor"] == "2026-01-01"


@pytest.mark.parametrize("anchor", [None, "bad", "2026-01-02T05:00:00", False])
def test_scheduler_refuses_missing_or_invalid_persisted_anchor(anchor):
    result = scheduler.run_ingestor_attempt(
        lambda *args, **kwargs: pytest.fail("Invalid rolling subprocess"),
        entsog_lookback_gas_days=2,
    )({"source_id": "src-entsog", "scheduled_for_utc": anchor}, 1)
    assert not result.succeeded and result.classification == FailureCategory.CONFIGURATION
    assert "entsog_window_anchor_invalid" in result.error_message


def test_scheduler_missing_anchor_is_refused_without_implicit_clock():
    result = scheduler.run_ingestor_attempt(
        lambda *args, **kwargs: pytest.fail("Missing anchor subprocess"),
        entsog_lookback_gas_days=2,
    )({"source_id": "src-entsog", "run_id": "missing"}, 1)
    assert not result.succeeded and "entsog_window_anchor_invalid" in result.error_message


@pytest.mark.parametrize("complete", [True, False])
def test_persisted_scheduler_anchor_replays_identically_after_new_runner_and_keeps_warnings(
    complete,
):
    commands = []
    payload = {
        "source_id": "src-entsog",
        "run_id": "persisted-run",
        "scheduled_for_utc": "2026-07-02T03:59:59+00:00",
    }

    def run(command, **kwargs):
        commands.append(command)
        return _success(complete)

    first = scheduler.run_ingestor_attempt(run, entsog_lookback_gas_days=2)(payload, 1)
    second = scheduler.run_ingestor_attempt(run, entsog_lookback_gas_days=2)(payload, 2)
    assert first.succeeded and second.succeeded and commands[0] == commands[1]
    assert first.lineage_refs == second.lineage_refs
    assert any("anchor=2026-07-02T03:59:59" in ref for ref in first.lineage_refs)
    codes = {issue.quality_code for issue in first.quality_issues}
    assert "entsog_open_gas_day" in codes
    assert ("entsog_bounded_partial" in codes) is (not complete)


def test_both_entrypoints_pass_opt_in_policy(monkeypatch):
    calls = []
    monkeypatch.setattr(worker, "run_worker", lambda **kwargs: calls.append(kwargs) or 0)
    monkeypatch.setattr(scheduler, "run_loop", lambda **kwargs: calls.append(kwargs) or 0)
    assert (
        worker.main(
            ["--source", "entsog", "--interval-seconds", "60", "--entsog-lookback-gas-days", "2"]
        )
        == 0
    )
    assert scheduler.main(["--once", "--entsog-lookback-gas-days", "3"]) == 0
    assert [call["entsog_lookback_gas_days"] for call in calls] == [2, 3]


def test_worker_mixed_policy_refuses_before_clock_or_child():
    with pytest.raises(EntsogWindowError):
        worker.run_worker(
            sources=["entsog"],
            limit=20,
            interval_seconds=60,
            max_iterations=1,
            entsog_from="2026-01-01",
            entsog_to="2026-01-02",
            entsog_lookback_gas_days=2,
            clock=lambda: pytest.fail("Mixed policy clock"),
            runner=lambda *args, **kwargs: pytest.fail("Mixed policy subprocess"),
        )


def test_scheduler_revision_refusal_is_actionable_and_not_retryable():
    report = {"ok": False, "failures": [{"code": "entsog_revision_requires_history"}]}
    result = scheduler.run_ingestor_attempt(
        lambda *args, **kwargs: SimpleNamespace(returncode=1, stderr="", stdout=json.dumps(report)),
        entsog_lookback_gas_days=2,
    )({"source_id": "src-entsog", "scheduled_for_utc": "2026-01-02T05:00:00+00:00"}, 1)
    assert not result.succeeded and result.classification == FailureCategory.QUALITY_REJECTED
    assert result.quality_issues[0].quality_code == "entsog_revision_requires_history"
    assert "Review revisions" in result.quality_issues[0].message
