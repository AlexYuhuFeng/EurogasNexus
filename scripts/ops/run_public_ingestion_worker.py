"""Run the existing public-source ingestor on an explicit recurring cadence."""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from pathlib import Path

from eurogas_nexus.application.source_operations import (
    SourceOperationPolicy,
    run_with_retry,
)

INGEST_SCRIPT = Path(__file__).with_name("ingest_public_sources.py")


def build_ingestion_command(sources: Sequence[str], limit: int) -> list[str]:
    """Build a bounded child command without embedding credentials."""

    command = [sys.executable, str(INGEST_SCRIPT)]
    for source in sources:
        command.extend(["--source", source])
    command.extend(["--limit", str(limit), "--json"])
    return command


def run_worker(
    *,
    sources: Sequence[str],
    limit: int,
    interval_seconds: int,
    max_iterations: int | None = None,
    retry_max: int = 3,
    retry_backoff_seconds: float = 30.0,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    sleeper: Callable[[float], None] = time.sleep,
) -> int:
    """Run ingestion repeatedly; source failures do not terminate supervision."""

    command = build_ingestion_command(sources, limit)
    policy = SourceOperationPolicy(
        source_system="public-sources",
        retry_max=max(0, retry_max),
        retry_backoff_seconds=max(0.0, retry_backoff_seconds),
    )
    iteration = 0
    while max_iterations is None or iteration < max_iterations:
        result = run_with_retry(
            "public-sources",
            lambda: runner(command, check=False, text=True),
            is_success=lambda completed: completed.returncode == 0,
            policy=policy,
            sleeper=sleeper,
        )
        iteration += 1
        if not result.succeeded:
            print(
                "Public ingestion iteration failed after "
                f"{result.attempts} attempt(s): {result.last_error_type}; "
                "inspect Source Center and ingestion_runs."
            )
        if max_iterations is not None and iteration >= max_iterations:
            break
        sleeper(interval_seconds)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """    Run the public ingestion worker loop."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", action="append", required=True)
    parser.add_argument("--limit", type=int, default=10_000)
    parser.add_argument("--interval-seconds", type=int, required=True)
    parser.add_argument("--max-iterations", type=int)
    parser.add_argument("--retry-max", type=int, default=3)
    parser.add_argument("--retry-backoff-seconds", type=float, default=30.0)
    args = parser.parse_args(argv)
    if args.interval_seconds < 60:
        parser.error("--interval-seconds must be at least 60")
    return run_worker(
        sources=args.source,
        limit=args.limit,
        interval_seconds=args.interval_seconds,
        max_iterations=args.max_iterations,
        retry_max=args.retry_max,
        retry_backoff_seconds=args.retry_backoff_seconds,
    )


if __name__ == "__main__":
    raise SystemExit(main())
