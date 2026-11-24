"""GOV-1 (P5): the governed-write register and the helper that makes audit part of the write."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from eurogas_nexus.application.audit_service import (
    GOVERNED_WRITES,
    GovernedAuditError,
    governed_actions,
    record_governed_audit,
)
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import AssumptionSetRecord, AuditEventRecord, CreditLineRecord
from eurogas_nexus.db.repositories import audit as audit_repository
from eurogas_nexus.db.repositories.commercial_assumptions import create_assumption_set

SRC = Path(__file__).resolve().parents[2] / "src" / "eurogas_nexus"


def _engine(tmp_path):
    engine = create_engine(f"sqlite+pysqlite:///{(tmp_path / 'a.sqlite').as_posix()}", future=True)
    Base.metadata.create_all(engine)
    return engine


def _line(name: str = "C1") -> CreditLineRecord:
    return CreditLineRecord(
        counterparty_id="C1",
        name=name,
        limit_amount=1.0,
        currency="EUR",
        updated_by="risk",
        updated_at_utc=datetime.now(UTC),
    )


def _broken(*_args, **_kwargs):
    raise RuntimeError("audit store refused the row")


def test_every_governed_action_is_recorded_somewhere_in_the_code() -> None:
    """A register entry that no code records is a promise nobody keeps."""

    sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in SRC.rglob("*.py")
        if path.name != "audit_service.py"
    )
    missing = sorted(a for a in governed_actions() if f'"{a}"' not in sources)
    assert missing == []
    assert len(governed_actions()) == sum(len(w.actions) for w in GOVERNED_WRITES)


def test_no_governed_action_is_recorded_through_the_best_effort_helper() -> None:
    """The best-effort helper opens its own session, so it can never be part of a write."""

    offenders = []
    for path in SRC.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "application.audit_service import record_audit_event" not in text:
            continue
        for action in re.findall(r'action="([^"]+)"', text):
            if action in governed_actions():
                offenders.append(f"{path.relative_to(SRC)}: {action}")
    assert offenders == []


def test_the_change_and_its_audit_row_commit_together(tmp_path) -> None:
    engine = _engine(tmp_path)
    with Session(engine) as session:
        session.add(_line())
        row = record_governed_audit(
            session,
            event_type="risk.limits",
            principal="risk",
            action="risk.credit_line.update",
            resource="credit_line:C1",
        )
        session.commit()
        assert session.get(AuditEventRecord, row.event_id) is not None


def test_a_missing_audit_row_refuses_the_change(tmp_path, monkeypatch) -> None:
    engine = _engine(tmp_path)
    monkeypatch.setattr(audit_repository, "record_audit_event", _broken)
    with Session(engine) as session:
        session.add(_line())
        with pytest.raises(GovernedAuditError) as raised:
            record_governed_audit(
                session,
                event_type="risk.limits",
                principal="risk",
                action="risk.credit_line.update",
                resource="credit_line:C1",
            )
        session.rollback()
    assert raised.value.action == "risk.credit_line.update"
    assert raised.value.code == "audit_unavailable"
    assert raised.value.cause_type == "RuntimeError"
    with Session(engine) as session:
        assert session.query(CreditLineRecord).count() == 0


def test_a_fault_in_the_change_itself_is_not_reported_as_an_audit_failure(tmp_path) -> None:
    engine = _engine(tmp_path)
    with Session(engine) as session:
        session.add(_line())
        session.commit()
    with Session(engine) as session:
        session.add(_line("again"))
        with pytest.raises(IntegrityError):
            record_governed_audit(
                session,
                event_type="risk.limits",
                principal="risk",
                action="risk.credit_line.update",
                resource="credit_line:C1",
            )


def test_an_assumption_set_is_not_created_without_its_audit_row(tmp_path, monkeypatch) -> None:
    engine = _engine(tmp_path)
    monkeypatch.setattr(audit_repository, "record_audit_event", _broken)
    with Session(engine) as session:
        with pytest.raises(GovernedAuditError):
            create_assumption_set(
                session, name="Boil-off", book_id=None, description="", actor="risk"
            )
        session.rollback()
    with Session(engine) as session:
        assert session.query(AssumptionSetRecord).count() == 0
