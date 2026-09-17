#!/usr/bin/env python
"""Seed one authenticated browser-UAT principal (development/test only).

This helper is intentionally narrow: it creates or refreshes one browser-UAT
principal used by the Playwright acceptance job. It never stores a password;
the development login credential remains an environment-only secret. The helper
is blocked outside development/test and requires the same explicit UAT-fixture
acknowledgement as the simulated-data seed.

Architecture V2 separates platform administration from commercial-data access
(``docs/engineering/Architecture-V2/06_IDENTITY_ACCESS_CONTROL_PLANE.md``
section 7), so the UAT operator holds two overlapping functional assignments:
``ADMIN`` for the control plane it exercises and ``ANALYST`` for the market,
portfolio and strategy flows the browser workflow validates. A single ADMIN
assignment would be refused commercial reads by
``eurogas_nexus.api.dependencies.commercial_access``.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

from eurogas_nexus.db.models import IdentityPrincipalRecord
from eurogas_nexus.db.repositories.identity import create_identity_principal
from eurogas_nexus.db.session import get_session_factory, resolve_database_url

UAT_ROLES = ["ADMIN", "ANALYST"]
UAT_DISPLAY_NAME = "Eurogas Browser UAT Operator"


def main() -> int:
    environment = os.getenv("EUROGAS_NEXUS_ENV", "development").strip().lower()
    if environment not in {"development", "test"}:
        print("Browser UAT identity is blocked outside development/test.")
        return 2
    if os.getenv("EUROGAS_NEXUS_UAT_FIXTURE_ALLOWED", "").strip() != "1":
        print("Set EUROGAS_NEXUS_UAT_FIXTURE_ALLOWED=1 to acknowledge UAT fixtures.")
        return 2

    database_url = resolve_database_url()
    if not database_url:
        print("Runtime DB URL missing.")
        return 2

    username = (os.getenv("EUROGAS_NEXUS_DEV_LOGIN_USERNAME") or "").strip()
    if not username:
        print("EUROGAS_NEXUS_DEV_LOGIN_USERNAME is required.")
        return 2

    now = datetime.now(UTC)
    session_factory = get_session_factory(database_url=database_url)
    with session_factory() as session:
        row = (
            session.query(IdentityPrincipalRecord)
            .filter(IdentityPrincipalRecord.name == username)
            .one_or_none()
        )
        if row is None:
            row = create_identity_principal(
                session,
                name=username,
                display_name=UAT_DISPLAY_NAME,
                role=UAT_ROLES[0],
                data_scopes=["*"],
                now_utc=now,
            )
        else:
            row.display_name = UAT_DISPLAY_NAME
        row.role = UAT_ROLES[0]
        row.roles = list(UAT_ROLES)
        row.status = "ACTIVE"
        row.data_scopes = ["*"]
        row.updated_at_utc = now
        session.flush()
        session.commit()
        principal_id = row.principal_id

    print(f"Browser UAT principal ready: {principal_id} (roles: {', '.join(UAT_ROLES)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
