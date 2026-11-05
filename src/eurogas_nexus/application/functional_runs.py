"""Durable, owner-scoped functional work using the existing Job state machine."""

import time
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from eurogas_nexus.application.calculation_manifest import calculation_manifest
from eurogas_nexus.db.models.functional import FunctionalRunRecord
from eurogas_nexus.db.models.jobs import JobRecord
from eurogas_nexus.db.repositories.jobs import (
    create_job,
    fail_job,
    finish_job,
    start_job,
    update_progress,
)
from eurogas_nexus.domain.analysis_contracts import content_hash

ENGINES = {
    "SCENARIO_COMPARISON": "sequential-joint-attribution/1",
    "WEATHER_PROFILE": "nwe-weather-profile/1",
    "FROZEN_WEATHER": "frozen-nwe-weather/1",
    "SHADOW_EVALUATION": "nwe-shadow-evaluation/1",
    "NWE_BALANCE": "nwe-balance-scenario/1",
    "JOINT_OPTIMIZATION": "bounded-circulation/1",
    "READINESS": "interval-readiness/1",
    "WEATHER_VALIDATION": "nwe-weather-walk-forward/1",
}
JOB_KINDS = {
    "SCENARIO_COMPARISON": "REPORT",
    "WEATHER_PROFILE": "REPORT",
    "FROZEN_WEATHER": "REPORT",
    "SHADOW_EVALUATION": "BACKTEST",
    "NWE_BALANCE": "REPORT",
    "JOINT_OPTIMIZATION": "OPTIMISATION",
    "READINESS": "DATASET_BUILD",
    "WEATHER_VALIDATION": "BACKTEST",
}


class SubmitRun(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    kind: str
    inputs: dict
    idempotency_key: str = Field(min_length=1, max_length=80)
    version_refs: dict[str, str] = Field(default_factory=dict, max_length=32)
    deadline_seconds: int = Field(default=60, ge=1, le=120)

    @field_validator("version_refs")
    @classmethod
    def bounded_versions(cls, value):
        if any(not 1 <= len(k) <= 160 or not 1 <= len(v) <= 128 for k, v in value.items()):
            raise ValueError("version references require bounded non-empty identifiers")
        return value


def validate_inputs(kind, inputs):
    from eurogas_nexus.application.frozen_weather import FrozenPrediction, ShadowEvaluation
    from eurogas_nexus.application.functional_comparison import JointComparison
    from eurogas_nexus.application.nwe_balance_scenario import NweBalanceScenarioRequest
    from eurogas_nexus.application.nwe_model_validation import ValidationRequest
    from eurogas_nexus.application.weather_region_profile import WeatherRegionProfile
    from eurogas_nexus.domain.analysis_contracts import ReadinessRequest
    from eurogas_nexus.optimization.joint import JointRequest

    models = {
        "SCENARIO_COMPARISON": JointComparison,
        "WEATHER_PROFILE": WeatherRegionProfile,
        "FROZEN_WEATHER": FrozenPrediction,
        "SHADOW_EVALUATION": ShadowEvaluation,
        "NWE_BALANCE": NweBalanceScenarioRequest,
        "JOINT_OPTIMIZATION": JointRequest,
        "READINESS": ReadinessRequest,
        "WEATHER_VALIDATION": ValidationRequest,
    }
    if kind not in models:
        raise ValueError("unknown_functional_kind")
    return models[kind].model_validate(inputs)


def find_submission(session, owner, key, request_hash):
    row = session.scalar(
        select(FunctionalRunRecord).where(
            FunctionalRunRecord.owner_id == owner.principal_id,
            FunctionalRunRecord.idempotency_key == key,
        )
    )
    if row and row.request_hash != request_hash:
        raise ValueError("idempotency_key_conflict")
    return row


def submit(
    session,
    owner,
    request: SubmitRun,
    *,
    scopes=(),
    weather_evidence=None,
    request_hash=None,
    evidence_warnings=(),
):
    canonical = validate_inputs(request.kind, request.inputs).model_dump(mode="json")
    manifest = calculation_manifest(
        request.kind,
        ENGINES[request.kind],
        canonical,
        versions=request.version_refs,
        scopes=tuple(scopes),
    )
    manifest["weather_evidence"] = weather_evidence or []
    manifest["evidence_warnings"] = list(evidence_warnings)
    manifest["manifest_hash"] = content_hash(
        {k: v for k, v in manifest.items() if k != "manifest_hash"}
    )
    request_hash = request_hash or content_hash(
        {"manifest": manifest, "deadline": request.deadline_seconds}
    )

    def existing():
        return find_submission(session, owner, request.idempotency_key, request_hash)

    found = existing()
    if found:
        return found, False
    from eurogas_nexus.db.models.identity import IdentityPrincipalRecord

    session.get(IdentityPrincipalRecord, owner.principal_id, with_for_update=True)
    found = existing()
    if found:
        return found, False
    active = session.scalars(
        select(FunctionalRunRecord.run_id)
        .join(JobRecord)
        .where(
            FunctionalRunRecord.owner_id == owner.principal_id,
            JobRecord.status.in_(["QUEUED", "RUNNING"]),
        )
    ).all()
    if len(active) >= 3:
        raise ValueError("functional_queue_limit")
    try:
        job = create_job(
            session,
            kind=JOB_KINDS[request.kind],
            principal=owner.name,
            owner_principal_id=owner.principal_id,
            input_hash=manifest["input_hash"],
            provenance=tuple(scopes),
        )
        row = FunctionalRunRecord(
            run_id=f"frun-{uuid4().hex[:24]}",
            owner_id=owner.principal_id,
            job_id=job["job_id"],
            kind=request.kind,
            idempotency_key=request.idempotency_key,
            request_hash=request_hash,
            manifest=manifest,
            inputs=canonical,
            result=None,
            source_scopes=list(scopes),
            deadline_seconds=request.deadline_seconds,
            created_at=datetime.now(UTC),
        )
        session.add(row)
        session.flush()
        record_dependencies(session, row.run_id, request.version_refs)
        return row, True
    except IntegrityError:
        session.rollback()
        found = existing()
        if found is None:
            raise
        return found, False


def execute(factory, run_id):
    """Claim once, calculate outside locks, then atomically publish job + result."""
    with factory() as session:
        row = session.scalar(
            select(FunctionalRunRecord)
            .where(FunctionalRunRecord.run_id == run_id)
            .with_for_update()
        )
        if row is None:
            return
        job = session.get(JobRecord, row.job_id, with_for_update=True)
        if job.status != "QUEUED":
            return
        from eurogas_nexus.application.calculation_manifest import numerical_bundle_fingerprint

        if (
            row.manifest.get("numerical_bundle_fingerprint") != numerical_bundle_fingerprint()
            or row.manifest["engine_version"] != ENGINES[row.kind]
        ):
            start_job(session, row.job_id)
            fail_job(session, row.job_id, error_code="FUNCTIONAL_ENGINE_CHANGED", retryable=False)
            session.commit()
            return
        start_job(session, row.job_id)
        kind, inputs, job_id, limit = row.kind, row.inputs, row.job_id, row.deadline_seconds
        session.commit()
    started = time.monotonic()
    last_check = -1.0

    def checkpoint():
        nonlocal last_check
        elapsed = time.monotonic() - started
        if elapsed > limit:
            raise TimeoutError("functional_deadline_exceeded")
        if elapsed - last_check >= 0.1:
            with factory() as session:
                job = session.get(JobRecord, job_id)
                if job is None or job.status != "RUNNING":
                    raise InterruptedError("functional_job_cancelled")
                update_progress(session, job_id, min(0.9, elapsed / limit))
                session.commit()
            last_check = elapsed

    try:
        checkpoint()
        result = compute(kind, inputs, checkpoint)
        checkpoint()
        with factory() as session:
            job = session.get(JobRecord, job_id, with_for_update=True, populate_existing=True)
            if job.status != "RUNNING":
                return
            row = session.get(FunctionalRunRecord, run_id)
            row.result = result
            if kind == "READINESS":
                dependencies = {
                    f"data:{ref}": version
                    for need in result["requirements"]
                    for ref, version in need["record_versions"].items()
                }
                record_dependencies(session, run_id, dependencies)
            finish_job(session, job_id, output_refs=(f"functional-run:{run_id}",))
            session.commit()
    except Exception as exc:
        with factory() as session:
            job = session.get(JobRecord, job_id, with_for_update=True, populate_existing=True)
            if job is not None and job.status == "RUNNING":
                fail_job(
                    session,
                    job_id,
                    error_code=(
                        "FUNCTIONAL_TIMEOUT"
                        if isinstance(exc, TimeoutError)
                        else "FUNCTIONAL_COMPUTE_FAILED"
                    ),
                    error_message=exc.__class__.__name__,
                    retryable=isinstance(exc, TimeoutError),
                )
                session.commit()


def compute(kind, inputs, checkpoint=lambda: None):
    payload = validate_inputs(kind, inputs)
    if kind == "SCENARIO_COMPARISON":
        from eurogas_nexus.application.functional_comparison import attribute_joint

        return attribute_joint(payload, checkpoint)
    if kind == "WEATHER_PROFILE":
        from eurogas_nexus.application.weather_region_profile import build_weather_profile

        return build_weather_profile(payload)
    if kind == "FROZEN_WEATHER":
        from eurogas_nexus.application.frozen_weather import predict_frozen

        return predict_frozen(payload)
    if kind == "SHADOW_EVALUATION":
        from eurogas_nexus.application.frozen_weather import evaluate_shadow

        return evaluate_shadow(payload)
    if kind == "NWE_BALANCE":
        from eurogas_nexus.application.nwe_balance_scenario import run_nwe_balance_scenario

        return run_nwe_balance_scenario(payload)
    if kind == "JOINT_OPTIMIZATION":
        from eurogas_nexus.optimization.joint import optimize_joint

        return optimize_joint(payload, checkpoint)
    if kind == "READINESS":
        from eurogas_nexus.domain.analysis_contracts import evaluate_readiness

        return evaluate_readiness(payload, checkpoint)
    from eurogas_nexus.application.nwe_model_validation import validate_weather_model

    return validate_weather_model(payload, checkpoint)


def run_pending(factory, limit=10):
    """Recover queued submissions and mark abandoned RUNNING jobs failed, never replay silently."""
    with factory() as session:
        rows = session.scalars(
            select(FunctionalRunRecord)
            .order_by(FunctionalRunRecord.created_at)
            .join(JobRecord)
            .where(JobRecord.status.in_(["QUEUED", "RUNNING"]))
            .limit(limit)
        ).all()
        ids = []
        for row in rows:
            job = session.get(JobRecord, row.job_id, with_for_update=True)
            instant = job.started_at_utc
            if instant is not None and instant.tzinfo is None:
                instant = instant.replace(tzinfo=UTC)
            if (
                job.status == "RUNNING"
                and instant
                and datetime.now(UTC) - instant > timedelta(seconds=row.deadline_seconds + 60)
            ):
                fail_job(session, job.job_id, error_code="FUNCTIONAL_WORKER_LOST", retryable=True)
            elif job.status == "QUEUED":
                ids.append(row.run_id)
        session.commit()
    for run_id in ids:
        execute(factory, run_id)
    return len(ids)


def record_dependencies(session, run_id, versions):
    from eurogas_nexus.db.models.functional import FunctionalDependencyRecord

    for reference, version in versions.items():
        row = session.get(FunctionalDependencyRecord, (run_id, reference))
        if row is not None and row.version_hash != version:
            raise ValueError("conflicting_dependency_version")
        if row is None:
            session.add(
                FunctionalDependencyRecord(
                    run_id=run_id,
                    reference=reference,
                    version_hash=version,
                    latest_hash=version,
                    stale=False,
                )
            )
    session.flush()


def reconcile_dependencies(session, changes, *, owner_id=None):
    """Apply source revision events without rewriting historical inputs/results.

    Ingestion adapters may call this with actual version events. The public
    scenario operation is restricted to the caller's own dependency records.
    """
    from eurogas_nexus.db.models.functional import FunctionalDependencyRecord

    statement = (
        select(FunctionalDependencyRecord)
        .join(FunctionalRunRecord)
        .where(FunctionalDependencyRecord.reference.in_(changes))
    )
    if owner_id is not None:
        statement = statement.where(FunctionalRunRecord.owner_id == owner_id)
    rows = session.scalars(statement.with_for_update()).all()
    affected = set()
    for row in rows:
        row.latest_hash = changes[row.reference]
        row.stale = row.latest_hash != row.version_hash
        if row.stale:
            affected.add(row.run_id)
    session.flush()
    return sorted(affected)


def stale_dependencies(session, run_id):
    from eurogas_nexus.db.models.functional import FunctionalDependencyRecord

    return [
        r.reference
        for r in session.scalars(
            select(FunctionalDependencyRecord).where(
                FunctionalDependencyRecord.run_id == run_id,
                FunctionalDependencyRecord.stale.is_(True),
            )
        ).all()
    ]
