"""Unit tests for recurring public-source ingestion supervision."""

from __future__ import annotations

import subprocess

import pytest

from scripts.ops.run_public_ingestion_worker import build_ingestion_command, run_worker


def test_build_ingestion_command_preserves_source_boundaries() -> None:
    command = build_ingestion_command(["ecb", "entsog-capacity"], 500)

    assert command[-3:] == ["--limit", "500", "--json"]
    assert command.count("--source") == 2
    assert "ecb" in command
    assert "entsog-capacity" in command
    assert not any("password" in argument.lower() for argument in command)


def test_build_ingestion_command_forwards_canonical_entsog_scope_only() -> None:
    command = build_ingestion_command(
        ["ecb", "entsog", "entsog-capacity"],
        500,
        entsog_point_directions=["B-EXIT", "a-entry,a-EXIT", "b-exit"],
    )

    point_directions = [
        command[index + 1]
        for index, argument in enumerate(command)
        if argument == "--entsog-point-direction"
    ]
    assert point_directions == ["a-entry", "a-exit", "b-exit"]
    assert command[-3:] == ["--limit", "500", "--json"]


def test_build_ingestion_command_does_not_forward_scope_to_non_entsog_sources() -> None:
    command = build_ingestion_command(
        ["ecb"],
        10,
        entsog_point_directions=["de-tso-0009itp-00126entry"],
    )

    assert "--entsog-point-direction" not in command


def test_worker_retries_same_frozen_window_and_point_scope() -> None:
    return_codes = iter([1, 0])
    calls: list[list[str]] = []

    def runner(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(command, next(return_codes))

    result = run_worker(
        sources=["entsog"],
        limit=20,
        interval_seconds=60,
        max_iterations=1,
        entsog_from="2026-10-10",
        entsog_to="2026-10-11",
        entsog_point_directions=["B-EXIT", "a-entry"],
        retry_max=1,
        retry_backoff_seconds=5,
        runner=runner,
        sleeper=lambda _: None,
    )

    assert result == 0
    assert len(calls) == 2
    assert calls[0] == calls[1]
    command = calls[0]
    assert [
        command[index + 1]
        for index, argument in enumerate(command)
        if argument == "--entsog-point-direction"
    ] == ["a-entry", "b-exit"]
    assert command[command.index("--entsog-from") + 1] == "2026-10-10"
    assert command[command.index("--entsog-to") + 1] == "2026-10-11"


def test_invalid_worker_point_scope_refuses_before_runner() -> None:
    calls: list[list[str]] = []

    def runner(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(command, 0)

    with pytest.raises(ValueError, match="must end with 'entry' or 'exit'"):
        run_worker(
            sources=["entsog"],
            limit=20,
            interval_seconds=60,
            max_iterations=1,
            entsog_point_directions=["not-a-direction"],
            runner=runner,
            sleeper=lambda _: None,
        )

    assert calls == []


def test_main_rejects_invalid_point_scope_before_worker() -> None:
    from scripts.ops import run_public_ingestion_worker as worker

    with pytest.raises(SystemExit) as exc:
        worker.main(
            [
                "--source",
                "entsog",
                "--interval-seconds",
                "60",
                "--entsog-point-direction",
                "not-a-direction",
            ]
        )

    assert exc.value.code == 2


def test_worker_continues_after_failed_iteration_without_sleeping_at_end() -> None:
    return_codes = iter([1, 0])
    calls: list[list[str]] = []
    sleeps: list[float] = []

    def runner(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(command, next(return_codes))

    result = run_worker(
        sources=["ecb"],
        limit=20,
        interval_seconds=60,
        max_iterations=2,
        retry_max=0,
        runner=runner,
        sleeper=sleeps.append,
    )

    assert result == 1
    assert len(calls) == 2
    assert sleeps == [60]


def test_worker_retries_transient_failure_before_next_interval() -> None:
    return_codes = iter([1, 0])
    calls: list[list[str]] = []
    sleeps: list[float] = []

    def runner(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(command, next(return_codes))

    result = run_worker(
        sources=["ecb"],
        limit=20,
        interval_seconds=60,
        max_iterations=1,
        retry_max=1,
        retry_backoff_seconds=5,
        runner=runner,
        sleeper=sleeps.append,
    )

    assert result == 0
    assert len(calls) == 2
    assert sleeps == [5]


def test_bounded_configured_worker_exhausted_retries_exits_failure() -> None:
    calls = []
    sleeps = []

    def runner(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 1)

    result = run_worker(
        sources=["entsog"],
        limit=20,
        interval_seconds=60,
        max_iterations=1,
        entsog_from="2026-10-10",
        entsog_to="2026-10-11",
        retry_max=2,
        retry_backoff_seconds=5,
        runner=runner,
        sleeper=sleeps.append,
    )
    assert result == 1 and len(calls) == 3 and sleeps == [5, 10]


def test_bounded_partial_warning_success_still_exits_success() -> None:
    result = run_worker(
        sources=["entsog"],
        limit=20,
        interval_seconds=60,
        max_iterations=1,
        entsog_from="2026-10-10",
        entsog_to="2026-10-11",
        runner=lambda command, **kwargs: subprocess.CompletedProcess(
            command,
            0,
            stdout='{"ok":true,"sources":{"ENTSOG":{"status":"SUCCEEDED_WITH_WARNINGS"}}}',
        ),
    )
    assert result == 0
