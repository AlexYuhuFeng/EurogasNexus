"""National Gas GB NTS actual demand connector manifest (src-national-gas-demand).

Its own connector rather than a third dataset of ``src-national-gas-supply``: the scheduler
runs one script per source and records one freshness per source, and demand has its own
script, table (``national_gas_actual_demand``, an append-only revision log) and publication
rhythm (D+1 initial, D+6 amended), as GIE's AGSI and ALSI share ``src-gie`` because they
share one ingestion path.
"""

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
    source_id="src-national-gas-demand",
    # Distinct from the storage/LNG connector's NATIONAL_GAS: one system per source.
    system="NATIONAL_GAS_DEMAND",
    attribution="Contains data from National Gas Transmission (data portal, open data)",
    category="infrastructure",
    datasets=("gb-nts-demand",),
    description="National Gas data portal: Great Britain NTS actual demand per gas day, "
    "D+1 initial (PUBOB637) and D+6 amended (PUBOB652), each publication kept as a "
    "revision. Free, no key; open data with attribution to National Gas Transmission.",
    entitled=False,
    freshness_minutes=1440,
    # Run by the scheduler through scripts/ops/ingest_national_gas_demand.py. No credential.
    operations={
        "source_class": SourceClass.PUBLIC,
        "access_mode": AccessMode.PUBLIC_HTTP,
        "schedulable": True,
        "enabled_default": True,
        "schedule": SourceScheduleSpec(
            schedule_type=ScheduleType.INTERVAL,
            interval_seconds=6 * 3600,
        ),
        "calendar": SourceCalendar.GAS_MARKET,
        # D+1 publishes the morning after the gas day; D+6 amends it five days later.
        "freshness_policy": FreshnessPolicy(1440, 2160, 4320),
        "retry_policy": RetryPolicy(3, 120.0, 1800.0),
        "rate_limit_policy": RateLimitPolicy(6, 3600.0, 30.0, 1),
        "adapter_version": "national-gas-demand-csv-v1",
    },
)
