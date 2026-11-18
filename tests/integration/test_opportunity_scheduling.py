"""Scheduled opportunity evaluation (CP-13): triggers, debounce, on-write, failure alert.

Acceptance (design K.1 row 13): a price import leads to a re-evaluation within the debounce;
a failing evaluator raises an administrator alert only.
"""

from __future__ import annotations

import importlib.util
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from eurogas_nexus.api.app import create_app
from eurogas_nexus.application.opportunities import schedule
from eurogas_nexus.application.opportunities.service import run_evaluation
from eurogas_nexus.core.config import Settings
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import (
    IngestionRunRecord,
    OpportunityEvaluationRecord,
    OpportunityPendingInputRecord,
    OpportunityRecord,
)
from eurogas_nexus.db.repositories import identity as identity_repository
from eurogas_nexus.domain.opportunities.hedge_gap import HEDGE_GAP
from eurogas_nexus.security import rate_limit as rate_limit_module

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 11, 17, 9, 42, tzinfo=UTC)
PUBLIC_TOKEN = "test-public-api-token"


@pytest.fixture()
def engine(tmp_path, monkeypatch):
    url = f"sqlite+pysqlite:///{(tmp_path / 'sched.sqlite').as_posix()}"
    engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    monkeypatch.setenv("EUROGAS_NEXUS_PUBLIC_API_TOKEN", PUBLIC_TOKEN)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    rate_limit_module._WINDOWS.clear()
    return engine


def _seed_demo(session) -> None:
    spec = importlib.util.spec_from_file_location(
        "seed_demo_desk_sched", ROOT / "scripts" / "demo" / "seed_demo_desk.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.seed(session, NOW, history_days=5)
    session.commit()


def _run(session, run_id: str, source_id: str, *, inserted: int, status="SUCCEEDED") -> dict:
    session.add(
        IngestionRunRecord(
            run_id=run_id,
            source_name=source_id,
            source_id=source_id,
            status=status,
            started_at_utc=NOW,
            rows_inserted=inserted,
        )
    )
    session.flush()
    return {"run_id": run_id, "source_id": source_id, "status": status}


def _scheduled(session) -> list[OpportunityEvaluationRecord]:
    return (
        session.query(OpportunityEvaluationRecord)
        .filter(OpportunityEvaluationRecord.trigger == "schedule")
        .order_by(OpportunityEvaluationRecord.as_of_utc)
        .all()
    )


def _runner(**fixed):
    def run(session, **kw):
        return run_evaluation(session, demo_desk=True, **{**kw, **fixed})

    return run


def test_a_price_import_leads_to_one_evaluation_within_the_debounce(engine) -> None:
    with Session(engine) as session:
        _seed_demo(session)
        assert schedule.run_due(session, now_utc=NOW) == {"status": "idle"}
        # A run that wrote nothing, a failed run and a weather run make nothing due.
        outcomes = [
            _run(session, "r0", "src-eex", inserted=0),
            _run(session, "r1", "src-eex", inserted=5, status="FAILED"),
            _run(session, "r2", "src-weather", inserted=9),
        ]
        assert schedule.note_ingestion_changes(session, outcomes, now_utc=NOW) == []
        noted = schedule.note_ingestion_changes(
            session,
            [
                _run(session, "r3", "src-eex", inserted=12),
                _run(session, "r4", "src-remit-umm", inserted=1),
            ],
            now_utc=NOW,
        )
        assert noted == ["outages", "prices"]
        first = schedule.run_due(session, now_utc=NOW, runner=_runner())
        session.commit()
        assert first["status"] == "ran" and first["classes"] == ["outages", "prices"]
        assert first["evaluation"]["trigger"] == "schedule"
        assert session.query(OpportunityPendingInputRecord).count() == 0
        assert session.query(OpportunityRecord).count() > 0  # the demo book's hedge gaps

        # Another import two minutes later waits for the debounce, then runs once.
        later = NOW + timedelta(minutes=2)
        schedule.note_ingestion_changes(
            session, [_run(session, "r5", "src-ecb", inserted=1)], now_utc=later
        )
        held = schedule.run_due(session, now_utc=later, runner=_runner())
        assert held["status"] == "debounced" and held["classes"] == ["fx"]
        assert held["next_at_utc"] == (NOW + schedule.DEBOUNCE).isoformat()
        after = schedule.run_due(session, now_utc=NOW + schedule.DEBOUNCE, runner=_runner())
        session.commit()
        assert after["status"] == "ran" and after["classes"] == ["fx"]
        assert len(_scheduled(session)) == 2
        assert schedule.run_due(session, now_utc=NOW + timedelta(minutes=20)) == {"status": "idle"}


def test_a_change_during_the_run_stays_pending(engine) -> None:
    with Session(engine) as session:
        schedule.note_input_changed(session, "marks", reason="firm marks", at_utc=NOW)

        def runner(session, **kw):
            # A write lands while the evaluation runs.
            schedule.note_input_changed(
                session, "limits", reason="mandate", at_utc=NOW + timedelta(seconds=30)
            )
            return {"evaluation_id": "x", "status": "ok"}

        result = schedule.run_due(session, now_utc=NOW, runner=runner)
        assert result["classes"] == ["marks"]
        assert [r.input_class for r in session.query(OpportunityPendingInputRecord)] == ["limits"]
        with pytest.raises(ValueError):
            schedule.note_input_changed(session, "weather", reason="x")


def test_a_failing_evaluator_raises_an_admin_alert_only(engine) -> None:
    from eurogas_nexus.application.monitoring_service import _opportunity_evaluator_candidates

    class Broken:
        name = "hedge_gap"
        version = "x"
        type = HEDGE_GAP.type

        def evaluate(self, snapshot, context):
            raise RuntimeError("defect")

    with Session(engine) as session:
        _seed_demo(session)
        schedule.note_input_changed(session, "prices", reason="ingestion src-eex", at_utc=NOW)
        result = schedule.run_due(session, now_utc=NOW, runner=_runner(evaluators=[Broken()]))
        session.commit()
        assert result["status"] == "ran" and result["evaluation"]["status"] == "failed"
        assert session.query(OpportunityRecord).count() == 0  # nothing reaches the desk
        alerts = _opportunity_evaluator_candidates(session)
        assert [a.fingerprint for a in alerts] == ["opportunity_evaluator:hedge_gap"]


def test_the_scheduler_tick_never_fails_the_ingestion_loop(engine, monkeypatch) -> None:
    spec = importlib.util.spec_from_file_location(
        "run_dataops_scheduler_cp13", ROOT / "scripts" / "ops" / "run_dataops_scheduler.py"
    )
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    factory = sessionmaker(engine)
    with factory() as session:
        outcome = _run(session, "s1", "src-eex", inserted=3)
        session.commit()
    monkeypatch.setattr(schedule, "run_due", lambda session, now_utc: {"status": "debounced"})
    tick = script.evaluate_opportunities_if_due(factory, [outcome], now_utc=NOW)
    assert tick == {
        "status": "debounced",
        "noted": ["prices"],
        "classes": [],
        "evaluation_id": None,
        "evaluation_status": None,
    }

    def boom(session, now_utc):
        raise RuntimeError("store away")

    monkeypatch.setattr(schedule, "run_due", boom)
    assert script.evaluate_opportunities_if_due(factory, [], now_utc=NOW) == {
        "status": "failed",
        "error_type": "RuntimeError",
    }


def test_a_firm_mark_write_makes_an_evaluation_due(engine) -> None:
    with Session(engine) as session:
        row = identity_repository.create_identity_principal(
            session, name="m-trader", display_name="m", role="ANALYST", data_scopes=["*"]
        )
        _key, bearer = identity_repository.create_identity_api_key(session, row.principal_id)
        session.commit()
    client = TestClient(create_app(Settings(api_profile="release")))
    response = client.put(
        "/api/market/firm-marks",
        json={"marks": [{"hub": "TTF", "period": "2027-01", "value": 30.0, "unit": "EUR/MWh"}]},
        headers={"X-Eurogas-Api-Key": PUBLIC_TOKEN, "X-Eurogas-Identity": bearer},
    )
    assert response.status_code == 200, response.text
    with Session(engine) as session:
        pending = session.get(OpportunityPendingInputRecord, "marks")
        assert pending is not None and pending.last_reason == "firm marks"
