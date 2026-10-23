"""Object ACL checks for direct agent/MCP research capability handlers."""

from fastapi import HTTPException

from eurogas_nexus.domain.agents.contracts import CapabilityFailureCode, CapabilityResult


def guard_strategy_capability(session, arguments, context, definition, *, write=False):
    """Check every referenced object; one permitted id cannot mask another id."""
    from eurogas_nexus.db.repositories import shadow, strategy_registry
    from eurogas_nexus.db.repositories.review import can_read_review_target
    from eurogas_nexus.db.repositories.strategy import get_strategy_run
    from eurogas_nexus.db.repositories.strategy_access import (
        require_named_principal,
        require_strategy_access,
    )

    try:
        principal_id = require_named_principal(session, getattr(context, "principal_id", None))
        strategy_ids = set()
        strategy_id = arguments.get("strategy_id")
        if strategy_id:
            creating = definition.capability_id == "strategy.create_draft"
            if (
                not creating
                or strategy_registry.get_strategy(session, str(strategy_id)) is not None
            ):
                strategy_ids.add(str(strategy_id))
        if arguments.get("strategy_version_id"):
            version = strategy_registry.get_strategy_version(
                session, str(arguments["strategy_version_id"])
            )
            if version is None:
                raise HTTPException(404)
            strategy_ids.add(version.strategy_id)
        if arguments.get("run_id"):
            run = get_strategy_run(session, str(arguments["run_id"]))
            if run is None or not run.get("strategy_id"):
                raise HTTPException(404)
            strategy_ids.add(run["strategy_id"])
        if arguments.get("monitor_id"):
            monitor = shadow.get_monitor(session, str(arguments["monitor_id"]))
            if monitor is None:
                raise HTTPException(404)
            strategy_ids.add(monitor.strategy_id)
        for strategy_id in strategy_ids:
            require_strategy_access(session, strategy_id, principal_id, write=write)
        if arguments.get("entity_type") and arguments.get("entity_id"):
            if not can_read_review_target(
                session, arguments["entity_type"], arguments["entity_id"], principal_id
            ):
                raise HTTPException(404)
    except HTTPException:
        return CapabilityResult.blocked(
            capability=definition.capability_id,
            capability_version=definition.capability_version,
            code=CapabilityFailureCode.ENTITY_NOT_FOUND,
            detail="Strategy not found or not accessible",
        )
    return None
