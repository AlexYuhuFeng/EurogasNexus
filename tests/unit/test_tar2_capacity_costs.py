"""TAR-2 on SQLite: bookings imported, contracted before public in pipeline and terminal
costs, point-in-time reads of the tariff book, the new-final alert, the source-precedence
resolver against the store (FX and interest rates, the firm's bank first) and the migration.

Every figure here is made up; the shapes are the registers' own.
"""

from __future__ import annotations

import importlib.util
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import eurogas_nexus.db.models  # noqa: F401  (registers every table)
from eurogas_nexus.application import capacity_costs as costs
from eurogas_nexus.application import tariff_book as book
from eurogas_nexus.application.import_contracts import CONTRACTS, run_import
from eurogas_nexus.application.source_precedence import (
    order_in_force,
    resolve_fx_rate,
    resolve_interest_rate,
)
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import (
    CapacityBookingRecord,
    FxObservationRecord,
    InterestRateObservationRecord,
    LngTerminalOperatorTermsRecord,
    MarketEventRecord,
    OrganisationSettingRecord,
    TariffVersionRecord,
)
from tests.unit.test_tariff_book import entsog_row, lng_row

ROOT = Path(__file__).resolve().parents[2]
T0 = datetime(2026, 11, 20, 9, tzinfo=UTC)
AS_OF = datetime(2026, 11, 25, 12, tzinfo=UTC)

BOOKINGS = (
    "booking_id,kind,facility,first_gas_day,last_gas_day,quantity,quantity_unit,acquired_via,"
    "price,price_unit,operator,product\n"
    "LT-7,exit,ITP-1,2026-10-01,2027-09-30,2500,kWh/h,long_term,3.65,EUR/(kWh/h)/y,"
    "Operator A,ANNUAL\n"
    "SLOT-3,lng_slot,zeebrugge:term,2027-03-01,2027-03-31,1,slot,auction,450000,EUR/slot,,\n"
)


@pytest.fixture()
def session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def daily_row(value, *, gas_year="2026/27", start=date(2026, 10, 1), status="INDICATIVE",
              refs=(), at=T0):
    row = entsog_row(value, status, at=at, refs=refs)
    row.tariff_id = f"entsog-ITP-1-exit-daily-{start.year}"
    row.capacity_product = "DAILY"
    row.unit = "EUR/(kWh/h)/d"
    row.gas_year = gas_year
    row.effective_from = datetime.combine(start, datetime.min.time(), tzinfo=UTC)
    row.effective_to = datetime.combine(
        date(start.year + 1, 9, 30), datetime.min.time(), tzinfo=UTC
    )
    return row


def booked(session, text=BOOKINGS, *, at=T0):
    report = run_import("etrm.capacity_bookings.v1", text, system="Endur", session=session,
                        commit=True, now=at)
    assert not report.refused, report.as_dict()
    session.flush()
    return report


# ----------------------------------------------------------------- bookings import


def test_bookings_import_upserts_and_a_released_booking_stays_readable_as_of_before(session):
    first = booked(session)
    assert (first.created, first.updated, first.unchanged) == (2, 0, 0)
    again = booked(session, at=T0 + timedelta(hours=1))
    assert again.unchanged == 2
    record = session.get(CapacityBookingRecord, "ENDUR:LT-7")
    assert (record.direction, record.quantity_basis, record.currency) == ("EXIT", "per_day", "EUR")
    released = BOOKINGS.replace("acquired_via,price", "acquired_via,price").splitlines()
    text = released[0] + ",status\n" + released[1] + ",RELEASED\n"
    gone = booked(session, text, at=T0 + timedelta(days=2))
    assert gone.removed == 1
    assert [r.booking_id for r in costs.bookings_as_of(session, as_of=T0 + timedelta(days=1),
                                                       kinds=("exit",))] == ["ENDUR:LT-7"]
    assert costs.bookings_as_of(session, as_of=T0 + timedelta(days=3), kinds=("exit",)) == []


def test_a_booking_row_that_breaks_the_contract_is_refused_with_its_reason(session):
    bad = (
        "booking_id,kind,facility,first_gas_day,last_gas_day,quantity,quantity_unit,acquired_via\n"
        "X,lng_slot,t,2027-01-01,2027-01-31,1,MWh/d,auction\n"
        "Y,exit,p,2027-02-01,2027-01-01,10,MWh/d,auction\n"
        "Z,exit,p,2027-01-01,2027-01-31,10,MWh/d,barter\n"
    )
    report = run_import("etrm.capacity_bookings.v1", bad, system="Endur", session=session)
    assert sorted(item.reason_code for item in report.refused) == [
        "acquired_via_unknown", "period_reversed", "unit_unknown"
    ]
    assert report.file_refused
    assert {"etrm.capacity_bookings.v1", "bank.fx_rates.v1", "bank.interest_rates.v1"} <= set(
        CONTRACTS
    )


# ------------------------------------------- worked example: pipeline, contracted + DA


def test_long_term_capacity_covers_part_and_the_rest_is_priced_at_the_day_ahead_reserve(
    session,
):
    session.merge(daily_row(0.0125, status="FINAL"))
    session.flush()
    book.capture_tariffs(session, now_utc=T0)
    booked(session)
    out = costs.pipeline_cost(
        session, point_key="ITP-1", direction="EXIT", first=date(2027, 1, 1),
        last=date(2027, 1, 31), mwh_per_day=100.0, product="DAILY", premium=0.05, as_of=AS_OF,
    )
    contracted, public = out["layers"]
    assert contracted["layer"] == "contracted" and contracted["booking_id"] == "ENDUR:LT-7"
    assert contracted["quantity"] == pytest.approx(60.0 * 31)
    assert contracted["unit_cost"] == pytest.approx(3.65 / 365 / 24 * 1000)  # 0.4167 EUR
    assert public["layer"] == "public" and public["quantity"] == pytest.approx(40.0 * 31)
    assert public["how_bought"] == "day-ahead auction reserve price"
    assert public["unit_cost"] == pytest.approx(0.0125 / 24 * 1000 + 0.05)  # 0.5708 EUR
    assert (public["status"], public["tariff_year"]) == ("FINAL", "GY 2026/27")
    assert public["version_id"] and public["recorded_at"]
    assert out["total_cost"] == pytest.approx(775.0 + 1240 * (0.0125 / 24 * 1000 + 0.05), abs=0.01)
    assert out["total_cost"] == 1482.83
    assert [s["tier"] for s in out["sources"] if s["used"]] == ["contracted", "public_final"]
    assert out["complete"] and not out["indicative"]


def test_with_no_booking_and_no_tariff_the_cost_is_not_held_never_zero(session):
    out = costs.pipeline_cost(
        session, point_key="ITP-9", direction="ENTRY", first=date(2027, 1, 1),
        last=date(2027, 1, 2), mwh_per_day=10.0, as_of=AS_OF,
    )
    assert out["total_cost"] is None and out["covered"]["not_held"] == 20.0
    assert all(not s["used"] for s in out["sources"])


# --------------------------------------------------------------- point in time


def test_a_later_final_does_not_change_an_earlier_as_of_result(session):
    stated = ["remarks: indicative reserve prices"]
    session.merge(daily_row(0.0125, status="INDICATIVE", refs=stated))
    session.flush()
    book.capture_tariffs(session, now_utc=T0)
    before = costs.pipeline_cost(
        session, point_key="ITP-1", direction="EXIT", first=date(2027, 1, 1),
        last=date(2027, 1, 1), mwh_per_day=10.0, product="DAILY", as_of=T0 + timedelta(hours=1),
    )
    later = T0 + timedelta(days=3)
    session.merge(daily_row(0.0150, status="FINAL", refs=["remarks: final reserve prices"],
                            at=later))
    session.flush()
    book.capture_tariffs(session, now_utc=later)
    again = costs.pipeline_cost(
        session, point_key="ITP-1", direction="EXIT", first=date(2027, 1, 1),
        last=date(2027, 1, 1), mwh_per_day=10.0, product="DAILY", as_of=T0 + timedelta(hours=1),
    )
    now = costs.pipeline_cost(
        session, point_key="ITP-1", direction="EXIT", first=date(2027, 1, 1),
        last=date(2027, 1, 1), mwh_per_day=10.0, product="DAILY", as_of=later,
    )
    assert again == before
    assert before["layers"][0]["status"] == "INDICATIVE" and before["indicative"]
    assert now["layers"][0]["status"] == "FINAL"
    assert now["total_cost"] > before["total_cost"]
    years = book.tariff_years(session, facility_id="ITP-1", product="DAILY")["years"]
    assert years[0]["INDICATIVE"]["value"] == 0.0125 and years[0]["FINAL"]["value"] == 0.015
    assert years[0]["used"] == "FINAL" and years[0]["tariff_year"]["label"] == "GY 2026/27"
    early = book.tariff_years(session, facility_id="ITP-1", product="DAILY",
                              as_of=T0 + timedelta(hours=1))["years"]
    assert early[0]["FINAL"] is None and early[0]["used"] == "INDICATIVE"


def test_a_period_across_two_tariff_years_splits_and_the_rule_is_read_as_of_t(session):
    session.merge(daily_row(0.0125))
    session.merge(daily_row(0.0200, gas_year="2027/28", start=date(2027, 10, 1)))
    session.flush()
    book.capture_tariffs(session, now_utc=T0)

    def cost(as_of):
        return costs.pipeline_cost(
            session, point_key="ITP-1", direction="EXIT", first=date(2027, 9, 29),
            last=date(2027, 10, 2), mwh_per_day=10.0, product="DAILY", as_of=as_of,
        )

    june = cost(datetime(2027, 6, 1, tzinfo=UTC))
    years = [(x["tariff_year"], x["status"], x["quantity"]) for x in june["layers"]]
    assert years == [("GY 2026/27", "FINAL", 20.0), ("GY 2027/28", "INDICATIVE", 20.0)]
    assert june["indicative"]
    # After the yearly auction of 5 July 2027 the same rows read final (NC TAR Art. 29).
    august = cost(datetime(2027, 8, 1, tzinfo=UTC))
    assert {x["status"] for x in august["layers"]} == {"FINAL"}
    assert august["layers"][1]["status_basis"] == "nc_tar_yearly_auction_held"


# ------------------------------------------ applied: route pricing and contract costs


def test_route_pricing_takes_the_booked_part_first_and_the_rest_at_the_public_rate():
    from eurogas_nexus.application.route_tariff_cost import LegBooking, price_leg
    from eurogas_nexus.domain.tariffs.precedence import Held

    spec = type("Spec", (), {"point_key": "ITP-1", "point_name": "Point one",
                             "tso": "Operator A", "direction": "EXIT",
                             "role": "market_area_exit"})
    row = {
        "tariff_id": "entsog-ITP-1-exit-daily-2026", "tso": "Operator A", "point_id": "ITP-1",
        "direction": "EXIT", "gas_year": "2026/27", "tariff_value": 0.0125, "currency": "EUR",
        "unit": "EUR/(kWh/h)/d", "effective_from": datetime(2026, 10, 1, tzinfo=UTC),
        "effective_to": datetime(2027, 9, 30, tzinfo=UTC), "tariff_status": "FINAL",
        "source_table": "tso_tariffs", "capacity_product": "DAILY", "firmness": "FIRM",
        "version_id": "tv-1", "version": 1, "tariff_year": "GY 2026/27",
        "status_basis": "nc_tar_tariff_in_force",
    }
    held = Held("ENDUR:LT-7", date(2026, 10, 1), date(2027, 9, 30), 60.0,
                3.65 / 365 / 24 * 1000, "EUR", acquired_via="long_term")
    booking = LegBooking("ITP-1", "EXIT", "Operator A", held)
    public = price_leg(spec, [row], date(2027, 1, 1), product="DAILY")
    assert public.cost_basis == "public" and public.value == pytest.approx(0.0125 / 24 * 1000)
    leg = price_leg(spec, [row], date(2027, 1, 1), product="DAILY", bookings=[booking],
                    mwh_per_day=100.0)
    assert leg.cost_basis == "contracted+public"
    assert [item["layer"] for item in leg.layers] == ["contracted", "public"]
    blended = (60 * 3.65 / 365 / 24 * 1000 + 40 * 0.0125 / 24 * 1000) / 100
    assert leg.value == pytest.approx(blended)
    assert leg.as_dict()["breakdown"]["sources"][0]["tier"] == "contracted"
    covered = price_leg(spec, [row], date(2027, 1, 1), product="DAILY", bookings=[booking],
                        mwh_per_day=50.0)
    assert covered.cost_basis == "contracted" and covered.input_class == "sourced"
    assert covered.value == pytest.approx(3.65 / 365 / 24 * 1000)
    # Another point's booking does not touch this leg.
    other = LegBooking("ITP-2", "EXIT", None, held)
    assert price_leg(spec, [row], date(2027, 1, 1), product="DAILY",
                     bookings=[other]).cost_basis == "public"


def test_regas_cost_uses_a_slot_the_firm_holds_before_the_terminal_terms(session):
    from eurogas_nexus.application import contract_costs

    booked(session)
    held = contract_costs.regas_cost(session, None, terminal="zeebrugge:term", month="2027-03",
                                     cargo_mwh=900_000)
    assert held["basis"] == "contracted" and held["input_class"] == "contract"
    assert held["value"] == pytest.approx(450000 / 900_000)
    assert held["breakdown"]["layers"][0]["booking_id"] == "ENDUR:SLOT-3"
    # No slot held in April: the existing terms-and-tariff path answers (here: nothing held).
    april = contract_costs.regas_cost(session, None, terminal="zeebrugge:term", month="2027-04",
                                      cargo_mwh=900_000)
    assert april["basis"] == "missing"


# ------------------------------------------------- LNG: slot at auction versus FCFS


def test_a_slot_booked_at_auction_prices_before_the_first_come_first_served_rate(session):
    session.add(LngTerminalOperatorTermsRecord(
        operator="fluxys_lng", permission_state="permitted", reference="letter 2026-11-01"
    ))
    spot = lng_row(review="REVIEWED", amount=520000.0)
    spot.product = "spot"
    session.add(spot)
    session.flush()
    book.capture_tariffs(session, now_utc=T0)
    booked(session)
    held = costs.terminal_cost(session, "zeebrugge:term", arrival=date(2027, 3, 12),
                               cargo_mwh=1_000_000, as_of=AS_OF)
    assert held["total_cost"] == 450000.0
    assert held["layers"][0]["acquired_via"] == "auction"
    fcfs = costs.terminal_cost(session, "zeebrugge:term", arrival=date(2027, 4, 12),
                               cargo_mwh=1_000_000, as_of=AS_OF)
    (layer,) = fcfs["layers"]
    assert (layer["layer"], layer["cost"], layer["status"]) == ("public", 520000.0, "FINAL")
    assert layer["how_bought"] == "first-come-first-served public rate"
    assert layer["tariff_year"] == "CY 2027" and layer["version_id"]
    assert [(s["tier"], s["reason"]) for s in fcfs["sources"]][0] == ("contracted", "not_covering")


def test_lng_3_reads_booked_send_out_as_a_contracted_offer_and_names_an_unpriced_one(session):
    from eurogas_nexus.application.lng_disruption import _contracted_offers

    text = (
        "booking_id,kind,facility,first_gas_day,last_gas_day,quantity,quantity_unit,"
        "acquired_via,price,price_unit\n"
        "SO-1,send_out,gate:term,2027-01-01,2027-03-31,2000,MWh/d,long_term,0.9,EUR/MWh\n"
        "ST-1,storage,gate:term,2027-01-01,2027-03-31,50000,MWh/d,auction,,\n"
    )
    booked(session, text)
    inputs, warnings = [], []
    offers = _contracted_offers(session, "any-book", date(2027, 1, 20), AS_OF, inputs, warnings)
    assert [(o.offer_id, o.basis, o.price_eur_mwh, o.max_mwh_per_day) for o in offers] == [
        ("booking:ENDUR:SO-1", "contracted", 0.9, 2000.0)
    ]
    assert offers[0].start == date(2027, 1, 20)
    assert any("ENDUR:ST-1" in w and "not used" in w for w in warnings)


def test_lng_3_ranks_a_booked_send_out_before_a_cheaper_quoted_offer():
    from eurogas_nexus.domain.lng.disruption import CapacityOffer, Portfolio

    day = date(2027, 3, 1)
    quoted = CapacityOffer("q", "T", "send_out", day, day, 0.5, 100.0, basis="quoted")
    mine = CapacityOffer("booking:x", "T", "send_out", day, day, 0.9, 100.0, basis="contracted")
    portfolio = Portfolio((), (), (), (quoted, mine), {})
    assert [o.offer_id for o in portfolio.offers_at("T", "send_out")] == ["booking:x", "q"]


# ------------------------------------------------------ new final: flag and alert


def test_a_new_final_is_flagged_in_the_event_and_raises_a_prominent_alert(session):
    session.merge(daily_row(0.0125, refs=["remarks: indicative"]))
    session.flush()
    book.capture_tariffs(session, now_utc=T0)
    session.merge(daily_row(0.0125, status="FINAL", refs=["remarks: final"],
                            at=T0 + timedelta(hours=1)))
    session.flush()
    book.capture_tariffs(session, now_utc=T0 + timedelta(hours=1))
    events = session.query(MarketEventRecord).order_by(MarketEventRecord.ingested_at_utc).all()
    last = events[-1]
    assert last.payload_json["new_final"] is True
    assert last.payload_json["tariff_year"] == "GY 2026/27"
    assert last.priority == 1
    assert any(key.startswith("tariff:ITP-1:EXIT:DAILY") for key in last.dependency_keys)
    alerts = [c for c in book.monitoring_candidates(session, T0 + timedelta(hours=2))
              if c.alert_type == "tariff_final_published"]
    assert len(alerts) == 1 and alerts[0].severity == "warning"
    assert "GY 2026/27" in alerts[0].title_en and "最终费率" in alerts[0].title_zh_cn
    assert book.monitoring_candidates(session, T0 + timedelta(days=5)) == [] or not [
        c for c in book.monitoring_candidates(session, T0 + timedelta(days=5))
        if c.alert_type == "tariff_final_published"
    ]


# --------------------------------------------- source precedence against the store


def _fx(session, oid, system, base, quote, rate, day, at):
    session.add(FxObservationRecord(
        observation_id=oid, pair=f"{base}{quote}", base_currency=base, quote_currency=quote,
        rate=rate, rate_type="reference", value_date=day, observed_at_utc=at,
        source_system=system, source_reference="test", freshness="daily", research_only=True,
    ))


def _banks(session, value):
    session.add(OrganisationSettingRecord(setting_key="financial_institutions", value_json=value,
                                          updated_by="admin", updated_at_utc=T0))
    session.flush()


def test_resolve_fx_rate_takes_the_contracted_bank_first_then_reference_then_ecb(session):
    _fx(session, "ecb-1", "ECB", "EUR", "USD", 1.10, "2026-11-24", T0)
    _fx(session, "wmr-1", "WMR", "EUR", "GBP", 0.86, "2026-11-24", T0)
    session.flush()
    ecb = resolve_fx_rate(session, "USD", "EUR", AS_OF, "lng_demurrage")
    assert ecb.value == pytest.approx(1 / 1.10) and ecb.used.tier == "ecb_reference"
    # No bank configured; the WM/Reuters rows held do not include USD.
    assert [t.reason for t in ecb.tiers] == ["not_configured", "not_held", "used"]
    _banks(session, {"ABCBANK": {"name": "ABC Bank", "contracted": True,
                                 "provides": ["fx", "interest"]}})
    report = run_import(
        "bank.fx_rates.v1",
        "base_currency,quote_currency,rate,value_date,rate_type\nEUR,USD,1.095,2026-11-24,mid\n",
        system="ABCBANK", session=session, commit=True, now=T0,
    )
    assert report.created == 1
    session.flush()
    bank = resolve_fx_rate(session, "USD", "EUR", AS_OF, "lng_demurrage")
    assert bank.used.tier == "contracted_bank" and bank.used.found.source == "BANK:ABCBANK"
    assert bank.value == pytest.approx(1 / 1.095)
    assert [s["used"] for s in bank.as_dict()["sources"]] == [True, False, False]
    # Nothing recorded before T0: the same question as of then holds no rate at all.
    assert resolve_fx_rate(session, "USD", "EUR", T0 - timedelta(hours=1)).value is None
    # A pair no tier quotes directly is crossed through EUR from two rates of one tier only.
    mixed = resolve_fx_rate(session, "USD", "GBP", AS_OF,
                            order=["published_reference", "ecb_reference"])
    assert mixed.value is None and [t.reason for t in mixed.tiers] == [
        "not_covering", "not_covering"
    ]
    _fx(session, "ecb-2", "ECB", "EUR", "GBP", 0.87, "2026-11-24", T0)
    session.flush()
    cross = resolve_fx_rate(session, "USD", "GBP", AS_OF,
                            order=["published_reference", "ecb_reference"])
    assert cross.value == pytest.approx(0.87 / 1.10)
    assert cross.used.found.detail["method"] == "cross_via_eur"
    stale = resolve_fx_rate(session, "USD", "EUR", AS_OF + timedelta(days=30))
    assert stale.value is None and {t.reason for t in stale.tiers} >= {"stale"}
    same = resolve_fx_rate(session, "EUR", "EUR", AS_OF)
    assert same.value == 1.0


def test_the_firms_order_reorders_fx_tiers_per_context(session):
    _fx(session, "ecb-1", "ECB", "EUR", "USD", 1.10, "2026-11-24", T0)
    _fx(session, "bank-1", "BANK:ABCBANK", "EUR", "USD", 1.095, "2026-11-24", T0)
    _banks(session, {"ABCBANK": {"name": "ABC", "contracted": True, "provides": ["fx"]}})
    session.add(OrganisationSettingRecord(
        setting_key="source_precedence",
        value_json={"fx_rate@route_cost": ["ecb_reference", "contracted_bank"]},
        updated_by="admin", updated_at_utc=T0,
    ))
    session.flush()
    assert resolve_fx_rate(session, "EUR", "USD", AS_OF, "route_cost").value == 1.10
    assert resolve_fx_rate(session, "EUR", "USD", AS_OF, "lng_demurrage").value == 1.095
    view = order_in_force(session, "fx_rate", "route_cost")
    assert view["order_source"] == "setting:fx_rate@route_cost"


def test_resolve_interest_rate_bank_then_benchmark(session):
    session.add(InterestRateObservationRecord(
        observation_id="estr-1", benchmark_id="ESTR", currency="EUR", value_date=date(2026, 11, 24),
        rate_pct=1.93, day_count="ACT/360", source_system="ECB", source_reference="t",
        ingested_at_utc=T0,
    ))
    session.flush()
    ecb = resolve_interest_rate(session, "EUR", AS_OF)
    assert ecb.value == 1.93 and ecb.used.tier == "ecb_reference"
    _banks(session, {"ABCBANK": {"name": "ABC", "contracted": True, "provides": ["interest"]}})
    run_import("bank.interest_rates.v1",
               "rate_id,currency,rate_pct,value_date\nEUR-ON,EUR,2.10,2026-11-24\n",
               system="ABCBANK", session=session, commit=True, now=T0)
    session.flush()
    bank = resolve_interest_rate(session, "EUR", AS_OF)
    assert bank.value == 2.10 and bank.used.found.detail["benchmark_id"] == "ABCBAN:EUR-ON"


# ------------------------------------------------------------------- migration


def test_0088_adds_bookings_and_the_tariff_year_and_downgrades():
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import inspect

    from eurogas_nexus.release.constants import DB_SCHEMA_REVISION

    path = ROOT / "alembic" / "versions" / "0088_tar2_capacity_bookings.py"
    spec = importlib.util.spec_from_file_location("m0088", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert (module.revision, module.down_revision) == (
        "0088_tar2_capacity_bookings", "0086_lng_disruption"
    )
    assert DB_SCHEMA_REVISION == "0089_alert_reader_state"  # later revisions follow
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as connection:
        TariffVersionRecord.__table__.create(connection)
        connection.exec_driver_sql("ALTER TABLE tariff_versions DROP COLUMN tariff_year")
        module.op = Operations(MigrationContext.configure(connection=connection))
        module.upgrade()
        inspector = inspect(connection)
        columns = {c["name"] for c in inspector.get_columns("capacity_bookings")}
        assert columns == set(CapacityBookingRecord.__table__.columns.keys())
        assert "tariff_year" in {c["name"] for c in inspector.get_columns("tariff_versions")}
        module.downgrade()
        inspector = inspect(connection)
        assert "capacity_bookings" not in inspector.get_table_names()
        assert "tariff_year" not in {c["name"] for c in inspector.get_columns("tariff_versions")}


def test_lng4_demurrage_fx_takes_the_firms_order_by_default_and_a_chosen_source_as_chosen(
    session,
):
    from eurogas_nexus.application.lng_demurrage import FxChoice, _fx_rate, fx_book

    _fx(session, "ecb-1", "ECB", "EUR", "USD", 1.10, "2026-11-24", T0)
    session.flush()
    on = AS_OF.date()
    # No bank configured: the ECB reference, as before.
    ecb = fx_book(session, None, on=on).rate("USD")
    assert ecb.source == "ECB" and ecb.units_per_eur == pytest.approx(1.10)
    _banks(session, {"ABCBANK": {"name": "ABC Bank", "contracted": True, "provides": ["fx"]}})
    _fx(session, "bank-1", "BANK:ABCBANK", "EUR", "USD", 1.095, "2026-11-24", T0)
    session.flush()
    book = fx_book(session, None, on=on)
    bank = book.rate("USD")
    assert bank.source == "BANK:ABCBANK" and bank.units_per_eur == pytest.approx(1.095)
    used = _fx_rate(session, "USD", "EUR", on, book)
    assert used.rate == pytest.approx(1 / 1.095) and used.source == "BANK:ABCBANK"
    # A rate entered by hand is used as entered, whatever the firm's order.
    manual = fx_book(session, FxChoice(source="manual", rate=1.2, rate_currency="USD"), on=on)
    assert manual.rate("USD").units_per_eur == 1.2 and manual.rate("USD").entered
    # The firm can put ECB first for this calculation.
    session.add(OrganisationSettingRecord(
        setting_key="source_precedence",
        value_json={"fx_rate@lng_demurrage": ["ecb_reference", "contracted_bank"]},
        updated_by="admin", updated_at_utc=T0,
    ))
    session.flush()
    assert fx_book(session, None, on=on).rate("USD").source == "ECB"
