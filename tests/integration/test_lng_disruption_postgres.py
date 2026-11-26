"""LNG-3 and LNG-4 through the store: the owner's scenario seeded as rows, re-optimised,
chosen, and re-run by the outbox consumer when the ETA slips again. LNG-4 adds interruptible
capacity at Huelva (so the Huelva swap is a possible option, flagged as breaking Cepsa), a
GATE-1 demurrage rate in USD converted at the ECB rate, and, in the first test, another user's
carrier due at the Dunkerque berth so the contracted-terminal option carries its knock-on.

The scenario is the one in docs/engineering/Commercial-Intelligence-V3/
06_ACCEPTANCE_SCENARIOS.md ("LNG-3 a disruption re-optimises the portfolio"), judged on
20 Jan 2027 09:00 UTC. Every price, offer and term is illustrative. The rows carry no
boil-off (voyage terms 0 %/day), so the cargo lands exactly 1,000,000 MWh as in the worked
example; the domain test (tests/domain/test_lng_disruption.py) carries the boil-off lines.

Runs on SQLite always, and on PostgreSQL migrated to head (``0087_lng4_options_demurrage``) when
``EUROGAS_NEXUS_TEST_POSTGRES_URL`` is set. Every id carries a suffix and the rows are
removed afterwards, so a shared database is left as found.
"""

from __future__ import annotations

import os
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.application import lng_disruption, market_events
from eurogas_nexus.application.market_event_capture import capture_desk
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import (
    FirmMarkRecord,
    FxObservationRecord,
    LngBerthCallRecord,
    LngCapacityOfferRecord,
    LngCargoRecord,
    LngDeliveryObligationRecord,
    LngDisruptionDecisionRecord,
    LngDisruptionRunRecord,
    LngSlotTermsRecord,
    LngTerminalTermsRecord,
    LngVoyageTermsRecord,
    NotificationOutboxRecord,
    PipelineSupplyRecord,
    RegasSlotRecord,
)
from eurogas_nexus.domain.market.gas_day import gas_day_start_for_date

NOW = datetime(2027, 1, 20, 9, tzinfo=UTC)
PRICES = {
    ("ZTP", "2027-01"): 30.00,
    ("ZTP", "2027-02"): 29.00,
    ("TTF", "2027-01"): 30.40,
    ("TTF", "2027-02"): 29.40,
    ("PEG", "2027-01"): 30.20,
    ("PEG", "2027-02"): 29.40,
    ("PVB", "2027-01"): 31.00,
    ("PVB", "2027-02"): 30.00,
}
_POSTGRES_URL = os.environ.get("EUROGAS_NEXUS_TEST_POSTGRES_URL", "")


def jan(day: int) -> date:
    return date(2027, 1, day)


def feb(day: int) -> date:
    return date(2027, 2, day)


@pytest.fixture(params=["sqlite", "postgresql"])
def engine(request, tmp_path, monkeypatch):
    if request.param == "postgresql":
        if not _POSTGRES_URL.startswith("postgresql"):
            pytest.skip("Needs EUROGAS_NEXUS_TEST_POSTGRES_URL migrated to head.")
        url = _POSTGRES_URL
        made = create_engine(url, future=True)
    else:
        url = f"sqlite+pysqlite:///{(tmp_path / 'lng3.sqlite').as_posix()}"
        made = create_engine(url, future=True)
        Base.metadata.create_all(made)
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    yield made
    made.dispose()


class Case:
    """The owner's book under suffixed ids: A (ZEE-1, late), B (GATE-1), C (HUE-1), P."""

    def __init__(self) -> None:
        sfx = uuid4().hex[:8]
        self.sfx = sfx
        self.book = f"lng3-{sfx}"
        self.ids = {key: f"lng3-{sfx}-{key.lower()}" for key in ("A", "B", "C", "P")}
        self.slots = {key: f"lng3-{sfx}-slot-{key.lower()}" for key in ("Z", "G", "H", "D")}
        self.terminals = {
            name: f"LNG3 {sfx} {name}" for name in ("Zeebrugge", "Gate", "Huelva", "Dunkerque")
        }

    def key(self, text: str) -> str:
        """A key of the worked example ("A:swap:B+absorb") in this case's ids."""

        head, _, rest = text.partition(":")
        out = f"{self.ids[head]}:{rest}"
        for short, long in (("swap:B", "B"), ("swap:C", "C")):
            if f"{short}+" in out:
                out = out.replace(f"{short}+", f"swap:{self.ids[long]}+")
        if "divert:D+" in out:
            out = out.replace("divert:D+", f"divert:{self.slots['D']}+")
        return out


def seed(session, case: Case, *, berth_call: bool = False) -> None:
    t = case.terminals
    # ECB EUR/USD of the day before, so GATE-1's 77,000 USD/day is 70,000 EUR/day.
    session.add(
        FxObservationRecord(
            observation_id=f"lng3-{case.sfx}-eurusd",
            pair="EURUSD",
            base_currency="EUR",
            quote_currency="USD",
            rate=1.10,
            rate_type="reference",
            value_date="2027-01-19",
            observed_at_utc=NOW - timedelta(days=1),
            source_system="ECB",
            source_reference="LNG-4 test: illustrative",
            freshness="fresh",
            research_only=False,
        )
    )
    if berth_call:
        session.add(
            LngBerthCallRecord(
                call_id=f"lng3-{case.sfx}-dk-call",
                terminal_name=t["Dunkerque"],
                label="another user's carrier",
                berth_gas_day=jan(30),
                berth_days=2,
                laytime_left_hours=24.0,
                demurrage_rate_per_day=65_000.0,
                demurrage_currency="EUR",
                boil_off_mwh_per_day=1_000.0,
                source_reference="LNG-4 test: illustrative",
                updated_at_utc=NOW,
            )
        )
    for name, hub, sail in (
        ("Zeebrugge", "ZTP", 0.0),
        ("Gate", "TTF", 0.0),
        ("Huelva", "PVB", -3.0),
        ("Dunkerque", "PEG", 0.0),
    ):
        session.add(
            LngTerminalTermsRecord(
                terminal_id=f"lng3-{case.sfx}-{name.lower()}",
                name=t[name],
                country=None,
                hub=hub,
                regas_tariff_per_mwh=0.0,
                entry_tariff_per_mwh=0.0,
                fuel_retention_pct=0.0,
                port_costs_per_cargo=0.0,
                other_per_mwh=0.0,
                extra_sailing_days=sail,
                source_note="LNG-3 test: illustrative",
                updated_by="test",
                updated_at_utc=NOW,
            )
        )
    for (hub, month), price in PRICES.items():
        start = date.fromisoformat(f"{month}-01")
        end = (start.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        session.add(
            FirmMarkRecord(
                mark_id=f"lng3-{case.sfx}-{hub}-{month}",
                hub=hub,
                period_label=month,
                period_start=start,
                period_end=end,
                value=Decimal(str(price)),
                unit="MWh",
                currency="EUR",
                note="LNG-3 test: illustrative",
                entered_by="test",
                entered_at_utc=NOW - timedelta(hours=1),
            )
        )
    cargoes = (
        ("A", "ZEE-1", "Zeebrugge", jan(28), "medium", "Z"),
        ("B", "GATE-1", "Gate", jan(26), "high", "G"),
        ("C", "HUE-1", "Huelva", jan(24), "high", "H"),
    )
    for key, vessel, terminal, eta, confidence, _slot in cargoes:
        cargo_id = case.ids[key]
        session.add(
            LngCargoRecord(
                cargo_id=cargo_id,
                vessel_name=vessel,
                status="laden",
                load_port="Test load port",
                departed_at_utc=NOW - timedelta(days=8),
                destination_terminal=t[terminal],
                eta_utc=gas_day_start_for_date(eta) + timedelta(hours=6),
                volume_m3=170_000.0,
                energy_gwh=1_000.0,
                book_id=case.book,
                source_system="LNG3_TEST",
                source_reference="test",
                updated_at_utc=NOW,
                eta_basis="master_notice",
                eta_confidence=confidence,
                eta_source="LNG3_TEST",
                eta_recorded_at_utc=NOW,
            )
        )
        session.add(
            LngVoyageTermsRecord(
                cargo_id=cargo_id,
                charter_reference=None,
                laytime_hours=36.0,
                demurrage_eur_per_day=None if key == "B" else 70_000.0,
                demurrage_rate_per_day=77_000.0 if key == "B" else None,
                demurrage_currency="USD" if key == "B" else None,
                demurrage_terms="pro rata after laytime (test)" if key == "B" else None,
                boil_off_pct_per_day=0.0,
                diversion_allowed=True,
                diversion_note=None,
                source_reference="LNG-3 test: illustrative",
                updated_at_utc=NOW,
            )
        )
    for key, terminal, first, days, rate, holder in (
        ("Z", "Zeebrugge", jan(26), 10, 100.0, "A"),
        ("G", "Gate", jan(28), 10, 100.0, "B"),
        ("H", "Huelva", jan(24), 20, 50.0, "C"),
        ("D", "Dunkerque", jan(30), 10, 100.0, None),
    ):
        session.add(
            RegasSlotRecord(
                slot_id=case.slots[key],
                terminal_name=t[terminal],
                window_start_utc=gas_day_start_for_date(first),
                window_end_utc=gas_day_start_for_date(first + timedelta(days=days)),
                send_out_gwh_d=rate,
                energy_gwh=rate * days,
                cargo_id=None if holder is None else case.ids[holder],
                book_id=case.book,
                source_system="LNG3_TEST",
                source_reference="test",
                updated_at_utc=NOW,
            )
        )
    session.add(
        LngSlotTermsRecord(
            slot_id=case.slots["Z"],
            slot_days=10,
            storage_mwh=1_000_000.0,
            storage_profile="linear_decline",
            release_value_eur_mwh=0.10,
            source_reference="LNG-3 test: illustrative",
            updated_at_utc=NOW,
        )
    )
    if berth_call:
        # The Dunkerque slot: a call there holds the berth two gas days.
        session.add(
            LngSlotTermsRecord(
                slot_id=case.slots["D"],
                slot_days=10,
                storage_mwh=1_000_000.0,
                storage_profile="linear_decline",
                release_value_eur_mwh=0.05,
                berth_days=2,
                source_reference="LNG-4 test: illustrative",
                updated_at_utc=NOW,
            )
        )
    for name, kind, first, last, price, per_day, total, storage in (
        ("borrow", "borrow", jan(26), jan(27), 0.10, 100_000.0, None, None),
        ("send", "send_out", jan(26), feb(10), 0.15, 50_000.0, None, None),
        ("store", "storage", jan(26), feb(10), 0.02, None, 300_000.0, None),
        ("int", "interruptible", jan(26), feb(20), 0.05, 100_000.0, None, 0.01),
    ):
        session.add(
            LngCapacityOfferRecord(
                offer_id=f"lng3-{case.sfx}-{name}",
                book_id=case.book,
                terminal_name=t["Zeebrugge"],
                kind=kind,
                first_gas_day=first,
                last_gas_day=last,
                price_eur_mwh=price,
                max_mwh_per_day=per_day,
                max_mwh=total,
                storage_price_eur_mwh_day=storage,
                basis="indicative",
                counterparty=None,
                source_reference="LNG-3 test: illustrative",
                valid_until_utc=None,
                updated_at_utc=NOW,
            )
        )
    # LNG-4: interruptible send-out and storage at Huelva, so ZEE-1 can physically land there.
    session.add(
        LngCapacityOfferRecord(
            offer_id=f"lng3-{case.sfx}-hint",
            book_id=case.book,
            terminal_name=t["Huelva"],
            kind="interruptible",
            first_gas_day=jan(24),
            last_gas_day=feb(20),
            price_eur_mwh=0.05,
            max_mwh_per_day=50_000.0,
            max_mwh=None,
            storage_price_eur_mwh_day=0.01,
            basis="indicative",
            counterparty=None,
            source_reference="LNG-4 test: illustrative",
            valid_until_utc=None,
            updated_at_utc=NOW,
        )
    )
    session.add(
        LngDeliveryObligationRecord(
            obligation_id=f"lng3-{case.sfx}-cepsa",
            book_id=case.book,
            counterparty="Cepsa",
            contract_id=None,
            point=t["Huelva"],
            hub="PVB",
            first_gas_day=jan(24),
            last_gas_day=feb(12),
            mwh_per_day=50_000.0,
            firm=True,
            penalty_eur_mwh=None,
            source_reference="LNG-3 test: illustrative",
            updated_at_utc=NOW,
        )
    )
    session.add(
        PipelineSupplyRecord(
            supply_id=case.ids["P"],
            book_id=case.book,
            label="Pipeline ZTP",
            contract_id=None,
            hub="ZTP",
            point="ZTP",
            first_gas_day=jan(20),
            last_gas_day=feb(28),
            mwh_per_day=30_000.0,
            cost_eur_mwh=28.0,
            curtailed=[],
            source_system="LNG3_TEST",
            source_reference="LNG-3 test: illustrative",
            updated_at_utc=NOW,
        )
    )
    session.flush()


def clean(session, case: Case) -> None:
    like = f"lng3-{case.sfx}%"
    for model, column in (
        (LngDisruptionDecisionRecord, LngDisruptionDecisionRecord.book_id),
        (LngDisruptionRunRecord, LngDisruptionRunRecord.book_id),
        (PipelineSupplyRecord, PipelineSupplyRecord.book_id),
        (LngDeliveryObligationRecord, LngDeliveryObligationRecord.book_id),
        (LngCapacityOfferRecord, LngCapacityOfferRecord.offer_id),
        (LngSlotTermsRecord, LngSlotTermsRecord.slot_id),
        (RegasSlotRecord, RegasSlotRecord.slot_id),
        (LngVoyageTermsRecord, LngVoyageTermsRecord.cargo_id),
        (LngCargoRecord, LngCargoRecord.cargo_id),
        (FirmMarkRecord, FirmMarkRecord.mark_id),
        (FxObservationRecord, FxObservationRecord.observation_id),
        (LngBerthCallRecord, LngBerthCallRecord.call_id),
        (LngTerminalTermsRecord, LngTerminalTermsRecord.terminal_id),
    ):
        session.query(model).filter(column.like(like)).delete(synchronize_session=False)
    session.commit()


def objectives(option: dict) -> tuple:
    o = option["objectives"]
    return (
        o["pnl_expected"],
        o["pnl_worst"],
        o["cost"],
        o["flexibility_mwh"],
        o["disrupted_mwh"],
    )


def test_the_owner_scenario_is_valued_from_the_store_and_chosen(engine):
    case = Case()
    with Session(engine) as session:
        try:
            seed(session, case, berth_call=True)
            session.commit()
            data = lng_disruption.disruption_options(session, case.ids["A"], now=NOW)
            assert data["status"] == "disrupted"
            assert [s["supply_id"] for s in data["disrupted"]] == [case.ids["A"]]
            options = {o["key"]: o for o in data["options"]}
            # (expected, worst, cost, spare firm send-out MWh, MWh of other supplies moved)
            hand = {
                "A:stay+absorb": (-279_000, -417_000, 79_000, 800_000, 0),
                "A:stay+borrow": (-20_000, -158_000, 20_000, 1_000_000, 0),
                "A:stay+buy": (-36_000, -249_000, 36_000, 1_000_000, 0),
                # No boil-off in these rows: the swap saves GATE-1's half day of demurrage.
                "A:swap:B+absorb": (35_000, -391_000, -35_000, 1_000_000, 1_000_000),
                # Direct: -40,000 physical - 212,000 re-hedge - 35,000 demurrage + 100,000
                # release = -187,000. Opportunity (LNG-4): ZEE-1 holds the Dunkerque berth on
                # 30 and 31 Jan, so the carrier due on 30 Jan waits 48 h against 24 h laytime
                # (65,000) and boils off 2,000 MWh at PEG 30.20 (60,400); the slot's
                # 1,000,000 MWh could have been released at 0.05 (50,000). -187,000 - 175,400.
                "A:divert:D+absorb": (-362_400, -432_400, 247_000, 0, 0),
                # LNG-4: possible at Huelva's interruptible capacity, and breaking Cepsa.
                "A:swap:C+absorb": (-215_000, -289_500, 65_000, 850_000, 1_000_000),
            }
            for key, numbers in hand.items():
                assert objectives(options[case.key(key)]) == numbers, key
            divert = options[case.key("A:divert:D+absorb")]
            assert (divert["direct_pnl_expected"], divert["opportunity_cost_expected"]) == (
                -187_000,
                175_400,
            )
            (call, forgone) = divert["opportunity"]
            assert (call["kind"], call["delay_days"], call["held_by"]) == (
                "berth_delay",
                2,
                "ZEE-1",
            )
            assert (call["demurrage_eur"], call["boil_off_eur"]) == (-65_000, -60_400)
            assert (forgone["kind"], forgone["value_eur"]) == ("capacity_forgone", -50_000)
            # The knock-on moves the contracted Dunkerque slot below staying and absorbing.
            assert divert["rank"] > options[case.key("A:stay+absorb")]["rank"]
            iberia = options[case.key("A:swap:C+absorb")]
            assert iberia["possible"] and iberia["flags"]["contract_breach"]
            huelva = case.terminals["Huelva"]
            (breach,) = iberia["breaches"]
            assert breach["text"].startswith(
                f"breaks the firm delivery to Cepsa at {huelva}: 50,000 MWh short on 24 Jan"
            )
            assert not breach["penalty_held"]
            # GATE-1's demurrage is held in USD and converted at the ECB rate of the day before.
            swap = options[case.key("A:swap:B+absorb")]
            detail = lng_disruption.option_detail(
                session, case.ids["A"], swap["option_id"], now=NOW
            )
            gate = next(leg for leg in detail["legs"] if leg["supply_id"] == case.ids["B"])
            terms = gate["demurrage"]["terms"]
            assert (terms["rate_per_day"], terms["currency"], terms["eur_per_day"]) == (
                77_000,
                "USD",
                70_000,
            )
            assert (terms["fx"]["source"], terms["fx"]["rate_date"]) == ("ECB", "2027-01-19")
            assert set(data["frontier"]) == {
                options[case.key("A:stay+borrow")]["option_id"],
                options[case.key("A:swap:B+absorb")]["option_id"],
            }
            default = options[case.key("A:stay+borrow")]
            assert data["recommended"] == default["option_id"] and default["score"] == -89_000

            assert [(r["basis"], r["option_id"]) for r in data["recommended_set"]] == [
                ("clean", default["option_id"]),
                ("best_expected", swap["option_id"]),
            ]

            # A breach option may be chosen; the record keeps what it breaks.
            breaking = lng_disruption.choose_option(
                session, case.ids["A"], iberia["option_id"], actor="trader", now=NOW
            )
            assert breaking["consequences"]["flags"]["contract_breach"] is True
            assert not breaking["was_recommended"]
            session.query(LngDisruptionDecisionRecord).filter(
                LngDisruptionDecisionRecord.book_id == case.book
            ).delete(synchronize_session=False)
            chosen = lng_disruption.choose_option(
                session, case.ids["A"], swap["option_id"], actor="trader", note="t", now=NOW
            )
            session.commit()
            assert chosen["booked"] is False and chosen["was_recommended"]
            assert chosen["consequences"]["recommended_as"] == ["best_expected"]
            assert session.get(LngCargoRecord, case.ids["A"]).eta_utc is not None
            held = session.get(RegasSlotRecord, case.slots["Z"])
            assert held.cargo_id == case.ids["A"]  # nothing moved: the choice is a record
        finally:
            session.rollback()
            clean(session, case)


def test_a_later_eta_flips_the_default_and_the_roles_are_told_once(engine):
    case = Case()
    with Session(engine) as session:
        try:
            seed(session, case)
            session.commit()

            def runs():
                return (
                    session.query(LngDisruptionRunRecord)
                    .filter(LngDisruptionRunRecord.book_id == case.book)
                    .order_by(LngDisruptionRunRecord.computed_at_utc)
                    .all()
                )

            def told():
                return (
                    session.query(NotificationOutboxRecord)
                    .filter(
                        NotificationOutboxRecord.dedupe_key.like(f"lng_disruption:{case.book}:%")
                    )
                    .all()
                )

            capture_desk(session, cargo_ids=[case.ids["A"]], now_utc=NOW)
            session.commit()
            market_events.process(session, lng_disruption.CONSUMER_NAME, now_utc=NOW)
            session.commit()
            first = runs()
            assert len(first) == 1 and first[0].notified
            assert first[0].recommended_key == case.key("A:stay+borrow")
            assert len(told()) == 3

            # The ETA slips two more days (30 Jan), five minutes on: the default flips to
            # borrowing in tank and buying extra send-out, told at once despite the cooldown.
            cargo = session.get(LngCargoRecord, case.ids["A"])
            cargo.eta_utc = gas_day_start_for_date(jan(30)) + timedelta(hours=6)
            later = NOW + timedelta(minutes=5)
            capture_desk(session, cargo_ids=[case.ids["A"]], now_utc=later)
            session.commit()
            market_events.process(session, lng_disruption.CONSUMER_NAME, now_utc=later)
            session.commit()
            second = runs()
            assert len(second) == 2
            flipped = second[-1]
            assert flipped.change == "recommendation" and flipped.notified
            assert flipped.recommended_key == case.key("A:stay+borrow_buy")
            assert flipped.recommended_pnl_eur == -182_000
            frontier_keys = {item["key"] for item in flipped.frontier}
            assert frontier_keys == {case.key("A:stay+borrow_buy"), case.key("A:divert:D+absorb")}
            notices = told()
            assert len(notices) == 6
            assert {n.category for n in notices} == {"cargo", "nomination", "desk_head"}

            # Re-run on the same inputs: no new run, nobody told again.
            again = lng_disruption.reoptimise(
                session, case.book, trigger="test", now=later + timedelta(minutes=1)
            )
            session.commit()
            assert again["status"] == "unchanged"
            assert len(runs()) == 2 and len(told()) == 6
        finally:
            session.rollback()
            session.query(NotificationOutboxRecord).filter(
                NotificationOutboxRecord.dedupe_key.like(f"lng_disruption:{case.book}:%")
            ).delete(synchronize_session=False)
            clean(session, case)


def test_a_remit_outage_reaches_the_pipeline_supply_through_the_outbox(engine):
    """LNG-4: an ``outage.published`` event links the message to the supply that flows
    through its asset before the book is re-optimised; a withdrawn version removes the
    curtailment; the manual override keeps only the days entered by hand."""

    from eurogas_nexus.application import pipeline_outages
    from eurogas_nexus.application.market_event_capture import capture_rows
    from eurogas_nexus.db.models import AuditEventRecord, PipelineOutageLinkRecord, RemitUmmRecord

    case = Case()
    eic = f"21Z-LNG4-{case.sfx}"[:32]

    def umm(version: int, status: str = "active") -> RemitUmmRecord:
        return RemitUmmRecord(
            record_id=f"lng3-{case.sfx}-umm-v{version}",
            message_id=f"lng3-{case.sfx}-umm",
            version=version,
            published_at_utc=NOW + timedelta(minutes=version),
            event_status=status,
            unavailability_type="unplanned",
            event_start_utc=gas_day_start_for_date(feb(1)),
            event_stop_utc=gas_day_start_for_date(feb(4)),
            asset_name="LNG-4 test interconnector",
            asset_eic=eic,
            asset_type="interconnector",
            balancing_zone="ZTP",
            direction="entry",
            unit="GWh/d",
            technical_capacity=100.0,
            available_capacity=40.0,
            unavailable_capacity=60.0,
            unavailable_mcm_d=None,
            unavailable_gwh_d=60.0,
            reason="LNG-4 test",
            market_participant="Test TSO",
            remarks="",
            source_system="REMIT",
            source_reference="LNG-4 test: illustrative",
            ingested_at_utc=NOW + timedelta(minutes=version),
        )

    def drain(moment):
        capture = market_events.process(session, lng_disruption.CONSUMER_NAME, now_utc=moment)
        session.commit()
        return capture

    with Session(engine) as session:
        try:
            seed(session, case)
            pipe = session.get(PipelineSupplyRecord, case.ids["P"])
            pipe.depends_on = [{"asset_eic": eic, "kind": "interconnector"}]
            session.commit()

            first = umm(1)
            session.add(first)
            capture_rows(session, outages=[first], now_utc=NOW)
            session.commit()
            drain(NOW + timedelta(minutes=5))
            (link,) = (
                session.query(PipelineOutageLinkRecord).filter_by(supply_id=case.ids["P"]).all()
            )
            assert (link.status, link.fraction, link.matched_on) == ("applied", 0.6, "asset_eic")
            # 30,000 MWh/d x 60 % unavailable on the 1, 2 and 3 Feb gas days.
            assert link.curtailed == [
                ["2027-02-01", 18_000.0],
                ["2027-02-02", 18_000.0],
                ["2027-02-03", 18_000.0],
            ]
            assert link.event_id
            book = lng_disruption.frontier(session, case.book, now=NOW)
            (outage,) = book["pipeline_outages"]
            assert outage["outage_mode"] == "auto"
            assert outage["effective"][0] == ["2027-02-01", 18_000.0]
            assert any(
                item["input"] == f"pipeline {case.ids['P']} outage" for item in book["inputs"]
            )
            assert case.ids["P"] in {s["supply_id"] for s in book["disrupted"]}

            # The same message delivered again changes nothing.
            capture_rows(session, outages=[first], now_utc=NOW + timedelta(minutes=1))
            session.commit()
            drain(NOW + timedelta(minutes=6))
            assert (
                session.query(PipelineOutageLinkRecord)
                .filter_by(supply_id=case.ids["P"])
                .one()
                .version
                == 1
            )

            # Version 2 withdraws it: the link stays, curtailing nothing.
            withdrawn = umm(2, "dismissed")
            session.add(withdrawn)
            capture_rows(session, outages=[withdrawn], now_utc=NOW + timedelta(minutes=2))
            session.commit()
            drain(NOW + timedelta(minutes=7))
            link = session.query(PipelineOutageLinkRecord).filter_by(supply_id=case.ids["P"]).one()
            assert (link.status, link.version, link.curtailed) == ("withdrawn", 2, [])
            book = lng_disruption.frontier(session, case.book, now=NOW)
            assert book["pipeline_outages"][0]["effective"] == []
            assert case.ids["P"] not in {s["supply_id"] for s in book["disrupted"]}

            # The manual override: only the days entered by hand count.
            shown = pipeline_outages.set_override(
                session,
                case.ids["P"],
                mode="manual",
                curtailed=[["2027-02-02", 5_000]],
                actor="trader",
                now=NOW,
            )
            session.commit()
            assert shown["effective"] == [["2027-02-02", 5_000.0]]
            assert shown["links"][0]["status"] == "withdrawn"
        finally:
            session.rollback()
            session.query(PipelineOutageLinkRecord).filter(
                PipelineOutageLinkRecord.supply_id == case.ids["P"]
            ).delete(synchronize_session=False)
            session.query(RemitUmmRecord).filter(
                RemitUmmRecord.message_id == f"lng3-{case.sfx}-umm"
            ).delete(synchronize_session=False)
            session.query(AuditEventRecord).filter(
                AuditEventRecord.resource == f"pipeline_supply:{case.ids['P']}"
            ).delete(synchronize_session=False)
            session.query(NotificationOutboxRecord).filter(
                NotificationOutboxRecord.dedupe_key.like(f"lng_disruption:{case.book}:%")
            ).delete(synchronize_session=False)
            clean(session, case)
