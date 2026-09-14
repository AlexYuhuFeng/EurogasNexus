"""Research data foundation API (CR-14).

Read-only catalog plus governed dataset materialization. No raw unrestricted
licensed data is returned.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, ValidationError

from eurogas_nexus.application.research_registry import DatasetRegistryError
from eurogas_nexus.domain.research.datasets import (
    DatasetBuildResult,
    DatasetEvidenceRecord,
    DatasetSpec,
)
from eurogas_nexus.domain.research.temporal import (
    ObservationKind,
    TemporalIntegrityState,
)
from eurogas_nexus.security.identity import (
    AuthenticatedPrincipal,
    legacy_public_token_principal,
)
from eurogas_nexus.security.research_entitlement import (
    authorized_source_definitions,
    definition_for_runtime_source,
    effective_entitlement_envelope,
    principal_can_read_snapshot,
    row_export_policy,
)

router = APIRouter(tags=["research-data"])


class DatasetValidateRequest(BaseModel):
    dataset_spec: dict[str, Any]


class DatasetMaterializeRequest(BaseModel):
    dataset_spec: dict[str, Any]
    snapshot_id: str | None = Field(default=None, max_length=128)
    materialize: bool = True


class DatasetExportRequest(BaseModel):
    format: str = Field(default="parquet", pattern="^(parquet|csv)$")


def _session():
    if not _db_configured():
        raise HTTPException(
            status_code=503, detail="Runtime PostgreSQL is required for research data."
        )
    from eurogas_nexus.db.session import get_session_factory

    return get_session_factory()()


def _db_configured() -> bool:
    from eurogas_nexus.db.session import resolve_database_url

    return resolve_database_url() is not None


def _env(data: object, request: Request, *, source: str, warnings: list[str] | None = None) -> dict:
    return {
        "data": data,
        "meta": {
            "research_only": True,
            "human_review_required": True,
            "source_references": [source],
            "warnings": warnings or [],
        },
    }


def _feature_payload(row) -> dict[str, Any]:
    return {
        "feature_id": row.feature_id,
        "content_hash": row.content_hash,
        "status": row.status,
        "definition": row.definition_json,
    }


def _target_payload(row) -> dict[str, Any]:
    return {
        "target_id": row.target_id,
        "content_hash": row.content_hash,
        "status": row.status,
        "definition": row.definition_json,
    }


def _dataset_spec_error(exc: ValidationError) -> HTTPException:
    """Convert DatasetSpec validation into a safe, stable 422 contract."""

    issues: list[dict[str, str]] = []
    for error in exc.errors():
        location = ".".join(str(part) for part in error.get("loc", ())) or "dataset_spec"
        message = str(error.get("msg") or "")
        if "origin count" in message:
            code = "origin_count_limit"
            location = "forecast_origin_frequency"
            safe_message = "The requested dataset has too many forecast origins."
        elif location == "forecast_origin_frequency" or "forecast_origin_frequency" in message:
            code = "frequency_invalid"
            location = "forecast_origin_frequency"
            safe_message = (
                "forecast_origin_frequency must be a positive integer with "
                "suffix 'h' or 'd'."
            )
        elif location in {"start", "end"} or "end must be after start" in message:
            location = "start/end"
            code = "date_bounds_invalid"
            safe_message = "end must be after start."
        elif location == "history_lookback" or "history_lookback" in message:
            location = "history_lookback"
            code = "history_lookback_invalid"
            safe_message = (
                "history_lookback must be non-negative and no greater than 3650 days."
            )
        else:
            code = "dataset_field_invalid"
            safe_message = "The dataset specification contains an invalid field."
        issues.append({"field": location, "code": code, "message": safe_message})
    return HTTPException(
        status_code=422,
        detail={
            "error": "dataset_spec_invalid",
            "message": "Dataset specification failed validation.",
            "issues": issues,
        },
    )


def _dataset_build_error() -> HTTPException:
    """Return a safe 422 for a dataset build rejected by domain validation."""

    return HTTPException(
        status_code=422,
        detail={
            "error": "dataset_build_invalid",
            "message": "Dataset specification cannot be materialized.",
        },
    )


def _registry_error(exc: DatasetRegistryError) -> HTTPException:
    """Return a safe, field-level 422 for unresolvable registry ids."""

    return HTTPException(
        status_code=422,
        detail={
            "error": exc.error_code,
            "message": "Dataset specification references unavailable registry ids.",
            "issues": exc.issues,
        },
    )


def _artifact_store_error(detail: str) -> HTTPException:
    """Return a safe 503 when research artifacts cannot be stored."""

    return HTTPException(
        status_code=503,
        detail={
            "code": "artifact_store_unavailable",
            "message": "Research artifact storage is not available.",
            "detail": detail[:256],
        },
    )


def _request_principal(request: Request) -> AuthenticatedPrincipal:
    """Return the authenticated principal, preserving dev-token compatibility."""

    return getattr(request.state, "identity", legacy_public_token_principal())


def _source_access_denied() -> HTTPException:
    return HTTPException(
        status_code=403,
        detail={
            "code": "source_entitlement_denied",
            "message": "The current identity is not entitled to the requested sources.",
        },
    )


@router.get("/api/research/features")
def list_features(request: Request) -> dict:
    from eurogas_nexus.db.repositories.research import list_feature_definitions

    with _session() as session:
        rows = list_feature_definitions(session)
    return _env([_feature_payload(row) for row in rows], request, source="research-catalog")


@router.get("/api/research/features/{feature_id}")
def get_feature(feature_id: str, request: Request) -> dict:
    from eurogas_nexus.db.models import FeatureDefinitionRecord

    with _session() as session:
        row = session.get(FeatureDefinitionRecord, feature_id)
        if row is None:
            raise HTTPException(status_code=404, detail=f"Unknown feature: {feature_id}")
        payload = _feature_payload(row)
    return _env(payload, request, source="research-catalog")


@router.get("/api/research/targets")
def list_targets(request: Request) -> dict:
    from eurogas_nexus.db.repositories.research import list_target_definitions

    with _session() as session:
        rows = list_target_definitions(session)
    return _env([_target_payload(row) for row in rows], request, source="research-catalog")


@router.get("/api/research/targets/{target_id}")
def get_target(target_id: str, request: Request) -> dict:
    from eurogas_nexus.db.models import TargetDefinitionRecord

    with _session() as session:
        row = session.get(TargetDefinitionRecord, target_id)
        if row is None:
            raise HTTPException(status_code=404, detail=f"Unknown target: {target_id}")
        payload = _target_payload(row)
    return _env(payload, request, source="research-catalog")


@router.get("/api/research/capabilities")
def list_research_capabilities(request: Request) -> dict:
    from eurogas_nexus.domain.research.capabilities import REGISTERED_RESEARCH_CAPABILITIES

    return _env(
        [capability.public_metadata() for capability in REGISTERED_RESEARCH_CAPABILITIES],
        request,
        source="domain-contract",
    )


@router.post("/api/research/datasets/validate")
def validate_dataset_spec(body: DatasetValidateRequest, request: Request) -> dict:
    """Validate a spec against the canonical registry, without building it.

    CR14-SEMANTICS-001: validation resolves feature/target/entity/source/policy
    ids through the same resolver the build path uses, so an unknown or
    unhonourable id fails here with a structured field issue instead of
    surfacing later as an opaque build failure. ``issues`` entries are
    ``{field, code, message}`` objects; the envelope keys are unchanged.
    """

    try:
        spec = DatasetSpec.model_validate(body.dataset_spec)
    except ValidationError as exc:
        raise _dataset_spec_error(exc) from None
    registry_status = "RESOLVED"
    if _db_configured():
        from eurogas_nexus.application.research_registry import (
            resolve_dataset_registry,
        )

        with _session() as session:
            resolution = resolve_dataset_registry(session, spec)
        issues = resolution.issue_list()
    else:
        # Fail closed: without the registry the spec cannot be proven valid, so
        # validation reports a blocker instead of claiming success.
        registry_status = "UNAVAILABLE"
        issues = [
            {
                "field": "dataset_spec",
                "code": "registry_unavailable",
                "message": "Runtime PostgreSQL is required to resolve dataset registry ids.",
            }
        ]
    return _env(
        {
            "ok": not issues,
            "issues": issues,
            "spec_hash": spec.content_hash(),
            "registry_resolution": registry_status,
        },
        request,
        source="domain-contract",
    )


@router.get("/api/research/datasets")
def list_datasets(request: Request) -> dict:
    from eurogas_nexus.db.repositories.research import list_dataset_snapshots

    principal = _request_principal(request)
    with _session() as session:
        rows = list_dataset_snapshots(session)
    payload = [
        {
            "dataset_snapshot_id": row.dataset_snapshot_id,
            "dataset_spec_id": row.dataset_spec_id,
            "source_cutoff_utc": row.source_cutoff_utc.isoformat(),
            "row_count": row.row_count,
            "column_count": row.column_count,
            "coverage": row.coverage,
            "temporal_integrity": row.temporal_integrity,
            "status": row.status,
            "created_at_utc": row.created_at_utc.isoformat(),
        }
        for row in rows
        if principal_can_read_snapshot(principal, row.metadata_json) is not None
    ]
    return _env(payload, request, source="research-catalog")


@router.post("/api/research/datasets")
def materialize_dataset(body: DatasetMaterializeRequest, request: Request) -> dict:
    """Build and persist one immutable point-in-time dataset snapshot."""

    if not _db_configured():
        raise HTTPException(
            status_code=503, detail="Runtime PostgreSQL is required for dataset builds."
        )
    principal = _request_principal(request)
    try:
        spec = DatasetSpec.model_validate(body.dataset_spec)
    except ValidationError as exc:
        raise _dataset_spec_error(exc) from None
    with _session() as session:
        try:
            result, dependency_rows, issue_rows = _build_from_runtime(
                session, spec, snapshot_id=body.snapshot_id, principal=principal
            )
        except HTTPException:
            raise
        except DatasetRegistryError as exc:
            raise _registry_error(exc) from exc
        except (KeyError, TypeError, ValueError) as exc:
            raise _dataset_build_error() from exc
        if body.materialize:
            from eurogas_nexus.application import research_artifacts
            from eurogas_nexus.db.repositories.research import persist_dataset_snapshot

            try:
                # CR14-ARTIFACT-001: materialize the format-specific artifacts
                # this deployment can produce before persisting the snapshot, so
                # a snapshot can never reference an artifact that was not
                # written, and an unusable store fails closed.
                artifacts = research_artifacts.write_dataset_artifacts(result)
            except research_artifacts.ArtifactStoreUnavailable as exc:
                raise _artifact_store_error(exc.detail) from exc
            persist_dataset_snapshot(
                session,
                metadata=result.as_metadata(),
                dependencies=dependency_rows,
                issues=issue_rows,
                artifacts=artifacts,
            )
            session.commit()
    return _env(
        {
            **result.as_metadata(),
            "rows": result.rows[:100],
            "temporal_integrity": result.quality_report["temporal_integrity"],
        },
        request,
        source="runtime-postgresql",
        warnings=result.warnings,
    )


@router.get("/api/research/datasets/{dataset_snapshot_id}")
def get_dataset(dataset_snapshot_id: str, request: Request) -> dict:
    from eurogas_nexus.db.repositories.research import get_dataset_snapshot

    principal = _request_principal(request)
    with _session() as session:
        row = get_dataset_snapshot(session, dataset_snapshot_id)
        if row is None:
            raise HTTPException(
                status_code=404, detail=f"Unknown dataset snapshot: {dataset_snapshot_id}"
            )
        if principal_can_read_snapshot(principal, row.metadata_json) is None:
            raise _source_access_denied()
        payload = {
            "dataset_snapshot_id": row.dataset_snapshot_id,
            "dataset_spec_id": row.dataset_spec_id,
            "spec_hash": row.spec_hash,
            "ontology_version": row.ontology_version,
            "source_cutoff_utc": row.source_cutoff_utc.isoformat(),
            "row_count": row.row_count,
            "column_count": row.column_count,
            "coverage": row.coverage,
            "temporal_integrity": row.temporal_integrity,
            "entitlement_envelope": row.entitlement_envelope,
            "artifact_ref": row.artifact_ref,
            "status": row.status,
            "metadata": row.metadata_json,
        }
    return _env(payload, request, source="runtime-postgresql")


@router.get("/api/research/datasets/{dataset_snapshot_id}/quality")
def get_dataset_quality(dataset_snapshot_id: str, request: Request) -> dict:
    from eurogas_nexus.db.repositories.research import get_dataset_snapshot

    principal = _request_principal(request)
    with _session() as session:
        row = get_dataset_snapshot(session, dataset_snapshot_id)
        if row is None:
            raise HTTPException(
                status_code=404, detail=f"Unknown dataset snapshot: {dataset_snapshot_id}"
            )
        if principal_can_read_snapshot(principal, row.metadata_json) is None:
            raise _source_access_denied()
        metadata = row.metadata_json or {}
        payload = {
            "dataset_snapshot_id": row.dataset_snapshot_id,
            "quality_report": metadata.get("quality_report", {}),
            "leakage_issues": metadata.get("leakage_issues", []),
            "warnings": metadata.get("warnings", []),
        }
    return _env(payload, request, source="runtime-postgresql")


@router.post("/api/research/datasets/{dataset_snapshot_id}/export")
def export_dataset(dataset_snapshot_id: str, body: DatasetExportRequest, request: Request) -> dict:
    """Return a reference to the stored artifact of the requested format.

    CR14-ARTIFACT-001: the requested format is matched against the snapshot's
    persisted ``dataset_artifacts`` rows. Rights are derived server-side from
    canonical provenance (a request envelope never authorizes an export), and the
    call fails closed with a structured error when no artifact of that format was
    registered -- it never returns HTTP 200 with a null reference.
    """

    from eurogas_nexus.application import research_artifacts
    from eurogas_nexus.db.repositories.research import (
        get_dataset_snapshot,
        list_dataset_artifacts,
    )

    principal = _request_principal(request)
    with _session() as session:
        row = get_dataset_snapshot(session, dataset_snapshot_id)
        if row is None:
            raise HTTPException(
                status_code=404, detail=f"Unknown dataset snapshot: {dataset_snapshot_id}"
            )
        definitions = principal_can_read_snapshot(principal, row.metadata_json)
        if definitions is None:
            raise _source_access_denied()
        envelope = effective_entitlement_envelope(definitions)
        policy = envelope["export_policy"]
        if policy != "EXPORT_ALLOWED":
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "export_denied_entitlement",
                    "message": "Export is not permitted by the canonical source policy.",
                    "policy": policy,
                },
            )
        artifacts = list_dataset_artifacts(session, dataset_snapshot_id)
        available_formats = sorted({artifact.format for artifact in artifacts})
        artifact = next(
            (item for item in artifacts if item.format == body.format), None
        )
        if artifact is None:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "artifact_not_available",
                    "message": (
                        "No stored artifact matches the requested format for this snapshot."
                    ),
                    "format": body.format,
                    "available_formats": available_formats,
                    "reason": "FORMAT_NOT_REGISTERED",
                },
            )
        file_present = True
        try:
            file_present = research_artifacts.resolve_artifact_file(
                artifact.artifact_path
            ).is_file()
        except research_artifacts.ArtifactStoreUnavailable:
            file_present = False
        if not file_present:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "artifact_not_available",
                    "message": "The registered artifact is no longer present in storage.",
                    "format": body.format,
                    "available_formats": available_formats,
                    "reason": "FILE_MISSING",
                },
            )
        payload = {
            "dataset_snapshot_id": dataset_snapshot_id,
            "format": body.format,
            "artifact_ref": artifact.artifact_path,
            "artifact_id": artifact.artifact_id,
            "artifact_sha256": artifact.sha256,
            "available_formats": available_formats,
            "entitlement_policy": policy,
        }
    return _env(
        payload,
        request,
        source="runtime-postgresql",
        warnings=[
            "EXPORT_REFERENCE_ONLY: the artifact stays server-side; this response "
            "returns a governed reference, not dataset rows."
        ],
    )


def _build_from_runtime(
    session,
    spec: DatasetSpec,
    *,
    snapshot_id: str | None = None,
    principal: AuthenticatedPrincipal | None = None,
) -> tuple[DatasetBuildResult, list[dict[str, str]], list[dict[str, str]]]:
    """Build one snapshot from runtime observation tables.

    Market observations are mapped through their metadata (hub/tenor) into
    canonical series. Temporal metadata is consulted when present; otherwise
    the source is TEMPORAL_APPROXIMATE and STRICT builds fail.

    CR14-SEMANTICS-001: the spec's registry ids are resolved through the same
    shared resolver used by validation (raising ``DatasetRegistryError`` with
    field-level issues when they cannot be resolved), records are filtered by
    ``spec.entity_ids``, and the resolved ``spec.resampling_policy_id`` is the
    policy actually applied by the builder.
    """

    from eurogas_nexus.application.research_registry import require_dataset_registry
    from eurogas_nexus.db.models import (
        MarketObservationRecord,
        ObservationTemporalMetadataRecord,
    )
    from eurogas_nexus.domain.research.ontology import (
        CanonicalEntityType,
        canonical_entity_id,
    )

    principal = principal or legacy_public_token_principal()
    resolution = require_dataset_registry(session, spec)
    authorized_sources = authorized_source_definitions(principal, spec.source_restrictions)
    if not authorized_sources:
        raise _source_access_denied()
    source_systems = [definition.provider for definition in authorized_sources]
    source_by_system = {
        definition.provider.casefold(): definition for definition in authorized_sources
    }

    features = resolution.features
    targets = resolution.targets
    policy = resolution.resampling_policy
    if policy is None:  # pragma: no cover - guarded by require_dataset_registry
        raise DatasetRegistryError(
            [
                {
                    "field": "resampling_policy_id",
                    "code": "unknown_resampling_policy_id",
                    "message": "resampling policy could not be resolved",
                }
            ]
        )
    requested_entity_ids = set(resolution.entity_ids)

    records: list[DatasetEvidenceRecord] = []
    history_start = spec.start - spec.history_lookback
    market_query = (
        session.query(MarketObservationRecord)
        .filter(MarketObservationRecord.observed_at_utc >= history_start)
        .filter(MarketObservationRecord.observed_at_utc < spec.end)
    )
    market_query = market_query.filter(MarketObservationRecord.source_system.in_(source_systems))
    market_rows = market_query.all()
    temporal_query = (
        session.query(ObservationTemporalMetadataRecord)
        .join(
            MarketObservationRecord,
            ObservationTemporalMetadataRecord.observation_id
            == MarketObservationRecord.observation_id,
        )
        .filter(MarketObservationRecord.source_system.in_(source_systems))
        .filter(MarketObservationRecord.observed_at_utc >= history_start)
        .filter(MarketObservationRecord.observed_at_utc < spec.end)
    )
    temporal_rows = {
        row.observation_id: row for row in temporal_query.all()
    }
    trusted_source_ids: set[str] = set()
    for row in market_rows:
        source_definition = (
            source_by_system.get(str(row.source_system).casefold())
            or definition_for_runtime_source(str(row.source_system))
        )
        if source_definition is None:
            continue
        metadata = row.metadata_json or {}
        hub = str(metadata.get("hub") or row.market_venue).strip().upper()
        tenor = str(metadata.get("tenor") or row.product).strip().lower()
        if hub not in {"NBP", "TTF"}:
            continue
        entity_id = canonical_entity_id(CanonicalEntityType.MARKET_HUB, hub)
        # An empty entity_ids list means "no entity restriction"; otherwise the
        # requested canonical entities are the only rows that may enter the build.
        if requested_entity_ids and entity_id not in requested_entity_ids:
            continue
        series_id = f"market.price.{hub}.{tenor.upper().replace('-', '_')}"
        temporal = temporal_rows.get(row.observation_id)
        if temporal is not None and temporal.available_at_utc is not None:
            available_at = temporal.available_at_utc
            integrity = TemporalIntegrityState(temporal.temporal_integrity)
        else:
            available_at = None
            integrity = TemporalIntegrityState.TEMPORAL_APPROXIMATE
        records.append(
            DatasetEvidenceRecord(
                record_id=row.observation_id,
                series_id=series_id,
                entity_id=entity_id,
                observed_at=row.observed_at_utc,
                available_at=available_at,
                ingested_at=temporal.ingested_at_utc if temporal else None,
                value=row.price,
                unit=row.unit,
                currency=row.currency,
                observation_kind=(
                    ObservationKind.SIMULATED
                    if str(row.source_system).endswith("_Sim")
                    else ObservationKind.ACTUAL
                ),
                temporal_integrity=integrity,
                source_reference=row.source_reference,
                export_policy=row_export_policy(source_definition),
            )
        )
        trusted_source_ids.add(source_definition.source_id)
    if not records:
        raise HTTPException(
            status_code=422,
            detail="No eligible runtime observations matched the dataset spec.",
        )

    from eurogas_nexus.domain.research.datasets import build_dataset

    result = build_dataset(
        spec,
        records,
        features,
        targets,
        policy,
        snapshot_id=snapshot_id,
    )
    trusted_ids = sorted(trusted_source_ids)
    result.trusted_source_ids = trusted_ids
    used_definitions = tuple(
        definition
        for definition in authorized_sources
        if definition.source_id in trusted_source_ids
    )
    result.effective_entitlement_envelope = effective_entitlement_envelope(used_definitions)
    dependencies = [
        {
            "dependency_id": f"dep:{result.dataset_snapshot_id}:{feature_id}",
            "dependency_type": "feature",
            "dependency_id_ref": feature_id,
            "version_ref": features[feature_id].version(),
        }
        for feature_id in spec.feature_ids
    ]
    issue_rows = [
        {
            "issue_id": f"issue:{result.dataset_snapshot_id}:{index}",
            "severity": str(issue.get("severity")),
            "code": str(issue.get("code")),
            "detail": str(issue.get("detail")),
        }
        for index, issue in enumerate(result.leakage_issues)
    ]
    return result, dependencies, issue_rows
