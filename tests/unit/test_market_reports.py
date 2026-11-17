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


def test_a_book_section_in_a_shareable_report_is_left_out_not_refused():
    # The form's default sections for an internal daily include the book; switching to a
    # report for distribution must not end in a refusal (the owner's pop-up).
    plan = validate_plan({"kind": "daily", "audience": "shareable",
                          "sections": ["prices", "book_position"]}, now=NOW)
    assert plan.sections == ["prices"] and plan.notes
    with pytest.raises(PlanError) as refused:
        validate_plan({"kind": "daily", "audience": "shareable",
                       "sections": ["book_position"]}, now=NOW)
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
            .order_by(MarketObservationRecord.observed_at_utc.desc()).limit(2000)
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
        assert record.template_version == "market-report/3"
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
            .order_by(MarketObservationRecord.observed_at_utc.desc()).limit(2000)
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


def test_a_period_read_includes_outages_that_ended_and_the_live_view_does_not(env):
    from eurogas_nexus.application.remit_outages import load_outage_rows

    later = NOW + timedelta(days=6)  # both demo outages have ended by then
    with Session(env) as session:
        live = load_outage_rows(session, now=later, horizon_days=14)
        period = load_outage_rows(session, now=later, horizon_days=14, ended_since=NOW)
    assert not [r for r in live if r["status"] == "ended"]
    ended = [r for r in period if r["status"] == "ended"]
    assert ended and all(r["end_utc"] for r in ended)


# ----------------------------------------- round 3: page economy, page one, brand (standard)

from eurogas_nexus.application.reports import render as report_render  # noqa: E402


def test_page_one_carries_the_brand_mark_and_a_lead_exhibit_sized_to_the_page(daily):
    front = daily.html.split('class="r-sheet r-body"')[0]
    assert '<p class="r-brand"><svg' in front and 'aria-hidden="true"' in front
    lead = re.search(r'<figure class="r-exhibit r-lead-ex" id="f1">.*?viewBox="0 0 640 (\d+)"',
                     front)
    assert lead, "page one has no lead exhibit"
    assert report_render.LEAD_MIN <= int(lead.group(1)) <= report_render.LEAD_MAX


def test_the_lead_exhibit_falls_back_to_the_section_chart_when_a_finding_cites_a_table(daily):
    snapshot = dict(daily.snapshot)
    outage = next(f for f in snapshot["fact_sheet"] if f["key"] == "outages.offline")
    snapshot["findings"] = [{"fact_ids": [outage["id"]], "text": outage["sentence"]}] + [
        f for f in snapshot["findings"] if outage["id"] not in f["fact_ids"]]
    html = report_render.render_report(snapshot)
    assert 'class="r-exhibit r-lead-ex"' in html.split('class="r-sheet r-body"')[0]


def test_findings_bold_only_the_lead_clause():
    lead, rest = report_render.split_lead_clause(
        "Net withdrawal from storage was 2,038 GWh/d on 15 Nov, up 142 GWh/d on the day.")
    assert lead == "Net withdrawal from storage was 2,038 GWh/d on 15 Nov"
    assert rest.startswith(", up 142")


def test_text_sits_beside_a_single_exhibit_and_only_exhibits_avoid_breaks(daily):
    body = _body(daily.html)
    storage = re.search(r'<section class="r-section" id="s-storage".*?</section>', body).group(0)
    assert re.search(r'<div class="r-row"><div class="r-text">.*?<figure', storage)
    css = re.search(r"<style>(.*?)</style>", daily.html).group(1)
    assert "figure{margin:0 0 3mm;break-inside:avoid" in css
    assert ".r-section{margin:0 0 3mm}" in css and ".r-section{break-inside" not in css


def test_tables_align_text_left_and_numbers_right(daily):
    css = re.search(r"<style>(.*?)</style>", daily.html).group(1)
    assert "tbody td,tbody th{" in css and "text-align:left;font-weight:400" in css
    assert "td.n,th.n{text-align:right" in css
    glance = re.search(r'<figure class="r-exhibit r-glance".*?</figure>', daily.html).group(0)
    assert '<th scope="col" class="r-unit">Unit</th>' in glance


def test_a_daily_prints_no_annex_and_says_where_the_data_is(env, daily):
    assert 'class="r-annex"' not in daily.html
    assert "CSV download" in daily.html and 'id="report-data"' in daily.html
    asked = _generate(env, _caller("DEMO", "BOOKS:*"), {"kind": "daily", "annex": True})
    assert 'class="r-annex"' in asked.html
    weekly = _generate(env, _caller("DEMO"), {"kind": "weekly"})
    assert 'class="r-annex"' in weekly.html


def test_capacity_offline_outranks_a_routine_withdrawal_change(env):
    report = _generate(env, _caller("DEMO"), {"kind": "daily", "audience": "shareable"})
    sheet = {f["id"]: f for f in report.snapshot["fact_sheet"]}
    lead = sheet[report.snapshot["findings"][0]["fact_ids"][0]]
    assert lead["key"] == "outages.offline", lead["key"]
    assert report.snapshot["headline"].startswith("Outages remove")


def test_a_chinese_edition_prints_its_furniture_in_chinese(env):
    report = _generate(env, _caller("DEMO"), {"kind": "daily", "audience": "shareable"},
                       language="zh-CN")
    assert '<html lang="zh-CN">' in report.html
    assert "要点" in report.html and "一览" in report.html and "第 \" counter(page)" in report.html


# ------------------------------------------------- round 4: asked reports answer the question

from eurogas_nexus.application.reports import answer as asked_answer  # noqa: E402
from eurogas_nexus.application.reports.plan import plan_for_question  # noqa: E402
from eurogas_nexus.application.reports.store import manage_reports  # noqa: E402

NORWAY_QUESTION = "How are the recent Norwegian outages affecting the supply?"


def _asked(env, question=NORWAY_QUESTION, audience="shareable", caller=None):
    plan = plan_for_question(question, audience=audience, now=NOW)["plan"]
    return _generate(env, caller or _caller("DEMO", "BOOKS:*"), plan)


def test_an_asked_report_is_titled_by_its_question_and_answers_it_first(env):
    report = _asked(env)
    snapshot = report.snapshot
    front = report.html.split('class="r-sheet r-body"')[0]
    assert f'<h1 class="r-question">{NORWAY_QUESTION}</h1>' in front
    assert 'class="r-answer"' in front and "Answer" in front
    answer = snapshot["answer"]
    assert answer["basis"] == "rule" and 2 <= len(re.findall(r"[.!?](?:\s|$)", answer["text"])) <= 4
    # The demo desk holds no outage on a Norwegian asset: the answer says so plainly.
    assert asked_answer.NOT_SHOWN in answer["text"]
    sheet = {f["id"]: f for f in snapshot["fact_sheet"]}
    assert sheet[answer["fact_ids"][0]]["key"] == "q.outages.norway"
    body = _body(report.html)
    assert "Evidence" in body and "What the data cannot tell" in body
    assert snapshot["section_order"][0] == "outages"
    assert not BOOK.search(report.html.split('class="r-sheet r-back-sheet"')[0])


def test_the_question_join_attributes_norwegian_outages_and_relates_the_landings():
    rows = [{"facility": "Kollsnes processing plant", "gwh": 300.0, "status": "active",
             "start": "2026-11-05T06:00:00+00:00", "end": None, "norway": "asset"},
            {"facility": "Speicher Breitbrunn", "gwh": 100.0, "status": "active",
             "start": "2026-11-01T06:00:00+00:00", "end": None, "norway": None}]
    days = {date(2026, 10, 28) + timedelta(days=i): 4000.0 + (0 if i < 8 else -250.0)
            for i in range(10)}
    results = {"outages": {"simulated": False}, "pipeline_supply": {"simulated": False}}
    facts_, cannot = asked_answer._outage_supply(
        results, {"outages": {"rows": rows, "state": "current"},
                  "pipeline_supply": {"total": days, "latest": max(days), "state": "current"}},
        date(2026, 11, 6))
    by_key = {f["key"]: f for f in facts_}
    nor = by_key["q.outages.norway"]
    assert nor["value"] == 300.0 and "Kollsnes" in nor["sentence"]
    window = by_key["q.landings.outage_window"]
    assert window["related"] == ["q.outages.norway"] and nor["related"] == [window["key"]]
    assert "down 250 GWh/d" in window["sentence"]
    assert any("Speicher Breitbrunn" in c for c in cannot)
    assert any("coincidence" in c for c in cannot)


def test_an_unanswerable_part_is_said_plainly_and_a_shareable_ask_holds_no_book(env):
    report = _asked(env, "How do oil prices and our book react to TTF this week?")
    assert report.snapshot["cannot_tell"][0].startswith(asked_answer.NOT_SHOWN + " oil")
    assert asked_answer.NOT_SHOWN in report.snapshot["answer"]["text"]
    assert not any(f["section"].startswith("book_") for f in report.snapshot["fact_sheet"])


def test_a_situation_report_finds_its_outage_by_any_grouped_message_id(env):
    from eurogas_nexus.application.reports.sections import Ctx, find_outage

    with Session(env) as session:
        plan = validate_plan({"kind": "situation", "outage_id": "x"}, now=NOW)
        ctx = Ctx(session=session, caller=_caller("DEMO"), now=NOW, plan=plan)
        rows = sections_outage_rows(ctx)
        assert rows and all("messages" in r for r in rows)
        member = rows[0]["messages"][-1]
        assert find_outage(ctx, member)["event_id"] == rows[0]["event_id"]


def sections_outage_rows(ctx):
    from eurogas_nexus.application.reports.sections import _outage_rows

    return _outage_rows(ctx, 400)


def test_a_report_is_deleted_or_renamed_only_by_its_author_or_an_administrator(env):
    from eurogas_nexus.db.models import AuditEventRecord, MarketReportRecord

    author, other = _caller("DEMO", pid="p-author"), _caller("DEMO", pid="p-other")
    admin = Caller(AuthenticatedPrincipal(
        principal_id="p-admin", name="admin", principal_type="USER", role="ADMIN",
        status="ACTIVE", data_scopes=("DEMO",), roles=("ADMIN",)))
    first = _generate(env, author, {"kind": "daily", "sections": ["prices"]})
    second = _generate(env, author, {"kind": "daily", "sections": ["prices"]})
    with Session(env) as session:
        refused = manage_reports(session, other, [first.report_id], action="delete", now=NOW)
        assert refused == {"done": [], "refused": [{"report_id": first.report_id,
                                                    "code": "report_not_owned"}]}
        renamed = manage_reports(session, author, [first.report_id], action="rename",
                                 title="  Desk note  ", now=NOW)
        assert renamed["done"] == [first.report_id]
        assert session.get(MarketReportRecord, first.report_id).title == "Desk note"
        bulk = manage_reports(session, admin, [first.report_id, second.report_id, "mr-none"],
                              action="delete", now=NOW)
        assert bulk["done"] == [first.report_id, second.report_id]
        assert bulk["refused"] == [{"report_id": "mr-none", "code": "report_not_found"}]
        assert session.get(MarketReportRecord, first.report_id) is None
        actions = [(e.action, e.outcome) for e in session.query(AuditEventRecord)
                   .filter(AuditEventRecord.event_type == "report.manage")]
        assert ("report.delete", "refused") in actions and ("report.rename", "renamed") in actions
        assert actions.count(("report.delete", "deleted")) == 2


def test_the_api_deletes_renames_and_lists_with_question_and_editor(env):
    from eurogas_nexus.api.app import create_app

    client = TestClient(create_app())
    made = client.post("/api/reports/market", json={
        "kind": "ask", "question": NORWAY_QUESTION, "audience": "shareable",
        "sections": ["pipeline_supply", "outages"], "use_model": False}).json()["data"]
    assert made["answer"]["text"]
    row = next(r for r in client.get("/api/reports/market").json()["data"]
               if r["report_id"] == made["report_id"])
    assert row["question"] == NORWAY_QUESTION and row["edited_by"] == "rule"
    assert client.patch(f"/api/reports/market/{made['report_id']}",
                        json={"title": "Norway outages"}).status_code == 200
    assert client.delete(f"/api/reports/market/{made['report_id']}").status_code == 200
    assert client.delete(f"/api/reports/market/{made['report_id']}").status_code == 404
    bulk = client.post("/api/reports/market/bulk-delete", json={"report_ids": ["mr-x"]})
    assert bulk.json()["data"]["refused"][0]["code"] == "report_not_found"


# ------------------------------------- round 5: market facts only; the report's language

from eurogas_nexus.application.reports.editor import META  # noqa: E402


def _sentences(snapshot):
    texts = [snapshot["headline"], snapshot.get("standfirst") or ""]
    texts += [f["text"] for f in snapshot.get("findings") or []]
    texts += [f.get("implication") or "" for f in snapshot.get("findings") or []]
    texts += [(snapshot.get("answer") or {}).get("text") or ""]
    texts += list(snapshot.get("cannot_tell") or []) + [w["text"] for w in snapshot.get("watch")
                                                        or []]
    for section in snapshot["sections"]:
        if section["status"] == "ok":
            texts += [section["commentary"]["headline"], *section["commentary"]["bullets"]]
    return [s for t in texts for s in re.split(r"(?<=[.!?。])\s*", t) if s]


@pytest.mark.parametrize("language", ["en", "zh-CN"])
def test_rule_text_states_market_facts_and_never_speaks_about_the_report(env, language):
    for plan in ({"kind": "daily"}, {"kind": "weekly"},
                 plan_for_question(NORWAY_QUESTION, audience="shareable", now=NOW)["plan"]):
        report = _generate(env, _caller("DEMO", "BOOKS:*"), plan, language=language)
        meta = [s for s in _sentences(report.snapshot) if META.search(s)]
        assert not meta, meta


def test_a_chinese_report_is_written_in_chinese_throughout(env):
    report = _generate(env, _caller("DEMO", "BOOKS:*"), {"kind": "daily"}, language="zh-CN")
    allowed = {"Demo", "Haldor", "Kestrel", "field", "export", "line", "GWh", "MWh", "TWh", "EUR",
               "GBp", "TTF", "NBP", "Dec", "LNG", "Rhinmark", "Handel", "GmbH", "Nordvik",
               "Petroleum", "ASA", "Aldermoor", "Energy", "plc", "desk", "trader", "Brae",
               "North", "supply", "Easington", "Fergus", "NETRA", "Dornum", "Emden",
               "Norwegian", "shelf"}
    english = [s for s in _sentences(report.snapshot)
               if [w for w in re.findall(r"[A-Za-z]{3,}", s) if w not in allowed]]
    assert not english, english[:5]
    html = report.html
    assert "方法与来源" in html and "各指标的计算方法" in html and "近月合约每日收盘价" in html
    assert "Front-month daily closes" not in html and "How each indicator" not in html
