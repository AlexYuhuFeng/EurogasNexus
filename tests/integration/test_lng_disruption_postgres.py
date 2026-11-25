"""LNG-3 through the store: the owner's scenario seeded as rows, re-optimised, chosen, and
re-run by the outbox consumer when the ETA slips again.

The scenario is the one in docs/engineering/Commercial-Intelligence-V3/
06_ACCEPTANCE_SCENARIOS.md ("LNG-3 a disruption re-optimises the portfolio"), judged on
20 Jan 2027 09:00 UTC. Every price, offer and term is illustrative. The rows carry no
boil-off (voyage terms 0 %/day), so the cargo lands exactly 1,000,000 MWh as in the worked
example; the domain test (tests/domain/test_lng_disruption.py) carries the boil-off lines.

Runs on SQLite always, and on PostgreSQL migrated to head (``0086_lng_disruption``) when
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


def seed(session, case: Case) -> None:
    t = case.terminals
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
                demurrage_eur_per_day=70_000.0,
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
            seed(session, case)
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
                # -40,000 physical - 212,000 re-hedge - 35,000 demurrage + 100,000 release.
                "A:divert:D+absorb": (-187_000, -257_000, 247_000, 0, 0),
            }
            for key, numbers in hand.items():
                assert objectives(options[case.key(key)]) == numbers, key
            iberia = options[case.key("A:swap:C+absorb")]
            assert not iberia["feasible"]
            huelva = case.terminals["Huelva"]
            assert (
                f"breaks the firm delivery to Cepsa at {huelva}: 50,000 MWh short on 24 Jan"
                in iberia["reasons"]
            )
            assert set(data["frontier"]) == {
                options[case.key("A:stay+borrow")]["option_id"],
                options[case.key("A:swap:B+absorb")]["option_id"],
            }
            default = options[case.key("A:stay+borrow")]
            assert data["recommended"] == default["option_id"] and default["score"] == -89_000

            with pytest.raises(lng_disruption.CargoPlanError) as refused:
                lng_disruption.choose_option(
                    session, case.ids["A"], iberia["option_id"], actor="trader", now=NOW
                )
            assert refused.value.status_code == 409
            swap = options[case.key("A:swap:B+absorb")]
            chosen = lng_disruption.choose_option(
                session, case.ids["A"], swap["option_id"], actor="trader", note="t", now=NOW
            )
            session.commit()
            assert chosen["booked"] is False and not chosen["was_recommended"]
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
