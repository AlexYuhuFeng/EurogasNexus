"""Import-safe data-operations domain contracts.

This module is pure Python: no web framework, no ORM, no network. It defines
the canonical vocabulary used by the scheduler, freshness engine, retry and
circuit policy, quality framework, certification ladder and entitlement
propagation in CR-09.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum


def as_utc(value: datetime) -> datetime:
    """Normalize a timestamp to aware UTC (naive timestamps are UTC)."""

    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class SourceClass(StrEnum):
    """Provider/source classification used by data policy."""

    PUBLIC = "public"
    LICENSED = "licensed"
    BROKER = "broker"
    EXCHANGE = "exchange"
    OPERATOR = "operator"
    MODEL = "model"
    REFERENCE = "reference"
    SIMULATED = "simulated"
    UNKNOWN = "unknown"


class AccessMode(StrEnum):
    """How the provider is accessed."""

    PUBLIC_HTTP = "public_http"
    KEYED_HTTP = "keyed_http"
    SOCKET_FEED = "socket_feed"
    FILE_UPLOAD = "file_upload"
    NONE = "none"


class SourceCalendar(StrEnum):
    """Publication-calendar class for a source."""

    ALWAYS_OPEN = "always_open"
    GAS_MARKET = "gas_market"
    WEEKDAYS_ONLY = "weekdays_only"


class ScheduleType(StrEnum):
    """Typed ingestion schedules."""

    INTERVAL = "INTERVAL"
    DAILY = "DAILY"
    MARKET_RELATIVE = "MARKET_RELATIVE"
    EXTERNAL = "EXTERNAL"


class IngestionTriggerType(StrEnum):
    """Who asked for one ingestion run."""

    SCHEDULED = "SCHEDULED"
    MANUAL = "MANUAL"
    BACKFILL = "BACKFILL"
    RECOVERY = "RECOVERY"
    CERTIFICATION_TEST = "CERTIFICATION_TEST"


class IngestionRunStatus(StrEnum):
    """Persisted ingestion run lifecycle."""

    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    SUCCEEDED_WITH_WARNINGS = "SUCCEEDED_WITH_WARNINGS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class FailureCategory(StrEnum):
    """Failure classification used before any retry decision."""

    NETWORK_TRANSIENT = "NETWORK_TRANSIENT"
    RATE_LIMITED = "RATE_LIMITED"
    AUTHENTICATION = "AUTHENTICATION"
    ENTITLEMENT = "ENTITLEMENT"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    BAD_RESPONSE = "BAD_RESPONSE"
    SCHEMA_CHANGED = "SCHEMA_CHANGED"
    QUALITY_REJECTED = "QUALITY_REJECTED"
    CONFIGURATION = "CONFIGURATION"
    INTERNAL = "INTERNAL"


RETRYABLE_FAILURE_CATEGORIES = frozenset(
    {
        FailureCategory.NETWORK_TRANSIENT,
        FailureCategory.RATE_LIMITED,
        FailureCategory.PROVIDER_UNAVAILABLE,
        FailureCategory.BAD_RESPONSE,
        FailureCategory.INTERNAL,
    }
)

NON_RETRYABLE_FAILURE_CATEGORIES = frozenset(
    {
        FailureCategory.AUTHENTICATION,
        FailureCategory.ENTITLEMENT,
        FailureCategory.SCHEMA_CHANGED,
        FailureCategory.QUALITY_REJECTED,
        FailureCategory.CONFIGURATION,
    }
)


class CircuitState(StrEnum):
    """Persisted per-source circuit-breaker state."""

    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    OPEN_CIRCUIT = "OPEN_CIRCUIT"
    DISABLED = "DISABLED"


class FreshnessState(StrEnum):
    """Deterministic source freshness states (backend-owned)."""

    FRESH = "FRESH"
    LATE = "LATE"
    STALE = "STALE"
    MISSING = "MISSING"
    UNKNOWN = "UNKNOWN"
    NOT_EXPECTED = "NOT_EXPECTED"
    RESTRICTED = "RESTRICTED"


class CertificationState(StrEnum):
    """Dataset/provider certification ladder.

    Implementation, configuration, connection and data validation are all
    distinct from ``CERTIFIED``. Mocked tests may never reach CERTIFIED.
    """

    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
    IMPLEMENTED = "IMPLEMENTED"
    CONFIGURED = "CONFIGURED"
    CONNECTION_VERIFIED = "CONNECTION_VERIFIED"
    DATA_VALIDATED = "DATA_VALIDATED"
    CERTIFIED = "CERTIFIED"
    CERTIFICATION_EXPIRED = "CERTIFICATION_EXPIRED"
    BLOCKED = "BLOCKED"


class QualitySeverity(StrEnum):
    """Structured issue severity."""

    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class QualityResult(StrEnum):
    """Run-level quality summary."""

    PASSED = "PASSED"
    PASSED_WITH_WARNINGS = "PASSED_WITH_WARNINGS"
    FAILED = "FAILED"


class EntitlementOutcome(StrEnum):
    """Outcome of a derived-result entitlement evaluation."""

    ALLOWED = "ALLOWED"
    DENIED = "DENIED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class FreshnessPolicy:
    """Backend-owned freshness thresholds for one dataset/source."""

    normal_max_age_minutes: int
    late_after_minutes: int
    stale_after_minutes: int
    basis: str = "observed_at_utc"


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Bounded exponential backoff with full jitter."""

    retry_max: int = 3
    backoff_seconds: float = 30.0
    max_delay_seconds: float = 900.0
    jitter: bool = True


@dataclass(frozen=True, slots=True)
class RateLimitPolicy:
    """Provider-defined rate limits (configuration gaps stay explicit)."""

    max_requests_per_interval: int | None = None
    interval_seconds: float = 60.0
    min_spacing_seconds: float = 0.0
    max_concurrency: int = 1


@dataclass(frozen=True, slots=True)
class CircuitPolicy:
    """Circuit breaker thresholds for one source."""

    degraded_after_failures: int = 3
    open_after_failures: int = 6
    recovery_probe_after_seconds: int = 900


@dataclass(frozen=True, slots=True)
class SourceScheduleSpec:
    """Typed schedule for one source/dataset."""

    schedule_type: ScheduleType = ScheduleType.EXTERNAL
    interval_seconds: int | None = None
    daily_at: str | None = None
    timezone: str = "UTC"
    market_relative_offset_seconds: int | None = None
    missed_policy: str = "CATCH_UP_LIMITED"


@dataclass(frozen=True, slots=True)
class LicensedDataPolicy:
    """Fail-closed licensed-data boundary configuration."""

    raw_retention_allowed: bool = False
    api_exposure_allowed: bool = False
    logging_allowed: bool = False
    export_allowed: bool = False
    llm_allowed: bool = False
    retention_note: str = ""


@dataclass(frozen=True, slots=True)
class SourceDefinition:
    """Canonical backend-owned source descriptor."""

    source_id: str
    provider: str
    dataset: str
    source_class: SourceClass = SourceClass.UNKNOWN
    access_mode: AccessMode = AccessMode.NONE
    entitlement_scope: str = "public"
    credential_fields: tuple[str, ...] = ()
    certification_required: bool = False
    schedulable: bool = False
    enabled_default: bool = False
    datasets: tuple[str, ...] = ()
    schedule: SourceScheduleSpec = field(default_factory=SourceScheduleSpec)
    freshness_policy: FreshnessPolicy = field(
        default_factory=lambda: FreshnessPolicy(1440, 2880, 4320)
    )
    retry_policy: RetryPolicy = field(default_factory=RetryPolicy)
    rate_limit_policy: RateLimitPolicy = field(default_factory=RateLimitPolicy)
    circuit_policy: CircuitPolicy = field(default_factory=CircuitPolicy)
    calendar: SourceCalendar = SourceCalendar.ALWAYS_OPEN
    adapter_version: str = "unversioned"
    licensed_data: LicensedDataPolicy = field(default_factory=LicensedDataPolicy)
    description: str = ""


@dataclass(frozen=True, slots=True)
class FailureClassification:
    """Classified ingestion failure; retry is decided from the category."""

    category: FailureCategory
    retryable: bool
    code: str = ""
    message: str = ""


@dataclass(frozen=True, slots=True)
class RetryDecision:
    """Retry decision with the delay to sleep before the next attempt."""

    retry: bool
    category: FailureCategory
    delay_seconds: float = 0.0
    reason: str = ""


@dataclass(frozen=True, slots=True)
class FreshnessEvaluation:
    """Deterministic freshness result for one source."""

    source_id: str
    state: FreshnessState
    source_age_seconds: float | None = None
    threshold_minutes: int | None = None
    reason: str = ""
    evaluated_at_utc: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )


@dataclass(frozen=True, slots=True)
class QualityIssue:
    """One structured data-quality issue."""

    quality_code: str
    severity: QualitySeverity
    field: str = ""
    observation_reference: str = ""
    message: str = ""
    rule_version: str = "dataops-quality/1"


@dataclass(frozen=True, slots=True)
class QualitySummary:
    """Run-level quality result and issue counts."""

    result: QualityResult
    warning_count: int
    error_count: int
    issues: tuple[QualityIssue, ...] = ()


@dataclass(frozen=True, slots=True)
class DerivedAccessDecision:
    """Whether a derived result may be exposed to a principal."""

    outcome: EntitlementOutcome
    blocked_sources: tuple[str, ...] = ()
    reason: str = ""
