"""Who a calculation runs for: a person's request, or the firm under a service identity.

Business calculations (positions, credit, mandates) read data the caller is entitled to:
licensed quotes by data scope, screen orders by strategy visibility, books by portfolio
scope. A ``Caller`` carries that identity explicitly, so the same calculation serves an API
request and a headless worker (monitoring) without a fake HTTP request. Book scope still
comes from :mod:`eurogas_nexus.security.portfolio_scope`, which is unset outside a request,
so a worker sees every book.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from eurogas_nexus.security.identity import (
    AuthenticatedPrincipal,
    Role,
    legacy_public_token_principal,
)

#: A firm-wide principal for headless calculations when no service identity is configured.
#: It sees every book, and only the licensed families the firm may use for automated
#: calculation (a current NON_DISPLAY licence in the register).
FIRM_PRINCIPAL_ID = "system:firm-calculation"
NON_DISPLAY_USES = frozenset({"NON_DISPLAY", "DISPLAY_AND_NON_DISPLAY"})


@dataclass(frozen=True)
class Caller:
    """The principal a calculation runs for."""

    principal: AuthenticatedPrincipal

    @property
    def principal_id(self) -> str | None:
        return getattr(self.principal, "principal_id", None)


def caller_of(who: Any) -> Caller:
    """A ``Caller`` from an API request (its attached identity) or an existing caller."""

    if isinstance(who, Caller):
        return who
    # The identity dependency attaches the principal to the request (as current_principal
    # reads it); a request without one is the static-token operator.
    return Caller(getattr(who.state, "identity", None) or legacy_public_token_principal())


def firm_caller(principal: AuthenticatedPrincipal | None = None, session=None) -> Caller:
    """The caller a worker uses: the configured service principal, else a firm-wide one.

    The firm-wide caller's data scopes are every book plus the source families the licence
    register holds a current non-display licence for (automated risk calculation is
    non-display use); with demo marks on, the demo family too.
    """

    if principal is not None:
        return Caller(principal)
    return Caller(
        AuthenticatedPrincipal(
            principal_id=FIRM_PRINCIPAL_ID,
            name="firm calculation",
            principal_type="SERVICE",
            role=Role.VIEWER.value,
            status="ACTIVE",
            data_scopes=("BOOKS:*", *non_display_families(session)),
            roles=(Role.VIEWER.value,),
        )
    )


def non_display_families(session, today: date | None = None) -> tuple[str, ...]:
    """Families with a current non-display licence, and ``DEMO`` when demo marks are on."""

    from eurogas_nexus.core.config import demo_marks_allowed

    families: set[str] = {"DEMO"} if demo_marks_allowed() else set()
    if session is not None:
        from eurogas_nexus.db.models import MarketDataLicenceRecord

        day = today or datetime.now(UTC).date()
        for row in session.query(MarketDataLicenceRecord).all():
            current = row.valid_from <= day and (row.valid_to is None or row.valid_to >= day)
            if current and str(row.licensed_use).upper() in NON_DISPLAY_USES:
                families.add(row.source_family)
    return tuple(sorted(families))
