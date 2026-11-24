"""CP-13 scheduled evaluation (M5 fix): a change noted while the evaluation runs stays pending.

``run_due`` used to delete the pending rows it had read, so a change noted between the read
and the delete was lost until the next change in its class. It now deletes by condition in
the store (``last_noted_at_utc <= now``).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from eurogas_nexus.application.opportunities import schedule
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import OpportunityPendingInputRecord

NOW = datetime(2026, 11, 17, 9, 42, tzinfo=UTC)


@pytest.fixture()
def engine(tmp_path, monkeypatch):
    url = f"sqlite+pysqlite:///{(tmp_path / 'schedule.sqlite').as_posix()}"
    engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    return engine



def test_a_change_noted_while_the_scheduled_evaluation_runs_stays_pending(engine) -> None:
    factory = sessionmaker(engine)
    with factory() as session:
        schedule.note_input_changed(session, "prices", reason="before", at_utc=NOW)
        session.commit()

    def runner(session, **_kwargs):
        # Another writer notes a new price change while the evaluation runs.
        with factory() as other:
            schedule.note_input_changed(
                other, "prices", reason="during", at_utc=NOW + timedelta(minutes=10)
            )
            other.commit()
        return {"status": "ok"}

    with factory() as session:
        outcome = schedule.run_due(session, now_utc=NOW + timedelta(minutes=6), runner=runner)
        session.commit()
    assert outcome["status"] == "ran"
    with factory() as session:
        pending = session.get(OpportunityPendingInputRecord, "prices")
        assert pending is not None and pending.last_reason == "during"
