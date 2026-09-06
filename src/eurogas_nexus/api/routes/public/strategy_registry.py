"""Versioned strategy-registry decision-support endpoints.

These endpoints implement the reproducibility contract for strategy research:
strategies are long-lived identities, versions are immutable semantic
definitions, and runs are immutable evaluations of one exact version against
one exact evidence snapshot. Nothing in this module creates orders, trades or
nominations.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from eurogas_nexus.domain.backtest.contracts import (
    BacktestDecisionSchedule,
    BacktestEconomicAssumptions,
    BacktestPeriod,
    BacktestRunDefinition,
)
from eurogas_nexus.domain.ontology.vocabulary import (
    ExperimentType,
    StrategyRunMode,
)
from eurogas_nexus.domain.strategy_lab.registry import (
    StrategyRunType,
    StrategyVersionDefinition,
)

router = APIRouter(tags=["strategy-registry"])


class StrategyCreateRequest(BaseModel):
    """Create a long-lived strategy research identity."""

    strategy_id: str | None = Field(
        default=None,
        min_length=3,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$",
    )
    name: str = Field(min_length=1, max_length=256)
    description: str = Field(default="", max_length=4000)
    tags: list[str] = Field(default_factory=list)


class StrategyVersionCreateRequest(BaseModel):
    """Create a new draft semantic version for one strategy.

    The semantic ``definition`` carries the typed component/parameter model.
    The optional legacy-evaluation fields are merged into the immutable stored
    definition so the current evaluator can execute the version as configured.
    """

    hypothesis: str = Field(default="", max_length=4000)
    definition: StrategyVersionDefinition
    strategy_name: str | None = Field(default=None, max_length=256)
    run_mode: StrategyRunMode = StrategyRunMode.SHADOW_RUN
    resource_contexts: list[dict[str, Any]] = Field(default_factory=list)
    price_observations: list[dict[str, Any]] = Field(default_factory=list)
    existing_shadow_pnl_gbp: float = 0.0


class StrategyForkRequest(BaseModel):
    """Fork an immutable frozen version into a new draft."""

    hypothesis: str | None = Field(default=None, max_length=4000)
    definition: StrategyVersionDefinition | None = None


class StrategyRunCreateRequest(BaseModel):
    """Request one reproducible strategy evaluation or backtest."""

    strategy_version_id: str = Field(min_length=1, max_length=128)
    run_type: StrategyRunType = StrategyRunType.EVALUATION
    deterministic_seed: str | None = Field(default=None, max_length=64)
    trigger_type: str = Field(default="MANUAL", max_length=32)
    correlation_request_id: str | None = Field(default=None, max_length=64)
    evaluation_period_start_utc: datetime | None = None
    evaluation_period_end_utc: datetime | None = None
    decision_schedule: BacktestDecisionSchedule | None = None
    economic_assumptions: BacktestEconomicAssumptions | None = None
    parameter_values: dict[str, Any] = Field(default_factory=dict)
    experiment_id: str | None = Field(default=None, max_length=128)


class BacktestExperimentCreateRequest(BaseModel):
    """Create a lightweight SINGLE_RUN backtest experiment group."""

    experiment_id: str | None = Field(default=None, max_length=128)
    strategy_id: str = Field(min_length=1, max_length=128)
    base_strategy_version_id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=256)
    hypothesis: str = Field(default="", max_length=4000)
    experiment_type: ExperimentType = ExperimentType.SINGLE_RUN
    evaluation_period_start_utc: datetime
    evaluation_period_end_utc: datetime


@router.get("/api/strategies")
def get_strategies(
    request: Request,
    limit: int = Query(default=200, ge=1, le=500),
) -> dict:
    """List strategy research identities, newest first."""

    with _db_session() as session:
        from eurogas_nexus.db.repositories import strategy_registry

        rows = strategy_registry.list_strategies(session, limit=limit)
        data = [strategy_registry.strategy_record_payload(row) for row in rows]
    return _env(data, request, source="runtime-postgresql")


@router.post("/api/strategies")
def post_strategy(body: StrategyCreateRequest, request: Request) -> dict:
    """Create a strategy research identity."""

    with _db_session() as session:
        from eurogas_nexus.db.repositories import strategy_registry

        strategy_id = body.strategy_id or f"strategy-{uuid4().hex[:16]}"
        row = strategy_registry.create_strategy(
            session,
            strategy_id=strategy_id,
            name=body.name,
            description=body.description,
            created_by=_requested_by(request),
            now_utc=datetime.now(UTC),
            tags=body.tags,
        )
        data = strategy_registry.strategy_record_payload(row)
    return _env(data, request, source="operator-input")


@router.get("/api/strategies/{strategy_id}")
def get_strategy(strategy_id: str, request: Request) -> dict:
    """Return one strategy identity, or 404."""

    with _db_session() as session:
        from eurogas_nexus.db.repositories import strategy_registry

        row = strategy_registry.get_strategy(session, strategy_id)
        if row is None:
            raise HTTPException(status_code=404, detail=f"Unknown strategy: {strategy_id}")
        data = strategy_registry.strategy_record_payload(row)
    return _env(data, request, source="runtime-postgresql")


@router.get("/api/strategies/{strategy_id}/versions")
def get_strategy_versions(
    strategy_id: str,
    request: Request,
    limit: int = Query(default=100, ge=1, le=500),
) -> dict:
    """List semantic versions of one strategy, newest first."""

    with _db_session() as session:
        from eurogas_nexus.db.repositories import strategy_registry

        if strategy_registry.get_strategy(session, strategy_id) is None:
            raise HTTPException(status_code=404, detail=f"Unknown strategy: {strategy_id}")
        rows = strategy_registry.list_strategy_versions(session, strategy_id, limit=limit)
        data = [strategy_registry.strategy_version_payload(row) for row in rows]
    return _env(data, request, source="runtime-postgresql")


@router.post("/api/strategies/{strategy_id}/versions")
def post_strategy_version(
    strategy_id: str,
    body: StrategyVersionCreateRequest,
    request: Request,
) -> dict:
    """Create a new draft semantic version of a strategy."""

    with _db_session() as session:
        from eurogas_nexus.db.repositories import strategy_registry

        strategy = strategy_registry.get_strategy(session, strategy_id)
        if strategy is None:
            raise HTTPException(status_code=404, detail=f"Unknown strategy: {strategy_id}")
        row = strategy_registry.create_strategy_version(
            session,
            strategy_id=strategy_id,
            definition=body.definition,
            hypothesis=body.hypothesis,
            created_by=_requested_by(request),
            now_utc=datetime.now(UTC),
            definition_overrides={
                "strategy_name": body.strategy_name or strategy.name,
                "run_mode": body.run_mode.value,
                "resource_contexts": body.resource_contexts,
                "price_observations": body.price_observations,
                "existing_shadow_pnl_gbp": body.existing_shadow_pnl_gbp,
            },
        )
        data = strategy_registry.strategy_version_payload(row)
    return _env(data, request, source="operator-input")


@router.get("/api/strategy-versions/{version_id}")
def get_strategy_version(version_id: str, request: Request) -> dict:
    """Return one immutable semantic version, or 404."""

    with _db_session() as session:
        from eurogas_nexus.db.repositories import strategy_registry

        row = strategy_registry.get_strategy_version(session, version_id)
        if row is None:
            raise HTTPException(
                status_code=404, detail=f"Unknown strategy version: {version_id}"
            )
        data = strategy_registry.strategy_version_payload(row)
    return _env(data, request, source="runtime-postgresql")


@router.post("/api/strategy-versions/{version_id}/freeze")
def freeze_strategy_version(version_id: str, request: Request) -> dict:
    """Freeze a draft version so it can never change again.

    Freezing makes the version the strategy's current version. Runs may only
    reference frozen versions.
    """

    with _db_session() as session:
        from eurogas_nexus.db.repositories import strategy_registry

        if strategy_registry.get_strategy_version(session, version_id) is None:
            raise HTTPException(
                status_code=404, detail=f"Unknown strategy version: {version_id}"
            )
        row = strategy_registry.freeze_strategy_version(
            session,
            strategy_version_id=version_id,
            frozen_by=_requested_by(request),
            now_utc=datetime.now(UTC),
        )
        data = strategy_registry.strategy_version_payload(row)
    return _env(data, request, source="operator-input")


@router.post("/api/strategy-versions/{version_id}/fork")
def fork_strategy_version(
    version_id: str,
    body: StrategyForkRequest,
    request: Request,
) -> dict:
    """Fork a frozen version into a new draft without mutating the source."""

    with _db_session() as session:
        from eurogas_nexus.db.repositories import strategy_registry

        if strategy_registry.get_strategy_version(session, version_id) is None:
            raise HTTPException(
                status_code=404, detail=f"Unknown strategy version: {version_id}"
            )
        row = strategy_registry.fork_strategy_version(
            session,
            source_version_id=version_id,
            definition=body.definition,
            hypothesis=body.hypothesis,
            created_by=_requested_by(request),
            now_utc=datetime.now(UTC),
        )
        data = strategy_registry.strategy_version_payload(row)
    return _env(data, request, source="operator-input")


@router.post("/api/strategy-runs")
def post_strategy_run(body: StrategyRunCreateRequest, request: Request) -> dict:
    """Evaluate or backtest one frozen strategy version.

    ``EVALUATION`` is the CR-03 single-scenario compatibility path.
    ``BACKTEST`` runs the temporally safe historical engine over an explicit
    evaluation period and persists decision events, series and attribution.
    """

    if body.run_type == StrategyRunType.EVALUATION:
        if _has_backtest_fields(body):
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "backtest_fields_not_applicable",
                    "message": "Backtest fields require run_type=BACKTEST.",
                },
            )
        return _post_evaluation_run(body, request)
    if body.run_type == StrategyRunType.BACKTEST:
        return _post_backtest_run(body, request)
    raise HTTPException(
        status_code=422,
        detail={
            "code": "run_type_not_supported",
            "message": "Only EVALUATION and BACKTEST runs are executable.",
            "requested_run_type": body.run_type.value,
        },
    )


def _post_evaluation_run(
    body: StrategyRunCreateRequest, request: Request
) -> dict:
    with _db_session() as session:
        from eurogas_nexus.db.repositories import strategy_registry
        from eurogas_nexus.db.repositories.strategy import strategy_run_payload
        from eurogas_nexus.domain.strategy_lab.run_orchestration import (
            StrategyVersionExecutionError,
            execute_evaluation_run,
        )

        version = strategy_registry.get_strategy_version(
            session, body.strategy_version_id
        )
        if version is None:
            raise HTTPException(
                status_code=404,
                detail=f"Unknown strategy version: {body.strategy_version_id}",
            )
        if version.status != "FROZEN":
            _raise_version_not_frozen(version.status, version.strategy_version_id)
        try:
            row = execute_evaluation_run(
                session,
                version=version,
                requested_by=_requested_by(request),
                deterministic_seed=body.deterministic_seed,
                trigger_type=body.trigger_type,
                correlation_request_id=body.correlation_request_id,
            )
        except StrategyVersionExecutionError as exc:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "strategy_version_not_executable",
                    "message": str(exc),
                },
            ) from exc
        data = strategy_run_payload(row)
    return _env(data, request, source="runtime-postgresql")


def _post_backtest_run(
    body: StrategyRunCreateRequest, request: Request
) -> dict:
    if (
        body.evaluation_period_start_utc is None
        or body.evaluation_period_end_utc is None
    ):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "backtest_period_required",
                "message": "BACKTEST requires evaluation_period_start_utc and end_utc.",
            },
        )
    try:
        period = BacktestPeriod(
            start_utc=body.evaluation_period_start_utc,
            end_utc=body.evaluation_period_end_utc,
        )
        definition = BacktestRunDefinition(
            strategy_version_id=body.strategy_version_id,
            period=period,
            schedule=body.decision_schedule or BacktestDecisionSchedule(),
            economic_assumptions=body.economic_assumptions
            or BacktestEconomicAssumptions(),
            parameter_values=body.parameter_values,
            deterministic_seed=body.deterministic_seed,
            experiment_id=body.experiment_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "backtest_request_invalid", "message": str(exc)},
        ) from exc

    with _db_session() as session:
        from eurogas_nexus.application.backtest_service import execute_backtest_run
        from eurogas_nexus.db.repositories import strategy_registry
        from eurogas_nexus.db.repositories.strategy import strategy_run_payload

        version = strategy_registry.get_strategy_version(
            session, body.strategy_version_id
        )
        if version is None:
            raise HTTPException(
                status_code=404,
                detail=f"Unknown strategy version: {body.strategy_version_id}",
            )
        if version.status != "FROZEN":
            _raise_version_not_frozen(version.status, version.strategy_version_id)
        try:
            row = execute_backtest_run(
                session,
                version=version,
                definition=definition,
                requested_by=_requested_by(request),
                run_id=None,
                requested_at_utc=None,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail={"code": "backtest_request_invalid", "message": str(exc)},
            ) from exc
        data = strategy_run_payload(row)
    return _env(data, request, source="runtime-postgresql")




@router.post("/api/backtest-experiments")
def post_backtest_experiment(
    body: BacktestExperimentCreateRequest, request: Request
) -> dict:
    """Create a lightweight SINGLE_RUN backtest experiment group."""

    try:
        period = BacktestPeriod(
            start_utc=body.evaluation_period_start_utc,
            end_utc=body.evaluation_period_end_utc,
        )
        period_payload = period.model_dump(mode="json")
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "experiment_period_invalid", "message": str(exc)},
        ) from exc

    with _db_session() as session:
        from eurogas_nexus.db.repositories import backtest, strategy_registry

        strategy = strategy_registry.get_strategy(session, body.strategy_id)
        if strategy is None:
            raise HTTPException(
                status_code=404, detail=f"Unknown strategy: {body.strategy_id}"
            )
        version = strategy_registry.get_strategy_version(
            session, body.base_strategy_version_id
        )
        if version is None or version.strategy_id != body.strategy_id:
            raise HTTPException(
                status_code=404,
                detail="Unknown or mismatched base strategy version",
            )
        if version.status != "FROZEN":
            _raise_version_not_frozen(version.status, version.strategy_version_id)
        experiment_id = body.experiment_id or f"experiment-{uuid4().hex[:20]}"
        row = backtest.create_experiment(
            session,
            experiment_id=experiment_id,
            strategy_id=body.strategy_id,
            base_strategy_version_id=body.base_strategy_version_id,
            name=body.name,
            hypothesis=body.hypothesis,
            experiment_type=body.experiment_type.value,
            evaluation_period=period_payload,
            created_by=_requested_by(request),
            now_utc=datetime.now(UTC),
        )
        data = {
            "experiment_id": row.experiment_id,
            "strategy_id": row.strategy_id,
            "base_strategy_version_id": row.base_strategy_version_id,
            "name": row.name,
            "hypothesis": row.hypothesis,
            "experiment_type": row.experiment_type,
            "evaluation_period": row.evaluation_period_json,
            "run_ids": row.run_ids,
            "status": row.status,
            "created_by": row.created_by,
            "created_at_utc": row.created_at_utc.isoformat(),
            "updated_at_utc": row.updated_at_utc.isoformat(),
            "research_only": row.research_only,
        }
    return _env(data, request, source="operator-input")


@router.get("/api/backtest-experiments")
def get_backtest_experiments(
    request: Request,
    limit: int = Query(default=200, ge=1, le=500),
) -> dict:
    """List backtest experiments, newest first."""

    with _db_session() as session:
        from eurogas_nexus.db.repositories import backtest

        data = backtest.list_experiments(session, limit=limit)
    return _env(data, request, source="runtime-postgresql")


@router.get("/api/backtest-experiments/{experiment_id}")
def get_backtest_experiment(experiment_id: str, request: Request) -> dict:
    """Return one backtest experiment, or 404."""

    with _db_session() as session:
        from eurogas_nexus.db.repositories import backtest

        row = backtest.get_experiment(session, experiment_id)
        if row is None:
            raise HTTPException(
                status_code=404, detail=f"Unknown experiment: {experiment_id}"
            )
        data = {
            "experiment_id": row.experiment_id,
            "strategy_id": row.strategy_id,
            "base_strategy_version_id": row.base_strategy_version_id,
            "name": row.name,
            "hypothesis": row.hypothesis,
            "experiment_type": row.experiment_type,
            "evaluation_period": row.evaluation_period_json,
            "run_ids": row.run_ids,
            "status": row.status,
            "created_by": row.created_by,
            "created_at_utc": row.created_at_utc.isoformat(),
            "updated_at_utc": row.updated_at_utc.isoformat(),
            "research_only": row.research_only,
        }
    return _env(data, request, source="runtime-postgresql")


@router.get("/api/strategy-runs")
def get_strategy_runs(
    request: Request,
    strategy_id: str | None = Query(default=None),
    strategy_version_id: str | None = Query(default=None),
    run_type: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict:
    """List persisted strategy runs, newest first."""

    with _db_session() as session:
        from eurogas_nexus.db.repositories import strategy_registry
        from eurogas_nexus.db.repositories.strategy import strategy_run_payload

        rows = strategy_registry.list_strategy_runs(
            session,
            strategy_id=strategy_id,
            strategy_version_id=strategy_version_id,
            run_type=run_type,
            limit=limit,
        )
        data = [strategy_run_payload(row) for row in rows]
    return _env(data, request, source="runtime-postgresql")


@router.get("/api/strategy-runs/{run_id}")
def get_strategy_run(run_id: str, request: Request) -> dict:
    """Return one persisted strategy run by id, or 404."""

    with _db_session() as session:
        from eurogas_nexus.db.repositories.strategy import get_strategy_run

        data = get_strategy_run(session, run_id)
        if data is None:
            raise HTTPException(status_code=404, detail=f"Unknown strategy run: {run_id}")
    return _env(data, request, source="runtime-postgresql")



@router.get("/api/strategy-runs/{run_id}/events")
def get_backtest_run_events(run_id: str, request: Request) -> dict:
    """Return persisted backtest decision events for one run."""

    with _db_session() as session:
        from eurogas_nexus.db.repositories import backtest
        from eurogas_nexus.db.repositories.strategy import get_strategy_run

        if get_strategy_run(session, run_id) is None:
            raise HTTPException(status_code=404, detail=f"Unknown strategy run: {run_id}")
        data = backtest.list_backtest_events(session, run_id)
    return _env(
        data,
        request,
        source="runtime-postgresql",
        warnings=[] if data else ["BACKTEST_EVENTS_NOT_AVAILABLE"],
    )


@router.get("/api/strategy-runs/{run_id}/series")
def get_backtest_run_series(run_id: str, request: Request) -> dict:
    """Return the persisted cumulative net PnL/exposure series."""

    with _db_session() as session:
        from eurogas_nexus.db.repositories import backtest
        from eurogas_nexus.db.repositories.strategy import get_strategy_run

        if get_strategy_run(session, run_id) is None:
            raise HTTPException(status_code=404, detail=f"Unknown strategy run: {run_id}")
        data = backtest.list_backtest_series(session, run_id)
    return _env(
        data,
        request,
        source="runtime-postgresql",
        warnings=[] if data else ["BACKTEST_SERIES_NOT_AVAILABLE"],
    )


@router.get("/api/strategy-runs/{run_id}/attribution")
def get_backtest_run_attribution(run_id: str, request: Request) -> dict:
    """Return persisted backtest attribution rows for one run."""

    with _db_session() as session:
        from eurogas_nexus.db.repositories import backtest
        from eurogas_nexus.db.repositories.strategy import get_strategy_run

        if get_strategy_run(session, run_id) is None:
            raise HTTPException(status_code=404, detail=f"Unknown strategy run: {run_id}")
        data = backtest.list_backtest_attribution(session, run_id)
    return _env(
        data,
        request,
        source="runtime-postgresql",
        warnings=[] if data else ["BACKTEST_ATTRIBUTION_NOT_AVAILABLE"],
    )


# --- Persistence and envelope helpers ---------------------------------------



def _has_backtest_fields(body: StrategyRunCreateRequest) -> bool:
    return any(
        value is not None and bool(value)
        for value in (
            body.evaluation_period_start_utc,
            body.evaluation_period_end_utc,
            body.decision_schedule,
            body.economic_assumptions,
            body.parameter_values,
            body.experiment_id,
        )
    )


def _raise_version_not_frozen(status: str, version_id: str) -> None:
    raise HTTPException(
        status_code=409,
        detail={
            "code": "strategy_version_not_frozen",
            "message": "Runs require an immutable FROZEN strategy version.",
            "strategy_version_id": version_id,
            "version_status": status,
        },
    )


@contextmanager
def _db_session():
    if not _db_is_configured():
        raise HTTPException(
            status_code=503,
            detail={"code": "runtime_db_unavailable", "message": "Runtime DB is not configured."},
        )
    from sqlalchemy.exc import SQLAlchemyError

    from eurogas_nexus.db.repositories.strategy_registry import StrategyRegistryError
    from eurogas_nexus.db.session import get_session_factory

    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except HTTPException:
        session.rollback()
        raise
    except StrategyRegistryError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        session.rollback()
        raise HTTPException(
            status_code=503,
            detail={"code": "runtime_postgresql_unavailable", "message": str(exc)},
        ) from exc
    finally:
        session.close()


def _db_is_configured() -> bool:
    from eurogas_nexus.db.session import resolve_database_url

    return resolve_database_url() is not None


def _requested_by(request: Request) -> str:
    identity = getattr(request.state, "identity", None)
    if identity is not None and getattr(identity, "principal_id", None):
        return str(identity.principal_id)
    return "operator"


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
