"""The portfolio and outlook report: planning, sections on the demo desk, audience, Chinese."""

from __future__ import annotations

import importlib.util
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import eurogas_nexus.db.models  # noqa: F401  (registers every table)
from eurogas_nexus.application.caller import Caller
from eurogas_nexus.application.reports import findings
from eurogas_nexus.application.reports.catalogue import (
    BOOK_SECTIONS,
    PORTFOLIO_SECTIONS,
    PlanError,
    validate_plan,
)
from eurogas_nexus.application.reports.engine import generate_report
from eurogas_nexus.application.reports.facts import fact
from eurogas_nexus.application.reports.plan import rule_plan
from eurogas_nexus.db.base import Base
from eurogas_nexus.security.identity import AuthenticatedPrincipal

SEED = Path(__file__).resolve().parents[2] / "scripts" / "demo" / "seed_demo_desk.py"
NOW = datetime(2026, 11, 26, 7, tzinfo=UTC)
QUESTION = ("What's our portfolio like right now, and what are we expecting for the rest of "
            "2026 and next year? Trades by counterparty and delivery type, sales by country "
            "and hub, realised prices and P&L, strategies, risk.")
PF = tuple(key for key in PORTFOLIO_SECTIONS if key.startswith("pf_"))


def _caller(*scopes: str) -> Caller:
    return Caller(AuthenticatedPrincipal(
        principal_id="p-head", name="desk head", principal_type="USER", role="ANALYST",
        status="ACTIVE", data_scopes=scopes, roles=("ANALYST",)))


@pytest.fixture(scope="module")
def desk(tmp_path_factory):
    path = tmp_path_factory.mktemp("portfolio") / "desk.sqlite"
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
        yield engine, url


@pytest.fixture(scope="module")
def reports(desk):
    engine, url = desk
    plan = {"kind": "ask", "question": QUESTION, "sections": list(PORTFOLIO_SECTIONS)}
    out = {}
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("RUNTIME_STORE_DATABASE_URL", url)
        mp.setenv("EUROGAS_NEXUS_DEMO_MARKS", "true")
        for language in ("en", "zh-CN"):
            with Session(engine) as session:
                out[language] = generate_report(session, _caller("DEMO", "BOOKS:*"), plan,
                                                now=NOW, language=language, store=False)
    return out


def _sections(report):
    return {s["key"]: s for s in report.snapshot["sections"]}


def test_a_portfolio_question_plans_the_portfolio_and_outlook_sections():
    plan = rule_plan(QUESTION, "internal")
    assert plan["sections"][:len(PORTFOLIO_SECTIONS)] == list(PORTFOLIO_SECTIONS)
    # The book sections the portfolio covers itself are not added a second time.
    assert not {"book_position", "book_pnl", "book_contracts"} & set(plan["sections"])
    # The firm's own cargoes are held; a budget is not, and a question naming it is told so.
    assert not any(item.startswith("LNG cargo tracking") for item in plan["missing"])
    asked = rule_plan(QUESTION + " How are we against budget?", "internal")
    assert any("budget" in item for item in asked["missing"])


def test_the_scheduled_reports_keep_their_book_sections():
    assert all(key.startswith("book_") for key in BOOK_SECTIONS)
    assert not set(PF) & set(BOOK_SECTIONS)


def test_a_shareable_report_leaves_the_portfolio_out():
    with pytest.raises(PlanError) as refused:
        validate_plan({"kind": "ask", "audience": "shareable", "question": QUESTION,
                       "sections": list(PF)}, now=NOW)
    assert refused.value.code == "internal_section_in_shareable"


def test_every_portfolio_section_is_built_on_the_demo_desk(reports):
    report = reports["en"]
    sections = _sections(report)
    for key in PF:
        assert sections[key]["status"] == "ok", (key, sections[key].get("empty"))
    assert report.snapshot["title"].startswith("Portfolio and outlook")
    outlook = sections["pf_outlook"]
    captions = [t["caption"] for t in outlook["tables"]]
    assert any(c.startswith("Contracted against open volume") for c in captions)
    assert any(c.startswith("Value change of the open position") for c in captions)
    # The FOB cargo is said to be outside the hub figures, not silently dropped.
    assert "FOB LNG cargo" in " ".join(outlook["commentary"]["bullets"])
    # Shares and counts read as such, not as two-decimal numbers.
    bucket = next(t for t in outlook["tables"] if t["caption"].startswith("Contracted"))
    assert all(row["sold_share"].endswith("%") or row["sold_share"] == "-"
               for row in bucket["rows"])
    supply = sections["pf_supply"]
    types = {row["type"] for row in supply["tables"][0]["rows"]}
    assert {"beach", "pipeline", "hub", "lng_cargo"} <= types
    trades = sections["pf_trades"]
    assert any(t["caption"].startswith("Sales by hub and country") for t in trades["tables"])
    # Every section names its source and as-of.
    for key in PF:
        assert sections[key]["evidence"]["sources"], key


def test_the_answer_cites_the_portfolio_and_says_no_budget_is_held(reports):
    report = reports["en"]
    answer = report.snapshot["answer"]["text"]
    assert answer.startswith("Rest of 2026:")
    assert "budget" in answer
    assert "{observations}" not in report.html
    assert "1 trades" not in report.html


def test_the_chinese_edition_writes_the_portfolio_in_chinese(reports):
    report = reports["zh-CN"]
    assert report.snapshot["title"].startswith("组合与展望")
    html = report.html
    for words in ("远期展望", "已实现与未实现", "供应组合", "LNG 船货"):
        assert words in html, words
    assert "Contracted against open volume" not in html


def test_a_quiet_prices_only_report_does_not_speak_for_flows_or_storage():
    sheet = [fact("price.TTF", "prices", "TTF", 42.06, "EUR/MWh", day="2026-11-25",
                  state="current", sentence="TTF closed at 42.06 EUR/MWh.", score=0.2,
                  reason="test")]
    sheet[0]["id"] = "F1"
    ranked = findings.rank_findings(sheet)
    assert ranked[0]["text"] == findings.PRICES_QUIET
    assert findings.headline_of(ranked, sheet) == "Prices within their recent range"


def _generate(desk, caller, language="en"):
    """A report with book isolation on (``EUROGAS_NEXUS_PORTFOLIO_ISOLATION``), as a
    deployment that separates books runs."""

    engine, url = desk
    plan = {"kind": "ask", "question": QUESTION, "sections": list(PORTFOLIO_SECTIONS)}
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("RUNTIME_STORE_DATABASE_URL", url)
        mp.setenv("EUROGAS_NEXUS_DEMO_MARKS", "true")
        mp.setenv("EUROGAS_NEXUS_PORTFOLIO_ISOLATION", "true")
        with Session(engine) as session:
            return generate_report(session, caller, plan, now=NOW, language=language,
                                   store=False)


def test_a_caller_limited_to_one_book_sees_only_that_book(desk, reports):
    """The portfolio reads only the books the caller may see: a TTF-book trader's report holds
    the NL book and nothing of the UK book or the LNG book."""

    everything = _sections(reports["en"])
    seen_all = {b for key in PF for b in everything[key].get("books") or []}
    assert {"demo-uk-nbp", "demo-nl-ttf"} <= seen_all  # the head of desk sees both

    report = _generate(desk, _caller("DEMO", "BOOKS:BOOK:demo-nl-ttf"))
    sections = _sections(report)
    for key in PF:
        assert set(sections[key].get("books") or []) <= {"demo-nl-ttf"}, key
    assert "demo-uk-nbp" not in report.html
    # The LNG book's cargoes (Meridian, Halcyon, Solace) are not in a TTF-book report.
    for vessel in ("Meridian", "Halcyon", "Solace"):
        assert vessel not in report.html, vessel


def test_a_caller_without_a_book_gets_the_portfolio_omitted_with_the_reason(desk):
    report = _generate(desk, _caller("DEMO"))
    assert not set(PF) & set(_sections(report))
    omitted = {item["key"]: item for item in report.snapshot["omitted"]}
    for key in PF:
        assert omitted[key]["reason"] == "the generating principal may see no book", key
    for vessel in ("Meridian", "Halcyon", "Solace"):
        assert vessel not in report.html, vessel


def test_marks_from_the_simulated_close_are_marked_simulated(reports):
    """Rule 17: a value from the demo's simulated close never reads as a market price."""

    sections = _sections(reports["en"])
    assert sections["pf_pnl"]["simulated"] is True
    assert sections["pf_outlook"]["simulated"] is True  # its value at risk reads the marks


def test_delivery_type_and_counterparty_fall_back_in_order():
    from types import SimpleNamespace

    from eurogas_nexus.application.reports import portfolio
    from eurogas_nexus.domain.contracts import kinds

    def contract(**kw):
        base = {"contract_id": "c1", "contract_kind": None, "kind_terms": None,
                "resource_type": None, "delivery_point_name": "", "notes": None,
                "master_contract_id": None}
        return SimpleNamespace(**{**base, **kw})

    assert portfolio.delivery_type(contract(contract_kind=kinds.LNG_CARGO), None) == "lng_cargo"
    assert portfolio.delivery_type(contract(resource_type="BEACH_DELIVERY"), "NBP") == "beach"
    assert portfolio.delivery_type(contract(delivery_point_name="NBP"), "NBP") == "hub"
    assert portfolio.delivery_type(contract(delivery_point_name="Bacton IP"), "NBP") == "pipeline"
    assert portfolio.delivery_type(contract(), None) == "other"

    line = SimpleNamespace(name="Aldermoor Energy", counterparty_id="ALD", aliases=["ALDM"],
                           contract_ids=["c1"])
    # The credit line first, then the name in the notes, then the master agreement's, then
    # "not recorded".
    assert portfolio.counterparty_of(contract(), [line], {}) == "Aldermoor Energy"
    noted = contract(contract_id="c2", notes='{"counterparty": "Rhinmark"}')
    assert portfolio.counterparty_of(noted, [line], {}) == "Rhinmark"
    master = contract(contract_id="m1", notes='{"counterparty": "Nordvik"}')
    child = contract(contract_id="c3", master_contract_id="m1")
    assert portfolio.counterparty_of(child, [], {"m1": master}) == "Nordvik"
    assert portfolio.counterparty_of(contract(contract_id="c4"), [], {}) == "not recorded"

    order = SimpleNamespace(account_label="ALDM", venue="ICE Endex", provider_id=None)
    assert portfolio.trade_counterparty(order, [line]) == "Aldermoor Energy"
    cleared = SimpleNamespace(account_label="", venue="ICE Endex", provider_id=None)
    assert portfolio.trade_counterparty(cleared, [line]) == "ICE Endex (cleared)"
