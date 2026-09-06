"""Repository operations for the shadow research runtime."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import func
from sqlalchemy.orm import Session

from eurogas_nexus.db.models import (
    StrategyShadowAlertRecord,
    StrategyShadowCandidateRecord,
    StrategyShadowDriftSnapshotRecord,
    StrategyShadowEvaluationRecord,
    StrategyShadowMonitorRecord,
    StrategyShadowOutcomeRecord,
    StrategyShadowRiskCheckRecord,
    StrategyShadowSchedulerHeartbeatRecord,
)
from eurogas_nexus.domain.shadow.schedule import next_scheduled_instant


class ShadowRepositoryError(ValueError):
    """Domain failure in shadow persistence."""


def create_monitor(
    session: Session,
    *,
    monitor_id: str,
    strategy_id: str,
    strategy_version_id: str,
    baseline_run_id: str | None,
    schedule_json: dict,
    created_by: str,
    now_utc: datetime,
    state: str = "DRAFT",
) -> StrategyShadowMonitorRecord:
    if session.get(StrategyShadowMonitorRecord, monitor_id) is not None:
        raise ShadowRepositoryError(f"Shadow monitor already exists: {monitor_id}")
    row = StrategyShadowMonitorRecord(
        shadow_monitor_id=monitor_id,
        strategy_id=strategy_id,
        strategy_version_id=strategy_version_id,
        baseline_run_id=baseline_run_id,
        state=state,
        schedule_json=schedule_json,
        created_by=created_by,
        created_at_utc=now_utc,
        activated_at_utc=None,
        paused_at_utc=None,
        retired_at_utc=None,
        last_evaluation_at_utc=None,
        next_evaluation_at_utc=None,
        latest_evaluation_id=None,
        consecutive_failures=0,
        health_state="OK",
        cumulative_shadow_pnl_gbp=0.0,
        current_exposure_mwh_per_day=0.0,
        research_only=True,
    )
    session.add(row)
    session.flush()
    return row


def get_monitor(
    session: Session, monitor_id: str
) -> StrategyShadowMonitorRecord | None:
    return session.get(StrategyShadowMonitorRecord, monitor_id)


def list_monitors(session: Session, *, state: str | None = None) -> list[dict]:
    query = session.query(StrategyShadowMonitorRecord)
    if state:
        query = query.filter(StrategyShadowMonitorRecord.state == state.upper())
    rows = query.order_by(StrategyShadowMonitorRecord.created_at_utc.desc()).all()
    return [monitor_payload(row) for row in rows]


def activate_monitor(
    session: Session,
    *,
    monitor_id: str,
    now_utc: datetime,
) -> StrategyShadowMonitorRecord:
    row = get_monitor(session, monitor_id)
    if row is None:
        raise ShadowRepositoryError(f"Unknown monitor: {monitor_id}")
    if row.state not in {"DRAFT", "PAUSED", "BLOCKED"}:
        raise ShadowRepositoryError(f"Monitor {row.state} cannot be activated")
    row.state = "ACTIVE"
    row.activated_at_utc = now_utc
    row.paused_at_utc = None
    row.next_evaluation_at_utc = next_scheduled_instant(
        schedule=row.schedule_json,
        activated_at=row.activated_at_utc,
        after=now_utc,
    )
    row.health_state = "OK"
    session.flush()
    return row


def pause_monitor(
    session: Session,
    *,
    monitor_id: str,
    now_utc: datetime,
) -> StrategyShadowMonitorRecord:
    row = get_monitor(session, monitor_id)
    if row is None:
        raise ShadowRepositoryError(f"Unknown monitor: {monitor_id}")
    if row.state != "ACTIVE":
        raise ShadowRepositoryError(f"Only ACTIVE monitors can pause; got {row.state}")
    row.state = "PAUSED"
    row.paused_at_utc = now_utc
    row.next_evaluation_at_utc = None
    session.flush()
    return row


def resume_monitor(
    session: Session,
    *,
    monitor_id: str,
    now_utc: datetime,
) -> StrategyShadowMonitorRecord:
    return activate_monitor(session, monitor_id=monitor_id, now_utc=now_utc)


def retire_monitor(
    session: Session,
    *,
    monitor_id: str,
    now_utc: datetime,
) -> StrategyShadowMonitorRecord:
    row = get_monitor(session, monitor_id)
    if row is None:
        raise ShadowRepositoryError(f"Unknown monitor: {monitor_id}")
    row.state = "RETIRED"
    row.retired_at_utc = now_utc
    row.next_evaluation_at_utc = None
    session.flush()
    return row


def claim_due_monitors(
    session: Session,
    *,
    now_utc: datetime,
    limit: int = 10,
) -> list[StrategyShadowMonitorRecord]:
    query = (
        session.query(StrategyShadowMonitorRecord)
        .filter(StrategyShadowMonitorRecord.state == "ACTIVE")
        .filter(StrategyShadowMonitorRecord.next_evaluation_at_utc <= now_utc)
        .order_by(StrategyShadowMonitorRecord.next_evaluation_at_utc)
        .limit(max(1, min(limit, 100)))
        .with_for_update(skip_locked=True)
    )
    return list(query.all())


def create_evaluation(
    session: Session,
    *,
    monitor_id: str,
    strategy_version_id: str,
    scheduled_for_utc: datetime,
    now_utc: datetime,
) -> StrategyShadowEvaluationRecord:
    row = StrategyShadowEvaluationRecord(
        shadow_evaluation_id=f"shadow-eval-{uuid4().hex[:20]}",
        shadow_monitor_id=monitor_id,
        strategy_version_id=strategy_version_id,
        scheduled_for_utc=scheduled_for_utc,
        started_at_utc=now_utc,
        decision_time_utc=None,
        completed_at_utc=None,
        state="RUNNING",
        gas_day=None,
        gas_day_start_utc=None,
        gas_day_end_utc=None,
        snapshot_id=None,
        candidate_id=None,
        price_evidence_refs=[],
        fx_evidence_refs=[],
        resource_evidence_refs=[],
        source_systems=[],
        freshness_json=[],
        missing_inputs=[],
        warnings=[],
        result_json=None,
        failure_class=None,
        retry_count=0,
        research_only=True,
        human_review_required=True,
    )
    session.add(row)
    session.flush()
    return row


def get_evaluation(
    session: Session, evaluation_id: str
) -> StrategyShadowEvaluationRecord | None:
    return session.get(StrategyShadowEvaluationRecord, evaluation_id)


def get_evaluation_by_schedule(
    session: Session,
    *,
    monitor_id: str,
    scheduled_for_utc: datetime,
) -> StrategyShadowEvaluationRecord | None:
    return (
        session.query(StrategyShadowEvaluationRecord)
        .filter(
            StrategyShadowEvaluationRecord.shadow_monitor_id == monitor_id,
            StrategyShadowEvaluationRecord.scheduled_for_utc == scheduled_for_utc,
        )
        .one_or_none()
    )


def list_evaluations(
    session: Session,
    *,
    monitor_id: str,
    limit: int = 100,
) -> list[dict]:
    rows = (
        session.query(StrategyShadowEvaluationRecord)
        .filter(StrategyShadowEvaluationRecord.shadow_monitor_id == monitor_id)
        .order_by(StrategyShadowEvaluationRecord.scheduled_for_utc.desc())
        .limit(max(1, min(limit, 500)))
        .all()
    )
    return [evaluation_payload(row) for row in rows]


def list_stale_running_evaluations(
    session: Session,
    *,
    now_utc: datetime,
    stale_after_seconds: int = 300,
) -> list[StrategyShadowEvaluationRecord]:
    from datetime import timedelta

    return (
        session.query(StrategyShadowEvaluationRecord)
        .filter(StrategyShadowEvaluationRecord.state == "RUNNING")
        .filter(
            StrategyShadowEvaluationRecord.started_at_utc
            < now_utc - timedelta(seconds=stale_after_seconds)
        )
        .all()
    )


def persist_candidate(
    session: Session,
    *,
    evaluation_id: str,
    monitor_id: str,
    strategy_version_id: str,
    decision_time_utc: datetime,
    gas_day: str,
    candidate_type: str,
    market_context: dict,
    hypothetical_direction: str,
    hypothetical_quantity_mwh_per_day: float,
    expected_indicative_margin_gbp_mwh: float,
    expected_indicative_pnl_gbp: float,
    reference_price_gbp_mwh: float | None,
    all_in_cost_gbp_mwh: float | None,
    risk_state: str,
    evidence_state: str,
    explanation_codes: list[str],
    warnings: list[str],
    blocker_references: list[str],
) -> StrategyShadowCandidateRecord:
    row = StrategyShadowCandidateRecord(
        candidate_id=f"shadow-candidate-{uuid4().hex[:20]}",
        shadow_evaluation_id=evaluation_id,
        shadow_monitor_id=monitor_id,
        strategy_version_id=strategy_version_id,
        decision_time_utc=decision_time_utc,
        gas_day=gas_day,
        candidate_type=candidate_type,
        market_context=market_context,
        hypothetical_direction=hypothetical_direction,
        hypothetical_quantity_mwh_per_day=hypothetical_quantity_mwh_per_day,
        expected_indicative_margin_gbp_mwh=expected_indicative_margin_gbp_mwh,
        expected_indicative_pnl_gbp=expected_indicative_pnl_gbp,
        reference_price_gbp_mwh=reference_price_gbp_mwh,
        all_in_cost_gbp_mwh=all_in_cost_gbp_mwh,
        risk_state=risk_state,
        evidence_state=evidence_state,
        explanation_codes=explanation_codes,
        warnings=warnings,
        blocker_references=blocker_references,
        research_only=True,
    )
    session.add(row)
    session.flush()
    return row


def get_candidate(
    session: Session, candidate_id: str
) -> StrategyShadowCandidateRecord | None:
    return session.get(StrategyShadowCandidateRecord, candidate_id)


def candidate_payload(row: StrategyShadowCandidateRecord) -> dict:
    return {
        "candidate_id": row.candidate_id,
        "shadow_evaluation_id": row.shadow_evaluation_id,
        "shadow_monitor_id": row.shadow_monitor_id,
        "strategy_version_id": row.strategy_version_id,
        "decision_time_utc": _iso(row.decision_time_utc),
        "gas_day": row.gas_day,
        "candidate_type": row.candidate_type,
        "market_context": row.market_context or {},
        "hypothetical_direction": row.hypothetical_direction,
        "hypothetical_quantity_mwh_per_day": row.hypothetical_quantity_mwh_per_day,
        "expected_indicative_margin_gbp_mwh": row.expected_indicative_margin_gbp_mwh,
        "expected_indicative_pnl_gbp": row.expected_indicative_pnl_gbp,
        "reference_price_gbp_mwh": row.reference_price_gbp_mwh,
        "all_in_cost_gbp_mwh": row.all_in_cost_gbp_mwh,
        "risk_state": row.risk_state,
        "evidence_state": row.evidence_state,
        "explanation_codes": row.explanation_codes or [],
        "warnings": row.warnings or [],
        "blocker_references": row.blocker_references or [],
        "research_only": row.research_only,
    }


def persist_risk_check(
    session: Session,
    *,
    evaluation_id: str,
    control_id: str,
    observed_value: float | None,
    limit_value: float | None,
    state: str,
    severity: str,
    explanation: str,
) -> StrategyShadowRiskCheckRecord:
    row = StrategyShadowRiskCheckRecord(
        risk_check_id=f"shadow-risk-{uuid4().hex[:20]}",
        shadow_evaluation_id=evaluation_id,
        control_id=control_id,
        observed_value=observed_value,
        limit_value=limit_value,
        state=state,
        severity=severity,
        explanation=explanation,
        research_only=True,
    )
    session.add(row)
    session.flush()
    return row


def list_risk_checks(
    session: Session, evaluation_id: str
) -> list[dict]:
    rows = (
        session.query(StrategyShadowRiskCheckRecord)
        .filter(StrategyShadowRiskCheckRecord.shadow_evaluation_id == evaluation_id)
        .order_by(StrategyShadowRiskCheckRecord.control_id)
        .all()
    )
    return [risk_check_payload(row) for row in rows]


def create_outcome(
    session: Session,
    *,
    candidate_id: str,
    evaluation_id: str,
    pnl_basis: str,
    gross: float,
    modeled_costs: float,
    net: float,
    settlement_refs: list[str],
    note: str,
    now_utc: datetime,
) -> StrategyShadowOutcomeRecord:
    row = StrategyShadowOutcomeRecord(
        outcome_id=f"shadow-outcome-{uuid4().hex[:20]}",
        candidate_id=candidate_id,
        shadow_evaluation_id=evaluation_id,
        state="OPEN",
        pnl_basis=pnl_basis,
        gross_indicative_pnl_gbp=gross,
        modeled_costs_gbp=modeled_costs,
        net_indicative_pnl_gbp=net,
        settlement_evidence_refs=settlement_refs,
        maturation_note=note,
        created_at_utc=now_utc,
        matured_at_utc=None,
        research_only=True,
    )
    session.add(row)
    session.flush()
    return row


def mature_outcome(
    session: Session,
    *,
    outcome_id: str,
    pnl_basis: str,
    gross: float,
    modeled_costs: float,
    net: float,
    settlement_refs: list[str],
    note: str,
    now_utc: datetime,
) -> StrategyShadowOutcomeRecord:
    row = session.get(StrategyShadowOutcomeRecord, outcome_id)
    if row is None:
        raise ShadowRepositoryError(f"Unknown outcome: {outcome_id}")
    row.state = "MATURED"
    row.pnl_basis = pnl_basis
    row.gross_indicative_pnl_gbp = gross
    row.modeled_costs_gbp = modeled_costs
    row.net_indicative_pnl_gbp = net
    row.settlement_evidence_refs = settlement_refs
    row.maturation_note = note
    row.matured_at_utc = now_utc
    session.flush()
    return row


def list_open_outcomes(
    session: Session,
) -> list[StrategyShadowOutcomeRecord]:
    return (
        session.query(StrategyShadowOutcomeRecord)
        .filter(StrategyShadowOutcomeRecord.state == "OPEN")
        .all()
    )


def upsert_alert(
    session: Session,
    *,
    monitor_id: str,
    evaluation_id: str | None,
    alert_type: str,
    severity: str,
    fingerprint: str,
    summary: str,
    evidence_refs: list[str],
    now_utc: datetime,
) -> tuple[StrategyShadowAlertRecord, bool]:
    row = (
        session.query(StrategyShadowAlertRecord)
        .filter(StrategyShadowAlertRecord.fingerprint == fingerprint)
        .one_or_none()
    )
    created = False
    if row is None:
        row = StrategyShadowAlertRecord(
            alert_id=f"shadow-alert-{uuid4().hex[:20]}",
            shadow_monitor_id=monitor_id,
            shadow_evaluation_id=evaluation_id,
            alert_type=alert_type,
            severity=severity,
            state="OPEN",
            fingerprint=fingerprint,
            summary=summary,
            evidence_refs=evidence_refs,
            first_seen_at_utc=now_utc,
            last_seen_at_utc=now_utc,
            occurrence_count=1,
            acknowledged_at_utc=None,
            acknowledged_by=None,
            resolved_at_utc=None,
            research_only=True,
        )
        session.add(row)
        created = True
    else:
        if row.state == "RESOLVED":
            # Recurrence starts a new episode.
            row.state = "OPEN"
            row.occurrence_count = 1
            row.acknowledged_at_utc = None
            row.acknowledged_by = None
            row.resolved_at_utc = None
            row.first_seen_at_utc = now_utc
        else:
            row.occurrence_count += 1
        row.last_seen_at_utc = now_utc
        row.shadow_evaluation_id = evaluation_id
        row.summary = summary
        row.evidence_refs = list(dict.fromkeys([*row.evidence_refs, *evidence_refs]))
    session.flush()
    return row, created


def list_alerts(
    session: Session,
    *,
    state: str | None = None,
    severity: str | None = None,
    monitor_id: str | None = None,
    limit: int = 100,
) -> list[dict]:
    query = session.query(StrategyShadowAlertRecord)
    if state:
        query = query.filter(StrategyShadowAlertRecord.state == state.upper())
    if severity:
        query = query.filter(StrategyShadowAlertRecord.severity == severity.upper())
    if monitor_id:
        query = query.filter(StrategyShadowAlertRecord.shadow_monitor_id == monitor_id)
    rows = query.order_by(StrategyShadowAlertRecord.last_seen_at_utc.desc()).limit(
        max(1, min(limit, 500))
    )
    return [alert_payload(row) for row in rows]


def acknowledge_alert(
    session: Session,
    *,
    alert_id: str,
    acknowledged_by: str,
    now_utc: datetime,
) -> dict:
    row = session.get(StrategyShadowAlertRecord, alert_id)
    if row is None:
        raise ShadowRepositoryError(f"Unknown shadow alert: {alert_id}")
    if row.state == "RESOLVED":
        raise ShadowRepositoryError("Resolved alerts cannot be acknowledged")
    row.state = "ACKNOWLEDGED"
    row.acknowledged_at_utc = now_utc
    row.acknowledged_by = acknowledged_by
    session.flush()
    return alert_payload(row)


def resolve_alert(
    session: Session,
    *,
    fingerprint: str,
    now_utc: datetime,
) -> None:
    row = (
        session.query(StrategyShadowAlertRecord)
        .filter(StrategyShadowAlertRecord.fingerprint == fingerprint)
        .one_or_none()
    )
    if row is not None and row.state != "RESOLVED":
        row.state = "RESOLVED"
        row.resolved_at_utc = now_utc
        session.flush()


def create_drift_snapshot(
    session: Session,
    *,
    monitor_id: str,
    baseline_run_id: str | None,
    window_json: dict,
    state: str,
    metrics_json: list[dict],
    sample_size: int,
    explanation: str,
    now_utc: datetime,
) -> StrategyShadowDriftSnapshotRecord:
    row = StrategyShadowDriftSnapshotRecord(
        drift_snapshot_id=f"shadow-drift-{uuid4().hex[:20]}",
        shadow_monitor_id=monitor_id,
        baseline_run_id=baseline_run_id,
        observation_window_json=window_json,
        state=state,
        metrics_json=metrics_json,
        sample_size=sample_size,
        explanation=explanation,
        created_at_utc=now_utc,
        research_only=True,
    )
    session.add(row)
    session.flush()
    return row


def list_drift_snapshots(
    session: Session,
    *,
    monitor_id: str,
    limit: int = 20,
) -> list[dict]:
    rows = (
        session.query(StrategyShadowDriftSnapshotRecord)
        .filter(StrategyShadowDriftSnapshotRecord.shadow_monitor_id == monitor_id)
        .order_by(StrategyShadowDriftSnapshotRecord.created_at_utc.desc())
        .limit(max(1, min(limit, 100)))
        .all()
    )
    return [drift_payload(row) for row in rows]


def record_heartbeat(
    session: Session,
    *,
    now_utc: datetime,
    due_count: int,
    claimed_count: int,
    completed_count: int,
    blocked_count: int,
    failed_count: int,
    duplicate_claim_count: int,
    active_monitor_count: int,
    oldest_overdue_seconds: float | None,
) -> StrategyShadowSchedulerHeartbeatRecord:
    row = session.get(StrategyShadowSchedulerHeartbeatRecord, "primary")
    if row is None:
        row = StrategyShadowSchedulerHeartbeatRecord(
            heartbeat_id="primary",
            last_heartbeat_at_utc=now_utc,
            last_scan_at_utc=now_utc,
            due_count=0,
            claimed_count=0,
            completed_count=0,
            blocked_count=0,
            failed_count=0,
            duplicate_claim_count=0,
            active_monitor_count=0,
            oldest_overdue_seconds=None,
        )
        session.add(row)
    row.last_heartbeat_at_utc = now_utc
    row.last_scan_at_utc = now_utc
    row.due_count = due_count
    row.claimed_count = claimed_count
    row.completed_count = completed_count
    row.blocked_count = blocked_count
    row.failed_count = failed_count
    row.duplicate_claim_count = duplicate_claim_count
    row.active_monitor_count = active_monitor_count
    row.oldest_overdue_seconds = oldest_overdue_seconds
    session.flush()
    return row


def runtime_status_payload(session: Session) -> dict:
    row = session.get(StrategyShadowSchedulerHeartbeatRecord, "primary")
    active = (
        session.query(func.count(StrategyShadowMonitorRecord.shadow_monitor_id))
        .filter(StrategyShadowMonitorRecord.state == "ACTIVE")
        .scalar()
        or 0
    )
    due = (
        session.query(func.count(StrategyShadowMonitorRecord.shadow_monitor_id))
        .filter(
            StrategyShadowMonitorRecord.state == "ACTIVE",
            StrategyShadowMonitorRecord.next_evaluation_at_utc <= datetime.now(UTC),
        )
        .scalar()
        or 0
    )
    return {
        "scheduler": "healthy" if row and row.last_heartbeat_at_utc else "offline",
        "last_heartbeat_at_utc": _iso(row.last_heartbeat_at_utc) if row else None,
        "active_monitors": active,
        "pending_evaluations": due,
        "failed_evaluations_24h": row.failed_count if row else 0,
        "duplicate_claims_prevented": row.duplicate_claim_count if row else 0,
    }


# --- payload helpers --------------------------------------------------------


def monitor_payload(row: StrategyShadowMonitorRecord) -> dict:
    return {
        "shadow_monitor_id": row.shadow_monitor_id,
        "strategy_id": row.strategy_id,
        "strategy_version_id": row.strategy_version_id,
        "baseline_run_id": row.baseline_run_id,
        "state": row.state,
        "schedule": row.schedule_json or {},
        "created_by": row.created_by,
        "created_at_utc": _iso(row.created_at_utc),
        "activated_at_utc": _iso(row.activated_at_utc),
        "paused_at_utc": _iso(row.paused_at_utc),
        "retired_at_utc": _iso(row.retired_at_utc),
        "last_evaluation_at_utc": _iso(row.last_evaluation_at_utc),
        "next_evaluation_at_utc": _iso(row.next_evaluation_at_utc),
        "latest_evaluation_id": row.latest_evaluation_id,
        "consecutive_failures": row.consecutive_failures,
        "health_state": row.health_state,
        "cumulative_shadow_pnl_gbp": row.cumulative_shadow_pnl_gbp,
        "current_exposure_mwh_per_day": row.current_exposure_mwh_per_day,
        "research_only": row.research_only,
    }


def evaluation_payload(row: StrategyShadowEvaluationRecord) -> dict:
    return {
        "shadow_evaluation_id": row.shadow_evaluation_id,
        "shadow_monitor_id": row.shadow_monitor_id,
        "strategy_version_id": row.strategy_version_id,
        "scheduled_for_utc": _iso(row.scheduled_for_utc),
        "started_at_utc": _iso(row.started_at_utc),
        "decision_time_utc": _iso(row.decision_time_utc),
        "completed_at_utc": _iso(row.completed_at_utc),
        "state": row.state,
        "gas_day": row.gas_day,
        "gas_day_start_utc": _iso(row.gas_day_start_utc),
        "gas_day_end_utc": _iso(row.gas_day_end_utc),
        "snapshot_id": row.snapshot_id,
        "candidate_id": row.candidate_id,
        "price_evidence_refs": row.price_evidence_refs or [],
        "fx_evidence_refs": row.fx_evidence_refs or [],
        "resource_evidence_refs": row.resource_evidence_refs or [],
        "source_systems": row.source_systems or [],
        "freshness": row.freshness_json or [],
        "missing_inputs": row.missing_inputs or [],
        "warnings": row.warnings or [],
        "result": row.result_json or {},
        "failure_class": row.failure_class,
        "retry_count": row.retry_count,
        "research_only": row.research_only,
        "human_review_required": row.human_review_required,
    }


def risk_check_payload(row: StrategyShadowRiskCheckRecord) -> dict:
    return {
        "risk_check_id": row.risk_check_id,
        "shadow_evaluation_id": row.shadow_evaluation_id,
        "control_id": row.control_id,
        "observed_value": row.observed_value,
        "limit_value": row.limit_value,
        "state": row.state,
        "severity": row.severity,
        "explanation": row.explanation,
    }


def alert_payload(row: StrategyShadowAlertRecord) -> dict:
    return {
        "alert_id": row.alert_id,
        "shadow_monitor_id": row.shadow_monitor_id,
        "shadow_evaluation_id": row.shadow_evaluation_id,
        "alert_type": row.alert_type,
        "severity": row.severity,
        "state": row.state,
        "fingerprint": row.fingerprint,
        "summary": row.summary,
        "evidence_refs": row.evidence_refs or [],
        "first_seen_at_utc": _iso(row.first_seen_at_utc),
        "last_seen_at_utc": _iso(row.last_seen_at_utc),
        "occurrence_count": row.occurrence_count,
        "acknowledged_at_utc": _iso(row.acknowledged_at_utc),
        "acknowledged_by": row.acknowledged_by,
        "resolved_at_utc": _iso(row.resolved_at_utc),
        "research_only": row.research_only,
    }


def drift_payload(row: StrategyShadowDriftSnapshotRecord) -> dict:
    return {
        "drift_snapshot_id": row.drift_snapshot_id,
        "shadow_monitor_id": row.shadow_monitor_id,
        "baseline_run_id": row.baseline_run_id,
        "observation_window": row.observation_window_json or {},
        "state": row.state,
        "metrics": row.metrics_json or [],
        "sample_size": row.sample_size,
        "explanation": row.explanation,
        "created_at_utc": _iso(row.created_at_utc),
    }


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()
