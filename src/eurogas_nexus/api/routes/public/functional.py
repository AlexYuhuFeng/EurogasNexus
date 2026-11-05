"""Owner-scoped functional tasks, frozen inputs and research model versions."""

from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from eurogas_nexus.api.dependencies.row_entitlement import require_derived_access
from eurogas_nexus.application.functional_contracts import SubmitRun
from eurogas_nexus.domain.analysis_contracts import compare_analysis, content_hash

router = APIRouter(tags=["functional-analysis"])


def factory():
    from eurogas_nexus.db.session import get_session_factory, resolve_database_url

    if not resolve_database_url():
        raise HTTPException(503, detail={"code": "runtime_database_required"})
    return get_session_factory()


def owner_id(session, request):
    from eurogas_nexus.db.repositories.strategy_access import require_named_principal

    return require_named_principal(session, getattr(request.state.identity, "principal_id", None))


def load_owned(session, run_id, request):
    from eurogas_nexus.db.models.functional import FunctionalRunRecord

    row = session.get(FunctionalRunRecord, run_id)
    if row is None or row.owner_id != owner_id(session, request):
        raise HTTPException(404, detail={"code": "functional_run_not_found"})
    require_derived_access(request, row.source_scopes, resource="functional_run")
    return row


def payload(session, row):
    from eurogas_nexus.application import functional_runs as service
    from eurogas_nexus.db.models.jobs import JobRecord

    job = session.get(JobRecord, row.job_id)
    return {
        "run_id": row.run_id,
        "job_id": row.job_id,
        "kind": row.kind,
        "status": job.status,
        "progress": job.progress,
        "error_code": job.error_code,
        "manifest": row.manifest,
        "stale_dependencies": service.stale_dependencies(session, row.run_id),
        "inputs": row.inputs,
        "result": row.result,
    }


def envelope(data):
    return {
        "data": data,
        "meta": {
            "research_only": True,
            "human_review_required": True,
            "source_references": ["functional-runs"],
            "warnings": [],
        },
    }


@router.post("/api/functional-runs", status_code=202)
def submit_run(body: SubmitRun, request: Request, background: BackgroundTasks):
    from eurogas_nexus.application import functional_runs as service

    if body.kind in {"FROZEN_WEATHER", "SHADOW_EVALUATION"}:
        raise HTTPException(422, detail={"code": "use_registered_model_operation"})
    request_hash = content_hash({"operation": "submit", "body": body.model_dump(mode="json")})
    with factory()() as session:
        owner_id(session, request)
        try:
            existing = service.find_submission(
                session, request.state.identity, body.idempotency_key, request_hash
            )
        except ValueError as exc:
            raise HTTPException(409, detail={"code": "idempotency_key_conflict"}) from exc
        if existing is not None:
            require_derived_access(request, existing.source_scopes, resource="functional_run")
            return envelope(payload(session, existing))

    scopes, evidence, warnings = (), [], []
    if body.kind == "NWE_BALANCE":
        from eurogas_nexus.api.balance_weather import compose_balance_weather
        from eurogas_nexus.api.schemas.nwe_balance import NweBalanceRequest

        try:
            supplied = NweBalanceRequest.model_validate(body.inputs)
            resolved, evidence, warnings = compose_balance_weather(supplied, request)
        except ValueError as exc:
            raise HTTPException(422, detail={"code": "invalid_balance_inputs"}) from exc
        if supplied.persisted_weather:
            scopes = ("ECMWF_OPEN_DATA",)
        if supplied.use_runtime_history:
            scopes = (*scopes, "ENTSOG", "GIE", "REMIT")
        body = body.model_copy(update={"inputs": resolved.model_dump(mode="json")})
    return _submit(
        body,
        request,
        background,
        scopes=scopes,
        evidence=evidence,
        request_hash=request_hash,
        warnings=warnings,
    )


def _submit(body, request, background, *, scopes=(), evidence=None, request_hash=None, warnings=()):
    from eurogas_nexus.application import functional_runs as service

    store = factory()
    try:
        with store() as session:
            owner_id(session, request)
            row, created = service.submit(
                session,
                request.state.identity,
                body,
                scopes=scopes,
                weather_evidence=evidence,
                request_hash=request_hash,
                evidence_warnings=warnings,
            )
            require_derived_access(request, row.source_scopes, resource="functional_run")
            result = payload(session, row)
            session.commit()
        if created:
            background.add_task(service.execute, store, result["run_id"])
        return envelope(result)
    except ValueError as exc:
        raise HTTPException(
            409
            if str(exc) == "idempotency_key_conflict"
            else (429 if str(exc) == "functional_queue_limit" else 422),
            detail={"code": "invalid_functional_submission", "reason": str(exc)},
        ) from exc


@router.get("/api/functional-runs/{run_id}")
def get_run(run_id: str, request: Request):
    with factory()() as session:
        return envelope(payload(session, load_owned(session, run_id, request)))


class Replay(BaseModel):
    model_config = ConfigDict(extra="forbid")
    idempotency_key: str = Field(min_length=1, max_length=80)


@router.post("/api/functional-runs/{run_id}/replay", status_code=202)
def replay_run(run_id: str, body: Replay, request: Request, background: BackgroundTasks):
    from eurogas_nexus.application import functional_runs as service
    from eurogas_nexus.application.calculation_manifest import numerical_bundle_fingerprint

    with factory()() as session:
        old = load_owned(session, run_id, request)
        if (
            old.manifest["engine_version"] != service.ENGINES[old.kind]
            or old.manifest.get("numerical_bundle_fingerprint") != numerical_bundle_fingerprint()
        ):
            raise HTTPException(409, detail={"code": "historical_engine_unavailable"})
        supplied = SubmitRun(
            kind=old.kind,
            inputs=old.inputs,
            idempotency_key=body.idempotency_key,
            version_refs=old.manifest["version_refs"],
            deadline_seconds=old.deadline_seconds,
        )
        scopes, evidence = tuple(old.source_scopes), old.manifest.get("weather_evidence")
        warnings = tuple(old.manifest.get("evidence_warnings", ()))
    return _submit(
        supplied, request, background, scopes=scopes, evidence=evidence, warnings=warnings
    )


class Compare(BaseModel):
    model_config = ConfigDict(extra="forbid")
    other_run_id: str = Field(min_length=1, max_length=64)
    attribute: bool = False
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=80)


@router.post("/api/functional-runs/{run_id}/compare")
def compare_runs(run_id: str, body: Compare, request: Request, background: BackgroundTasks):
    with factory()() as session:
        left, right = (
            load_owned(session, run_id, request),
            load_owned(session, body.other_run_id, request),
        )
        comparison = compare_analysis(left.manifest, right.manifest)
        comparison["same_result"] = content_hash(left.result) == content_hash(right.result)
        if not body.attribute:
            return envelope(comparison)
        if left.kind != "JOINT_OPTIMIZATION" or right.kind != left.kind or not body.idempotency_key:
            raise HTTPException(
                422, detail={"code": "joint_attribution_requires_two_joint_runs_and_key"}
            )
        submitted = SubmitRun(
            kind="SCENARIO_COMPARISON",
            inputs={"left": left.inputs, "right": right.inputs},
            idempotency_key=body.idempotency_key,
            version_refs={
                "left_manifest": left.manifest["manifest_hash"],
                "right_manifest": right.manifest["manifest_hash"],
            },
        )
        scopes = tuple(set(left.source_scopes) | set(right.source_scopes))
    return _submit(submitted, request, background, scopes=scopes)


@router.post("/api/functional-models")
def freeze_model(body: Compare, request: Request):
    from sqlalchemy import select

    from eurogas_nexus.db.models.functional import FunctionalModelRecord

    with factory()() as session:
        run = load_owned(session, body.other_run_id, request)
        if (
            run.kind not in {"WEATHER_VALIDATION", "WEATHER_PROFILE"}
            or not run.result
            or not run.result.get("eligible_for_shadow")
        ):
            raise HTTPException(422, detail={"code": "model_not_qualified_for_shadow"})
        digest = content_hash({"manifest": run.manifest, "report": run.result})
        row = session.scalar(
            select(FunctionalModelRecord).where(
                FunctionalModelRecord.owner_id == run.owner_id,
                FunctionalModelRecord.version_hash == digest,
            )
        )
        if row is None:
            row = FunctionalModelRecord(
                model_id=f"fmodel-{uuid4().hex[:24]}",
                owner_id=run.owner_id,
                run_id=run.run_id,
                target="NWE_WEATHER_PROFILE"
                if run.kind == "WEATHER_PROFILE"
                else "NWE_FLEXIBLE_SUPPLY_CALL",
                version_hash=digest,
                status="SHADOW",
                review={},
                created_at=datetime.now(UTC),
            )
            session.add(row)
            session.flush()
        data = _model(row)
        session.commit()
        return envelope(data)


def _model(row):
    return {
        "model_id": row.model_id,
        "run_id": row.run_id,
        "target": row.target,
        "version_hash": row.version_hash,
        "status": row.status,
        "review": row.review,
        "production_promoted": False,
    }


@router.get("/api/functional-models/{model_id}")
def get_model(model_id: str, request: Request):
    from eurogas_nexus.db.models.functional import FunctionalModelRecord

    with factory()() as session:
        row = session.get(FunctionalModelRecord, model_id)
        if row is None or row.owner_id != owner_id(session, request):
            raise HTTPException(404, detail={"code": "functional_model_not_found"})
        load_owned(session, row.run_id, request)
        return envelope(_model(row))


class Review(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str = Field(pattern="^(SHADOW|RESEARCH_APPROVED|RETIRED)$")
    note: str = Field(min_length=10, max_length=2000)


@router.patch("/api/functional-models/{model_id}")
def review_model(model_id: str, body: Review, request: Request):
    from eurogas_nexus.db.models.functional import FunctionalModelRecord
    from eurogas_nexus.security.capabilities import Capability, capabilities_for_principal

    if Capability.DECISION_REVIEW not in capabilities_for_principal(request.state.identity):
        raise HTTPException(403, detail={"code": "model_review_capability_required"})
    from eurogas_nexus.db.repositories.audit import record_audit_event

    with factory()() as session:
        row = session.get(FunctionalModelRecord, model_id, with_for_update=True)
        if row is None or row.owner_id != owner_id(session, request):
            raise HTTPException(404, detail={"code": "functional_model_not_found"})
        load_owned(session, row.run_id, request)
        previous = row.status
        row.status = body.status
        row.review = {
            "actor": request.state.identity.principal_id,
            "note": body.note,
            "reviewed_at": datetime.now(UTC).isoformat(),
        }
        record_audit_event(
            session,
            event_type="functional.model",
            principal=request.state.identity.name,
            action="model_review",
            resource=model_id,
            outcome="succeeded",
            severity="info",
            detail=f"{previous}->{body.status}",
            source_system="functional-analysis",
        )
        data = _model(row)
        session.commit()
        return envelope(data)


@router.get("/api/functional-runs")
def list_runs(request: Request):
    from sqlalchemy import select

    from eurogas_nexus.db.models.functional import FunctionalRunRecord
    from eurogas_nexus.db.models.jobs import JobRecord
    from eurogas_nexus.optimization.capabilities import engine_catalog

    with factory()() as session:
        rows = (
            session.execute(
                select(
                    FunctionalRunRecord.run_id,
                    FunctionalRunRecord.job_id,
                    FunctionalRunRecord.kind,
                    FunctionalRunRecord.source_scopes,
                    JobRecord.status,
                    JobRecord.progress,
                    JobRecord.error_code,
                )
                .join(JobRecord)
                .where(FunctionalRunRecord.owner_id == owner_id(session, request))
                .order_by(FunctionalRunRecord.created_at.desc())
                .limit(50)
            )
            .mappings()
            .all()
        )
        visible = []
        for row in rows:
            try:
                require_derived_access(request, row["source_scopes"], resource="functional_run")
            except HTTPException as exc:
                if exc.status_code != 403:
                    raise
                continue
            visible.append({k: v for k, v in row.items() if k != "source_scopes"})
        return envelope({"runs": visible, "engines": engine_catalog()})


class Predict(Replay):
    prediction_origin: AwareDatetime
    feature_policy_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    features: list[dict] = Field(min_length=1, max_length=31)


@router.post("/api/functional-models/{model_id}/predict", status_code=202)
def model_predict(model_id: str, body: Predict, request: Request, background: BackgroundTasks):
    from eurogas_nexus.application import functional_runs as service
    from eurogas_nexus.db.models.functional import FunctionalModelRecord

    with factory()() as session:
        model = session.get(FunctionalModelRecord, model_id)
        if model is None or model.owner_id != owner_id(session, request):
            raise HTTPException(404, detail={"code": "functional_model_not_found"})
        run = load_owned(session, model.run_id, request)
        if service.stale_dependencies(session, run.run_id):
            raise HTTPException(409, detail={"code": "model_dependencies_changed"})
        from eurogas_nexus.application.calculation_manifest import numerical_bundle_fingerprint

        if run.manifest.get("numerical_bundle_fingerprint") != numerical_bundle_fingerprint():
            raise HTTPException(409, detail={"code": "model_numerical_environment_changed"})
        if model.status == "RETIRED":
            raise HTTPException(409, detail={"code": "model_retired"})
        if model.target != "NWE_FLEXIBLE_SUPPLY_CALL":
            raise HTTPException(422, detail={"code": "not_a_prediction_model"})
        if body.feature_policy_hash != run.inputs["feature_policy_hash"]:
            raise HTTPException(422, detail={"code": "weather_feature_policy_mismatch"})
        inputs = {
            "model_id": model_id,
            "model_version": model.version_hash,
            "selection_available_at": run.result["selection_available_at"],
            "prediction_origin": body.prediction_origin.isoformat(),
            "coefficients": run.result["frozen_coefficients"],
            "feature_policy_hash": body.feature_policy_hash,
            "features": body.features,
            "reference_interval_radius": run.result["interval_radius"],
        }
        scopes = tuple(run.source_scopes)
    submitted = SubmitRun(
        kind="FROZEN_WEATHER", inputs=inputs, idempotency_key=body.idempotency_key
    )
    return _submit(submitted, request, background, scopes=scopes)


class Evaluate(Replay):
    prediction_run_id: str = Field(min_length=1, max_length=64)
    actuals: list[dict] = Field(min_length=1, max_length=31)
    evaluation_as_of: AwareDatetime
    maximum_mae_gwh: float = Field(ge=0, allow_inf_nan=False)


@router.post("/api/functional-models/{model_id}/evaluate", status_code=202)
def model_evaluate(model_id: str, body: Evaluate, request: Request, background: BackgroundTasks):
    from eurogas_nexus.db.models.functional import FunctionalModelRecord

    with factory()() as session:
        model = session.get(FunctionalModelRecord, model_id)
        if model is None or model.owner_id != owner_id(session, request):
            raise HTTPException(404, detail={"code": "functional_model_not_found"})
        run = load_owned(session, body.prediction_run_id, request)
        if run.kind != "FROZEN_WEATHER" or not run.result or run.result["model_id"] != model_id:
            raise HTTPException(422, detail={"code": "invalid_model_prediction_run"})
        inputs = {
            "prediction": run.result,
            "actuals": body.actuals,
            "evaluation_as_of": body.evaluation_as_of.isoformat(),
            "maximum_mae_gwh": body.maximum_mae_gwh,
        }
        scopes = tuple(run.source_scopes)
    submitted = SubmitRun(
        kind="SHADOW_EVALUATION", inputs=inputs, idempotency_key=body.idempotency_key
    )
    return _submit(submitted, request, background, scopes=scopes)


class Reconcile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    changes: dict[str, str] = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def valid_versions(self):
        SubmitRun.bounded_versions(self.changes)
        return self


@router.post("/api/functional-runs/reconcile")
def reconcile(body: Reconcile, request: Request):
    from eurogas_nexus.application import functional_runs as service

    with factory()() as session:
        affected = service.reconcile_dependencies(
            session, body.changes, owner_id=owner_id(session, request)
        )
        for run_id in affected:
            load_owned(session, run_id, request)
        session.commit()
        return envelope({"recompute_required": affected})
