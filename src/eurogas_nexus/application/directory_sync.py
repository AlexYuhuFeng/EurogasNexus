"""Directory-managed identities: the company's SSO directory owns who has access.

With ``EUROGAS_NEXUS_OIDC_PROVISIONING_MODE=directory`` a person who signs in through the
company SSO (OIDC or the authenticating gateway) gets a local principal on first sign-in,
active at once, and on every sign-in the principal's roles, data scopes (including
``BOOKS:`` portfolio scopes) and office are re-derived from the person's directory groups.
Joiners, movers and leavers are therefore handled in the directory, not here: removing a
person from a group removes the access at their next request.

Local administrators can still disable or lock a directory principal; that local
decision wins over the directory. Roles and scopes edited locally for a directory
principal are overwritten at the next sign-in, which is the point of the mode.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from eurogas_nexus.db.models import IdentityPrincipalRecord

ROLE_RANK = ["VIEWER", "REVIEWER", "ANALYST", "OPERATOR", "ADMIN"]
DIRECTORY_MODE = "directory"


class DirectoryAccessRefused(Exception):
    """The local principal exists but an administrator disabled or locked it."""


def access_from_groups(
    groups: list[str] | tuple[str, ...],
    role_map: dict[str, str],
    scope_map: dict[str, list[str]],
) -> tuple[list[str], list[str]]:
    """(roles, data scopes) for a set of directory groups; VIEWER when no group maps."""

    roles = sorted({role_map[g] for g in groups if g in role_map}) or ["VIEWER"]
    scopes = sorted({str(s).strip().upper() for g in groups for s in scope_map.get(g, []) if s})
    return roles, scopes


def sync_directory_principal(
    session: Session,
    *,
    issuer: str,
    subject: str,
    display_name: str,
    email: str | None,
    roles: list[str],
    scopes: list[str],
    office: str | None,
    source: str,
    now_utc: datetime | None = None,
) -> IdentityPrincipalRecord:
    """Create or update the principal for a directory identity; audits every change."""

    from eurogas_nexus.db.repositories import identity as identity_repository
    from eurogas_nexus.db.repositories.audit import record_audit_event
    from eurogas_nexus.db.repositories.security import (
        create_external_identity,
        find_external_identity,
    )

    now = now_utc or datetime.now(UTC)
    external = find_external_identity(session, issuer, subject)
    created = external is None
    if created:
        principal = identity_repository.create_identity_principal(
            session,
            # Principal names allow letters, digits and . _ @ - (CORP\\jsmith -> corp-jsmith).
            name=re.sub(r"[^A-Za-z0-9._@-]+", "-", f"{source.lower()}-{subject}").strip("-")[:64],
            display_name=display_name,
            role="VIEWER",
            principal_type="USER",
            data_scopes=scopes,
            now_utc=now,
        )
        create_external_identity(
            session,
            principal_id=principal.principal_id,
            issuer=issuer,
            subject=subject,
            provider_id=source.lower(),
            email=email,
            display_name=display_name,
            now_utc=now,
        )
    else:
        principal = session.get(IdentityPrincipalRecord, external.principal_id)
        if principal is None:
            raise DirectoryAccessRefused("directory identity is linked to a missing principal")
        if principal.status in {"DISABLED", "LOCKED"}:
            raise DirectoryAccessRefused(f"principal is {principal.status.lower()} locally")
    before = (sorted(principal.roles or []), sorted(principal.data_scopes or []), principal.office)
    principal.roles = roles
    principal.role = max(roles, key=ROLE_RANK.index)
    principal.data_scopes = scopes
    principal.office = (office or "").strip().upper()[:16] or principal.office
    principal.email = email or principal.email
    principal.display_name = display_name or principal.display_name
    principal.identity_source = source.upper()
    principal.status = "ACTIVE"
    principal.last_login_at_utc = now
    principal.updated_at_utc = now
    after = (sorted(roles), sorted(scopes), principal.office)
    if created or before != after:
        record_audit_event(
            session,
            event_type="governance.access",
            principal=principal.principal_id,
            action="access.directory.sync",
            resource=f"identity_principal:{principal.principal_id}",
            outcome="created" if created else "updated",
            severity="info",
            detail=f"roles={roles}; scopes={scopes}; office={principal.office}; source={source}",
            source_system="directory-sync",
            now_utc=now,
        )
    session.flush()
    return principal
