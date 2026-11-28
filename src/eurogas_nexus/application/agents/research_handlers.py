"""Dataset and review capability handlers (CR-15)."""

from __future__ import annotations

from typing import Any

from eurogas_nexus.domain.agents.contracts import (
    ActionPolicy,
    CapabilityDefinition,
    CapabilityDomain,
    CapabilityFailureCode,
    CapabilityResult,
    CapabilityStatus,
    DeterminismClass,
    IdempotencyClass,
    SideEffectClass,
)
from eurogas_nexus.security.identity import AuthenticatedPrincipal
from eurogas_nexus.security.research_entitlement import principal_can_read_snapshot


def _result(definition: CapabilityDefinition, data: Any) -> CapabilityResult:
    return CapabilityResult.success(
        capability=definition.capability_id,
        capability_version=definition.capability_version,
        data=data,
    )


def _blocked(
    definition: CapabilityDefinition, code: CapabilityFailureCode, detail: str
) -> CapabilityResult:
    return CapabilityResult.blocked(
        capability=definition.capability_id,
        capability_version=definition.capability_version,
        code=code,
        detail=detail,
    )


def _schema(properties: dict[str, Any], *, required: list[str] | None = None) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required or [],
        "additionalProperties": False,
    }


def _research_principal(context) -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        principal_id=context.principal_id,
        name=context.principal_id,
        principal_type="USER",
        role=context.role,
        status="ACTIVE",
        data_scopes=tuple(context.data_scopes),
        roles=tuple(context.roles or [context.role]),
        auth_method="identity_key",
    )


def _register(
    registry,
    *,
    capability_id: str,
    name: str,
    domain: CapabilityDomain,
    description: str,
    input_schema: dict[str, Any],
    output_schema: dict[str, Any],
    handler,
    side_effect_class: SideEffectClass = SideEffectClass.READ_ONLY,
    required_permissions: list[str] | None = None,
    action_policy: ActionPolicy = ActionPolicy.AUTO_ALLOWED,
    mcp_name: str | None = None,
    timeout_policy: str = "30s",
) -> None:
    registry.register(
        CapabilityDefinition(
            capability_id=capability_id,
            name=name,
            domain=domain,
            description=description,
            input_schema=input_schema,
            output_schema=output_schema,
            determinism_class=DeterminismClass.DETERMINISTIC,
            side_effect_class=side_effect_class,
            required_permissions=required_permissions or ["capability.invoke"],
            capability_version="v1",
            status=CapabilityStatus.ACTIVE,
            owner="research",
            action_policy=action_policy,
            mcp_name=mcp_name,
            timeout_policy=timeout_policy,
            idempotency=IdempotencyClass.NOT_IDEMPOTENT,
        ),
        handler,
    )


def register_research_capabilities(registry) -> None:
    from eurogas_nexus.application.agents.review_handlers import (
        register_review_capabilities,
    )

    _register_dataset_capabilities(registry)
    register_review_capabilities(registry)


def _register_dataset_capabilities(registry) -> None:
    from eurogas_nexus.application.agents.db_bridge import session_scope
    from eurogas_nexus.application.research_artifacts import (
        ArtifactStoreUnavailable,
        write_dataset_artifacts,
    )
    from eurogas_nexus.application.research_registry import (
        DatasetRegistryError,
        resolve_dataset_registry,
    )
    from eurogas_nexus.domain.research.datasets import DatasetSpec

    def validate_spec(arguments, _context):
        definition = registry.get("dataset.validate_spec")
        try:
            spec = DatasetSpec.model_validate(arguments.get("spec") or {})
        except Exception as exc:
            return _result(definition, {"ok": False, "issues": [str(exc)]})
        # Same shared resolver as the build path, so an agent cannot receive a
        # different verdict at validate time than at build time.
        registry_status = "RESOLVED"
        with session_scope() as session:
            if session is None:
                registry_status = "UNAVAILABLE"
                issues: list[dict[str, str]] = [
                    {
                        "field": "dataset_spec",
                        "code": "registry_unavailable",
                        "message": (
                            "Runtime PostgreSQL is required to resolve dataset registry ids."
                        ),
                    }
                ]
            else:
                issues = resolve_dataset_registry(session, spec).issue_list()
        return _result(
            definition,
            {
                "ok": not issues,
                "issues": issues,
                "spec_hash": spec.content_hash(),
                "qualified_version": spec.qualified_version(),
                "registry_resolution": registry_status,
            },
        )

    def build(arguments, _context):
        definition = registry.get("dataset.build")
        with session_scope() as session:
            if session is None:
                return _blocked(
                    definition,
                    CapabilityFailureCode.DATA_MISSING,
                    "Runtime PostgreSQL is required for dataset builds",
                )
            from eurogas_nexus.api.routes.public.research_data import _build_from_runtime
            from eurogas_nexus.db.repositories.research import persist_dataset_snapshot

            spec = DatasetSpec.model_validate(arguments.get("spec") or {})
            try:
                result, dependencies, issues = _build_from_runtime(
                    session, spec, principal=_research_principal(_context)
                )
            except DatasetRegistryError as exc:
                return _blocked(
                    definition,
                    CapabilityFailureCode.ENTITY_NOT_FOUND,
                    "; ".join(item["message"] for item in exc.issues),
                )
            try:
                # CR14-ARTIFACT-001: the agent build path registers the same
                # format-specific artifacts as the HTTP build path.
                artifacts = write_dataset_artifacts(result)
            except ArtifactStoreUnavailable as exc:
                return _blocked(
                    definition,
                    CapabilityFailureCode.DATA_MISSING,
                    f"Research artifact store is unavailable: {exc.detail}",
                )
            # The return value carries whether the snapshot was newly created; the
            # handler reports the built dataset either way, so a repeat build of
            # unchanged inputs succeeds instead of failing on the snapshot id.
            persist_dataset_snapshot(
                session,
                metadata=result.as_metadata(),
                dependencies=dependencies,
                issues=issues,
                artifacts=artifacts,
            )[0]
            session.commit()
        return _result(
            definition,
            {
                **result.as_metadata(),
                "rows": result.rows[:50],
                "artifacts": artifacts,
            },
        )

    def export_dataset(arguments, context):
        definition = registry.get("dataset.export")
        with session_scope() as session:
            if session is None:
                return _blocked(
                    definition,
                    CapabilityFailureCode.DATA_MISSING,
                    "Runtime PostgreSQL is not configured",
                )
            from eurogas_nexus.db.repositories.research import (
                get_dataset_snapshot,
                list_dataset_artifacts,
            )
            from eurogas_nexus.security.research_entitlement import (
                effective_entitlement_envelope,
            )

            snapshot_id = str(arguments["dataset_snapshot_id"])
            artifact_format = str(arguments.get("format") or "parquet")
            row = get_dataset_snapshot(session, snapshot_id)
            if row is None:
                return _blocked(definition, CapabilityFailureCode.ENTITY_NOT_FOUND, snapshot_id)
            # Rights come from persisted canonical provenance and current grants
            # only: a request envelope (including any entitlement_envelope or
            # export_policy field) can never authorize an export.
            definitions = principal_can_read_snapshot(
                _research_principal(context), row.metadata_json
            )
            if definitions is None:
                return _blocked(
                    definition,
                    CapabilityFailureCode.ENTITLEMENT_DENIED,
                    "Snapshot source provenance is not authorized for this identity",
                )
            if getattr(row, "status", None) == "BLOCKED":
                return _blocked(
                    definition,
                    CapabilityFailureCode.TEMPORAL_INTEGRITY_INSUFFICIENT,
                    "Snapshot failed its STRICT leakage checks and cannot be exported",
                )
            policy = effective_entitlement_envelope(definitions)["export_policy"]
            if policy != "EXPORT_ALLOWED":
                code = (
                    "EXPORT_DENIED_UNKNOWN_POLICY"
                    if policy == "UNKNOWN"
                    else "EXPORT_DENIED_ENTITLEMENT"
                )
                return _blocked(
                    definition,
                    CapabilityFailureCode.ENTITLEMENT_DENIED,
                    f"{code}: canonical export policy is {policy}",
                )
            artifacts = list_dataset_artifacts(session, snapshot_id)
            available_formats = sorted({artifact.format for artifact in artifacts})
            artifact = next((item for item in artifacts if item.format == artifact_format), None)
            if artifact is None:
                # Fail closed: never return a reference for an artifact that was
                # not registered, and never fabricate one.
                return _blocked(
                    definition,
                    CapabilityFailureCode.DATA_MISSING,
                    "EXPORT_DENIED_ARTIFACT_UNAVAILABLE: no stored "
                    f"{artifact_format} artifact; available formats: {available_formats}",
                )
            payload = {
                "dataset_snapshot_id": snapshot_id,
                "artifact_id": artifact.artifact_id,
                "format": artifact.format,
                "artifact_ref": artifact.artifact_path,
                "sha256": artifact.sha256,
                "entitlement_policy": policy,
                "research_only": True,
                "human_review_required": True,
            }
        return _result(definition, payload)

    def inspect_snapshot(arguments, context):
        definition = registry.get("dataset.inspect_snapshot")
        with session_scope() as session:
            if session is None:
                return _blocked(
                    definition,
                    CapabilityFailureCode.DATA_MISSING,
                    "Runtime PostgreSQL is not configured",
                )
            from eurogas_nexus.db.repositories.research import get_dataset_snapshot

            row = get_dataset_snapshot(session, str(arguments["dataset_snapshot_id"]))
            if row is None:
                return _blocked(
                    definition,
                    CapabilityFailureCode.ENTITY_NOT_FOUND,
                    str(arguments["dataset_snapshot_id"]),
                )
            if principal_can_read_snapshot(_research_principal(context), row.metadata_json) is None:
                return _blocked(
                    definition,
                    CapabilityFailureCode.ENTITLEMENT_DENIED,
                    "Snapshot source provenance is not authorized for this identity",
                )
            payload = {
                "dataset_snapshot_id": row.dataset_snapshot_id,
                "dataset_spec_id": row.dataset_spec_id,
                "spec_hash": row.spec_hash,
                "ontology_version": row.ontology_version,
                "row_count": row.row_count,
                "column_count": row.column_count,
                "coverage": row.coverage,
                "temporal_integrity": row.temporal_integrity,
                "content_hash": row.content_hash,
                "artifact_ref": row.artifact_ref,
                "status": row.status,
            }
        return _result(definition, payload)

    def quality_report(arguments, context):
        definition = registry.get("dataset.get_quality_report")
        with session_scope() as session:
            if session is None:
                return _blocked(
                    definition,
                    CapabilityFailureCode.DATA_MISSING,
                    "Runtime PostgreSQL is not configured",
                )
            from eurogas_nexus.db.repositories.research import get_dataset_snapshot

            row = get_dataset_snapshot(session, str(arguments["dataset_snapshot_id"]))
            if row is None:
                return _blocked(
                    definition,
                    CapabilityFailureCode.ENTITY_NOT_FOUND,
                    str(arguments["dataset_snapshot_id"]),
                )
            if principal_can_read_snapshot(_research_principal(context), row.metadata_json) is None:
                return _blocked(
                    definition,
                    CapabilityFailureCode.ENTITLEMENT_DENIED,
                    "Snapshot source provenance is not authorized for this identity",
                )
            metadata = row.metadata_json or {}
            payload = {
                "dataset_snapshot_id": row.dataset_snapshot_id,
                "quality_report": metadata.get("quality_report", {}),
                "leakage_issues": metadata.get("leakage_issues", []),
                "warnings": metadata.get("warnings", []),
            }
        return _result(definition, payload)

    def temporal_report(arguments, context):
        definition = registry.get("dataset.temporal_integrity_report")
        with session_scope() as session:
            if session is None:
                return _blocked(
                    definition,
                    CapabilityFailureCode.DATA_MISSING,
                    "Runtime PostgreSQL is not configured",
                )
            from eurogas_nexus.db.repositories.research import get_dataset_snapshot

            row = get_dataset_snapshot(session, str(arguments["dataset_snapshot_id"]))
            if row is None:
                return _blocked(
                    definition,
                    CapabilityFailureCode.ENTITY_NOT_FOUND,
                    str(arguments["dataset_snapshot_id"]),
                )
            if principal_can_read_snapshot(_research_principal(context), row.metadata_json) is None:
                return _blocked(
                    definition,
                    CapabilityFailureCode.ENTITLEMENT_DENIED,
                    "Snapshot source provenance is not authorized for this identity",
                )
            metadata = row.metadata_json or {}
            issues = metadata.get("leakage_issues", [])
            payload = {
                "dataset_snapshot_id": row.dataset_snapshot_id,
                "temporal_integrity": row.temporal_integrity,
                "issues": issues,
                "blockers": [item for item in issues if item.get("severity") == "BLOCKER"],
            }
        return _result(definition, payload)

    _register(
        registry,
        capability_id="dataset.validate_spec",
        name="Validate dataset spec",
        domain=CapabilityDomain.DATASET,
        description="Validate a declarative DatasetSpec without building it.",
        input_schema=_schema({"spec": {"type": "object"}}, required=["spec"]),
        output_schema={"type": "object"},
        handler=validate_spec,
        mcp_name="validate_dataset_spec",
    )
    _register(
        registry,
        capability_id="dataset.build",
        name="Build dataset snapshot",
        domain=CapabilityDomain.DATASET,
        description="Build and persist one immutable point-in-time dataset snapshot.",
        input_schema=_schema({"spec": {"type": "object"}}, required=["spec"]),
        output_schema={"type": "object"},
        handler=build,
        side_effect_class=SideEffectClass.RESEARCH_OBJECT_WRITE,
        required_permissions=["capability.invoke", "analysis.query"],
        action_policy=ActionPolicy.AGENT_ALLOWED_WITHIN_RESEARCH,
        mcp_name="build_dataset",
        timeout_policy="120s",
    )
    _register(
        registry,
        capability_id="dataset.inspect_snapshot",
        name="Inspect dataset snapshot",
        domain=CapabilityDomain.DATASET,
        description="Inspect immutable snapshot metadata and content hash.",
        input_schema=_schema(
            {"dataset_snapshot_id": {"type": "string"}}, required=["dataset_snapshot_id"]
        ),
        output_schema={"type": "object"},
        handler=inspect_snapshot,
        mcp_name="inspect_dataset_snapshot",
    )
    _register(
        registry,
        capability_id="dataset.get_quality_report",
        name="Get dataset quality report",
        domain=CapabilityDomain.DATASET,
        description="Return structured dataset quality and leakage report.",
        input_schema=_schema(
            {"dataset_snapshot_id": {"type": "string"}}, required=["dataset_snapshot_id"]
        ),
        output_schema={"type": "object"},
        handler=quality_report,
        mcp_name="get_dataset_quality_report",
    )
    _register(
        registry,
        capability_id="dataset.temporal_integrity_report",
        name="Get temporal integrity report",
        domain=CapabilityDomain.DATASET,
        description="Return temporal leakage blockers and warnings.",
        input_schema=_schema(
            {"dataset_snapshot_id": {"type": "string"}}, required=["dataset_snapshot_id"]
        ),
        output_schema={"type": "object"},
        handler=temporal_report,
        mcp_name="get_dataset_temporal_integrity",
    )
    _register(
        registry,
        capability_id="dataset.export",
        name="Export dataset snapshot",
        domain=CapabilityDomain.DATASET,
        description=(
            "Return the governed reference of a stored format-specific dataset "
            "artifact; denied unless the canonical source policy allows export."
        ),
        input_schema=_schema(
            {
                "dataset_snapshot_id": {"type": "string"},
                "format": {"type": "string", "enum": ["parquet", "csv"]},
            },
            required=["dataset_snapshot_id"],
        ),
        output_schema={"type": "object"},
        handler=export_dataset,
        # Serving a stored artifact is not a new persist side effect; the
        # entitlement and registry checks inside the handler are the gate.
        side_effect_class=SideEffectClass.READ_ONLY,
        action_policy=ActionPolicy.AGENT_ALLOWED_WITHIN_RESEARCH,
        mcp_name="export_dataset_snapshot",
    )

