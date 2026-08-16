"""Strategy-lab decision-support endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, Query, Request

from eurogas_nexus.domain.strategy_lab.evaluation import (
    StrategyLabScenario,
    evaluate_strategy_lab,
)

router = APIRouter(tags=["strategy-lab"])


@router.post("/api/strategy-lab/evaluate")
def post_strategy_lab_evaluation(body: StrategyLabScenario, request: Request) -> dict:
    """Evaluate backtest, shadow-run, or live-monitor strategy inputs."""

    result = evaluate_strategy_lab(body)
    run_id = f"run-{uuid4().hex[:16]}"
    warnings = list(result.warnings)
    if not _persist_run(run_id, body, result):
        warnings.append("STRATEGY_RUN_NOT_PERSISTED")

    return _env(
        {"run_id": run_id, **result.model_dump(mode="json")},
        request,
        source="operator-input",
        warnings=warnings,
    )


@router.get("/api/strategy-lab/runs")
def get_strategy_runs(
    request: Request,
    strategy_id: str | None = Query(default=None),
    run_mode: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict:
    """List persisted strategy runs."""

    data, warnings = _list_runs(strategy_id=strategy_id, run_mode=run_mode, limit=limit)
    return _env(data, request, source="runtime-postgresql", warnings=warnings)


@router.get("/api/strategy-lab/runs/{run_id}")
def get_strategy_run(run_id: str, request: Request) -> dict:
    """Return one persisted strategy run."""

    data, warnings = _get_run(run_id)
    return _env(data, request, source="runtime-postgresql", warnings=warnings)


@router.get("/api/strategy-lab/summary")
def get_strategy_summary(
    request: Request,
    strategy_id: str | None = Query(default=None),
    run_mode: str | None = Query(default=None),
) -> dict:
    """Aggregate cumulative shadow-run paper performance."""

    data, warnings = _summarize(strategy_id=strategy_id, run_mode=run_mode)
    return _env(data, request, source="runtime-postgresql", warnings=warnings)


# --- Persistence helpers -----------------------------------------------------


def _persist_run(run_id: str, scenario: StrategyLabScenario, result) -> bool:
    if not _db_is_configured():
        return False
    try:
        from eurogas_nexus.db.repositories.strategy import persist_strategy_run
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            persist_strategy_run(
                session,
                run_id=run_id,
                scenario=scenario,
                result=result,
                now_utc=datetime.now(UTC),
            )
            session.commit()
        return True
    except _sqlalchemy_error_type():
        return False


def _list_runs(
    *, strategy_id: str | None, run_mode: str | None, limit: int
) -> tuple[list, list[str]]:
    if not _db_is_configured():
        return [], ["RUNTIME_DB_NOT_CONFIGURED"]
    try:
        from eurogas_nexus.db.repositories.strategy import list_strategy_runs
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            return list_strategy_runs(
                session,
                strategy_id=strategy_id,
                run_mode=run_mode,
                limit=limit,
            ), []
    except _sqlalchemy_error_type():
        return [], ["RUNTIME_POSTGRESQL_UNAVAILABLE"]


def _get_run(run_id: str) -> tuple[dict | None, list[str]]:
    if not _db_is_configured():
        return None, ["RUNTIME_DB_NOT_CONFIGURED"]
    try:
        from eurogas_nexus.db.repositories.strategy import get_strategy_run
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            return get_strategy_run(session, run_id), []
    except _sqlalchemy_error_type():
        return None, ["RUNTIME_POSTGRESQL_UNAVAILABLE"]


def _summarize(*, strategy_id: str | None, run_mode: str | None) -> tuple[dict, list[str]]:
    if not _db_is_configured():
        return _empty_summary(strategy_id, run_mode), ["RUNTIME_DB_NOT_CONFIGURED"]
    try:
        from eurogas_nexus.db.repositories.strategy import strategy_summary
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            return strategy_summary(
                session,
                strategy_id=strategy_id,
                run_mode=run_mode,
            ), []
    except _sqlalchemy_error_type():
        return _empty_summary(strategy_id, run_mode), ["RUNTIME_POSTGRESQL_UNAVAILABLE"]


def _empty_summary(strategy_id: str | None, run_mode: str | None) -> dict:
    return {
        "strategy_id": strategy_id,
        "run_mode": run_mode,
        "run_count": 0,
        "total_paper_pnl_gbp": 0.0,
        "cumulative_pnl_gbp": 0.0,
        "hit_rate": 0.0,
        "max_drawdown_gbp": 0.0,
        "first_started_at_utc": None,
        "last_started_at_utc": None,
        "latest_status": None,
    }


def _db_is_configured() -> bool:
    from eurogas_nexus.db.session import resolve_database_url

    return resolve_database_url() is not None


def _sqlalchemy_error_type():
    from sqlalchemy.exc import SQLAlchemyError

    return SQLAlchemyError


def _env(
    data: object,
    _request: Request,
    *,
    source: str,
    warnings: list[str] | None = None,
) -> dict:
    return {
        "data": data,
        "meta": {
            "research_only": True,
            "human_review_required": True,
            "source_references": [source],
            "warnings": list(dict.fromkeys(warnings or [])),
        },
    }
