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

**Where the rule is enforced.** Not only where the attempt is scheduled. The scan gate decides
whether to *try*, and the provider boundary (``monitoring_service.enrich_monitoring_alert``'s
authority check) decides whether the call may actually happen: it re-reads the persisted identity
so a revocation, deactivation or downgrade between scheduling and invocation takes effect
immediately, and it checks that the acting principal the caller carries is the canonical persisted
identity rather than trusting the dataclass it was handed. The configured identity must also be a
**SERVICE** principal: a human (``USER``) identity named in the configuration is a masquerade the
worker refuses, because a person's role is not a service authority and must not be spent headlessly.

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
#: Only a provisioned SERVICE principal may act headlessly; a human (``USER``) row is refused.
SERVICE_AUTHORITY_HUMAN_PRINCIPAL = "service_principal_human_identity"
#: The attempt carried no acting principal at all.
SERVICE_AUTHORITY_ACTOR_MISSING = "service_actor_missing"
#: The acting principal is not the configured, persisted service identity.
SERVICE_AUTHORITY_ACTOR_MISMATCH = "service_actor_mismatch"


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
                f"{SERVICE_PRINCIPAL_ENV} to the name of an ACTIVE SERVICE identity that holds "
                "the analysis capability, or run the worker with "
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
        # Re-read the persisted row on every resolution: a long-lived worker holds an authority
        # dataclass across scans, and a cached instance must not hide a revocation or downgrade.
        .populate_existing()
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
    principal_type = (getattr(row, "principal_type", "") or "").strip().upper()
    if principal_type != "SERVICE":
        return ServiceAuthority(
            principal=None,
            refusal=SERVICE_AUTHORITY_HUMAN_PRINCIPAL,
            detail=(
                f"The identity {name!r} is a {principal_type or 'UNKNOWN'} principal, and a "
                "headless provider call runs only as a provisioned SERVICE principal. Provision "
                f"a least-privilege SERVICE identity and name it in {SERVICE_PRINCIPAL_ENV}; a "
                "human identity cannot act for the worker."
            ),
        )

    principal = _service_principal_from_row(row)
    return require_service_capability(principal)


def bind_service_actor(
    session: object | None,
    actor: AuthenticatedPrincipal | None,
) -> ServiceAuthority:
    """Re-authorise one headless attempt and bind it to the persisted service identity.

    每次提供方调用前重新读取持久化身份：停用、撤销或降权立即生效，即使调用方仍持有
    扫描阶段解析出的旧对象；声明的主体必须与配置的规范身份一致。

    This is the check a provider boundary runs before loading a credential or calling out. It
    never grants anything *from* ``actor``: the returned authority is resolved from the
    deployment's configured name and the persisted row, and only the caller's claim to *be*
    that identity is checked. A missing, mismatched or forged actor is refused so an
    unauthorised or unattributed process cannot spend a provider credential.

    Args:
        session: Open runtime-database session, or ``None`` when no database is configured.
        actor: The principal the attempt claims to run as, as the caller resolved it earlier.

    Returns:
        A granted :class:`ServiceAuthority` naming the persisted service principal, or a
        refusal code for the caller to report.
    """

    authority = resolve_service_authority(session)
    if not authority.granted or authority.principal is None:
        return authority
    canonical = authority.principal
    if actor is None:
        return ServiceAuthority(
            principal=None,
            refusal=SERVICE_AUTHORITY_ACTOR_MISSING,
            detail=(
                "The attempt carried no acting principal. A provider call runs only as the "
                f"identity named by {SERVICE_PRINCIPAL_ENV} ({canonical.name!r}), so the "
                "caller must pass the identity it resolved instead of invoking a provider "
                "with nobody attributed to it."
            ),
        )
    claimed_id = getattr(actor, "principal_id", None)
    claimed_name = getattr(actor, "name", None)
    claimed_type = getattr(actor, "principal_type", None)
    if (
        claimed_id != canonical.principal_id
        or claimed_name != canonical.name
        or claimed_type != canonical.principal_type
    ):
        return ServiceAuthority(
            principal=None,
            refusal=SERVICE_AUTHORITY_ACTOR_MISMATCH,
            detail=(
                f"The attempt claims to run as {claimed_name!r} ({claimed_id!r}, "
                f"{claimed_type!r}), but this deployment's service identity is "
                f"{canonical.name!r} ({canonical.principal_id}, {canonical.principal_type}). "
                "The configured identity is re-read from the database and only it may act."
            ),
        )
    return authority


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
