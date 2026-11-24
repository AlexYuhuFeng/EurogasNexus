"""M7 (c): ``/api/stream/opportunities`` serves the opportunity engine: an opportunity opens and
is withdrawn on the stream (including at the end of its validity), and finished evaluations move
the page's "as of".
"""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import eurogas_nexus.db.session as db_session
from eurogas_nexus.api.routes.public import streaming
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import OpportunityEvaluationRecord, OpportunityRecord

NOW = datetime.now(UTC).replace(microsecond=0)


@pytest.fixture()
def engine():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return engine


def _record(opportunity_id: str, *, state="actionable", surfaced=True, changed=NOW, expires=None):
    return OpportunityRecord(
        opportunity_id=opportunity_id,
        opp_key=f"key-{opportunity_id}",
        type="prompt_arbitrage",
        lane="market",
        state=state,
        assessed_state=state,
        version=1,
        claim_key="prompt.da_wd",
        claim_fields={"hub": "TTF"},
        claim_text="Within-day above day-ahead",
        headline_value=Decimal("0.4"),
        headline_unit="EUR/MWh",
        period_label="WD",
        period_start=date(2026, 11, 24),
        period_end=date(2026, 11, 24),
        quality_class="sourced",
        simulated=False,
        book_ids=[],
        source_families=[],
        reasons=[],
        first_seen_utc=changed,
        last_evaluated_utc=changed,
        last_changed_utc=changed,
        consecutive_seen=2,
        consecutive_missed=0,
        surfaced=surfaced,
        expires_at_utc=expires or NOW + timedelta(hours=2),
        snapshot_id="snap",
        evaluation_id="oeval-1",
        evaluator="prompt_arbitrage",
        evaluator_version="1",
    )


def test_a_change_after_the_cursor_is_an_open_or_a_withdrawal(engine) -> None:
    before = NOW - timedelta(minutes=1)
    with Session(engine) as session:
        session.add(_record("o-open", changed=NOW))
        session.add(_record("o-gone", state="expired", changed=NOW + timedelta(seconds=1)))
        session.add(_record("o-new", state="new", surfaced=False, changed=NOW))
        session.add(_record("o-old", changed=before - timedelta(minutes=5)))
        session.commit()
        changes = streaming._fetch_new_opportunities(session, (before, ""))
    by_id = {change["opportunity_id"]: change for change in changes}
    assert list(by_id) == ["o-new", "o-open", "o-gone"]
    assert by_id["o-open"]["status"] == "open" and by_id["o-open"]["reason"] is None
    assert by_id["o-gone"]["status"] == "withdrawn" and by_id["o-gone"]["reason"] == "expired"
    assert by_id["o-new"]["sent"] is False  # moves the cursor, never shown
    assert "headline_value" not in by_id["o-open"]  # a notice carries no figure


def test_an_opportunity_is_withdrawn_on_the_stream_when_its_validity_ends(engine) -> None:
    with Session(engine) as session:
        session.add(_record("o-lapsed", expires=NOW - timedelta(seconds=5)))
        session.add(_record("o-live", expires=NOW + timedelta(hours=1)))
        session.add(_record("o-long-gone", expires=NOW - timedelta(hours=1)))
        session.commit()
        notices = streaming._fetch_opportunity_expiries(
            session, (NOW - timedelta(seconds=30), ""), None
        )
    shown = [notice for notice in notices if notice["visible"]]
    assert [notice["detail"]["opportunity_id"] for notice in shown] == ["o-lapsed"]
    assert shown[0]["detail"]["status"] == "withdrawn"
    assert shown[0]["detail"]["reason"] == "expired"
    # Time moves the cursor even when nothing expired.
    assert notices[-1]["visible"] is False and notices[-1]["cursor"] >= NOW


def test_a_finished_evaluation_moves_the_pages_as_of(engine) -> None:
    with Session(engine) as session:
        session.add(
            OpportunityEvaluationRecord(
                evaluation_id="oeval-9",
                trigger="outbox",
                triggered_by="market-event-outbox",
                as_of_utc=NOW,
                started_at_utc=NOW,
                finished_at_utc=NOW + timedelta(milliseconds=200),
                status="ok",
                demo_desk=False,
                evaluators_json={},
                counts_json={},
            )
        )
        session.commit()
        (notice,) = streaming._fetch_evaluations(session, (NOW - timedelta(seconds=1), ""), None)
        assert streaming._fetch_evaluations(session, (notice["cursor"], ""), None) == []
    assert notice["detail"] == {"evaluation_id": "oeval-9", "trigger": "outbox", "as_of_utc": NOW}


def test_the_stream_sends_opens_withdrawals_and_evaluations(engine, monkeypatch) -> None:
    soon = datetime.now(UTC) + timedelta(milliseconds=400)
    with Session(engine) as session:
        session.add(_record("o-open", changed=NOW))
        session.add(_record("o-lapsing", expires=soon, changed=NOW + timedelta(seconds=1)))
        session.commit()
    monkeypatch.setattr(db_session, "get_session_factory", lambda: (lambda: Session(engine)))
    monkeypatch.setattr(streaming, "POLL_SECONDS", 0.2)

    async def drive() -> list[str]:
        generator = streaming._event_stream(
            "opportunity",
            streaming._fetch_new_opportunities,
            "changed_at_utc",
            "opportunity_id",
            (NOW - timedelta(seconds=10), ""),
            notices=(
                ("opportunity", streaming._fetch_opportunity_expiries),
                ("evaluated", streaming._fetch_evaluations),
            ),
        )
        frames: list[str] = []
        while len(frames) < 3:
            frame = await asyncio.wait_for(generator.__anext__(), timeout=5)
            if not frame.startswith(":"):
                frames.append(frame)
        await generator.aclose()
        return frames

    frames = asyncio.run(drive())
    # Both open on the first poll, each with a resume id; the withdrawal at the end of the
    # validity window follows as a notice without one.
    assert all(frame.startswith("id: ") and '"status": "open"' in frame for frame in frames[:2])
    assert frames[2].startswith("event: opportunity\n")
    assert '"group": "expiry"' in frames[2] and '"status": "withdrawn"' in frames[2]
    assert '"opportunity_id": "o-lapsing"' in frames[2]
