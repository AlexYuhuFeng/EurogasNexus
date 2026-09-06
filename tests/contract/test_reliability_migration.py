"""CR-11 reliability migration/index contracts."""

from __future__ import annotations

from pathlib import Path

from eurogas_nexus.db.models import (
    AuditEventRecord,
    StrategyRunRecord,
    UserSessionRecord,
)

ROOT = Path(__file__).resolve().parents[2]


def test_reliability_migration_chains_to_enterprise_identity() -> None:
    text = (
        ROOT / "alembic" / "versions" / "0030_reliability_indexes.py"
    ).read_text(encoding="utf-8")

    assert 'revision: str = "0030_reliability_indexes"' in text
    assert 'down_revision: str | None = "0029_enterprise_identity_v1"' in text
    for token in (
        '"ix_strategy_runs_strategy_started"',
        '"ix_strategy_runs_version_started"',
        '"ix_strategy_runs_type_started"',
        '"uq_user_sessions_token"',
        '"ix_audit_events_actor_action"',
    ):
        assert token in text


def test_evidence_indexes_are_declared_on_models() -> None:
    strategy_indexes = {index.name for index in StrategyRunRecord.__table__.indexes}
    assert {
        "ix_strategy_runs_strategy_started",
        "ix_strategy_runs_version_started",
        "ix_strategy_runs_type_started",
    }.issubset(strategy_indexes)

    session_indexes = {index.name for index in UserSessionRecord.__table__.indexes}
    assert "uq_user_sessions_token" in session_indexes

    audit_indexes = {index.name for index in AuditEventRecord.__table__.indexes}
    assert "ix_audit_events_actor_action" in audit_indexes
