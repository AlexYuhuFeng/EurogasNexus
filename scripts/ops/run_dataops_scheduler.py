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
from eurogas_nexus.application.publication_watch import watch_publications_if_due
from eurogas_nexus.application.retention import run_retention_if_due
from eurogas_nexus.application.scheduled_source_keys import (
    activate_keyed_sources,
    key_configured,
)
from eurogas_nexus.application.scheduler_lease import (
    HeartbeatKeeper,
    holder_label,
    lease_for,
    touch_heartbeat,
)
from eurogas_nexus.db.session import get_session_factory, resolve_database_url
from eurogas_nexus.domain.dataops.contracts import FailureCategory, QualityIssue, QualitySeverity
from eurogas_nexus.domain.dataops.retry import classify_script_failure
from eurogas_nexus.ingestion.entsog_scope import validate_entsog_point_directions
from eurogas_nexus.ingestion.entsog_transport import EntsogWindowError
from eurogas_nexus.ingestion.entsog_window import EntsogWindowPolicy, require_aware_anchor

INGEST_SCRIPT = Path(__file__).with_name("ingest_public_sources.py")

_SOURCE_ARGS = {
    "src-ecb": ("ecb",),
    "src-entsog": ("entsog", "entsog-capacity", "entsog-reference", "entsog-tariffs"),
    "src-gie": ("gie-agsi", "gie-alsi"),
}

#: Read bounds per scheduled public-source run, in one place. The ingestor's own default
#: (``--limit 20``) is an operator's sample size, not a production read: under it the
#: ENTSOG reference read was partial and refused, and flows fetched 4 records (live,
#: 2026-11-13). Sizes measured live (docs/data/LIVE_BRINGUP_2026-11-12.md):
#:
#: * ENTSOG: 789 connection points and 1,283 operator point directions; a gas day of all
#:   points is a few thousand raw rows per indicator, so a 7-day unscoped flow or capacity
#:   query is some 20-30 thousand. Page size 1,000 is the platform maximum, and 50 pages of
#:   1,000 (50,000 records) is the transport's hard cap, so a query can never be cut by a
#:   smaller bound than the transport allows. A query that reaches the bound is incomplete
#:   and the attempt fails (``entsog_read_bound_reached``); it never passes as complete.
#:   The reference network changes rarely, so it is re-read at most once a day.
#: * GIE: read by ``backfill_gie_history.py`` (``_SCRIPT_COMMANDS``), not with a record bound
#:   here: one gas year per window through this ingestor, so every gate and revision rule
#:   applies.
_SOURCE_BOUNDS: dict[str, tuple[tuple[str, str], ...]] = {
    "src-entsog": (
        ("--limit", "50000"),
        ("--entsog-page-size", "1000"),
        ("--entsog-max-pages", "50"),
        ("--entsog-reference-max-age-hours", "24"),
        # Published tariffs change once a tariff period: each point is read at most daily, for
        # the current and the next gas year, one point every 2 s; a point read within the day
        # is skipped, so a retried or restarted run resumes where it stopped.
        ("--entsog-tariffs-max-age-hours", "24"),
        ("--entsog-pace-seconds", "2"),
    ),
}



def _tariff_max_age_hours(scheduled_for: object) -> str:
    """How old a point's ENTSOG tariffs may be before this run reads them again (TAR-1).

    The tariff book's poll for ENTSOG (``domain/tariffs/publishers``): hourly in the windows
    operators publish reserve prices (TAR-2: before the April years, the NC TAR window before
    the July yearly auction, before the gas year and before the calendar year), every 6 hours
    otherwise. The age is nine tenths of the interval, so a point read by the previous run of
    an hourly job is read again by the next one rather than skipped for a few seconds' jitter.
    ``_SOURCE_BOUNDS`` keeps the daily figure as the default a run without an anchor uses.
    """

    from eurogas_nexus.domain.tariffs.publishers import publisher

    try:
        anchor = datetime.fromisoformat(str(scheduled_for).replace("Z", "+00:00"))
    except ValueError:
        anchor = datetime.now(UTC)
    poll = publisher("entsog-tp").poll
    minutes = poll.interval_minutes(anchor) if poll else 1440
    return f"{max(minutes, 1) * 0.9 / 60:g}"


# Sources with their own ingest script; each prints the same JSON report with --json.
_SCRIPT_COMMANDS = {
    # Seven days: ENTSO-E actual generation arrives late (DE-LU A75 for 10-11 Nov 2026 was
    # not yet published 36 h after the day), and a two-day window never read it again.
    "src-entsoe": ("ingest_power.py", "--commit", "--json", "--days", "7"),
    "src-elexon": ("ingest_power_gb.py", "--commit", "--json", "--days", "2"),
    "src-national-gas-supply": (
        "ingest_national_gas_supply.py", "--commit", "--json", "--days", "5",
    ),
    # Eight gas days cover the D+6 amendment of each day; every publication is appended.
    "src-national-gas-demand": ("ingest_national_gas_demand.py", "--json", "--days", "8"),
    # GIE IIP storage and LNG UMMs: two days of submissions, about two pages of 50.
    "src-remit-umm": ("ingest_remit_iip.py", "--commit", "--json", "--days", "2"),
    # ENTSOG transmission UMMs: the whole dataset is read (about 100 versions); seven days
    # of publications plus every event still running.
    "src-entsog-umm": ("ingest_remit_entsog.py", "--commit", "--json", "--days", "7"),
    "src-boe": ("ingest_interest_rates.py", "--json", "--benchmark", "SONIA", "--days", "10"),
    "src-ecb-estr": ("ingest_interest_rates.py", "--json", "--benchmark", "ESTR", "--days", "10"),
    "src-eia": ("ingest_eia.py", "--json", "--days", "14"),
    "src-nyfed": ("ingest_interest_rates.py", "--json", "--benchmark", "SOFR", "--days", "10"),
    # TAR-2: the firm's own bank (Societe Generale) over its API. Off by default: it runs only
    # once an administrator enables it, and the script itself refuses (exit 3, CONFIGURATION)
    # without the firm's agreement recorded, the endpoint configuration and the credential.
    "src-bank-socgen": (
        "fetch_bank_rates.py", "--institution", "SOCGEN", "--commit", "--json",
    ),
    # GIE AGSI and ALSI for the EU total and every country GIE publishes: five complete gas
    # years kept filled (at most 40 missing windows a run, so a new store fills in a few
    # runs), and the last week of each series re-read for provider revisions (up to 4 days
    # back seen live). Each window goes through ingest_public_sources.py, so the approval,
    # certification and key gates and the revision rules are unchanged.
    "src-gie": (
        "backfill_gie_history.py", "--product", "agsi", "--product", "alsi", "--years", "5",
        "--refresh", "--max-windows", "40", "--json",
    ),
}


#: ENTSOG persistence refusals: a row changed in a field a revision may not change, or a
#: changed value not received after the stored one. A provider revision of a value is
#: stored with history and is not a failure (docs/operations/DATA_REVISIONS.md).
_ENTSOG_REFUSAL_CODES = (
    "entsog_revision_identity_conflict",
    "entsog_revision_not_newer",
    "entsog_revision_requires_history",
)


def _failure_report(stdout: str | None) -> tuple[list[str], int]:
    """The failure codes and the rows a failed script still stored, from its JSON report."""

    report = None
    for text in [(stdout or "").strip(), *reversed((stdout or "").strip().splitlines())]:
        try:
            value = json.loads(text)
        except ValueError:
            continue
        if isinstance(value, dict):
            report = value
            break
    if report is None:
        return [], 0
    codes = [
        str(failure.get("code"))
        for failure in report.get("failures") or []
        if isinstance(failure, dict) and failure.get("code")
    ]
    sources = report.get("sources") if isinstance(report.get("sources"), dict) else {}
    stored = 0
    for detail in sources.values():
        if isinstance(detail, dict):
            for field in ("inserted", "updated"):
                value = detail.get(field)
                if type(value) is int and value > 0:
                    stored += value
    return codes, stored


def _configuration_refusal(stdout: str | None) -> tuple[str, str] | None:
    """A script's own refusal for missing set-up (``configuration_code`` in its JSON report,
    e.g. a bank feed not connected): recorded as CONFIGURATION, never retried as a failure."""

    try:
        report = json.loads(stdout or "{}")
    except json.JSONDecodeError:
        return None
    code = report.get("configuration_code") if isinstance(report, dict) else None
    if not isinstance(code, str) or not code:
        return None
    return code[:120], str(report.get("message") or "")[:300]


def run_ingestor_attempt(
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    *,
    entsog_from: str | None = None,
    entsog_to: str | None = None,
    entsog_lookback_gas_days: int | None = None,
    entsog_point_directions: Sequence[str] = (),
    key_check: Callable[[str], bool | None] | None = None,
    entsog_history: bool = False,
) -> Callable[[dict, int], IngestionAttemptResult]:
    """Return an adapter runner bound to the public-source ingestor.

    ``entsog_history`` (the loop passes True): after a successful ``src-entsog`` attempt, run
    the landing-point history step (``ENTSOG_HISTORY_COMMAND``) behind the same gates.

    ``key_check(source_id)`` (the loop passes ``scheduled_source_keys.key_configured``)
    returns False for a keyed source whose key is not configured: the attempt then does not
    start the script and is recorded as ``CONFIGURATION credential_missing``.
    """

    point_directions = validate_entsog_point_directions(entsog_point_directions)

    def run(payload: dict, attempt: int) -> IngestionAttemptResult:
        source_id = str(payload.get("source_id") or "")
        source_args = _SOURCE_ARGS.get(source_id)
        script_command = _SCRIPT_COMMANDS.get(source_id)
        if key_check is not None and key_check(source_id) is False:
            emit_event(
                event="ingestion.attempt.blocked",
                level="warning",
                source_id=source_id,
                run_id=str(payload.get("run_id") or ""),
                error_category=FailureCategory.CONFIGURATION.value,
                attempt=attempt,
                details={"code": "credential_missing"},
            )
            return IngestionAttemptResult(
                succeeded=False,
                classification=FailureCategory.CONFIGURATION,
                error_message=(
                    "CONFIGURATION credential_missing: this source reads with the firm's own "
                    "provider key; store it on Admin -> Data sources (Credentials)."
                ),
            )
        if not source_args and not script_command:
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
        if script_command:
            script, *script_args = script_command
            command = [sys.executable, str(INGEST_SCRIPT.with_name(script)), *script_args]
        else:
            command = [sys.executable, str(INGEST_SCRIPT), "--json"]
            for source in source_args:
                command.extend(["--source", source])
            for flag, value in _SOURCE_BOUNDS.get(source_id, ()):
                if flag == "--entsog-tariffs-max-age-hours":
                    value = _tariff_max_age_hours(payload.get("scheduled_for_utc"))
                command.extend([flag, value])
        window = None
        if source_id == "src-entsog":
            for point_direction in point_directions:
                command.extend(["--entsog-point-direction", point_direction])
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
        if completed.returncode != 0 and (refusal := _configuration_refusal(completed.stdout)):
            emit_event(
                event="ingestion.attempt.blocked",
                level="warning",
                source_id=source_id,
                run_id=str(payload.get("run_id") or ""),
                error_category=FailureCategory.CONFIGURATION.value,
                attempt=attempt,
                details={"code": refusal[0]},
            )
            return IngestionAttemptResult(
                succeeded=False,
                classification=FailureCategory.CONFIGURATION,
                error_message=f"CONFIGURATION {refusal[0]}: {refusal[1]}"[:500],
            )
        if completed.returncode != 0:
            if source_id == "src-entsog":
                try:
                    failure_report = json.loads(completed.stdout or "{}")
                except json.JSONDecodeError:
                    failure_report = {}
                failures = (
                    failure_report.get("failures") if isinstance(failure_report, dict) else None
                )
                refusal = next(
                    (
                        failure.get("code")
                        for failure in (failures if isinstance(failures, list) else [])
                        if isinstance(failure, dict)
                        and failure.get("code") in _ENTSOG_REFUSAL_CODES
                    ),
                    None,
                )
                if refusal is not None:
                    action = (
                        "ENTSOG rows that differ from stored rows in more than a revisable value "
                        "were refused; original rows and raw evidence retained. Review the "
                        "identity change before replay."
                    )
                    emit_event(
                        event="ingestion.attempt.failed",
                        level="error",
                        source_id=source_id,
                        run_id=str(payload.get("run_id") or ""),
                        attempt=attempt,
                        error_category=FailureCategory.QUALITY_REJECTED.value,
                        details={"code": refusal, "action": action},
                    )
                    return IngestionAttemptResult(
                        succeeded=False,
                        classification=FailureCategory.QUALITY_REJECTED,
                        error_message=f"QUALITY_REJECTED {refusal}: {action}",
                        quality_issues=[
                            QualityIssue(
                                quality_code=refusal,
                                severity=QualitySeverity.ERROR,
                                message=action,
                            )
                        ],
                        lineage_refs=[window.reference],
                    )
            # The script's own report says what failed (a rate limit, a provider outage, a
            # missing key); only a script that said nothing is INTERNAL.
            codes, stored = _failure_report(completed.stdout)
            classified = classify_script_failure(codes)
            emit_event(
                event="ingestion.attempt.failed",
                level="warning",
                source_id=source_id,
                run_id=str(payload.get("run_id") or ""),
                error_category=classified.category.value,
                attempt=attempt,
                details={
                    "codes": codes,
                    "rows_stored": stored,
                    "stderr_tail": (completed.stderr or "")[-400:],
                },
            )
            text = (completed.stderr or completed.stdout or "").strip()[-400:]
            partial = (
                f"partial read: {stored} rows stored before it stopped; " if stored else ""
            )
            return IngestionAttemptResult(
                succeeded=False,
                classification=classified.category,
                error_message=f"{classified.code}: {partial}{text}"[:500],
                rows_received=stored,
                rows_accepted=stored,
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
        counts = (
            "records",
            "received_records",
            "skipped_records",
            "inserted",
            "updated",
            "unchanged",
            "revised",
        )
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
        bounded = sorted(
            name for name, detail in sources.items() if detail.get("complete") is False
        )
        if source_id == "src-entsog" and bounded:
            # The rows that were read are stored and correct, but the window is not covered:
            # widening the bound or narrowing the window is an operator decision, so the
            # attempt fails without a retry that would hit the same bound.
            action = (
                f"ENTSOG {', '.join(bounded)} stopped at the read bound before the provider's "
                "data was exhausted; the window is not covered. Raise the bound in "
                "_SOURCE_BOUNDS or narrow the window."
            )
            emit_event(
                event="ingestion.attempt.failed",
                level="error",
                source_id=source_id,
                run_id=str(payload.get("run_id") or ""),
                attempt=attempt,
                error_category=FailureCategory.QUALITY_REJECTED.value,
                details={"code": "entsog_read_bound_reached", "datasets": bounded},
            )
            return IngestionAttemptResult(
                succeeded=False,
                classification=FailureCategory.QUALITY_REJECTED,
                error_message=f"QUALITY_REJECTED entsog_read_bound_reached: {action}",
                quality_issues=[
                    QualityIssue(
                        quality_code="entsog_read_bound_reached",
                        severity=QualitySeverity.ERROR,
                        message=action,
                    )
                ],
                lineage_refs=[window.reference] if window else [],
            )
        rows = sum(int(detail.get("records") or 0) for detail in sources.values())
        emit_event(
            event="ingestion.attempt.succeeded",
            source_id=source_id,
            run_id=str(payload.get("run_id") or ""),
            attempt=attempt,
            details={
                "rows": rows,
                "datasets": sorted(sources),
                "revised": sum(int(detail.get("revised") or 0) for detail in sources.values()),
            },
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
            detail.get("skipped_records") for detail in sources.values()
        ):
            partial_issues.append(
                QualityIssue(
                    quality_code="entsog_bounded_partial",
                    severity=QualitySeverity.WARNING,
                    message=(
                        "ENTSOG normalization skipped records (for example N/A exemptions); "
                        "snapshot consistency unproven."
                    ),
                )
            )

        def total(field: str) -> int:
            return sum(int(detail.get(field) or 0) for detail in sources.values())

        # A report that states its write counters is taken at its word; one that states only
        # ``records`` (older script reports) counts every record as written.
        counted = any("inserted" in detail for detail in sources.values())
        return IngestionAttemptResult(
            succeeded=True,
            rows_received=(
                total("received_records")
                if any("received_records" in detail for detail in sources.values())
                else rows
            ),
            rows_accepted=rows,
            rows_rejected=total("skipped_records"),
            rows_inserted=total("inserted") if counted else rows,
            rows_updated=total("updated"),
            duplicate_count=total("unchanged"),
            lineage_refs=[f"public-source-ingestor:{source_id}"]
            + ([window.reference] if window else []),
            quality_issues=partial_issues,
        )

    if not entsog_history:
        return run

    def run_with_history(payload: dict, attempt: int) -> IngestionAttemptResult:
        result = run(payload, attempt)
        if str(payload.get("source_id") or "") != "src-entsog" or not result.succeeded:
            return result
        return _with_entsog_landing_history(runner, result, str(payload.get("run_id") or ""))

    return run_with_history


#: After a successful scheduled ENTSOG read, the landing points' history is kept filled for
#: the flows read (Research → Fundamentals → Flows): at most this many quarter windows a run,
#: through the same gated ingestor (scripts/ops/backfill_entsog_landings.py).
ENTSOG_HISTORY_COMMAND = (
    "backfill_entsog_landings.py", "--years", "5", "--refresh", "--max-windows", "8", "--json",
)


def _with_entsog_landing_history(
    runner: Callable[..., subprocess.CompletedProcess[str]],
    result: IngestionAttemptResult,
    run_id: str,
) -> IngestionAttemptResult:
    """Run the landing history step; its outcome adds to the attempt, never fails it.

    The ENTSOG read itself succeeded, so its rows stand. A history step that could not run
    (refused, timed out, malformed) is recorded as a warning on the attempt and is read
    again at the next run (the driver resumes from what the store holds).
    """

    from dataclasses import replace

    script, *script_args = ENTSOG_HISTORY_COMMAND
    command = [sys.executable, str(INGEST_SCRIPT.with_name(script)), *script_args]
    completed = runner(command, text=True, capture_output=True)
    try:
        report = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError:
        report = {}
    sources = report.get("sources") if isinstance(report, dict) else None
    if completed.returncode == 0 and isinstance(sources, dict):
        rows = sum(int(d.get("records") or 0) for d in sources.values() if isinstance(d, dict))
        inserted = sum(int(d.get("inserted") or 0) for d in sources.values() if isinstance(d, dict))
        emit_event(event="ingestion.history.succeeded", source_id="src-entsog", run_id=run_id,
                   details={"rows": rows, "windows": len(report.get("done") or [])})
        return replace(
            result,
            rows_received=result.rows_received + rows,
            rows_accepted=result.rows_accepted + rows,
            rows_inserted=result.rows_inserted + inserted,
            lineage_refs=[*result.lineage_refs, "entsog-landing-history"],
        )
    codes = sorted({str(f.get("codes")) for f in (report.get("failed") or [])}) if isinstance(
        report, dict) else []
    emit_event(event="ingestion.history.failed", level="warning", source_id="src-entsog",
               run_id=run_id, details={"codes": codes, "returncode": completed.returncode})
    return replace(
        result,
        quality_issues=[
            *result.quality_issues,
            QualityIssue(
                quality_code="entsog_landing_history_incomplete",
                severity=QualitySeverity.WARNING,
                message=(
                    "The landing-point history step did not complete; the ENTSOG read itself "
                    "succeeded. It resumes at the next run."
                ),
            ),
        ],
    )


def evaluate_opportunities_if_due(session_factory, outcomes, *, now_utc) -> dict:
    """Note the input classes the ingestions changed, then run the debounced evaluation.

    Its own transactions: a failure here is reported and never undoes or stops ingestion.
    """

    from eurogas_nexus.application.opportunities.schedule import (
        note_ingestion_changes,
        run_due,
    )

    try:
        with session_factory() as session:
            noted = note_ingestion_changes(session, outcomes, now_utc=now_utc)
            session.commit()
        with session_factory() as session:
            result = run_due(session, now_utc=now_utc)
            session.commit()
    except Exception as exc:  # noqa: BLE001 - the evaluation never stops the ingestion loop
        emit_event(
            event="scheduler.opportunity_evaluation.failed",
            level="error",
            error_category="INTERNAL",
            details={"error_type": exc.__class__.__name__},
        )
        return {"status": "failed", "error_type": exc.__class__.__name__}
    evaluation = result.get("evaluation") or {}
    return {
        "status": result["status"],
        "noted": noted,
        "classes": result.get("classes", []),
        "evaluation_id": evaluation.get("evaluation_id"),
        "evaluation_status": evaluation.get("status"),
    }


def deliver_market_events(session_factory, outcomes, *, now_utc) -> dict:
    """M4/M5: record a ``source.ingested`` event per run that wrote rows, capture price, FX and
    REMIT changes in the lookback window (M5), then drain the outbox.

    Its own transactions, after the CP-13 hook: a failure is reported and never undoes or stops
    ingestion. Consumers that raise are retried by the outbox, not here.
    """

    from eurogas_nexus.application import market_event_capture, market_events

    try:
        with session_factory() as session:
            published = [
                market_events.publish(session, event).kind.value
                for event in market_events.ingestion_events(session, outcomes, now_utc=now_utc)
            ]
            session.commit()
        with session_factory() as session:
            captured = market_event_capture.capture(session, now_utc=now_utc)
            session.commit()
        batches = market_events.drain(session_factory, now_utc=now_utc)
    except Exception as exc:  # noqa: BLE001 - the outbox never stops the ingestion loop
        emit_event(
            event="scheduler.market_events.failed",
            level="error",
            error_category="INTERNAL",
            details={"error_type": exc.__class__.__name__},
        )
        return {"status": "failed", "error_type": exc.__class__.__name__}
    return {
        "status": "ok",
        "published": published,
        "captured": captured["published"],
        "processed": sum(batch.get("processed", 0) for batch in batches),
        "failed": sum(batch.get("failed", 0) for batch in batches),
        "dead": sum(batch.get("dead", 0) for batch in batches),
    }


def track_strategies_if_due(session_factory, *, now_utc) -> dict:
    """Evaluate tracked strategies that have newer inputs than their last evaluation.

    Daily tracks re-run once a day on the new close; an intraday track gets its trailing
    tick evaluated. Before this hook ``strategy_tracking.run_due`` had no scheduled caller, so
    a daily track was evaluated once, at creation, and never again (persona review B1).
    Its own transaction: a failure is reported and never stops ingestion.
    """

    from eurogas_nexus.application import strategy_tracking

    try:
        with session_factory() as session:
            result = strategy_tracking.run_due(session, now_utc)
            session.commit()
    except Exception as exc:  # noqa: BLE001 - tracking never stops the ingestion loop
        emit_event(
            event="scheduler.strategy_tracking.failed",
            level="error",
            error_category="INTERNAL",
            details={"error_type": exc.__class__.__name__},
        )
        return {"status": "failed", "error_type": exc.__class__.__name__}
    return {"status": "ok", "evaluated": result.get("evaluated", 0)}


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
    entsog_point_directions: Sequence[str] = (),
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    lease_factory: Callable[[object], object] | None = None,
) -> int:
    """Run scheduler scans and run executions on a bounded cadence.

    Only the process holding the scheduler lock scans, claims and executes
    (:mod:`eurogas_nexus.application.scheduler_lease`); another one waits as a standby and
    takes over within one interval when the active one stops. With ``--once`` a standby
    process exits 3 without ingesting.
    """

    point_directions = validate_entsog_point_directions(entsog_point_directions)
    if resolve_database_url() is None:
        emit_event(event="scheduler.blocked", level="error", error_category="CONFIGURATION")
        emit(json.dumps({"status": "blocked", "reason": "database_url_missing"}))
        return 2

    from eurogas_nexus.db.resilience import wait_for_database_at_startup

    wait_for_database_at_startup(component="scheduler", emit=emit)
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
        entsog_point_directions=point_directions,
        key_check=lambda source_id: key_configured(source_id, session_factory=session_factory),
        entsog_history=True,
    )
    iteration = 0
    failed_iterations = 0
    lease = (lease_factory or lease_for)(session_factory)
    keeper = (
        HeartbeatKeeper(lease, lambda: touch_heartbeat(session_factory))
        if getattr(lease, "postgresql", False)
        else None
    )
    standby_iterations = 0
    try:
        while max_iterations is None or iteration < max_iterations:
            if not _hold_lease(lease, keeper, emit):
                standby_iterations += 1
                iteration += 1
                if max_iterations is not None and iteration >= max_iterations:
                    break
                sleeper(max(1.0, interval_seconds))
                continue
            failed_iterations += _iteration(
                session_factory=session_factory,
                clock=clock,
                scan_limit=scan_limit,
                run_limit=run_limit,
                attempt_runner=attempt_runner,
                configuration_blocks=configuration_blocks,
                emit=emit,
            )
            iteration += 1
            if max_iterations is not None and iteration >= max_iterations:
                break
            sleeper(max(1.0, interval_seconds))
    finally:
        if keeper is not None:
            keeper.stop()
        lease.release()
    if standby_iterations and standby_iterations == iteration:
        return 3
    return 2 if configuration_blocks else int(failed_iterations > 0)


def _hold_lease(lease, keeper, emit: Callable[[str], None]) -> bool:
    """Take (or keep) the scheduler lock; report a change of role once."""

    if lease.held and not lease.lost.is_set():
        return True
    was_lost = lease.lost.is_set()
    if keeper is not None:
        keeper.stop()
    if not lease.acquire():
        emit_event(
            event="scheduler.standby",
            level="info",
            details={"reason": "another scheduler holds the lock", "holder": holder_label()},
        )
        emit(json.dumps({"status": "standby", "reason": "scheduler_lock_held_elsewhere"}))
        return False
    emit_event(
        event="scheduler.lock.reacquired" if was_lost else "scheduler.lock.acquired",
        level="info",
        details={"holder": holder_label()},
    )
    if keeper is not None:
        keeper.start()
    return True


def _iteration(
    *,
    session_factory,
    clock,
    scan_limit: int,
    run_limit: int,
    attempt_runner,
    configuration_blocks: dict,
    emit: Callable[[str], None],
) -> int:
    """One scan and execution; returns 1 when it failed or ran a failed attempt."""

    failed = 0
    try:
        now_utc = require_aware_anchor(clock())
        with session_factory() as session:
            scan = scan_scheduler(session, limit=scan_limit, now_utc=now_utc)
            # A keyed source switches on once its key is stored (unless an operator
            # switched it off); the next scan schedules it.
            try:
                scan["keyed_sources_activated"] = activate_keyed_sources(
                    session, now_utc=now_utc, session_factory=session_factory
                )
            except Exception:  # noqa: BLE001 - activation never stops the scan
                emit_event(
                    event="scheduler.keyed_activation.failed",
                    level="warning",
                    error_category="INTERNAL",
                )
            session.commit()
        with session_factory() as session:
            execution = execute_claimed_runs(
                session,
                runner=attempt_runner,
                limit=run_limit,
                now_utc=now_utc,
            )
            session.commit()
        # CP-13: ingestions that wrote rows mark their input class pending; a debounced
        # full opportunity evaluation follows. Never stops the ingestion loop.
        execution["opportunity_evaluation"] = evaluate_opportunities_if_due(
            session_factory, execution.get("outcomes", []), now_utc=now_utc
        )
        # M4: the market event outbox (lineage, staleness, targeted re-evaluation).
        execution["market_events"] = deliver_market_events(
            session_factory, execution.get("outcomes", []), now_utc=now_utc
        )
        # Tracked strategies with a newer close or tick than their last evaluation.
        execution["strategy_tracking"] = track_strategies_if_due(
            session_factory, now_utc=now_utc
        )
        # Retention by data class, once a day after its hour (application/retention.py). Runs
        # here, so only the process holding the scheduler lock prunes, in the system book
        # scope run_loop's caller set (it deletes across every book by data class, never by a
        # user's scope). Never raises: a failure is reported in the summary and audited.
        execution["retention"] = run_retention_if_due(session_factory, now_utc=now_utc)
        # Package G: the public publications the desk relies on (auction calendars), each on its
        # own interval and only where its terms allow fetching (application/publication_watch).
        # Never raises; EUROGAS_NEXUS_PUBLICATION_WATCH=off stops it.
        execution["publications"] = watch_publications_if_due(session_factory, now_utc=now_utc)
        failures = [
            outcome
            for outcome in execution.get("outcomes", [])
            if outcome.get("status") == "FAILED"
        ]
        failed += bool(failures)
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
        failed += 1
        emit_event(event="scheduler.scan.failed", level="error", error_category="INTERNAL")
        emit(json.dumps({"status": "failed", "error_type": exc.__class__.__name__}))
    return int(failed > 0)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--interval-seconds", type=float, default=60.0)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--scan-limit", type=int, default=10)
    parser.add_argument("--run-limit", type=int, default=10)
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
            "only to src-entsog flow/capacity observations, never reference "
            "topology or non-ENTSOG scheduled jobs."
        ),
    )
    args = parser.parse_args(argv)
    from eurogas_nexus.core.structured_logging import configure_logging

    configure_logging(service="eurogas-nexus-scheduler")
    if args.interval_seconds < 15:
        parser.error("--interval-seconds must be at least 15")
    try:
        point_directions = validate_entsog_point_directions(args.entsog_point_direction)
    except ValueError as exc:
        parser.error(f"invalid --entsog-point-direction: {exc}")
    from eurogas_nexus.security.portfolio_scope import system_scope

    # The scheduler is the firm's own machinery, not a person: it ingests public sources and
    # runs the firm-wide opportunity evaluation and strategy tracking, which store results for
    # every book (each reader is filtered when reading). So it runs in the explicit system
    # scope under book isolation (db/book_scope.py), never in a narrowed or deny-all one.
    with system_scope():
        return run_loop(
            interval_seconds=args.interval_seconds,
            max_iterations=1 if args.once else None,
            scan_limit=args.scan_limit,
            run_limit=args.run_limit,
            entsog_from=args.entsog_from,
            entsog_to=args.entsog_to,
            entsog_lookback_gas_days=args.entsog_lookback_gas_days,
            entsog_point_directions=point_directions,
        )


if __name__ == "__main__":
    raise SystemExit(main())
