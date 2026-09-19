"""Service identities for headless callers (owner decision D7).

Every *caller-driven* provider invocation is re-authorised against the caller's own
``analysis.query`` capability (finding C8). The deployed ``monitoring-worker`` was the exception: it
enriches alerts through ``invoke_deepseek`` with no principal, permission or authority reference at
all, because it has no caller identity for a capability to bind to. Deciding what *should* bind is a
design question about service identities, which is why it sat in the register as D7 rather
than being patched as a missing check.

**The decision.** A headless caller authenticates as a **named service principal** the deployment
provisions — a real identity row, so its role, data scopes and status are enforceable and revocable
like any other actor — the provider call is authorised against *that principal's* capability using
the same rule interactive calls use, and every enriched alert records it as the actor. A deployment
that has not named one gets **no enrichment**: the worker reports the refusal instead of calling a
provider with nobody's authority behind the call. That fail-closed shape is deliberate: a
monitoring pipeline that stops analysing and says why is a broken feature, while one that
silently spends a provider credential on behalf of nobody is a missing control.

Note the difference from the interactive path on purpose: the compatibility deployment token is
accepted there as the deployment's own configuration (finding C5), and a *service* identity here
must hold ``analysis.query`` explicitly. A service principal exists precisely so that its
authority is a grant somebody made, not a default it inherited.
"""

from __future__ import annotations

from dataclasses import dataclass

from eurogas_nexus.security.authorization import (
    Permission,
    authorize,
)
from eurogas_nexus.security.identity import AuthenticatedPrincipal

#: Environment variable naming the principal a headless worker runs as.
SERVICE_PRINCIPAL_ENV = "EUROGAS_NEXUS_WORKER_PRINCIPAL"

#: Why a headless provider call was refused. Declared codes, so a log line and a test agree.
SERVICE_AUTHORITY_NOT_CONFIGURED = "service_principal_not_configured"
SERVICE_AUTHORITY_UNKNOWN_PRINCIPAL = "service_principal_unknown"
SERVICE_AUTHORITY_INACTIVE_PRINCIPAL = "service_principal_inactive"
SERVICE_AUTHORITY_NOT_GRANTED = "service_authority_not_granted"


@dataclass(frozen=True)
class ServiceAuthority:
    """The outcome of resolving a headless caller's authority.

    Attributes:
        principal: The service principal when one is configured and usable, else ``None``.
        refusal: The declared refusal code when there is none, else ``""``.
        detail: A sentence naming what is missing, for the operator reading the worker's log.
    """

    principal: AuthenticatedPrincipal | None
    refusal: str
    detail: str

    @property
    def granted(self) -> bool:
        """Whether a provider call may proceed under this authority."""

        return self.principal is not None and not self.refusal


def configured_service_principal_name() -> str:
    """Return the configured service principal name, or an empty string when none is named."""

    import os

    return os.environ.get(SERVICE_PRINCIPAL_ENV, "").strip()


def _service_principal_from_row(row: object) -> AuthenticatedPrincipal:
    """Build the acting principal from a provisioned identity row."""

    return AuthenticatedPrincipal(
        principal_id=row.principal_id,
        name=row.name,
        principal_type=getattr(row, "principal_type", "SERVICE"),
        role=row.role,
        status=getattr(row, "status", "ACTIVE"),
        data_scopes=tuple(getattr(row, "data_scopes", None) or []),
        roles=tuple(getattr(row, "roles", None) or [row.role]),
        email=getattr(row, "email", None),
        identity_source=getattr(row, "identity_source", "LOCAL") or "LOCAL",
        auth_method="service_identity",
    )


def resolve_service_authority(session: object | None) -> ServiceAuthority:
    """Resolve the headless caller's authority from the deployment's configuration.

    解析无头调用方的服务身份：未配置、未知、已停用或未获授权时拒绝调用提供方。

    Args:
        session: Open runtime-database session, or ``None`` when no database is configured.

    Returns:
        A :class:`ServiceAuthority`; inspect ``granted`` before invoking a provider.
    """

    name = configured_service_principal_name()
    if not name:
        return ServiceAuthority(
            principal=None,
            refusal=SERVICE_AUTHORITY_NOT_CONFIGURED,
            detail=(
                "No service principal is configured. Set "
                f"{SERVICE_PRINCIPAL_ENV} to the name of an ACTIVE identity that holds the "
                "analysis capability, or run the worker with "
                "enrichment disabled and accept that alerts stay unanalysed."
            ),
        )
    if session is None:
        return ServiceAuthority(
            principal=None,
            refusal=SERVICE_AUTHORITY_UNKNOWN_PRINCIPAL,
            detail=(
                f"{SERVICE_PRINCIPAL_ENV} names {name!r}, but no runtime database is configured to "
                "provision it from."
            ),
        )

    from eurogas_nexus.db.models import IdentityPrincipalRecord

    row = (
        session.query(IdentityPrincipalRecord)
        .filter(IdentityPrincipalRecord.name == name)
        .one_or_none()
    )
    if row is None:
        return ServiceAuthority(
            principal=None,
            refusal=SERVICE_AUTHORITY_UNKNOWN_PRINCIPAL,
            detail=(
                f"{SERVICE_PRINCIPAL_ENV} names {name!r}, and no identity by that name exists in "
                "this deployment."
            ),
        )
    if getattr(row, "status", "ACTIVE") != "ACTIVE":
        return ServiceAuthority(
            principal=None,
            refusal=SERVICE_AUTHORITY_INACTIVE_PRINCIPAL,
            detail=(
                f"The service principal {name!r} is {getattr(row, 'status', 'unknown')}; a "
                "non-ACTIVE identity cannot act."
            ),
        )

    principal = _service_principal_from_row(row)
    return require_service_capability(principal)


def require_service_capability(principal: AuthenticatedPrincipal) -> ServiceAuthority:
    """Check a service principal holds the capability a provider call needs.

    与交互式调用使用同一套能力判定：服务身份必须显式持有 `analysis.query`。

    Args:
        principal: The service principal to check.

    Returns:
        A granted :class:`ServiceAuthority`, or a refusal naming the missing capability.
    """

    decision = authorize(principal, Permission.ANALYSIS_QUERY)
    if decision.allowed:
        return ServiceAuthority(principal=principal, refusal="", detail="")
    return ServiceAuthority(
        principal=None,
        refusal=SERVICE_AUTHORITY_NOT_GRANTED,
        detail=(
            f"The service principal {principal.name!r} does not hold "
            f"{Permission.ANALYSIS_QUERY.value!r}"
            + (f" ({decision.reason})" if decision.reason else "")
            + ", so it may not spend a provider call."
        ),
    )
