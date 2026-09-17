"""Product error taxonomy (Architecture V2 08_DECISION_APPLICATION_AI.md section 6).

Architecture V2 requires every failure a user can meet to answer four questions -
what happened, what it affects, the likely cause, and how to recover - through a
stable code rather than a raw exception string:

- families: AUTH, ENTITLEMENT, VALIDATION, DATA, CALCULATION, DEPENDENCY,
  CONFIGURATION, JOB, AGENT, SYSTEM;
- every response carries a stable code, a user-safe message key, severity,
  recoverability, a suggested action and the correlation id;
- operator detail is included only on operator surfaces.

This module is the catalogue and the payload builder. It is framework-free so the
API, workers, scheduled jobs, the CLI and the client all speak one vocabulary, and
it covers the codes this repository already returns rather than inventing a second
set. The older operational taxonomy in ``operations/errors.py`` stays in place for
infrastructure classification; :func:`family_for_operational_category` bridges the
two.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from eurogas_nexus.domain.operations.errors import OperationalErrorCategory


class ErrorFamily(StrEnum):
    """Product failure families."""

    AUTH = "AUTH"
    ENTITLEMENT = "ENTITLEMENT"
    VALIDATION = "VALIDATION"
    DATA = "DATA"
    CALCULATION = "CALCULATION"
    DEPENDENCY = "DEPENDENCY"
    CONFIGURATION = "CONFIGURATION"
    JOB = "JOB"
    AGENT = "AGENT"
    SYSTEM = "SYSTEM"


class ErrorSeverity(StrEnum):
    """How much the failure matters to the user's task."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class Recoverability(StrEnum):
    """What the user or the system can do about it."""

    RETRY = "retry"
    AFTER_USER_ACTION = "after_user_action"
    PERMANENT = "permanent"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class ErrorDefinition:
    """One catalogued failure mode."""

    code: str
    family: ErrorFamily
    severity: ErrorSeverity
    recoverability: Recoverability
    #: Translation keys. The client renders them, so EN and zh-CN stay in step.
    message_key: str
    action_key: str
    #: True when the code may only be shown on an operator surface.
    operator_only: bool = False


def _definition(
    code: str,
    family: ErrorFamily,
    *,
    severity: ErrorSeverity = ErrorSeverity.ERROR,
    recoverability: Recoverability = Recoverability.UNKNOWN,
    operator_only: bool = False,
) -> ErrorDefinition:
    return ErrorDefinition(
        code=code,
        family=family,
        severity=severity,
        recoverability=recoverability,
        message_key=f"errors.{code}.message",
        action_key=f"errors.{code}.action",
        operator_only=operator_only,
    )


# Codes already returned by this repository plus the failure modes Architecture V2
# names explicitly. A code that is not listed here still produces a valid payload
# through the SYSTEM fallback; adding it here is what makes it explainable.
ERROR_CATALOGUE: dict[str, ErrorDefinition] = {
    defn.code: defn
    for defn in (
        # --- authentication and identity ---
        _definition("unauthenticated", ErrorFamily.AUTH, recoverability=Recoverability.AFTER_USER_ACTION),
        _definition("invalid_credentials", ErrorFamily.AUTH, recoverability=Recoverability.AFTER_USER_ACTION),
        _definition("session_invalid", ErrorFamily.AUTH, recoverability=Recoverability.AFTER_USER_ACTION),
        _definition("session_principal_inactive", ErrorFamily.AUTH, recoverability=Recoverability.PERMANENT),
        _definition("identity_not_provisioned", ErrorFamily.AUTH, recoverability=Recoverability.PERMANENT),
        _definition("dev_login_disabled", ErrorFamily.AUTH, recoverability=Recoverability.PERMANENT),
        _definition("oidc_not_configured", ErrorFamily.CONFIGURATION, operator_only=True),
        _definition(
            "identity_store_not_configured", ErrorFamily.CONFIGURATION, operator_only=True
        ),
        _definition("identity_store_unavailable", ErrorFamily.DEPENDENCY, recoverability=Recoverability.RETRY),
        _definition("principal_missing", ErrorFamily.AUTH, recoverability=Recoverability.AFTER_USER_ACTION),
        _definition("operator_principal_missing", ErrorFamily.AUTH, recoverability=Recoverability.AFTER_USER_ACTION),
        _definition("operator_principal_invalid", ErrorFamily.AUTH, recoverability=Recoverability.AFTER_USER_ACTION),
        # --- authorization and entitlement ---
        _definition("identity_role_forbidden", ErrorFamily.AUTH, recoverability=Recoverability.PERMANENT),
        _definition("permission_denied", ErrorFamily.AUTH, recoverability=Recoverability.PERMANENT),
        _definition("permission_not_declared", ErrorFamily.CONFIGURATION, severity=ErrorSeverity.CRITICAL, operator_only=True),
        _definition(
            "commercial_access_not_granted",
            ErrorFamily.ENTITLEMENT,
            recoverability=Recoverability.AFTER_USER_ACTION,
        ),
        _definition("entitlement_denied", ErrorFamily.ENTITLEMENT, recoverability=Recoverability.PERMANENT),
        _definition("entitlement_unavailable", ErrorFamily.ENTITLEMENT, recoverability=Recoverability.RETRY),
        _definition("export_denied", ErrorFamily.ENTITLEMENT, recoverability=Recoverability.PERMANENT),
        # --- validation ---
        _definition("dataset_spec_invalid", ErrorFamily.VALIDATION, recoverability=Recoverability.AFTER_USER_ACTION),
        _definition("dataset_build_invalid", ErrorFamily.VALIDATION, recoverability=Recoverability.AFTER_USER_ACTION),
        # --- data ---
        _definition("DATA_STALE", ErrorFamily.DATA, severity=ErrorSeverity.WARNING, recoverability=Recoverability.RETRY),
        _definition("DATA_MISSING", ErrorFamily.DATA, severity=ErrorSeverity.WARNING),
        _definition("PORTFOLIO_INCOMPLETE", ErrorFamily.DATA, severity=ErrorSeverity.WARNING),
        _definition("SNAPSHOT_EXPIRED", ErrorFamily.DATA, recoverability=Recoverability.AFTER_USER_ACTION),
        # --- calculation ---
        _definition("ROUTE_INFEASIBLE", ErrorFamily.CALCULATION, recoverability=Recoverability.AFTER_USER_ACTION),
        _definition("OPTIMIZATION_INFEASIBLE", ErrorFamily.CALCULATION, recoverability=Recoverability.AFTER_USER_ACTION),
        # --- dependency and runtime ---
        _definition("PROVIDER_UNAVAILABLE", ErrorFamily.DEPENDENCY, severity=ErrorSeverity.WARNING, recoverability=Recoverability.RETRY),
        _definition("runtime_db_unavailable", ErrorFamily.DEPENDENCY, recoverability=Recoverability.RETRY),
        _definition("runtime_db_required", ErrorFamily.CONFIGURATION, recoverability=Recoverability.AFTER_USER_ACTION),
        # --- jobs and agents ---
        _definition("JOB_FAILED", ErrorFamily.JOB, recoverability=Recoverability.RETRY),
        _definition("JOB_CANCELLED", ErrorFamily.JOB, severity=ErrorSeverity.INFO, recoverability=Recoverability.AFTER_USER_ACTION),
        _definition("AGENT_BUDGET_EXCEEDED", ErrorFamily.AGENT, severity=ErrorSeverity.WARNING, recoverability=Recoverability.AFTER_USER_ACTION),
        _definition("AGENT_CAPABILITY_UNAVAILABLE", ErrorFamily.AGENT, recoverability=Recoverability.RETRY),
        # --- system ---
        _definition("internal", ErrorFamily.SYSTEM, severity=ErrorSeverity.CRITICAL, operator_only=True),
    )
}

UNKNOWN_ERROR_CODE = "UNCLASSIFIED_ERROR"

_SYSTEM_FALLBACK = ErrorDefinition(
    code=UNKNOWN_ERROR_CODE,
    family=ErrorFamily.SYSTEM,
    severity=ErrorSeverity.ERROR,
    recoverability=Recoverability.UNKNOWN,
    message_key="errors.unclassified.message",
    action_key="errors.unclassified.action",
    operator_only=False,
)


def error_definition(code: str) -> ErrorDefinition:
    """Look up a code, failing closed to a safe SYSTEM definition when unknown."""

    return ERROR_CATALOGUE.get((code or "").strip(), _SYSTEM_FALLBACK)


def error_family(code: str) -> ErrorFamily:
    """Family of a code (SYSTEM for an unknown code)."""

    return error_definition(code).family


def error_payload(
    code: str,
    *,
    correlation_id: str | None = None,
    message: str | None = None,
    detail: str | None = None,
    operator: bool = False,
) -> dict[str, object]:
    """Build the V2 error body.

    ``message`` overrides the translation key with an already-safe message.
    ``detail`` is operator-only: it is dropped unless ``operator`` is true and the
    definition allows an operator surface, so an internal cause can never leak to
    a business user.
    """

    definition = error_definition(code)
    payload: dict[str, object] = {
        "error": definition.code,
        "family": definition.family.value,
        "severity": definition.severity.value,
        "recoverability": definition.recoverability.value,
        "message_key": definition.message_key,
        "action_key": definition.action_key,
        "correlation_id": correlation_id,
    }
    if message:
        payload["message"] = message
    if operator and detail and not definition.severity == ErrorSeverity.INFO:
        payload["detail"] = detail
    return payload


_OPERATIONAL_FAMILY: dict[OperationalErrorCategory, ErrorFamily] = {
    OperationalErrorCategory.CONFIGURATION: ErrorFamily.CONFIGURATION,
    OperationalErrorCategory.AUTHENTICATION: ErrorFamily.AUTH,
    OperationalErrorCategory.AUTHORIZATION: ErrorFamily.AUTH,
    OperationalErrorCategory.ENTITLEMENT: ErrorFamily.ENTITLEMENT,
    OperationalErrorCategory.DATABASE: ErrorFamily.DEPENDENCY,
    OperationalErrorCategory.MIGRATION: ErrorFamily.CONFIGURATION,
    OperationalErrorCategory.SOURCE_NETWORK: ErrorFamily.DEPENDENCY,
    OperationalErrorCategory.SOURCE_SCHEMA: ErrorFamily.DATA,
    OperationalErrorCategory.SOURCE_QUALITY: ErrorFamily.DATA,
    OperationalErrorCategory.TIMEOUT: ErrorFamily.DEPENDENCY,
    OperationalErrorCategory.SOLVER: ErrorFamily.CALCULATION,
    OperationalErrorCategory.JOB: ErrorFamily.JOB,
    OperationalErrorCategory.INTERNAL: ErrorFamily.SYSTEM,
}


def family_for_operational_category(category: OperationalErrorCategory) -> ErrorFamily:
    """Bridge the infrastructure taxonomy onto the product families."""

    return _OPERATIONAL_FAMILY.get(category, ErrorFamily.SYSTEM)


def catalogue_by_family() -> dict[ErrorFamily, tuple[str, ...]]:
    """Every catalogued code grouped by family (stable order)."""

    grouped: dict[ErrorFamily, list[str]] = {family: [] for family in ErrorFamily}
    for code in sorted(ERROR_CATALOGUE):
        grouped[error_definition(code).family].append(code)
    return {family: tuple(codes) for family, codes in grouped.items()}
