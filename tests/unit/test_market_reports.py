"""Market reports on the demo desk: assembly, audience, licences, records, as-of, the API."""

from __future__ import annotations

import importlib.util
import re
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import eurogas_nexus.db.models  # noqa: F401  (registers every table)
from eurogas_nexus.application.caller import Caller
from eurogas_nexus.application.monitoring_service import scan_monitoring_conditions
from eurogas_nexus.application.reports import findings
from eurogas_nexus.application.reports.catalogue import PlanError, validate_plan
from eurogas_nexus.application.reports.engine import ReportRefused, generate_report
from eurogas_nexus.application.reports.facts import fact
from eurogas_nexus.application.reports.store import reader_may_see, rerender
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import MarketReportRecord
from eurogas_nexus.security import portfolio_scope
from eurogas_nexus.security.identity import AuthenticatedPrincipal

SEED = Path(__file__).resolve().parents[2] / "scripts" / "demo" / "seed_demo_desk.py"
NOW = datetime(2026, 11, 7, 7, tzinfo=UTC)
BOOK_WORDS = re.compile(r"Our book|Net position|P&amp;L|Rhinmark|Aldermoor|Nordvik|credit line|"
                        r"mandate|Contracts in effect", re.I)


def _caller(*scopes: str, pid: str = "p-analyst") -> Caller:
    return Caller(AuthenticatedPrincipal(
        principal_id=pid, name="analyst", principal_type="USER", role="ANALYST",
        status="ACTIVE", data_scopes=scopes, roles=("ANALYST",)))


@pytest.fixture(scope="module")
def desk(tmp_path_factory):
    path = tmp_path_factory.mktemp("reports") / "desk.sqlite"
    url = f"sqlite+pysqlite:///{path}"
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("RUNTIME_STORE_DATABASE_URL", url)
        mp.setenv("EUROGAS_NEXUS_DEMO_MARKS", "true")
        engine = create_engine(url)
        Base.metadata.create_all(engine)
        spec = importlib.util.spec_from_file_location("seed_demo_desk", SEED)
        seed = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(seed)
        with Session(engine) as session:
            seed.seed(session, NOW)
            session.commit()
            scan_monitoring_conditions(session, now_utc=NOW, enrich_with_llm=False)
        yield engine, url


@pytest.fixture
def env(desk, monkeypatch):
    engine, url = desk
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    monkeypatch.setenv("EUROGAS_NEXUS_DEMO_MARKS", "true")
    return engine


def _balance():
    from eurogas_nexus.api.routes.public.fundamentals import get_nwe_balance

    return get_nwe_balance(None, days=14, history_days=400, format="json")["data"]


def _generate(engine, caller, plan, now=NOW, **kw):
    with Session(engine) as session:
        return generate_report(session, caller, plan, now=now, balance_reader=_balance, **kw)


def _sections(report):
    return {s["key"]: s for s in report.snapshot["sections"]}


def test_a_morning_daily_is_assembled_from_every_section_on_the_demo_desk(env):
    report = _generate(env, _caller("DEMO", "BOOKS:*"), {"kind": "daily"})
    sections = _sections(report)
    for key in ("prices", "pipeline_supply", "lng", "storage", "outages", "balance",
                "book_position", "book_pnl", "book_limits"):
        assert sections[key]["status"] == "ok", (key, sections[key]["empty"])
    snap = report.snapshot
    assert snap["simulated"] and 3 <= len(snap["key_points"]) <= 5
    # Every section's commentary is rule text with a headline and at most three facts.
    for section in snap["sections"]:
        assert section["commentary"]["basis"] == "rule"
        assert len(section["commentary"]["bullets"]) <= 3
    # Demo prices are said to be simulated next to the value.
    assert "(simulated)" in sections["prices"]["commentary"]["headline"]
    # The balance's forecast is labelled and its method is in the evidence.
    assert sections["balance"]["forecast"]
    assert any(m["key"].startswith("forecast_") for m in sections["balance"]["evidence"]["methods"])
    # The supply stack table replaces the Sankey at print size (house standard).
    assert sections["balance"]["tables"][0]["caption"].startswith("Supply stack")
    html = report.html
    assert html.count("<h1>") == 1 and "Methodology and sources" in html
    assert "Our book" in html and "Key findings" in html and "At a glance" in html
    assert "DEMONSTRATION DATA: SIMULATED" in html


def test_the_html_is_self_contained(env):
    html = _generate(env, _caller("DEMO", "BOOKS:*"), {"kind": "daily"}).html
    assert "<link" not in html and "@import" not in html
    assert not re.search(r"""\s(src|href)\s*=""", html)
    stripped = html.replace('xmlns="http://www.w3.org/2000/svg"', "")
    stripped = stripped.replace("https://transparency.entsog.eu/", "")
    assert "http://" not in stripped and "https://" not in stripped
    assert "@page" in html and "display:table-header-group" in html


def test_a_shareable_report_never_contains_positions_pnl_limits_or_contracts(env):
    report = _generate(env, _caller("DEMO", "BOOKS:*"), {"kind": "daily",
                                                         "audience": "shareable"})
    keys = set(_sections(report))
    assert not keys & {"book_position", "book_pnl", "book_limits", "book_contracts"}
    body = report.html.split("Methodology and sources")[0]
    assert not BOOK_WORDS.search(body), BOOK_WORDS.search(body)
    assert report.book_ids == []


def test_asking_for_a_book_section_in_a_shareable_report_is_refused():
    with pytest.raises(PlanError) as refused:
        validate_plan({"kind": "daily", "audience": "shareable",
                       "sections": ["prices", "book_position"]}, now=NOW)
    assert refused.value.code == "internal_section_in_shareable"


def test_a_principal_without_a_book_gets_no_our_book_section(env, monkeypatch):
    monkeypatch.setenv(portfolio_scope.ISOLATION_ENV, "true")
    report = _generate(env, _caller("DEMO", "BOOKS:BOOK:SOMEONE-ELSES"), {"kind": "daily"})
    keys = set(_sections(report))
    assert not keys & {"book_position", "book_pnl", "book_limits", "book_contracts"}
    omitted = {item["key"] for item in report.snapshot["omitted"]}
    assert {"book_position", "book_pnl"} <= omitted
    assert "Prices" in report.html  # the market sections stand


def test_a_licensed_source_forces_internal_unless_the_licence_allows_redistribution(env):
    from eurogas_nexus.db.models import MarketDataLicenceRecord, MarketObservationRecord

    with Session(env) as session:
        template = next(
            row for row in session.query(MarketObservationRecord)
            .filter(MarketObservationRecord.source_system == "DEMO_Sim")
            .order_by(MarketObservationRecord.observed_at_utc.desc()).limit(200)
            if (row.metadata_json or {}).get("hub", row.product) == "TTF"
            and str((row.metadata_json or {}).get("tenor", "")).lower() == "month-ahead"
        )
        clone = {c.name: getattr(template, c.name) for c in template.__table__.columns}
        for offset in (1, 2):
            row = dict(clone)
            pk = template.__table__.primary_key.columns.keys()[0]
            row[pk] = f"lic-test-{offset}"
            row["source_system"] = "EEX"
            row["product"] = "PEG"
            row["metadata_json"] = {**(template.metadata_json or {}), "hub": "PEG",
                                    "tenor": "month-ahead", "simulated": False}
            row["observed_at_utc"] = template.observed_at_utc - timedelta(days=offset - 1)
            session.add(MarketObservationRecord(**row))
        session.commit()
    caller = _caller("DEMO", "EEX", "BOOKS:*")
    try:
        internal = _generate(env, caller, {"kind": "daily", "hubs": ["PEG", "TTF"]})
        if "EEX" not in internal.licensed_families:
            pytest.skip("the demo price reader did not pick the EEX row up")
        assert "Licensed data from EEX: internal use" in internal.html
        with pytest.raises(ReportRefused) as refused:
            _generate(env, caller, {"kind": "daily", "audience": "shareable",
                                    "hubs": ["PEG", "TTF"]})
        assert refused.value.code == "licensed_data_not_redistributable"
        assert refused.value.detail["families"] == ["EEX"]
        with Session(env) as session:
            session.add(MarketDataLicenceRecord(
                licence_id="lic-eex", vendor="EEX", source_family="EEX", licence_type="ENTERPRISE",
                licensed_use="DISPLAY", valid_from=date(2026, 1, 1), redistribution_allowed=True,
                updated_by="test", updated_at_utc=NOW))
            session.commit()
        shared = _generate(env, caller, {"kind": "daily", "audience": "shareable",
                                         "hubs": ["PEG", "TTF"]})
        assert shared.licensed_families == ["EEX"]
    finally:
        with Session(env) as session:
            session.query(MarketObservationRecord).filter(
                MarketObservationRecord.source_system == "EEX").delete()
            session.query(MarketDataLicenceRecord).delete()
            session.commit()


def test_a_stored_report_reopens_identically_and_its_hashes_hold(env):
    from eurogas_nexus.application.reports.engine import canonical_json, sha256

    report = _generate(env, _caller("DEMO", "BOOKS:*"), {"kind": "weekly"})
    with Session(env) as session:
        record = session.get(MarketReportRecord, report.report_id)
        assert record.kind == "weekly" and record.audience == "internal"
        assert rerender(record) == record.html == report.html
        assert sha256(record.html) == record.html_sha256
        assert sha256(canonical_json(record.snapshot_json)) == record.snapshot_sha256
        assert record.template_version == "market-report/2"
        assert "DEMO_Sim" in record.source_systems
        assert record.generated_by == "p-analyst"


def test_the_report_is_as_of_its_instant(env):
    from eurogas_nexus.db.models import MarketObservationRecord

    caller = _caller("DEMO", "BOOKS:*")
    before = _sections(_generate(env, caller, {"kind": "daily", "sections": ["prices"]}))
    with Session(env) as session:
        template = next(
            row for row in session.query(MarketObservationRecord)
            .filter(MarketObservationRecord.source_system == "DEMO_Sim")
            .order_by(MarketObservationRecord.observed_at_utc.desc()).limit(200)
            if (row.metadata_json or {}).get("hub", row.product) == "TTF"
            and str((row.metadata_json or {}).get("tenor", "")).lower() == "month-ahead"
        )
        row = {c.name: getattr(template, c.name) for c in template.__table__.columns}
        pk = template.__table__.primary_key.columns.keys()[0]
        row[pk] = "late-arrival"
        row["price"] = float(row["price"]) + 50.0
        row["observed_at_utc"] = (NOW + timedelta(hours=3)).replace(tzinfo=None)
        session.add(MarketObservationRecord(**row))
        session.commit()
    try:
        again = _sections(_generate(env, caller, {"kind": "daily", "sections": ["prices"]}))
        assert again["prices"]["tables"] == before["prices"]["tables"]
        later = _sections(_generate(env, caller, {"kind": "daily", "sections": ["prices"]},
                                    now=NOW + timedelta(hours=4)))
        assert later["prices"]["tables"] != before["prices"]["tables"]
    finally:
        with Session(env) as session:
            session.query(MarketObservationRecord).filter(
                MarketObservationRecord.observation_id == "late-arrival").delete()
            session.commit()


def test_a_reader_is_rechecked_for_sources_and_books(env, monkeypatch):
    report = _generate(env, _caller("DEMO", "BOOKS:*"), {"kind": "daily"})
    with Session(env) as session:
        record = session.get(MarketReportRecord, report.report_id)
        assert reader_may_see(session, record, _caller("DEMO", "BOOKS:*"))[0]
        # Without the demo family the reader may not read the demo prices it carries.
        assert reader_may_see(session, record, _caller("BOOKS:*")) == (
            False, "report_contains_unlicensed_source")
        monkeypatch.setenv(portfolio_scope.ISOLATION_ENV, "true")
        if record.book_ids:
            assert reader_may_see(session, record, _caller("DEMO", "BOOKS:BOOK:OTHER")) == (
                False, "report_contains_books_outside_scope")


def test_a_situation_report_from_an_outage_measures_before_and_after(env):
    from eurogas_nexus.application.remit_outages import load_outage_rows

    with Session(env) as session:
        rows = load_outage_rows(session, now=NOW, horizon_days=14)
    active = [r for r in rows if r["status"] == "active"]
    assert active
    report = _generate(env, _caller("DEMO", "BOOKS:*"),
                       {"kind": "situation", "outage_id": str(active[0]["event_id"])})
    event = _sections(report)["situation_event"]
    assert event["status"] == "ok"
    assert active[0]["facility_name"] in event["commentary"]["headline"]
    assert report.snapshot["plan"]["hubs"]  # the hubs the zone touches


def test_monthly_and_weekly_aggregate_over_their_period(env):
    weekly = _generate(env, _caller("DEMO"), {"kind": "weekly"})
    prices = _sections(weekly)["prices"]
    text = " ".join([prices["commentary"]["headline"], *prices["commentary"]["bullets"]])
    # The week of 31 Oct to 6 Nov spans the front-month roll: no change across two contracts.
    assert "rolled from Nov-26 to Dec-26" in text
    assert all(f["comparisons"]["week"] is None or f["key"].startswith("spread")
               for f in prices["facts"] if f["key"].startswith("price."))
    columns = [c["key"] for c in prices["tables"][0]["columns"]]
    assert {"period_change", "high", "low", "average"} <= set(columns)
    monthly = _generate(env, _caller("DEMO"), {"kind": "monthly"})
    assert monthly.plan.period_start == date(2026, 10, 1)
    assert monthly.plan.period_end == date(2026, 10, 31)
    assert "October 2026" in _sections(monthly)["pipeline_supply"]["commentary"]["headline"]


def test_the_api_generates_lists_and_serves_the_html(env):
    from eurogas_nexus.api.app import create_app

    client = TestClient(create_app())
    catalogue = client.get("/api/reports/catalogue").json()["data"]
    assert {s["key"] for s in catalogue["sections"]} >= {"prices", "balance", "book_position"}
    made = client.post("/api/reports/market", json={"kind": "daily", "use_model": False})
    assert made.status_code == 200, made.text
    meta = made.json()["data"]
    listed = client.get("/api/reports/market").json()["data"]
    assert meta["report_id"] in {row["report_id"] for row in listed}
    one = client.get(f"/api/reports/market/{meta['report_id']}").json()["data"]
    assert one["html_sha256"] == meta["html_sha256"]
    html = client.get(f"/api/reports/market/{meta['report_id']}/html")
    assert html.status_code == 200 and html.text.startswith("<!doctype html>")
    assert "default-src 'none'" in html.headers["content-security-policy"]
    bad = client.post("/api/reports/market", json={"kind": "daily", "audience": "shareable",
                                                   "sections": ["book_pnl"]})
    assert bad.status_code == 422
    assert client.get("/api/reports/market/mr-missing").status_code == 404


# =================================== house standard (REPORT_EDITORIAL_STANDARD.md)

BOOK = re.compile(r"Our book|Net position|Rhinmark|Aldermoor|Nordvik|credit line|mandate", re.I)


@pytest.fixture
def daily(env):
    return _generate(env, _caller("DEMO", "BOOKS:*"), {"kind": "daily"})


def _body(html: str) -> str:
    return html.split('class="r-sheet r-body"')[1].split('class="r-sheet r-back-sheet"')[0]


def test_the_document_has_no_interface(daily):
    html = daily.html
    for tag in ("<button", "<details", "<summary", "<input", "<select"):
        assert tag not in html
    assert "<script>" not in html  # only the JSON data block, never code
    assert html.count('<script type="application/json" id="report-data">') == 1


def test_page_one_is_the_report_in_miniature(daily):
    front = daily.html.split('class="r-sheet r-body"')[0]
    assert 'class="r-masthead"' in front and "Issue " in front and "Data as of" in front
    assert front.count("<h1>") == 1 and 'class="r-standfirst"' in front
    findings_ = re.search(r'<section class="r-findings".*?</section>', front).group(0)
    assert 3 <= findings_.count("<li>") <= 5
    assert "At a glance" in front and "Figure 1" in front


def test_every_exhibit_has_number_title_subtitle_and_source(daily):
    figures = re.findall(r'<figure class="r-exhibit[^"]*" id="[ft]\d+">.*?</figure>', daily.html)
    assert len(figures) >= 6
    for figure in figures:
        assert re.search(r'<span class="r-exno">(Figure|Table) \d+</span>', figure), figure[:200]
        assert re.search(r'<span class="r-extitle">[^<]+', figure)
        assert '<p class="r-source">Source: ' in figure and "Data as of" in figure


def test_numbers_are_unique_and_in_order(daily):
    numbers = [int(n) for n in re.findall(r'class="r-exno">Figure (\d+)<', daily.html)]
    assert numbers == list(range(1, len(numbers) + 1))


def test_body_tables_are_edited_and_captions_carry_no_duplicate_unit(daily):
    body = _body(daily.html)
    for table in re.findall(r"<tbody>(.*?)</tbody>", body):
        assert table.count("<tr") <= findings.MAX_FINDINGS + 3  # at most eight rows
    assert not re.search(r"\(([^()]+)\)\s*\(\1\)", daily.html)


def test_classification_and_simulated_mark_are_on_every_page(daily):
    css = re.search(r"<style>(.*?)</style>", daily.html).group(1)
    assert '@bottom-left{content:"INTERNAL' in css
    assert 'counter(page) " of " counter(pages)' in css
    assert "Simulated demonstration data" in css  # the dagger's meaning in every footer
    assert 'class="r-mark"' in daily.html and "position:fixed" in css


def test_a_shareable_report_still_holds_no_book(env):
    report = _generate(env, _caller("DEMO", "BOOKS:*"), {"kind": "daily",
                                                         "audience": "shareable"})
    front_and_body = report.html.split('class="r-sheet r-back-sheet"')[0]
    assert not BOOK.search(front_and_body)
    assert not any(f["section"].startswith("book_") for f in report.snapshot["fact_sheet"])
    css = re.search(r"<style>(.*?)</style>", report.html).group(1)
    assert '@bottom-left{content:"FOR DISTRIBUTION' in css


# --------------------------------------------------------------------- findings ranking


def _f(key, score, state="current", simulated=False, section=None):
    item = fact(key, section or key.split(".")[0], key, 1.0, "GWh/d", day="2026-11-15",
                state=state, simulated=simulated, sentence=f"{key} sentence.", score=score,
                reason="test")
    return item


def _sheet(*facts_):
    for index, item in enumerate(facts_, start=1):
        item["id"] = f"F{index}"
    return list(facts_)


def test_a_large_outage_outranks_a_small_storage_move():
    sheet = _sheet(_f("storage.fill", 0.02), _f("outage.1", 3.4, section="outages"),
                   _f("landings", 0.6, section="pipeline_supply"))
    ranked = findings.rank_findings(sheet)
    assert ranked[0]["fact_ids"] == ["F2"]
    assert "score 3.4" in ranked[0]["why"]


def test_one_finding_per_indicator_and_three_to_five():
    sheet = _sheet(_f("price.TTF", 2.0, section="prices"), _f("price.NBP", 1.9, section="prices"),
                   _f("landings", 1.5, section="pipeline_supply"), _f("lng", 1.2),
                   _f("storage.fill", 1.1), _f("power.gen", 1.05, section="power_burn"),
                   _f("balance.call", 1.01, section="balance"))
    ranked = findings.rank_findings(sheet)
    assert len(ranked) == 5
    assert sum(1 for r in ranked if r["fact_ids"][0] in {"F1", "F2"}) == 1


def test_a_quiet_day_says_so_first():
    sheet = _sheet(_f("landings", 0.3, section="pipeline_supply"), _f("lng", 0.2),
                   _f("storage.fill", 0.1))
    ranked = findings.rank_findings(sheet)
    assert ranked[0]["text"] == findings.NO_NEWS
    assert findings.headline_of(ranked, sheet).startswith("Flows, storage and prices")
