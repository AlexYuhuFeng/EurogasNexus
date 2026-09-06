"""Research data foundation API (CR-14).

Read-only catalog plus governed dataset materialization. No raw unrestricted
licensed data is returned.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from eurogas_nexus.domain.research.datasets import (
    DatasetBuildResult,
    DatasetEvidenceRecord,
    DatasetSpec,
)
from eurogas_nexus.domain.research.resampling import ResamplingPolicy
from eurogas_nexus.domain.research.temporal import (
    ObservationKind,
    TemporalIntegrityState,
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
    try:
        spec = DatasetSpec.model_validate(body.dataset_spec)
        issues = []
        if not spec.target_ids:
            issues.append("at least one target_id is required")
        return _env(
            {"ok": not issues, "issues": issues, "spec_hash": spec.content_hash()},
            request,
            source="domain-contract",
        )
    except Exception as exc:
        return _env({"ok": False, "issues": [str(exc)]}, request, source="domain-contract")


@router.get("/api/research/datasets")
def list_datasets(request: Request) -> dict:
    from eurogas_nexus.db.repositories.research import list_dataset_snapshots

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
    ]
    return _env(payload, request, source="research-catalog")


@router.post("/api/research/datasets")
def materialize_dataset(body: DatasetMaterializeRequest, request: Request) -> dict:
    """Build and persist one immutable point-in-time dataset snapshot."""

    if not _db_configured():
        raise HTTPException(
            status_code=503, detail="Runtime PostgreSQL is required for dataset builds."
        )
    spec = DatasetSpec.model_validate(body.dataset_spec)
    with _session() as session:
        result, dependency_rows, issue_rows = _build_from_runtime(
            session, spec, snapshot_id=body.snapshot_id
        )
        if body.materialize:
            from eurogas_nexus.db.repositories.research import persist_dataset_snapshot

            persist_dataset_snapshot(
                session,
                metadata=result.as_metadata(),
                dependencies=dependency_rows,
                issues=issue_rows,
                artifacts=[],
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

    with _session() as session:
        row = get_dataset_snapshot(session, dataset_snapshot_id)
        if row is None:
            raise HTTPException(
                status_code=404, detail=f"Unknown dataset snapshot: {dataset_snapshot_id}"
            )
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

    with _session() as session:
        row = get_dataset_snapshot(session, dataset_snapshot_id)
        if row is None:
            raise HTTPException(
                status_code=404, detail=f"Unknown dataset snapshot: {dataset_snapshot_id}"
            )
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
    """Export a persisted snapshot under its entitlement envelope."""

    from eurogas_nexus.db.repositories.research import get_dataset_snapshot

    with _session() as session:
        row = get_dataset_snapshot(session, dataset_snapshot_id)
        if row is None:
            raise HTTPException(
                status_code=404, detail=f"Unknown dataset snapshot: {dataset_snapshot_id}"
            )
        envelope = row.entitlement_envelope or {}
        policy = str(envelope.get("export_policy") or "UNKNOWN").upper()
        if policy != "EXPORT_ALLOWED":
            raise HTTPException(
                status_code=403,
                detail={"code": "export_denied_entitlement", "policy": policy},
            )
        payload = {
            "dataset_snapshot_id": dataset_snapshot_id,
            "format": body.format,
            "artifact_ref": row.artifact_ref,
            "entitlement_policy": policy,
        }
    return _env(payload, request, source="runtime-postgresql")


def _build_from_runtime(
    session,
    spec: DatasetSpec,
    *,
    snapshot_id: str | None = None,
) -> tuple[DatasetBuildResult, list[dict[str, str]], list[dict[str, str]]]:
    """Build one snapshot from runtime observation tables.

    Market observations are mapped through their metadata (hub/tenor) into
    canonical series. Temporal metadata is consulted when present; otherwise
    the source is TEMPORAL_APPROXIMATE and STRICT builds fail.
    """

    from eurogas_nexus.db.models import (
        FeatureDefinitionRecord,
        MarketObservationRecord,
        ObservationTemporalMetadataRecord,
        ResamplingPolicyRecord,
        TargetDefinitionRecord,
    )
    from eurogas_nexus.domain.research.features import FeatureDefinition as FeatureDef
    from eurogas_nexus.domain.research.resampling import ResamplingPolicy as PolicyDef
    from eurogas_nexus.domain.research.targets import TargetDefinition as TargetDef

    feature_rows = list(session.query(FeatureDefinitionRecord).all())
    target_rows = list(session.query(TargetDefinitionRecord).all())
    policy_rows = list(session.query(ResamplingPolicyRecord).all())
    features = {
        row.feature_id: FeatureDef.model_validate(row.definition_json) for row in feature_rows
    }
    targets = {row.target_id: TargetDef.model_validate(row.definition_json) for row in target_rows}
    policy = (
        PolicyDef.model_validate(policy_rows[0].definition_json)
        if policy_rows
        else ResamplingPolicy(semantic_type="market_price")
    )

    temporal_rows = {
        row.observation_id: row for row in session.query(ObservationTemporalMetadataRecord).all()
    }
    records: list[DatasetEvidenceRecord] = []
    history_start = spec.start - spec.history_lookback
    market_query = (
        session.query(MarketObservationRecord)
        .filter(MarketObservationRecord.observed_at_utc >= history_start)
        .filter(MarketObservationRecord.observed_at_utc < spec.end)
    )
    if spec.source_restrictions:
        market_query = market_query.filter(
            MarketObservationRecord.source_system.in_(spec.source_restrictions)
        )
    market_rows = market_query.all()
    for row in market_rows:
        metadata = row.metadata_json or {}
        hub = str(metadata.get("hub") or row.market_venue).strip().upper()
        tenor = str(metadata.get("tenor") or row.product).strip().lower()
        if hub not in {"NBP", "TTF"}:
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
                entity_id=f"ent:market_hub:{hub}",
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
                export_policy="EXPORT_ALLOWED",
            )
        )
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
