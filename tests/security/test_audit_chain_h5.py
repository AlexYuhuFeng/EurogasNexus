"""The audit trail is a verifiable hash chain; pruning keeps it verifiable, under dual control,
above the configured retention, and is itself audited (security review H5)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.application.audit_retention import (
    AuditPruneRefused,
    prune_expired_audit_events,
)
from eurogas_nexus.db import audit_chain
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import AuditChainRecord, AuditEventRecord
from eurogas_nexus.db.repositories.audit import record_audit_event


def _engine(tmp_path):
    engine = create_engine(f"sqlite+pysqlite:///{(tmp_path / 'chain.sqlite').as_posix()}")
    Base.metadata.create_all(engine)
    return engine


def _write(session, n: int, *, days_ago: int = 0) -> None:
    for index in range(n):
        record_audit_event(
            session, event_type="test", principal="alice", action="test.act",
            resource=f"thing:{index}", detail=f"n={index}",
            now_utc=datetime.now(UTC) - timedelta(days=days_ago, seconds=n - index),
        )


def test_committed_rows_are_sealed_and_verify(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as session:
        _write(session, 3)
        session.commit()
        _write(session, 2)
        session.commit()
        assert session.query(AuditChainRecord).count() == 5
        result = audit_chain.verify_chain(session)
    assert result["ok"] and result["rows_verified"] == 5 and result["unsealed_rows"] == 0


def test_an_edited_or_removed_row_breaks_the_chain(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as session:
        _write(session, 4)
        session.commit()
        row = session.query(AuditEventRecord).order_by(AuditEventRecord.event_ts_utc).all()[1]
        row.detail = "rewritten"
        session.flush()
        broken = audit_chain.verify_chain(session)
        assert not broken["ok"] and "content" in broken["first_break"]["reason"]
        session.rollback()
        link = session.query(AuditChainRecord).filter_by(chain_seq=2).one()
        session.delete(link)
        session.flush()
        gap = audit_chain.verify_chain(session)
        assert not gap["ok"] and "gap" in gap["first_break"]["reason"]


def test_a_checkpoint_is_signed_when_a_key_is_set(tmp_path, monkeypatch):
    monkeypatch.setenv("EUROGAS_NEXUS_SECRET_KEY", "k" * 43 + "=")
    engine = _engine(tmp_path)
    with Session(engine) as session:
        _write(session, 2)
        session.commit()
        result = audit_chain.checkpoint(session, by="test")
    assert result["anchor"]["chain_seq"] == 2
    assert result["anchor"]["signature"].startswith("hmac-sha256:")


def test_pruning_refuses_below_retention_and_without_approval(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as session:
        with pytest.raises(AuditPruneRefused, match="configured retention"):
            prune_expired_audit_events(session, retention_days=30)
        with pytest.raises(AuditPruneRefused, match="second administrator"):
            prune_expired_audit_events(session, dry_run=False)


def test_an_approved_prune_keeps_the_rest_verifiable_and_is_audited(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as session:
        _write(session, 3, days_ago=2000)
        session.commit()
        _write(session, 2)
        session.commit()
        summary = prune_expired_audit_events(
            session, dry_run=False, approved_change_id="pc-test", by="admin-b"
        )
        session.commit()
        assert summary["audit_events_deleted"] == 3
        result = audit_chain.verify_chain(session)
        assert result["ok"], result
        assert result["anchored_from_seq"] == 3
        actions = [row.action for row in session.query(AuditEventRecord)]
        assert "audit.retention.prune" in actions


def test_sealed_rows_are_forwarded_as_json_lines(tmp_path, monkeypatch):
    sink = tmp_path / "siem.jsonl"
    monkeypatch.setenv(audit_chain.AUDIT_SINK_ENV, f"file:{sink}")
    engine = _engine(tmp_path)
    with Session(engine) as session:
        _write(session, 2)
        session.commit()
    lines = [json.loads(line) for line in sink.read_text().splitlines()]
    assert [line["chain_seq"] for line in lines] == [1, 2]
    assert lines[0]["type"] == "eurogas_nexus.audit" and lines[0]["row_hash"]


def test_the_restricted_role_sql_takes_update_and_delete_away():
    from pathlib import Path

    sql = (Path(__file__).resolve().parents[2] / "deploy/runtime/database_roles.sql").read_text()
    assert "REVOKE UPDATE, DELETE, TRUNCATE ON audit_events, audit_chain" in sql
