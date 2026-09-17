"""Architecture V2 capability catalogue and experience profile.

Architecture V2 separates five things that were previously conflated
(``docs/engineering/Architecture-V2/06_IDENTITY_ACCESS_CONTROL_PLANE.md``):

``identity + capability grants + scope + data entitlements + constraints``
``    -> effective access``
``effective access + functional assignments + selected work mode + preferences``
``    -> experience composition``

This module implements the middle of that model for the current repository:

- :class:`Capability` is the V2 capability vocabulary, each entry bound to the
  fine-grained :class:`~eurogas_nexus.security.authorization.Permission` values
  that already exist. The binding is derived, never invented: a capability is
  available only when the principal's role-derived permissions provide it, so
  **a capability can never exceed the role model** (the second equation never
  creates permissions).
- :class:`FunctionalAssignment` and :class:`WorkMode` are *composition* inputs.
  They describe which work a person does and which surface composition suits it.
  They grant nothing: :data:`EXPERIENCE_PROFILE_GRANTS_AUTHORITY` is ``False``
  and :func:`profile_stays_within_role_permissions` proves it for one principal.
- :class:`ExperienceProfile` is the safe composition contract returned to the
  client. It carries capability *names* the caller already holds, plus an honest
  statement of the scope kinds the backend cannot yet express (organisation,
  portfolio) so the client never invents them.

Backend enforcement remains authoritative: every API call is re-authorised
server-side, and this profile is never consulted to allow or deny anything.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from eurogas_nexus.security.authorization import (
    Permission,
    permissions_for_principal,
)
from eurogas_nexus.security.identity import AuthenticatedPrincipal


class Capability(StrEnum):
    """V2 capability vocabulary reachable in this repository today.

    Names follow ``06_IDENTITY_ACCESS_CONTROL_PLANE.md`` section 3. A capability
    that has no implementation yet is deliberately absent rather than declared
    with nothing behind it.
    """

    IDENTITY_SELF_READ = "identity.self.read"

    MARKET_READ = "market.read"

    PORTFOLIO_READ = "portfolio.read"
    PORTFOLIO_ASSUMPTION_WRITE = "portfolio.assumption.write"

    SCENARIO_DESIGN = "scenario.design"
    OPTIMIZATION_RUN = "optimization.run"

    STRATEGY_READ = "strategy.read"
    STRATEGY_DESIGN = "strategy.design"
    STRATEGY_EDIT = "strategy.edit"
    STRATEGY_FREEZE = "strategy.freeze"
    STRATEGY_RETIRE = "strategy.retire"
    STRATEGY_SHADOW_OPERATE = "strategy.shadow.operate"

    DECISION_EVIDENCE_READ = "decision.evidence.read"
    DECISION_REVIEW = "decision.review"

    RESEARCH_QUERY = "research.query"

    AGENT_CAPABILITY_READ = "agent.capability.read"
    AGENT_CAPABILITY_INVOKE = "agent.capability.invoke"
    AGENT_RUN_READ = "agent.run.read"
    AGENT_RESEARCH_RUN = "agent.research.run"

    PROVIDER_CONNECTION_VIEW = "provider.connection.view"
    PROVIDER_INGESTION_OPERATE = "provider.ingestion.operate"
    PROVIDER_BACKFILL_OPERATE = "provider.backfill.operate"
    PROVIDER_CREDENTIAL_MANAGE = "provider.credential.manage"
    PROVIDER_CERTIFICATION_MANAGE = "provider.certification.manage"

    RUNTIME_READ = "runtime.read"

    ACCESS_READ = "access.read"
    ACCESS_MANAGE = "access.manage"
    API_KEYS_MANAGE = "api_keys.manage"
    AUDIT_READ = "audit.read"


# Capability -> the fine-grained permissions that provide it. A capability is
# available when the principal holds at least one of its source permissions, and
# every source permission is itself role-derived, so the mapping cannot widen
# authority beyond ``ROLE_PERMISSIONS``.
CAPABILITY_PERMISSIONS: dict[Capability, frozenset[Permission]] = {
    Capability.IDENTITY_SELF_READ: frozenset({Permission.ME_READ}),
    Capability.MARKET_READ: frozenset({Permission.MARKET_READ}),
    Capability.PORTFOLIO_READ: frozenset({Permission.PORTFOLIO_READ}),
    Capability.PORTFOLIO_ASSUMPTION_WRITE: frozenset({Permission.PORTFOLIO_WRITE}),
    Capability.SCENARIO_DESIGN: frozenset({Permission.SCENARIO_CREATE}),
    Capability.OPTIMIZATION_RUN: frozenset({Permission.OPTIMIZATION_RUN}),
    Capability.STRATEGY_READ: frozenset({Permission.STRATEGY_READ}),
    Capability.STRATEGY_DESIGN: frozenset({Permission.STRATEGY_CREATE}),
    Capability.STRATEGY_EDIT: frozenset({Permission.STRATEGY_EDIT}),
    Capability.STRATEGY_FREEZE: frozenset({Permission.STRATEGY_FREEZE}),
    Capability.STRATEGY_RETIRE: frozenset({Permission.STRATEGY_RETIRE}),
    Capability.STRATEGY_SHADOW_OPERATE: frozenset({Permission.STRATEGY_SHADOW_MANAGE}),
    Capability.DECISION_EVIDENCE_READ: frozenset({Permission.REVIEW_READ}),
    Capability.DECISION_REVIEW: frozenset({Permission.REVIEW_RECORD}),
    Capability.RESEARCH_QUERY: frozenset({Permission.ANALYSIS_QUERY}),
    Capability.AGENT_CAPABILITY_READ: frozenset({Permission.CAPABILITY_READ}),
    Capability.AGENT_CAPABILITY_INVOKE: frozenset({Permission.CAPABILITY_INVOKE}),
    Capability.AGENT_RUN_READ: frozenset({Permission.AGENT_READ}),
    Capability.AGENT_RESEARCH_RUN: frozenset({Permission.AGENT_RESEARCH}),
    Capability.PROVIDER_CONNECTION_VIEW: frozenset({Permission.SOURCE_READ}),
    Capability.PROVIDER_INGESTION_OPERATE: frozenset({Permission.SOURCE_RUN}),
    Capability.PROVIDER_BACKFILL_OPERATE: frozenset({Permission.SOURCE_BACKFILL}),
    Capability.PROVIDER_CREDENTIAL_MANAGE: frozenset({Permission.SOURCE_CREDENTIALS_WRITE}),
    Capability.PROVIDER_CERTIFICATION_MANAGE: frozenset(
        {Permission.SOURCE_CERTIFICATION_MANAGE}
    ),
    Capability.RUNTIME_READ: frozenset({Permission.RUNTIME_READ}),
    Capability.ACCESS_READ: frozenset({Permission.IDENTITY_READ}),
    Capability.ACCESS_MANAGE: frozenset({Permission.IDENTITY_MANAGE}),
    Capability.API_KEYS_MANAGE: frozenset({Permission.API_KEYS_MANAGE}),
    Capability.AUDIT_READ: frozenset({Permission.AUDIT_READ}),
}

# Capabilities that read or write commercial data (prices, positions, contract
# terms, strategy parameters, PnL, decision evidence). Platform administration
# does not imply any of these: "no ADMIN sees everything" shortcut
# (06_IDENTITY_ACCESS_CONTROL_PLANE.md section 7).
COMMERCIAL_CAPABILITIES: frozenset[Capability] = frozenset(
    {
        Capability.MARKET_READ,
        Capability.PORTFOLIO_READ,
        Capability.PORTFOLIO_ASSUMPTION_WRITE,
        Capability.SCENARIO_DESIGN,
        Capability.OPTIMIZATION_RUN,
        Capability.STRATEGY_READ,
        Capability.STRATEGY_DESIGN,
        Capability.STRATEGY_EDIT,
        Capability.STRATEGY_FREEZE,
        Capability.STRATEGY_RETIRE,
        Capability.STRATEGY_SHADOW_OPERATE,
        Capability.DECISION_EVIDENCE_READ,
        Capability.DECISION_REVIEW,
        Capability.RESEARCH_QUERY,
        Capability.AGENT_CAPABILITY_INVOKE,
        Capability.AGENT_RESEARCH_RUN,
    }
)

# Capabilities that operate the platform rather than read the market. A platform
# administrator holds these without holding any commercial capability.
PLATFORM_ADMINISTRATION_CAPABILITIES: frozenset[Capability] = frozenset(
    {
        Capability.ACCESS_READ,
        Capability.ACCESS_MANAGE,
        Capability.API_KEYS_MANAGE,
        Capability.AUDIT_READ,
        Capability.PROVIDER_CONNECTION_VIEW,
        Capability.PROVIDER_INGESTION_OPERATE,
        Capability.PROVIDER_BACKFILL_OPERATE,
        Capability.PROVIDER_CREDENTIAL_MANAGE,
        Capability.PROVIDER_CERTIFICATION_MANAGE,
        Capability.RUNTIME_READ,
        Capability.AGENT_CAPABILITY_READ,
        Capability.IDENTITY_SELF_READ,
    }
)


class FunctionalAssignment(StrEnum):
    """What a person does. Overlapping by design: nobody holds exactly one.

    ``06_IDENTITY_ACCESS_CONTROL_PLANE.md`` section 2 forbids modelling these as
    mutually exclusive personas, so the set is derived from capabilities and any
    combination is valid.
    """

    TRADER = "TRADER"
    HQ_BUSINESS_ANALYST = "HQ_BUSINESS_ANALYST"
    REVIEWER_MANAGEMENT = "REVIEWER_MANAGEMENT"
    QUANT_RESEARCHER = "QUANT_RESEARCHER"
    DATA_OPERATOR = "DATA_OPERATOR"
    PLATFORM_ADMINISTRATOR = "PLATFORM_ADMINISTRATOR"


class WorkMode(StrEnum):
    """Composition modes from ``04_PRODUCT_EXPERIENCE_ARCHITECTURE.md`` section 9.

    A mode changes information composition only. It never changes authority.
    """

    TRADING_ANALYSIS = "TRADING_ANALYSIS"
    PORTFOLIO_OVERSIGHT = "PORTFOLIO_OVERSIGHT"
    RESEARCH = "RESEARCH"
    REVIEW = "REVIEW"
    ADMINISTRATION = "ADMINISTRATION"


ASSIGNMENT_CAPABILITIES: dict[FunctionalAssignment, frozenset[Capability]] = {
    FunctionalAssignment.TRADER: frozenset(
        {
            Capability.MARKET_READ,
            Capability.PORTFOLIO_READ,
            Capability.OPTIMIZATION_RUN,
        }
    ),
    FunctionalAssignment.HQ_BUSINESS_ANALYST: frozenset(
        {
            Capability.PORTFOLIO_READ,
            Capability.DECISION_EVIDENCE_READ,
        }
    ),
    FunctionalAssignment.REVIEWER_MANAGEMENT: frozenset({Capability.DECISION_REVIEW}),
    FunctionalAssignment.QUANT_RESEARCHER: frozenset(
        {
            Capability.STRATEGY_DESIGN,
            Capability.STRATEGY_FREEZE,
            Capability.AGENT_RESEARCH_RUN,
        }
    ),
    FunctionalAssignment.DATA_OPERATOR: frozenset({Capability.PROVIDER_INGESTION_OPERATE}),
    FunctionalAssignment.PLATFORM_ADMINISTRATOR: frozenset({Capability.ACCESS_MANAGE}),
}

WORK_MODE_CAPABILITIES: dict[WorkMode, frozenset[Capability]] = {
    WorkMode.TRADING_ANALYSIS: frozenset(
        {
            Capability.MARKET_READ,
            Capability.PORTFOLIO_READ,
            Capability.OPTIMIZATION_RUN,
        }
    ),
    WorkMode.PORTFOLIO_OVERSIGHT: frozenset(
        {
            Capability.PORTFOLIO_READ,
            Capability.DECISION_EVIDENCE_READ,
        }
    ),
    WorkMode.RESEARCH: frozenset(
        {
            Capability.STRATEGY_READ,
            Capability.STRATEGY_DESIGN,
        }
    ),
    WorkMode.REVIEW: frozenset(
        {
            Capability.DECISION_EVIDENCE_READ,
            Capability.DECISION_REVIEW,
        }
    ),
    WorkMode.ADMINISTRATION: frozenset(
        {
            Capability.ACCESS_MANAGE,
            Capability.PROVIDER_CONNECTION_VIEW,
            Capability.RUNTIME_READ,
        }
    ),
}

# Fixed priority so ``default_work_mode`` is deterministic for a given principal.
WORK_MODE_PRIORITY: tuple[WorkMode, ...] = (
    WorkMode.TRADING_ANALYSIS,
    WorkMode.PORTFOLIO_OVERSIGHT,
    WorkMode.REVIEW,
    WorkMode.RESEARCH,
    WorkMode.ADMINISTRATION,
)

# Scope kinds Architecture V2 defines. Only ``DATA`` is expressible in the
# current repository (``principal.data_scopes``); the others are declared here so
# the profile can report them as unsupported instead of pretending they exist.
SUPPORTED_SCOPE_KINDS: frozenset[str] = frozenset({"DATA"})
UNSUPPORTED_SCOPE_KINDS: tuple[str, ...] = ("ORGANIZATION", "PORTFOLIO", "MARKET", "REGION")

# The second equation never creates permissions. Asserted by the focused tests
# and by ``profile_stays_within_role_permissions``.
EXPERIENCE_PROFILE_GRANTS_AUTHORITY = False


def capabilities_for_principal(principal: AuthenticatedPrincipal) -> frozenset[Capability]:
    """Capabilities the principal actually holds, derived from its permissions."""

    permissions = permissions_for_principal(principal)
    return frozenset(
        capability
        for capability, sources in CAPABILITY_PERMISSIONS.items()
        if permissions & sources
    )


def commercial_capabilities_for_principal(
    principal: AuthenticatedPrincipal,
) -> frozenset[Capability]:
    """The commercial-data subset of a principal's capabilities (may be empty)."""

    return capabilities_for_principal(principal) & COMMERCIAL_CAPABILITIES


def functional_assignments_for(
    capabilities: frozenset[Capability],
) -> tuple[FunctionalAssignment, ...]:
    """Assignments whose capability requirement the principal fully satisfies."""

    ordered = sorted(FunctionalAssignment, key=lambda item: item.value)
    return tuple(
        assignment
        for assignment in ordered
        if ASSIGNMENT_CAPABILITIES[assignment] <= capabilities
    )


def available_work_modes(capabilities: frozenset[Capability]) -> tuple[WorkMode, ...]:
    """Work modes the principal may compose, in deterministic priority order."""

    available = {
        mode for mode, required in WORK_MODE_CAPABILITIES.items() if required <= capabilities
    }
    return tuple(mode for mode in WORK_MODE_PRIORITY if mode in available)


def default_work_mode(modes: tuple[WorkMode, ...]) -> WorkMode | None:
    """The first available mode in priority order, or ``None`` when none apply."""

    return modes[0] if modes else None


def scope_refs_for(principal: AuthenticatedPrincipal) -> tuple[str, ...]:
    """Scope references the current backend can express.

    Commercial source-family grants live in ``principal.data_scopes``; the
    organisation and portfolio scope kinds do not exist yet, so they are reported
    through :data:`UNSUPPORTED_SCOPE_KINDS` rather than fabricated here.
    """

    refs: list[str] = []
    for scope in principal.data_scopes or ():
        value = (scope or "").strip()
        if value:
            refs.append(f"DATA:{'ALL' if value == '*' else value}")
    return tuple(refs)


@dataclass(frozen=True, slots=True)
class ExperienceProfile:
    """Safe composition contract returned to the client."""

    principal_id: str
    role: str
    roles: tuple[str, ...]
    functional_assignments: tuple[FunctionalAssignment, ...]
    available_work_modes: tuple[WorkMode, ...]
    default_work_mode: WorkMode | None
    effective_capabilities: tuple[Capability, ...]
    commercial_capabilities: tuple[Capability, ...]
    scope_refs: tuple[str, ...]
    data_entitlement_refs: tuple[str, ...]
    unsupported_scope_kinds: tuple[str, ...]

    def to_payload(self) -> dict[str, object]:
        """JSON-ready form. Capability names only: never a secret or a raw record."""

        return {
            "principal_id": self.principal_id,
            "role": self.role,
            "roles": list(self.roles),
            "functional_assignments": [item.value for item in self.functional_assignments],
            "available_work_modes": [item.value for item in self.available_work_modes],
            "default_work_mode": (
                self.default_work_mode.value if self.default_work_mode is not None else None
            ),
            "effective_capabilities": sorted(item.value for item in self.effective_capabilities),
            "commercial_capabilities": sorted(
                item.value for item in self.commercial_capabilities
            ),
            "scope_refs": list(self.scope_refs),
            "data_entitlement_refs": list(self.data_entitlement_refs),
            "unsupported_scope_kinds": list(self.unsupported_scope_kinds),
            "work_mode_grants_authority": EXPERIENCE_PROFILE_GRANTS_AUTHORITY,
        }


def build_experience_profile(principal: AuthenticatedPrincipal) -> ExperienceProfile:
    """Compose the ExperienceProfile for one authenticated principal."""

    capabilities = capabilities_for_principal(principal)
    modes = available_work_modes(capabilities)
    return ExperienceProfile(
        principal_id=principal.principal_id,
        role=principal.role,
        roles=tuple(principal.roles or (principal.role,)),
        functional_assignments=functional_assignments_for(capabilities),
        available_work_modes=modes,
        default_work_mode=default_work_mode(modes),
        effective_capabilities=tuple(sorted(capabilities, key=lambda item: item.value)),
        commercial_capabilities=tuple(
            sorted(capabilities & COMMERCIAL_CAPABILITIES, key=lambda item: item.value)
        ),
        scope_refs=scope_refs_for(principal),
        data_entitlement_refs=tuple(
            sorted({(scope or "").strip() for scope in principal.data_scopes or () if scope})
        ),
        unsupported_scope_kinds=UNSUPPORTED_SCOPE_KINDS,
    )


def profile_stays_within_role_permissions(
    principal: AuthenticatedPrincipal,
    profile: ExperienceProfile | None = None,
) -> bool:
    """Whether a profile grants nothing the role model does not already grant.

    This is the machine-checked form of "the composition equation never creates
    permissions". It is asserted for every role in the focused tests.
    """

    resolved = profile or build_experience_profile(principal)
    permissions = permissions_for_principal(principal)
    permitted = {
        capability
        for capability, sources in CAPABILITY_PERMISSIONS.items()
        if permissions & sources
    }
    return set(resolved.effective_capabilities) <= permitted


def capability_source_permissions(capability: Capability) -> frozenset[Permission]:
    """The fine-grained permissions that provide a capability (empty if unknown)."""

    return CAPABILITY_PERMISSIONS.get(capability, frozenset())
