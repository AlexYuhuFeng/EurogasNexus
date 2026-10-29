"""Run the existing public-source ingestor on an explicit recurring cadence."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path

from eurogas_nexus.application.source_operations import (
    SourceOperationPolicy,
    run_with_retry,
)
from eurogas_nexus.ingestion.entsog_scope import validate_entsog_point_directions
from eurogas_nexus.ingestion.entsog_transport import EntsogWindowError
from eurogas_nexus.ingestion.entsog_window import EntsogWindowPolicy

INGEST_SCRIPT = Path(__file__).with_name("ingest_public_sources.py")
ENTSOG_POINT_SCOPE_SOURCES = frozenset({"all", "entsog", "entsog-capacity"})


def build_ingestion_command(
    sources: Sequence[str],
    limit: int,
    *,
    entsog_from: str | None = None,
    entsog_to: str | None = None,
    entsog_lookback_gas_days: int | None = None,
    entsog_window_anchor: str | None = None,
    entsog_point_directions: Sequence[str] = (),
) -> list[str]:
    """Build a bounded child command without embedding credentials."""

    point_directions = validate_entsog_point_directions(entsog_point_directions)
    command = [sys.executable, str(INGEST_SCRIPT)]
    for source in sources:
        command.extend(["--source", source])
    if entsog_from is not None:
        command.extend(["--entsog-from", entsog_from])
    if entsog_to is not None:
        command.extend(["--entsog-to", entsog_to])
    if entsog_lookback_gas_days is not None:
        command.extend(["--entsog-lookback-gas-days", str(entsog_lookback_gas_days)])
    if entsog_window_anchor is not None:
        command.extend(["--entsog-window-anchor", entsog_window_anchor])
    if set(sources) & ENTSOG_POINT_SCOPE_SOURCES:
        for point_direction in point_directions:
            command.extend(["--entsog-point-direction", point_direction])
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
    entsog_from: str | None = None,
    entsog_to: str | None = None,
    entsog_lookback_gas_days: int | None = None,
    entsog_point_directions: Sequence[str] = (),
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> int:
    """Run ingestion repeatedly; source failures do not terminate supervision."""

    point_directions = validate_entsog_point_directions(entsog_point_directions)
    configuration_blocked = False
    window_policy = None
    if set(sources) & {"all", "entsog", "entsog-capacity"}:
        try:
            window_policy = EntsogWindowPolicy(entsog_from, entsog_to, entsog_lookback_gas_days)
        except EntsogWindowError as exc:
            expanded = (
                ("ecb", "entsog", "entsog-capacity", "entsog-reference", "gie-agsi", "gie-alsi")
                if "all" in sources
                else sources
            )
            remaining = tuple(s for s in expanded if s not in {"entsog", "entsog-capacity"})
            if not remaining:
                raise
            configuration_blocked = True
            sources = remaining
            entsog_from = entsog_to = None
            print(
                f"Public ingestion degraded ({exc.code}): ENTSOG observations blocked "
                "before subprocess; independently configured sources continue."
            )
    policy = SourceOperationPolicy(
        source_system="public-sources",
        retry_max=max(0, retry_max),
        retry_backoff_seconds=max(0.0, retry_backoff_seconds),
    )
    iteration = 0
    failed_iterations = 0
    while max_iterations is None or iteration < max_iterations:
        window = (
            window_policy.select(clock() if window_policy.lookback_gas_days is not None else None)
            if window_policy
            else None
        )
        command = build_ingestion_command(
            sources,
            limit,
            entsog_from=window.from_date if window and not window.rolling else entsog_from,
            entsog_to=window.to_date if window and not window.rolling else entsog_to,
            entsog_lookback_gas_days=window.lookback_gas_days if window else None,
            entsog_window_anchor=window.anchor_utc.isoformat()
            if window and window.rolling
            else None,
            entsog_point_directions=point_directions,
        )
        if window and window.rolling:
            print(
                json.dumps(
                    {
                        "event": "ingestion.window.selected",
                        "source": "ENTSOG",
                        "window": window.metadata(),
                        "quality_warning": "entsog_open_gas_day",
                    }
                )
            )
        result = run_with_retry(
            "public-sources",
            lambda command=command: runner(command, check=False, text=True),
            is_success=lambda completed: completed.returncode == 0,
            policy=policy,
            sleeper=sleeper,
        )
        iteration += 1
        if not result.succeeded:
            failed_iterations += 1
            print(
                "Public ingestion iteration failed after "
                f"{result.attempts} attempt(s): {result.last_error_type}; "
                "inspect Source Center and ingestion_runs."
            )
        if max_iterations is not None and iteration >= max_iterations:
            break
        sleeper(interval_seconds)
    return 2 if configuration_blocked else int(failed_iterations > 0)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the public ingestion worker loop."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", action="append", required=True)
    parser.add_argument("--limit", type=int, default=10_000)
    parser.add_argument("--interval-seconds", type=int, required=True)
    parser.add_argument("--max-iterations", type=int)
    parser.add_argument("--retry-max", type=int, default=3)
    parser.add_argument("--retry-backoff-seconds", type=float, default=30.0)
    parser.add_argument("--entsog-from")
    parser.add_argument("--entsog-to")
    parser.add_argument("--entsog-lookback-gas-days", type=int)
    parser.add_argument(
        "--entsog-point-direction",
        action="append",
        default=[],
        metavar="POINT_DIRECTION",
        help=(
            "Explicit ENTSOG operational point direction (repeatable or "
            "comma-separated; each value must end with entry or exit). Applies "
            "only to flow/capacity observations, never topology reference data."
        ),
    )
    args = parser.parse_args(argv)
    if args.interval_seconds < 60:
        parser.error("--interval-seconds must be at least 60")
    try:
        point_directions = validate_entsog_point_directions(args.entsog_point_direction)
    except ValueError as exc:
        parser.error(f"invalid --entsog-point-direction: {exc}")
    return run_worker(
        sources=args.source,
        limit=args.limit,
        interval_seconds=args.interval_seconds,
        max_iterations=args.max_iterations,
        retry_max=args.retry_max,
        retry_backoff_seconds=args.retry_backoff_seconds,
        entsog_from=args.entsog_from,
        entsog_to=args.entsog_to,
        entsog_lookback_gas_days=args.entsog_lookback_gas_days,
        entsog_point_directions=point_directions,
    )


if __name__ == "__main__":
    raise SystemExit(main())
