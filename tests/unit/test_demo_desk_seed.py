"""The fictional demo desk: invented names, flagged prices, limits that tell a known story."""

from __future__ import annotations

import importlib.util
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import eurogas_nexus.db.models  # noqa: F401  (registers every table)
from eurogas_nexus.core.config import demo_marks_allowed
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import (
    CreditLineRecord,
    MarketObservationRecord,
    UpstreamResourceContractRecord,
)

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "demo" / "seed_demo_desk.py"
REAL_FIRMS = ("centrica", "equinor", "rwe", "shell", "bp ", "uniper", "engie", "eni ", "orsted")


def _load():
    spec = importlib.util.spec_from_file_location("seed_demo_desk", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db


def test_limits_are_sized_from_the_book_into_ok_watch_and_breach(session):
    seed = _load()
    sizing = seed.seed(session, datetime(2026, 11, 7, 9, tzinfo=UTC))
    session.commit()

    utilisation = {cpty: row["net"] / row["limit"] for cpty, row in sizing.items()}
    assert utilisation["ALD"] < 0.75  # ok
    assert 0.75 <= utilisation["NVK"] <= 1.0  # watch
    assert utilisation["RHM"] > 1.0  # breach, with a stated cause
    assert "letter of credit" in sizing["RHM"]["why"]
    assert session.query(CreditLineRecord).count() == 3


def test_every_name_is_fictional_and_every_price_is_flagged(session):
    seed = _load()
    seed.seed(session, datetime(2026, 11, 7, 9, tzinfo=UTC))
    session.commit()

    names = [line.name.lower() for line in session.query(CreditLineRecord)]
    names += [c.contract_name.lower() for c in session.query(UpstreamResourceContractRecord)]
    for name in names:
        assert not any(firm in f"{name} " for firm in REAL_FIRMS), name
    prices = session.query(MarketObservationRecord).all()
    assert prices
    assert all(row.source_system.endswith("_Sim") for row in prices)
    assert all((row.metadata_json or {}).get("simulated") is True for row in prices)


def test_reseeding_replaces_the_demo_rows(session):
    seed = _load()
    now = datetime(2026, 11, 7, 9, tzinfo=UTC)
    seed.seed(session, now)
    session.commit()
    seed.seed(session, now)
    session.commit()
    assert session.query(CreditLineRecord).count() == 3
    # Three supply contracts, the cross-border position (TTF sold at NBP through BBL) and one
    # contract of each typed kind (an LNG master, a cargo under it, an upstream tender).
    assert session.query(UpstreamResourceContractRecord).count() == 7


def test_the_seed_refuses_release_and_demo_marks_stay_off_by_default(monkeypatch, capsys):
    monkeypatch.setenv("EUROGAS_NEXUS_ENV", "release")
    assert _load().main() == 2
    assert "refused" in capsys.readouterr().err

    monkeypatch.setenv("EUROGAS_NEXUS_DEMO_MARKS", "true")
    assert demo_marks_allowed() is False  # never in trial or release

    monkeypatch.setenv("EUROGAS_NEXUS_ENV", "development")
    monkeypatch.delenv("EUROGAS_NEXUS_DEMO_MARKS")
    assert demo_marks_allowed() is False  # off unless asked for
    monkeypatch.setenv("EUROGAS_NEXUS_DEMO_MARKS", "true")
    assert demo_marks_allowed() is True


def test_market_around_the_book_is_simulated_and_fills_the_balance_and_map(session):
    from datetime import date

    from eurogas_nexus.application.map_situation import build_map_situation
    from eurogas_nexus.application.pipeline_supply import landed_supply
    from eurogas_nexus.db.models import FlowObservationRecord, ReferenceNode
    from eurogas_nexus.db.models.observation import (
        LngObservationRecord,
        StorageObservationRecord,
    )
    from eurogas_nexus.db.models.power import PowerObservationRecord

    now = datetime(2026, 11, 7, 9, tzinfo=UTC)
    seed = _load()
    seed.seed(session, now)
    session.commit()

    assert session.query(ReferenceNode).count() > 200  # the shipped reference network
    for model in (FlowObservationRecord, StorageObservationRecord, LngObservationRecord):
        rows = session.query(model).all()
        assert rows
        assert all(row.source_system == "DEMO_Sim" for row in rows)
        assert all((row.metadata_json or {}).get("simulated") is True for row in rows)
    power = session.query(PowerObservationRecord).all()
    assert power and all(row.source_system == "DEMO_Sim" for row in power)
    # No simulated power price: it could be read as a market price.
    assert not {row.metric for row in power} & {"day_ahead_price", "market_index_price"}

    supply = landed_supply(session, date(2025, 9, 1), as_of=now)
    assert len(supply.by_day) >= 395  # 400 gas days, every landing point every day
    assert supply.incomplete_days == []
    assert 3_000 < max(supply.by_day.values()) < 7_000  # GWh/d, a believable NWE landing

    payload = build_map_situation(session, now=now, entitled=lambda rows: list(rows))
    assert len(payload["flows"]) >= 20

    # Simulated market LNG vessels (Kpler_Sim) heading to NW Europe terminals, counted as such.
    vessels = [cargo for cargo in payload["cargoes"] if not cargo["own"]]
    assert len(vessels) == 5
    assert all(cargo["source_system"] == "Kpler_Sim" for cargo in vessels)
    assert payload["vessel_feed"]["market_cargoes"] == 5
    assert payload["vessel_feed"]["simulated"] == 5
    # Without the licensed-feed entitlement the sea stays empty and the map says why.
    unentitled = build_map_situation(
        session,
        now=now,
        entitled=lambda rows: [row for row in rows if not row["source_system"].startswith("Kpler")],
        vessel_feed_entitled=False,
    )
    assert unentitled["vessel_feed"] == {
        "entitled": False,
        "market_cargoes": 0,
        "simulated": 0,
        "families": ["Kpler"],
    }


def test_simulated_vessels_step_aside_for_a_real_vessel_feed(session):
    from eurogas_nexus.db.models.lng_positions import LngCargoRecord

    seed = _load()
    now = datetime(2026, 11, 7, 9, tzinfo=UTC)
    seed.seed(session, now)
    session.commit()
    real = LngCargoRecord(
        cargo_id="kpler-1",
        vessel_name="Real vessel",
        status="laden",
        load_port="Port",
        source_system="Kpler",
        source_reference="kpler:export",
        updated_at_utc=now,
    )
    session.add(real)
    session.flush()
    removed = seed.retire_simulated_series(session)
    assert removed["vessels"] == 5
    assert session.query(LngCargoRecord).filter_by(source_system="Kpler_Sim").count() == 0


def test_reseeding_keeps_one_copy_of_the_simulated_history(session):
    from eurogas_nexus.db.models import FlowObservationRecord

    seed = _load()
    now = datetime(2026, 11, 7, 9, tzinfo=UTC)
    seed.seed(session, now)
    session.commit()
    first = session.query(FlowObservationRecord).count()
    seed.seed(session, now)
    session.commit()
    assert session.query(FlowObservationRecord).count() == first


# --- roll-forward after a paused server ----------------------------------------------


def _snapshot(session):
    """Every stored demo row's key and value, to prove earlier rows are never rewritten."""

    from eurogas_nexus.db.models import FlowObservationRecord, PowerObservationRecord
    from eurogas_nexus.db.models.observation import LngObservationRecord, StorageObservationRecord

    rows = {}
    for model, value in (
        (FlowObservationRecord, "original_value"),
        (StorageObservationRecord, "inventory_twh"),
        (LngObservationRecord, "send_out_twh_d"),
        (PowerObservationRecord, "value"),
        (MarketObservationRecord, "price"),
    ):
        for row in session.query(model):
            rows[(model.__name__, row.observation_id)] = getattr(row, value)
    return rows


def test_roll_forward_after_a_30_day_pause_ends_at_today_and_keeps_every_stored_row(session):
    from sqlalchemy import func

    from eurogas_nexus.db.models import (
        ContractDeliveryRecord,
        FlowObservationRecord,
        PowerObservationRecord,
    )

    seed = _load()
    seeded_at = datetime(2026, 10, 8, 9, tzinfo=UTC)
    seed.seed(session, seeded_at, history_days=40)
    session.commit()
    # A tester's own edit to a demo row and a tester's own contract must survive.
    line = session.get(CreditLineRecord, "RHM")
    line.limit_amount = 5_000_000
    session.add(
        UpstreamResourceContractRecord(
            contract_id="tester-own-1", contract_name="Tester contract",
            resource_type="PIPELINE_IMPORT", delivery_point_name="TTF", gas_year="2026/27",
            delivery_quantity_mwh_per_day=1000.0, contract_price_gbp_mwh=30.0,
            settlement_frequency="monthly", upstream_payment_lag_days=20,
            screen_sale_cash_lag_days=1, delivery_tolerance_pct=5.0,
            nomination_tolerance_pct=2.0, annual_financing_rate_pct=5.0,
            allowed_exit_points=["TTF"], eligible_sale_modes=["LOCAL_MARKET_SALE"],
            created_at_utc=seeded_at, updated_at_utc=seeded_at,
        )
    )
    session.commit()
    before = _snapshot(session)

    later = datetime(2026, 11, 7, 9, tzinfo=UTC)  # the server was paused for 30 days
    counts = seed.roll_forward(session, later)
    session.commit()

    after = _snapshot(session)
    assert all(after[key] == value for key, value in before.items())  # nothing rewritten
    assert counts["physical_rows"] > 0
    # Oct 8 to Nov 6, every hub of the demo market.
    assert counts["month_ahead_rows"] == len(seed.DEMO_PRICE_HUBS) * 30
    newest_flow = session.query(func.max(FlowObservationRecord.period_start_utc)).scalar()
    assert seed._gas_day_of(newest_flow) == seed._closed_gas_days(later, 1)[0][0]
    newest_power = session.query(func.max(PowerObservationRecord.period_start_utc)).scalar()
    assert newest_power.date() == datetime(2026, 11, 6).date()
    curve = (
        session.query(MarketObservationRecord)
        .filter(MarketObservationRecord.source_reference == "demo:curve")
        .order_by(MarketObservationRecord.observed_at_utc.desc())
        .first()
    )
    assert curve.observed_at_utc.date() == later.date()
    assert all(
        (row.metadata_json or {}).get("simulated") is True
        for row in session.query(MarketObservationRecord)
    )
    # Every gas day of the pause is filled up to yesterday; today holds the nomination the
    # demo gas day records (``seed_demo_gas_day``), its allocation still pending.
    days = {day for (day,) in session.query(ContractDeliveryRecord.gas_day).filter(
        ContractDeliveryRecord.contract_id == "demo-haldor-24")}
    assert max(days) == datetime(2026, 11, 7).date()
    assert datetime(2026, 11, 6).date() in days and datetime(2026, 10, 20).date() in days
    assert session.get(ContractDeliveryRecord, ("demo-haldor-24", max(days))).allocated_mwh is None
    assert counts["outage_rows"] == 2  # the demo outages had ended during the pause
    assert session.get(CreditLineRecord, "RHM").limit_amount == 5_000_000
    assert session.get(UpstreamResourceContractRecord, "tester-own-1") is not None

    # Idempotent: a second start the same day adds nothing.
    total = len(after)
    again = seed.roll_forward(session, later)
    session.commit()
    assert again.get("physical_rows", 0) == 0
    assert again["curve_rows"] == again["month_ahead_rows"] == again["delivery_rows"] == 0
    assert again["outage_rows"] == 0
    assert len(_snapshot(session)) == total


def test_roll_forward_leaves_an_unseeded_store_alone(session):
    seed = _load()
    assert seed.roll_forward(session, datetime(2026, 11, 7, 9, tzinfo=UTC)) == {"seeded": 0}


def test_real_public_data_replaces_the_simulated_series_it_covers(session):
    """Once a real provider stored a series, the simulated one of the same scope goes: no
    reader mixes the two in one series or sums both. Only demo rows are removed, and a
    later roll-forward does not bring them back; the demo book and its prices stay."""

    from sqlalchemy import func

    from eurogas_nexus.db.models import FlowObservationRecord, FxObservationRecord
    from eurogas_nexus.db.models.observation import StorageObservationRecord

    seed = _load()
    seeded_at = datetime(2026, 11, 7, 9, tzinfo=UTC)
    seed.seed(session, seeded_at, history_days=20)
    session.commit()
    day = datetime(2026, 11, 5, 5, tzinfo=UTC)
    session.add_all([
        StorageObservationRecord(
            observation_id="gie-agsi-de", source_dataset="AGSI", facility_id="DE",
            facility_name="Germany", country="DE", inventory_twh=200.0,
            working_capacity_twh=250.0, fill_pct=80.0, period_start_utc=day,
            period_end_utc=day.replace(day=6), observed_at_utc=seeded_at, source_system="GIE",
            source_reference="gie", freshness="daily", research_only=True,
        ),
        StorageObservationRecord(
            observation_id="gie-agsi-eu", source_dataset="AGSI", facility_id="eu",
            facility_name="EU", country="eu", inventory_twh=900.0,
            working_capacity_twh=1100.0, fill_pct=81.0, period_start_utc=day,
            period_end_utc=day.replace(day=6), observed_at_utc=seeded_at, source_system="GIE",
            source_reference="gie", freshness="daily", research_only=True,
        ),
        FxObservationRecord(
            observation_id="ecb-gbp", pair="EURGBP", base_currency="EUR", quote_currency="GBP",
            rate=0.84, rate_type="reference", value_date="2026-11-06", observed_at_utc=seeded_at,
            source_system="ECB", source_reference="ecb", freshness="live", research_only=True,
        ),
    ])
    session.commit()
    sim_flows = session.query(FlowObservationRecord).count()
    # The demo holds a daily EUR/GBP history (for conversions at each day's rate): all of it goes.
    sim_gbp = (
        session.query(FxObservationRecord)
        .filter_by(pair="EURGBP", source_system=seed.SOURCE)
        .count()
    )

    removed = seed.retire_simulated_series(session)
    session.commit()

    def storage(country):
        return {
            source for (source,) in session.query(StorageObservationRecord.source_system)
            .filter(func.upper(StorageObservationRecord.country) == country).distinct()
        }

    assert storage("DE") == {"GIE"} and storage("EU") == {"GIE"}  # "eu" covers "EU"
    assert storage("FR") == {seed.SOURCE}  # not covered: stays simulated, labelled so
    pairs = {
        (row.pair, row.source_system) for row in session.query(FxObservationRecord)
    }
    assert ("EURGBP", seed.SOURCE) not in pairs and ("EURUSD", seed.SOURCE) in pairs
    assert removed["storage"] == 40 and removed["fx"] == sim_gbp > 1
    assert "flows" not in removed and session.query(FlowObservationRecord).count() == sim_flows
    assert session.query(MarketObservationRecord).count() > 0  # demo prices stay

    # Real flows arrive: the simulated network flows go; a roll-forward keeps them gone and
    # still rolls the demo book forward.
    session.add(seed._flow_row("entsog-x", "Real point", "OP", "entry", 10.0, day.date(), day,
                               day.replace(day=6), seeded_at))
    session.query(FlowObservationRecord).filter(
        FlowObservationRecord.observation_id.like("demo-%"),
        FlowObservationRecord.point_id == "entsog-x",
    ).update({"source_system": "ENTSOG", "observation_id": "entsog-real-x"},
             synchronize_session=False)
    session.commit()
    assert seed.retire_simulated_series(session)["flows"] == sim_flows
    session.commit()
    counts = seed.roll_forward(session, datetime(2026, 11, 12, 9, tzinfo=UTC))
    session.commit()
    assert counts["month_ahead_rows"] > 0
    assert {
        source for (source,) in session.query(FlowObservationRecord.source_system).distinct()
    } == {"ENTSOG"}
    assert storage("DE") == {"GIE"}


def test_demo_rates_convert_forward_and_give_way_to_real_fixings(session):
    """The demo holds daily simulated EUR reference rates and SONIA/€STR/SOFR fixings, so a
    demo price converts at its own day's rates (and a forward month at the derived forward,
    marked simulated). A real fixing of the same benchmark and day replaces the demo one
    instead of failing the one-fixing-per-day constraint."""

    from datetime import date

    from eurogas_nexus.application.market_normalisation import normalise_value
    from eurogas_nexus.db.models import FxObservationRecord, InterestRateObservationRecord
    from eurogas_nexus.domain.market.fx_forward import Delivery, FxHoldings
    from eurogas_nexus.domain.market.interest_rates import RateFixing

    seed = _load()
    seed.seed(session, datetime(2026, 11, 7, 9, tzinfo=UTC), history_days=20)
    session.commit()
    fixings = session.query(InterestRateObservationRecord).all()
    assert {row.benchmark_id for row in fixings} == {"SONIA", "ESTR", "SOFR"}
    assert all(row.source_system == seed.SOURCE for row in fixings)
    holdings = FxHoldings.from_rows(
        [
            {"pair": r.pair, "rate": r.rate, "rate_type": r.rate_type, "value_date": r.value_date,
             "source_system": r.source_system}
            for r in session.query(FxObservationRecord).all()
        ],
        [
            {"benchmark_id": r.benchmark_id, "value_date": r.value_date, "rate_pct": r.rate_pct,
             "source_system": r.source_system}
            for r in fixings
        ],
    )
    converted = normalise_value(
        78.0, "p/th", "EUR/MWh", holdings=holdings, as_of=date(2026, 11, 6),
        delivery=Delivery(date(2027, 1, 1), date(2027, 1, 31), "month", "Jan-27"),
    )
    assert converted["simulated"] is True
    assert converted["normalisation"]["fx"]["method"] == "derived: covered interest parity"
    # Twelve days earlier the demo still holds that day's rates.
    assert normalise_value(
        78.0, "p/th", "EUR/MWh", holdings=holdings, as_of=date(2026, 10, 26)
    )["simulated"] is True

    spec = importlib.util.spec_from_file_location(
        "ingest_interest_rates", SCRIPT.parent.parent / "ops" / "ingest_interest_rates.py"
    )
    ingest = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ingest)
    real = RateFixing("SONIA", date(2026, 11, 6), 3.7271, "BOE", "boe-iadb:IUDSOIA")
    assert ingest.upsert(session, [real], now=datetime(2026, 11, 7, 10, tzinfo=UTC)) == (1, 0)
    session.commit()
    on_day = session.query(InterestRateObservationRecord).filter_by(
        benchmark_id="SONIA", value_date=date(2026, 11, 6)
    ).all()
    assert [(row.source_system, row.rate_pct) for row in on_day] == [("BOE", 3.7271)]
def test_the_running_unplanned_demo_outage_is_revised_so_it_stays_news(session):
    """The strip shows an outage for six hours after it is published: the demo revises its
    unplanned outage after five, so a demo opened at any hour has one live urgent item."""

    from eurogas_nexus.db.models import RemitUmmRecord

    seed = _load()
    seeded_at = datetime(2026, 11, 7, 9, tzinfo=UTC)
    seed.seed(session, seeded_at, history_days=10)
    session.commit()
    # Within five hours of the last publication: nothing new.
    assert seed._roll_outages(session, seeded_at + timedelta(hours=1)) == 0
    later = seeded_at + timedelta(hours=6)
    assert seed._roll_outages(session, later) == 1
    session.commit()
    revised = (
        session.query(RemitUmmRecord)
        .filter(RemitUmmRecord.message_id == "demo-umm-1")
        .order_by(RemitUmmRecord.version.desc())
        .first()
    )
    assert revised.version == 2 and revised.source_system == "DEMO"
    assert revised.published_at_utc.replace(tzinfo=UTC) == later
    assert revised.source_reference == "demo:umm"  # still marked as demo data
    assert revised.unavailable_capacity != 52.0  # a revision changes the size a little
    assert seed._roll_outages(session, later + timedelta(minutes=30)) == 0  # idempotent
    # The planned one is a schedule and is left as it is.
    planned = session.query(RemitUmmRecord).filter(RemitUmmRecord.message_id == "demo-umm-2")
    assert planned.count() == 1


def test_every_board_hub_has_a_simulated_market_that_a_real_one_replaces(session):
    """The owner asked for a complete demo market: every hub on the board has a simulated
    curve and month-ahead history, marked simulated, and a hub a provider prices gets no
    simulated series beside the real one."""

    from eurogas_nexus.domain.ontology.markets import european_gas_hubs

    seed = _load()
    seeded_at = datetime(2026, 10, 8, 9, tzinfo=UTC)
    seed.seed(session, seeded_at, history_days=20)
    session.commit()
    hubs = {
        (row.metadata_json or {}).get("hub")
        for row in session.query(MarketObservationRecord)
        if (row.metadata_json or {}).get("tenor") == "month-ahead"
    }
    assert hubs == set(european_gas_hubs())
    assert all(
        (row.metadata_json or {}).get("simulated") is True and row.source_system.endswith("_Sim")
        for row in session.query(MarketObservationRecord)
    )
    # Plausible spreads: every continental hub within a few EUR of TTF on the same month.
    curve = {
        (row.metadata_json or {})["hub"]: row.price
        for row in session.query(MarketObservationRecord).filter_by(source_reference="demo:curve")
        if row.period_start_utc.month == 1
    }
    assert all(abs(curve[hub] - curve["TTF"]) < 4 for hub in curve if hub != "NBP")

    # A provider starts pricing THE: the roll-forward writes no simulated THE beside it.
    session.add(MarketObservationRecord(
        observation_id="eex-the-ma", market_venue="EEX", product="THE month-ahead", price=41.0,
        unit="EUR/MWh", currency="EUR", period_start_utc=datetime(2026, 11, 1, tzinfo=UTC),
        period_end_utc=datetime(2026, 12, 1, tzinfo=UTC), observed_at_utc=seeded_at,
        source_system="EEX", source_reference="eex:settlement", freshness="end_of_day",
        quality_score=1.0, research_only=True, metadata_json={"hub": "THE", "tenor": "month-ahead"},
    ))
    session.commit()
    later = datetime(2026, 10, 20, 9, tzinfo=UTC)
    seed.roll_forward(session, later)
    session.commit()
    rolled = {
        (row.metadata_json or {}).get("hub")
        for row in session.query(MarketObservationRecord)
        .filter(MarketObservationRecord.source_system == seed.SOURCE)
        .filter(MarketObservationRecord.observed_at_utc > seeded_at)
    }
    assert "THE" not in rolled and "TTF" in rolled

def test_one_case_awaits_review_and_reseeding_keeps_one_copy(session):
    from eurogas_nexus.db.models.decision import DecisionCaseRecord

    seed = _load()
    seed.seed(session, datetime(2026, 11, 7, 9, tzinfo=UTC))
    session.commit()
    seed.seed(session, datetime(2026, 11, 8, 9, tzinfo=UTC))
    session.commit()

    cases = session.query(DecisionCaseRecord).all()
    assert [case.case_id for case in cases] == [seed.DEMO_REVIEW_CASE_ID]
    case = cases[0]
    assert case.status == "UNDER_REVIEW"
    assert case.created_by == "demo.trader"  # never a reviewer's own case
    assert case.gas_day == "2026-11-08"
    assert any("simulated" in warning.lower() for warning in case.warnings_json)


def test_a_real_fixing_for_the_same_day_is_not_written_again_as_demo(session):
    """interest_rate_observations is unique on (benchmark, day) across sources."""

    from eurogas_nexus.db.models import InterestRateObservationRecord

    seed = _load()
    now = datetime(2026, 11, 18, 9, tzinfo=UTC)
    session.add(
        InterestRateObservationRecord(
            observation_id="boe-sonia-2026-11-17", benchmark_id="SONIA", currency="GBP",
            value_date=datetime(2026, 11, 17).date(), rate_pct=3.97, day_count="ACT/365F",
            source_system="BOE", source_reference="boe:iadb", ingested_at_utc=now,
        )
    )
    session.flush()
    rows = seed._new_rows_only(session, seed._demo_rate_rows(now, 3))
    pairs = {
        (row.benchmark_id, row.value_date)
        for row in rows if isinstance(row, InterestRateObservationRecord)
    }
    assert ("SONIA", datetime(2026, 11, 17).date()) not in pairs
    assert ("ESTR", datetime(2026, 11, 17).date()) in pairs


def test_the_real_price_hub_read_runs_on_postgresql() -> None:
    """The read that keeps simulated prices off a hub a provider prices is DISTINCT over the
    stated hub text: PostgreSQL has no equality operator for a `json` column, so a DISTINCT on
    the document itself stopped the demo's start there (SQLite, which these tests use, accepts
    it)."""

    from sqlalchemy.dialects import postgresql

    seed = _load()

    class _Recorder:
        def __init__(self) -> None:
            self.query = None

        def __call__(self, *columns):
            self.query = Session().query(*columns)
            return self

        def filter(self, *criteria):
            self.query = self.query.filter(*criteria)
            return self

        def distinct(self):
            self.query = self.query.distinct()
            return self

        def __iter__(self):
            return iter([])

    recorder = _Recorder()
    session = type("S", (), {"query": recorder})()
    assert seed._real_price_hubs(session) == set()
    sql = str(recorder.query.statement.compile(dialect=postgresql.dialect()))
    assert "DISTINCT" in sql
    assert "metadata_json ->> " in sql
    assert "DISTINCT market_observations.metadata_json AS" not in sql


def test_an_older_volume_gets_the_newer_fixtures_and_keeps_tester_changes(session):
    from eurogas_nexus.db.models import TsoTariffRecord
    from eurogas_nexus.db.models.decision import DecisionCaseRecord

    seed = _load()
    seeded_at = datetime(2026, 11, 7, 9, tzinfo=UTC)
    seed.seed(session, seeded_at, history_days=5)
    session.commit()
    session.query(TsoTariffRecord).delete()
    session.query(DecisionCaseRecord).delete()
    # A volume seeded before contract kinds holds none of the typed demo contracts.
    from eurogas_nexus.db.models import UpstreamResourceContractRecord as Contract

    session.query(Contract).filter(Contract.master_contract_id.isnot(None)).delete()
    session.query(Contract).filter(Contract.contract_id.in_(seed.TYPED_DEMO_CONTRACTS)).delete()
    session.get(CreditLineRecord, "RHM").limit_amount = 5_000_000
    session.get(Contract, "demo-haldor-24").notes = "Demo contract (fictional)."
    session.commit()

    counts = seed.ensure_demo_fixtures(session, seeded_at)
    session.commit()
    assert counts == {
        "fixture_tariffs": len(seed.SIMULATED_TARIFFS),
        "fixture_review_case": 1,
        "fixture_typed_contracts": 3,
        "contract_counterparties": 1,
    }
    # A demo contract still holding the seed's plain notes gets its counterparty named once.
    haldor = session.get(Contract, "demo-haldor-24")
    assert json.loads(haldor.notes)["counterparty"] == "Nordvik Petroleum ASA"
    kinds = {row.contract_id: row.contract_kind for row in session.query(Contract).all()}
    assert kinds["demo-mspa-atlantic-cn07"] == "LNG_CARGO"
    assert session.get(Contract, "demo-tender-skarv").kind_terms["schema"] == "upstream-tender/v2"
    assert session.get(CreditLineRecord, "RHM").limit_amount == 5_000_000
    assert seed.ensure_demo_fixtures(session, seeded_at) == {}


def test_a_simulated_henry_hub_series_rolls_forward_and_gives_way_to_eia(session):
    """CP-18: the demo market's own Henry Hub stream (labelled simulated), 400 days to
    yesterday; a paused server appends only the missing days; EIA rows retire it."""

    seed = _load()
    start = datetime(2026, 11, 7, 9, tzinfo=UTC)
    seed.seed(session, start)
    session.commit()
    rows = (
        session.query(MarketObservationRecord)
        .filter(MarketObservationRecord.product == "HH spot")
        .order_by(MarketObservationRecord.period_start_utc)
        .all()
    )
    assert len(rows) == seed.HISTORY_DAYS
    assert {row.source_system for row in rows} == {"DEMO_Sim"}
    assert all(row.metadata_json["simulated"] is True for row in rows)
    assert rows[-1].period_start_utc.date() == start.date() - timedelta(days=1)
    assert all(1.0 <= row.price <= 6.0 and row.unit == "USD/MMBtu" for row in rows)

    later = start + timedelta(days=5)
    assert seed._roll_henry_hub(session, later) == 5
    assert seed._roll_henry_hub(session, later) == 0  # nothing twice
    session.add(
        MarketObservationRecord(
            observation_id="eia-rngwhhd-2026-11-10",
            market_venue="EIA",
            product="HH spot",
            price=3.1,
            unit="USD/MMBtu",
            currency="USD",
            period_start_utc=datetime(2026, 11, 10, tzinfo=UTC),
            period_end_utc=datetime(2026, 11, 11, tzinfo=UTC),
            observed_at_utc=datetime(2026, 11, 10, 18, tzinfo=UTC),
            source_system="EIA",
            source_reference="eia",
            freshness="end_of_day",
            quality_score=1.0,
            research_only=True,
            metadata_json={"hub": "HH", "tenor": "spot"},
        )
    )
    session.flush()
    assert seed._roll_henry_hub(session, later + timedelta(days=1)) == 0
    left = session.query(MarketObservationRecord).filter_by(product="HH spot").all()
    assert [row.source_system for row in left] == ["EIA"]


def test_an_older_volume_gets_bands_storage_and_assumptions_but_not_removed_contracts(session):
    """Live finding 2026-11-19: a volume seeded by an older build showed "approved hedge
    bands: 0" and listed no storage spread. The top-up adds the bands of the demo contracts
    that still exist, the firm storage at CEGH and the demo assumption set; a contract a
    tester removed is not re-added, nor is its band."""

    from eurogas_nexus.db.models import (
        AssumptionSetRecord,
        AssumptionSetVersionRecord,
        AssumptionValueRecord,
        HedgeApprovalRecord,
        StorageFacilityMasterRecord,
    )

    seed = _load()
    seeded_at = datetime(2026, 11, 7, 9, tzinfo=UTC)
    seed.seed(session, seeded_at, history_days=2)
    session.commit()
    # What an older build left behind: no bands, no storage, no assumption set.
    session.query(HedgeApprovalRecord).delete()
    session.query(AssumptionValueRecord).delete()
    session.query(AssumptionSetVersionRecord).delete()
    session.query(AssumptionSetRecord).delete()
    session.query(StorageFacilityMasterRecord).delete()
    session.commit()

    counts = seed.ensure_demo_fixtures(session, seeded_at)
    session.commit()
    # The demo gas day's cash-out sets (one per book) were removed with the other sets.
    assert counts == {"fixture_hedge_approvals": 1, "fixture_storage": 1,
                      "fixture_assumption_set": 1, "fixture_cash_out_sets": 2}
    assert session.get(HedgeApprovalRecord, "demo-haldor-24") is not None
    assert session.get(StorageFacilityMasterRecord, seed.DEMO_STORAGE_ID).market_hub == "CEGH"
    version = session.get(AssumptionSetVersionRecord, seed.DEMO_ASSUMPTION_VERSION_ID)
    assert version.review_state == "approved"
    fees = {
        row.key: float(row.value)
        for row in session.query(AssumptionValueRecord).filter(
            AssumptionValueRecord.version_id == version.version_id)
    }
    assert set(fees) == {"storage.capacity_fee", "storage.injection_fee",
                         "storage.withdrawal_fee"}
    assert sum(fees.values()) == pytest.approx(3.8)
    assert seed.ensure_demo_fixtures(session, seeded_at) == {}

    # A tester removed the Haldor contract: its band does not come back.
    session.query(HedgeApprovalRecord).delete()
    session.query(UpstreamResourceContractRecord).filter(
        UpstreamResourceContractRecord.contract_id == "demo-haldor-24").delete()
    session.commit()
    assert "fixture_hedge_approvals" not in seed.ensure_demo_fixtures(session, seeded_at)
    assert session.get(UpstreamResourceContractRecord, "demo-haldor-24") is None


def test_the_board_quotes_the_gas_day_the_desk_trades_on(session, monkeypatch):
    """On gas day D the desk reads D's prompt: WD is gas day D, DA the next quoted day; WD and
    DA are a running snapshot per roll-forward, with a size and a last inside bid and offer.
    With the demo exchange feed running, the roll-forward writes no WD or DA of its own."""

    from eurogas_nexus.db.models import MarketQuoteRecord

    seed = _load()
    monkeypatch.delenv(seed.EXCHANGE_FEED_SETTING, raising=False)
    thursday = datetime(2026, 12, 3, 9, tzinfo=UTC)
    seed.seed(session, thursday, history_days=3)
    session.commit()
    quotes = session.query(MarketQuoteRecord).filter(MarketQuoteRecord.hub == "TTF").all()
    by_code = {q.metadata_json["rolling_code"]: q for q in quotes}
    wd, da = by_code["WD"], by_code["DA"]
    assert wd.delivery_start_utc.date().isoformat() == "2026-12-03"
    assert da.delivery_start_utc.date().isoformat() == "2026-12-04"
    for quote in (wd, da):
        assert quote.simulated and quote.bid_price < quote.ask_price
        assert quote.bid_price <= quote.last_price <= quote.ask_price
        assert quote.bid_quantity_mwh and quote.ask_quantity_mwh
        assert quote.metadata_json["trading_day"] == "2026-12-03"
    # A later roll-forward the same day adds a new WD/DA snapshot, not a second curve.
    later = thursday + timedelta(hours=1)
    counts = seed.roll_forward(session, later)
    session.commit()
    hubs = {hub for hub, _currency in seed.DEMO_PRICE_HUBS}
    assert counts["market_quote_rows"] == 2 * len(hubs)
    monkeypatch.setenv(seed.EXCHANGE_FEED_SETTING, "true")
    assert seed.roll_forward(session, later + timedelta(hours=1))["market_quote_rows"] == 0


def test_a_friday_board_quotes_monday_as_day_ahead(session):
    from eurogas_nexus.db.models import MarketQuoteRecord

    seed = _load()
    friday = datetime(2026, 12, 4, 9, tzinfo=UTC)
    seed.seed(session, friday, history_days=2)
    session.commit()
    codes = {
        q.metadata_json["rolling_code"]: q.delivery_start_utc.date().isoformat()
        for q in session.query(MarketQuoteRecord).filter(MarketQuoteRecord.hub == "TTF")
    }
    assert codes["WD"] == "2026-12-04" and codes["DA"] == "2026-12-07"
    assert codes["WE"] == "2026-12-05"


def test_curve_months_a_year_apart_are_not_the_same_price(session):
    """QA-T-02 (seed part): the demo curve carries a small deterministic month-on-month drift,
    so the same calendar month a year further out is a different price, and the same day seeds
    the same curve."""

    seed = _load()
    seeded_at = datetime(2026, 11, 24, 9, tzinfo=UTC)
    seed.seed(session, seeded_at, history_days=5)
    session.commit()
    curve = {
        (row.period_start_utc.year, row.period_start_utc.month): row.price
        for row in session.query(MarketObservationRecord).filter_by(source_reference="demo:curve")
        if (row.metadata_json or {}).get("hub") == "TTF"
    }
    assert curve[(2027, 12)] != curve[(2026, 12)]
    assert curve[(2027, 2)] != curve[(2026, 12)]  # same season, symmetric around January
    step = seed._CURVE_SHAPE["TTF"][0] * seed.CURVE_DRIFT_PER_MONTH
    assert curve[(2027, 12)] - curve[(2026, 12)] == pytest.approx(12 * step, abs=0.002)
    assert seed._forward_curve_price("TTF", seeded_at.date(), 3) == seed._forward_curve_price(
        "TTF", seeded_at.date(), 3
    )
