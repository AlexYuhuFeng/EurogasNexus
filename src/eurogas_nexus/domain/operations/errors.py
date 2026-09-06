"""Shared operational error taxonomy.

Stable machine codes replace exception-text-only diagnosis. Categories are
independent of any framework so API, workers, schedulers and scripts use the
same vocabulary.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class OperationalErrorCategory(StrEnum):
    CONFIGURATION = "CONFIGURATION"
    AUTHENTICATION = "AUTHENTICATION"
    AUTHORIZATION = "AUTHORIZATION"
    ENTITLEMENT = "ENTITLEMENT"
    DATABASE = "DATABASE"
    MIGRATION = "MIGRATION"
    SOURCE_NETWORK = "SOURCE_NETWORK"
    SOURCE_SCHEMA = "SOURCE_SCHEMA"
    SOURCE_QUALITY = "SOURCE_QUALITY"
    TIMEOUT = "TIMEOUT"
    SOLVER = "SOLVER"
    JOB = "JOB"
    INTERNAL = "INTERNAL"


@dataclass(frozen=True, slots=True)
class OperationalError:
    """One classified operational error (safe for user/operator surfaces)."""

    category: OperationalErrorCategory
    code: str
    message: str = ""
    retryable: bool = False
    affected: tuple[str, ...] = ()
    last_valid_at_utc: str | None = None


def classify_exception(exc: BaseException) -> OperationalError:
    """Classify common infrastructure/adapter exceptions conservatively."""

    name = exc.__class__.__name__.lower()
    text = str(exc).lower()
    if "operationalerror" in name and "timeout" in name or "timeout" in name or "timed out" in text:
        return OperationalError(
            OperationalErrorCategory.TIMEOUT,
            code="timeout",
            message="The operation exceeded its configured time limit.",
            retryable=True,
        )
    if "connection" in name or "connection" in text:
        return OperationalError(
            OperationalErrorCategory.DATABASE,
            code="database_connection",
            message="The database connection could not be established.",
            retryable=True,
        )
    if "migration" in name or "alembic" in text:
        return OperationalError(
            OperationalErrorCategory.MIGRATION,
            code="migration",
            message="A database migration step failed.",
        )
    if "authentication" in text or "credential" in text:
        return OperationalError(
            OperationalErrorCategory.AUTHENTICATION,
            code="authentication",
            message="Authentication or credential validation failed.",
        )
    if "entitlement" in text:
        return OperationalError(
            OperationalErrorCategory.ENTITLEMENT,
            code="entitlement",
            message="Commercial data entitlement is unavailable or denied.",
        )
    if "schema" in text:
        return OperationalError(
            OperationalErrorCategory.SOURCE_SCHEMA,
            code="source_schema",
            message="A provider schema changed unexpectedly.",
        )
    return OperationalError(
        OperationalErrorCategory.INTERNAL,
        code="internal",
        message="An unexpected internal error occurred.",
    )


def classify_http_status(status_code: int | None) -> OperationalError:
    """Classify HTTP dependency failures with stable codes."""

    if status_code == 401 or status_code == 403:
        return OperationalError(
            OperationalErrorCategory.AUTHENTICATION,
            code=f"http_{status_code}",
            message="Authentication with a dependency failed.",
        )
    if status_code == 429:
        return OperationalError(
            OperationalErrorCategory.SOURCE_NETWORK,
            code="rate_limited",
            message="A dependency rate limit was reached.",
            retryable=True,
        )
    if status_code in {500, 502, 503, 504}:
        return OperationalError(
            OperationalErrorCategory.SOURCE_NETWORK,
            code=f"http_{status_code}",
            message="A dependency is temporarily unavailable.",
            retryable=True,
        )
    if status_code == 404:
        return OperationalError(
            OperationalErrorCategory.CONFIGURATION,
            code="dependency_not_found",
            message="A configured dependency endpoint was not found.",
        )
    return OperationalError(
        OperationalErrorCategory.INTERNAL,
        code=f"http_{status_code or 'unknown'}",
        message="An unexpected dependency response was received.",
    )
