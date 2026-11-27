"""Deal capture end to end: import, repeats and corrections, manual deals, the blotter, the
ETRM entry sheet, the end-of-day check and close, the daily pack, and book isolation.

Fixtures are invented trades laid out after the public descriptions of the EEX and ICE
exports (``tests/fixtures/deal_capture``); dates are stated, not taken from today.
"""

from __future__ import annotations

import io
import zipfile
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pypdf
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import (
    AuditEventRecord,
    CapturedDealRecord,
    NotificationChannelRecord,
    NotificationOutboxRecord,
    TradingBookRecord,
)
from eurogas_nexus.db.repositories.identity import (
    create_identity_api_key,
    create_identity_principal,
)

PUBLIC_TOKEN = "test-public-api-token"
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "deal_capture"
DAY = date(2026, 11, 26)
NOW = datetime(2026, 11, 26, 17, 0, tzinfo=UTC)


def _setup(tmp_path, monkeypatch):
    url = f"sqlite+pysqlite:///{(tmp_path / 'deals.sqlite').as_posix()}"
    engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)
    who = {}
    with Session(engine) as session:
        for book, entity in (("desk-a", "EGN-A"), ("desk-b", "EGN-B")):
            session.add(TradingBookRecord(
                book_id=book, name=book.upper(), legal_entity=entity, region="europe",
                business="gas", base_currency="EUR", commodities=["gas"], active=True,
                updated_by="test", updated_at_utc=NOW,
            ))
        for name, role, scopes in (
            ("trader.a", "ANALYST", ["BOOKS:BOOK:desk-a"]),
            ("trader.b", "ANALYST", ["BOOKS:BOOK:desk-b"]),
            ("head", "ANALYST", ["*"]),
            ("viewer", "VIEWER", ["*"]),
        ):
            row = create_identity_principal(session, name=name, display_name=name, role=role,
                                            data_scopes=scopes)
            _key, bearer = create_identity_api_key(session, row.principal_id, display_name="t",
                                                   scopes=["*"])
            who[name] = {"X-Eurogas-Api-Key": PUBLIC_TOKEN, "X-Eurogas-Identity": bearer}
        session.commit()
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DEAL_FORMATS_DIR", raising=False)
    return engine, who


def _import(client, headers, name, *, book="desk-a", fmt=None):
    params = {"book_id": book, "file_name": name}
    if fmt:
        params["format"] = fmt
    return client.post("/api/desk/deals/import", params=params,
                       content=(FIXTURES / name).read_bytes(),
                       headers={**headers, "Content-Type": "text/csv"})


@pytest.fixture
def desk(tmp_path, monkeypatch):
    engine, who = _setup(tmp_path, monkeypatch)
    return engine, who, TestClient(create_app())


def test_repeated_exports_are_recognised_and_corrections_keep_history(desk):
    engine, who, client = desk
    first = _import(client, who["trader.a"], "ice_deal_report_day1.csv")
    assert first.status_code == 200, first.text
    data = first.json()["data"]
    assert data["format"] == "ice_deal_report"  # recognised by its headers
    assert data["verified"] is False and "unverified" in data["provenance"]
    assert data["counts"] == {"rows": 4, "new": 3, "amended": 0, "cancelled": 0,
                              "duplicate": 0, "unreadable": 1}
    assert data["problems"][0]["line"] == 4 and data["problems"][0]["code"] == "hub_unknown"

    again = _import(client, who["trader.a"], "ice_deal_report_day1_rerun.csv").json()["data"]
    assert again["counts"] == {"rows": 4, "new": 1, "amended": 1, "cancelled": 1,
                               "duplicate": 1, "unreadable": 0}
    # The same file twice adds nothing.
    third = _import(client, who["trader.a"], "ice_deal_report_day1_rerun.csv").json()["data"]
    assert third["counts"]["duplicate"] == 4 and third["counts"]["new"] == 0

    with Session(engine) as session:
        versions = session.query(CapturedDealRecord).filter_by(deal_key="ICE:9100002").all()
        assert sorted(v.version for v in versions) == [1, 2]
        current = [v for v in versions if v.superseded_at_utc is None]
        assert len(current) == 1 and current[0].price == Decimal("95.15")
        assert "corrected by ice_deal_report_day1_rerun.csv line 3" in current[0].change_reason
        # Exact decimals: 2000 th/d over Q1-27 (90 gas days) in MWh.
        assert current[0].total_mwh == Decimal("5275.279263")

    history = client.get("/api/desk/deals/history", params={"deal_key": "ICE:9100004"},
                         headers=who["trader.a"]).json()["data"]
    assert [row["status"] for row in history] == ["live", "cancelled"]
    assert history[0]["superseded_at_utc"] is not None

    blotter = client.get("/api/desk/deals", params={"day": DAY.isoformat()},
                         headers=who["trader.a"]).json()["data"]
    by_key = {row["deal_key"]: row for row in blotter["deals"]}
    assert set(by_key) == {"ICE:9100001", "ICE:9100002", "ICE:9100004", "ICE:9100005"}
    assert by_key["ICE:9100002"]["versions"] == 2
    assert by_key["ICE:9100001"]["source"] == {"kind": "file",
                                               "file_name": "ice_deal_report_day1.csv",
                                               "line": 2}
    assert by_key["ICE:9100005"]["instrument"] == "option"
    # The unread row is shown, not dropped, once (the rerun did not repeat it).
    assert [p["line"] for p in blotter["unreadable"]] == [4]
    assert blotter["unreadable"][0]["raw"].startswith("9100003")
    ttf_dec = next(t for t in blotter["totals"] if t["hub"] == "TTF" and t["product"] == "Dec-26")
    assert ttf_dec["buy_mwh"] == "3720" and ttf_dec["net_mwh"] == "3720"
    assert ttf_dec["avg_buy_price"] == "31.25"
    # Cancelled deals are on the blotter but not in the totals.
    assert not any(t["product"] == "Cal-27" for t in blotter["totals"])
    assert blotter["status"]["closed"] is False
    assert blotter["status"]["label"] == "desk estimate, before ETRM close"
    # Filters by trader, hub, venue.
    only_b = client.get("/api/desk/deals", params={"day": DAY.isoformat(), "trader": "trader.b"},
                        headers=who["trader.a"]).json()["data"]
    assert {row["trader"] for row in only_b["deals"]} == {"trader.b"}
    assert sorted(only_b["choices"]["traders"]) == ["trader.a", "trader.b"]

    with Session(engine) as session:
        actions = {row.action for row in session.query(AuditEventRecord).all()}
    assert "deals.import" in actions


def test_eex_export_is_read_from_its_product_ids_and_unread_rows_are_reported(desk):
    _engine, who, client = desk
    response = _import(client, who["trader.a"], "eex_trades_day1.csv")
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["format"] == "eex_trades"
    assert data["counts"]["new"] == 2 and data["counts"]["unreadable"] == 2
    codes = sorted(p["code"] for p in data["problems"])
    assert codes == ["hub_unknown", "number_invalid"]
    rows = client.get("/api/desk/deals", params={"day": DAY.isoformat(), "venue": "EEX"},
                      headers=who["trader.a"]).json()["data"]["deals"]
    assert {(r["product"], r["total_mwh"]) for r in rows} == {("Dec-26", "7440"),
                                                              ("Q1-27", "10795")}


def test_a_file_no_format_recognises_is_refused_with_its_headers(desk):
    _engine, who, client = desk
    response = client.post("/api/desk/deals/import", params={"book_id": "desk-a"},
                           content=b"a,b,c\n1,2,3\n",
                           headers={**who["trader.a"], "Content-Type": "text/csv"})
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "format_not_recognised"
    assert response.json()["detail"]["headers"] == ["a", "b", "c"]


def test_manual_deals_are_marked_and_only_manual_deals_are_corrected_by_hand(desk):
    engine, who, client = desk
    body = {"book": "desk-a", "venue": "BROKER", "trade_date": DAY.isoformat(),
            "counterparty": "Northwind Gas Trading", "hub": "ZTP", "product": "Dec-26",
            "side": "buy", "volume": "100", "volume_unit": "MWh/d", "price": "29.5",
            "price_unit": "EUR/MWh", "physical": True}
    created = client.post("/api/desk/deals/manual", json=body, headers=who["trader.a"])
    assert created.status_code == 200, created.text
    data = created.json()["data"]
    assert data["origin"] == "manual" and data["outcome"] == "new"
    assert "price" in data["entered_by_hand"] and "volume" in data["entered_by_hand"]
    key = data["deal_key"]
    assert key.startswith("BROKER:M-")
    fixed = client.post("/api/desk/deals/manual", json={"book": "desk-a", "deal_key": key,
                                                        "price": "29.75"},
                        headers=who["trader.a"])
    assert fixed.status_code == 200 and fixed.json()["data"]["outcome"] == "amended"
    with Session(engine) as session:
        current = session.query(CapturedDealRecord).filter_by(
            deal_key=key, superseded_at_utc=None).one()
        assert current.price == Decimal("29.75") and current.origin == "manual"
        assert current.change_reason == "corrected by hand"
        assert current.total_mwh == Decimal("3100")
    _import(client, who["trader.a"], "ice_deal_report_day1.csv")
    refused = client.post("/api/desk/deals/manual",
                          json={"book": "desk-a", "deal_key": "ICE:9100001", "price": "1"},
                          headers=who["trader.a"])
    assert refused.status_code == 409 and refused.json()["detail"]["code"] == "deal_from_file"
    bad = client.post("/api/desk/deals/manual", json={**body, "hub": "HENRY"},
                      headers=who["trader.a"])
    assert bad.status_code == 422 and bad.json()["detail"]["code"] == "hub_unknown"
    viewer = client.post("/api/desk/deals/manual", json=body, headers=who["viewer"])
    assert viewer.status_code == 403


def test_etrm_sheet_follows_the_layout_file(desk, tmp_path, monkeypatch):
    _engine, who, client = desk
    _import(client, who["trader.a"], "ice_deal_report_day1.csv")
    csv_file = client.get("/api/desk/deals/etrm-sheet",
                          params={"day": DAY.isoformat(), "format": "csv"},
                          headers=who["trader.a"])
    assert csv_file.status_code == 200, csv_file.text
    lines = csv_file.content.decode("utf-8-sig").splitlines()
    assert lines[0].startswith("Trade Date,Trade Time,Exchange Ref,Venue,Trader,Book")
    assert lines[1].startswith("26/11/2026,")
    assert (",9100001,ICE,trader.a,desk-a,ICE,Buy,TTF,Dec-26,01/12/2026,31/12/2026,5.000,MW,"
            in lines[1])
    assert len(lines) == 4  # header + three live deals
    xlsx = client.get("/api/desk/deals/etrm-sheet", params={"day": DAY.isoformat()},
                      headers=who["trader.a"])
    assert xlsx.status_code == 200
    with zipfile.ZipFile(io.BytesIO(xlsx.content)) as archive:
        sheet = archive.read("xl/worksheets/sheet1.xml").decode()
    assert "Exchange Ref" in sheet and "<v>31.2500</v>" in sheet

    # The desk's template is matched by editing the layout file: order, headers, fixed values.
    custom = tmp_path / "formats"
    custom.mkdir()
    (custom / "etrm_entry_sheet.toml").write_text(
        'name = "etrm_entry_sheet"\ntitle = "Desk template"\ndate_format = "%Y%m%d"\n'
        'include_header = true\ncsv_delimiter = ";"\ndecimal_separator = ","\n'
        '[[column]]\nheader = "Portfolio"\nvalue = "GAS-01"\n'
        '[[column]]\nheader = "B/S"\nfield = "side"\nvalues = { buy = "B", sell = "S" }\n'
        '[[column]]\nheader = "Ref"\nfield = "venue_trade_id"\n'
        '[[column]]\nheader = "Start"\nfield = "delivery_start"\n'
        '[[column]]\nheader = "Px"\nfield = "price"\ndecimals = 2\n',
        encoding="utf-8")
    monkeypatch.setenv("EUROGAS_NEXUS_DEAL_FORMATS_DIR", str(custom))
    lines = client.get("/api/desk/deals/etrm-sheet",
                       params={"day": DAY.isoformat(), "format": "csv"},
                       headers=who["trader.a"]).content.decode("utf-8-sig").splitlines()
    assert lines[0] == "Portfolio;B/S;Ref;Start;Px"
    assert lines[1] == "GAS-01;B;9100001;20261201;31,25"


def test_end_of_day_check_lists_every_difference_and_the_close_needs_each_acknowledged(desk):
    engine, who, client = desk
    _import(client, who["trader.a"], "ice_deal_report_day1.csv")
    _import(client, who["trader.a"], "desk_csv_day1.csv")
    etrm = (FIXTURES / "etrm_export_day1.csv").read_bytes()
    checked = client.post("/api/desk/deals/eod-check",
                          params={"day": DAY.isoformat(), "file_name": "etrm.csv"},
                          content=etrm, headers={**who["trader.a"], "Content-Type": "text/csv"})
    assert checked.status_code == 200, checked.text
    data = checked.json()["data"]
    kinds = sorted((d["kind"], d["deal_key"] or d["etrm_trade_id"]) for d in data["differences"])
    assert kinds == [
        ("missing_in_capture", "E-9"),
        ("missing_in_etrm", "BROKER:B-2611-02"),
        ("missing_in_etrm", "ICE:9100004"),
        ("volume", "BROKER:B-2611-01"),
    ]
    volume = next(d for d in data["differences"] if d["kind"] == "volume")
    assert volume["matched_by"] == "terms"
    assert volume["detail"]["difference_mwh"] == "310"  # 250 vs 240 MWh/d over 31 days
    assert data["matched"] == 3 and data["pairs"]["ICE:9100001"] == "E-1"

    refused = client.post("/api/desk/deals/close", json={
        "day": DAY.isoformat(), "etrm_file_name": "etrm.csv", "etrm_csv": etrm.decode(),
        "acknowledgements": {data["differences"][0]["id"]: "ok"}}, headers=who["trader.a"])
    assert refused.status_code == 409
    assert len(refused.json()["detail"]["missing"]) == 3

    acks = {d["id"]: f"seen: {d['kind']}" for d in data["differences"]}
    closed = client.post("/api/desk/deals/close", json={
        "day": DAY.isoformat(), "etrm_file_name": "etrm.csv", "etrm_csv": etrm.decode(),
        "acknowledgements": acks, "note": "E-9 is a late broker deal"},
        headers=who["trader.a"])
    assert closed.status_code == 200, closed.text
    assert closed.json()["data"]["closed_by"] == "trader.a"
    status = client.get("/api/desk/deals", params={"day": DAY.isoformat()},
                        headers=who["trader.a"]).json()["data"]["status"]
    assert status["closed"] is True and status["label"] is None
    assert status["closes"][0]["differences"] == 4
    with Session(engine) as session:
        events = [row for row in session.query(AuditEventRecord).all()
                  if row.action == "deals.day.close"]
        assert len(events) == 1 and events[0].principal == "trader.a"
        assert "4 difference(s) acknowledged" in events[0].detail


def test_daily_pack_in_both_languages_says_what_failed_at_the_top(desk):
    _engine, who, client = desk
    _import(client, who["head"], "ice_deal_report_day1.csv")
    for language, estimate, title in (("en", "Desk estimate, before ETRM close",
                                       "Daily management summary"),
                                      ("zh-CN", "交易台估算", "每日管理摘要")):
        pdf = client.get("/api/desk/deals/pack", params={
            "day": DAY.isoformat(), "kind": "management", "language": language,
            "format": "pdf"}, headers=who["head"])
        assert pdf.status_code == 200, pdf.text
        text = "".join(page.extract_text() for page in pypdf.PdfReader(
            io.BytesIO(pdf.content)).pages)
        assert title in text and estimate in text
        check = "CHECK BEFORE USE" if language == "en" else "使用前请核对"
        assert check in text  # not closed, one unread row
        xlsx = client.get("/api/desk/deals/pack", params={
            "day": DAY.isoformat(), "kind": "management", "language": language,
            "format": "xlsx"}, headers=who["head"])
        with zipfile.ZipFile(io.BytesIO(xlsx.content)) as archive:
            names = archive.read("xl/workbook.xml").decode()
            first = archive.read("xl/worksheets/sheet1.xml").decode()
        assert ("Volume traded today" in names) if language == "en" else ("成交量" in names)
        assert ("1 row(s) of the exchange files could not be read" in first
                if language == "en" else "1 行无法读取" in first)
    risk = client.get("/api/desk/deals/pack", params={
        "day": DAY.isoformat(), "kind": "risk", "language": "en", "format": "pdf"},
        headers=who["head"])
    text = "".join(page.extract_text() for page in pypdf.PdfReader(
        io.BytesIO(risk.content)).pages)
    for heading in ("Profit and loss by trader and hub", "Counterparty exposure",
                    "Mandate checks", "End-of-day check", "Rows that could not be read"):
        assert heading in text
    assert "no mandate recorded for this trader" in text
    assert "option: the mandate allows no options" not in text  # no option on day 1
    viewer = client.get("/api/desk/deals/pack", params={"kind": "risk"}, headers=who["viewer"])
    assert viewer.status_code == 403


def test_pack_is_sent_only_to_a_recipient_list_with_its_files(desk):
    engine, who, client = desk
    _import(client, who["head"], "ice_deal_report_day1.csv")
    refused = client.post("/api/desk/deals/pack/send", json={
        "day": DAY.isoformat(), "kinds": ["management"], "languages": ["en"]},
        headers=who["head"])
    assert refused.status_code == 409 and refused.json()["detail"]["code"] == "no_recipients"
    with Session(engine) as session:
        session.add(NotificationChannelRecord(
            channel_id="mgmt", name="Managers", kind="email", recipients="boss@example.com",
            categories=["pack_management"], min_severity="critical", enabled=True,
            updated_by="admin", updated_at_utc=NOW))
        session.add(NotificationChannelRecord(
            channel_id="alerts", name="All alerts", kind="email", recipients="ops@example.com",
            categories=[], min_severity="info", enabled=True, updated_by="admin",
            updated_at_utc=NOW))
        session.commit()
    sent = client.post("/api/desk/deals/pack/send", json={
        "day": DAY.isoformat(), "kinds": ["management"], "languages": ["en", "zh-CN"]},
        headers=who["head"])
    assert sent.status_code == 200, sent.text
    assert len(sent.json()["data"]["queued"]) == 2
    from eurogas_nexus.application.notifications import dispatch

    delivered = []
    with Session(engine) as session:
        rows = session.query(NotificationOutboxRecord).all()
        assert {row.category for row in rows} == {"pack_management"}
        assert all(row.severity == "warning" for row in rows)  # the sanity checks failed
        counts = dispatch(session, now=NOW, senders={
            "email": lambda channel, message: delivered.append((channel.channel_id, message))})
        session.commit()
    assert counts["sent"] == 2
    # Only the channel that asked for packs, whatever its minimum severity.
    assert {channel for channel, _m in delivered} == {"mgmt"}
    names = sorted(name for _c, message in delivered for name, _t, _b in message.attachments)
    assert names == ["management-pack-2026-11-26-en.pdf", "management-pack-2026-11-26-en.xlsx",
                     "management-pack-2026-11-26-zh.pdf", "management-pack-2026-11-26-zh.xlsx"]


def test_a_trader_of_one_book_never_sees_another_books_deals(desk):
    engine, who, client = desk
    assert _import(client, who["trader.a"], "ice_deal_report_day1.csv").status_code == 200
    assert _import(client, who["trader.b"], "eex_trades_day1.csv",
                   book="desk-b").status_code == 200
    # Importing into another trader's book is refused.
    refused = _import(client, who["trader.b"], "desk_csv_day1.csv", book="desk-a")
    assert refused.status_code == 404
    seen_b = client.get("/api/desk/deals", params={"day": DAY.isoformat()},
                        headers=who["trader.b"]).json()["data"]
    assert {row["venue"] for row in seen_b["deals"]} == {"EEX"}
    assert all(p["book_id"] == "desk-b" for p in seen_b["unreadable"])
    assert {book["book_id"] for book in seen_b["books"]} == {"desk-b"}
    history = client.get("/api/desk/deals/history", params={"deal_key": "ICE:9100001"},
                         headers=who["trader.b"])
    assert history.status_code == 404
    sheet = client.get("/api/desk/deals/etrm-sheet", params={"day": DAY.isoformat(),
                                                             "format": "csv"},
                       headers=who["trader.b"]).content.decode("utf-8-sig")
    assert "9100001" not in sheet and "770001" in sheet
    # The same trade id in another book is refused without saying where.
    clash = _import(client, who["trader.b"], "ice_deal_report_day1.csv", book="desk-b")
    assert clash.status_code == 200
    assert {p["code"] for p in clash.json()["data"]["problems"]} >= {"held_elsewhere"}
    with Session(engine) as session:
        assert session.query(CapturedDealRecord).filter_by(deal_key="ICE:9100001").count() == 1
    head = client.get("/api/desk/deals", params={"day": DAY.isoformat()},
                      headers=who["head"]).json()["data"]
    assert {row["book_id"] for row in head["deals"]} == {"desk-a", "desk-b"}


class _Inputs:
    def __init__(self, marks):
        self.marks = marks
        self.warnings = []
        self.resolved = {}


def test_day_pnl_uses_the_ladder_marks_and_carries_values_from_close_to_close(desk, monkeypatch):
    """Day P&L is the change in value since the previous close; month to date adds the closes.

    The marks are the position ladder's (``marks_for`` wraps ``ladder_inputs``); here they are
    stated so the arithmetic is exact: TTF Dec-26 bought 5 MW (3,720 MWh) at 31.25.
    """

    from eurogas_nexus.application import deal_capture

    _engine, who, client = desk
    _import(client, who["trader.a"], "ice_deal_report_day1.csv")
    marks = {("TTF", "2026-12"): 32.0}
    monkeypatch.setattr(deal_capture, "marks_for",
                        lambda caller, today, last, now=None: (_Inputs(dict(marks)), False))
    day1 = client.get("/api/desk/deals/pnl", params={"day": DAY.isoformat()},
                      headers=who["trader.a"]).json()["data"]
    ttf = next(row for row in day1["by_trader_hub"] if row["hub"] == "TTF")
    # (32.00 - 31.25) x 3,720 = 2,790; the Cal-27 sale has no mark: listed, not counted.
    assert ttf["day"] == "2790" and ttf["mtd"] == "2790" and ttf["ytd"] == "2790"
    assert {item["deal_key"] for item in day1["not_valued"]} == {"ICE:9100002", "ICE:9100004"}
    etrm = ("trade_id,book_id,hub,side,delivery_start,delivery_end,quantity,quantity_unit,"
            "price,price_unit\n")
    row = "E-1,desk-a,TTF,BUY,2026-12-01,2026-12-31,5,MW,31.25,EUR/MWh\n"
    checked = client.post("/api/desk/deals/eod-check", params={"day": DAY.isoformat()},
                          content=(etrm + row).encode(),
                          headers={**who["trader.a"], "Content-Type": "text/csv"}).json()["data"]
    acks = {d["id"]: "known" for d in checked["differences"]}
    closed = client.post("/api/desk/deals/close", json={
        "day": DAY.isoformat(), "etrm_file_name": "e.csv", "acknowledgements": acks,
        "etrm_csv": etrm + row},
        headers=who["trader.a"])
    assert closed.status_code == 200, closed.text
    marks[("TTF", "2026-12")] = 31.5
    day2 = client.get("/api/desk/deals/pnl", params={"day": "2026-11-27"},
                      headers=who["trader.a"]).json()["data"]
    ttf = next(row for row in day2["by_trader_hub"] if row["hub"] == "TTF")
    # Today (31.50 - 31.25) x 3,720 = 930, less 2,790 at the close: -1,860; MTD 930.
    assert ttf["day"] == "-1860" and ttf["mtd"] == "930" and ttf["ytd"] == "930"
    assert day2["status"]["label"] == "desk estimate, before ETRM close"
