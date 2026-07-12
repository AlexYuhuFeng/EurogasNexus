"""Unit tests for recurring public-source ingestion supervision."""

from __future__ import annotations

import subprocess

from scripts.ops.run_public_ingestion_worker import build_ingestion_command, run_worker


def test_build_ingestion_command_preserves_source_boundaries() -> None:
    command = build_ingestion_command(["ecb", "entsog-capacity"], 500)

    assert command[-3:] == ["--limit", "500", "--json"]
    assert command.count("--source") == 2
    assert "ecb" in command
    assert "entsog-capacity" in command
    assert not any("password" in argument.lower() for argument in command)


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
        runner=runner,
        sleeper=sleeps.append,
    )

    assert result == 0
    assert len(calls) == 2
    assert sleeps == [60]
