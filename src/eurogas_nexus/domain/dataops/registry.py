"""Canonical typed source registry for data operations.

The static display registry in ``eurogas_nexus.domain.ingestion.source_registry``
remains the compiled baseline for the 24 registered sources. This module turns
that baseline into typed operational descriptors (source class, schedule,
freshness, retry, circuit, rate-limit and licensed-data policy) used by the
scheduler, freshness engine and API. It must stay import-safe and DB-free.
"""

from __future__ import annotations

from dataclasses import replace

from eurogas_nexus.domain.dataops.contracts import (
    AccessMode,
    CircuitPolicy,
    FreshnessPolicy,
    LicensedDataPolicy,
    RateLimitPolicy,
    RetryPolicy,
    SourceCalendar,
    SourceClass,
    SourceDefinition,
    SourceScheduleSpec,
)
from eurogas_nexus.domain.ingestion.source_registry import registered_sources


def _operations_by_source() -> dict[str, dict]:
    """Operations policy per source, from each provider's connector manifest (C1)."""

    from eurogas_nexus.domain.connectors.registry import connector_manifests

    return {manifest.source_id: dict(manifest.operations) for manifest in connector_manifests()}


_SIMULATED_SOURCES = {
    "src-eex-sim": ("EEX", SourceClass.SIMULATED),
    "src-ice-ocm-sim": ("ICE_OCM", SourceClass.SIMULATED),
    "src-trayport-sim": ("Trayport", SourceClass.SIMULATED),
    "src-icis-sim": ("ICIS", SourceClass.SIMULATED),
}


def _source_class_for(source_id: str, provider: str) -> SourceClass:
    if source_id in _SIMULATED_SOURCES:
        return _SIMULATED_SOURCES[source_id][1]
    provider_upper = provider.upper()
    if provider_upper in {"EEX", "ICE_OCM"}:
        return SourceClass.EXCHANGE
    if provider_upper == "TRAYPORT":
        return SourceClass.BROKER
    if provider_upper in {"PLATTS", "ICIS", "ARGUS", "KPLER", "WEATHER"}:
        return SourceClass.LICENSED
    if provider_upper == "DEEPSEEK":
        return SourceClass.MODEL
    if source_id.endswith("-sim"):
        return SourceClass.SIMULATED
    return SourceClass.PUBLIC


def source_definitions() -> tuple[SourceDefinition, ...]:
    """Return typed operational descriptors for every registered source."""

    definitions: list[SourceDefinition] = []
    operations = _operations_by_source()
    for row in registered_sources():
        source_id = str(row["source_id"])
        provider = str(row["source_system"])
        datasets = tuple(str(dataset) for dataset in row["datasets"])
        override = operations.get(source_id, {})
        entitlement_scope = "licensed" if row["credential_requirements"] else "public"
        credential_fields: tuple[str, ...] = ()
        if row["credential_requirements"]:
            credential_fields = tuple(override.get("credential_fields") or ("api_key",))
        definition = SourceDefinition(
            source_id=source_id,
            provider=provider,
            dataset=datasets[0] if datasets else "",
            datasets=datasets,
            source_class=override.get("source_class", _source_class_for(source_id, provider)),
            access_mode=override.get("access_mode", AccessMode.NONE),
            entitlement_scope=entitlement_scope,
            credential_fields=credential_fields,
            certification_required=bool(
                override.get("certification_required")
                or bool(row["credential_requirements"])
                or entitlement_scope == "licensed"
            ),
            schedulable=bool(override.get("schedulable", False)),
            enabled_default=bool(override.get("enabled_default", False)),
            schedule=override.get("schedule", SourceScheduleSpec()),
            freshness_policy=override.get(
                "freshness_policy",
                FreshnessPolicy(int(row["freshness_expectation_minutes"]), 2880, 4320),
            ),
            retry_policy=override.get("retry_policy", RetryPolicy()),
            rate_limit_policy=override.get("rate_limit_policy", RateLimitPolicy()),
            circuit_policy=override.get("circuit_policy", CircuitPolicy()),
            calendar=override.get("calendar", SourceCalendar.ALWAYS_OPEN),
            adapter_version=str(override.get("adapter_version", "unversioned")),
            licensed_data=override.get("licensed_data", LicensedDataPolicy()),
            description=str(row["description"]),
        )
        definitions.append(definition)
    return tuple(definitions)


def definition_for_source(source_id: str | None) -> SourceDefinition | None:
    """Return the typed definition for one source id (case-insensitive)."""

    for definition in source_definitions():
        if definition.source_id.casefold() == (source_id or "").strip().casefold():
            return definition
    return None


def definition_for_provider(provider: str | None) -> SourceDefinition | None:
    """Return the first typed definition for a provider/system label."""

    needle = (provider or "").strip().casefold()
    for definition in source_definitions():
        if definition.provider.casefold() == needle:
            return definition
    return None


def schedulable_definitions() -> tuple[SourceDefinition, ...]:
    """Return the definitions the PostgreSQL scheduler may claim."""

    return tuple(definition for definition in source_definitions() if definition.schedulable)


def with_overrides(definition: SourceDefinition, **changes) -> SourceDefinition:
    """Return a copy of one definition with explicit policy overrides."""

    return replace(definition, **changes)
