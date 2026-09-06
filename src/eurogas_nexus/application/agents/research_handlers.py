"""Dataset/strategy/backtest/shadow/review capability handlers (CR-15)."""

from __future__ import annotations

from datetime import UTC, datetime
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
from eurogas_nexus.domain.agents.strategy_ir import (
    StrategyIR,
    compile_strategy_ir,
    validate_strategy_ir,
)
from eurogas_nexus.domain.backtest.contracts import (
    BacktestDecisionSchedule,
    BacktestEconomicAssumptions,
    BacktestPeriod,
    BacktestRunDefinition,
)


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
    from eurogas_nexus.application.agents.shadow_handlers import (
        register_shadow_capabilities,
    )

    _register_dataset_capabilities(registry)
    _register_strategy_capabilities(registry)
    _register_backtest_capabilities(registry)
    register_shadow_capabilities(registry)
    register_review_capabilities(registry)


def _register_dataset_capabilities(registry) -> None:
    from eurogas_nexus.application.agents.db_bridge import session_scope
    from eurogas_nexus.domain.research.datasets import DatasetSpec

    def validate_spec(arguments, _context):
        definition = registry.get("dataset.validate_spec")
        try:
            spec = DatasetSpec.model_validate(arguments.get("spec") or {})
            issues = [] if spec.target_ids else ["at least one target_id is required"]
            return _result(
                definition,
                {
                    "ok": not issues,
                    "issues": issues,
                    "spec_hash": spec.content_hash(),
                    "qualified_version": spec.qualified_version(),
                },
            )
        except Exception as exc:
            return _result(definition, {"ok": False, "issues": [str(exc)]})

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
            result, dependencies, issues = _build_from_runtime(session, spec)
            persist_dataset_snapshot(
                session,
                metadata=result.as_metadata(),
                dependencies=dependencies,
                issues=issues,
                artifacts=[],
            )
            session.commit()
        return _result(
            definition,
            {
                **result.as_metadata(),
                "rows": result.rows[:50],
            },
        )

    def inspect_snapshot(arguments, _context):
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

    def quality_report(arguments, _context):
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
            metadata = row.metadata_json or {}
            payload = {
                "dataset_snapshot_id": row.dataset_snapshot_id,
                "quality_report": metadata.get("quality_report", {}),
                "leakage_issues": metadata.get("leakage_issues", []),
                "warnings": metadata.get("warnings", []),
            }
        return _result(definition, payload)

    def temporal_report(arguments, _context):
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
        required_permissions=["capability.invoke", "strategy.create"],
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


def _register_strategy_capabilities(registry) -> None:
    from eurogas_nexus.application.agents.db_bridge import session_scope
    from eurogas_nexus.db.repositories import strategy_registry

    def list_strategies(arguments, _context):
        definition = registry.get("strategy.list")
        with session_scope() as session:
            if session is None:
                return _blocked(
                    definition,
                    CapabilityFailureCode.DATA_MISSING,
                    "Runtime PostgreSQL is not configured",
                )
            rows = strategy_registry.list_strategies(
                session, limit=int(arguments.get("limit") or 100)
            )
            payload = [strategy_registry.strategy_record_payload(row) for row in rows]
        return _result(definition, {"strategies": payload, "count": len(payload)})

    def get_strategy(arguments, _context):
        definition = registry.get("strategy.get")
        with session_scope() as session:
            if session is None:
                return _blocked(
                    definition,
                    CapabilityFailureCode.DATA_MISSING,
                    "Runtime PostgreSQL is not configured",
                )
            row = strategy_registry.get_strategy(session, str(arguments["strategy_id"]))
            if row is None:
                return _blocked(
                    definition,
                    CapabilityFailureCode.ENTITY_NOT_FOUND,
                    str(arguments["strategy_id"]),
                )
            payload = strategy_registry.strategy_record_payload(row)
        return _result(definition, payload)

    def create_draft(arguments, context):
        definition = registry.get("strategy.create_draft")
        with session_scope() as session:
            if session is None:
                return _blocked(
                    definition,
                    CapabilityFailureCode.DATA_MISSING,
                    "Runtime PostgreSQL is not configured",
                )
            strategy_id = str(arguments.get("strategy_id") or f"strategy-{_now_hex()}")
            row = strategy_registry.create_strategy(
                session,
                strategy_id=strategy_id,
                name=str(arguments.get("name") or strategy_id),
                description=str(arguments.get("description") or ""),
                created_by=context.principal_id,
                now_utc=datetime.now(UTC),
                tags=list(arguments.get("tags") or []),
            )
            session.commit()
        return _result(definition, strategy_registry.strategy_record_payload(row))

    def create_version(arguments, context):
        definition = registry.get("strategy.create_version")
        try:
            ir = StrategyIR.model_validate(arguments.get("strategy_ir") or {})
            validation = validate_strategy_ir(ir)
        except Exception as exc:
            return _blocked(definition, CapabilityFailureCode.STRATEGY_INVALID, str(exc))
        if not validation.ok:
            return _blocked(
                definition,
                CapabilityFailureCode.STRATEGY_INVALID,
                "; ".join(item.detail for item in validation.issues),
            )
        compiled = compile_strategy_ir(ir)
        with session_scope() as session:
            if session is None:
                return _blocked(
                    definition,
                    CapabilityFailureCode.DATA_MISSING,
                    "Runtime PostgreSQL is not configured",
                )
            row = strategy_registry.create_strategy_version(
                session,
                strategy_id=str(arguments["strategy_id"]),
                definition=compiled,
                hypothesis=ir.hypothesis,
                created_by=context.principal_id,
                now_utc=datetime.now(UTC),
            )
            session.commit()
        return _result(definition, strategy_registry.strategy_version_payload(row))

    def validate_spec(arguments, _context):
        definition = registry.get("strategy.validate_spec")
        try:
            ir = StrategyIR.model_validate(arguments.get("strategy_ir") or {})
        except Exception as exc:
            return _result(definition, {"ok": False, "issues": [str(exc)]})
        validation = validate_strategy_ir(ir)
        compiled_hash = compile_strategy_ir(ir).content_hash() if validation.ok else None
        return _result(
            definition,
            {
                "ok": validation.ok,
                "issues": [item.model_dump(mode="json") for item in validation.issues],
                "compiled_content_hash": compiled_hash,
            },
        )

    def freeze_version(arguments, context):
        definition = registry.get("strategy.freeze_version")
        with session_scope() as session:
            if session is None:
                return _blocked(
                    definition,
                    CapabilityFailureCode.DATA_MISSING,
                    "Runtime PostgreSQL is not configured",
                )
            row = strategy_registry.get_strategy_version(
                session, str(arguments["strategy_version_id"])
            )
            if row is None:
                return _blocked(
                    definition,
                    CapabilityFailureCode.ENTITY_NOT_FOUND,
                    str(arguments["strategy_version_id"]),
                )
            row = strategy_registry.freeze_strategy_version(
                session,
                strategy_version_id=row.strategy_version_id,
                frozen_by=context.principal_id,
                now_utc=datetime.now(UTC),
            )
            session.commit()
        return _result(definition, strategy_registry.strategy_version_payload(row))

    def get_data_requirements(arguments, _context):
        definition = registry.get("strategy.get_data_requirements")
        with session_scope() as session:
            if session is None:
                return _blocked(
                    definition,
                    CapabilityFailureCode.DATA_MISSING,
                    "Runtime PostgreSQL is not configured",
                )
            row = strategy_registry.get_strategy_version(
                session, str(arguments["strategy_version_id"])
            )
            if row is None:
                return _blocked(
                    definition,
                    CapabilityFailureCode.ENTITY_NOT_FOUND,
                    str(arguments["strategy_version_id"]),
                )
            payload = {
                "strategy_version_id": row.strategy_version_id,
                "data_requirements": (row.definition_json or {}).get("data_requirements", {}),
            }
        return _result(definition, payload)

    def compare_versions(arguments, _context):
        definition = registry.get("strategy.compare_versions")
        with session_scope() as session:
            if session is None:
                return _blocked(
                    definition,
                    CapabilityFailureCode.DATA_MISSING,
                    "Runtime PostgreSQL is not configured",
                )
            rows = strategy_registry.list_strategy_versions(
                session, str(arguments["strategy_id"]), limit=50
            )
            payload = [
                {
                    "strategy_version_id": row.strategy_version_id,
                    "version_number": row.version_number,
                    "status": row.status,
                    "content_hash": row.content_hash,
                    "hypothesis": row.hypothesis,
                }
                for row in rows
            ]
        return _result(definition, {"versions": payload, "count": len(payload)})

    _register(
        registry,
        capability_id="strategy.list",
        name="List strategies",
        domain=CapabilityDomain.STRATEGY,
        description="List strategy research identities.",
        input_schema=_schema({"limit": {"type": "integer"}}),
        output_schema={"type": "object"},
        handler=list_strategies,
        mcp_name="list_strategies",
    )
    _register(
        registry,
        capability_id="strategy.get",
        name="Get strategy",
        domain=CapabilityDomain.STRATEGY,
        description="Return one strategy research identity.",
        input_schema=_schema({"strategy_id": {"type": "string"}}, required=["strategy_id"]),
        output_schema={"type": "object"},
        handler=get_strategy,
        mcp_name="get_strategy",
    )
    _register(
        registry,
        capability_id="strategy.create_draft",
        name="Create strategy draft",
        domain=CapabilityDomain.STRATEGY,
        description="Create a draft strategy research identity.",
        input_schema=_schema(
            {
                "strategy_id": {"type": "string"},
                "name": {"type": "string"},
                "description": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
            }
        ),
        output_schema={"type": "object"},
        handler=create_draft,
        side_effect_class=SideEffectClass.RESEARCH_OBJECT_WRITE,
        required_permissions=["capability.invoke", "strategy.create"],
        action_policy=ActionPolicy.AGENT_ALLOWED_WITHIN_RESEARCH,
        mcp_name="create_strategy_draft",
    )
    _register(
        registry,
        capability_id="strategy.create_version",
        name="Create strategy version",
        domain=CapabilityDomain.STRATEGY,
        description="Compile a validated StrategyIR into a CR-03 draft StrategyVersion.",
        input_schema=_schema(
            {
                "strategy_id": {"type": "string"},
                "strategy_ir": {"type": "object"},
            },
            required=["strategy_id", "strategy_ir"],
        ),
        output_schema={"type": "object"},
        handler=create_version,
        side_effect_class=SideEffectClass.RESEARCH_OBJECT_WRITE,
        required_permissions=["capability.invoke", "strategy.create"],
        action_policy=ActionPolicy.AGENT_ALLOWED_WITHIN_RESEARCH,
        mcp_name="create_strategy_version",
    )
    _register(
        registry,
        capability_id="strategy.validate_spec",
        name="Validate StrategyIR",
        domain=CapabilityDomain.STRATEGY,
        description="Semantically validate StrategyIR without persisting.",
        input_schema=_schema({"strategy_ir": {"type": "object"}}, required=["strategy_ir"]),
        output_schema={"type": "object"},
        handler=validate_spec,
        mcp_name="validate_strategy_ir",
    )
    _register(
        registry,
        capability_id="strategy.freeze_version",
        name="Freeze strategy version",
        domain=CapabilityDomain.STRATEGY,
        description="Freeze a draft StrategyVersion into an immutable version.",
        input_schema=_schema(
            {"strategy_version_id": {"type": "string"}},
            required=["strategy_version_id"],
        ),
        output_schema={"type": "object"},
        handler=freeze_version,
        side_effect_class=SideEffectClass.RESEARCH_OBJECT_WRITE,
        required_permissions=["capability.invoke", "strategy.freeze"],
        action_policy=ActionPolicy.HUMAN_CONFIRMATION,
        mcp_name="freeze_strategy_version",
    )
    _register(
        registry,
        capability_id="strategy.get_data_requirements",
        name="Get strategy data requirements",
        domain=CapabilityDomain.STRATEGY,
        description="Return a strategy version data requirements.",
        input_schema=_schema(
            {"strategy_version_id": {"type": "string"}},
            required=["strategy_version_id"],
        ),
        output_schema={"type": "object"},
        handler=get_data_requirements,
        mcp_name="get_strategy_data_requirements",
    )
    _register(
        registry,
        capability_id="strategy.compare_versions",
        name="Compare strategy versions",
        domain=CapabilityDomain.STRATEGY,
        description="Compare immutable strategy versions by hash/status/hypothesis.",
        input_schema=_schema({"strategy_id": {"type": "string"}}, required=["strategy_id"]),
        output_schema={"type": "object"},
        handler=compare_versions,
        mcp_name="compare_strategy_versions",
    )


def _register_backtest_capabilities(registry) -> None:
    from eurogas_nexus.application.agents.db_bridge import session_scope
    from eurogas_nexus.db.repositories import backtest, strategy_registry

    def _period(arguments):
        return BacktestPeriod(
            start_utc=datetime.fromisoformat(
                str(arguments["period_start_utc"]).replace("Z", "+00:00")
            ),
            end_utc=datetime.fromisoformat(str(arguments["period_end_utc"]).replace("Z", "+00:00")),
        )

    def validate(arguments, _context):
        definition = registry.get("backtest.validate")
        try:
            BacktestRunDefinition(
                strategy_version_id=str(arguments.get("strategy_version_id") or "validate-only"),
                period=_period(arguments),
                schedule=BacktestDecisionSchedule(),
                economic_assumptions=BacktestEconomicAssumptions(),
            )
            return _result(definition, {"ok": True, "issues": []})
        except Exception as exc:
            return _result(definition, {"ok": False, "issues": [str(exc)]})

    def run(arguments, context):
        definition = registry.get("backtest.run")
        try:
            run_definition = BacktestRunDefinition(
                strategy_version_id=str(arguments["strategy_version_id"]),
                period=_period(arguments),
                schedule=BacktestDecisionSchedule(),
                economic_assumptions=BacktestEconomicAssumptions(),
                deterministic_seed=str(arguments.get("deterministic_seed") or ""),
            )
        except Exception as exc:
            return _blocked(definition, CapabilityFailureCode.BACKTEST_BLOCKED, str(exc))
        with session_scope() as session:
            if session is None:
                return _blocked(
                    definition,
                    CapabilityFailureCode.DATA_MISSING,
                    "Runtime PostgreSQL is not configured",
                )
            version = strategy_registry.get_strategy_version(
                session, str(arguments["strategy_version_id"])
            )
            if version is None:
                return _blocked(
                    definition,
                    CapabilityFailureCode.ENTITY_NOT_FOUND,
                    str(arguments["strategy_version_id"]),
                )
            if version.status != "FROZEN":
                return _blocked(
                    definition,
                    CapabilityFailureCode.BACKTEST_BLOCKED,
                    f"strategy version is {version.status}, not FROZEN",
                )
            from eurogas_nexus.application.backtest_service import execute_backtest_run
            from eurogas_nexus.db.repositories.strategy import strategy_run_payload

            row = execute_backtest_run(
                session,
                version=version,
                definition=run_definition,
                requested_by=context.principal_id,
            )
            session.commit()
        return _result(definition, strategy_run_payload(row))

    def get_result(arguments, _context):
        definition = registry.get("backtest.get_result")
        with session_scope() as session:
            if session is None:
                return _blocked(
                    definition,
                    CapabilityFailureCode.DATA_MISSING,
                    "Runtime PostgreSQL is not configured",
                )
            from eurogas_nexus.db.repositories.strategy import get_strategy_run

            payload = get_strategy_run(session, str(arguments["run_id"]))
            if payload is None:
                return _blocked(
                    definition, CapabilityFailureCode.ENTITY_NOT_FOUND, str(arguments["run_id"])
                )
        return _result(definition, payload)

    def get_event_log(arguments, _context):
        definition = registry.get("backtest.get_event_log")
        with session_scope() as session:
            if session is None:
                return _blocked(
                    definition,
                    CapabilityFailureCode.DATA_MISSING,
                    "Runtime PostgreSQL is not configured",
                )
            rows = backtest.list_backtest_events(session, str(arguments["run_id"]))
        return _result(definition, {"events": rows, "count": len(rows)})

    def get_attribution(arguments, _context):
        definition = registry.get("backtest.get_attribution")
        with session_scope() as session:
            if session is None:
                return _blocked(
                    definition,
                    CapabilityFailureCode.DATA_MISSING,
                    "Runtime PostgreSQL is not configured",
                )
            rows = backtest.list_backtest_attribution(session, str(arguments["run_id"]))
        return _result(definition, {"attribution": rows, "count": len(rows)})

    def robustness_summary(arguments, _context):
        definition = registry.get("backtest.get_robustness_summary")
        with session_scope() as session:
            if session is None:
                return _blocked(
                    definition,
                    CapabilityFailureCode.DATA_MISSING,
                    "Runtime PostgreSQL is not configured",
                )
            from eurogas_nexus.db.repositories.strategy import get_strategy_run

            payload = get_strategy_run(session, str(arguments["run_id"]))
            if payload is None:
                return _blocked(
                    definition, CapabilityFailureCode.ENTITY_NOT_FOUND, str(arguments["run_id"])
                )
            events = backtest.list_backtest_events(session, str(arguments["run_id"]))
        metrics = (payload.get("result_snapshot") or {}).get("metrics", {})
        return _result(
            definition,
            {
                "run_id": arguments["run_id"],
                "event_count": len(events),
                "metrics": metrics,
                "robustness": {
                    "baseline_comparison": "NOT_SUPPORTED_CR04",
                    "out_of_sample": "DEFERRED",
                    "parameter_sensitivity": "DEFERRED",
                    "cost_sensitivity": "EXPLICIT_ZERO_UNMODELED",
                    "period_sensitivity": "DEFERRED",
                    "regime_segmentation": "DEFERRED",
                    "data_quality_sensitivity": "DEFERRED",
                },
            },
        )

    _register(
        registry,
        capability_id="backtest.validate",
        name="Validate backtest request",
        domain=CapabilityDomain.BACKTEST,
        description="Validate period and economic assumptions before a backtest.",
        input_schema=_schema(
            {
                "strategy_version_id": {"type": "string"},
                "period_start_utc": {"type": "string"},
                "period_end_utc": {"type": "string"},
            },
            required=["period_start_utc", "period_end_utc"],
        ),
        output_schema={"type": "object"},
        handler=validate,
        mcp_name="validate_backtest",
    )
    _register(
        registry,
        capability_id="backtest.run",
        name="Run backtest",
        domain=CapabilityDomain.BACKTEST,
        description="Run one deterministic backtest for a FROZEN strategy version.",
        input_schema=_schema(
            {
                "strategy_version_id": {"type": "string"},
                "period_start_utc": {"type": "string"},
                "period_end_utc": {"type": "string"},
                "deterministic_seed": {"type": "string"},
            },
            required=["strategy_version_id", "period_start_utc", "period_end_utc"],
        ),
        output_schema={"type": "object"},
        handler=run,
        side_effect_class=SideEffectClass.RESEARCH_OBJECT_WRITE,
        required_permissions=["capability.invoke", "strategy.create"],
        action_policy=ActionPolicy.AGENT_ALLOWED_WITHIN_RESEARCH,
        mcp_name="run_strategy_backtest",
        timeout_policy="120s",
    )
    _register(
        registry,
        capability_id="backtest.get_result",
        name="Get backtest result",
        domain=CapabilityDomain.BACKTEST,
        description="Return one immutable backtest run payload.",
        input_schema=_schema({"run_id": {"type": "string"}}, required=["run_id"]),
        output_schema={"type": "object"},
        handler=get_result,
        mcp_name="get_backtest_result",
    )
    _register(
        registry,
        capability_id="backtest.get_event_log",
        name="Get backtest event log",
        domain=CapabilityDomain.BACKTEST,
        description="Return decision event log for one backtest run.",
        input_schema=_schema({"run_id": {"type": "string"}}, required=["run_id"]),
        output_schema={"type": "object"},
        handler=get_event_log,
        mcp_name="get_backtest_event_log",
    )
    _register(
        registry,
        capability_id="backtest.get_attribution",
        name="Get backtest attribution",
        domain=CapabilityDomain.BACKTEST,
        description="Return deterministic PnL attribution rows.",
        input_schema=_schema({"run_id": {"type": "string"}}, required=["run_id"]),
        output_schema={"type": "object"},
        handler=get_attribution,
        mcp_name="get_backtest_attribution",
    )
    _register(
        registry,
        capability_id="backtest.get_robustness_summary",
        name="Get robustness summary",
        domain=CapabilityDomain.BACKTEST,
        description=(
            "Return supported robustness checks; unsupported checks are "
            "DEFERRED, never faked."
        ),
        input_schema=_schema({"run_id": {"type": "string"}}, required=["run_id"]),
        output_schema={"type": "object"},
        handler=robustness_summary,
        mcp_name="get_backtest_robustness",
    )


def _now_hex() -> str:
    return datetime.now(UTC).strftime("%Y%m%d%H%M%S%f")
