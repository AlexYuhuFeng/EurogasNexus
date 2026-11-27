"""Captured deals in the one position source (small-desk plan section 4, step 3).

Every position and P&L screen reads ``position_inputs.ladder_inputs``; the captured deals enter
it through ``application/captured_position``. These tests drive the writes through the API
(imports, hand entries, the close) and the ETRM extract the way ``import_etrm_trades.py``
loads it, and read the one source with a stated day, so no ordering of capture, ETRM load and
close counts a deal twice. Dates are stated, not taken from today.
"""

from __future__ import annotations

import contextvars
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.db.models import AuditEventRecord, DealPositionKindRecord

from .test_deal_capture_api import DAY, NOW, _import, _setup

END = date(2027, 12, 31)
ETRM_HEADER = ("trade_id,trade_time,book_id,hub,side,delivery_start,delivery_end,quantity,"
               "quantity_unit,price,price_unit,status,counterparty,external_reference\n")
E1 = ("E-1,2026-11-26T09:15:02Z,desk-a,TTF,BUY,2026-12-01,2026-12-31,5,MW,31.25,EUR/MWh,,"
      "ICE,9100001\n")
E2 = ("E-2,2026-11-26T10:01:44Z,desk-a,NBP,SELL,2027-01-01,2027-03-31,2000,th/d,95.10,GBp/th,,"
      "ICE,9100002\n")
# No exchange reference: paired by terms.
E3 = "E-3,2026-11-26T14:00:00Z,desk-a,THE,BUY,2026-12-01,2026-12-31,240,MWh/d,30.95,EUR/MWh,,NW,\n"


@pytest.fixture
def desk(tmp_path, monkeypatch):
    # The position is read through ladder_inputs directly; the warm views are tested apart.
    monkeypatch.setenv("EUROGAS_NEXUS_WARM_VIEWS", "off")
    engine, who = _setup(tmp_path, monkeypatch)
    return engine, who, TestClient(create_app())


def _load_etrm(engine, rows: str) -> None:
    """The ETRM extract into the book, as ``scripts/ops/import_etrm_trades.py`` loads it."""

    from eurogas_nexus.db.models import ScreenOrderObservationRecord
    from eurogas_nexus.ingestion.etrm_trades import parse_etrm_trades

    parsed = parse_etrm_trades(ETRM_HEADER + rows, system="ETRM", source_reference="test",
                               reference_column="external_reference")
    with Session(engine) as session:
        for row in parsed.upserts:
            session.merge(ScreenOrderObservationRecord(**row))
        session.commit()


def _inputs(today: date = DAY, scopes: list[str] | None = None):
    from eurogas_nexus.application.caller import firm_caller
    from eurogas_nexus.application.position_inputs import ladder_inputs
    from eurogas_nexus.security.portfolio_scope import set_request_scope

    def read():
        if scopes is not None:
            set_request_scope(scopes, "reader")
        return ladder_inputs(firm_caller(), today, today, END, now=NOW)

    return contextvars.copy_context().run(read)


def _net(inputs, hub: str, kind: str | None = None, today: date = DAY) -> float:
    from eurogas_nexus.domain.portfolio.position_ladder import build_ladder

    rows = [r for r in build_ladder(inputs.legs, horizon_start=today, horizon_end=END)
            if r.hub == hub]
    if kind == "physical":
        return round(sum(r.physical_mwh for r in rows), 3)
    if kind == "financial":
        return round(sum(r.financial_mwh for r in rows), 3)
    return round(sum(r.net_mwh for r in rows), 3)


def _close(client, headers, etrm_rows: str) -> None:
    text = ETRM_HEADER + etrm_rows
    checked = client.post("/api/desk/deals/eod-check", params={"day": DAY.isoformat()},
                          content=text.encode(),
                          headers={**headers, "Content-Type": "text/csv"}).json()["data"]
    acks = {d["id"]: "seen" for d in checked["differences"]}
    closed = client.post("/api/desk/deals/close", json={
        "day": DAY.isoformat(), "etrm_file_name": "etrm.csv", "etrm_csv": text,
        "acknowledgements": acks}, headers=headers)
    assert closed.status_code == 200, closed.text


#: ICE day 1: TTF Dec-26 bought 5 MW (3,720 MWh), Cal-27 sold 1 MW (8,760 MWh); NBP Q1-27 sold
#: 2,000 th/d (5,275.279263 MWh).
TTF_NET, NBP_NET = 3720 - 8760, -5275.279


def test_capture_then_etrm_load_then_close_counts_each_deal_once(desk):
    engine, who, client = desk
    before = _inputs()
    assert before.captured is None or not before.captured.deals
    assert _import(client, who["trader.a"], "ice_deal_report_day1.csv").status_code == 200

    captured = _inputs()
    assert (_net(captured, "TTF"), _net(captured, "NBP")) == (TTF_NET, NBP_NET)
    assert captured.estimate_label == "desk estimate, before ETRM close"

    _load_etrm(engine, E1 + E2)  # the ETRM is filled in before the day is closed
    loaded = _inputs()
    assert (_net(loaded, "TTF"), _net(loaded, "NBP")) == (TTF_NET, NBP_NET)  # not twice
    assert loaded.captured.suppressed == {"etrm-etrm-E-1", "etrm-etrm-E-2"}
    assert {d["deal_key"]: d["matched_by"] for d in loaded.captured.deals
            if d["matched_by"]} == {"ICE:9100001": "reference", "ICE:9100002": "reference"}

    _close(client, who["trader.a"], E1 + E2)
    closed = _inputs()
    assert (_net(closed, "TTF"), _net(closed, "NBP")) == (TTF_NET, NBP_NET)
    by_key = {d["deal_key"]: d["counted_as"] for d in closed.captured.deals}
    # The official record counts once the day is closed; the Cal-27 sale has no ETRM twin.
    assert by_key == {"ICE:9100001": "etrm", "ICE:9100002": "etrm", "ICE:9100004": "captured"}
    assert closed.captured.suppressed == set()
    assert closed.estimate_label is None


def test_etrm_load_then_capture_and_a_partial_load_count_each_deal_once(desk):
    engine, who, client = desk
    _load_etrm(engine, E1)  # only part of the day's ETRM entry
    etrm_only = _inputs()
    assert (_net(etrm_only, "TTF"), _net(etrm_only, "NBP")) == (3720, 0)
    _import(client, who["trader.a"], "ice_deal_report_day1.csv")
    both = _inputs()
    assert (_net(both, "TTF"), _net(both, "NBP")) == (TTF_NET, NBP_NET)
    assert both.captured.suppressed == {"etrm-etrm-E-1"}
    _load_etrm(engine, E2)  # the rest of the ETRM entry
    rest = _inputs()
    assert (_net(rest, "TTF"), _net(rest, "NBP")) == (TTF_NET, NBP_NET)


def _manual(client, headers, **values):
    body = {"book": "desk-a", "venue": "BROKER", "trade_date": DAY.isoformat(),
            "counterparty": "Northwind Gas Trading", "hub": "THE", "product": "Dec-26",
            "side": "buy", "volume": "240", "volume_unit": "MWh/d", "price": "30.95",
            "price_unit": "EUR/MWh", **values}
    response = client.post("/api/desk/deals/manual", json=body, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["data"]["deal_key"]


def test_a_correction_after_the_etrm_load_shows_at_once_and_counts_once(desk):
    engine, who, client = desk
    key = _manual(client, who["trader.a"])
    _load_etrm(engine, E3)  # the ETRM row carries no exchange reference: paired by terms
    assert _net(_inputs(), "THE") == 7440
    _manual(client, who["trader.a"], deal_key=key, volume="250")  # corrected by hand
    corrected = _inputs()
    assert _net(corrected, "THE") == 7750  # the desk's latest word, once
    assert corrected.captured.deals[0]["matched_by"] == "terms"
    assert corrected.captured.suppressed == {"etrm-etrm-E-3"}


def test_a_cancelled_deal_leaves_the_position_while_the_etrm_still_holds_it(desk):
    engine, who, client = desk
    key = _manual(client, who["trader.a"])
    _load_etrm(engine, E3)
    _manual(client, who["trader.a"], deal_key=key, status="cancelled")
    cancelled = _inputs()
    assert _net(cancelled, "THE") == 0  # neither the cancelled deal nor its ETRM twin
    assert cancelled.captured.deals[0]["counted_as"] == "none"
    # A re-export that cancels a deal the ETRM holds by reference: the same.
    _import(client, who["trader.a"], "ice_deal_report_day1.csv")
    _load_etrm(engine, "E-4,2026-11-26T12:45:10Z,desk-a,TTF,SELL,2027-01-01,2027-12-31,1,MW,"
                       "29.80,EUR/MWh,,ICE,9100004\n")
    assert _net(_inputs(), "TTF") == TTF_NET
    _import(client, who["trader.a"], "ice_deal_report_day1_rerun.csv")  # cancels 9100004
    rerun = _inputs()
    assert "etrm-etrm-E-4" in rerun.captured.suppressed
    # 9100001 (3,720) and the new Feb-27 option (3 MW, 2,016 MWh) remain at TTF.
    assert _net(rerun, "TTF") == 3720 + 2016


def test_physical_and_financial_follow_the_rule_file_and_a_choice_by_hand(desk):
    engine, who, client = desk
    _import(client, who["trader.a"], "ice_deal_report_day1.csv")
    key = _manual(client, who["trader.a"])  # a broker forward, bilateral: title transfer
    inputs = _inputs()
    assert _net(inputs, "TTF", "financial") == TTF_NET  # exchange futures before delivery
    assert _net(inputs, "THE", "physical") == 7440
    kinds = {d["deal_key"]: d["position_kind"] for d in inputs.captured.deals}
    assert kinds["ICE:9100001"]["rule_kind"] == "financial_until_delivery"
    assert kinds[key] == {"kind": "physical", "rule_kind": "physical", "basis": "rule",
                          "rule": "Bilateral and broker forwards are title transfer at the hub"}
    # Once the December future goes to delivery it is physical gas at TTF.
    in_delivery = _inputs(date(2026, 12, 2))
    assert _net(in_delivery, "TTF", "physical", date(2026, 12, 2)) == round(3720 * 30 / 31, 3)

    chosen = client.post("/api/desk/deals/position-kind",
                         json={"deal_key": key, "kind": "financial", "note": "a swap really"},
                         headers=who["trader.a"])
    assert chosen.status_code == 200, chosen.text
    after = _inputs()
    assert _net(after, "THE", "financial") == 7440 and _net(after, "THE", "physical") == 0
    kind = next(d for d in after.captured.deals if d["deal_key"] == key)["position_kind"]
    assert kind["basis"] == "entered_by_hand" and kind["rule"] == "trader.a"
    blotter = client.get("/api/desk/deals", params={"day": DAY.isoformat()},
                         headers=who["trader.a"]).json()["data"]
    row = next(r for r in blotter["deals"] if r["deal_key"] == key)
    assert row["position_kind"]["basis"] == "entered_by_hand"
    assert row["position_kind"]["note"] == "a swap really"
    # Withdrawn: the rule decides again; both choices are kept and audited.
    client.post("/api/desk/deals/position-kind", json={"deal_key": key, "kind": None},
                headers=who["trader.a"])
    assert _net(_inputs(), "THE", "physical") == 7440
    with Session(engine) as session:
        assert session.query(DealPositionKindRecord).count() == 1
        actions = [r.outcome for r in session.query(AuditEventRecord).all()
                   if r.action == "deals.position_kind"]
        assert actions == ["financial", "withdrawn"]
    refused = client.post("/api/desk/deals/position-kind",
                          json={"deal_key": key, "kind": "financial"}, headers=who["trader.b"])
    assert refused.status_code == 404  # another book's deal is not there for trader.b
    viewer = client.post("/api/desk/deals/position-kind",
                         json={"deal_key": key, "kind": "financial"}, headers=who["viewer"])
    assert viewer.status_code == 403


def test_exact_rows_in_desk_units_and_unvalued_deals_listed(desk):
    from eurogas_nexus.application.captured_position import summary

    _engine, who, client = desk
    _import(client, who["trader.a"], "ice_deal_report_day1.csv")
    inputs = _inputs()
    block = summary(inputs.captured, horizon_start=DAY, horizon_end=END, marks={})
    rows = {(r["hub"], r["month"]): r for r in block["rows"]}
    dec26 = rows[("TTF", "2026-12")]
    assert (dec26["unit"], dec26["financial"], dec26["net"]) == ("MW", "5", "5")
    assert dec26["net_mwh"] == "3720"
    jan27 = rows[("NBP", "2027-01")]
    assert (jan27["unit"], jan27["net"]) == ("th/d", "-2000")
    # 2,000 th/d over Q1-27 is 5,275.279263 MWh; January holds 31 of its 90 gas days, exactly.
    assert Decimal(jan27["net_mwh"]) == (Decimal("-5275.279263") * 31 / 90).quantize(
        Decimal("0.001"))
    # The Cal-27 TTF sale: 1 MW in every month, a 23-hour day in March included.
    assert rows[("TTF", "2027-03")]["net"] == "-1"
    assert rows[("TTF", "2027-03")]["net_mwh"] == "-743"
    # No marks held: every deal is listed as not valued, none counted as zero.
    assert {d["deal_key"] for d in block["not_valued"]} == {"ICE:9100001", "ICE:9100002",
                                                             "ICE:9100004"}
    assert block["label"] == "desk estimate, before ETRM close"


def test_a_trader_of_one_book_never_sees_another_books_captured_deals(desk):
    _engine, who, client = desk
    _import(client, who["trader.a"], "ice_deal_report_day1.csv")
    _import(client, who["trader.b"], "eex_trades_day1.csv", book="desk-b")
    seen_b = _inputs(scopes=["BOOKS:BOOK:desk-b"])
    assert {d["deal_key"].split(":")[0] for d in seen_b.captured.deals} == {"EEX"}
    assert _net(seen_b, "NBP") == 0
    seen_a = _inputs(scopes=["BOOKS:BOOK:desk-a"])
    assert {d["deal_key"].split(":")[0] for d in seen_a.captured.deals} == {"ICE"}


def test_the_daily_pack_reads_the_same_position_with_physical_and_financial(desk):
    from eurogas_nexus.application.caller import firm_caller
    from eurogas_nexus.application.daily_pack import pack_data

    engine, who, client = desk
    _import(client, who["trader.a"], "ice_deal_report_day1.csv")
    _load_etrm(engine, E1)
    with Session(engine) as session:
        data = pack_data(session, firm_caller(), day=DAY, now=NOW)
    rows = {(r["hub"], r["month"]): r for r in data["position"]}
    assert rows[("TTF", "Dec-26")]["net_mwh"] == "3720"  # once, though the ETRM has it too
    assert rows[("TTF", "Dec-26")]["financial_mwh"] == "3720"
    assert rows[("TTF", "Dec-26")]["net_desk"] == "5"
    assert rows[("TTF", "Dec-26")]["desk_unit"] == "MW"
    assert rows[("NBP", "Jan-27")]["net_desk"] == "-2000"
    assert data["overlay_deals"] == 3


def test_an_exchange_holiday_is_not_a_trading_day_without_deals(desk, tmp_path, monkeypatch):
    from eurogas_nexus.application import daily_pack
    from eurogas_nexus.application.caller import firm_caller
    from eurogas_nexus.domain.deals.position import load_trading_calendar

    calendar = load_trading_calendar()
    assert not calendar.is_trading_day(date(2026, 12, 25))  # every listed venue shut
    assert calendar.is_trading_day(date(2026, 5, 1))  # EEX shut, ICE open
    assert calendar.closed_venues(date(2026, 5, 1)) == ["EEX"]
    assert not calendar.is_trading_day(date(2026, 11, 28))  # a Saturday
    assert all(not venue.checked for venue in calendar.venues)  # said, until someone checks

    engine, _who, _client = desk
    with Session(engine) as session:
        christmas = pack_data_sanity(daily_pack, session, firm_caller(), date(2026, 12, 25))
        ordinary = pack_data_sanity(daily_pack, session, firm_caller(), date(2026, 12, 23))
        uncovered = pack_data_sanity(daily_pack, session, firm_caller(), date(2028, 3, 1))
    assert "check.no_deals" not in christmas
    assert "check.no_deals" in ordinary
    assert "check.calendar" in uncovered and "check.no_deals" in uncovered

    # A desk copy of the calendar replaces the built-in one.
    folder = tmp_path / "desk-files"
    folder.mkdir()
    (folder / "trading_calendars.toml").write_text(
        'years = [2026]\n[venue.EEX]\nsource = "x"\nnon_trading_days = ["2026-12-23"]\n',
        encoding="utf-8")
    monkeypatch.setenv("EUROGAS_NEXUS_DEAL_FORMATS_DIR", str(folder))
    assert not load_trading_calendar().is_trading_day(date(2026, 12, 23))


def pack_data_sanity(daily_pack, session, caller, day: date) -> set[str]:
    from datetime import UTC, datetime

    data = daily_pack.pack_data(session, caller, day=day,
                                now=datetime.combine(day, datetime.min.time(), tzinfo=UTC))
    return {key for key, _params in data["sanity"]}


def test_the_ladder_today_and_limits_carry_the_estimate_label(desk):
    """The read routes show "desk estimate, before ETRM close" while a day is open.

    The routes read today's date, so the deal is entered for today's month-ahead (relative,
    not a stated calendar month): the same on any day.
    """

    from datetime import UTC, datetime

    _engine, who, client = desk
    today = datetime.now(UTC).date()
    _manual(client, who["head"], hub="TTF", product="M+1", trade_date=today.isoformat(),
            volume="10", volume_unit="MW")
    ladder = client.get("/api/portfolio/position-ladder", headers=who["head"])
    assert ladder.status_code == 200, ladder.text
    data = ladder.json()["data"]
    assert data["estimate_label"] == "desk estimate, before ETRM close"
    assert data["captured"]["deals_counted"] == 1
    assert data["captured"]["kinds"]["physical"] == 1
    row = data["captured"]["rows"][0]
    assert (row["hub"], row["unit"], row["physical"]) == ("TTF", "MW", "10")
    assert data["totals"]["physical_mwh"] > 0
    today_read = client.get("/api/desk/today", headers=who["head"])
    assert today_read.status_code == 200, today_read.text
    assert today_read.json()["data"]["position_estimate"] == "desk estimate, before ETRM close"
    credit = client.get("/api/portfolio/credit-exposure", headers=who["head"])
    assert credit.status_code == 200, credit.text
    assert credit.json()["data"]["estimate_label"] == "desk estimate, before ETRM close"
