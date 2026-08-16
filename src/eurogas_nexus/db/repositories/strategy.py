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
    """Render a persisted strategy run as a JSON-safe payload."""

    snapshot = row.result_snapshot or {}
    return {
        "run_id": row.run_id,
        "strategy_id": row.strategy_id,
        "run_mode": row.run_mode,
        "status": row.status,
        "started_at_utc": _as_utc(row.started_at_utc).isoformat(),
        "finished_at_utc": (
            _as_utc(row.finished_at_utc).isoformat() if row.finished_at_utc else None
        ),
        "paper_pnl_gbp": snapshot.get("paper_pnl_gbp"),
        "cumulative_pnl_gbp": snapshot.get("cumulative_pnl_gbp"),
        "hit": snapshot.get("hit"),
        "weighted_score": snapshot.get("weighted_score"),
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
