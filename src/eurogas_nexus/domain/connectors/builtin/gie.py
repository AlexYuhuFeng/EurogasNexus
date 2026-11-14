"""GIE connector manifest (src-gie)."""

from __future__ import annotations

from eurogas_nexus.domain.connectors.manifest import ConnectorManifest, ProviderCredentialSpec
from eurogas_nexus.domain.dataops.contracts import (
    AccessMode,
    DatasetFreshness,
    FreshnessPolicy,
    LicensedDataPolicy,
    RateLimitPolicy,
    RetryPolicy,
    ScheduleType,
    SourceCalendar,
    SourceClass,
    SourceScheduleSpec,
)

MANIFEST = ConnectorManifest(
    source_id="src-gie",
    system="GIE",
    attribution="Source: GIE AGSI+/ALSI (Gas Infrastructure Europe)",
    category="infrastructure",
    datasets=("agsi-storage", "alsi-lng"),
    description="Gas Infrastructure Europe AGSI storage and ALSI LNG data.",
    entitled=True,
    freshness_minutes=360,
    operations={
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
        # One read a day after the 09:00 run: a receipt is up to a day old before the next.
        "freshness_policy": FreshnessPolicy(1500, 2880, 4320),
        "retry_policy": RetryPolicy(3, 60.0, 1800.0),
        "rate_limit_policy": RateLimitPolicy(12, 3600.0, 10.0, 1),
        "adapter_version": "public-source-ingestor/1",
        "licensed_data": LicensedDataPolicy(
            raw_retention_allowed=True,
            retention_note="bounded archive; never served through public API",
        ),
    },
    credentials=(
        ProviderCredentialSpec(
            "GIE",
            "GIE AGSI/ALSI",
            ("GIE_API_KEY",),
            file_env="GIE_API_KEY_FILE",
            note="Also needs a certification record before live ingestion.",
        ),
    ),
    # The stored datasets and how old each one's newest period may be (FRESH-01).
    dataset_freshness=(
        DatasetFreshness(
            "GIE storage (AGSI)",
            72,
            216,
            "AGSI+ publishes gas day D at about 18:00 CET on D+1, corrected the next morning.",
        ),
        DatasetFreshness(
            "GIE LNG (ALSI)",
            72,
            216,
            "ALSI publishes gas day D at about 18:00 CET on D+1, corrected the next morning.",
        ),
    ),
)
