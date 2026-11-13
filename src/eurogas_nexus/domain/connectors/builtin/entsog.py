"""ENTSOG connector manifest (src-entsog)."""

from __future__ import annotations

from eurogas_nexus.domain.connectors.manifest import ConnectorManifest
from eurogas_nexus.domain.dataops.contracts import (
    AccessMode,
    FreshnessPolicy,
    RateLimitPolicy,
    RetryPolicy,
    ScheduleType,
    SourceCalendar,
    SourceClass,
    SourceScheduleSpec,
)

MANIFEST = ConnectorManifest(
    source_id="src-entsog",
    system="ENTSOG",
    attribution="Source: ENTSOG Transparency Platform",
    category="infrastructure",
    datasets=("connection-points", "operator-directions", "flows", "capacity", "outages", "ip"),
    description="ENTSOG Transparency Platform infrastructure, flows, capacities, IPs, and outages.",
    entitled=False,
    freshness_minutes=60,
    operations={
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
)
