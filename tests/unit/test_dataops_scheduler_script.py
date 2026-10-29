"""CR-09 scheduler script tests (no live provider calls)."""

from __future__ import annotations

import json
import subprocess
from types import SimpleNamespace

import pytest

from eurogas_nexus.domain.dataops.contracts import FailureCategory
from scripts.ops.run_dataops_scheduler import (
    _SOURCE_ARGS,
    run_ingestor_attempt,
    run_loop,
)


def test_scheduler_maps_only_implemented_public_sources() -> None:
    assert set(_SOURCE_ARGS) == {"src-ecb", "src-entsog", "src-gie"}
    assert _SOURCE_ARGS["src-ecb"] == ("ecb",)


def test_ingestor_attempt_parses_success_report() -> None:
    def fake_runner(command, **kwargs):
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"ok": True, "sources": {"ECB": {"records": 12}}}),
            stderr="",
        )

    attempt = run_ingestor_attempt(fake_runner)
    result = attempt({"source_id": "src-ecb", "run_id": "run-1"}, 1)

    assert result.succeeded is True
    assert result.rows_received == 12
    assert result.lineage_refs == ["public-source-ingestor:src-ecb"]


def test_ingestor_attempt_classifies_unsupported_source_as_configuration() -> None:
    attempt = run_ingestor_attempt(subprocess.run)
    result = attempt({"source_id": "src-platts", "run_id": "run-1"}, 1)

    assert result.succeeded is False
    assert result.classification == FailureCategory.CONFIGURATION


def test_ingestor_attempt_classifies_bad_json_as_bad_response() -> None:
    def fake_runner(command, **kwargs):
        return SimpleNamespace(returncode=0, stdout="not-json", stderr="")

    result = run_ingestor_attempt(fake_runner)({"source_id": "src-ecb", "run_id": "run-1"}, 1)

    assert result.succeeded is False
    assert result.classification == FailureCategory.BAD_RESPONSE


def test_run_loop_blocks_without_database(monkeypatch, capsys) -> None:
    monkeypatch.delenv("RUNTIME_STORE_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)

    result = run_loop(
        interval_seconds=1,
        max_iterations=1,
        emit=lambda value: None,
    )

    assert result == 2
    captured = capsys.readouterr()
    assert "database_url_missing" not in captured.out  # emit was suppressed


def test_entsog_missing_window_is_configuration_failure_before_subprocess():
    attempt = run_ingestor_attempt(
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("Unbounded ENTSOG subprocess"))
    )
    result = attempt({"source_id": "src-entsog", "run_id": "run-one"}, 1)
    assert not result.succeeded and result.classification == FailureCategory.CONFIGURATION
    assert "entsog_window_required" in result.error_message


@pytest.mark.parametrize(
    "report",
    [
        [],
        {"ok": True, "sources": []},
        {"ok": True, "sources": {}},
        {"ok": False, "sources": {"ECB": {"records": 1}}},
        {"ok": True, "sources": {"ECB": None}},
        {"ok": True, "sources": {"ECB": {"records": True}}},
        {"ok": True, "sources": {"ECB": {"records": -1}}},
        {"ok": True, "sources": {"ECB": {"records": "1"}}},
    ],
)
def test_scheduler_refuses_invalid_report_shapes_and_counters(report):
    result = run_ingestor_attempt(
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout=json.dumps(report), stderr="")
    )({"source_id": "src-ecb"}, 1)
    assert not result.succeeded and result.classification == FailureCategory.BAD_RESPONSE


def test_entsog_window_pass_through_preserves_partial_warning_and_actual_counts():
    commands = []

    def runner(command, **kwargs):
        commands.append(command)
        return SimpleNamespace(
            returncode=0,
            stderr="",
            stdout=json.dumps(
                {
                    "ok": True,
                    "sources": {
                        "ENTSOG": {
                            "records": 3,
                            "received_records": 4,
                            "skipped_records": 1,
                            "inserted": 1,
                            "unchanged": 2,
                            "complete": False,
                            "status": "SUCCEEDED_WITH_WARNINGS",
                        }
                    },
                }
            ),
        )

    result = run_ingestor_attempt(runner, entsog_from="2026-10-10", entsog_to="2026-10-11")(
        {"source_id": "src-entsog"}, 1
    )
    command = commands[0]
    assert command[command.index("--entsog-from") + 1] == "2026-10-10"
    assert command[command.index("--entsog-to") + 1] == "2026-10-11"
    assert result.succeeded and result.rows_received == 4 and result.rows_accepted == 3
    assert result.rows_rejected == 1 and result.rows_inserted == 1 and result.duplicate_count == 2
    assert result.quality_issues[0].quality_code == "entsog_bounded_partial"


def test_ingestor_attempt_forwards_canonical_point_scope_only_to_entsog():
    commands = []

    def runner(command, **kwargs):
        commands.append(command)
        return SimpleNamespace(
            returncode=0,
            stderr="",
            stdout=json.dumps({"ok": True, "sources": {"ENTSOG": {"records": 1}}}),
        )

    attempt = run_ingestor_attempt(
        runner,
        entsog_from="2026-10-10",
        entsog_to="2026-10-11",
        entsog_point_directions=["B-EXIT", "a-entry,a-EXIT"],
    )
    assert attempt({"source_id": "src-entsog", "run_id": "run-one"}, 1).succeeded is True
    command = commands[0]
    assert [
        command[index + 1]
        for index, argument in enumerate(command)
        if argument == "--entsog-point-direction"
    ] == ["a-entry", "a-exit", "b-exit"]
    assert command[command.index("--entsog-from") + 1] == "2026-10-10"
    assert command[command.index("--entsog-to") + 1] == "2026-10-11"

    ecb_attempt = run_ingestor_attempt(runner, entsog_point_directions=["c-entry"])
    ecb_result = ecb_attempt({"source_id": "src-ecb", "run_id": "run-two"}, 1)
    assert ecb_result.succeeded is True
    assert "--entsog-point-direction" not in commands[-1]


def test_invalid_point_scope_refuses_before_runner_factory_runs():
    commands = []

    def runner(command, **kwargs):
        commands.append(command)
        return SimpleNamespace(returncode=0, stdout="{}", stderr="")

    with pytest.raises(ValueError, match="must end with 'entry' or 'exit'"):
        run_ingestor_attempt(runner, entsog_point_directions=["not-a-direction"])

    assert commands == []


def test_run_loop_passes_canonical_point_scope_to_attempt_factory(monkeypatch):
    from contextlib import nullcontext

    from scripts.ops import run_dataops_scheduler as scheduler

    monkeypatch.setattr(scheduler, "resolve_database_url", lambda: "configured")
    monkeypatch.setattr(
        scheduler,
        "get_session_factory",
        lambda: lambda: nullcontext(SimpleNamespace(commit=lambda: None)),
    )
    monkeypatch.setattr(scheduler, "scan_scheduler", lambda *args, **kwargs: {})
    monkeypatch.setattr(
        scheduler,
        "execute_claimed_runs",
        lambda *args, **kwargs: {"outcomes": []},
    )
    captured = {}

    def fake_factory(runner, **kwargs):
        captured.update(kwargs)
        return lambda payload, attempt: None

    monkeypatch.setattr(scheduler, "run_ingestor_attempt", fake_factory)
    result = scheduler.run_loop(
        interval_seconds=60,
        max_iterations=1,
        emit=lambda value: None,
        entsog_from="2026-10-10",
        entsog_to="2026-10-11",
        entsog_point_directions=["B-EXIT", "a-entry,a-EXIT"],
    )

    assert result == 0
    assert captured["entsog_point_directions"] == ("a-entry", "a-exit", "b-exit")


def test_main_rejects_invalid_point_scope_before_run_loop(monkeypatch):
    from scripts.ops import run_dataops_scheduler as scheduler

    monkeypatch.setattr(
        scheduler,
        "run_loop",
        lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("run loop must not start with invalid point scope")
        ),
    )
    with pytest.raises(SystemExit) as exc:
        scheduler.main(["--once", "--entsog-point-direction", "not-a-direction"])

    assert exc.value.code == 2


def test_scheduler_loop_does_not_label_failed_configuration_as_ok(monkeypatch):
    from contextlib import nullcontext

    from scripts.ops import run_dataops_scheduler as scheduler

    monkeypatch.setattr(scheduler, "resolve_database_url", lambda: "configured")
    monkeypatch.setattr(
        scheduler,
        "get_session_factory",
        lambda: lambda: nullcontext(SimpleNamespace(commit=lambda: None)),
    )
    monkeypatch.setattr(scheduler, "scan_scheduler", lambda *args, **kwargs: {})
    monkeypatch.setattr(
        scheduler,
        "execute_claimed_runs",
        lambda *args, **kwargs: {
            "outcomes": [
                {"source_id": "src-entsog", "status": "FAILED", "error_category": "CONFIGURATION"}
            ]
        },
    )
    reports = []
    assert scheduler.run_loop(interval_seconds=60, max_iterations=1, emit=reports.append) == 2
    assert json.loads(reports[0])["status"] == "degraded"
    assert json.loads(reports[0])["configuration_blocks"] == {
        "src-entsog": "entsog_window_required"
    }
