"""ENTSOG transmission UMM connector manifest (src-entsog-umm).

Its own connector rather than a dataset of ``src-entsog``: the scheduler runs one script per
source and records one freshness per source, and these messages have their own script
(``scripts/ops/ingest_remit_entsog.py``), table (``remit_umm_messages``, shared with the GIE
IIP collector and the file import) and rhythm (event-driven, months apart). Same provider
terms as ``src-entsog``; no key.
"""

from __future__ import annotations

from eurogas_nexus.domain.connectors.manifest import ConnectorManifest
from eurogas_nexus.domain.dataops.contracts import (
    AccessMode,
    DatasetFreshness,
    FreshnessPolicy,
    RateLimitPolicy,
    RetryPolicy,
    ScheduleType,
    SourceCalendar,
    SourceClass,
    SourceScheduleSpec,
)

MANIFEST = ConnectorManifest(
    source_id="src-entsog-umm",
    system="ENTSOG_UMM",
    # ENTSOG TP Terms of Use Art. 5.2: the source with the download date, which every
    # stored message carries in its source reference (ENTSOG_TP:terms-published:api:<UTC>).
    attribution="ENTSOG TP [DD-MM-YYYY] https://transparency.entsog.eu/",
    category="infrastructure",
    datasets=("transmission-umm-outages",),
    description="ENTSOG Transparency Platform urgent market messages: planned and "
    "unplanned transmission system and compressor station unavailability published by "
    "TSOs (scripts/ops/ingest_remit_entsog.py), stored with the REMIT outages. Free, no "
    "key; ENTSOG TP terms (download, store and use with source and date cited).",
    entitled=False,
    freshness_minutes=60,
    integration="api",
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
        "freshness_policy": FreshnessPolicy(60, 180, 720),
        "retry_policy": RetryPolicy(3, 60.0, 900.0),
        "rate_limit_policy": RateLimitPolicy(6, 3600.0, 10.0, 1),
        "adapter_version": "entsog-umm-api-v1",
    },
    # The stored datasets and how old each one's newest period may be (FRESH-01).
    dataset_freshness=(
        DatasetFreshness(
            "Outages (ENTSOG UMM)",
            2160,
            4320,
            "Event-driven and sparse: months between transmission messages are normal "
            "(none May to September 2026).",
        ),
    ),
)
