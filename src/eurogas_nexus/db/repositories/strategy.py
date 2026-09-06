"""Repository operations for strategy-lab shadow runs and summaries."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.orm import Session

from eurogas_nexus.db.models import (
    StrategyAllocationTargetRecord,
    StrategyRunRecord,
)
from eurogas_nexus.domain.strategy_lab.evaluation import (
    StrategyLabResult,
    StrategyLabScenario,
)


def persist_strategy_run(
    session: Session,
    *,
    run_id: str,
    scenario: StrategyLabScenario,
    result: StrategyLabResult,
    now_utc: datetime,
) -> StrategyRunRecord:
    """Persist one evaluated shadow-run snapshot and its allocation targets."""

    run = StrategyRunRecord(
        run_id=run_id,
        strategy_id=scenario.strategy_id,
        run_mode=str(scenario.run_mode.value),
        status=result.status,
        started_at_utc=now_utc,
        finished_at_utc=now_utc,
        input_snapshot=scenario.model_dump(mode="json"),
        result_snapshot=result.model_dump(mode="json"),
        source_refs=result.source_refs,
        warnings=result.warnings,
        missing_inputs=result.missing_inputs,
        research_only=result.research_only,
        human_review_required=result.human_review_required,
    )
    session.add(run)
    for target in result.allocation_targets:
        session.add(
            StrategyAllocationTargetRecord(
                target_id=f"target-{uuid4().hex[:16]}",
                run_id=run_id,
                market_bucket=target.market_bucket,
                target_allocation_pct=target.target_allocation_pct,
                target_quantity_mwh_per_day=target.target_quantity_mwh_per_day,
                reference_price_gbp_mwh=target.reference_price_gbp_mwh,
                expected_margin_gbp_mwh=target.expected_margin_gbp_mwh,
                rationale=target.rationale,
                created_at_utc=now_utc,
            )
        )
    session.flush()
    return run


def list_strategy_runs(
    session: Session,
    *,
    strategy_id: str | None = None,
    run_mode: str | None = None,
    limit: int = 100,
) -> list[dict]:
    """Return persisted strategy runs, newest first."""

    query = session.query(StrategyRunRecord)
    if strategy_id:
        query = query.filter(StrategyRunRecord.strategy_id == strategy_id)
    if run_mode:
        query = query.filter(StrategyRunRecord.run_mode == run_mode)
    rows = (
        query.order_by(StrategyRunRecord.started_at_utc.desc())
        .limit(max(1, min(limit, 500)))
        .all()
    )
    return [strategy_run_payload(row) for row in rows]


def get_strategy_run(session: Session, run_id: str) -> dict | None:
    """Return one persisted strategy run by id."""

    row = session.get(StrategyRunRecord, run_id)
    return strategy_run_payload(row) if row is not None else None


def strategy_summary(
    session: Session,
    *,
    strategy_id: str | None = None,
    run_mode: str | None = None,
) -> dict:
    """Aggregate cumulative paper performance across persisted runs."""

    query = session.query(StrategyRunRecord)
    if strategy_id:
        query = query.filter(StrategyRunRecord.strategy_id == strategy_id)
    if run_mode:
        query = query.filter(StrategyRunRecord.run_mode == run_mode)
    rows = query.order_by(StrategyRunRecord.started_at_utc.asc()).all()

    cumulative = 0.0
    peak = 0.0
    max_drawdown = 0.0
    hits = 0
    for row in rows:
        paper_pnl = _paper_pnl(row)
        cumulative = round(cumulative + paper_pnl, 4)
        peak = max(peak, cumulative)
        max_drawdown = max(max_drawdown, round(peak - cumulative, 4))
        if bool(row.result_snapshot.get("hit")):
            hits += 1

    run_count = len(rows)
    return {
        "strategy_id": strategy_id,
        "run_mode": run_mode,
        "run_count": run_count,
        "total_paper_pnl_gbp": cumulative,
        "cumulative_pnl_gbp": cumulative,
        "hit_rate": round(hits / run_count, 4) if run_count else 0.0,
        "max_drawdown_gbp": max_drawdown,
        "first_started_at_utc": _as_utc(rows[0].started_at_utc).isoformat() if rows else None,
        "last_started_at_utc": _as_utc(rows[-1].started_at_utc).isoformat() if rows else None,
        "latest_status": rows[-1].status if rows else None,
    }


def strategy_run_payload(row: StrategyRunRecord) -> dict:
    """Render a persisted strategy run as a JSON-safe payload.

    Price basis and review-context fields are read from the persisted result
    snapshot. They are intentionally not recalculated from current inputs or
    market rows. ``strategy_name`` falls back to the input snapshot only when
    the result snapshot value is absent or null. Legacy runs lacking these
    fields expose ``None``; zero and negative stored values are preserved.
    """

    snapshot = row.result_snapshot or {}
    strategy_name = snapshot.get("strategy_name")
    if strategy_name is None:
        strategy_name = (row.input_snapshot or {}).get("strategy_name")
    return {
        "run_id": row.run_id,
        "strategy_id": row.strategy_id,
        "strategy_name": strategy_name,
        "strategy_version_id": getattr(row, "strategy_version_id", None),
        "run_type": getattr(row, "run_type", None),
        "run_mode": row.run_mode,
        "status": row.status,
        "requested_at_utc": (
            _as_utc(row.requested_at_utc).isoformat()
            if getattr(row, "requested_at_utc", None)
            else None
        ),
        "started_at_utc": _as_utc(row.started_at_utc).isoformat(),
        "completed_at_utc": (
            _as_utc(row.completed_at_utc).isoformat()
            if getattr(row, "completed_at_utc", None)
            else None
        ),
        "finished_at_utc": (
            _as_utc(row.finished_at_utc).isoformat() if row.finished_at_utc else None
        ),
        "evaluation_start_utc": (
            _as_utc(row.evaluation_start_utc).isoformat()
            if getattr(row, "evaluation_start_utc", None)
            else None
        ),
        "evaluation_end_utc": (
            _as_utc(row.evaluation_end_utc).isoformat()
            if getattr(row, "evaluation_end_utc", None)
            else None
        ),
        "data_cutoff_utc": (
            _as_utc(row.data_cutoff_utc).isoformat()
            if getattr(row, "data_cutoff_utc", None)
            else None
        ),
        "dataset_snapshot_id": getattr(row, "dataset_snapshot_id", None),
        "manifest_json": getattr(row, "manifest_json", None),
        "manifest_hash": getattr(row, "manifest_hash", None),
        "engine_version": getattr(row, "engine_version", None),
        "backtest_engine_version": getattr(row, "backtest_engine_version", None),
        "experiment_id": getattr(row, "experiment_id", None),
        "application_version": getattr(row, "application_version", None),
        "git_commit_sha": getattr(row, "git_commit_sha", None),
        "strategy_schema_version": getattr(row, "strategy_schema_version", None),
        "run_schema_version": getattr(row, "run_schema_version", None),
        "deterministic_seed": getattr(row, "deterministic_seed", None),
        "requested_by": getattr(row, "requested_by", None),
        "trigger_type": getattr(row, "trigger_type", None),
        "correlation_request_id": getattr(row, "correlation_request_id", None),
        "backtest_metrics": snapshot.get("metrics"),
        "paper_pnl_gbp": snapshot.get("paper_pnl_gbp"),
        "cumulative_pnl_gbp": snapshot.get("cumulative_pnl_gbp"),
        "hit": snapshot.get("hit"),
        "weighted_score": snapshot.get("weighted_score"),
        "day_ahead_average_gbp_mwh": snapshot.get("day_ahead_average_gbp_mwh"),
        "intraday_average_gbp_mwh": snapshot.get("intraday_average_gbp_mwh"),
        "intraday_vs_day_ahead_spread_gbp_mwh": snapshot.get(
            "intraday_vs_day_ahead_spread_gbp_mwh"
        ),
        "candidate_action_for_review": snapshot.get("candidate_action_for_review"),
        "allocation_targets": snapshot.get("allocation_targets", []),
        "missing_inputs": row.missing_inputs or [],
        "warnings": row.warnings or [],
        "source_refs": row.source_refs or [],
        "research_only": row.research_only,
        "human_review_required": row.human_review_required,
    }


def _paper_pnl(row: StrategyRunRecord) -> float:
    value = (row.result_snapshot or {}).get("paper_pnl_gbp")
    try:
        return round(float(value), 4)
    except (TypeError, ValueError):
        return 0.0


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
