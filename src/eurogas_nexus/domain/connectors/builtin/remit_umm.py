"""REMIT connector manifest (src-remit-umm).

Two ways in, one store (``remit_umm_messages``): the scheduler collects storage and LNG
UMMs from GIE's Inside Information Platform API (scripts/ops/ingest_remit_iip.py, GIE key,
reuse permitted with GIE credited), and an operator can still import the desk's export
from any other platform (scripts/ops/import_remit_umm.py).
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
    source_id="src-remit-umm",
    system="REMIT",
    attribution="Source: GIE Inside Information Platform (IIP/GIE)",
    category="infrastructure",
    datasets=("gas-umm-outages",),
    description="REMIT urgent market messages: planned and unplanned outages of gas "
    "storage and LNG collected from GIE's Inside Information Platform API "
    "(scripts/ops/ingest_remit_iip.py), plus production and transmission messages "
    "imported from the desk's inside-information platform export "
    "(scripts/ops/import_remit_umm.py).",
    entitled=False,
    # UMMs are event-driven: a day without a new message is normal.
    freshness_minutes=1440,
    integration="api",
    operations={
        "source_class": SourceClass.PUBLIC,
        "access_mode": AccessMode.KEYED_HTTP,
        "credential_fields": ("api_key",),
        "schedulable": True,
        # Needs the registered GIE key (GIE_API_KEY), as src-gie.
        "enabled_default": False,
        "schedule": SourceScheduleSpec(
            schedule_type=ScheduleType.INTERVAL,
            interval_seconds=30 * 60,
        ),
        "calendar": SourceCalendar.GAS_MARKET,
        "freshness_policy": FreshnessPolicy(1440, 2880, 10080),
        "retry_policy": RetryPolicy(3, 120.0, 1800.0),
        "rate_limit_policy": RateLimitPolicy(6, 3600.0, 30.0, 1),
        "adapter_version": "remit-gie-iip-api-v1",
    },
)
