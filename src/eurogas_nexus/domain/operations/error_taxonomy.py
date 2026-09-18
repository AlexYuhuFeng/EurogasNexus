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
        # The origin/CSRF guard's refusals. Catalogued because the code-shape rules would
        # otherwise file them elsewhere ("origin_not_allowed" matches no rule and fell to
        # SYSTEM; "csrf_invalid" would read as a VALIDATION failure), and both are
        # session-bound security refusals the caller can act on.
        _definition(
            "origin_not_allowed",
            ErrorFamily.AUTH,
            recoverability=Recoverability.AFTER_USER_ACTION,
        ),
        _definition(
            "csrf_invalid",
            ErrorFamily.AUTH,
            recoverability=Recoverability.AFTER_USER_ACTION,
        ),
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
        # The analysis and report routes refuse a selection the pipeline cannot apply
        # (Architecture V2 Wave 7 section 16). Catalogued rather than left to the
        # code-shape rules so the caller is told the request itself has to change.
        _definition(
            "analysis_selection_not_supported",
            ErrorFamily.VALIDATION,
            recoverability=Recoverability.AFTER_USER_ACTION,
        ),
        # Generic HTTP failures an endpoint may raise without a domain code. They
        # exist so the error envelope never has to label a plain 404 or 409 as an
        # unclassified SYSTEM fault.
        _definition("not_found", ErrorFamily.VALIDATION, severity=ErrorSeverity.WARNING, recoverability=Recoverability.PERMANENT),
        _definition("conflict", ErrorFamily.VALIDATION, severity=ErrorSeverity.WARNING, recoverability=Recoverability.AFTER_USER_ACTION),
        _definition("validation_failed", ErrorFamily.VALIDATION, recoverability=Recoverability.AFTER_USER_ACTION),
        _definition("service_unavailable", ErrorFamily.DEPENDENCY, recoverability=Recoverability.RETRY),
        _definition("rate_limited", ErrorFamily.DEPENDENCY, severity=ErrorSeverity.WARNING, recoverability=Recoverability.RETRY),
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
        # --- configuration and secrets ---
        _definition("public_api_token_not_configured", ErrorFamily.CONFIGURATION, severity=ErrorSeverity.CRITICAL, operator_only=True),
        _definition("internal_api_token_not_configured", ErrorFamily.CONFIGURATION, severity=ErrorSeverity.CRITICAL, operator_only=True),
        _definition("credential_store_not_configured", ErrorFamily.CONFIGURATION, operator_only=True),
        _definition("llm_provider_denied", ErrorFamily.ENTITLEMENT, recoverability=Recoverability.AFTER_USER_ACTION),
        _definition("oidc_login_error", ErrorFamily.AUTH, recoverability=Recoverability.RETRY),
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

# Suffix/prefix rules for a code that is not catalogued. They exist because the API
# legitimately raises dozens of specific codes (``analysis_snapshot_not_found``,
# ``runtime_db_not_configured``, ``registry_unavailable`` …): the envelope should
# still classify those sensibly instead of dumping every one into SYSTEM, while the
# code string itself is reported unchanged so operators see the real thing.
_FAMILY_RULES: tuple[tuple[tuple[str, ...], ErrorFamily], ...] = (
    # Most specific first: a malformed *request* is VALIDATION even when the subject
    # is an optimisation, and a missing configuration is CONFIGURATION.
    (("not_configured",), ErrorFamily.CONFIGURATION),
    (
        (
            "_not_found",
            "_invalid",
            "_required",
            "_unsupported",
            "_not_applicable",
            "_not_supported",
            "_too_long",
            "_too_many",
            "not_decidable",
            "not_found",
            "invalid",
            "unsupported",
            "conflict",
            "validation",
        ),
        ErrorFamily.VALIDATION,
    ),
    (("_unavailable", "unavailable"), ErrorFamily.DEPENDENCY),
    (("denied", "entitlement", "export", "commercial_access"), ErrorFamily.ENTITLEMENT),
    (
        (
            "credential",
            "authenticated",
            "unauthenticated",
            "oidc",
            "session",
            "principal",
            "identity_role",
        ),
        ErrorFamily.AUTH,
    ),
    (("_stale", "data_", "snapshot_expired", "missing_data"), ErrorFamily.DATA),
    (("optimization", "route_", "infeasible", "calculation"), ErrorFamily.CALCULATION),
    (("job_", "backfill"), ErrorFamily.JOB),
    (("agent_", "capability_"), ErrorFamily.AGENT),
)


def _infer_family(code: str) -> ErrorFamily | None:
    """Family inferred from a code shape, or ``None`` when nothing matches."""

    normalized = code.casefold()
    for markers, family in _FAMILY_RULES:
        if any(marker in normalized for marker in markers):
            return family
    return None


def error_definition(code: str) -> ErrorDefinition:
    """Look up a code, falling back to a family inference and then to SYSTEM.

    An uncatalogued code keeps its own identifier - operators need the real string -
    but takes the family-level translation keys, so a client always has text to
    render instead of a missing-key placeholder.
    """

    normalized = (code or "").strip()
    catalogued = ERROR_CATALOGUE.get(normalized)
    if catalogued is not None:
        return catalogued

    family = _infer_family(normalized) if normalized else None
    if family is None:
        return _SYSTEM_FALLBACK

    return ErrorDefinition(
        code=normalized,
        family=family,
        severity=ErrorSeverity.ERROR,
        recoverability=Recoverability.UNKNOWN,
        message_key=f"errors.family.{family.value}.title",
        action_key=f"errors.family.{family.value}.action",
        operator_only=False,
    )


def error_family(code: str) -> ErrorFamily:
    """Family of a code (SYSTEM for an unknown code)."""

    return error_definition(code).family


def error_payload(
    code: str,
    *,
    correlation_id: str | None = None,
    message: str | None = None,
    operator_detail: str | None = None,
    operator: bool = False,
) -> dict[str, object]:
    """Build the V2 error body.

    ``message`` overrides the translation key with an already-safe message.
    ``operator_detail`` is operator-only: it is dropped unless ``operator`` is true
    and the code is not merely informational, so an internal cause can never leak to
    a business user. The field is named distinctly from ``detail`` so it cannot be
    confused with the endpoint's own ``detail`` payload.
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
    if operator and operator_detail and definition.severity != ErrorSeverity.INFO:
        payload["operator_detail"] = operator_detail
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


# Fallback codes for an HTTP failure raised without a domain code, used by the API
# error envelope. A status without a catalogued meaning stays unclassified rather
# than being mislabelled.
_STATUS_FALLBACK_CODES: dict[int, str] = {
    400: "validation_failed",
    401: "unauthenticated",
    403: "permission_denied",
    404: "not_found",
    409: "conflict",
    422: "validation_failed",
    429: "rate_limited",
    503: "service_unavailable",
}


def code_for_status(status_code: int) -> str:
    """Best-effort code for an HTTP failure raised without one."""

    return _STATUS_FALLBACK_CODES.get(status_code, UNKNOWN_ERROR_CODE)


def catalogue_by_family() -> dict[ErrorFamily, tuple[str, ...]]:
    """Every catalogued code grouped by family (stable order)."""

    grouped: dict[ErrorFamily, list[str]] = {family: [] for family in ErrorFamily}
    for code in sorted(ERROR_CATALOGUE):
        grouped[error_definition(code).family].append(code)
    return {family: tuple(codes) for family, codes in grouped.items()}
