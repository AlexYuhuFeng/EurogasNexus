"""CR-09 data-operations baseline benchmark.

Requires the configured runtime PostgreSQL store. Measures scheduler scan,
claim, freshness evaluation, issue read, and entitlement-filter overhead for
the registered source surface. No performance target is set before baseline.
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime

from eurogas_nexus.db.repositories import dataops as dataops_repository
from eurogas_nexus.db.session import get_session_factory, resolve_database_url
from eurogas_nexus.domain.dataops.entitlement import filter_rows_for_principal
from eurogas_nexus.domain.dataops.freshness import FreshnessEvidence, evaluate_source_freshness
from eurogas_nexus.domain.dataops.registry import source_definitions
from eurogas_nexus.security.identity import legacy_public_token_principal


def _measure(name: str, operation) -> float:
    started = time.perf_counter()
    operation()
    return round(time.perf_counter() - started, 6)


def main() -> int:
    if resolve_database_url() is None:
        print(json.dumps({"error": "database_url_missing"}))
        return 2

    definitions = source_definitions()
    now = datetime.now(UTC)
    session_factory = get_session_factory()
    results: dict[str, float] = {}
    with session_factory() as session:
        dataops_repository.reconcile_source_runtime_states(
            session, definitions, now_utc=now
        )
        session.commit()

    with session_factory() as session:
        results["scheduler_scan_seconds"] = _measure(
            "scheduler_scan",
            lambda: dataops_repository.claim_due_sources(
                session, definitions, now_utc=now, limit=10
            ),
        )
        session.rollback()
        results["freshness_24_sources_seconds"] = _measure(
            "freshness",
            lambda: [
                evaluate_source_freshness(
                    definition,
                    FreshnessEvidence(last_success_at_utc=now),
                    now_utc=now,
                )
                for definition in definitions
            ],
        )
        rows = [
            {"source_system": definition.provider}
            for definition in definitions
        ]
        results["entitlement_filter_seconds"] = _measure(
            "entitlement_filter",
            lambda: filter_rows_for_principal(
                legacy_public_token_principal(), rows
            ),
        )
    payload = {
        "engine": "dataops/1",
        "registered_sources": len(definitions),
        "results_seconds": results,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
