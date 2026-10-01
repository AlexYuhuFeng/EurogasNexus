"""PostgreSQL-authoritative contract-revision capture semantics.

The SQLite fixture tests prove the repository-level capture against a
throw-away database; these run the same repository capture against the
configured runtime store (CI: the PostgreSQL 16 service) because the
per-contract revision numbering guarantee - "two concurrent captures cannot
allocate the same number" - and the stale-identity-map refresh are properties
of the database read and row lock, not of the process. Like the other
integration tests, this module is skipped unless a PostgreSQL URL and the
explicit capture-test opt-in are configured. These tests commit synthetic rows
and must target a disposable test database, never a developer's running desk
database. They run no migrations; the CI runner applies the chain before the
tests.
"""

from __future__ import annotations

import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.db.models import (
    AuditEventRecord,
    UpstreamContractRevisionRecord,
    UpstreamResourceContractRecord,
)
from eurogas_nexus.db.repositories.route_cost import (
    CONTRACT_REVISION_ALREADY_CAPTURED,
    CONTRACT_REVISION_CAPTURED,
    capture_upstream_contract_revision,
    upsert_upstream_contract,
)

pytestmark = pytest.mark.skipif(
    not os.environ.get("RUNTIME_STORE_DATABASE_URL", "").startswith("postgresql")
    or os.environ.get("EUROGAS_NEXUS_CONTRACT_REVISION_INTEGRATION_TEST") != "1",
    reason="Requires disposable PostgreSQL and explicit opt-in; use run_postgres_ci.sh",
)

_NOW = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)


def _engine():
    return create_engine(os.environ["RUNTIME_STORE_DATABASE_URL"], future=True)


def _contract_payload(contract_id: str, *, price: float = 29.75) -> dict[str, object]:
    return {
        "contract_id": contract_id,
        "contract_name": f"Integration contract {contract_id}",
        "resource_type": "PIPELINE_IMPORT",
        "delivery_point_name": "TTF",
        "gas_year": "2025+",
        "delivery_quantity_mwh_per_day": 125.5,
        "contract_price_gbp_mwh": price,
        "settlement_frequency": "monthly",
        "upstream_payment_lag_days": 20,
        "screen_sale_cash_lag_days": 1,
        "delivery_tolerance_pct": 2.0,
        "nomination_tolerance_pct": 1.0,
        "tolerance_risk_allowance_gbp_mwh": 0.1,
        "annual_financing_rate_pct": 6.0,
        "owned_entry_capacity_mwh_per_day": None,
        "owned_exit_capacity_mwh_per_day": None,
        "allowed_exit_points": ["NBP", "TTF"],
        "eligible_sale_modes": ["TARGET_MARKET_SALE", "LOCAL_MARKET_SALE"],
        "notes": json.dumps({"variable_cost_gbp_mwh": 0.75}, sort_keys=True),
    }


def _seed_contract(engine, contract_id: str, *, price: float = 29.75) -> None:
    with Session(engine) as session:
        upsert_upstream_contract(session, _contract_payload(contract_id, price=price))
        session.commit()


def _capture(engine, contract_id: str, *, actor: str, at: datetime) -> dict:
    """Capture in its own transaction and return plain values after commit."""

    with Session(engine) as session:
        result = capture_upstream_contract_revision(
            session, contract_id, recorded_by=actor, recorded_at_utc=at
        )
        session.commit()
        if result.revision is None:
            return {
                "outcome": result.outcome,
                "refusal_code": result.refusal_code,
                "revision_id": None,
                "revision_number": None,
                "content_hash": None,
                "recorded_by": None,
                "recorded_at_utc": None,
            }
        return {
            "outcome": result.outcome,
            "refusal_code": None,
            "revision_id": result.revision.contract_revision_id,
            "revision_number": result.revision.revision_number,
            "content_hash": result.revision.content_hash,
            "recorded_by": result.revision.recorded_by,
            "recorded_at_utc": result.revision.recorded_at_utc,
        }


def test_repeat_capture_is_idempotent_and_the_changed_row_gets_the_next_number() -> None:
    engine = _engine()
    contract_id = f"contract-it-{uuid4().hex[:12]}"
    _seed_contract(engine, contract_id)

    first = _capture(engine, contract_id, actor="trader-a", at=_NOW)
    assert first["outcome"] == CONTRACT_REVISION_CAPTURED
    assert first["revision_number"] == 1

    repeat = _capture(
        engine, contract_id, actor="trader-b", at=_NOW + timedelta(hours=2)
    )
    assert repeat["outcome"] == CONTRACT_REVISION_ALREADY_CAPTURED
    assert repeat["revision_id"] == first["revision_id"]
    assert repeat["recorded_by"] == "trader-a"
    assert repeat["recorded_at_utc"] == _NOW

    _seed_contract(engine, contract_id, price=31.5)
    changed = _capture(
        engine, contract_id, actor="trader-c", at=_NOW + timedelta(days=1)
    )
    assert changed["outcome"] == CONTRACT_REVISION_CAPTURED
    assert changed["revision_number"] == 2
    assert changed["content_hash"] != first["content_hash"]

    with Session(engine) as session:
        revisions = (
            session.query(UpstreamContractRevisionRecord)
            .filter(UpstreamContractRevisionRecord.contract_id == contract_id)
            .order_by(UpstreamContractRevisionRecord.revision_number)
            .all()
        )
        assert [row.revision_number for row in revisions] == [1, 2]
        # Two accepted captures, one idempotent repeat: exactly two audit rows.
        audits = (
            session.query(AuditEventRecord)
            .filter(AuditEventRecord.resource == f"upstream_contract:{contract_id}")
            .count()
        )
        assert audits == 2


def test_concurrent_captures_allocate_exactly_one_first_revision() -> None:
    engine = _engine()
    contract_id = f"contract-it-{uuid4().hex[:12]}"
    _seed_contract(engine, contract_id)

    barrier = threading.Barrier(2)
    actors = {"first": "trader-a", "second": "trader-b"}

    def _run(label: str) -> dict:
        barrier.wait(timeout=10)
        return _capture(engine, contract_id, actor=actors[label], at=_NOW)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = {label: pool.submit(_run, label) for label in actors}
        results = {label: future.result(timeout=30) for label, future in futures.items()}

    outcomes = sorted(result["outcome"] for result in results.values())
    # PostgreSQL decides: both calls complete, exactly one inserted revision 1
    # and the other observes it as the identical capture.
    assert outcomes == [CONTRACT_REVISION_ALREADY_CAPTURED, CONTRACT_REVISION_CAPTURED]
    revision_ids = {result["revision_id"] for result in results.values()}
    assert len(revision_ids) == 1

    with Session(engine) as session:
        revisions = (
            session.query(UpstreamContractRevisionRecord)
            .filter(UpstreamContractRevisionRecord.contract_id == contract_id)
            .all()
        )
        assert len(revisions) == 1
        assert revisions[0].revision_number == 1


def test_capture_refreshes_a_stale_identity_map_row_before_capturing() -> None:
    engine = _engine()
    contract_id = f"contract-it-{uuid4().hex[:12]}"
    _seed_contract(engine, contract_id, price=29.75)

    with Session(engine, expire_on_commit=False) as stale_session:
        loaded = stale_session.get(UpstreamResourceContractRecord, contract_id)
        assert loaded is not None
        assert loaded.contract_price_gbp_mwh == 29.75
        # End the read transaction without expiring the instance: the identity
        # map now holds a row another transaction is about to change.
        stale_session.commit()

        _seed_contract(engine, contract_id, price=31.5)

        result = capture_upstream_contract_revision(
            stale_session, contract_id, recorded_by="trader-a", recorded_at_utc=_NOW
        )
        assert result.outcome == CONTRACT_REVISION_CAPTURED
        assert result.revision is not None
        captured_price = json.loads(result.revision.snapshot_json)[
            "contract_price_gbp_mwh"
        ]
        stale_session.commit()

    # The FOR UPDATE select must have re-read the committed row, not captured
    # the identity-map instance the session loaded before that commit.
    assert captured_price == "31.5"
