"""ELEXON connector manifest (src-elexon)."""

from __future__ import annotations

from eurogas_nexus.domain.connectors.manifest import ConnectorManifest
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
    source_id="src-elexon",
    system="ELEXON",
    category="power",
    datasets=("generation-by-fuel", "demand-outturn", "market-index-price"),
    description="Elexon Insights (BMRS) Great Britain half-hourly gas-fired and wind "
    "generation, national demand and the APX market index price: the GB side of gas "
    "burned for power, which ENTSO-E does not carry. Free, no key; attribution: "
    "Contains BMRS data © Elexon Limited copyright and database right.",
    entitled=False,
    freshness_minutes=120,
    # Run by the scheduler through scripts/ops/ingest_power_gb.py. No credential.
    operations={
        "source_class": SourceClass.PUBLIC,
        "access_mode": AccessMode.PUBLIC_HTTP,
        "schedulable": True,
        "enabled_default": True,
        "schedule": SourceScheduleSpec(
            schedule_type=ScheduleType.INTERVAL,
            interval_seconds=1800,
        ),
        # Generation and demand publish within the hour of each settlement period.
        "freshness_policy": FreshnessPolicy(120, 360, 1440),
        "retry_policy": RetryPolicy(3, 120.0, 1800.0),
        "rate_limit_policy": RateLimitPolicy(6, 3600.0, 30.0, 1),
        "adapter_version": "elexon-insights-json-v1",
    },
)
