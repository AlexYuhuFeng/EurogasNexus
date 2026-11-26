"""My gas day: golden balance arithmetic, units, cut-offs, scope per mandate, the demo seed."""

from __future__ import annotations

import importlib.util
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import eurogas_nexus.db.models  # noqa: F401  (registers every table)
from eurogas_nexus.application.caller import Caller
from eurogas_nexus.application.gas_day import my_gas_day, native_quantity
from eurogas_nexus.application.gas_day_checklist import checklist
from eurogas_nexus.db.base import Base
from eurogas_nexus.domain.market.hub_cutoffs import (
    last_renomination,
    nomination_deadline,
    product_cutoff,
)
from eurogas_nexus.domain.portfolio.gas_day_balance import (
    IN,
    OUT,
    Delegation,
    GasDayLine,
    balance_for,
    split_line,
)
from eurogas_nexus.security import portfolio_scope
from eurogas_nexus.security.identity import AuthenticatedPrincipal

SEED = Path(__file__).resolve().parents[2] / "scripts" / "demo" / "seed_demo_desk.py"
NOW = datetime(2026, 11, 19, 9, tzinfo=UTC)
TODAY = date(2026, 11, 19)


def _line(ref, hub, book, direction, mwh, kind="supply"):
    return GasDayLine(ref=ref, hub=hub, book_id=book, direction=direction, kind=kind,
                      label=ref, mwh=mwh, basis="scheduled")


# ------------------------------------------------------------------ golden arithmetic

LINES = [
    _line("contract:beach", "NBP", "uk", IN, 24_000),
    _line("contract:field", "NBP", "uk", IN, 10_000),
    _line("trade:sale", "NBP", "uk", OUT, 6_000, "sale"),
    _line("schedule:offtake", "NBP", "uk", OUT, 9_000, "customer_offtake"),
    _line("contract:ttf", "TTF", "nl", IN, 18_000),
    _line("schedule:city", "TTF", "nl", OUT, 14_000, "customer_offtake"),
    _line("schedule:storage", "TTF", "nl", OUT, 7_000, "storage_injection"),
]


def test_a_long_hub_and_a_short_hub():
    hubs = balance_for(LINES, [])
    nbp, ttf = hubs["NBP"], hubs["TTF"]
    assert (nbp.in_mwh, nbp.out_mwh, nbp.net_mwh, nbp.state) == (34_000, 15_000, 19_000, "long")
    assert (ttf.in_mwh, ttf.out_mwh, ttf.net_mwh, ttf.state) == (18_000, 21_000, -3_000, "short")


def test_a_net_within_half_a_mwh_is_balanced():
    hubs = balance_for([_line("a", "TTF", "nl", IN, 100.0), _line("b", "TTF", "nl", OUT, 99.6)],
                       [])
    assert hubs["TTF"].state == "balanced"


def test_nbp_in_therms_and_continental_in_mwh_with_mw():
    nbp = native_quantity("NBP", 19_000, TODAY)
    assert nbp["unit"] == "th/d"
    assert nbp["value"] == round(19_000 * 34.1214163)  # units authority: 1 MWh = 34.1214 th
    assert nbp["mwh"] == 19_000
    ttf = native_quantity("TTF", -3_000, TODAY)
    assert (ttf["unit"], ttf["value"], ttf["mw"]) == ("MWh/d", -3_000, -125.0)
    # The autumn clock change makes a 25-hour gas day: the same MWh is fewer MW.
    long_day = native_quantity("TTF", 2_500, date(2026, 10, 24))
    assert long_day["mw"] == 100.0


SPLIT = [Delegation(trader="nl.trader", book_id="uk", hub="NBP", ref="contract:beach",
                    mwh=8_000, trader_name="NL desk")]


def test_a_delegated_split_never_counts_twice():
    own, parts = split_line(LINES[0], SPLIT)
    assert own == 16_000 and [mwh for mwh, _ in parts] == [8_000]
    owner = balance_for(LINES, SPLIT, trader="uk.trader", owned_books=frozenset({"uk"}))["NBP"]
    receiver = balance_for(LINES, SPLIT, trader="nl.trader", owned_books=frozenset({"nl"}))
    desk = balance_for(LINES, SPLIT)["NBP"]
    assert owner.net_mwh == 11_000  # 19,000 less the 8,000 handed over
    assert receiver["NBP"].net_mwh == 8_000 and receiver["NBP"].in_mwh == 8_000
    assert receiver["TTF"].net_mwh == -3_000  # his own book stays his
    assert owner.net_mwh + receiver["NBP"].net_mwh == desk.net_mwh == 19_000
    assert [(line.ref, mwh) for line, mwh, _ in owner.delegated] == [("contract:beach", 8_000)]
    assert [(line.ref, mwh) for line, mwh, _ in desk.delegated] == [("contract:beach", 8_000)]


def test_a_split_larger_than_the_line_is_capped_and_a_hub_delegation_takes_the_rest():
    big = [Delegation("b", "uk", "NBP", "contract:beach", 30_000),
           Delegation("c", "uk", "NBP", None, None)]
    own, parts = split_line(LINES[0], big)
    assert own == 0 and [mwh for mwh, _ in parts] == [24_000]
    own, parts = split_line(LINES[1], big)
    assert own == 0 and [(mwh, item.trader) for mwh, item in parts] == [(10_000, "c")]


# ------------------------------------------------------------------ cut-offs (one calendar)


def test_network_code_defaults_in_winter_and_summer():
    assert nomination_deadline(date(2026, 11, 20)) == datetime(2026, 11, 19, 13, tzinfo=UTC)
    assert nomination_deadline(date(2026, 7, 2)) == datetime(2026, 7, 1, 12, tzinfo=UTC)
    assert last_renomination(date(2026, 11, 19)) == datetime(2026, 11, 20, 2, tzinfo=UTC)
    assert last_renomination(date(2026, 7, 1)) == datetime(2026, 7, 2, 1, tzinfo=UTC)


def test_prompt_signals_read_the_same_calendar():
    from eurogas_nexus.application.strategy_tracking import cutoff_for

    class Leg:
        def __init__(self, product):
            self.product = product

    assert cutoff_for([Leg("within-day")], {}, NOW) == datetime(2026, 11, 20, 2, tzinfo=UTC)
    assert cutoff_for([Leg("day-ahead")], {}, NOW) == datetime(2026, 11, 19, 13, tzinfo=UTC)
    late = NOW.replace(hour=15)
    assert product_cutoff("day-ahead", late) == datetime(2026, 11, 20, 5, tzinfo=UTC)


# ------------------------------------------------------------------ the demo desk


def _caller(name: str, *scopes: str) -> Caller:
    return Caller(AuthenticatedPrincipal(
        principal_id=f"p-{name}", name=name, principal_type="USER", role="ANALYST",
        status="ACTIVE", data_scopes=scopes or ("*",), roles=("ANALYST",),
    ))


def _seed_module():
    spec = importlib.util.spec_from_file_location("seed_demo_desk", SEED)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def desk(tmp_path, monkeypatch):
    url = f"sqlite+pysqlite:///{tmp_path / 'gasday.sqlite'}"
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    monkeypatch.setenv("EUROGAS_NEXUS_DEMO_MARKS", "true")
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_module().seed(session, NOW, history_days=3)
        session.commit()
    return engine


def _day(engine, caller, which="today"):
    with Session(engine) as session:
        row = my_gas_day(session, caller, now=NOW)
    return row, {hub["hub"]: hub for hub in next(d for d in row["days"]
                                                 if d["which"] == which)["hubs"]}


def _refs(hub):
    return {line["ref"]: line for line in hub["lines"]}


def test_the_nbp_trader_sees_his_mandated_book_only(desk):
    row, hubs = _day(desk, _caller("demo.trader"))
    assert row["scope"]["kind"] == "mandate" and row["scope"]["books"] == ["demo-uk-nbp"]
    assert set(hubs) == {"NBP", "TTF"}  # the UK book's TTF delivery is his too
    nbp = hubs["NBP"]
    assert nbp["state"] == "long" and nbp["net"]["unit"] == "th/d"
    assert "contract:demo-kestrel-18" not in _refs(hubs["TTF"])  # the NL book's contract
    # Today's nomination is read where held; the 2,000 MWh/d split is with the TTF desk.
    assert _refs(nbp)["contract:demo-haldor-24"]["basis"] == "nominated"
    ttf = hubs["TTF"]
    kestrel = _refs(ttf)["contract:demo-kestrel-uk-6"]
    assert [item["trader"] for item in ttf["delegated"]] == ["demo.nl.trader"]
    assert ttf["delegated"][0]["quantity"]["mwh"] == 2_000
    assert kestrel["quantity"]["mwh"] == pytest.approx(ttf["in"]["mwh"])
    # Tomorrow is not nominated yet: the contract quantity, said so.
    _, tomorrow = _day(desk, _caller("demo.trader"), "tomorrow")
    assert _refs(tomorrow["NBP"])["contract:demo-haldor-24"]["basis"] == "contract_quantity"


def test_the_ttf_trader_holds_his_book_and_the_split_he_was_given(desk):
    row, hubs = _day(desk, _caller("demo.nl.trader"))
    assert row["scope"]["books"] == ["demo-nl-ttf"]
    assert set(hubs) == {"TTF"}
    ttf = hubs["TTF"]
    assert _refs(ttf)["contract:demo-kestrel-uk-6"]["quantity"]["mwh"] == 2_000
    assert ttf["state"] == "short"
    assert ttf["cost_of_nothing"]["basis"] == "assumption"
    assert ttf["cost_of_nothing"]["side"] == "short_premium"
    assert ttf["cost_of_nothing"]["value"] == pytest.approx(-ttf["net"]["mwh"] * 1.80, abs=0.05)
    # Tomorrow the LNG send-out covers what the Kestrel outage takes off the supply: within
    # the band. The slot holds no cargo, so its rate over the window is the line (assumed).
    _, tomorrow = _day(desk, _caller("demo.nl.trader"), "tomorrow")
    assert tomorrow["TTF"]["state"] == "balanced"
    lng = next(line for line in tomorrow["TTF"]["lines"] if line["kind"] == "lng_send_out")
    assert lng["basis"] == "slot" and lng["source_ref"] is None
    assert lng["quantity"]["mwh"] == 4_800


def test_operations_without_a_mandate_sees_every_book_once(desk):
    row, hubs = _day(desk, _caller("demo.operations"))
    _, uk = _day(desk, _caller("demo.trader"))
    _, nl = _day(desk, _caller("demo.nl.trader"))
    assert row["scope"]["kind"] == "all_books"
    assert hubs["TTF"]["net"]["mwh"] == pytest.approx(
        uk["TTF"]["net"]["mwh"] + nl["TTF"]["net"]["mwh"], abs=0.2)
    assert hubs["NBP"]["net"]["mwh"] == pytest.approx(uk["NBP"]["net"]["mwh"], abs=0.2)
    assert row["simulated"] is True


def test_portfolio_isolation_still_limits_a_caller_without_a_mandate(desk, monkeypatch):
    monkeypatch.setenv(portfolio_scope.ISOLATION_ENV, "true")
    token = portfolio_scope._current.set(
        portfolio_scope.scope_from_data_scopes(("BOOKS:BOOK:demo-nl-ttf",)))
    try:
        _, hubs = _day(desk, _caller("someone", "BOOKS:BOOK:demo-nl-ttf"))
    finally:
        portfolio_scope._current.reset(token)
    assert set(hubs) == {"TTF"}
    assert {line["book_id"] for line in hubs["TTF"]["lines"]} == {"demo-nl-ttf"}


def test_an_expired_mandate_grants_no_scope(desk):
    from eurogas_nexus.db.models import TraderMandateRecord

    with Session(desk) as session:
        session.get(TraderMandateRecord, "DEMO-UK-1").valid_until = TODAY - timedelta(days=1)
        session.commit()
    row, _ = _day(desk, _caller("demo.trader"))
    assert row["scope"]["kind"] == "all_books"  # a reader of the books he may see, no more


def test_an_older_volume_gets_the_gas_day_on_its_next_roll_forward(desk):
    from eurogas_nexus.db.models import GasDayDelegationRecord, GasDayScheduleLineRecord

    with Session(desk) as session:
        session.query(GasDayScheduleLineRecord).delete()
        session.query(GasDayDelegationRecord).delete()
        session.commit()
        counts = _seed_module().ensure_demo_fixtures(session, NOW + timedelta(days=1))
        session.commit()
        assert counts["fixture_gas_day_lines"] == 10
        assert counts["fixture_gas_day_splits"] == 1
        again = _seed_module().seed_demo_gas_day(session, NOW + timedelta(days=1))
        assert sum(again.values()) == 0


def test_today_appends_the_row_without_moving_the_others(desk):
    from eurogas_nexus.application.desk_today import build_today

    with Session(desk) as session:
        today = build_today(session, _caller("demo.trader"), now=NOW,
                            balance_reader=lambda: None)
    keys = [row["key"] for row in today["rows"]]
    assert keys == ["key_figures", "changes", "book", "fundamentals", "needs_me", "gas_day",
                    "checklist"]
    assert today["rows"][5]["populated"] is True, today["warnings"]


# ------------------------------------------------------------------ outages (QA-T-09)


def test_an_outage_at_the_source_caps_the_supply_line_and_names_the_message(desk):
    _, hubs = _day(desk, _caller("demo.trader"))
    haldor = _refs(hubs["NBP"])["contract:demo-haldor-24"]
    # The demo Haldor field: 52 of 70 mcm/d out all day. 24,000 MWh/d x (1 - 52/70) is what
    # the field can deliver; the 21,120 nominated is above it, so the line is capped.
    assert haldor["quantity"]["mwh"] == pytest.approx(24_000 * (1 - 52 / 70), abs=0.1)
    (outage,) = haldor["adjustments"]
    assert outage["kind"] == "outage" and outage["source"] == "REMIT"
    assert outage["id"] == "demo-umm-1" and outage["asset"].startswith("Haldor field")
    assert outage["share_out_pct"] == pytest.approx(74.29) and outage["day_share_pct"] == 100
    assert outage["quantity"]["mwh"] == pytest.approx(21_120 - 24_000 * (1 - 52 / 70), abs=0.1)
    # A contract whose source has no outage is untouched.
    assert _refs(hubs["NBP"])["contract:demo-brae-10"]["adjustments"] == []


def test_an_outage_covering_part_of_the_gas_day_takes_its_share_of_the_day(desk):
    from eurogas_nexus.db.models import RemitUmmRecord

    with Session(desk) as session:
        row = session.query(RemitUmmRecord).filter(
            RemitUmmRecord.message_id == "demo-umm-1").one()
        # Ends at 11:00 UTC tomorrow: a quarter of tomorrow's gas day (05:00 to 05:00 UTC).
        row.event_stop_utc = datetime(2026, 11, 20, 11)
        session.commit()
    _, tomorrow = _day(desk, _caller("demo.trader"), "tomorrow")
    haldor = _refs(tomorrow["NBP"])["contract:demo-haldor-24"]
    assert haldor["adjustments"][0]["day_share_pct"] == 25.0
    assert haldor["quantity"]["mwh"] == pytest.approx(24_000 * (1 - 52 / 70 * 0.25), abs=0.1)


# ------------------------------------------------------------------ LNG send-out (QA-L-01)


def _cargo_at_the_slot(engine, eta: datetime) -> str:
    from eurogas_nexus.db.models import LngCargoRecord, RegasSlotRecord

    slot_id = "demo-slot-gate-20261120"
    with Session(engine) as session:
        session.add(LngCargoRecord(
            cargo_id="test-cargo-1", vessel_name="Test vessel", status="laden",
            load_port="Sabine Pass", departed_at_utc=NOW - timedelta(days=10),
            destination_terminal="Rotterdam terminal", eta_utc=eta, energy_gwh=1_000.0,
            book_id="demo-nl-ttf", source_system="ETRM_CSV", source_reference="etrm:test",
            updated_at_utc=NOW,
        ))
        session.get(RegasSlotRecord, slot_id).cargo_id = "test-cargo-1"
        session.commit()
    return slot_id


def test_a_cargo_that_misses_the_slot_window_sends_out_nothing_that_gas_day(desk):
    # The window is tomorrow's gas day (20 Nov 05:00 to 21 Nov 05:00 UTC); the ship arrives
    # on 22 Nov: the slot is missed, and the plan sends out nothing on the 20th.
    slot_id = _cargo_at_the_slot(desk, datetime(2026, 11, 22, 12, tzinfo=UTC))
    _, tomorrow = _day(desk, _caller("demo.nl.trader"), "tomorrow")
    lng = _refs(tomorrow["TTF"])[f"lng:{slot_id}"]
    assert lng["basis"] == "cargo_plan" and lng["source_ref"] == "cargo:test-cargo-1"
    assert lng["quantity"]["mwh"] == 0
    with Session(desk) as session:
        row = checklist(session, _caller("demo.nl.trader"), now=NOW)
    items = next(d for d in row["days"] if d["which"] == "tomorrow")["items"]
    send_out = next(item for item in items if item["step"] == "lng_send_out")
    assert send_out["expected"]["mwh"] == 0 and send_out["expected"]["basis"] == "cargo_plan"


def test_a_cargo_on_time_sends_out_what_its_plan_says(desk):
    from eurogas_nexus.application.lng_in_transit import send_out_plan

    slot_id = _cargo_at_the_slot(desk, datetime(2026, 11, 20, 17, tzinfo=UTC))
    with Session(desk) as session:
        plan, planned_slot = send_out_plan(session, "test-cargo-1", now=NOW)
    assert planned_slot == slot_id and plan.slot_status == "on_time"
    by_day = dict(plan.send_out)
    _, tomorrow = _day(desk, _caller("demo.nl.trader"), "tomorrow")
    lng = _refs(tomorrow["TTF"])[f"lng:{slot_id}"]
    # Berth at 17:00 UTC: 12 of the gas day's 24 hours at 4,800 MWh/d, not the whole day.
    assert lng["quantity"]["mwh"] == pytest.approx(by_day["2026-11-20"], abs=0.1)
    assert lng["quantity"]["mwh"] == pytest.approx(2_400, abs=0.1)


# ------------------------------------------------------------------ one daily balance (QA-T-07)


def test_the_daily_balance_is_the_gas_day_row_with_the_approved_rate(desk):
    from eurogas_nexus.application.gas_day import gas_day_view, hub_daily_balance

    caller = _caller("demo.operations")
    _, hubs = _day(desk, caller)
    with Session(desk) as session:
        view = gas_day_view(session, caller, now=NOW)
        rows = hub_daily_balance(session, view, "NBP")
    today = rows[0]
    nbp = hubs["NBP"]
    assert today["gas_day"] == "2026-11-19"
    assert today["residual_mwh"] == pytest.approx(nbp["net"]["mwh"], abs=0.1)
    assert today["state"] == nbp["state"]
    assert today["cash_out"] == nbp["cost_of_nothing"]
    # The rate comes from the approved set in force, named with its version, never a default.
    assert today["cash_out"]["basis"] == "assumption"
    assert today["cash_out"]["assumption_set"] and today["cash_out"]["assumption_version"]
    assert today["cash_out_cost"] == nbp["cost_of_nothing"]["value"]
    # The BBL import and the customer offtake are physical lines: in the supply, as on Today.
    refs = {line["ref"] for line in today["lines"]}
    assert any("bbl-import" in ref for ref in refs) and any("offtake" in ref for ref in refs)
    assert today["supply"] + today["bilateral_bought"] + today["exchange_bought"] - (
        today["bilateral_sold"] + today["exchange_sold"]) == pytest.approx(
            today["residual_mwh"], abs=0.2)


def test_the_opportunity_residuals_are_each_books_gas_day_balance(desk):
    """P-11: the sell-down residual is tomorrow's daily balance (the gas day's own lines),
    book by book, every book whatever mandate names the caller, the measured delivery shown
    and not applied; the books' residuals add up to the hub's balance."""

    from eurogas_nexus.application.gas_day import gas_day_view, hub_daily_balance
    from eurogas_nexus.application.opportunity_reads import BookReads

    tomorrow = TODAY + timedelta(days=1)
    with Session(desk) as session:
        rows = BookReads(_caller("demo.trader"), TODAY, as_of_utc=NOW).residuals(session)
        view = gas_day_view(session, _caller("demo.operations"), now=NOW, days=[tomorrow])
        by_hub = {hub: hub_daily_balance(session, view, hub)[0] for hub in ("NBP", "TTF")}
        books = {
            hub: {
                book: hub_daily_balance(session, view, hub, book_id=book)[0]
                for book in ("demo-uk-nbp", "demo-nl-ttf")
            }
            for hub in by_hub
        }
    keyed = {(row["hub"], row["book_id"]): row for row in rows}
    # The NBP trader's mandate does not narrow the firm's evaluation: the NL book is there.
    assert ("TTF", "demo-nl-ttf") in keyed and ("NBP", "demo-uk-nbp") in keyed
    for (hub, book), row in keyed.items():
        balance = books[hub][book]
        assert row["gas_day"] == tomorrow.isoformat() and row["definition"] == "gas_day"
        assert row["residual_mwh"] == balance["residual_mwh"] and row["state"] == balance["state"]
        assert row["supply_mwh"] == balance["supply"]
        assert row["delivery_ratio_applied"] is False
    for hub, total in by_hub.items():
        assert sum(item["residual_mwh"] for item in books[hub].values()) == pytest.approx(
            total["residual_mwh"], abs=0.2
        )
    # Each book's cash-out rate is its own set's (the NL book's TTF residual, in EUR).
    nl = books["TTF"]["demo-nl-ttf"]["cash_out"]
    assert nl["assumption_set"] == "NL TTF balancing"
