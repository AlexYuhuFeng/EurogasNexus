"""The per-owner background-job limit holds when two requests arrive together (PostgreSQL).

PR 61 review: the limit was a count followed by an insert, so two simultaneous requests could
both count the same active jobs and both create one. ``submit_background_job`` now takes a
transaction-scoped advisory lock per owner first: the second request waits for the first to
commit, then counts its job. Runs when ``EUROGAS_NEXUS_TEST_POSTGRES_URL`` is set (the
PostgreSQL CI job); the rows it writes carry a unique owner and are removed afterwards.
"""

from __future__ import annotations

import os
import threading
import time
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, delete
from sqlalchemy.orm import sessionmaker

from eurogas_nexus.application import background_jobs as bg
from eurogas_nexus.db.models import JobRecord
from eurogas_nexus.db.repositories.identity import create_identity_principal

_POSTGRES_URL = os.environ.get("EUROGAS_NEXUS_TEST_POSTGRES_URL", "")

pytestmark = pytest.mark.skipif(
    not _POSTGRES_URL.startswith("postgresql"),
    reason="needs EUROGAS_NEXUS_TEST_POSTGRES_URL (the PostgreSQL CI job)",
)


def _submit(session, owner: str) -> dict:
    return bg.submit_background_job(
        session,
        kind="DATASET_BUILD",
        principal="race-test",
        owner_principal_id=owner,
        steps_total=1,
    )


def test_two_requests_at_once_cannot_pass_the_per_owner_limit() -> None:
    engine = create_engine(_POSTGRES_URL, future=True)
    JobRecord.__table__.create(engine, checkfirst=True)
    factory = sessionmaker(engine, future=True)
    with factory() as session:
        owner = create_identity_principal(
            session,
            name=f"race.owner.{uuid4().hex[:10]}",
            display_name="Race owner",
            role="ANALYST",
        ).principal_id
        session.commit()
    try:
        # One below the limit, committed.
        for _ in range(bg.MAX_ACTIVE_JOBS_PER_OWNER - 1):
            with factory() as session:
                _submit(session, owner)
                session.commit()

        first = factory()
        _submit(first, owner)  # holds the owner's lock until it commits

        outcome: dict[str, object] = {}

        def second_request() -> None:
            with factory() as session:
                try:
                    _submit(session, owner)
                    session.commit()
                    outcome["result"] = "created"
                except bg.JobQueueFull:
                    session.rollback()
                    outcome["result"] = "refused"

        thread = threading.Thread(target=second_request)
        thread.start()
        time.sleep(0.5)
        # The second request waits for the first instead of counting beside it.
        assert thread.is_alive()
        first.commit()
        first.close()
        thread.join(timeout=10)
        assert not thread.is_alive()
        assert outcome["result"] == "refused"

        with factory() as session:
            active = (
                session.query(JobRecord)
                .filter(JobRecord.owner_principal_id == owner)
                .count()
            )
        assert active == bg.MAX_ACTIVE_JOBS_PER_OWNER
    finally:
        with factory() as session:
            session.execute(delete(JobRecord).where(JobRecord.owner_principal_id == owner))
            session.commit()
        engine.dispose()
