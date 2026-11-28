"""The regas auction desk end to end: open a case, the live answer, missing and hand-entered
inputs, snapshots, the read-only what-if, closing, the deadlines, the report in both languages,
the audit trail and book isolation.

The store has no market prices (a test store): the hub prices are entered by hand, which is
the manual path the case states in its answer. Dates are stated, never taken from today.
"""

from __future__ import annotations

import io
import zipfile
from datetime import UTC, datetime, timedelta
from decimal import Decimal

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
    CreditLineRecord,
    LngCargoHedgeRecord,
    RegasAuctionCaseRecord,
    RegasAuctionSnapshotRecord,
    RegasSlotRecord,
    TradingBookRecord,
)
from eurogas_nexus.db.repositories.identity import (
    create_identity_api_key,
    create_identity_principal,
)

PUBLIC_TOKEN = "test-public-api-token"
NOW = datetime(2026, 11, 28, 9, 0, tzinfo=UTC)


def _setup(tmp_path, monkeypatch):
    url = f"sqlite+pysqlite:///{(tmp_path / 'regas.sqlite').as_posix()}"
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
        session.add(CreditLineRecord(
            counterparty_id="owner-1", name="Cargo Owner One", legal_entity="EGN-A",
            limit_amount=50_000_000, currency="EUR", collateral_amount=0, receivable_days=50,
            updated_by="risk", updated_at_utc=NOW,
        ))
        for name, role, scopes in (
            ("trader.a", "ANALYST", ["BOOKS:BOOK:desk-a"]),
            ("trader.b", "ANALYST", ["BOOKS:BOOK:desk-b"]),
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


@pytest.fixture
def desk(tmp_path, monkeypatch):
    engine, who = _setup(tmp_path, monkeypatch)
    return engine, who, TestClient(create_app())


def _body(**overrides):
    body = {
        "book_id": "desk-a",
        "title": "Gate slot 10-13 Jan",
        "terminal": {"terminal_id": "gate-terminal", "name": "Gate (Rotterdam)", "hub": "TTF"},
        "slot": {"first_day": "2027-01-10", "last_day": "2027-01-13", "quantity": "1000",
                 "unit": "GWh"},
        "auction": {"format": "rising_rounds", "opens_at": "2026-12-01T08:00:00Z",
                    "closes_at": "2026-12-02T16:00:00Z", "time_zone": "Europe/Amsterdam",
                    "quotation": "per_mwh", "level": "0.40"},
        "owner": {"counterparty_id": "owner-1", "name": "Cargo Owner One"},
        "offer": {"kind": "fixed", "price": "28.00", "price_unit": "EUR/MWh",
                  "tolerance_pct": "5", "expires_at": "2026-12-02T18:00:00Z"},
        "costs": {
            "regas_fee": {"value": "450000", "link": "https://example.org/gate-tariff"},
            "losses": {"value": "1"},
            "berthing": {"value": "120000"},
            "entry": {"value": "0.50"},
        },
        "prices": {"TTF": {"all": "30.60"}},
        "rate_pct": "2.5",
    }
    body.update(overrides)
    return body


def _open(client, headers, **overrides):
    response = client.post("/api/desk/regas-auctions", json=_body(**overrides), headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["data"]


def test_open_a_case_and_read_the_answer_with_hand_entered_inputs_marked(desk):
    engine, who, client = desk
    case = _open(client, who["trader.a"])
    assert case["state"] == "open" and case["version"] == 1
    entered = case["inputs"]["costs"]["regas_fee"]
    assert entered["by"] == "trader.a" and entered["link"] == "https://example.org/gate-tariff"

    read = client.get(f"/api/desk/regas-auctions/{case['case_id']}", headers=who["trader.a"])
    assert read.status_code == 200, read.text
    answer = read.json()["data"]["answer"]
    assert answer["computed"] is True
    # 990,000 MWh at 30.60 = 30,294,000; less the lines and the cargo (28,000,000).
    assert answer["revenue"] == "30294000.00"
    assert answer["cargo_cost"] == "28000000.00"
    lines = {line["key"]: line for line in answer["cost_lines"]}
    assert lines["regas_fee"]["origin"] == "hand"
    assert lines["regas_fee"]["source"].startswith("entered by hand by trader.a on ")
    assert lines["margin"]["origin"] == "default"  # 0.25 desk default, stated
    assert lines["hedging"]["total"] == "49500.00"  # 990,000 x 0.05 desk default
    financing = Decimal(28_000_000) * Decimal("4.0") / 100 * 30 / 365
    expected = (Decimal(30_294_000) - Decimal(450_000) - Decimal(120_000) - Decimal(495_000)
                - Decimal(49_500) - financing - Decimal(247_500) - Decimal(28_000_000))
    assert answer["max_bid_total"] == str(expected.quantize(Decimal("0.01")))
    assert answer["state"] == "room"
    assert "price:TTF:2027-01-10" in answer["hand_entered"]
    assert "cost:regas_fee" in answer["hand_entered"]
    assert answer["prepare_hedge_orders"] == {
        "enabled": False, "note": "later step; a trader confirms in the execution tool"}
    assert answer["hedges"][0]["contract"] == "Jan-27"
    assert answer["hedges"][0]["desk_unit"] == "MW"
    assert answer["hedges"][0]["instrument"] == "future"
    assert answer["offer_expires_in_seconds"] > 0
    assert any(item["key"] == "default:margin" for item in answer["assumptions"])

    with Session(engine) as session:
        actions = [row.action for row in session.query(AuditEventRecord).all()]
    assert "regas_auction.create" in actions


def test_a_missing_input_is_named_and_not_computed(desk):
    _engine, who, client = desk
    body = _body(prices={}, costs={"losses": {"value": "1"}})
    case = _open(client, who["trader.a"], **{k: v for k, v in body.items() if k != "book_id"})
    answer = client.get(f"/api/desk/regas-auctions/{case['case_id']}",
                        headers=who["trader.a"]).json()["data"]["answer"]
    assert answer["computed"] is False and answer["state"] == "missing_inputs"
    assert "price:TTF:2027-01-10" in answer["missing"]
    assert "cost:berthing" in answer["missing"]
    assert "max_bid_total" not in answer


def test_the_level_moves_the_state_and_each_change_is_audited(desk):
    engine, who, client = desk
    case = _open(client, who["trader.a"])
    states = []
    for version, level in ((1, "0.83"), (2, "0.95")):
        body = _body(auction={**_body()["auction"], "level": level})
        body.pop("book_id")
        changed = client.put(f"/api/desk/regas-auctions/{case['case_id']}",
                             json={**body, "version": version}, headers=who["trader.a"])
        assert changed.status_code == 200, changed.text
        states.append(client.get(f"/api/desk/regas-auctions/{case['case_id']}",
                                 headers=who["trader.a"]).json()["data"]["answer"]["state"])
    assert states == ["at_limit", "stop"]
    stale = client.put(f"/api/desk/regas-auctions/{case['case_id']}",
                       json={**_body(), "version": 1}, headers=who["trader.a"])
    assert stale.status_code == 409
    with Session(engine) as session:
        row = session.get(RegasAuctionCaseRecord, case["case_id"])
        assert [item["value"] for item in row.inputs["auction"]["level_history"]] == [
            "0.40", "0.83", "0.95"]


def test_snapshot_what_if_and_close_won_book_nothing(desk):
    engine, who, client = desk
    case = _open(client, who["trader.a"])
    snap = client.post(f"/api/desk/regas-auctions/{case['case_id']}/snapshots",
                       json={"note": "bid 0.40 in round 3"}, headers=who["trader.a"])
    assert snap.status_code == 200, snap.text
    snapshot = snap.json()["data"]
    assert snapshot["state"] == "room" and snapshot["note"] == "bid 0.40 in round 3"
    assert any(row["key"] == "price:TTF:2027-01-10" for row in snapshot["prices"])

    what_if = client.get(f"/api/desk/regas-auctions/{case['case_id']}/what-if",
                         headers=who["trader.a"])
    assert what_if.status_code == 200, what_if.text
    data = what_if.json()["data"]
    assert data["booked"] is False and data["options_allowed"] is False
    assert data["instruments"] == ["future", "physical"]
    # The send-out long and the January sale cancel in the position.
    jan = next(row for row in data["added"] if row["month"] == "2027-01")
    assert abs(Decimal(jan["net_mwh"])) < Decimal("0.01")

    closed = client.post(f"/api/desk/regas-auctions/{case['case_id']}/close",
                         json={"outcome": "won", "note": "won at 0.42"}, headers=who["trader.a"])
    assert closed.status_code == 200, closed.text
    seam = closed.json()["data"]["position_seam"]
    assert seam["booked"] is False
    assert Decimal(seam["regas_slot"]["energy_gwh"]) == Decimal(1000)
    assert seam["hedges"][0]["mwh"].startswith("-")
    again = client.post(f"/api/desk/regas-auctions/{case['case_id']}/close",
                        json={"outcome": "lost", "note": "again"}, headers=who["trader.a"])
    assert again.status_code == 409

    with Session(engine) as session:
        assert session.query(RegasSlotRecord).count() == 0
        assert session.query(LngCargoHedgeRecord).count() == 0
        assert session.query(CapturedDealRecord).count() == 0
        assert session.query(RegasAuctionSnapshotRecord).count() == 1
        actions = sorted(row.action for row in session.query(AuditEventRecord).all()
                         if row.action.startswith("regas_auction"))
    assert actions == ["regas_auction.close", "regas_auction.create", "regas_auction.snapshot"]


def test_book_isolation(desk):
    _engine, who, client = desk
    case = _open(client, who["trader.a"])
    listing = client.get("/api/desk/regas-auctions", headers=who["trader.b"]).json()["data"]
    assert listing["cases"] == []
    hidden = client.get(f"/api/desk/regas-auctions/{case['case_id']}", headers=who["trader.b"])
    assert hidden.status_code == 404
    refused = client.post("/api/desk/regas-auctions", json=_body(book_id="desk-a"),
                          headers=who["trader.b"])
    assert refused.status_code == 404
    viewer = client.post("/api/desk/regas-auctions", json=_body(), headers=who["viewer"])
    assert viewer.status_code == 403
    mine = client.get("/api/desk/regas-auctions", headers=who["trader.a"]).json()["data"]
    assert [row["case_id"] for row in mine["cases"]] == [case["case_id"]]
    assert {t["terminal_id"] for t in mine["choices"]["terminals"]} >= {"gate-terminal"}
    assert mine["choices"]["owners"][0]["name"] == "Cargo Owner One"


def test_the_report_in_english_and_chinese(desk):
    _engine, who, client = desk
    case = _open(client, who["trader.a"])
    for language, word in (("en", "Maximum bid"), ("zh-CN", "最高出价")):
        pdf = client.get(f"/api/desk/regas-auctions/{case['case_id']}/report",
                         params={"language": language, "format": "pdf"},
                         headers=who["trader.a"])
        assert pdf.status_code == 200, pdf.text
        text = "".join(page.extract_text() for page in pypdf.PdfReader(io.BytesIO(pdf.content))
                       .pages)
        assert word in text
        xlsx = client.get(f"/api/desk/regas-auctions/{case['case_id']}/report",
                          params={"language": language, "format": "xlsx"},
                          headers=who["trader.a"])
        assert xlsx.status_code == 200
        with zipfile.ZipFile(io.BytesIO(xlsx.content)) as book:
            assert any(name.startswith("xl/worksheets/") for name in book.namelist())


def test_deadlines_reach_the_calendar_and_the_alerts(desk):
    engine, who, client = desk
    case = _open(client, who["trader.a"])
    from eurogas_nexus.application.regas_auction import calendar_items, monitoring_candidates

    closes = datetime(2026, 12, 2, 16, 0, tzinfo=UTC)
    with Session(engine) as session:
        items = calendar_items(session, now=NOW, days=60)
        assert {item["kind"] for item in items} == {"regas_auction_close", "regas_offer_expiry"}
        assert monitoring_candidates(session, closes - timedelta(hours=3)) == []
        warning = monitoring_candidates(session, closes - timedelta(minutes=90))
        assert [(c.alert_type, c.severity) for c in warning] == [
            ("regas_auction_close", "warning")]
        critical = monitoring_candidates(session, closes - timedelta(minutes=20))
        # The offer lapses two hours after the close: 140 minutes ahead, not yet alerted.
        assert {(c.alert_type, c.severity) for c in critical} == {
            ("regas_auction_close", "critical")}
        later = monitoring_candidates(session, closes + timedelta(minutes=30))
        assert [(c.alert_type, c.severity) for c in later] == [("regas_offer_expiry", "warning")]
        assert critical[0].evidence_snapshot["book_ids"] == ["desk-a"]
    calendar = client.get("/api/publications/calendar", params={"days": 60},
                          headers=who["trader.a"]).json()["data"]["items"]
    assert any(item["kind"] == "regas_auction_close" and item["case_id"] == case["case_id"]
               for item in calendar)
    other = client.get("/api/publications/calendar", params={"days": 60},
                       headers=who["trader.b"]).json()["data"]["items"]
    assert not any(item["kind"].startswith("regas") for item in other)


class _Item:
    def __init__(self, value, klass, label, native=None):
        from eurogas_nexus.domain.valuation.quality import InputClass

        self.value = None if value is None else Decimal(str(value))
        self.input_class = InputClass(klass)
        self.label = label
        self.held = value is not None
        self.as_of_utc = NOW
        self.detail = ({"native_value": native[0], "native_unit": native[1]} if native
                       else {"reason": "no price held"} if value is None else {})


class _Reader:
    """The valuation reader's shape: prices per gas day, FX and the benchmark rate."""

    def __init__(self, klass="indicative", nbp=False):
        self.klass = klass
        self.nbp = nbp

    def price(self, hub, period, side="mid"):
        if side != "mid":
            return _Item(None, "missing", f"{hub} {period.label} {side}")
        if hub == "NBP":
            return _Item("27.00", self.klass, f"NBP {period.label} settlement", ("92.13", "GBp/th"))
        return _Item("30.60", self.klass, f"{hub} {period.label} settlement")

    def fx(self, base, quote, period):
        return _Item("1.18", "derived", f"{base}/{quote} forward {period.label}")

    def rate(self, currency):
        return _Item("2.5", "sourced", f"{currency} overnight benchmark")


def _inputs(**changes):
    from eurogas_nexus.application.regas_auction import load_definition, normalise

    body = _body(**changes)
    body.pop("book_id")
    body.pop("prices")
    body.pop("rate_pct")
    body["terminal"] = {"name": "A terminal entered by hand", "hub": body["terminal"]["hub"]}
    return normalise(body, definition=load_definition({}), previous=None, actor="trader.a",
                     now=NOW)


def test_live_inputs_come_from_the_reader_and_are_not_marked_by_hand():
    from eurogas_nexus.application.regas_auction import answer

    data, _ = answer(None, None, _inputs(), now=NOW, reader=_Reader())
    assert data["computed"] and data["state"] == "room"
    assert not any(name.startswith("price:") for name in data["hand_entered"])
    assert data["days"][0]["source"] == "TTF 2027-01-10 settlement"
    assert data["grade"] == "assumption"  # the entered costs are the weakest inputs


def test_simulated_prices_give_an_illustration_not_a_bid_level():
    from eurogas_nexus.application.regas_auction import ILLUSTRATION, answer

    data, _ = answer(None, None, _inputs(), now=NOW, reader=_Reader("simulated"))
    assert data["state"] == "illustration" and data["illustration"] == ILLUSTRATION
    assert data["simulated"] is True


def test_an_nbp_slot_reads_pence_per_therm_and_states_the_step():
    from eurogas_nexus.application.regas_auction import answer

    data, _ = answer(None, None, _inputs(terminal={"name": "x", "hub": "NBP"},
                                         offer={"kind": "fixed", "price": "70.00",
                                                "price_unit": "GBp/th"}),
                     now=NOW, reader=_Reader(nbp=True))
    assert data["currency"] == "GBP"
    assert data["days"][0]["native_unit"] == "GBp/th"
    step = next(item for item in data["sensitivities"] if item["key"] == "price:NBP")
    assert step["per"] == "1 p/th"
    assert data["hedges"][0]["desk_unit"] == "th/d"
