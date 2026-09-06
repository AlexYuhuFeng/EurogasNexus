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

from eurogas_nexus.domain.ontology.vocabulary import StrategyRunMode
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
    """Request one reproducible strategy evaluation."""

    strategy_version_id: str = Field(min_length=1, max_length=128)
    run_type: StrategyRunType = StrategyRunType.EVALUATION
    deterministic_seed: str | None = Field(default=None, max_length=64)
    trigger_type: str = Field(default="MANUAL", max_length=32)
    correlation_request_id: str | None = Field(default=None, max_length=64)


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
    """Evaluate one frozen strategy version and persist a reproducible run.

    Only ``EVALUATION`` is executable in this release. The persisted run
    carries a complete run manifest: strategy version content hash, full
    definition, parameters, assumptions, evidence snapshot, time boundary,
    engine/application version and git commit.
    """

    if body.run_type != StrategyRunType.EVALUATION:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "run_type_not_supported",
                "message": "Only EVALUATION runs are executable in this release.",
                "requested_run_type": body.run_type.value,
            },
        )

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
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "strategy_version_not_frozen",
                    "message": "Runs require an immutable FROZEN strategy version.",
                    "strategy_version_id": version.strategy_version_id,
                    "version_status": version.status,
                },
            )
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


# --- Persistence and envelope helpers ---------------------------------------


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
