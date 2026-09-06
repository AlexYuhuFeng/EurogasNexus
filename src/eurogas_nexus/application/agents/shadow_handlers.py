"""Shadow capability handlers (CR-15): reads auto-allowed, writes human-confirmed."""

from __future__ import annotations

from datetime import UTC, datetime

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


def _result(definition, data):
    return CapabilityResult.success(
        capability=definition.capability_id,
        capability_version=definition.capability_version,
        data=data,
    )


def _blocked(definition, code, detail):
    return CapabilityResult.blocked(
        capability=definition.capability_id,
        capability_version=definition.capability_version,
        code=code,
        detail=detail,
    )


def _schema(properties, *, required=None):
    return {
        "type": "object",
        "properties": properties,
        "required": required or [],
        "additionalProperties": False,
    }


def _register(
    registry,
    *,
    capability_id,
    name,
    description,
    handler,
    side_effect_class,
    required_permissions,
    action_policy,
    mcp_name,
):
    registry.register(
        CapabilityDefinition(
            capability_id=capability_id,
            name=name,
            domain=CapabilityDomain.SHADOW,
            description=description,
            input_schema=_schema({"monitor_id": {"type": "string"}}, required=["monitor_id"]),
            output_schema={"type": "object"},
            determinism_class=DeterminismClass.OPERATIONAL_STATE_DEPENDENT,
            side_effect_class=side_effect_class,
            required_permissions=required_permissions,
            capability_version="v1",
            status=CapabilityStatus.ACTIVE,
            owner="research",
            action_policy=action_policy,
            mcp_name=mcp_name,
            timeout_policy="30s",
            idempotency=IdempotencyClass.NOT_IDEMPOTENT,
        ),
        handler,
    )


def register_shadow_capabilities(registry) -> None:
    from eurogas_nexus.application.agents.db_bridge import session_scope
    from eurogas_nexus.db.repositories import shadow

    def get_status(arguments, _context):
        definition = registry.get("shadow.get_status")
        with session_scope() as session:
            if session is None:
                return _blocked(
                    definition,
                    CapabilityFailureCode.DATA_MISSING,
                    "Runtime PostgreSQL is not configured",
                )
            rows = shadow.list_monitors(session, state=arguments.get("state"))
        return _result(definition, {"monitors": rows, "count": len(rows)})

    def get_evaluations(arguments, _context):
        definition = registry.get("shadow.get_evaluations")
        with session_scope() as session:
            if session is None:
                return _blocked(
                    definition,
                    CapabilityFailureCode.DATA_MISSING,
                    "Runtime PostgreSQL is not configured",
                )
            rows = shadow.list_evaluations(session, str(arguments["monitor_id"]))
        return _result(definition, {"evaluations": rows, "count": len(rows)})

    def get_drift(arguments, _context):
        definition = registry.get("shadow.get_drift")
        with session_scope() as session:
            if session is None:
                return _blocked(
                    definition,
                    CapabilityFailureCode.DATA_MISSING,
                    "Runtime PostgreSQL is not configured",
                )
            rows = shadow.list_drift_snapshots(session, str(arguments["monitor_id"]))
        return _result(definition, {"drift_snapshots": rows, "count": len(rows)})

    def get_alerts(arguments, _context):
        definition = registry.get("shadow.get_alerts")
        with session_scope() as session:
            if session is None:
                return _blocked(
                    definition,
                    CapabilityFailureCode.DATA_MISSING,
                    "Runtime PostgreSQL is not configured",
                )
            rows = shadow.list_alerts(session, str(arguments["monitor_id"]))
        return _result(definition, {"alerts": rows, "count": len(rows)})

    def start(arguments, _context):
        definition = registry.get("shadow.start")
        with session_scope() as session:
            if session is None:
                return _blocked(
                    definition,
                    CapabilityFailureCode.DATA_MISSING,
                    "Runtime PostgreSQL is not configured",
                )
            row = shadow.activate_monitor(
                session, monitor_id=str(arguments["monitor_id"]), now_utc=datetime.now(UTC)
            )
            session.commit()
        return _result(definition, shadow.monitor_payload(row))

    def pause(arguments, _context):
        definition = registry.get("shadow.pause")
        with session_scope() as session:
            if session is None:
                return _blocked(
                    definition,
                    CapabilityFailureCode.DATA_MISSING,
                    "Runtime PostgreSQL is not configured",
                )
            row = shadow.pause_monitor(
                session, monitor_id=str(arguments["monitor_id"]), now_utc=datetime.now(UTC)
            )
            session.commit()
        return _result(definition, shadow.monitor_payload(row))

    def resume(arguments, _context):
        definition = registry.get("shadow.resume")
        with session_scope() as session:
            if session is None:
                return _blocked(
                    definition,
                    CapabilityFailureCode.DATA_MISSING,
                    "Runtime PostgreSQL is not configured",
                )
            row = shadow.resume_monitor(
                session, monitor_id=str(arguments["monitor_id"]), now_utc=datetime.now(UTC)
            )
            session.commit()
        return _result(definition, shadow.monitor_payload(row))

    for capability_id, name, description, handler, mcp_name in (
        (
            "shadow.get_status",
            "Get shadow status",
            "List shadow monitor status.",
            get_status,
            "get_shadow_status",
        ),
        (
            "shadow.get_evaluations",
            "Get shadow evaluations",
            "Return persisted shadow evaluations.",
            get_evaluations,
            "get_shadow_evaluations",
        ),
        (
            "shadow.get_drift",
            "Get shadow drift",
            "Return shadow drift snapshots.",
            get_drift,
            "get_shadow_drift",
        ),
        (
            "shadow.get_alerts",
            "Get shadow alerts",
            "Return persisted shadow alerts.",
            get_alerts,
            "get_shadow_alerts",
        ),
    ):
        _register(
            registry,
            capability_id=capability_id,
            name=name,
            description=description,
            handler=handler,
            side_effect_class=SideEffectClass.READ_ONLY,
            required_permissions=["capability.invoke"],
            action_policy=ActionPolicy.AUTO_ALLOWED,
            mcp_name=mcp_name,
        )
    for capability_id, name, handler, mcp_name in (
        ("shadow.start", "Start shadow monitor", start, "start_shadow_monitor"),
        ("shadow.pause", "Pause shadow monitor", pause, "pause_shadow_monitor"),
        ("shadow.resume", "Resume shadow monitor", resume, "resume_shadow_monitor"),
    ):
        _register(
            registry,
            capability_id=capability_id,
            name=name,
            description="Operational research write; requires explicit human confirmation.",
            handler=handler,
            side_effect_class=SideEffectClass.OPERATIONAL_WRITE,
            required_permissions=["capability.invoke", "strategy.shadow.manage"],
            action_policy=ActionPolicy.HUMAN_CONFIRMATION,
            mcp_name=mcp_name,
        )
