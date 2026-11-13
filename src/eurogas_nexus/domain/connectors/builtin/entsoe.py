"""ENTSOE connector manifest (src-entsoe)."""

from __future__ import annotations

from eurogas_nexus.domain.connectors.manifest import ConnectorManifest, ProviderCredentialSpec
from eurogas_nexus.domain.dataops.contracts import (
    AccessMode,
    FreshnessPolicy,
    RateLimitPolicy,
    RetryPolicy,
    ScheduleType,
    SourceClass,
    SourceScheduleSpec,
)

MANIFEST = ConnectorManifest(
    source_id="src-entsoe",
    system="ENTSOE",
    attribution="Source: ENTSO-E Transparency Platform",
    category="power",
    datasets=("day-ahead-prices", "actual-load", "generation-per-type"),
    description="ENTSO-E Transparency Platform day-ahead power prices, load, and wind, solar "
    "and gas-fired generation: the drivers of gas burned for power. Free; "
    "requires a registered security token; attribution: ENTSO-E.",
    entitled=True,
    freshness_minutes=120,
    # Run by the scheduler through scripts/ops/ingest_power.py (token from
    # ENTSOE_SECURITY_TOKEN); off until an operator enables it with the token in place.
    operations={
        "source_class": SourceClass.PUBLIC,
        "access_mode": AccessMode.KEYED_HTTP,
        "credential_fields": ("security_token",),
        "certification_required": True,
        "schedulable": True,
        "enabled_default": False,
        "schedule": SourceScheduleSpec(
            schedule_type=ScheduleType.INTERVAL,
            interval_seconds=3600,
        ),
        # Day-ahead prices publish once a day; load and generation hourly.
        "freshness_policy": FreshnessPolicy(120, 360, 1440),
        "retry_policy": RetryPolicy(3, 120.0, 1800.0),
        "rate_limit_policy": RateLimitPolicy(4, 3600.0, 60.0, 1),
        "adapter_version": "entsoe-transparency-xml-v1",
    },
    credentials=(
        ProviderCredentialSpec("ENTSOE", "ENTSO-E Transparency", ("ENTSOE_SECURITY_TOKEN",)),
    ),
)
