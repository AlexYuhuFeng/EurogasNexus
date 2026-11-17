"""Keyed scheduled sources: no key, no fetch; a stored key switches the source on once."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import eurogas_nexus.db.models  # noqa: F401
from eurogas_nexus.application import scheduled_source_keys as keys
from eurogas_nexus.application.dataops_runtime import set_source_enabled
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import SourceRuntimeStateRecord
from eurogas_nexus.db.repositories.dataops import reconcile_source_runtime_states
from eurogas_nexus.domain.dataops.contracts import FailureCategory
from eurogas_nexus.domain.dataops.registry import source_definitions
from scripts.ops.run_dataops_scheduler import run_ingestor_attempt

NOW = datetime(2026, 11, 17, 9, tzinfo=UTC)


@pytest.fixture
def session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        reconcile_source_runtime_states(db, source_definitions(), now_utc=NOW)
        db.commit()
        yield db


def test_a_keyed_source_without_its_key_starts_nothing_and_says_why():
    started = []
    attempt = run_ingestor_attempt(
        lambda *args, **kwargs: started.append(args),
        key_check=lambda source_id: False if source_id == "src-eia" else None,
    )
    result = attempt({"source_id": "src-eia", "run_id": "r1"}, 1)
    assert started == []
    assert result.succeeded is False
    assert result.classification is FailureCategory.CONFIGURATION
    assert result.error_message.startswith("CONFIGURATION credential_missing")


def test_storing_a_key_switches_an_off_by_default_source_on_once(session, monkeypatch):
    monkeypatch.setattr(
        keys, "key_configured", lambda source_id, **kwargs: source_id == "src-entsoe"
    )
    assert session.get(SourceRuntimeStateRecord, "src-entsoe").enabled is False
    assert keys.activate_keyed_sources(session, now_utc=NOW) == ["src-entsoe"]
    state = session.get(SourceRuntimeStateRecord, "src-entsoe")
    assert state.enabled is True and state.next_run_at_utc is not None
    assert keys.activate_keyed_sources(session, now_utc=NOW) == []  # already on


def test_an_operator_switch_off_always_stands(session, monkeypatch):
    monkeypatch.setattr(keys, "key_configured", lambda source_id, **kwargs: True)
    set_source_enabled(session, source_id="src-gie", enabled=False, now_utc=NOW)
    activated = keys.activate_keyed_sources(session, now_utc=NOW)
    assert "src-gie" not in activated
    assert session.get(SourceRuntimeStateRecord, "src-gie").enabled is False


def test_key_configured_is_none_for_a_source_that_needs_no_key():
    assert keys.key_configured("src-ecb") is None
    assert keys.key_configured("src-elexon") is None
