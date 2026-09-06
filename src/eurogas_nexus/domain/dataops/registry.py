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
    ScheduleType,
    SourceCalendar,
    SourceClass,
    SourceDefinition,
    SourceScheduleSpec,
)
from eurogas_nexus.domain.ingestion.source_registry import registered_sources

# source_id -> semantics not present in the static display registry.

def _tariff_override() -> dict:
    return {
        "source_class": SourceClass.REFERENCE,
        "access_mode": AccessMode.PUBLIC_HTTP,
        "freshness_policy": FreshnessPolicy(43200, 64800, 129600),
        "retry_policy": RetryPolicy(2, 60.0, 1800.0),
    }


def _exchange_override(provider: str) -> dict:
    return {
        "source_class": SourceClass.EXCHANGE,
        "access_mode": AccessMode.KEYED_HTTP,
        "credential_fields": ("api_key",),
        "certification_required": True,
        "freshness_policy": FreshnessPolicy(1, 5, 30),
        "licensed_data": LicensedDataPolicy(),
    }


def _licensed_override(normal: int, late: int, stale: int) -> dict:
    return {
        "source_class": SourceClass.LICENSED,
        "access_mode": AccessMode.KEYED_HTTP,
        "credential_fields": ("api_key",),
        "certification_required": True,
        "freshness_policy": FreshnessPolicy(normal, late, stale),
        "licensed_data": LicensedDataPolicy(),
    }



_SOURCE_OVERRIDES: dict[str, dict] = {
    "src-ecb": {
        "source_class": SourceClass.PUBLIC,
        "access_mode": AccessMode.PUBLIC_HTTP,
        "schedulable": True,
        "enabled_default": True,
        "schedule": SourceScheduleSpec(
            schedule_type=ScheduleType.DAILY,
            daily_at="16:10",
            timezone="Europe/Berlin",
        ),
        "calendar": SourceCalendar.WEEKDAYS_ONLY,
        "freshness_policy": FreshnessPolicy(1440, 2880, 4320),
        "retry_policy": RetryPolicy(3, 300.0, 1800.0),
        "rate_limit_policy": RateLimitPolicy(4, 3600.0, 60.0, 1),
        "adapter_version": "public-source-ingestor/1",
    },
    "src-entsog": {
        "source_class": SourceClass.PUBLIC,
        "access_mode": AccessMode.PUBLIC_HTTP,
        "schedulable": True,
        "enabled_default": True,
        "schedule": SourceScheduleSpec(
            schedule_type=ScheduleType.INTERVAL,
            interval_seconds=3600,
        ),
        "calendar": SourceCalendar.GAS_MARKET,
        "freshness_policy": FreshnessPolicy(60, 120, 360),
        "retry_policy": RetryPolicy(3, 30.0, 600.0),
        "rate_limit_policy": RateLimitPolicy(6, 60.0, 5.0, 1),
        "adapter_version": "public-source-ingestor/1",
    },
    "src-gie": {
        "source_class": SourceClass.PUBLIC,
        "access_mode": AccessMode.KEYED_HTTP,
        "credential_fields": ("api_key",),
        "certification_required": True,
        "schedulable": True,
        "enabled_default": False,
        "schedule": SourceScheduleSpec(
            schedule_type=ScheduleType.DAILY,
            daily_at="09:00",
            timezone="Europe/Brussels",
        ),
        "calendar": SourceCalendar.GAS_MARKET,
        "freshness_policy": FreshnessPolicy(360, 720, 1440),
        "retry_policy": RetryPolicy(3, 60.0, 1800.0),
        "rate_limit_policy": RateLimitPolicy(12, 3600.0, 10.0, 1),
        "adapter_version": "public-source-ingestor/1",
        "licensed_data": LicensedDataPolicy(
            raw_retention_allowed=True,
            retention_note="bounded archive; never served through public API",
        ),
    },
    "src-national-gas-nts": _tariff_override(),
    "src-bbl": _tariff_override(),
    "src-iuk": _tariff_override(),
    "src-gts": _tariff_override(),
    "src-natran": _tariff_override(),
    "src-german-tso": _tariff_override(),
    "src-fluxys-belgium": _tariff_override(),
    "src-cnmc-enagas": _tariff_override(),
    "src-eex": _exchange_override("EEX"),
    "src-ice-ocm": _exchange_override("ICE_OCM"),
    "src-trayport": {
        "source_class": SourceClass.BROKER,
        "access_mode": AccessMode.SOCKET_FEED,
        "certification_required": True,
        "freshness_policy": FreshnessPolicy(1, 5, 30),
        "licensed_data": LicensedDataPolicy(),
    },
    "src-platts": _licensed_override(1440, 2880, 4320),
    "src-icis": _licensed_override(1440, 2880, 4320),
    "src-argus": _licensed_override(1440, 2880, 4320),
    "src-kpler": _licensed_override(60, 180, 720),
    "src-weather": {
        "source_class": SourceClass.LICENSED,
        "access_mode": AccessMode.KEYED_HTTP,
        "credential_fields": ("api_key",),
        "certification_required": True,
        "freshness_policy": FreshnessPolicy(180, 360, 720),
        "licensed_data": LicensedDataPolicy(),
    },
    "src-deepseek": {
        "source_class": SourceClass.MODEL,
        "access_mode": AccessMode.KEYED_HTTP,
        "credential_fields": ("api_key",),
        "certification_required": True,
        "freshness_policy": FreshnessPolicy(0, 0, 0),
        "licensed_data": LicensedDataPolicy(),
    },
}

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
    for row in registered_sources():
        source_id = str(row["source_id"])
        provider = str(row["source_system"])
        datasets = tuple(str(dataset) for dataset in row["datasets"])
        override = _SOURCE_OVERRIDES.get(source_id, {})
        entitlement_scope = "licensed" if row["credential_requirements"] else "public"
        credential_fields: tuple[str, ...] = ()
        if row["credential_requirements"]:
            credential_fields = tuple(
                override.get("credential_fields")
                or ("api_key",)
            )
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
