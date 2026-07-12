"""Run the existing public-source ingestor on an explicit recurring cadence."""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from pathlib import Path

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
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    sleeper: Callable[[float], None] = time.sleep,
) -> int:
    """Run ingestion repeatedly; source failures do not terminate supervision."""

    command = build_ingestion_command(sources, limit)
    iteration = 0
    while max_iterations is None or iteration < max_iterations:
        completed = runner(command, check=False, text=True)
        iteration += 1
        if completed.returncode != 0:
            print(
                "Public ingestion iteration failed; inspect Source Center and ingestion_runs."
            )
        if max_iterations is not None and iteration >= max_iterations:
            break
        sleeper(interval_seconds)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", action="append", required=True)
    parser.add_argument("--limit", type=int, default=10_000)
    parser.add_argument("--interval-seconds", type=int, required=True)
    parser.add_argument("--max-iterations", type=int)
    args = parser.parse_args(argv)
    if args.interval_seconds < 60:
        parser.error("--interval-seconds must be at least 60")
    return run_worker(
        sources=args.source,
        limit=args.limit,
        interval_seconds=args.interval_seconds,
        max_iterations=args.max_iterations,
    )


if __name__ == "__main__":
    raise SystemExit(main())
