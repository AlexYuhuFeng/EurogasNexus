"""Optimization run persistence (Gate 3 evidence trail)."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from eurogas_nexus.db.models import OptimizationRunRecord


def persist_optimization_run(
    session: Session,
    *,
    run_id: str,
    optimization_type: str,
    decision_context: str,
    status: str,
    input_snapshot: dict,
    output_snapshot: dict,
    source_refs: list[str],
    warnings: list[str],
    created_at_utc: datetime | None = None,
) -> OptimizationRunRecord:
    """Append one immutable optimization run record."""

    run = OptimizationRunRecord(
        run_id=run_id,
        optimization_type=optimization_type,
        decision_context=decision_context,
        status=status,
        input_snapshot=input_snapshot,
        output_snapshot=output_snapshot,
        source_refs=source_refs,
        warnings=warnings,
        created_at_utc=created_at_utc or datetime.now(UTC),
        research_only=True,
        human_review_required=True,
    )
    session.add(run)
    session.flush()
    return run


def get_optimization_run(session: Session, run_id: str) -> OptimizationRunRecord | None:
    """Return one optimization run by id."""

    return session.get(OptimizationRunRecord, run_id)
