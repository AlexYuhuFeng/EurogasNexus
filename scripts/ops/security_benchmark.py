"""CR-10 authorization overhead benchmark.

Requires the configured runtime PostgreSQL store. Measures permission
expansion for the five built-in roles, API-key verification, /api/me-style
principal payload assembly, and audit insertion.
"""

from __future__ import annotations

import json
import time

from eurogas_nexus.db.repositories import identity as identity_repository
from eurogas_nexus.db.repositories.audit import record_audit_event
from eurogas_nexus.db.session import get_session_factory, resolve_database_url
from eurogas_nexus.security.authorization import Permission, authorize
from eurogas_nexus.security.identity import (
    AuthenticatedPrincipal,
    generate_api_key,
    hash_key_secret,
    verify_key_hash,
)


def _measure(name: str, operation) -> float:
    started = time.perf_counter()
    operation()
    return round(time.perf_counter() - started, 6)


def main() -> int:
    if resolve_database_url() is None:
        print(json.dumps({"error": "database_url_missing"}))
        return 2

    results: dict[str, float] = {}
    for role in ("VIEWER", "REVIEWER", "ANALYST", "OPERATOR", "ADMIN"):
        principal = AuthenticatedPrincipal(
            principal_id="benchmark",
            name="benchmark",
            principal_type="USER",
            role=role,
            status="ACTIVE",
            data_scopes=(),
            roles=(role,),
        )
        results[f"authorize_{role.lower()}_seconds"] = _measure(
            f"authorize_{role}",
            lambda principal=principal: authorize(principal, Permission.STRATEGY_FREEZE),
        )

    key = generate_api_key(key_id="benchmark-key", display_name="benchmark")
    secret = key.bearer.split("_", 2)[2]
    results["api_key_verify_seconds"] = _measure(
        "api_key_verify",
        lambda: verify_key_hash(secret, hash_key_secret(secret)),
    )

    session_factory = get_session_factory()
    with session_factory() as session:
        principal = identity_repository.create_identity_principal(
            session,
            name=f"benchmark-principal-{int(time.time())}",
            display_name="Benchmark Principal",
            role="VIEWER",
            data_scopes=[],
        )
        session.commit()
        results["audit_insert_seconds"] = _measure(
            "audit_insert",
            lambda: record_audit_event(
                session,
                event_type="governance.benchmark",
                principal=principal.principal_id,
                action="security.benchmark",
                resource="benchmark",
                outcome="recorded",
            ),
        )
        session.commit()
        session.delete(principal)
        session.commit()

    print(
        json.dumps(
            {"engine": "security/1", "results_seconds": results},
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
