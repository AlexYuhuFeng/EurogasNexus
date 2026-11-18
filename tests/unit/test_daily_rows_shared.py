"""Identical daily-close reads inside one composed read (Today) are answered once."""

from __future__ import annotations

from datetime import date

from eurogas_nexus.application.projections import daily_closes
from eurogas_nexus.security.identity import AuthenticatedPrincipal


def _principal(pid: str) -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        principal_id=pid, name=pid, principal_type="USER", role="ANALYST", status="ACTIVE",
        data_scopes=("*",), roles=("ANALYST",),
    )


def test_identical_reads_are_shared_only_inside_the_block(monkeypatch):
    from eurogas_nexus.application.caller import Caller

    calls = []

    def fake(who, date_from=None, date_to=None, tenors=None):
        calls.append((date_from, date_to))
        return [{"hub": "NBP", "day": date_to}]

    monkeypatch.setattr(daily_closes, "_daily_rows", fake)
    trader = Caller(_principal("trader"))
    window = (date(2025, 10, 1), date(2026, 11, 18))
    with daily_closes.shared_daily_rows():
        first = daily_closes.daily_rows(trader, *window)
        second = daily_closes.daily_rows(trader, *window)
        daily_closes.daily_rows(trader, date(2026, 11, 8), date(2026, 11, 18))
        daily_closes.daily_rows(Caller(_principal("risk")), *window)
    assert first == second and first is not second
    assert len(calls) == 3  # one per distinct (caller, window)
    daily_closes.daily_rows(trader, *window)
    assert len(calls) == 4  # outside the block nothing is kept


def test_a_tenor_filter_reads_only_those_tenors_and_rows_that_state_none(tmp_path, monkeypatch):
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    import eurogas_nexus.db.models  # noqa: F401
    from eurogas_nexus.application.caller import Caller
    from eurogas_nexus.db.base import Base
    from eurogas_nexus.db.models import MarketObservationRecord

    url = f"sqlite+pysqlite:///{(tmp_path / 'closes.sqlite').as_posix()}"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    observed = datetime(2026, 11, 17, 16, tzinfo=UTC)
    with Session(engine) as session:
        for oid, product, metadata in (
            ("ma", "TTF month-ahead", {"hub": "TTF", "tenor": "month-ahead"}),
            ("q1", "TTF Q+1", {"hub": "TTF", "tenor": "q+1"}),
            ("plain", "TTF Day Ahead", None),
        ):
            session.add(MarketObservationRecord(
                observation_id=oid, market_venue="X", product=product, price=30.0,
                unit="EUR/MWh", currency="EUR", period_start_utc=observed,
                period_end_utc=observed + timedelta(days=1), observed_at_utc=observed,
                source_system="TEST", source_reference="t", freshness="daily",
                quality_score=1.0, research_only=True, metadata_json=metadata,
            ))
        session.commit()
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    caller = Caller(_principal("trader"))
    day = observed.date()
    every = daily_closes.daily_rows(caller, day, day)
    narrowed = daily_closes.daily_rows(caller, day, day, tenors=("month-ahead", "day-ahead"))
    assert len(every) == 3
    assert {row["tenor"] for row in narrowed} == {"month-ahead", "ttf day ahead"}
