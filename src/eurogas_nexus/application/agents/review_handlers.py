"""Review capability handlers (CR-15): agents prepare evidence, humans decide."""

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
    input_schema,
    handler,
    side_effect_class=SideEffectClass.READ_ONLY,
    required_permissions=None,
    action_policy=ActionPolicy.AUTO_ALLOWED,
    mcp_name=None,
):
    registry.register(
        CapabilityDefinition(
            capability_id=capability_id,
            name=name,
            domain=CapabilityDomain.REVIEW,
            description=description,
            input_schema=input_schema,
            output_schema={"type": "object"},
            determinism_class=DeterminismClass.DETERMINISTIC,
            side_effect_class=side_effect_class,
            required_permissions=required_permissions or ["capability.invoke"],
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


def register_review_capabilities(registry) -> None:
    from eurogas_nexus.application.agents.db_bridge import session_scope

    def get(arguments, _context):
        definition = registry.get("review.get")
        with session_scope() as session:
            if session is None:
                return _blocked(
                    definition,
                    CapabilityFailureCode.DATA_MISSING,
                    "Runtime PostgreSQL is not configured",
                )
            from eurogas_nexus.db.repositories.review import list_review_decisions

            rows = list_review_decisions(
                session,
                entity_type=arguments.get("entity_type"),
                entity_id=arguments.get("entity_id"),
                limit=int(arguments.get("limit") or 100),
            )
        return _result(definition, {"decisions": rows, "count": len(rows)})

    def prepare_pack(arguments, _context):
        definition = registry.get("review.prepare_pack")
        return _result(
            definition,
            {
                "review_pack_id": str(arguments.get("review_pack_id") or f"review-{_now_hex()}"),
                "objective": arguments.get("objective") or "",
                "findings": arguments.get("findings") or [],
                "strategy_specification": arguments.get("strategy_specification"),
                "backtest": arguments.get("backtest"),
                "challenge_report": arguments.get("challenge_report"),
                "warnings": arguments.get("warnings") or [],
                "known_limitations": arguments.get("known_limitations") or [],
            },
        )

    def record_decision(_arguments, _context):
        definition = registry.get("review.record_analytical_decision")
        return _blocked(
            definition,
            CapabilityFailureCode.PERMISSION_DENIED,
            "Human reviewers record analytical decisions; agents prepare evidence only",
        )

    _register(
        registry,
        capability_id="review.get",
        name="Get review decisions",
        description="List existing human review decisions.",
        input_schema=_schema(
            {
                "entity_type": {"type": "string"},
                "entity_id": {"type": "string"},
                "limit": {"type": "integer"},
            }
        ),
        handler=get,
        mcp_name="get_review_decisions",
    )
    _register(
        registry,
        capability_id="review.prepare_pack",
        name="Prepare review pack",
        description="Prepare structured evidence for a human reviewer; never impersonates review.",
        input_schema=_schema(
            {
                "review_pack_id": {"type": "string"},
                "objective": {"type": "string"},
                "findings": {"type": "array", "items": {"type": "object"}},
                "strategy_specification": {"type": "object"},
                "backtest": {"type": "object"},
                "challenge_report": {"type": "object"},
                "warnings": {"type": "array", "items": {"type": "string"}},
                "known_limitations": {"type": "array", "items": {"type": "string"}},
            },
            required=["objective"],
        ),
        handler=prepare_pack,
        action_policy=ActionPolicy.AGENT_ALLOWED_WITHIN_RESEARCH,
        mcp_name="prepare_review_pack",
    )
    _register(
        registry,
        capability_id="review.record_analytical_decision",
        name="Record analytical review decision",
        description="HUMAN_ONLY: agents may prepare evidence but never record a human decision.",
        input_schema=_schema(
            {
                "entity_type": {"type": "string"},
                "entity_id": {"type": "string"},
                "decision": {"type": "string"},
            }
        ),
        handler=record_decision,
        side_effect_class=SideEffectClass.RESEARCH_OBJECT_WRITE,
        required_permissions=["review.record"],
        action_policy=ActionPolicy.HUMAN_ONLY,
        mcp_name="record_review_decision",
    )


def _now_hex() -> str:
    return datetime.now(UTC).strftime("%Y%m%d%H%M%S%f")
