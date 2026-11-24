"""The live valuation snapshot reader over a runtime store (CP-07).

Pins the reading rules: executable quote > settlement > the firm's mark; simulated rows only
on a demo desk; entitlement fails closed; spot FX for a forward month is "indicative" and
says "FX: spot"; tariff publication status sets the class; and a frozen snapshot replays to
the identical inputs and figures.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.application.caller import Caller
from eurogas_nexus.application.valuation_snapshot import (
    SpotEcbFx,
    freeze_snapshot,
    open_valuation_snapshot,
    replay_snapshot,
)
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import (
    FxObservationRecord,
    InterestRateObservationRecord,
    MarketObservationRecord,
    MarketQuoteRecord,
    TsoTariffRecord,
)
from eurogas_nexus.db.repositories.commercial_assumptions import (
    approve_assumption_version,
    create_assumption_set,
    create_assumption_version,
    put_firm_marks,
)
from eurogas_nexus.domain.valuation.assumptions import validate_assumption_value
from eurogas_nexus.domain.valuation.firm_marks import validate_firm_mark
from eurogas_nexus.domain.valuation.periods import DeliveryPeriod
from eurogas_nexus.domain.valuation.quality import InputClass
from eurogas_nexus.security.identity import AuthenticatedPrincipal

AS_OF = datetime(2026, 11, 17, 9, 42, tzinfo=UTC)
JAN27 = DeliveryPeriod.month(2027, 1)
FEB27 = DeliveryPeriod.month(2027, 2)


def _caller(scopes: tuple[str, ...]) -> Caller:
    return Caller(
        AuthenticatedPrincipal(
            principal_id="p-test",
            name="tester",
            principal_type="USER",
            role="ANALYST",
            status="ACTIVE",
            data_scopes=scopes,
            roles=("ANALYST",),
        )
    )


def _utc(day: date) -> datetime:
    return datetime.combine(day, datetime.min.time(), tzinfo=UTC)


@pytest.fixture()
def session(tmp_path, monkeypatch):
    url = f"sqlite+pysqlite:///{(tmp_path / 'snap.sqlite').as_posix()}"
    engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    with Session(engine) as db:
        yesterday = AS_OF - timedelta(hours=20)
        db.add_all(
            [
                MarketQuoteRecord(
                    quote_id="q-the-jan",
                    source_system="ICE_ENDEX",
                    venue="ICE Endex",
                    instrument_id="THE-M-JAN27",
                    hub="THE",
                    product="Jan-27",
                    delivery_start_utc=_utc(JAN27.start),
                    delivery_end_utc=_utc(JAN27.end),
                    bid_price=31.20,
                    ask_price=31.30,
                    currency="EUR",
                    unit="EUR/MWh",
                    observed_at_utc=AS_OF - timedelta(minutes=5),
                    received_at_utc=AS_OF - timedelta(minutes=5),
                    source_reference="ice:q",
                    freshness="live",
                    quality_score=1.0,
                    simulated=False,
                ),
                MarketObservationRecord(
                    observation_id="eex-ttf-jan27",
                    market_venue="EEX",
                    product="TTF Jan-27",
                    price=30.00,
                    unit="EUR/MWh",
                    currency="EUR",
                    period_start_utc=_utc(JAN27.start),
                    period_end_utc=_utc(JAN27.end),
                    observed_at_utc=yesterday,
                    source_system="EEX",
                    source_reference="eex:settlement",
                    freshness="end_of_day",
                    quality_score=1.0,
                    research_only=True,
                    metadata_json={"hub": "TTF"},
                ),
                MarketObservationRecord(
                    observation_id="demo-ttf-feb27",
                    market_venue="Demo",
                    product="TTF Feb-27",
                    price=29.50,
                    unit="EUR/MWh",
                    currency="EUR",
                    period_start_utc=_utc(FEB27.start),
                    period_end_utc=_utc(FEB27.end),
                    observed_at_utc=yesterday,
                    source_system="DEMO_Sim",
                    source_reference="demo:curve",
                    freshness="end_of_day",
                    quality_score=0.0,
                    research_only=True,
                    metadata_json={"hub": "TTF", "simulated": True},
                ),
                FxObservationRecord(
                    observation_id="ecb-gbp",
                    pair="EURGBP",
                    base_currency="EUR",
                    quote_currency="GBP",
                    rate=0.87,
                    rate_type="reference",
                    value_date="2026-11-16",
                    observed_at_utc=yesterday,
                    source_system="ECB",
                    source_reference="ecb",
                    freshness="daily",
                    research_only=True,
                ),
                InterestRateObservationRecord(
                    observation_id="sonia-1",
                    benchmark_id="SONIA",
                    currency="GBP",
                    value_date=date(2026, 11, 16),
                    rate_pct=3.75,
                    day_count="ACT/365",
                    source_system="BOE",
                    source_reference="boe:sonia",
                    ingested_at_utc=yesterday,
                ),
                InterestRateObservationRecord(
                    observation_id="estr-1",
                    benchmark_id="ESTR",
                    currency="EUR",
                    value_date=date(2026, 11, 16),
                    rate_pct=1.90,
                    day_count="ACT/360",
                    source_system="ECB",
                    source_reference="ecb:estr",
                    ingested_at_utc=yesterday,
                ),
            ]
        )
        for tariff_id, status, value in (
            ("t-final", "FINAL", 0.0101),
            ("t-sim", "SIMULATOR_ONLY", 0.5),
        ):
            db.add(
                TsoTariffRecord(
                    tariff_id=tariff_id,
                    document_id=f"doc-{tariff_id}",
                    country="NL",
                    tso="GTS",
                    market_area="NL",
                    gas_year="2026/27",
                    point_id="ITP-00063" if tariff_id == "t-final" else "ITP-00207",
                    source_point_name="Julianadorp",
                    direction="EXIT",
                    capacity_product="MONTHLY",
                    firmness="FIRM",
                    tariff_value=value,
                    currency="EUR",
                    unit="EUR/(kWh/h)/d",
                    effective_from=_utc(date(2026, 10, 1)),
                    effective_to=None,
                    tariff_status=status,
                    source_table="t",
                    source_page=None,
                    source_refs=[],
                    manual_review_required=False,
                    created_at_utc=yesterday,
                )
            )
        put_firm_marks(
            db,
            [validate_firm_mark("NBP", "2027-01", "78.00", "GBp/th")],
            actor="trader",
            now_utc=AS_OF - timedelta(hours=1),
        )
        made = create_assumption_set(
            db, name="Base", book_id=None, description="", actor="trader", now_utc=yesterday
        )
        create_assumption_version(
            db,
            set_id=made["set_id"],
            values=[validate_assumption_value("capacity.load_factor", 100)],
            effective_from=date(2026, 10, 1),
            effective_to=None,
            note="",
            actor="trader",
            now_utc=yesterday,
        )
        approve_assumption_version(
            db, set_id=made["set_id"], version=1, actor="risk", now_utc=yesterday
        )
        db.commit()
        yield db


def test_reading_rules_on_a_real_desk(session) -> None:
    reader = open_valuation_snapshot(
        session, caller=_caller(("*",)), as_of_utc=AS_OF, demo_desk=False
    )
    ask = reader.price("THE", JAN27, "ask")
    assert (ask.input_class, ask.value, ask.source_family) == (
        InputClass.SOURCED,
        Decimal("31.3"),
        "ICE_ENDEX",
    )
    assert reader.price("THE", JAN27, "mid").input_class is InputClass.INDICATIVE
    settlement = reader.price("TTF", JAN27, "ask")
    assert settlement.input_class is InputClass.INDICATIVE  # a settlement is not executable
    mark = reader.price("NBP", JAN27, "bid")
    assert mark.input_class is InputClass.FIRM_MARK
    assert mark.unit == "GBP/MWh" and mark.detail["native_unit"] == "GBp/th"
    assert mark.value.quantize(Decimal("0.001")) == Decimal("26.615")  # 78 p/th x 0.341214
    demo_only = reader.price("TTF", FEB27, "ask")
    assert demo_only.input_class is InputClass.MISSING  # a real desk never reads demo prices
    # Design D.5: spot EUR/GBP 0.8700 (2026-11-16), SONIA 3.75 % ACT/365, ESTR 1.90 % ACT/360,
    # value date 2027-01-15 (60 days): F = 0.87 x (1 + 0.0375 x 60/365) / (1 + 0.019 x 60/360)
    # = 0.8726, derived, with the 0.1 % tolerance of a forward up to three months.
    fx = reader.fx("EUR", "GBP", JAN27)
    assert fx.input_class is InputClass.DERIVED and "interest parity" in fx.label
    assert fx.value.quantize(Decimal("0.0001")) == Decimal("0.8726")
    assert fx.detail["value_date"] == "2027-01-15" and fx.detail["tolerance"]
    prompt = reader.fx("EUR", "GBP", DeliveryPeriod.gas_day(date(2026, 11, 18)))
    assert prompt.input_class is InputClass.SOURCED and prompt.value == Decimal("0.87")
    spot_only = open_valuation_snapshot(
        session,
        caller=_caller(("*",)),
        as_of_utc=AS_OF,
        demo_desk=False,
        fx_source=SpotEcbFx(demo_desk=False),
    ).fx("EUR", "GBP", JAN27)
    assert spot_only.input_class is InputClass.INDICATIVE and "FX: spot" in spot_only.label
    assert reader.rate("EUR").value == Decimal("1.9")
    tariff = reader.tariff("ITP-00063", "EXIT", "MONTHLY", JAN27)
    assert tariff.input_class is InputClass.SOURCED
    # The register keeps the published 0.0101 EUR/(kWh/h)/d; the reader states it per MWh at
    # 100 % load factor (x 1000 / 24), with the published figure beside it.
    assert tariff.unit == "EUR/MWh" and tariff.value.quantize(Decimal("0.000001")) == Decimal(
        "0.420833"
    )
    assert tariff.detail["published"] == "0.0101 EUR/(kWh/h)/d"
    assert reader.tariff("ITP-00207", "EXIT", "MONTHLY", JAN27).input_class is (InputClass.MISSING)
    load = reader.assumption("capacity.load_factor")
    assert load.input_class is InputClass.ASSUMPTION and load.detail["approved_by"] == "risk"
    assert reader.assumption("financing.rate").input_class is InputClass.MISSING


def test_a_demo_desk_reads_demo_rows_and_marks_them_simulated(session) -> None:
    reader = open_valuation_snapshot(
        session, caller=_caller(("*",)), as_of_utc=AS_OF, demo_desk=True
    )
    assert reader.price("TTF", FEB27, "ask").input_class is InputClass.SIMULATED
    assert reader.price("TTF", JAN27, "ask").input_class is InputClass.INDICATIVE  # real wins
    assert reader.tariff("ITP-00207", "EXIT", "MONTHLY", JAN27).input_class is (
        InputClass.SIMULATED
    )


def test_entitlement_fails_closed(session) -> None:
    reader = open_valuation_snapshot(session, caller=_caller(()), as_of_utc=AS_OF, demo_desk=False)
    assert reader.price("THE", JAN27, "ask").input_class is InputClass.MISSING  # licensed quote
    assert reader.fx("EUR", "GBP", JAN27).held  # ECB is public


def test_nothing_after_the_evaluation_instant_is_read(session) -> None:
    reader = open_valuation_snapshot(
        session, caller=_caller(("*",)), as_of_utc=AS_OF - timedelta(days=2), demo_desk=False
    )
    assert reader.price("THE", JAN27, "ask").input_class is InputClass.MISSING
    assert reader.price("NBP", JAN27, "bid").input_class is InputClass.MISSING


def test_a_frozen_snapshot_replays_to_identical_figures(session) -> None:
    def figure(reader) -> Decimal | None:
        sell = reader.price("THE", JAN27, "bid")
        buy = reader.price("TTF", JAN27, "ask")
        tariff = reader.tariff("ITP-00063", "EXIT", "MONTHLY", JAN27)
        if not (sell.held and buy.held and tariff.held):
            return None
        return sell.value - buy.value - tariff.value * 1000 / 24

    live = open_valuation_snapshot(
        session, caller=_caller(("*",)), as_of_utc=AS_OF, demo_desk=False
    )
    original = figure(live)
    live.price("XYZ", JAN27, "bid")  # a refusal is recorded too
    manifest = freeze_snapshot(session, live, purpose="test", created_by="tester")
    session.commit()

    replay = replay_snapshot(session, manifest.snapshot_id)
    assert replay is not None
    assert figure(replay) == original
    assert replay.inputs() == tuple(
        item for item in live.inputs() if item.key in {i.key for i in replay.inputs()}
    )
    assert replay.replay_misses == []
    rebuilt = replay.manifest(manifest.snapshot_id)
    assert {item.key for item in rebuilt.inputs} <= {item.key for item in manifest.inputs}
    full = replay_snapshot(session, manifest.snapshot_id)
    for item in manifest.inputs:
        full._get(item.key, lambda: None)  # noqa: SLF001 - read every recorded key back
    assert full.manifest(manifest.snapshot_id).digest() == manifest.digest()


def test_a_book_reads_its_own_approved_set_and_falls_back_to_the_firm_wide_one(session) -> None:
    """P-11: a book-owned set answers for its book; any other book, and a key the book's set
    does not hold, read the firm-wide set; the book's read replays from the snapshot."""

    yesterday = AS_OF - timedelta(hours=20)
    own = create_assumption_set(
        session, name="Book A", book_id="book-a", description="", actor="trader",
        now_utc=yesterday,
    )
    create_assumption_version(
        session,
        set_id=own["set_id"],
        values=[validate_assumption_value("capacity.load_factor", 80)],
        effective_from=date(2026, 10, 1),
        effective_to=None,
        note="",
        actor="trader",
        now_utc=yesterday,
    )
    approve_assumption_version(session, set_id=own["set_id"], version=1, actor="risk",
                               now_utc=yesterday)
    session.commit()

    reader = open_valuation_snapshot(
        session, caller=_caller(("*",)), as_of_utc=AS_OF, demo_desk=False
    )
    firm = reader.assumption("capacity.load_factor")
    assert firm.value == Decimal("100") and firm.detail["book_id"] is None
    mine = reader.assumption("capacity.load_factor", "book-a")
    assert mine.value == Decimal("80") and mine.detail["book_id"] == "book-a"
    assert mine.key == "assumption:capacity.load_factor@book:book-a"
    assert mine.detail["set_name"] == "Book A"
    # Another book has no set of its own: the firm-wide value, not book A's.
    assert reader.assumption("capacity.load_factor", "book-b").value == Decimal("100")
    # Book A's set does not hold the key: the firm-wide set answers (here: nothing).
    assert reader.assumption("financing.rate", "book-a").input_class is InputClass.MISSING

    manifest = freeze_snapshot(session, reader, purpose="test", created_by="tester")
    session.commit()
    replay = replay_snapshot(session, manifest.snapshot_id)
    assert replay.assumption("capacity.load_factor", "book-a").value == Decimal("80")
    assert replay.assumption("capacity.load_factor", "book-b").value == Decimal("100")
    assert replay.replay_misses == []
