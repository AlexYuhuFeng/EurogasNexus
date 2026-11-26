"""The spread lab reads only its legs' tenors, and a tenor stated in another case still counts."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import eurogas_nexus.db.models  # noqa: F401
from eurogas_nexus.application import spread_history
from eurogas_nexus.application.caller import Caller
from eurogas_nexus.application.projections import daily_closes
from eurogas_nexus.application.spread_history import SpreadAnalysisInput
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import MarketObservationRecord
from eurogas_nexus.security.identity import AuthenticatedPrincipal


def _principal() -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        principal_id="trader", name="trader", principal_type="USER", role="ANALYST",
        status="ACTIVE", data_scopes=("*",), roles=("ANALYST",),
    )


def test_the_analysis_asks_only_for_its_legs_tenors(monkeypatch):
    asked: list[tuple[str, ...] | None] = []

    def fake(request, date_from=None, date_to=None, *, tenors=None):
        asked.append(tenors)
        return []

    monkeypatch.setattr(daily_closes, "daily_rows", fake)
    body = SpreadAnalysisInput(legs=[
        {"hub": "TTF", "tenor": "Day-Ahead", "weight": 1},
        {"hub": "NBP", "tenor": "day-ahead", "weight": -1},
    ])
    try:
        spread_history.spread_history(body, object())
    except spread_history.SpreadHistoryError:
        pass  # no rows: refused as a missing series, after the read
    assert asked == [("day-ahead",)]


def test_a_tenor_filter_ignores_case(tmp_path, monkeypatch):
    url = f"sqlite+pysqlite:///{(tmp_path / 'closes.sqlite').as_posix()}"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    observed = datetime(2026, 11, 17, 16, tzinfo=UTC)
    with Session(engine) as session:
        for oid, metadata in (("upper", {"hub": "TTF", "tenor": "Day-Ahead"}),
                              ("other", {"hub": "TTF", "tenor": "q+1"})):
            session.add(MarketObservationRecord(
                observation_id=oid, market_venue="X", product="TTF", price=30.0,
                unit="EUR/MWh", currency="EUR", period_start_utc=observed,
                period_end_utc=observed + timedelta(days=1), observed_at_utc=observed,
                source_system="TEST", source_reference="t", freshness="daily",
                quality_score=1.0, research_only=True, metadata_json=metadata,
            ))
        session.commit()
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    rows = daily_closes.daily_rows(Caller(_principal()), tenors=("day-ahead",))
    assert [row["tenor"] for row in rows] == ["day-ahead"]
