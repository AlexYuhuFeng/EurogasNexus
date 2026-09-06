"""Shadow research runtime application service.

The shadow runtime uses the CR-04 shared strategy evaluator over current
persisted evidence and CR-06 persisted schedule/monitor state. It has no
execution, order, nomination or external-venue code paths.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from eurogas_nexus.db.models import (
    StrategyRunRecord,
    StrategyShadowEvaluationRecord,
    StrategyShadowMonitorRecord,
    StrategyVersionRecord,
)
from eurogas_nexus.db.repositories import backtest as backtest_repository
from eurogas_nexus.db.repositories import shadow as shadow_repository
from eurogas_nexus.db.repositories import strategy_registry
from eurogas_nexus.domain.backtest.contracts import (
    BacktestDecisionSchedule,
    BacktestEconomicAssumptions,
    BacktestPeriod,
    BacktestRunDefinition,
)
from eurogas_nexus.domain.backtest.engine import evaluate_decision_event
from eurogas_nexus.domain.ontology.vocabulary import (
    ShadowAlertSeverity,
    ShadowFailureClass,
)
from eurogas_nexus.domain.shadow.schedule import next_scheduled_instant

SHADOW_ENGINE_VERSION = "shadow-engine/1"
DEFAULT_FAILURE_BLOCK_THRESHOLD = 6
DEFAULT_DEGRADED_FAILURE_THRESHOLD = 3
STALE_EVALUATION_SECONDS = 300

_FRESHNESS_MAX_AGE_SECONDS = {
    "ICE": 2 * 3600,
    "TRAYPORT": 2 * 3600,
    "EEX": 36 * 3600,
    "ICIS": 72 * 3600,
    "SAP": 72 * 3600,
    "ECB": 72 * 3600,
}


def create_shadow_monitor(
    session: Session,
    *,
    strategy_version_id: str,
    baseline_run_id: str | None,
    schedule_json: dict,
    created_by: str,
    now_utc: datetime | None = None,
    activate: bool = True,
) -> dict:
    """Validate and persist a shadow monitor; activate when requested."""

    now = _as_utc(now_utc or datetime.now(UTC))
    version = strategy_registry.get_strategy_version(session, strategy_version_id)
    if version is None:
        raise ValueError(f"Unknown strategy version: {strategy_version_id}")
    if version.status != "FROZEN":
        raise ValueError(
            f"Shadow activation requires FROZEN version; got {version.status}"
        )
    if not _supported_definition(version):
        raise ValueError("Strategy version contains unsupported component types")
    _validate_schedule(schedule_json)
    if baseline_run_id:
        baseline = session.get(StrategyRunRecord, baseline_run_id)
        if baseline is None:
            raise ValueError(f"Unknown baseline run: {baseline_run_id}")
        if baseline.strategy_version_id != strategy_version_id:
            raise ValueError("Baseline run must belong to the monitored version")

    monitor = shadow_repository.create_monitor(
        session,
        monitor_id=f"shadow-monitor-{uuid4().hex[:20]}",
        strategy_id=version.strategy_id,
        strategy_version_id=strategy_version_id,
        baseline_run_id=baseline_run_id,
        schedule_json=schedule_json,
        created_by=created_by,
        now_utc=now,
        state="DRAFT",
    )
    if activate:
        monitor = shadow_repository.activate_monitor(
            session, monitor_id=monitor.shadow_monitor_id, now_utc=now
        )
    session.flush()
    return shadow_repository.monitor_payload(monitor)


def pause_monitor(
    session: Session, *, monitor_id: str, now_utc: datetime | None = None
) -> dict:
    return shadow_repository.monitor_payload(
        shadow_repository.pause_monitor(
            session, monitor_id=monitor_id, now_utc=_as_utc(now_utc or datetime.now(UTC))
        )
    )


def resume_monitor(
    session: Session, *, monitor_id: str, now_utc: datetime | None = None
) -> dict:
    return shadow_repository.monitor_payload(
        shadow_repository.resume_monitor(
            session, monitor_id=monitor_id, now_utc=_as_utc(now_utc or datetime.now(UTC))
        )
    )


def retire_monitor(
    session: Session, *, monitor_id: str, now_utc: datetime | None = None
) -> dict:
    return shadow_repository.monitor_payload(
        shadow_repository.retire_monitor(
            session, monitor_id=monitor_id, now_utc=_as_utc(now_utc or datetime.now(UTC))
        )
    )


def run_due_shadow_evaluations(
    session: Session,
    *,
    now_utc: datetime | None = None,
    limit: int = 10,
) -> dict:
    """Claim due monitors and evaluate each once, restart-safe."""

    now = _as_utc(now_utc or datetime.now(UTC))
    monitors = shadow_repository.claim_due_monitors(
        session, now_utc=now, limit=limit
    )
    summary = {
        "due_count": len(monitors),
        "claimed_count": 0,
        "completed_count": 0,
        "blocked_count": 0,
        "failed_count": 0,
        "duplicate_claim_count": 0,
        "evaluations": [],
    }
    for monitor in monitors:
        scheduled_for = _as_utc(monitor.next_evaluation_at_utc)
        existing = shadow_repository.get_evaluation_by_schedule(
            session, monitor_id=monitor.shadow_monitor_id, scheduled_for_utc=scheduled_for
        )
        if existing is not None:
            summary["duplicate_claim_count"] += 1
            monitor.next_evaluation_at_utc = _next_after(monitor, now)
            continue
        evaluation = shadow_repository.create_evaluation(
            session,
            monitor_id=monitor.shadow_monitor_id,
            strategy_version_id=monitor.strategy_version_id,
            scheduled_for_utc=scheduled_for,
            now_utc=now,
        )
        try:
            session.flush()
        except IntegrityError:
            session.rollback()
            summary["duplicate_claim_count"] += 1
            continue
        summary["claimed_count"] += 1
        result = _evaluate_one(
            session,
            monitor=monitor,
            evaluation=evaluation,
            decision_time_utc=now,
        )
        summary["evaluations"].append(result)
        if evaluation.state == "BLOCKED":
            summary["blocked_count"] += 1
        elif evaluation.state in {"COMPLETED", "COMPLETED_WITH_WARNINGS"}:
            summary["completed_count"] += 1
        else:
            summary["failed_count"] += 1
        monitor.next_evaluation_at_utc = _next_after(monitor, now)

    session.flush()
    shadow_repository.record_heartbeat(
        session,
        now_utc=now,
        due_count=summary["due_count"],
        claimed_count=summary["claimed_count"],
        completed_count=summary["completed_count"],
        blocked_count=summary["blocked_count"],
        failed_count=summary["failed_count"],
        duplicate_claim_count=summary["duplicate_claim_count"],
        active_monitor_count=_active_monitor_count(session),
        oldest_overdue_seconds=_oldest_overdue_seconds(session, now),
    )
    return summary


def recover_stale_evaluations(
    session: Session,
    *,
    now_utc: datetime | None = None,
    stale_after_seconds: int = STALE_EVALUATION_SECONDS,
) -> int:
    now = _as_utc(now_utc or datetime.now(UTC))
    rows = shadow_repository.list_stale_running_evaluations(
        session, now_utc=now, stale_after_seconds=stale_after_seconds
    )
    for row in rows:
        row.state = "FAILED"
        row.completed_at_utc = now
        row.failure_class = ShadowFailureClass.INTERNAL_ERROR.value
        row.missing_inputs = list(
            dict.fromkeys([*row.missing_inputs, "OPERATIONAL_FAILURE:STALE_EVALUATION"])
        )
    session.flush()
    return len(rows)


def _evaluate_one(
    session: Session,
    *,
    monitor: StrategyShadowMonitorRecord,
    evaluation: StrategyShadowEvaluationRecord,
    decision_time_utc: datetime,
) -> dict:
    try:
        version = strategy_registry.get_strategy_version(
            session, monitor.strategy_version_id
        )
        if version is None:
            raise ValueError("Monitored version no longer exists")
        definition_payload = version.definition_json or {}
        economic = _economic_assumptions(definition_payload)
        decision = _as_utc(decision_time_utc)
        period = BacktestPeriod(
            start_utc=decision - timedelta(seconds=1),
            end_utc=decision + timedelta(seconds=1),
        )
        definition = BacktestRunDefinition(
            strategy_version_id=version.strategy_version_id,
            period=period,
            schedule=BacktestDecisionSchedule(decision_time_utc="00:00"),
            economic_assumptions=economic,
            deterministic_seed=monitor.shadow_monitor_id,
            experiment_id=None,
        )
        pool = backtest_repository.load_backtest_evidence_pool(
            session,
            version=version,
            period=period,
            max_lookback_seconds=economic.carry_forward_max_age_seconds,
        )
        snapshot_id = backtest_repository.create_backtest_snapshot(
            session, pool=pool, period=period, now_utc=decision
        )
        freshness_rows = _freshness_rows(pool, decision)
        stale_blockers = [
            f"DATA_STALE:{row['series']}:{int(row['age_seconds'])}s"
            for row in freshness_rows
            if row["state"] == "STALE"
        ]
        if stale_blockers:
            evaluation.state = "BLOCKED"
            evaluation.decision_time_utc = decision
            evaluation.completed_at_utc = decision
            evaluation.snapshot_id = snapshot_id
            evaluation.freshness_json = freshness_rows
            evaluation.missing_inputs = stale_blockers
            evaluation.source_systems = sorted(
                {row.source_system for row in pool.observations if row.source_system}
            )
            evaluation.result_json = {
                "outcome": "BLOCKED",
                "gross_indicative_pnl_gbp": 0.0,
                "modeled_costs_gbp": 0.0,
                "net_indicative_pnl_gbp": 0.0,
            }
            monitor.consecutive_failures += 1
            monitor.last_evaluation_at_utc = decision
            monitor.latest_evaluation_id = evaluation.shadow_evaluation_id
            monitor.health_state = "BLOCKED"
            _record_alert(
                session,
                monitor=monitor,
                evaluation=evaluation,
                alert_type="DATA_STALE",
                severity=ShadowAlertSeverity.WARNING,
                condition_key="stale-required-data",
                summary="Stale required shadow evidence blocked evaluation.",
                evidence_refs=[],
            )
            return shadow_repository.evaluation_payload(evaluation)

        event = evaluate_decision_event(
            version=version,
            pool=pool,
            definition=definition,
            run_id=evaluation.shadow_evaluation_id,
            requested_by=monitor.created_by,
            decision_sequence=1,
            decision_time_utc=decision,
            previous_cumulative_net=monitor.cumulative_shadow_pnl_gbp,
            previous_exposure=monitor.current_exposure_mwh_per_day,
        )
        _finalize_evaluation(
            session,
            monitor=monitor,
            evaluation=evaluation,
            version=version,
            event=event,
            pool=pool,
            snapshot_id=snapshot_id,
            decision=decision,
        )
        _refresh_drift(session, monitor=monitor, now_utc=decision)
    except Exception as exc:
        _mark_failed(evaluation, exc)
        _record_alert(
            session,
            monitor=monitor,
            evaluation=evaluation,
            alert_type="OPERATIONAL_FAILURE",
            severity=ShadowAlertSeverity.WARNING,
            condition_key=str(exc.__class__.__name__),
            summary=f"Shadow evaluation failed: {exc}",
            evidence_refs=[],
        )
    return shadow_repository.evaluation_payload(evaluation)


def _finalize_evaluation(
    session: Session,
    *,
    monitor: StrategyShadowMonitorRecord,
    evaluation: StrategyShadowEvaluationRecord,
    version: StrategyVersionRecord,
    event,
    pool,
    snapshot_id: str,
    decision: datetime,
) -> None:
    outcome = event.outcome
    blocked = outcome in {"BLOCKED", "SKIPPED"} or not event.allocation_targets
    if blocked:
        evaluation.state = "BLOCKED"
        monitor.consecutive_failures += 1
        _record_alert(
            session,
            monitor=monitor,
            evaluation=evaluation,
            alert_type="EVALUATION_BLOCKED",
            severity=ShadowAlertSeverity.WARNING,
            condition_key="evaluation-blocked",
            summary="Shadow evaluation was blocked; no normal candidate was produced.",
            evidence_refs=list(dict.fromkeys(event.price_evidence_refs)),
        )
    else:
        evaluation.state = (
            "COMPLETED_WITH_WARNINGS"
            if event.warnings or event.missing_inputs
            else "COMPLETED"
        )
        monitor.consecutive_failures = 0
    if monitor.consecutive_failures >= DEFAULT_FAILURE_BLOCK_THRESHOLD:
        monitor.state = "BLOCKED"
        monitor.next_evaluation_at_utc = None
    elif monitor.consecutive_failures >= DEFAULT_DEGRADED_FAILURE_THRESHOLD:
        monitor.state = "DEGRADED"

    evaluation.decision_time_utc = decision
    evaluation.completed_at_utc = decision
    evaluation.snapshot_id = snapshot_id
    evaluation.gas_day = event.gas_day
    evaluation.gas_day_start_utc = event.gas_day_start_utc
    evaluation.gas_day_end_utc = event.gas_day_end_utc
    evaluation.price_evidence_refs = event.price_evidence_refs
    evaluation.fx_evidence_refs = event.fx_evidence_refs
    evaluation.resource_evidence_refs = event.resource_evidence_refs
    evaluation.source_systems = sorted(
        {row.source_system for row in pool.observations if row.source_system}
    )
    evaluation.missing_inputs = event.missing_inputs
    evaluation.warnings = event.warnings
    evaluation.result_json = {
        "outcome": outcome,
        "weighted_score": event.weighted_score,
        "gross_indicative_pnl_gbp": event.gross_indicative_pnl_gbp,
        "modeled_costs_gbp": event.modeled_costs_gbp,
        "net_indicative_pnl_gbp": event.net_indicative_pnl_gbp,
    }
    evaluation.freshness_json = _freshness_rows(pool, decision)
    _record_evidence_alerts(session, monitor, evaluation, event)

    if blocked:
        evaluation.candidate_id = None
        monitor.last_evaluation_at_utc = decision
        monitor.latest_evaluation_id = evaluation.shadow_evaluation_id
        monitor.health_state = "BLOCKED"
        return

    targets = event.allocation_targets
    dominant = max(targets, key=lambda row: float(row.get("target_quantity_mwh_per_day") or 0))
    quantity = float(dominant.get("target_quantity_mwh_per_day") or 0)
    margin = float(dominant.get("expected_margin_gbp_mwh") or 0)
    reference = dominant.get("reference_price_gbp_mwh")
    cost = _resource_cost(version.definition_json or {})
    risk_rows = _risk_checks(session, evaluation, event, version.definition_json or {})
    risk_state = (
        "BLOCK"
        if any(row.state == "BLOCK" for row in risk_rows)
        else "WARN"
        if any(row.state == "WARN" for row in risk_rows)
        else "PASS"
    )
    evidence_state = "DEGRADED" if event.warnings else "COMPLETE"
    candidate = shadow_repository.persist_candidate(
        session,
        evaluation_id=evaluation.shadow_evaluation_id,
        monitor_id=monitor.shadow_monitor_id,
        strategy_version_id=version.strategy_version_id,
        decision_time_utc=decision,
        gas_day=event.gas_day,
        candidate_type="OCM_VS_DAY_AHEAD_ALLOCATION",
        market_context={
            "day_ahead_average_gbp_mwh": event.day_ahead_average_gbp_mwh,
            "intraday_average_gbp_mwh": event.intraday_average_gbp_mwh,
            "spread_gbp_mwh": event.intraday_vs_day_ahead_spread_gbp_mwh,
            "gas_day": event.gas_day,
        },
        hypothetical_direction=f"HYPOTHETICAL_{dominant.get('market_bucket', 'ALLOCATION')}",
        hypothetical_quantity_mwh_per_day=quantity,
        expected_indicative_margin_gbp_mwh=margin,
        expected_indicative_pnl_gbp=event.net_indicative_pnl_gbp,
        reference_price_gbp_mwh=reference,
        all_in_cost_gbp_mwh=cost,
        risk_state=risk_state,
        evidence_state=evidence_state,
        explanation_codes=[
            event.candidate_action_for_review or "REVIEW_STRATEGY_OUTPUT",
            *[
                item
                for target in targets
                for item in target.get("rationale", [])
                if isinstance(item, str)
            ],
        ],
        warnings=event.warnings,
        blocker_references=[],
    )
    evaluation.candidate_id = candidate.candidate_id
    shadow_repository.create_outcome(
        session,
        candidate_id=candidate.candidate_id,
        evaluation_id=evaluation.shadow_evaluation_id,
        pnl_basis="MARK_TO_MODEL",
        gross=event.gross_indicative_pnl_gbp,
        modeled_costs=event.modeled_costs_gbp,
        net=event.net_indicative_pnl_gbp,
        settlement_refs=[],
        note="Initial mark-to-model outcome from shadow evaluation.",
        now_utc=decision,
    )
    monitor.cumulative_shadow_pnl_gbp = round(
        monitor.cumulative_shadow_pnl_gbp + event.net_indicative_pnl_gbp, 4
    )
    monitor.current_exposure_mwh_per_day = event.ending_exposure_mwh_per_day
    monitor.last_evaluation_at_utc = decision
    monitor.latest_evaluation_id = evaluation.shadow_evaluation_id
    monitor.health_state = "OK"
    _record_alert(
        session,
        monitor=monitor,
        evaluation=evaluation,
        alert_type="RISK_BLOCK",
        severity=ShadowAlertSeverity.CRITICAL,
        condition_key="risk-block",
        summary="Shadow risk control blocked or constrained the candidate.",
        evidence_refs=[candidate.candidate_id],
    ) if risk_state == "BLOCK" else None


def _risk_checks(session, evaluation, event, definition_json: dict):
    rows = []
    controls = (definition_json.get("risk_controls") or {}).copy()
    max_ocm = float(controls.get("max_ocm_allocation_pct") or 80.0)
    min_da = float(controls.get("min_day_ahead_allocation_pct") or 10.0)
    min_margin = controls.get("min_expected_margin_gbp_mwh")
    ocm = max(
        (
            float(row.get("target_allocation_pct") or 0)
            for row in event.allocation_targets
            if row.get("market_bucket") == "ICE_OCM"
        ),
        default=0.0,
    )
    rows.append(
        shadow_repository.persist_risk_check(
            session,
            evaluation_id=evaluation.shadow_evaluation_id,
            control_id="OCM_ALLOCATION_CLAMP",
            observed_value=ocm,
            limit_value=max_ocm,
            state="WARN" if abs(ocm - max_ocm) < 1e-9 else "PASS",
            severity="WARNING",
            explanation=f"OCM allocation {ocm}% against {max_ocm}% limit.",
        )
    )
    da = max(
        (
            float(row.get("target_allocation_pct") or 0)
            for row in event.allocation_targets
            if row.get("market_bucket") == "DAY_AHEAD"
        ),
        default=0.0,
    )
    rows.append(
        shadow_repository.persist_risk_check(
            session,
            evaluation_id=evaluation.shadow_evaluation_id,
            control_id="MIN_DAY_AHEAD_ALLOCATION",
            observed_value=da,
            limit_value=min_da,
            state="WARN" if da < min_da else "PASS",
            severity="WARNING",
            explanation=f"Day-ahead allocation {da}% against {min_da}% floor.",
        )
    )
    stop_loss = "SHADOW_RUN_STOP_LOSS_TRIGGERED" in event.warnings
    rows.append(
        shadow_repository.persist_risk_check(
            session,
            evaluation_id=evaluation.shadow_evaluation_id,
            control_id="SHADOW_STOP_LOSS",
            observed_value=event.cumulative_net_indicative_pnl_gbp,
            limit_value=controls.get("stop_shadow_run_loss_gbp"),
            state="BLOCK" if stop_loss else "PASS",
            severity="CRITICAL",
            explanation=(
                "Shadow stop-loss triggered."
                if stop_loss
                else "Cumulative shadow PnL is inside stop-loss policy."
            ),
        )
    )
    if min_margin is not None:
        margins = [
            float(row.get("expected_margin_gbp_mwh") or 0)
            for row in event.allocation_targets
        ]
        below = any(value < float(min_margin) for value in margins)
        rows.append(
            shadow_repository.persist_risk_check(
                session,
                evaluation_id=evaluation.shadow_evaluation_id,
                control_id="EXPECTED_MARGIN_FLOOR",
                observed_value=min(margins, default=0.0),
                limit_value=float(min_margin),
                state="WARN" if below else "PASS",
                severity="WARNING",
                explanation="Expected margin floor check.",
            )
        )
    return rows


def _record_evidence_alerts(session, monitor, evaluation, event) -> None:
    for code in event.missing_inputs:
        if "PRICE" in code or "FX" in code or "SOURCE" in code:
            _record_alert(
                session,
                monitor=monitor,
                evaluation=evaluation,
                alert_type="DATA_MISSING",
                severity=ShadowAlertSeverity.WARNING,
                condition_key=code.split(":", 1)[0],
                summary=f"Missing required shadow evidence: {code}",
                evidence_refs=[],
            )
    for warning in event.warnings:
        code = warning.split(":", 1)[0]
        if "STALE" in code or "UNAVAILABLE" in code:
            _record_alert(
                session,
                monitor=monitor,
                evaluation=evaluation,
                alert_type="DATA_STALE",
                severity=ShadowAlertSeverity.WARNING,
                condition_key=code,
                summary=f"Stale shadow evidence: {warning}",
                evidence_refs=[],
            )
        elif "FALLBACK" in code:
            _record_alert(
                session,
                monitor=monitor,
                evaluation=evaluation,
                alert_type="SOURCE_FALLBACK",
                severity=ShadowAlertSeverity.WARNING,
                condition_key=code,
                summary=f"Approved fallback source used: {warning}",
                evidence_refs=[],
            )


def _refresh_drift(
    session: Session, *, monitor: StrategyShadowMonitorRecord, now_utc: datetime
) -> None:
    evaluations = shadow_repository.list_evaluations(
        session, monitor_id=monitor.shadow_monitor_id, limit=10
    )
    completed = [
        row
        for row in evaluations
        if row.get("state") in {"COMPLETED", "COMPLETED_WITH_WARNINGS"}
    ]
    blocked = [row for row in evaluations if row.get("state") == "BLOCKED"]
    sample = len(completed) + len(blocked)
    if sample < 3:
        state = "INSUFFICIENT_DATA"
        metrics = []
        explanation = "Fewer than three shadow evaluations."
    else:
        candidate_rate = len(completed) / sample
        blocked_rate = len(blocked) / sample
        fallback_rate = sum(
            1
            for row in evaluations
            if any(
                str(item).startswith("SOURCE_FALLBACK")
                or str(item).startswith("CARRY_FORWARD")
                for item in row.get("warnings", [])
            )
        ) / sample
        margins = [
            float(row.get("result", {}).get("net_indicative_pnl_gbp") or 0)
            for row in completed
        ]
        current_mean = sum(margins) / len(margins) if margins else 0.0
        baseline = _baseline_metrics(session, monitor.baseline_run_id)
        metrics = [
            {
                "dimension": "behavior",
                "metric": "candidate_frequency",
                "baseline": baseline.get("candidate_rate"),
                "current": round(candidate_rate, 4),
                "state": "NORMAL",
                "explanation": "Candidate frequency versus baseline.",
            },
            {
                "dimension": "performance",
                "metric": "mean_candidate_margin",
                "baseline": baseline.get("average_margin"),
                "current": round(current_mean, 4),
                "state": "NORMAL",
                "explanation": "Mean net indicative PnL per candidate.",
            },
            {
                "dimension": "operational",
                "metric": "blocked_rate",
                "baseline": baseline.get("blocked_rate"),
                "current": round(blocked_rate, 4),
                "state": "NORMAL",
                "explanation": "Blocked evaluation rate.",
            },
            {
                "dimension": "operational",
                "metric": "fallback_rate",
                "baseline": 0.0,
                "current": round(fallback_rate, 4),
                "state": "NORMAL",
                "explanation": "Explicit fallback usage rate.",
            },
        ]
        metrics = _classify_metrics(metrics)
        states = [row["state"] for row in metrics]
        state = (
            "MATERIAL"
            if "MATERIAL" in states
            else "WATCH"
            if "WATCH" in states
            else "NORMAL"
        )
        explanation = f"Drift snapshot over last {sample} evaluations."
    shadow_repository.create_drift_snapshot(
        session,
        monitor_id=monitor.shadow_monitor_id,
        baseline_run_id=monitor.baseline_run_id,
        window_json={"evaluations": sample, "basis": "last-10-evaluations"},
        state=state,
        metrics_json=metrics,
        sample_size=sample,
        explanation=explanation,
        now_utc=now_utc,
    )
    if state in {"WATCH", "MATERIAL"}:
        _record_alert(
            session,
            monitor=monitor,
            evaluation=None,
            alert_type="BEHAVIOR_DRIFT" if "behavior" in str(metrics) else "PERFORMANCE_DRIFT",
            severity=ShadowAlertSeverity.WARNING,
            condition_key=state,
            summary=f"Shadow drift state {state} with baseline {monitor.baseline_run_id}.",
            evidence_refs=[],
        )


def _classify_metrics(metrics: list[dict]) -> list[dict]:
    for row in metrics:
        baseline = row.get("baseline")
        current = row.get("current")
        if (
            baseline is None
            or current is None
            or not isinstance(baseline, (int, float))
            or not isinstance(current, (int, float))
        ):
            row["state"] = "INSUFFICIENT_DATA"
            continue
        delta = abs(float(current) - float(baseline))
        if row["metric"] == "candidate_frequency" and delta >= 0.25:
            row["state"] = "MATERIAL" if delta >= 0.5 else "WATCH"
        elif (
            row["metric"] == "mean_candidate_margin"
            and delta >= max(0.5, abs(float(baseline)) * 0.5)
        ):
            row["state"] = "MATERIAL" if delta >= abs(float(baseline)) * 1.0 else "WATCH"
        elif row["metric"] == "blocked_rate" and delta >= 0.2:
            row["state"] = "MATERIAL" if delta >= 0.4 else "WATCH"
    return metrics


def _baseline_metrics(session: Session, baseline_run_id: str | None) -> dict:
    if not baseline_run_id:
        return {}
    run = session.get(StrategyRunRecord, baseline_run_id)
    if run is None:
        return {}
    metrics = (run.result_snapshot or {}).get("metrics", {})
    evaluation_count = int(metrics.get("evaluation_count") or 0)
    return {
        "candidate_rate": (
            round(
                int(metrics.get("candidate_decision_count") or 0) / evaluation_count,
                4,
            )
            if evaluation_count
            else None
        ),
        "average_margin": metrics.get("average_margin_gbp_mwh"),
        "blocked_rate": (
            round(int(metrics.get("blocked_decision_count") or 0) / evaluation_count, 4)
            if evaluation_count
            else None
        ),
    }


def _record_alert(
    session: Session,
    *,
    monitor: StrategyShadowMonitorRecord,
    evaluation: StrategyShadowEvaluationRecord | None,
    alert_type: str,
    severity,
    condition_key: str,
    summary: str,
    evidence_refs: list[str],
) -> None:
    fingerprint = (
        f"{monitor.shadow_monitor_id}|{alert_type}|{condition_key}"[:256]
    )
    shadow_repository.upsert_alert(
        session,
        monitor_id=monitor.shadow_monitor_id,
        evaluation_id=evaluation.shadow_evaluation_id if evaluation else None,
        alert_type=alert_type,
        severity=severity.value,
        fingerprint=fingerprint,
        summary=summary,
        evidence_refs=evidence_refs,
        now_utc=datetime.now(UTC),
    )


def _freshness_rows(pool, decision: datetime) -> list[dict]:
    rows = []
    latest_by_name: dict[str, datetime] = {}
    for row in pool.observations:
        key = row.price_name.upper()
        current = latest_by_name.get(key)
        if current is None or row.observed_at_utc > current:
            latest_by_name[key] = row.observed_at_utc
    for name, observed in sorted(latest_by_name.items()):
        age = max(0.0, (decision - _as_utc(observed)).total_seconds())
        max_age = next(
            (
                seconds
                for prefix, seconds in _FRESHNESS_MAX_AGE_SECONDS.items()
                if name.startswith(prefix)
            ),
            24 * 3600,
        )
        rows.append(
            {
                "series": name,
                "state": "FRESH" if age <= max_age else "STALE",
                "age_seconds": round(age, 1),
                "max_age_seconds": max_age,
                "latest_observed_at_utc": _as_utc(observed).isoformat(),
            }
        )
    if not rows:
        rows.append(
            {
                "series": "PRICE_EVIDENCE",
                "state": "MISSING",
                "age_seconds": None,
                "max_age_seconds": None,
                "latest_observed_at_utc": None,
            }
        )
    return rows


def _mark_failed(evaluation, exc: Exception) -> None:
    evaluation.state = "FAILED"
    evaluation.completed_at_utc = datetime.now(UTC)
    if isinstance(exc, SQLAlchemyError):
        evaluation.failure_class = ShadowFailureClass.TRANSIENT_INFRASTRUCTURE.value
    elif isinstance(exc, ValueError):
        evaluation.failure_class = ShadowFailureClass.DOMAIN_BLOCKER.value
    else:
        evaluation.failure_class = ShadowFailureClass.INTERNAL_ERROR.value
    evaluation.result_json = {"error": str(exc)[:2000]}


def _supported_definition(version: StrategyVersionRecord) -> bool:
    components = (version.definition_json or {}).get("components", [])
    supported = {
        "OCM_VS_DAY_AHEAD",
        "MEAN_REVERSION",
        "BEST_BUCKETS",
        "SCORING",
        "WEIGHTED_COMBINATION",
    }
    return bool(components) and all(
        component.get("component_type") in supported for component in components
    )


def _validate_schedule(schedule: dict) -> None:
    schedule_type = str(schedule.get("type", ""))
    if schedule_type == "INTERVAL":
        if int(schedule.get("interval_seconds") or 0) <= 0:
            raise ValueError("INTERVAL schedule requires positive interval_seconds")
    elif schedule_type == "DAILY_AT":
        value = str(schedule.get("daily_at_utc", ""))
        if len(value.split(":")) != 2:
            raise ValueError("DAILY_AT schedule requires HH:MM UTC")
    else:
        raise ValueError(f"Unsupported shadow schedule type: {schedule_type}")
    missed = str(schedule.get("missed_policy", "SKIP"))
    if missed not in {"SKIP", "RUN_LATEST_ONLY", "CATCH_UP_LIMITED"}:
        raise ValueError(f"Unsupported missed policy: {missed}")


def _economic_assumptions(definition: dict) -> BacktestEconomicAssumptions:
    raw = definition.get("economic_assumptions") or {}
    return BacktestEconomicAssumptions(
        fill_price_policy=raw.get("fill_price_policy", "NEXT_ELIGIBLE"),
        missing_data_policy=raw.get("missing_data_policy", "FAIL"),
        carry_forward_max_age_seconds=int(
            raw.get("carry_forward_max_age_seconds", 86_400)
        ),
        require_historical_fx=bool(raw.get("require_historical_fx", True)),
        fallback_sources=dict(raw.get("fallback_sources") or {}),
        cost_components=list(raw.get("cost_components") or []),
    )


def _resource_cost(definition: dict) -> float | None:
    resources = definition.get("resource_contexts") or []
    if not resources:
        return None
    return float(resources[0].get("all_in_cost_gbp_mwh") or 0.0)


def _next_after(monitor: StrategyShadowMonitorRecord, now: datetime) -> datetime | None:
    return next_scheduled_instant(
        schedule=monitor.schedule_json,
        activated_at=_as_utc(monitor.activated_at_utc or monitor.created_at_utc),
        after=_as_utc(now),
    )


def _active_monitor_count(session: Session) -> int:
    from sqlalchemy import func

    return (
        session.query(func.count(StrategyShadowMonitorRecord.shadow_monitor_id))
        .filter(StrategyShadowMonitorRecord.state == "ACTIVE")
        .scalar()
        or 0
    )


def _oldest_overdue_seconds(
    session: Session, now: datetime
) -> float | None:
    from sqlalchemy import func

    oldest = (
        session.query(func.min(StrategyShadowMonitorRecord.next_evaluation_at_utc))
        .filter(
            StrategyShadowMonitorRecord.state == "ACTIVE",
            StrategyShadowMonitorRecord.next_evaluation_at_utc <= now,
        )
        .scalar()
    )
    if oldest is None:
        return None
    return round(max(0.0, (now - _as_utc(oldest)).total_seconds()), 1)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
