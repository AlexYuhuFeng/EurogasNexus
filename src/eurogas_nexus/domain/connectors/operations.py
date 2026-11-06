"""Shared operations profiles a connector manifest may use (C1).

Families of sources share a policy (TSO tariff publications, exchange feeds, licensed
vendor feeds, daily benchmark rates); a manifest names its family here instead of repeating
the numbers.
"""

from __future__ import annotations

from eurogas_nexus.domain.dataops.contracts import (
    AccessMode,
    FreshnessPolicy,
    LicensedDataPolicy,
    RateLimitPolicy,
    RetryPolicy,
    ScheduleType,
    SourceCalendar,
    SourceClass,
    SourceScheduleSpec,
)


def tariff_operations() -> dict:
    return {
        "source_class": SourceClass.REFERENCE,
        "access_mode": AccessMode.PUBLIC_HTTP,
        "freshness_policy": FreshnessPolicy(43200, 64800, 129600),
        "retry_policy": RetryPolicy(2, 60.0, 1800.0),
    }


def exchange_operations(provider: str) -> dict:
    return {
        "source_class": SourceClass.EXCHANGE,
        "access_mode": AccessMode.KEYED_HTTP,
        "credential_fields": ("api_key",),
        "certification_required": True,
        "freshness_policy": FreshnessPolicy(1, 5, 30),
        "licensed_data": LicensedDataPolicy(),
    }


def licensed_operations(normal: int, late: int, stale: int) -> dict:
    return {
        "source_class": SourceClass.LICENSED,
        "access_mode": AccessMode.KEYED_HTTP,
        "credential_fields": ("api_key",),
        "certification_required": True,
        "freshness_policy": FreshnessPolicy(normal, late, stale),
        "licensed_data": LicensedDataPolicy(),
    }


def rate_operations(daily_at: str, timezone: str) -> dict:
    return {
        "source_class": SourceClass.PUBLIC,
        "access_mode": AccessMode.PUBLIC_HTTP,
        "schedulable": True,
        "enabled_default": True,
        "schedule": SourceScheduleSpec(
            schedule_type=ScheduleType.DAILY, daily_at=daily_at, timezone=timezone
        ),
        "calendar": SourceCalendar.WEEKDAYS_ONLY,
        # A fixing a day; a long weekend or holiday leaves three to four days without one.
        "freshness_policy": FreshnessPolicy(1440 * 2, 1440 * 4, 1440 * 6),
        "retry_policy": RetryPolicy(3, 300.0, 3600.0),
        "rate_limit_policy": RateLimitPolicy(4, 3600.0, 60.0, 1),
        "adapter_version": "interest-rate-ingest/1",
    }
