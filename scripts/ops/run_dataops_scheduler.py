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
from datetime import UTC, datetime
from pathlib import Path

from eurogas_nexus.application.dataops_observability import emit_event
from eurogas_nexus.application.dataops_runtime import (
    IngestionAttemptResult,
    execute_claimed_runs,
    scan_scheduler,
)
from eurogas_nexus.db.session import get_session_factory, resolve_database_url
from eurogas_nexus.domain.dataops.contracts import FailureCategory, QualityIssue, QualitySeverity
from eurogas_nexus.ingestion.entsog_transport import EntsogWindowError
from eurogas_nexus.ingestion.entsog_window import EntsogWindowPolicy, require_aware_anchor

INGEST_SCRIPT = Path(__file__).with_name("ingest_public_sources.py")

_SOURCE_ARGS = {
    "src-ecb": ("ecb",),
    "src-entsog": ("entsog", "entsog-capacity", "entsog-reference"),
    "src-gie": ("gie-agsi", "gie-alsi"),
}


def run_ingestor_attempt(
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    *,
    entsog_from: str | None = None,
    entsog_to: str | None = None,
    entsog_lookback_gas_days: int | None = None,
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
        window = None
        if source_id == "src-entsog":
            try:
                policy = EntsogWindowPolicy(entsog_from, entsog_to, entsog_lookback_gas_days)
                anchor = None
                if policy.lookback_gas_days is not None:
                    anchor = require_aware_anchor(payload.get("scheduled_for_utc"))
                window = policy.select(anchor)
            except EntsogWindowError as exc:
                emit_event(
                    event="ingestion.attempt.blocked",
                    level="error",
                    source_id=source_id,
                    run_id=str(payload.get("run_id") or ""),
                    error_category=FailureCategory.CONFIGURATION.value,
                    attempt=attempt,
                    details={"code": exc.code},
                )
                return IngestionAttemptResult(
                    succeeded=False,
                    classification=FailureCategory.CONFIGURATION,
                    error_message=(
                        f"CONFIGURATION {exc.code}: ENTSOG window policy or run anchor refused."
                    ),
                )
            if window.rolling:
                command.extend(
                    [
                        "--entsog-lookback-gas-days",
                        str(window.lookback_gas_days),
                        "--entsog-window-anchor",
                        window.anchor_utc.isoformat(),
                    ]
                )
            else:
                command.extend(["--entsog-from", window.from_date, "--entsog-to", window.to_date])
            emit_event(
                event="ingestion.window.selected",
                source_id=source_id,
                run_id=str(payload.get("run_id") or ""),
                attempt=attempt,
                details=window.metadata(),
            )
        completed = runner(command, text=True, capture_output=True)
        if completed.returncode != 0:
            if source_id == "src-entsog":
                try:
                    failure_report = json.loads(completed.stdout or "{}")
                except json.JSONDecodeError:
                    failure_report = {}
                failures = (
                    failure_report.get("failures") if isinstance(failure_report, dict) else None
                )
                if isinstance(failures, list) and any(
                    isinstance(failure, dict)
                    and failure.get("code") == "entsog_revision_requires_history"
                    for failure in failures
                ):
                    action = (
                        "Changed ENTSOG measurements were refused; original rows and raw evidence "
                        "retained. Review revisions and implement approved append-only history "
                        "before replay."
                    )
                    emit_event(
                        event="ingestion.attempt.failed",
                        level="error",
                        source_id=source_id,
                        run_id=str(payload.get("run_id") or ""),
                        attempt=attempt,
                        error_category=FailureCategory.QUALITY_REJECTED.value,
                        details={"code": "entsog_revision_requires_history", "action": action},
                    )
                    return IngestionAttemptResult(
                        succeeded=False,
                        classification=FailureCategory.QUALITY_REJECTED,
                        error_message=(
                            f"QUALITY_REJECTED entsog_revision_requires_history: {action}"
                        ),
                        quality_issues=[
                            QualityIssue(
                                quality_code="entsog_revision_requires_history",
                                severity=QualitySeverity.ERROR,
                                message=action,
                            )
                        ],
                        lineage_refs=[window.reference],
                    )
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
        sources = report.get("sources") if isinstance(report, dict) else None
        counts = ("records", "received_records", "skipped_records", "inserted", "unchanged")
        if (
            not isinstance(report, dict)
            or report.get("ok") is not True
            or not isinstance(sources, dict)
            or not sources
            or any(
                not isinstance(name, str)
                or not isinstance(detail, dict)
                or "records" not in detail
                or any(
                    type(detail[field]) is not int or detail[field] < 0
                    for field in counts
                    if field in detail
                )
                for name, detail in sources.items()
            )
        ):
            return IngestionAttemptResult(
                succeeded=False,
                classification=FailureCategory.BAD_RESPONSE,
                error_message="Ingestor returned an invalid success report or source counters.",
            )
        rows = sum(int(detail.get("records") or 0) for detail in sources.values())
        emit_event(
            event="ingestion.attempt.succeeded",
            source_id=source_id,
            run_id=str(payload.get("run_id") or ""),
            attempt=attempt,
            details={"rows": rows, "datasets": sorted(sources)},
        )
        partial_issues = []
        if window and window.rolling:
            partial_issues.append(
                QualityIssue(
                    quality_code="entsog_open_gas_day",
                    severity=QualitySeverity.WARNING,
                    message=(
                        f"Gas day {window.open_gas_day_label} was open at the run anchor; "
                        "the date envelope is a replay slice, not closed-day coverage."
                    ),
                )
            )
        if source_id == "src-entsog" and any(
            detail.get("complete") is False or detail.get("status") == "SUCCEEDED_WITH_WARNINGS"
            for detail in sources.values()
        ):
            partial_issues.append(
                QualityIssue(
                    quality_code="entsog_bounded_partial",
                    severity=QualitySeverity.WARNING,
                    message=(
                        "ENTSOG query is bounded partial or normalization skipped records; "
                        "snapshot consistency unproven."
                    ),
                )
            )
        entsog_counts = source_id == "src-entsog"
        return IngestionAttemptResult(
            succeeded=True,
            rows_received=(
                sum(int(detail.get("received_records") or 0) for detail in sources.values())
                if entsog_counts
                else rows
            ),
            rows_accepted=rows,
            rows_rejected=(
                sum(int(detail.get("skipped_records") or 0) for detail in sources.values())
                if entsog_counts
                else 0
            ),
            rows_inserted=(
                sum(int(detail.get("inserted") or 0) for detail in sources.values())
                if entsog_counts
                else rows
            ),
            duplicate_count=(
                sum(int(detail.get("unchanged") or 0) for detail in sources.values())
                if entsog_counts
                else 0
            ),
            lineage_refs=[f"public-source-ingestor:{source_id}"]
            + ([window.reference] if window else []),
            quality_issues=partial_issues,
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
    entsog_from: str | None = None,
    entsog_to: str | None = None,
    entsog_lookback_gas_days: int | None = None,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> int:
    """Run scheduler scans and run executions on a bounded cadence."""

    if resolve_database_url() is None:
        emit_event(event="scheduler.blocked", level="error", error_category="CONFIGURATION")
        emit(json.dumps({"status": "blocked", "reason": "database_url_missing"}))
        return 2

    session_factory = get_session_factory()
    configuration_blocks = {}
    try:
        EntsogWindowPolicy(entsog_from, entsog_to, entsog_lookback_gas_days)
    except EntsogWindowError as exc:
        configuration_blocks["src-entsog"] = exc.code
        emit_event(
            event="scheduler.source.blocked",
            level="error",
            source_id="src-entsog",
            error_category=FailureCategory.CONFIGURATION.value,
            details={"code": exc.code},
        )
    attempt_runner = run_ingestor_attempt(
        runner,
        entsog_from=entsog_from,
        entsog_to=entsog_to,
        entsog_lookback_gas_days=entsog_lookback_gas_days,
    )
    iteration = 0
    failed_iterations = 0
    while max_iterations is None or iteration < max_iterations:
        try:
            now_utc = require_aware_anchor(clock())
            with session_factory() as session:
                scan = scan_scheduler(session, limit=scan_limit, now_utc=now_utc)
                session.commit()
            with session_factory() as session:
                execution = execute_claimed_runs(
                    session,
                    runner=attempt_runner,
                    limit=run_limit,
                    now_utc=now_utc,
                )
                session.commit()
            failures = [
                outcome
                for outcome in execution.get("outcomes", [])
                if outcome.get("status") == "FAILED"
            ]
            failed_iterations += bool(failures)
            emit(
                json.dumps(
                    {
                        "status": "degraded" if failures or configuration_blocks else "ok",
                        "configuration_blocks": configuration_blocks,
                        "scan": scan,
                        "execution": execution,
                    }
                )
            )
        except Exception as exc:
            failed_iterations += 1
            emit_event(event="scheduler.scan.failed", level="error", error_category="INTERNAL")
            emit(json.dumps({"status": "failed", "error_type": exc.__class__.__name__}))
        iteration += 1
        if max_iterations is not None and iteration >= max_iterations:
            break
        sleeper(max(1.0, interval_seconds))
    return 2 if configuration_blocks else int(failed_iterations > 0)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--interval-seconds", type=float, default=60.0)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--scan-limit", type=int, default=10)
    parser.add_argument("--run-limit", type=int, default=10)
    parser.add_argument("--entsog-from")
    parser.add_argument("--entsog-to")
    parser.add_argument("--entsog-lookback-gas-days", type=int)
    args = parser.parse_args(argv)
    if args.interval_seconds < 15:
        parser.error("--interval-seconds must be at least 15")
    return run_loop(
        interval_seconds=args.interval_seconds,
        max_iterations=1 if args.once else None,
        scan_limit=args.scan_limit,
        run_limit=args.run_limit,
        entsog_from=args.entsog_from,
        entsog_to=args.entsog_to,
        entsog_lookback_gas_days=args.entsog_lookback_gas_days,
    )


if __name__ == "__main__":
    raise SystemExit(main())
