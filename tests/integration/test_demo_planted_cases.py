"""The demo market's planted cases are found on their days, and nothing of their kind on a
quiet day (``scripts/demo/demo_market.py`` PLANTED_CASES; docs SELF_HOSTED_DEMO.md).

Each case: a fresh demo seed at 09:00 UTC on the day, two evaluations (an item is listed
after two, the persistence rule), then the caller's list. The listed set (lane, type code,
subject) must be exactly the expected one:

- every day: the hedge gap (G) and the outage exposures (E, O1) in "must act"; CEGH winter
  over summer above the stated storage cost (T, T1) in the market lane; and, on these seeds,
  the held BBL capacity (C, TTF -> NBP months, charges sunk) in "could act" (C is not planted:
  it depends on NBP's own walk inside the arbitrage band, and is present on all three days);
- L1 day: NBP day-ahead over TTF day-ahead net of the BBL route (market L, TTF -> NBP);
- W1 day: TTF within-day over day-ahead (market P);
- S1 day (the day before a planted S1 gas day): tomorrow left open, the UK book long at NBP
  and the NL book short at TTF (sell-down S in "must act"; the UK book's TTF residual has no
  TTF rate and is a "cannot evaluate", not listed);
- R1 day (the 11th or 12th of a month): Aldermoor nominated less than the desk's sale at NBP
  and the TSO confirmed the lesser. That is a scheduling break (SCHED-1's reconciliation,
  ``tests/integration/test_gas_day_reconciliation.py``), not an opportunity: nothing more is
  listed, and the reconciliation shows the one lesser-rule cut, which a quiet day does not;
- a quiet day: nothing more (every other gas day the demo schedule balances each book).
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.application.caller import Caller
from eurogas_nexus.application.opportunities.listing import list_opportunities
from eurogas_nexus.application.opportunities.service import run_evaluation
from eurogas_nexus.db.base import Base
from eurogas_nexus.security.identity import AuthenticatedPrincipal

DEMO = Path(__file__).resolve().parents[2] / "scripts" / "demo"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"{name}_planted", DEMO / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


SEED = _load("seed_demo_desk")
MARKET = _load("demo_market")

L1_DAY = date(2026, 12, 7)  # Monday, ordinal % 23 == 1
W1_DAY = date(2026, 12, 14)  # Monday, ordinal % 17 == 5
QUIET_DAY = date(2026, 12, 2)  # Wednesday, neither
S1_DAY = date(2026, 12, 17)  # Thursday: tomorrow, the 18th, is an S1 gas day
R1_DAY = date(2026, 12, 10)  # Thursday: today's gas day quiet, tomorrow's (the 11th) an R1 day

EVERY_DAY = {
    ("must_act", "G", "Haldor supply (Easington)"),
    ("must_act", "E", "Demo Haldor field, Norwegian shelf · Haldor supply (Easington)"),
    ("must_act", "E", "Demo Kestrel export line · Kestrel supply (TTF)"),
    ("must_act", "E", "Demo Kestrel export line · Kestrel UK leg (TTF, sold at NBP)"),
    ("could_act", "C", "TTF → NBP"),
    ("market", "T", "CEGH"),
}


def _principal() -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        principal_id="p-trader",
        name="trader",
        principal_type="USER",
        role="ANALYST",
        status="ACTIVE",
        data_scopes=("*",),
        roles=("ANALYST",),
    )


def _listed(tmp_path, monkeypatch, day: date) -> set[tuple[str, str, str]]:
    url = f"sqlite+pysqlite:///{(tmp_path / f'planted-{day}.sqlite').as_posix()}"
    engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    now = datetime(day.year, day.month, day.day, 9, tzinfo=UTC)
    with Session(engine) as session:
        SEED.seed(session, now, history_days=3)
        session.commit()
        for minute in (0, 1):
            run_evaluation(
                session,
                trigger="test",
                triggered_by="tester",
                now_utc=now + timedelta(minutes=minute),
                caller=Caller(_principal()),
                demo_desk=True,
            )
            session.commit()
        listing = list_opportunities(
            session, _principal(), now_utc=now + timedelta(minutes=1), limit=50
        )
    engine.dispose()
    return {
        (lane, item["type_code"], item["subject"])
        for lane, page in listing["lanes"].items()
        for item in page["items"]
    }


def test_the_planted_days_are_what_the_tests_say():
    assert MARKET.l1_planted(L1_DAY) and not MARKET.w1_planted(L1_DAY)
    assert MARKET.w1_planted(W1_DAY) and not MARKET.l1_planted(W1_DAY)
    assert not (MARKET.l1_planted(QUIET_DAY) or MARKET.w1_planted(QUIET_DAY))
    assert MARKET.s1_planted(S1_DAY + timedelta(days=1))
    assert not (MARKET.l1_planted(S1_DAY) or MARKET.w1_planted(S1_DAY))
    assert not any(
        MARKET.s1_planted(day + timedelta(days=1)) for day in (L1_DAY, W1_DAY, QUIET_DAY)
    )
    assert all(day.weekday() < 4 for day in (L1_DAY, W1_DAY, QUIET_DAY, S1_DAY, R1_DAY))
    assert MARKET.r1_planted(R1_DAY + timedelta(days=1)) and not MARKET.r1_planted(R1_DAY)
    assert not any(MARKET.r1_planted(day + timedelta(days=offset))
                   for day in (L1_DAY, W1_DAY, QUIET_DAY, S1_DAY) for offset in (0, 1))
    assert not (MARKET.l1_planted(R1_DAY) or MARKET.w1_planted(R1_DAY)
                or MARKET.s1_planted(R1_DAY + timedelta(days=1)))


def test_the_simulated_route_costs_bound_the_demo_market():
    costs = SEED.demo_route_costs()
    assert costs[("TTF", "NBP")] == pytest.approx(MARKET.BBL_ROUTE_COST_EUR_MWH)
    # L1's 1.20 at NBP is reachable only from TTF: every other hub's way to NBP through TTF
    # costs more than its distance below TTF allows.
    for hub in ("THE", "PEG", "ZTP"):
        assert (hub, "NBP") in costs and (hub, "TTF") in costs


@pytest.mark.parametrize(
    ("day", "extra"),
    [
        (L1_DAY, {("market", "L", "TTF → NBP")}),
        (W1_DAY, {("market", "P", "TTF · within-day · day-ahead")}),
        (QUIET_DAY, set()),
        (S1_DAY, {("must_act", "S", "NBP · long"), ("must_act", "S", "TTF · short")}),
        (R1_DAY, set()),
    ],
    ids=["L1", "W1", "quiet", "S1", "R1"],
)
def test_each_planted_case_is_found_on_its_day_and_nothing_else(tmp_path, monkeypatch, day, extra):
    assert _listed(tmp_path, monkeypatch, day) == EVERY_DAY | extra


@pytest.mark.parametrize(("day", "kinds"), [(R1_DAY, ["lesser_rule_cut"]), (QUIET_DAY, [])],
                         ids=["R1", "quiet"])
def test_the_r1_break_is_in_the_reconciliation_on_its_day_only(tmp_path, monkeypatch, day, kinds):
    from eurogas_nexus.application.gas_day_reconciliation import reconciliation

    url = f"sqlite+pysqlite:///{(tmp_path / f'r1-{day}.sqlite').as_posix()}"
    engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    # Late evening: tomorrow's nominations are matched (the TSO answered at 14:00 UTC).
    now = datetime(day.year, day.month, day.day, 21, tzinfo=UTC)
    with Session(engine) as session:
        SEED.seed(session, now, history_days=3)
        session.commit()
        found = [
            item["kind"]
            for gas_day in (day, day + timedelta(days=1))
            for item in reconciliation(session, Caller(_principal()), gas_day, now=now)["breaks"]
        ]
    engine.dispose()
    assert found == kinds


D1_DAY = date(2026, 12, 24)  # Thursday, the D1 day of the month


def test_d1_plants_a_late_cargo_whose_options_the_desk_can_read(tmp_path, monkeypatch):
    from eurogas_nexus.application import lng_disruption

    assert MARKET.d1_planted(D1_DAY)
    assert not any(MARKET.d1_planted(day) for day in (L1_DAY, W1_DAY, QUIET_DAY, S1_DAY, R1_DAY))
    for day, planted in ((D1_DAY, True), (QUIET_DAY, False)):
        url = f"sqlite+pysqlite:///{(tmp_path / f'd1-{day}.sqlite').as_posix()}"
        engine = create_engine(url, future=True)
        Base.metadata.create_all(engine)
        monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
        now = datetime(day.year, day.month, day.day, 9, tzinfo=UTC)
        with Session(engine) as session:
            SEED.seed(session, now, history_days=3)
            session.commit()
            frontier = lng_disruption.frontier(session, SEED.D1_BOOK, now=now) if planted else None
            if planted:
                assert [s["supply_id"] for s in frontier["disrupted"]] == ["demo-lng-a"]
                assert frontier["recommended"] in frontier["frontier"]
                options = lng_disruption.disruption_options(session, "demo-lng-a", now=now)
                assert options["status"] == "disrupted" and options["options"]
                # LNG-4: the Huelva swap is listed and flagged as breaking the firm delivery
                # to the Iberian offtaker; hub gas at PVB covering it is a further option.
                listed = {o["key"].split(":", 1)[1]: o for o in options["options"]}
                iberia = listed["swap:demo-lng-c+absorb"]
                assert iberia["possible"] and iberia["flags"]["contract_breach"]
                assert any(k.startswith("swap:demo-lng-c+absorb + cover:") for k in listed)
                assert [r["basis"] for r in options["recommended_set"]][0] == "clean"
                assert options["demurrage"]["currency"] == "USD"
            else:
                quiet = lng_disruption.reoptimise(session, SEED.D1_BOOK, trigger="test", now=now)
                assert quiet["status"] in {"as_planned", "skipped"}
        engine.dispose()


def test_the_d1_day_lists_nothing_more_than_every_day(tmp_path, monkeypatch):
    assert _listed(tmp_path, monkeypatch, D1_DAY) == EVERY_DAY
