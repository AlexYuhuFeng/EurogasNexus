"""The opportunity engine end to end over a runtime store (CP-08, reliability gate K.0).

- **Demo desk**: the seeded demo book produces a real hedge-gap object, marked simulated,
  whose legs reconcile and which replays from its snapshot to identical figures.
- **Public data only**: a store holding only public sources shows honest "missing" states
  and nothing simulated; a firm-entered contract and band then produce a sourced object.
- Dedupe, persistence, hysteresis, a failing evaluator (no change, one admin alert), and the
  book-scope property (no cross-book leak).
"""

from __future__ import annotations

import importlib.util
import random
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.application.caller import Caller
from eurogas_nexus.application.opportunities.listing import list_opportunities, visible_to
from eurogas_nexus.application.opportunities.service import run_evaluation
from eurogas_nexus.application.valuation_snapshot import replay_snapshot
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import (
    FxObservationRecord,
    HedgeApprovalRecord,
    MarketObservationRecord,
    OpportunityRecord,
    OpportunityVersionRecord,
    TsoTariffRecord,
    UpstreamResourceContractRecord,
)
from eurogas_nexus.domain.opportunities.controls import Thresholds
from eurogas_nexus.domain.opportunities.evaluator import EvaluationContext
from eurogas_nexus.domain.opportunities.hedge_gap import HEDGE_GAP
from eurogas_nexus.domain.opportunities.model import reconcile
from eurogas_nexus.security.identity import AuthenticatedPrincipal

SEED = Path(__file__).resolve().parents[2] / "scripts" / "demo" / "seed_demo_desk.py"
NOW = datetime(2026, 11, 17, 9, 42, tzinfo=UTC)


def _principal(scopes=("*",)) -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        principal_id="p-trader",
        name="trader",
        principal_type="USER",
        role="ANALYST",
        status="ACTIVE",
        data_scopes=tuple(scopes),
        roles=("ANALYST",),
    )


@pytest.fixture()
def store(tmp_path, monkeypatch):
    url = f"sqlite+pysqlite:///{(tmp_path / 'opp.sqlite').as_posix()}"
    engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    with Session(engine) as session:
        yield session


def _seed_demo(session) -> None:
    spec = importlib.util.spec_from_file_location("seed_demo_desk", SEED)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.seed(session, NOW, history_days=5)
    session.commit()


def _run(session, demo: bool, now=NOW):
    summary = run_evaluation(
        session,
        trigger="test",
        triggered_by="tester",
        now_utc=now,
        caller=Caller(_principal()),
        demo_desk=demo,
    )
    session.commit()
    return summary


def test_demo_desk_produces_a_reconciling_simulated_hedge_gap(store) -> None:
    _seed_demo(store)
    first = _run(store, demo=True)
    assert first["status"] == "ok" and first["evaluators"]["hedge_gap"]["candidates"] >= 1
    listed = list_opportunities(store, _principal(), now_utc=NOW)
    assert listed["lanes"]["must_act"]["total"] == 0 and listed["confirming"] >= 1  # persistence
    _run(store, demo=True)
    listed = list_opportunities(store, _principal(), now_utc=NOW)
    must = listed["lanes"]["must_act"]
    assert must["total"] >= 1
    top = must["items"][0]
    assert top["type_code"] == "G" and top["simulated"] is True
    assert top["quality"]["class"] == "simulated" and top["state"] == "indicative"
    assert "Haldor" in top["claim"] and "below the band edge" in top["claim"]
    assert listed["banner"] and listed["simulated"]
    assert top["rank"]["reason"].startswith("ranked 1st: ")
    # Every stored object reconciles: terms sum to the headline.
    for row in store.query(OpportunityRecord).all():
        version = store.get(OpportunityVersionRecord, (row.opportunity_id, row.version))
        terms = [leg for leg in version.payload_json["legs"] if leg["kind"] == "term"]
        from decimal import Decimal

        total = sum(Decimal(leg["contribution"]["value"]) for leg in terms)
        assert total == Decimal(version.payload_json["headline"]["value"])
    # The snapshot replays to identical figures.
    row = store.get(OpportunityRecord, top["opportunity_id"])
    replay = replay_snapshot(store, row.snapshot_id)
    context = EvaluationContext(NOW, Thresholds(), True)
    again = {c.key: c for c in HEDGE_GAP.evaluate(replay, context)}
    assert again[row.opp_key].headline.value == row.headline_value.normalize() or (
        again[row.opp_key].headline.value == row.headline_value
    )
    reconcile(again[row.opp_key])
    assert replay.replay_misses == []


def test_public_data_only_store_is_honest(store) -> None:
    store.add_all(
        [
            FxObservationRecord(
                observation_id="ecb-gbp",
                pair="EURGBP",
                base_currency="EUR",
                quote_currency="GBP",
                rate=0.87,
                rate_type="reference",
                value_date="2026-11-16",
                observed_at_utc=NOW - timedelta(hours=20),
                source_system="ECB",
                source_reference="ecb",
                freshness="daily",
                research_only=True,
            ),
            # ECB reference rates are also held as market observations: not a gas price.
            MarketObservationRecord(
                observation_id="ecb-gbp-obs",
                market_venue="ECB",
                product="EURGBP",
                price=0.87,
                unit="GBP per EUR",
                currency="GBP",
                period_start_utc=NOW - timedelta(days=1),
                period_end_utc=NOW,
                observed_at_utc=NOW - timedelta(hours=20),
                source_system="ECB",
                source_reference="ecb",
                freshness="daily",
                quality_score=1.0,
                research_only=True,
            ),
            TsoTariffRecord(
                tariff_id="entsog-1",
                document_id="entsog-tariffs-2026",
                country="NL",
                tso="GTS",
                market_area="NL",
                gas_year="2026/27",
                point_id="ITP-00005",
                source_point_name="Oude Statenzijl",
                direction="EXIT",
                capacity_product="MONTHLY",
                firmness="FIRM",
                tariff_value=0.0101,
                currency="EUR",
                unit="EUR/(kWh/h)/d",
                effective_from=datetime(2026, 10, 1, tzinfo=UTC),
                effective_to=None,
                tariff_status="FINAL",
                source_table="ENTSOG tariff",
                source_page=None,
                source_refs=["entsog"],
                manual_review_required=False,
                created_at_utc=NOW - timedelta(days=30),
            ),
        ]
    )
    store.commit()
    _run(store, demo=False)
    listed = list_opportunities(store, _principal(), now_utc=NOW)
    ready = listed["readiness"]
    assert ready["book"]["ready"] is False and "no contracts" in ready["book"]["missing"]
    assert ready["prices"]["ready"] is False and "entitlement" in ready["prices"]["missing"]
    assert ready["published_costs"]["transport_tariffs"] == 1
    assert listed["lanes"]["must_act"]["total"] == 0 and listed["simulated"] is False
    # The firm enters a contract and risk approves a band: a sourced object, not simulated.
    store.add(
        UpstreamResourceContractRecord(
            contract_id="norsk-2027",
            contract_name="Norsk-2027",
            resource_type="PIPELINE_IMPORT",
            delivery_point_name="TTF",
            gas_year="2026/27",
            delivery_quantity_mwh_per_day=10_000.0,
            contract_price_gbp_mwh=30.0,
            contract_price_currency="EUR",
            settlement_frequency="monthly",
            upstream_payment_lag_days=20,
            screen_sale_cash_lag_days=1,
            delivery_tolerance_pct=5.0,
            nomination_tolerance_pct=2.0,
            annual_financing_rate_pct=5.0,
            allowed_exit_points=["TTF"],
            eligible_sale_modes=["LOCAL_MARKET_SALE"],
            book_id=None,
            created_at_utc=NOW,
            updated_at_utc=NOW,
        )
    )
    store.add(
        HedgeApprovalRecord(
            contract_id="norsk-2027",
            min_hedge_ratio_pct=60.0,
            max_hedge_ratio_pct=80.0,
            approval_ref="RC-12",
            valid_until=date(2027, 9, 30),
            updated_by="risk",
            updated_at_utc=NOW,
        )
    )
    store.commit()
    _run(store, demo=False)
    _run(store, demo=False)
    listed = list_opportunities(store, _principal(), now_utc=NOW)
    items = listed["lanes"]["must_act"]["items"]
    assert items and all(item["simulated"] is False for item in items)
    assert {item["quality"]["class"] for item in items} == {"sourced"}
    # One item per contract; its months inside, largest first.
    months = [member for item in items for member in item["group"]["members"]]
    jan = next(member for member in months if member["period"] == "2027-01")
    # 10,000 MWh/d x 31 d = 310,000 MWh; 60 % = 186,000 MWh; no cover -> gap 186,000 MWh.
    assert jan["headline"] == {"value": "186000", "unit": "MWh"}
    assert jan["state"] == "actionable"


def test_dedupe_persistence_hysteresis_and_a_failing_evaluator(store) -> None:
    _seed_demo(store)
    for _ in range(3):
        _run(store, demo=True)
    keys = [row.opp_key for row in store.query(OpportunityRecord).all()]
    assert len(keys) == len(set(keys))  # one record per key, however often evaluated
    versions = {row.opportunity_id: row.version for row in store.query(OpportunityRecord)}

    class Broken:
        name = "hedge_gap"
        version = "x"
        type = HEDGE_GAP.type

        def evaluate(self, snapshot, context):
            raise RuntimeError("defect")

    summary = run_evaluation(
        store,
        trigger="test",
        triggered_by="tester",
        now_utc=NOW,
        caller=Caller(_principal()),
        evaluators=[Broken()],
        demo_desk=True,
    )
    store.commit()
    assert summary["status"] == "failed"
    after = {row.opportunity_id: (row.version, row.state) for row in store.query(OpportunityRecord)}
    assert {k: v for k, (v, _s) in after.items()} == versions  # a failure is not an absence
    from eurogas_nexus.application.monitoring_service import _opportunity_evaluator_candidates

    alerts = _opportunity_evaluator_candidates(store)
    assert [a.fingerprint for a in alerts] == ["opportunity_evaluator:hedge_gap"]

    # Hysteresis: the band is withdrawn; one miss keeps the records, two expire them.
    store.query(HedgeApprovalRecord).delete()
    store.commit()
    _run(store, demo=True)
    gaps = store.query(OpportunityRecord).filter(OpportunityRecord.type == "hedge_gap").all()
    assert "expired" not in {row.state for row in gaps}
    _run(store, demo=True)
    gaps = store.query(OpportunityRecord).filter(OpportunityRecord.type == "hedge_gap").all()
    assert {row.state for row in gaps} == {"expired"}
    assert {row.ended_reason for row in gaps} == {"no_longer_found"}


def test_book_scope_property_no_cross_book_leak() -> None:
    rng = random.Random(7)
    books = ["b1", "b2", "b3", "b4"]
    for _ in range(2000):
        row_books = rng.sample(books, rng.randint(0, 3))
        families = rng.sample(["ECB", "ICE_ENDEX", "operator-input", "DEMO"], rng.randint(0, 2))
        row = SimpleNamespace(book_ids=row_books, source_families=families)
        allowed = None if rng.random() < 0.2 else set(rng.sample(books, rng.randint(0, 4)))
        entitled_families = set(rng.sample(["ECB", "ICE_ENDEX", "operator-input", "DEMO"], 2))
        shown = visible_to(row, allowed, lambda family, held=entitled_families: family in held)
        if shown and allowed is not None:
            assert row_books and set(row_books) <= allowed
        if shown:
            assert set(families) <= entitled_families
        if allowed is not None and not row_books:
            assert not shown  # firm-level rows only for a caller who sees every book


def test_demo_desk_evaluators_i_produce_marked_objects(store) -> None:
    """CP-09 on the seeded demo desk (offline: its simulated BBL tariffs only).

    Event exposure: the two demo outages name the Haldor and Kestrel contracts' sources, so
    each linked contract carries a cover cost, marked simulated. Locational and held
    capacity: every pair is either priced (legs reconcile) or a named "cannot evaluate"
    record (a tariff not held at a real ENTSOG point, a mandate check). Sell-down (P-11):
    each demo book's cash-out rate is in a set the book owns, so the UK book's NBP residual
    and the NL book's TTF residual are valued at their own book's rate; the UK book's TTF
    residual has no TTF rate in either set and stays a named "cannot evaluate".
    """

    from decimal import Decimal

    _seed_demo(store)
    _run(store, demo=True)
    summary = _run(store, demo=True)
    assert {name for name, status in summary["evaluators"].items() if status["status"] == "ok"} >= {
        "event_exposure",
        "hedge_gap",
        "held_capacity",
        "locational",
        "sell_down",
    }
    rows = store.query(OpportunityRecord).filter(OpportunityRecord.state != "expired").all()
    events = [row for row in rows if row.type == "event_exposure"]
    assert events and all(row.simulated and row.state == "indicative" for row in events)
    assert any("Haldor" in row.claim_text for row in events)
    for row in rows:
        assert row.simulated or row.quality_class == "missing"
        version = store.get(OpportunityVersionRecord, (row.opportunity_id, row.version))
        if row.state == "blocked":
            assert row.claim_text.startswith("Cannot evaluate: ")
            continue
        terms = [leg for leg in version.payload_json["legs"] if leg["kind"] == "term"]
        total = sum(Decimal(leg["contribution"]["value"]) for leg in terms)
        assert total == Decimal(version.payload_json["headline"]["value"])
    assert any(row.type == "locational" for row in rows)
    sell_down = {
        (row.claim_fields.get("hub"), tuple(row.book_ids or ())): row
        for row in rows
        if row.type == "sell_down"
    }
    for key in (("NBP", ("demo-uk-nbp",)), ("TTF", ("demo-nl-ttf",))):
        row = sell_down[key]
        assert row.state == "indicative" and row.simulated, row.claim_text
        version = store.get(OpportunityVersionRecord, (row.opportunity_id, row.version))
        (use,) = version.payload_json["assumptions"]
        names = {"NBP": "UK NBP balancing", "TTF": "NL TTF balancing"}
        assert use["book_id"] == key[1][0] and use["set_name"] == names[key[0]]
    assert sell_down[("TTF", ("demo-uk-nbp",))].state == "blocked"
    # CP-10: Kestrel's BBL route makes the pool's re-routing gain a simulated R object.
    assert any(row.type == "reroute" and row.simulated for row in rows)
