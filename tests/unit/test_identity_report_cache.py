"""The cached identity report follows the data it reads; nothing stale after a write."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import eurogas_nexus.db.models  # noqa: F401
from eurogas_nexus.application import identity_resolution as identity
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import FlowObservationRecord
from eurogas_nexus.db.schema_cache import has_table, table_columns


def _flow(n: int, point: str) -> FlowObservationRecord:
    moment = datetime(2026, 11, 16, 5, tzinfo=UTC)
    return FlowObservationRecord(
        observation_id=f"f{n}", point_id=point, point_name=point, direction="entry",
        flow_mcm_d=1.0, period_start_utc=moment, period_end_utc=moment,
        observed_at_utc=moment, source_system="ENTSOG", source_reference="t",
        freshness="daily", research_only=True, metadata_json={"operatorKey": "OP-X"},
    )


def test_a_new_ingest_is_seen_at_once_and_an_unchanged_store_is_served_from_cache(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    identity.invalidate_identity_report()
    calls = []
    real = identity.identity_report
    monkeypatch.setattr(identity, "identity_report", lambda s: calls.append(1) or real(s))
    with Session(engine) as session:
        session.add(_flow(1, "ITP-1"))
        session.commit()
        first = identity.cached_identity_report(session, now=0.0)
        again = identity.cached_identity_report(session, now=1.0)
        assert again == first and len(calls) == 1
        session.add(_flow(2, "ITP-2"))  # an ingest adds a point: the next read sees it
        session.commit()
        identity.cached_identity_report(session, now=2.0)
        assert len(calls) == 2
        identity.cached_identity_report(session, now=2.0 + identity.IDENTITY_REPORT_TTL_SECONDS)
        assert len(calls) == 3  # the TTL backstop
        identity.record_identities(session, [])  # a mapping write in this process
        identity.cached_identity_report(session, now=3.0 + identity.IDENTITY_REPORT_TTL_SECONDS)
        assert len(calls) == 4


def test_schema_cache_remembers_found_tables_per_engine_only():
    one = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(one)
    empty = create_engine("sqlite+pysqlite:///:memory:")
    with Session(one) as session:
        assert "point_id" in table_columns(session, "flow_observations")
    with Session(empty) as session:
        assert has_table(session, "flow_observations") is False  # another engine, same URL
        assert has_table(session, "no_such_table") is False
