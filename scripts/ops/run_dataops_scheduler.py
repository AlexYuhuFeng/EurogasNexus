"""PostgreSQL-backed data-operations scheduler and worker.

The scheduler claims due sources and creates QUEUED ``ingestion_runs``; the
worker then claims QUEUED runs and executes the existing public-source
ingestor with failure-category-aware retry. All schedule truth is persisted;
this process can be restarted (and run in parallel) without duplicate
scheduled ingestion.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from pathlib import Path

from eurogas_nexus.application.dataops_observability import emit_event
from eurogas_nexus.application.dataops_runtime import (
    IngestionAttemptResult,
    execute_claimed_runs,
    scan_scheduler,
)
from eurogas_nexus.db.session import get_session_factory, resolve_database_url
from eurogas_nexus.domain.dataops.contracts import FailureCategory

INGEST_SCRIPT = Path(__file__).with_name("ingest_public_sources.py")

_SOURCE_ARGS = {
    "src-ecb": ("ecb",),
    "src-entsog": ("entsog", "entsog-capacity", "entsog-reference"),
    "src-gie": ("gie-agsi", "gie-alsi"),
}


def run_ingestor_attempt(
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> Callable[[dict, int], IngestionAttemptResult]:
    """Return an adapter runner bound to the public-source ingestor."""

    def run(payload: dict, attempt: int) -> IngestionAttemptResult:
        source_id = str(payload.get("source_id") or "")
        source_args = _SOURCE_ARGS.get(source_id)
        if not source_args:
            emit_event(
                event="ingestion.attempt.unsupported",
                level="error",
                source_id=source_id,
                run_id=str(payload.get("run_id") or ""),
                error_category=FailureCategory.CONFIGURATION.value,
                attempt=attempt,
            )
            return IngestionAttemptResult(
                succeeded=False,
                classification=FailureCategory.CONFIGURATION,
                error_message=f"No production runner is implemented for {source_id}.",
            )
        command = [sys.executable, str(INGEST_SCRIPT), "--json"]
        for source in source_args:
            command.extend(["--source", source])
        completed = runner(command, text=True, capture_output=True)
        if completed.returncode != 0:
            emit_event(
                event="ingestion.attempt.failed",
                level="warning",
                source_id=source_id,
                run_id=str(payload.get("run_id") or ""),
                error_category="INTERNAL",
                attempt=attempt,
                details={"stderr_tail": (completed.stderr or "")[-400:]},
            )
            return IngestionAttemptResult(
                succeeded=False,
                classification=FailureCategory.INTERNAL,
                error_message=(completed.stderr or completed.stdout or "").strip()[-500:],
            )
        try:
            report = json.loads(completed.stdout or "{}")
        except json.JSONDecodeError:
            return IngestionAttemptResult(
                succeeded=False,
                classification=FailureCategory.BAD_RESPONSE,
                error_message="Ingestor returned malformed JSON.",
            )
        sources = report.get("sources") or {}
        rows = sum(int(detail.get("records") or 0) for detail in sources.values())
        emit_event(
            event="ingestion.attempt.succeeded",
            source_id=source_id,
            run_id=str(payload.get("run_id") or ""),
            attempt=attempt,
            details={"rows": rows, "datasets": sorted(sources)},
        )
        return IngestionAttemptResult(
            succeeded=True,
            rows_received=rows,
            rows_accepted=rows,
            rows_inserted=rows,
            lineage_refs=[f"public-source-ingestor:{source_id}"],
        )

    return run


def run_loop(
    *,
    interval_seconds: float,
    max_iterations: int | None = None,
    scan_limit: int = 10,
    run_limit: int = 10,
    sleeper: Callable[[float], None] = time.sleep,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    emit: Callable[[str], None] = print,
) -> int:
    """Run scheduler scans and run executions on a bounded cadence."""

    if resolve_database_url() is None:
        emit_event(event="scheduler.blocked", level="error", error_category="CONFIGURATION")
        emit(json.dumps({"status": "blocked", "reason": "database_url_missing"}))
        return 2

    session_factory = get_session_factory()
    attempt_runner = run_ingestor_attempt(runner)
    iteration = 0
    while max_iterations is None or iteration < max_iterations:
        try:
            with session_factory() as session:
                scan = scan_scheduler(session, limit=scan_limit)
                session.commit()
            with session_factory() as session:
                execution = execute_claimed_runs(
                    session,
                    runner=attempt_runner,
                    limit=run_limit,
                )
                session.commit()
            emit(json.dumps({"status": "ok", "scan": scan, "execution": execution}))
        except Exception as exc:
            emit_event(event="scheduler.scan.failed", level="error", error_category="INTERNAL")
            emit(json.dumps({"status": "failed", "error_type": exc.__class__.__name__}))
        iteration += 1
        if max_iterations is not None and iteration >= max_iterations:
            break
        sleeper(max(1.0, interval_seconds))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--interval-seconds", type=float, default=60.0)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--scan-limit", type=int, default=10)
    parser.add_argument("--run-limit", type=int, default=10)
    args = parser.parse_args(argv)
    if args.interval_seconds < 15:
        parser.error("--interval-seconds must be at least 15")
    return run_loop(
        interval_seconds=args.interval_seconds,
        max_iterations=1 if args.once else None,
        scan_limit=args.scan_limit,
        run_limit=args.run_limit,
    )


if __name__ == "__main__":
    raise SystemExit(main())
