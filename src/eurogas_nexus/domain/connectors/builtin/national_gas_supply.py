"""National Gas GB storage and LNG connector manifest (src-national-gas-supply)."""

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
    source_id="src-national-gas-supply",
    system="NATIONAL_GAS",
    category="infrastructure",
    datasets=("gb-storage", "gb-lng"),
    description="National Gas data portal: Great Britain storage stock, withdrawal and "
    "injection, LNG tank stock and send-out into the NTS, per gas day. The GB side of the "
    "storage and LNG balance, which GIE AGSI/ALSI leave empty. Free, no key; open data "
    "with attribution to National Gas Transmission.",
    # Open data, no key: public entitlement (as ENTSOG and ECB), no credential requirement.
    entitled=False,
    freshness_minutes=1440,
    # Run by the scheduler through scripts/ops/ingest_national_gas_supply.py. No credential.
    operations={
        "source_class": SourceClass.PUBLIC,
        "access_mode": AccessMode.PUBLIC_HTTP,
        "schedulable": True,
        "enabled_default": True,
        "schedule": SourceScheduleSpec(
            schedule_type=ScheduleType.INTERVAL,
            interval_seconds=3 * 3600,
        ),
        "calendar": SourceCalendar.GAS_MARKET,
        # Nominations publish D+1 04:00, stock D+1 afternoon, allocations D+2.
        "freshness_policy": FreshnessPolicy(1440, 2160, 4320),
        "retry_policy": RetryPolicy(3, 120.0, 1800.0),
        "rate_limit_policy": RateLimitPolicy(6, 3600.0, 30.0, 1),
        "adapter_version": "national-gas-supply-csv-v1",
    },
)
