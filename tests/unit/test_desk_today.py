"""The Today read (UX-05): four populated rows on the demo desk, scoped as the brief is."""

from __future__ import annotations

import importlib.util
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import eurogas_nexus.db.models  # noqa: F401  (registers every table)
from eurogas_nexus.application.caller import Caller
from eurogas_nexus.application.desk_today import build_today, net_positions
from eurogas_nexus.application.monitoring_service import scan_monitoring_conditions
from eurogas_nexus.db.base import Base
from eurogas_nexus.domain.market.units import convert_price
from eurogas_nexus.domain.portfolio.position_ladder import PositionLeg
from eurogas_nexus.security import portfolio_scope
from eurogas_nexus.security.identity import AuthenticatedPrincipal

SEED = Path(__file__).resolve().parents[2] / "scripts" / "demo" / "seed_demo_desk.py"
NOW = datetime(2026, 11, 7, 7, tzinfo=UTC)
STATES = {"current", "late", "stale", "never", "manual"}


def _principal(*scopes: str) -> Caller:
    return Caller(
        AuthenticatedPrincipal(
            principal_id="p-analyst",
            name="analyst",
            principal_type="USER",
            role="ANALYST",
            status="ACTIVE",
            data_scopes=scopes,
            roles=("ANALYST",),
        )
    )


def _seeded(tmp_path, monkeypatch, now):
    url = f"sqlite+pysqlite:///{tmp_path / 'desk.sqlite'}"
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    monkeypatch.setenv("EUROGAS_NEXUS_DEMO_MARKS", "true")
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    spec = importlib.util.spec_from_file_location("seed_demo_desk", SEED)
    seed = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(seed)
    with Session(engine) as session:
        seed.seed(session, now)
        session.commit()
        scan_monitoring_conditions(session, now_utc=now, enrich_with_llm=False)
    return engine


@pytest.fixture
def desk(tmp_path, monkeypatch):
    return _seeded(tmp_path, monkeypatch, NOW)


def _balance():
    from eurogas_nexus.api.routes.public.fundamentals import get_nwe_balance

    return get_nwe_balance(None, days=1, history_days=14, format="json")["data"]


def _today(engine, caller, now=NOW):
    with Session(engine) as session:
        return build_today(session, caller, now=now, balance_reader=_balance)


def _figures(value):
    """Every figure object in a response (it has a unit, an as-of time and a state)."""

    if isinstance(value, dict):
        if {"unit", "as_of", "state", "value"} <= set(value):
            yield value
        for item in value.values():
            yield from _figures(item)
    elif isinstance(value, list):
        for item in value:
            yield from _figures(item)


def test_all_four_rows_are_populated_on_the_demo_desk(desk):
    data = _today(desk, _principal("DEMO", "BOOKS:*"))
    keys = [row["key"] for row in data["rows"]]
    # "My gas day" is appended, so every earlier row keeps its position.
    assert keys == ["key_figures", "changes", "book", "fundamentals", "needs_me", "gas_day",
                    "checklist"]
    assert all(row["populated"] for row in data["rows"])
    key, changes, book, fundamentals, _ = data["rows"][:5]
    # The book's hubs first, then the other hubs the demo market prices.
    assert [item["hub"] for item in key["prices"]][:2] == ["NBP", "TTF"]
    assert all(item["day_change"] is not None for item in key["prices"])
    assert key["position"]["today"]["unit"] == "MWh/d"
    assert key["tightest_limit"]["status"] == "breach"  # the demo's Rhinmark line
    assert key["tightest_limit"]["why"]["subject"] == "credit"
    assert changes["outages"]["counts"]["active"] >= 1
    assert changes["alerts"]["counts"]["open"] >= 1
    assert {hub["hub"] for hub in book["hubs"]} == {"NBP", "TTF"}
    assert all(hub["day_pnl_change"]["method"]["key"] == "day_pnl_change"
               for hub in book["hubs"])
    assert fundamentals["storage"]["series"] and fundamentals["balance"]["series"]
    assert fundamentals["storage"]["target"]["pct"] == 90.0
    # Demo prices are said to be simulated, figure by figure and for the page; every market
    # figure is, so the page says it once (positions are book data and do not count).
    assert data["simulated"] and data["simulated_notice"] and data["all_simulated"]
    assert key["prices"][0]["simulated"] and key["prices"][0]["source"] == "Simulated price"
    # Nothing says "Withheld"; every figure has a unit, an as-of time and a contract state.
    assert "withheld" not in json.dumps(data).casefold()
    figures = list(_figures(data))
    assert len(figures) >= 10
    for item in figures:
        assert item["unit"] and item["as_of"] and item["state"] in STATES, item["key"]


def test_the_day_pnl_change_is_the_open_position_times_the_close_change(desk):
    data = _today(desk, _principal("DEMO", "BOOKS:*"))
    prices = {item["hub"]: item for item in data["rows"][0]["prices"]}
    for hub in data["rows"][2]["hubs"]:
        price = prices[hub["hub"]]
        # The price is shown in the desk's quotation (NBP p/th); the P&L is per MWh.
        per_mwh = convert_price(price["day_change"], price["unit"], hub["mark"]["unit_mwh"])
        expected = hub["net_open_mwh"] * per_mwh
        assert hub["day_pnl_change"]["value"] == pytest.approx(expected, rel=1e-3)
        assert hub["mark"]["same_as"] == f"price.{hub['hub']}"  # one number, one place


def test_outage_counts_are_the_ticker_and_map_counts(tmp_path, monkeypatch):
    from eurogas_nexus.api.app import create_app

    now = datetime.now(UTC)  # the routes read the clock, so the desk is seeded at it
    desk = _seeded(tmp_path, monkeypatch, now)
    data = _today(desk, _principal("DEMO", "BOOKS:*"), now=now)
    assert data["rows"][1]["outages"]["counts"]["active"] >= 1
    client = TestClient(create_app())
    outages = client.get("/api/physical/outages", params={"horizon_days": 14}).json()["data"]
    situation = client.get("/api/portfolio/map-situation").json()["data"]
    counts = data["rows"][1]["outages"]["counts"]
    assert counts["active"] == sum(1 for row in outages if row["status"] == "active")
    assert counts["total"] == len(outages)
    assert counts["active"] == situation["totals"]["outages_active"]


def test_a_user_without_the_data_scope_sees_no_demo_prices_or_marks(desk):
    data = _today(desk, _principal("BOOKS:*"))
    key, _, book, fundamentals, _ = data["rows"][:5]
    # Positions are book data: still there; prices of an unlicensed family are not.
    assert key["position"] is not None
    assert all("empty" in item for item in key["prices"])
    assert key["prices"][0]["empty"]["code"] == "no_licensed_close"
    for hub in book["hubs"]:
        assert hub["mark"] is None
        assert hub["day_pnl_change"]["empty"]["code"] == "no_mark"
    assert "empty" in fundamentals["storage"]
    assert fundamentals["balance"]["empty"]["code"] == "balance_not_licensed"
    assert all(hub["empty"] for hub in key["market"]["hubs"])
    assert all("empty" in spread for spread in key["market"]["spreads"])
    assert "empty" in fundamentals["storage_europe"]
    priced = [item["key"] for item in _figures(data)
              if item["key"].startswith(("price.", "mark.", "pnl.", "storage.", "balance.",
                                         "market.", "spread."))]
    assert priced == []


def test_a_user_without_a_book_sees_no_positions_limits_or_book(desk, monkeypatch):
    monkeypatch.setenv(portfolio_scope.ISOLATION_ENV, "true")
    portfolio_scope.set_request_scope(("DEMO", "BOOKS:BOOK:SOMEONE-ELSES"))
    try:
        data = _today(desk, _principal("DEMO", "BOOKS:BOOK:SOMEONE-ELSES"))
    finally:
        portfolio_scope._current.set(None)
    key, changes, book, _, needs_me = data["rows"][:5]
    assert all(item["kind"] != "limit" for item in needs_me["items"])
    assert key["position"] is None and key["position_empty"]["code"] == "no_position"
    assert key["tightest_limit"] is None
    assert key["limit_empty"]["code"] == "no_limits"
    assert book["hubs"] == [] and book["empty"]["code"] == "no_position"
    assert all(item["category"] != "limits" for item in changes["alerts"]["items"])
    # Market rows stand: prices and outages are not book data.
    assert {"NBP", "TTF"} <= {item["hub"] for item in key["prices"]}
    assert changes["outages"]["counts"]["active"] >= 1


def test_one_principal_under_another_book_scope_is_not_served_the_first_scopes_findings(
    desk, monkeypatch
):
    """The discovery read is cached for a minute; the same principal on the same store, read
    first head-office-wide and then as a regional user, must not see head office's limits."""

    monkeypatch.setenv(portfolio_scope.ISOLATION_ENV, "true")
    wide = _principal("DEMO", "BOOKS:*")
    portfolio_scope.set_request_scope(("DEMO", "BOOKS:*"))
    try:
        first = _today(desk, wide)
    finally:
        portfolio_scope._current.set(None)
    assert any(item["kind"] == "limit" for item in first["rows"][4]["items"])
    narrow = _principal("DEMO", "BOOKS:BOOK:SOMEONE-ELSES")
    portfolio_scope.set_request_scope(("DEMO", "BOOKS:BOOK:SOMEONE-ELSES"))
    try:
        second = _today(desk, narrow)
    finally:
        portfolio_scope._current.set(None)
    assert all(item["kind"] != "limit" for item in second["rows"][4]["items"])


def test_late_and_stale_figures_are_named(desk):
    later = NOW + timedelta(days=6)  # no new closes or storage since the seed
    data = _today(desk, _principal("DEMO", "BOOKS:*"), now=later)
    named = {item["key"]: item["state"] for item in data["stale_figures"]}
    assert named["price.TTF"] == "stale" and named["price.NBP"] == "stale"
    assert "storage.nwe.fill" in named
    assert all(item["as_of"] for item in data["stale_figures"])


def test_the_route_serves_the_read(desk):
    from eurogas_nexus.api.app import create_app

    response = TestClient(create_app()).get("/api/desk/today")
    assert response.status_code == 200, response.text
    body = response.json()
    assert [row["key"] for row in body["data"]["rows"]][0] == "key_figures"
    assert body["meta"]["source_references"] == ["runtime-postgresql:desk-today"]


def test_the_front_month_is_the_months_average():
    today = datetime(2026, 11, 7).date()
    legs = [
        PositionLeg("physical", "TTF", today, datetime(2027, 9, 30).date(), 100.0, 30.0, "a"),
        # Starts mid-December: 16 of 31 days.
        PositionLeg("financial", "TTF", datetime(2026, 12, 16).date(),
                    datetime(2026, 12, 31).date(), -31.0, 40.0, "b"),
    ]
    net = net_positions(legs, today)
    assert net["TTF"]["today"] == pytest.approx(100.0)
    assert net["TTF"]["front_month"] == pytest.approx(100.0 - 16.0)


def test_nbp_is_shown_in_pence_per_therm_and_the_mark_is_too(desk):
    data = _today(desk, _principal("DEMO", "BOOKS:*"))
    prices = {item["hub"]: item for item in data["rows"][0]["prices"]}
    book = {hub["hub"]: hub for hub in data["rows"][2]["hubs"]}
    assert prices["NBP"]["unit"] == "GBp/th" and prices["TTF"]["unit"] == "EUR/MWh"
    # The mark is quoted in the desk's unit (one price, one unit on the screen), is the
    # same close as the shown price, and carries the per-MWh value the book is valued at.
    mark = book["NBP"]["mark"]
    assert mark["unit"] == "GBp/th" and mark["same_as"] == "price.NBP"
    assert mark["value"] == pytest.approx(prices["NBP"]["value"], abs=1e-3)
    assert mark["unit_mwh"] == "GBP/MWh"
    assert convert_price(mark["value_mwh"], "GBP/MWh", "GBp/th") == pytest.approx(
        prices["NBP"]["value"], abs=1e-3
    )
    assert book["TTF"]["mark"]["unit"] == "EUR/MWh"


def test_the_section_e_rows_my_market_needs_me_and_europe_storage(desk):
    """Design basis 2, E.2: my market (DA and front month per focus hub, a 30-day series, the
    spreads against TTF in EUR/MWh with the route cost or its reason), what needs me (one
    ranked list of at most five) and Europe's storage against its history."""

    data = _today(desk, _principal("DEMO", "BOOKS:*"))
    key, _, _, fundamentals, needs_me = data["rows"][:5]
    # My hubs: the book's (NBP, TTF), then the board's order, at most four.
    assert data["focus_hubs"] == ["NBP", "TTF", "THE", "PEG"]
    market = key["market"]
    assert [hub["hub"] for hub in market["hubs"]] == data["focus_hubs"]
    nbp = market["hubs"][0]["front_month"]
    assert nbp["unit"] == "GBp/th" and nbp["simulated"]  # the desk's quotation (rule 17)
    assert 20 <= len(nbp["series"]) <= 30 and nbp["series"][-1]["day"] == nbp["close_day"]
    assert nbp["day_change"] is not None
    spreads = {item["pair"]: item for item in market["spreads"]}
    assert set(spreads) == {"NBP–TTF", "THE–TTF"}
    for spread in spreads.values():
        assert spread["unit"] == "EUR/MWh" and spread["simulated"]
        route = spread["route_cost"]
        # A route cost is a figure with a verdict, or no figure and the reason: never zero.
        assert (route["value"] is not None and route["verdict"]) or route["reason"]
        if route["value"] is not None:
            # Priced from the cheaper hub to the dearer one, and judged on the absolute spread,
            # as Research > Spreads judges it (QA-R-06).
            hub, reference = spread["pair"].split("–")
            dearer = hub if spread["value"] >= 0 else reference
            assert route["to"] == dearer and route["from"] != dearer
            assert route["net"] == round(abs(spread["value"]) - route["value"], 3)
            assert route["verdict"] == ("in_the_money" if route["net"] > 0 else "out_of_the_money")
    assert spreads["NBP–TTF"]["fx"]["base"] == "GBP"  # the forward FX it used is named
    # What needs me: at most five, each with its kind and an object to open.
    assert 1 <= len(needs_me["items"]) <= 5 and needs_me["quiet"] is None
    assert needs_me["items"][0]["kind"] in {"opportunity", "outage"}
    # A nomination of the gas day checklist (Haldor nominated 12 % under) joins the list.
    assert all(item["kind"] in {"opportunity", "outage", "limit", "nomination"}
               for item in needs_me["items"])
    outages = [item for item in needs_me["items"] if item["kind"] == "outage"]
    assert outages and all(item["hub"] in data["focus_hubs"] for item in outages)
    # Europe's storage: the season with its history band, the focus countries first.
    europe = fundamentals["storage_europe"]
    assert europe["region"]["code"] == "EU" and europe["region"]["season"]["band"]
    assert europe["focus_countries"][:2] == ["NL", "DE"]
    assert [c["code"] for c in europe["countries"]][:2] == ["NL", "DE"]
    assert len(europe["countries"]) <= 8


def test_what_needs_me_reads_the_role_aware_discovery(desk):
    """CP-24 into CP-19: the opportunities in "What needs me" come from the discovery read (one
    ranked, phrased list per job function, every read under the caller), not from the list
    endpoint; each opens on Deals → Opportunities with the opportunity selected, and carries
    the Chinese sentence built from the same evidence."""

    import inspect

    from eurogas_nexus.application import desk_today
    from eurogas_nexus.application.opportunities.service import run_evaluation

    assert "list_opportunities" not in inspect.getsource(desk_today._needs_me)
    caller = _principal("DEMO", "BOOKS:*")
    with Session(desk) as session:
        for _ in range(2):  # shown only after two consecutive evaluations
            run_evaluation(session, trigger="test", triggered_by="test", now_utc=NOW,
                           caller=caller, demo_desk=True)
            session.commit()
    needs_me = _today(desk, caller)["rows"][4]
    assert 1 <= len(needs_me["items"]) <= 5
    opportunities = [item for item in needs_me["items"] if item["kind"] == "opportunity"]
    assert opportunities
    for item in opportunities:
        assert item["lane"] in {"must_act", "could_act"}
        assert item["target"] == {"mode": "deals", "task": "opportunities",
                                  "params": {"opportunity": item["id"]}}
        assert item["title"] and item["title_zh"] and item["title"] != item["title_zh"]
        assert item["simulated"] and item["as_of"]  # demo desk: marked, with its evaluation time
    # At most one "could act" item, and it comes after everything that must be acted on.
    kinds = [(item["kind"], item.get("lane")) for item in needs_me["items"]]
    assert kinds.count(("opportunity", "could_act")) <= 1
    if ("opportunity", "could_act") in kinds:
        assert kinds[-1] == ("opportunity", "could_act")


def test_simulated_is_said_once_when_every_price_and_mark_is_simulated():
    """A real ECB rate, tariff or public storage figure beside simulated prices is not 'mixed'."""

    from eurogas_nexus.application.desk_today import _all_simulated

    def item(key: str, simulated: bool) -> dict:
        return {"key": key, "simulated": simulated}

    prices = [item("price.TTF", True), item("market.NBP.day_ahead", True), item("mark.TTF", True)]
    real_inputs = [item("storage.nwe.fill", False), item("outages.active", False),
                   item("position.net.today", False), item("limit.credit.cp-1", False)]
    assert _all_simulated(prices + real_inputs)
    assert not _all_simulated([*prices, item("spread.NBP.TTF", False)])  # genuinely mixed prices
    assert not _all_simulated(real_inputs)  # no prices at all: nothing to say



def test_the_ladder_marks_the_front_month_at_the_month_ahead_close(desk):
    """One number: every hub's curve front month is its newest month-ahead close, and the
    ladder marks at that curve (not at a seasonal shape of its own); for TTF it is the price
    Today shows."""

    from datetime import date

    from eurogas_nexus.application.position_inputs import ladder_inputs
    from eurogas_nexus.db.models import MarketObservationRecord

    caller = _principal("DEMO", "BOOKS:*")
    prices = {item["hub"]: item for item in _today(desk, caller)["rows"][0]["prices"]}
    today = NOW.date()
    inputs = ladder_inputs(caller, today, today.replace(day=1), date(2029, 12, 1))
    with Session(desk) as session:
        closes = {}
        for row in (session.query(MarketObservationRecord)
                    .filter_by(source_reference="demo:history")
                    .order_by(MarketObservationRecord.observed_at_utc)):
            closes[row.metadata_json["hub"]] = row.price
    for hub in ("TTF", "NBP", "THE", "PEG", "ZTP"):
        curve = {point.month: point.price for point in inputs.curve.points if point.hub == hub}
        assert curve["2026-12"] == pytest.approx(closes[hub], abs=1e-6), hub
        assert inputs.marks[(hub, "2026-12")] == pytest.approx(curve["2026-12"], abs=1e-6), hub
        # A seasonal term structure, not one year repeated: winter over summer, January the
        # peak, and no two Decembers alike (the month-on-month drift, QA-T-02).
        assert curve["2027-01"] > curve["2026-12"] > curve["2027-07"], hub
        assert len({curve["2026-12"], curve["2027-12"], curve["2028-12"], curve["2029-12"]}) == 4
    # TTF, the arbitrage band's reference, is quoted on the board at its close: Today agrees.
    assert inputs.marks[("TTF", "2026-12")] == pytest.approx(prices["TTF"]["value"], abs=1e-3)


def test_today_and_the_position_ladder_show_one_net_position_per_hub(desk):
    """Today's NBP net was 11.91 TWh and the ladder's 11.19 on the demo: Today summed 13
    months (the current one plus 12), the ladder 12. Both now read ``ladder_horizon`` and
    ``net_position_by_hub``."""

    from eurogas_nexus.application.desk_today import book_horizon
    from eurogas_nexus.domain.portfolio.position_ladder import ladder_horizon

    caller = _principal("DEMO", "BOOKS:*")
    assert book_horizon(NOW.date()) == ladder_horizon(NOW.date())
    today = {hub["hub"]: hub["net_open_mwh"] for hub in _today(desk, caller)["rows"][2]["hubs"]}
    from eurogas_nexus.application.position_inputs import ladder_inputs
    from eurogas_nexus.domain.portfolio.position_ladder import build_ladder, tenor_exposure

    start, end = ladder_horizon(NOW.date())
    inputs = ladder_inputs(caller, NOW.date(), start, end)
    ladder = {item["hub"]: item["net_mwh"] for item in tenor_exposure(
        build_ladder(inputs.legs, horizon_start=start, horizon_end=end))}
    assert today and set(today) <= set(ladder)
    for hub, net in today.items():
        assert net == pytest.approx(ladder[hub], abs=0.1), hub
