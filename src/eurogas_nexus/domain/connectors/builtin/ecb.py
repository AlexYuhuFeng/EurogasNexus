"""ECB connector manifest (src-ecb)."""

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
    source_id="src-ecb",
    system="ECB",
    category="fx",
    datasets=("eurofxref-daily", "fx-reference-rates"),
    description="European Central Bank FX reference rates.",
    entitled=False,
    freshness_minutes=1440,
    operations={
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
)
