"""First-class Capability Registry (CR-15).

The registry is the single semantic source for agent/API/SDK/MCP tool
metadata. It does not replace HTTP route registration and is not a generic
RPC bypass: every invocation still passes permission and entitlement checks.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from eurogas_nexus.domain.agents.contracts import (
    AgentInvocationContext,
    CapabilityDefinition,
    CapabilityResult,
    CapabilityStatus,
)

CapabilityHandler = Callable[[dict, AgentInvocationContext], CapabilityResult]


@dataclass(frozen=True)
class CapabilityRegistration:
    definition: CapabilityDefinition
    handler: CapabilityHandler


class CapabilityRegistry:
    def __init__(self) -> None:
        self._registrations: dict[str, CapabilityRegistration] = {}

    def register(self, definition: CapabilityDefinition, handler: CapabilityHandler) -> None:
        if definition.capability_id in self._registrations:
            raise ValueError(f"Capability already registered: {definition.capability_id}")
        self._registrations[definition.capability_id] = CapabilityRegistration(
            definition=definition, handler=handler
        )

    def get(self, capability_id: str) -> CapabilityDefinition | None:
        registration = self._registrations.get(capability_id)
        return registration.definition if registration else None

    def handler(self, capability_id: str) -> CapabilityHandler | None:
        registration = self._registrations.get(capability_id)
        return registration.handler if registration else None

    def list_definitions(self, *, include_disabled: bool = False) -> list[CapabilityDefinition]:
        definitions = [
            registration.definition for registration in self._registrations.values()
        ]
        if not include_disabled:
            definitions = [
                definition
                for definition in definitions
                if definition.status == CapabilityStatus.ACTIVE
            ]
        return sorted(definitions, key=lambda item: (item.domain.value, item.capability_id))

    def search(self, query: str) -> list[CapabilityDefinition]:
        needle = (query or "").strip().casefold()
        if not needle:
            return self.list_definitions()
        results: list[CapabilityDefinition] = []
        for definition in self.list_definitions():
            haystack = " ".join(
                [
                    definition.capability_id,
                    definition.name,
                    definition.description,
                    definition.domain.value,
                    *definition.tags,
                ]
            ).casefold()
            if needle in haystack:
                results.append(definition)
        return results

    def disable(self, capability_id: str) -> CapabilityDefinition:
        registration = self._registrations.get(capability_id)
        if registration is None:
            raise KeyError(capability_id)
        replacement = registration.definition.model_copy(
            update={"status": CapabilityStatus.DISABLED}
        )
        self._registrations[capability_id] = CapabilityRegistration(
            definition=replacement, handler=registration.handler
        )
        return replacement

    def count(self) -> int:
        return len(self._registrations)

    def by_domain(self) -> dict[str, list[CapabilityDefinition]]:
        result: dict[str, list[CapabilityDefinition]] = {}
        for definition in self.list_definitions():
            result.setdefault(definition.domain.value, []).append(definition)
        return result


DEFAULT_CAPABILITY_REGISTRY = CapabilityRegistry()


def register_builtin_capabilities() -> CapabilityRegistry:
    """Idempotently register the CR-15 high-value capability inventory."""

    if DEFAULT_CAPABILITY_REGISTRY.count() == 0:
        from eurogas_nexus.application.agents.capability_handlers import (
            register_core_capabilities,
        )
        from eurogas_nexus.application.agents.research_handlers import (
            register_research_capabilities,
        )

        register_core_capabilities(DEFAULT_CAPABILITY_REGISTRY)
        register_research_capabilities(DEFAULT_CAPABILITY_REGISTRY)
    return DEFAULT_CAPABILITY_REGISTRY
