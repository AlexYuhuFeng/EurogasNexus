"""Reconciling source states reads the state table once (backend audit P2)."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

import eurogas_nexus.db.models  # noqa: F401
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.repositories.dataops import reconcile_source_runtime_states
from eurogas_nexus.domain.dataops.registry import source_definitions

NOW = datetime(2026, 11, 26, 9, tzinfo=UTC)


def test_reconciling_existing_states_reads_them_in_one_query() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        reconcile_source_runtime_states(db, source_definitions(), now_utc=NOW)
        db.commit()
    reads: list[str] = []

    def count(_conn, _cursor, statement, *_args) -> None:
        if statement.lstrip().upper().startswith("SELECT") and "source_runtime_states" in statement:
            reads.append(statement)

    event.listen(engine, "before_cursor_execute", count)
    with Session(engine) as db:
        reconcile_source_runtime_states(db, source_definitions(), now_utc=NOW)
    assert len(source_definitions()) > 10
    assert len(reads) == 1
