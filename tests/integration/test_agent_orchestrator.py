"""Governed research orchestrator integration tests (CR-15)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

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
from eurogas_nexus.domain.agents.contracts import AgentInvocationContext


@pytest.fixture()
def session():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        now = datetime.now(UTC)
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
                observed = now - timedelta(hours=hour + 1)
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
