"""QA-R-07: every risk figure says how old its marks are, and one freshness rule decides.

- Credit exposure rows carry ``marks_as_of`` and a ``state`` (current, late, stale, never) by
  the one business-day rule (``domain.monitoring.freshness.close_state``); mandate rows are
  measured in MWh and say so (no marks date, current).
- The position ladder's rows and totals carry the same, from the hubs' daily closes.
- The monitoring scan raises one ``marks_stale`` alert when the marks behind the credit limits
  are older than one business day, and none while they are current.
- Today's ``stale_figures`` and the Data feeds popover judge with the same freshness contract,
  mapped once (late is LATE, stale is STALE).
"""

from __future__ import annotations

import importlib.util
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import eurogas_nexus.db.models  # noqa: F401  (registers every table)
from eurogas_nexus.application.caller import firm_caller
from eurogas_nexus.application.freshness_contract import (
    FRESHNESS_STATES,
    projection_state,
    source_system_state,
)
from eurogas_nexus.application.limits_service import credit_exposure_rows, mandate_usage_rows
from eurogas_nexus.application.monitoring_service import scan_monitoring_conditions
from eurogas_nexus.application.projections.freshness import contract_state_for_rows
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import MonitoringAlertRecord
from eurogas_nexus.domain.monitoring.freshness import close_state, marks_as_of
from eurogas_nexus.domain.portfolio.position_ladder import PositionLeg, ladder_report

SEED = Path(__file__).resolve().parents[2] / "scripts" / "demo" / "seed_demo_desk.py"
NOW = datetime(2026, 11, 7, 9, tzinfo=UTC)  # a Saturday: Friday's close is current


@pytest.fixture
def desk(tmp_path, monkeypatch):
    url = f"sqlite+pysqlite:///{tmp_path / 'desk.sqlite'}"
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    monkeypatch.setenv("EUROGAS_NEXUS_DEMO_MARKS", "true")
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    spec = importlib.util.spec_from_file_location("seed_demo_desk", SEED)
    seed = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(seed)
    with Session(engine) as session:
        seed.seed(session, NOW)
        session.commit()
    return engine


def _limits_alerts(engine, now):
    with Session(engine) as session:
        scan_monitoring_conditions(session, now_utc=now, enrich_with_llm=False)
        return {
            row.fingerprint: row
            for row in session.query(MonitoringAlertRecord)
            .filter(MonitoringAlertRecord.category == "limits")
            .filter(MonitoringAlertRecord.resolved_at_utc.is_(None))
            .all()
        }


# ------------------------------------------------------------------ the business-day rule


def test_the_previous_weekdays_close_is_current_one_behind_late_more_stale():
    monday = date(2026, 11, 23)
    assert close_state(date(2026, 11, 20), monday) == "current"  # Friday, read on Monday
    assert close_state(date(2026, 11, 19), monday) == "late"  # one business day behind
    assert close_state(date(2026, 11, 18), monday) == "stale"
    assert close_state(None, monday) == "never"
    tuesday = date(2026, 11, 24)
    assert close_state(date(2026, 11, 23), tuesday) == "current"
    assert close_state(date(2026, 11, 20), tuesday) == "late"


def test_a_figure_on_several_hubs_is_as_old_as_its_least_current_hub():
    closes = {"TTF": {date(2026, 11, 20): 30.0}, "NBP": {date(2026, 11, 17): 80.0}}
    assert marks_as_of({"ttf", "NBP"}, closes) == date(2026, 11, 17)
    assert marks_as_of({"THE"}, closes) is None


# ------------------------------------------------------------------ the risk rows


def test_credit_rows_carry_their_marks_date_and_state(desk):
    credit = credit_exposure_rows(firm_caller(), NOW.date())
    priced = [row for row in credit.rows if row["legs"]]
    assert priced
    for row in priced:
        assert row["marks_as_of"] is not None
        assert row["state"] == "current" and row["freshness_state"] == "FRESH"
    mandates = mandate_usage_rows(firm_caller(), NOW.date())
    for row in mandates.rows:
        # Measured in MWh from the books: no marks date, as current as the read.
        assert row["marks_as_of"] is None and row["state"] == "current"


def test_six_day_old_marks_say_stale_on_the_rows_and_raise_one_marks_stale_alert(desk):
    assert "marks_stale:credit" not in _limits_alerts(desk, NOW)

    later = NOW + timedelta(days=6)  # QA-R-07: the store is six days old
    credit = credit_exposure_rows(firm_caller(), later.date())
    priced = [row for row in credit.rows if row["legs"]]
    assert {row["state"] for row in priced} == {"stale"}
    assert {row["freshness_state"] for row in priced} == {"STALE"}

    alerts = _limits_alerts(desk, later)
    alert = alerts["marks_stale:credit"]
    assert alert.alert_type == "marks_stale" and alert.severity == "warning"
    evidence = alert.evidence_snapshot
    assert evidence["state"] == "stale"
    assert evidence["marks_as_of"] == min(row["marks_as_of"] for row in priced)
    assert {line["counterparty_id"] for line in evidence["lines"]} == {
        row["counterparty_id"] for row in priced
    }
    # Book-scoped like the credit alerts it qualifies.
    assert evidence["book_ids"]
    assert evidence["marks_as_of"] in alert.title_en


def test_todays_tightest_credit_limit_uses_the_rows_own_marks_state(desk):
    from eurogas_nexus.application.desk_today import _Read, _tightest_limit

    later = NOW + timedelta(days=6)
    item = _tightest_limit(firm_caller(), later, _Read())
    if item is None or item.get("kind") != "credit":
        pytest.skip("the tightest limit in the seed is a mandate")
    credit = credit_exposure_rows(firm_caller(), later.date())
    row = next(r for r in credit.rows if f"limit.credit.{r['counterparty_id']}" == item["key"])
    assert item["state"] == row["state"] == "stale"
    assert item["as_of"] == row["marks_as_of"]


# ------------------------------------------------------------------ the position ladder


def test_ladder_rows_and_totals_carry_the_marks_date_and_state():
    today = date(2026, 11, 24)  # Tuesday: Monday's close is current
    legs = [
        PositionLeg("physical", "TTF", date(2026, 12, 1), date(2026, 12, 31), 100.0, 30.0),
        PositionLeg("physical", "NBP", date(2026, 12, 1), date(2026, 12, 31), -50.0, 80.0),
    ]
    closes = {
        "TTF": {date(2026, 11, 23): 31.0, date(2026, 11, 20): 30.5},
        "NBP": {date(2026, 11, 18): 79.0},
    }
    report = ladder_report(
        legs,
        horizon_start=today,
        horizon_end=date(2027, 1, 31),
        daily_closes_by_hub=closes,
        fx_by_hub={"TTF": 1.0, "NBP": 1.15},
        today=today,
    ).as_dict()
    by_hub = {row["hub"]: row for row in report["rows"]}
    assert by_hub["TTF"]["marks_as_of"] == "2026-11-23" and by_hub["TTF"]["state"] == "current"
    assert by_hub["NBP"]["marks_as_of"] == "2026-11-18" and by_hub["NBP"]["state"] == "stale"
    # The mark-to-market and VaR are as old as the least current hub held.
    assert report["marks_as_of"] == "2026-11-18" and report["marks_state"] == "stale"


def test_without_closes_the_ladder_rows_are_unchanged():
    legs = [PositionLeg("physical", "TTF", date(2026, 12, 1), date(2026, 12, 31), 100.0, 30.0)]
    report = ladder_report(
        legs, horizon_start=date(2026, 11, 24), horizon_end=date(2027, 1, 31)
    ).as_dict()
    assert "state" not in report["rows"][0] and "marks_state" not in report


# ------------------------------------------------------------------ one rule for both screens


def test_the_popover_and_today_map_one_contract_state_to_one_word():
    # A state Today names as not current (late or stale) is never FRESH in the popover, and a
    # current figure is never degraded there.
    for state in FRESHNESS_STATES:
        named_on_today = state in {"late", "stale"}
        degraded_in_popover = projection_state(state) in {"LATE", "STALE"}
        assert named_on_today == degraded_in_popover, state


def test_feeds_are_judged_by_the_sources_declared_policy():
    now = datetime(2026, 11, 24, 12, tzinfo=UTC)
    # EEX_Sim: 1 minute normal, 3 days to stale (its FreshnessPolicy).
    assert source_system_state("EEX_Sim", now - timedelta(seconds=30), now) == "current"
    assert source_system_state("EEX_Sim", now - timedelta(minutes=10), now) == "late"
    assert source_system_state("EEX_Sim", now - timedelta(days=4), now) == "stale"
    assert source_system_state("EEX_Sim", None, now) == "never"
    assert source_system_state("NOT_A_SOURCE", now, now) is None

    rows = [
        {"source_system": "EEX_Sim", "observed_at_utc": (now - timedelta(minutes=10)).isoformat()},
        {"source_system": "ENTSOG", "observed_at_utc": (now - timedelta(minutes=10)).isoformat()},
    ]
    keys = ("observed_at_utc",)
    # A slice is as current as its least current source.
    assert contract_state_for_rows(rows, keys, now) == "LATE"
    assert contract_state_for_rows(rows[1:], keys, now) == "FRESH"
    old = [{**rows[0], "observed_at_utc": (now - timedelta(days=4)).isoformat()}]
    assert contract_state_for_rows(old, keys, now) == "STALE"
    assert contract_state_for_rows([{"observed_at_utc": now.isoformat()}], keys, now) is None
