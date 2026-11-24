"""Desk edits as market events (M5b): contracts, hedge bands and approved assumptions.

A contract's terms, book, retirement or hedge band changing publishes one
``contract.changed`` revision, and only the evaluators that read the contract re-run; the
same terms saved again publish nothing; a return to earlier terms is news. Approving an
assumption version publishes ``assumption.changed`` for the keys whose value moved (or that
the version no longer sets), not for the keys it repeats. Payloads carry digests only.
"""

from __future__ import annotations

import importlib.util
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.application import market_event_capture as capture
from eurogas_nexus.application import market_events as outbox
from eurogas_nexus.application.opportunities.service import run_evaluation
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import (
    AssumptionSetVersionRecord,
    HedgeApprovalRecord,
    MarketEventRecord,
    OpportunityEvaluationRecord,
    UpstreamResourceContractRecord,
)
from eurogas_nexus.db.repositories.commercial_assumptions import (
    approve_assumption_version,
    create_assumption_version,
)
from eurogas_nexus.domain.valuation.assumptions import AssumptionValue

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 11, 17, 9, 42, tzinfo=UTC)
CONTRACT = "demo-haldor-24"
SET_ID = "aset-demo-desk"


@pytest.fixture()
def engine(tmp_path, monkeypatch):
    url = f"sqlite+pysqlite:///{(tmp_path / 'desk.sqlite').as_posix()}"
    engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    return engine


def _seed_capture_and_deliver(session) -> None:
    """The demo desk, evaluated, with its first capture delivered: every desk figure is held
    as revision 1, so what follows measures changes only."""

    spec = importlib.util.spec_from_file_location(
        "seed_demo_desk_desk_events", ROOT / "scripts" / "demo" / "seed_demo_desk.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.seed(session, NOW, history_days=5)
    session.commit()
    run_evaluation(session, trigger="on_demand", triggered_by="t", now_utc=NOW, demo_desk=True)
    session.commit()
    first = capture.capture(session, now_utc=NOW, kinds=("contracts", "assumptions"))
    session.commit()
    assert first["published"]["contract.changed"] >= 1
    assert first["published"]["assumption.changed"] >= 3  # the demo storage costs and more
    outbox.process(session, "opportunities", now_utc=NOW, limit=5000)
    session.commit()


def _events(session, key):
    return (
        session.query(MarketEventRecord)
        .filter(MarketEventRecord.subject_key == key)
        .order_by(MarketEventRecord.revision)
        .all()
    )


def _deliver(session, at):
    result = outbox.process(session, "opportunities", now_utc=at)
    session.commit()
    return result


# ------------------------------------------------------------------------------ builders


def test_a_contract_digest_ignores_who_saved_it_and_carries_no_term(engine) -> None:
    with Session(engine) as session:
        session.add(
            UpstreamResourceContractRecord(
                contract_id="c-1",
                contract_name="Test supply",
                resource_type="pipeline",
                delivery_point_name="TTF",
                gas_year="2026/27",
                delivery_quantity_mwh_per_day=1000.0,
                contract_price_gbp_mwh=30.0,
                contract_price_currency="EUR",
                settlement_frequency="monthly",
                upstream_payment_lag_days=20,
                screen_sale_cash_lag_days=2,
                delivery_tolerance_pct=5.0,
                nomination_tolerance_pct=5.0,
                tolerance_risk_allowance_gbp_mwh=0.0,
                annual_financing_rate_pct=5.0,
                owned_entry_capacity_mwh_per_day=0.0,
                owned_exit_capacity_mwh_per_day=0.0,
                allowed_exit_points=[],
                eligible_sale_modes=[],
                notes="",
                created_at_utc=NOW,
                updated_at_utc=NOW,
            )
        )
        session.flush()
        row = session.get(UpstreamResourceContractRecord, "c-1")
        first = capture.contract_event(row, now_utc=NOW)
        assert first.subject_key == "contract:c-1" and first.dependency_keys == ("contract:c-1",)
        assert set(first.payload) == {"contract_id", "retired", "terms_digest"}
        assert "1000" not in str(first.payload)

        row.updated_at_utc = NOW + timedelta(hours=1)  # saved again, same terms
        assert capture.contract_event(row, now_utc=NOW).content_hash == first.content_hash
        row.delivery_quantity_mwh_per_day = 1200.0
        moved = capture.contract_event(row, now_utc=NOW)
        assert moved.event_key == first.event_key and moved.content_hash != first.content_hash
        band = HedgeApprovalRecord(
            contract_id="c-1",
            min_hedge_ratio_pct=40.0,
            max_hedge_ratio_pct=80.0,
            updated_by="risk",
            updated_at_utc=NOW,
        )
        assert capture.contract_event(row, hedge=band, now_utc=NOW).content_hash != (
            moved.content_hash
        )


# ------------------------------------------------------------------------------ contracts


def test_a_contract_edit_reaches_only_its_readers_and_a_return_to_old_terms_is_news(
    engine,
) -> None:
    with Session(engine) as session:
        _seed_capture_and_deliver(session)
        key = f"contract:{CONTRACT}"
        assert [event.revision for event in _events(session, key)] == [1]

        # Saved again with the same terms: nothing.
        row = session.get(UpstreamResourceContractRecord, CONTRACT)
        row.updated_at_utc = NOW + timedelta(minutes=1)
        again = capture.capture_desk(session, contract_ids=[CONTRACT], now_utc=NOW)
        assert again["published"] == {} and again["unchanged"] == 1

        original = row.delivery_quantity_mwh_per_day
        row.delivery_quantity_mwh_per_day = original * 2
        edit_at = NOW + timedelta(minutes=2)
        edited = capture.capture_desk(session, contract_ids=[CONTRACT], now_utc=edit_at)
        session.commit()
        assert edited["published"] == {"contract.changed": 1}
        result = _deliver(session, edit_at)
        assert result["result"]["dependency_keys"] == [key]
        assert result["result"]["evaluators"] == ["hedge_gap"]
        run = session.get(OpportunityEvaluationRecord, result["result"]["evaluation_id"])
        assert run.trigger == "outbox" and set(run.evaluators_json) == {"hedge_gap"}

        # The desk puts the old quantity back: that is a change too.
        row.delivery_quantity_mwh_per_day = original
        back_at = NOW + timedelta(minutes=3)
        back = capture.capture_desk(session, contract_ids=[CONTRACT], now_utc=back_at)
        session.commit()
        assert back["published"] == {"contract.changed": 1}
        revisions = _events(session, key)
        assert [event.revision for event in revisions] == [1, 2, 3]
        assert revisions[2].content_hash == revisions[0].content_hash
        assert _deliver(session, back_at)["result"]["evaluators"] == ["hedge_gap"]


def test_a_hedge_band_and_a_retirement_are_contract_changes(engine) -> None:
    with Session(engine) as session:
        _seed_capture_and_deliver(session)
        key = f"contract:{CONTRACT}"
        band = session.get(HedgeApprovalRecord, CONTRACT)
        if band is None:
            band = HedgeApprovalRecord(contract_id=CONTRACT, updated_by="risk", updated_at_utc=NOW)
            session.add(band)
        band.max_hedge_ratio_pct = 55.0
        moved = capture.capture_desk(session, contract_ids=[CONTRACT], now_utc=NOW)
        assert moved["published"] == {"contract.changed": 1}

        row = session.get(UpstreamResourceContractRecord, CONTRACT)
        row.retired_at_utc, row.retired_by, row.retire_reason = NOW, "desk", "ended early"
        retired = capture.capture_desk(
            session, contract_ids=[CONTRACT], now_utc=NOW + timedelta(seconds=1)
        )
        session.commit()
        assert retired["published"] == {"contract.changed": 1}
        latest = _events(session, key)[-1]
        assert latest.revision == 3 and latest.payload_json["retired"] is True
        assert latest.priority == 1


# ---------------------------------------------------------------------------- assumptions


def _new_version(session, values, *, at):
    created = create_assumption_version(
        session,
        set_id=SET_ID,
        values=values,
        effective_from=date(2026, 11, 1),
        effective_to=None,
        note="test",
        actor="desk.trader",
        now_utc=at,
    )
    del created
    number = max(
        row.version
        for row in session.query(AssumptionSetVersionRecord).filter(
            AssumptionSetVersionRecord.set_id == SET_ID
        )
    )
    approve_assumption_version(
        session, set_id=SET_ID, version=number, actor="desk.risk", now_utc=at
    )


def _storage(capacity="2.80"):
    return [
        AssumptionValue("storage.capacity_fee", Decimal(capacity), "EUR/MWh", "EUR"),
        AssumptionValue("storage.injection_fee", Decimal("0.50"), "EUR/MWh", "EUR"),
        AssumptionValue("storage.withdrawal_fee", Decimal("0.50"), "EUR/MWh", "EUR"),
    ]


def test_an_approved_version_publishes_only_the_keys_whose_value_moved(engine) -> None:
    with Session(engine) as session:
        _seed_capture_and_deliver(session)
        at = NOW + timedelta(minutes=5)
        # The desk sets its own long discount and repeats the storage costs.
        discount = AssumptionValue("balancing.long_discount", Decimal("1.5"), "EUR/MWh", "EUR")
        _new_version(session, [*_storage(), discount], at=at)
        published = capture.capture_desk(session, set_ids=[SET_ID], now_utc=at)
        session.commit()
        assert published["published"] == {"assumption.changed": 1}
        assert published["unchanged"] == 3
        event = _events(session, "assumption:balancing.long_discount")[-1]
        assert event.payload_json["state"] == "set" and "1.5" not in str(event.payload_json)
        result = _deliver(session, at)
        assert result["result"]["evaluators"] == ["sell_down"]

        # A later version drops the discount and moves one fee: two keys change.
        later = at + timedelta(minutes=5)
        _new_version(session, _storage(capacity="3.10"), at=later)
        changed = capture.capture_desk(session, set_ids=[SET_ID], now_utc=later)
        session.commit()
        assert changed["published"] == {"assumption.changed": 2}
        dropped = _events(session, "assumption:balancing.long_discount")[-1]
        assert dropped.revision == 2 and dropped.payload_json["state"] == "unset"
        assert _events(session, "assumption:storage.capacity_fee")[-1].revision == 2


def test_the_desk_tables_captured_again_repeat_nothing(engine) -> None:
    with Session(engine) as session:
        _seed_capture_and_deliver(session)
        again = capture.capture(
            session, now_utc=NOW + timedelta(minutes=1), kinds=("contracts", "assumptions")
        )
        assert again["published"] == {} and again["unchanged"] == again["examined"] > 0
