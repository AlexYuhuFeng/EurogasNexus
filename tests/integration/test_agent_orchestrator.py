"""Governed research orchestrator integration tests (CR-15)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.application.agents.research_orchestrator import (
    GovernedResearchOrchestrator,
)
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import (
    AgentResearchBudgetRecord,
    CanonicalEntityRecord,
    MarketObservationRecord,
    SeriesDefinitionRecord,
)
from eurogas_nexus.db.repositories import agents
from eurogas_nexus.domain.agents.contracts import AgentInvocationContext


@pytest.fixture()
def database_url(tmp_path) -> str:
    return f"sqlite+pysqlite:///{(tmp_path / 'agent-orchestrator.sqlite').as_posix()}"


@pytest.fixture()
def session(database_url):
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        now = datetime.now(UTC)
        # The orchestrator reads market observations from the start of the current UTC day
        # (`market_rows(start_utc=now.replace(hour=0, ...))`), so the seed has to lie inside that
        # window rather than at a fixed offset from "now". Seeding relative to now made this
        # fixture pass after 05:00 UTC and fail before it, when "now - 1..5 hours" crossed back
        # into yesterday and the run legitimately found no data.
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        for code in ("NBP", "TTF"):
            session.add(
                CanonicalEntityRecord(
                    canonical_entity_id=f"ent:market_hub:{code}",
                    entity_type="market_hub",
                    canonical_code=code,
                    display_name=code,
                    created_at_utc=now,
                )
            )
        for series_id in (
            "market.price.NBP.DAY_AHEAD",
            "market.price.TTF.DAY_AHEAD",
            "market.fx.EUR.GBP",
        ):
            session.add(
                SeriesDefinitionRecord(
                    series_id=series_id,
                    name=series_id,
                    metric_type="price" if "price" in series_id else "fx",
                    entity_type="market_hub",
                    entity_id="ent:market_hub:NBP",
                    source_class="EEX_Sim",
                    native_frequency="1h",
                    native_unit="EUR/MWh",
                    temporal_type="OBSERVED",
                    availability_semantics="available_at_required",
                    created_at_utc=now,
                )
            )
        index = 0
        for hour in range(5):
            for hub, value in [("NBP", 30.0 + hour * 0.1), ("TTF", 28.0 + hour * 0.05)]:
                observed = day_start + timedelta(hours=hour + 1)
                session.add(
                    MarketObservationRecord(
                        observation_id=f"obs-{index}",
                        market_venue=hub,
                        product="DAY_AHEAD",
                        price=value,
                        unit="EUR/MWh",
                        currency="EUR",
                        period_start_utc=observed,
                        period_end_utc=observed + timedelta(hours=1),
                        observed_at_utc=observed,
                        source_system="EEX_Sim",
                        source_reference=f"test:{hub}:{hour}",
                        freshness="OBSERVED",
                        quality_score=1.0,
                        research_only=True,
                        metadata_json={"hub": hub, "tenor": "day-ahead"},
                    )
                )
                index += 1
        session.commit()
        yield session


def _principal() -> AgentInvocationContext:
    return AgentInvocationContext(
        principal_id="analyst-1",
        role="ANALYST",
        roles=["ANALYST"],
        data_scopes=["*"],
    )


def _run(session, **kwargs):
    return GovernedResearchOrchestrator().run_research(
        session,
        run_id=f"agent-run-{datetime.now(UTC).timestamp()}",
        principal=_principal(),
        objective="Does NBP trade at a premium to TTF?",
        **kwargs,
    )


def test_objective_to_plan_to_review_without_strategy(session) -> None:
    outcome = _run(session)
    assert outcome.status.value == "READY_FOR_HUMAN_REVIEW"
    assert outcome.plan is not None
    assert outcome.findings
    assert outcome.review_pack_id
    assert "STRATEGY_GENERATION_NOT_REQUESTED" in outcome.warnings


def test_strategy_generation_stops_at_human_freeze_gate(session) -> None:
    outcome = _run(session, strategy_generation_allowed=True)
    assert outcome.status.value == "READY_FOR_HUMAN_REVIEW"
    assert outcome.strategy_ir is not None
    assert "HUMAN_CONFIRMATION_REQUIRED" in outcome.blockers
    # The stages the profile declares but the run never entered are reported, so the run's label
    # cannot stand in for a pipeline that did not run.
    assert any(item.startswith("PROFILE_STAGES_NOT_REACHED:") for item in outcome.warnings)


def test_a_backtest_that_deferred_is_not_recorded_as_reached(session) -> None:
    # A frozen version that does not exist cannot be backtested: the capability refuses it, so the
    # run defers. It must then *not* claim it reached `BACKTESTED`, or the profile check built on
    # that record would read a stage that never ran as evidence that it did.
    outcome = _run(
        session,
        strategy_generation_allowed=True,
        frozen_strategy_version_id="version-does-not-exist",
        period_start_utc=datetime(2026, 1, 1, tzinfo=UTC),
        period_end_utc=datetime(2026, 2, 1, tzinfo=UTC),
    )

    assert "BACKTESTED" not in outcome.stages_reached
    assert outcome.backtest_run_id is None
    assert any(item.startswith("BACKTEST_DEFERRED") for item in outcome.warnings)
    assert "PROFILE_STAGES_NOT_REACHED:BACKTESTED" in outcome.warnings
    # The pipeline still finished its own work and reached the stages it did complete.
    assert "STRATEGY_VALIDATED" in outcome.stages_reached
    assert outcome.status.value in {"READY_FOR_HUMAN_REVIEW", "BLOCKED"}


def test_blocked_flow_persists_blocker(session) -> None:
    # Remove TTF canonical entity so semantic plan validation blocks.
    session.query(CanonicalEntityRecord).filter(
        CanonicalEntityRecord.canonical_entity_id == "ent:market_hub:TTF"
    ).delete()
    session.commit()
    outcome = _run(session)
    assert outcome.status.value == "BLOCKED"
    assert outcome.blockers
    assert session.query(AgentResearchBudgetRecord).count() == 1


def test_budget_is_created_and_replay_safe(session) -> None:
    outcome = _run(session)
    assert outcome.status.value == "READY_FOR_HUMAN_REVIEW"
    from eurogas_nexus.db.repositories import agents

    replay = agents.replay_payload(session, agents.get_agent_run(session, outcome.run_id))
    assert replay["hidden_chain_of_thought"] is None
    assert replay["tool_invocations"]


def test_persisted_artifact_chain_survives_a_fresh_session(session) -> None:
    outcome = _run(session, strategy_generation_allowed=True)
    assert outcome.status.value == "READY_FOR_HUMAN_REVIEW"
    session.commit()

    with Session(session.get_bind()) as fresh_session:
        row = agents.get_agent_run(fresh_session, outcome.run_id)
        assert row is not None
        replay = agents.replay_payload(fresh_session, row)
        summary = agents.artifact_chain_summary(fresh_session, row)

    assert replay["hidden_chain_of_thought"] is None
    assert replay["artifact_chain"]["complete"] is True
    assert summary["complete"] is True
    assert summary["artifact_ids"]["research_plan"] == [outcome.plan.research_plan_id]
    assert summary["artifact_ids"]["review_pack"] == [outcome.review_pack_id]

    artifacts = replay["artifacts"]
    assert artifacts["research_plan"]["artifact_id"] == outcome.plan.research_plan_id
    assert artifacts["research_plan"]["payload"]["question"] == outcome.plan.question
    assert len(artifacts["findings"]["artifact_ids"]) == len(outcome.findings)
    assert artifacts["strategy_ir"]["payload"]["schema_version"] == "strategy-ir/v1"
    assert artifacts["validation"]["payload"]["strategy_ir_validation"]["ok"] is True
    assert artifacts["challenge_report"]["payload"]["challenge_report_id"]
    assert artifacts["review_pack"]["artifact_id"] == outcome.review_pack_id
    for envelope in artifacts.values():
        assert envelope["fixture"]["fixture_id"].startswith("fixture-")
        assert envelope["replay_identity"]["replay_id"].startswith("replay-")
        assert envelope["rights"]["principal_id"] == "analyst-1"
        assert envelope["timestamps"]["created_at"]


def test_review_pack_confirmation_through_review_decision_api(
    database_url, session, monkeypatch
) -> None:
    """A persisted review pack is confirmed through the existing review API."""

    outcome = _run(session, strategy_generation_allowed=True)
    assert outcome.review_pack_id
    session.commit()

    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    client = TestClient(create_app())

    decision = client.post(
        "/api/review/decisions",
        json={
            "entity_type": "agent_review_pack",
            "entity_id": outcome.review_pack_id,
            "actor": "trader-a",
            "decision": "accepted",
            "note": "review pack confirmed",
        },
    )
    assert decision.status_code == 200
    assert decision.json()["data"]["entity_type"] == "agent_review_pack"

    replay = client.get(f"/api/agent/runs/{outcome.run_id}/replay")
    assert replay.status_code == 200
    payload = replay.json()["data"]
    confirmation = payload["artifacts"]["review_pack"]["payload"]["human_confirmation"]
    assert confirmation["entity_id"] == outcome.review_pack_id
    assert [row["decision"] for row in confirmation["decisions"]] == ["accepted"]

    rejected = client.post(
        "/api/review/decisions",
        json={
            "entity_type": "agent_replay",
            "entity_id": outcome.review_pack_id,
            "actor": "trader-a",
            "decision": "accepted",
        },
    )
    assert rejected.status_code == 422


def test_unknown_review_entity_kind_fails_closed_below_the_api(session) -> None:
    from eurogas_nexus.db.repositories.review import record_review_decision

    with pytest.raises(ValueError, match="unknown review entity type"):
        record_review_decision(
            session,
            entity_type="agent_replay",
            entity_id="agent-run-1",
            actor="trader-a",
            decision="accepted",
        )
