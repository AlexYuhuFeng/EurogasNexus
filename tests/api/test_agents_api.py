"""API tests for CR-15 capabilities and governed research orchestration."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import (
    CanonicalEntityRecord,
    MarketObservationRecord,
    SeriesDefinitionRecord,
)
from eurogas_nexus.db.repositories import agents
from eurogas_nexus.domain.agents.challenge import ChallengeResult
from eurogas_nexus.security.permissions import Permission, permission_for_path


@pytest.fixture()
def client(tmp_path, monkeypatch: pytest.MonkeyPatch):
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'agents-api.sqlite').as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    now = datetime.now(UTC)
    # Observations must stay inside the current UTC day (the orchestrator reads
    # the current gas day) and occupy distinct timestamps so the pairwise
    # spread has more than one sample at any wall-clock time.
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    span_microseconds = max(int((now - day_start).total_seconds() * 1_000_000), 6)
    with Session(engine) as session:
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
        for sample in range(5):
            for hub, base_value in [("NBP", 30.0), ("TTF", 28.0)]:
                observed = now - timedelta(
                    microseconds=span_microseconds * (sample + 1) // 8
                )
                session.add(
                    MarketObservationRecord(
                        observation_id=f"obs-{index}",
                        market_venue=hub,
                        product="DAY_AHEAD",
                        price=base_value + sample * 0.1,
                        unit="EUR/MWh",
                        currency="EUR",
                        period_start_utc=observed,
                        period_end_utc=observed + timedelta(hours=1),
                        observed_at_utc=observed,
                        source_system="EEX_Sim",
                        source_reference=f"test:{hub}:{sample}",
                        freshness="OBSERVED",
                        quality_score=1.0,
                        research_only=True,
                        metadata_json={"hub": hub, "tenor": "day-ahead"},
                    )
                )
                index += 1
        session.commit()
    test_client = TestClient(create_app())
    test_client.engine = engine
    return test_client


def test_agent_paths_have_declared_permissions() -> None:
    assert permission_for_path("/api/capabilities") == Permission.READ
    assert permission_for_path("/api/capabilities/x/invoke") == Permission.GOVERNED
    assert permission_for_path("/api/agent/research") == Permission.GOVERNED
    assert permission_for_path("/api/agent/runs/x/replay") == Permission.READ


def test_capability_catalog_and_invoke(client) -> None:
    catalog = client.get("/api/capabilities")
    assert catalog.status_code == 200
    capabilities = catalog.json()["data"]
    assert len(capabilities) >= 30
    ids = {item["capability_id"] for item in capabilities}
    assert "ontology.resolve_entity" in ids
    assert "route.calculate_economics" in ids

    search = client.get("/api/capabilities/search", params={"q": "spread"})
    assert search.status_code == 200
    assert any("spread" in item["capability_id"] for item in search.json()["data"])

    describe = client.get("/api/capabilities/route.calculate_economics")
    assert describe.status_code == 200
    assert describe.json()["data"]["determinism_class"] == "DETERMINISTIC"

    invoke = client.post(
        "/api/capabilities/market.get_spread/invoke",
        json={
            "arguments": {
                "origin_hub": "NBP",
                "destination_hub": "TTF",
                "product": "DAY_AHEAD",
                "origin_value": 30,
                "destination_value": 28,
                "unit": "EUR/MWh",
            }
        },
    )
    assert invoke.status_code == 200
    assert invoke.json()["data"]["data"]["value"] == -2.0

    missing = client.post("/api/capabilities/nope/invoke", json={"arguments": {}})
    assert missing.json()["data"]["failure"]["code"] == "UNKNOWN_CAPABILITY"


def test_human_confirmation_gate_via_api(client) -> None:
    response = client.post(
        "/api/capabilities/strategy.freeze_version/invoke",
        json={"arguments": {"strategy_version_id": "v1"}},
    )
    body = response.json()["data"]
    assert body["failure"]["code"] == "HUMAN_CONFIRMATION_REQUIRED"

    confirmed = client.post(
        "/api/capabilities/strategy.freeze_version/invoke",
        json={
            "arguments": {"strategy_version_id": "v1"},
            "human_confirmation": True,
            "confirmation_note": "reviewed",
        },
    )
    # Confirmation passes policy, then DB lookup fails with a typed code.
    assert confirmed.json()["data"]["status"] == "BLOCKED"


def test_agent_run_list_matches_web_dto_objective_vocabulary(client) -> None:
    run_id = _run_full_chain_research(client)
    listed = client.get("/api/agent/runs", params={"limit": 50})
    assert listed.status_code == 200
    run = next(
        item for item in listed.json()["data"]
        if item["agent_run_id"] == run_id
    )
    assert run["user_objective"] == "Is the NBP premium over TTF persistent today?"
    # Historical clients may still read the alias; both values must stay equal.
    assert run["objective"] == run["user_objective"]


def test_research_run_creates_replay_without_hidden_cot(client) -> None:
    response = client.post(
        "/api/agent/research",
        json={
            "objective": "Is the NBP premium over TTF persistent today?",
            "agent_profile": "STRATEGY_RESEARCHER",
        },
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["stage"] == "READY_FOR_HUMAN_REVIEW"
    run_id = data["agent_run_id"]

    detail = client.get(f"/api/agent/runs/{run_id}")
    assert detail.status_code == 200
    assert detail.json()["data"]["status"] == "READY_FOR_HUMAN_REVIEW"

    replay = client.get(f"/api/agent/runs/{run_id}/replay")
    assert replay.status_code == 200
    replay_data = replay.json()["data"]
    assert replay_data["hidden_chain_of_thought"] is None
    assert "tool_invocations" in replay_data
    assert replay_data["model_provider"] == "DETERMINISTIC"


def test_a_governed_research_run_registers_a_job_with_its_artefacts(client, monkeypatch) -> None:
    """Wave 8: the agent run appears in the unified job model, citing what it produced."""

    import os

    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session as SyncSession

    from eurogas_nexus.db.models import JobRecord

    response = client.post(
        "/api/agent/research",
        json={
            "objective": "Is the NBP premium over TTF persistent today?",
            "agent_profile": "STRATEGY_RESEARCHER",
        },
    )
    assert response.status_code == 200
    run_id = response.json()["data"]["agent_run_id"]
    strategy_version_id = response.json()["data"]["strategy_version_id"]

    database_url = os.environ["RUNTIME_STORE_DATABASE_URL"]
    with SyncSession(create_engine(database_url, future=True)) as session:
        jobs = session.execute(select(JobRecord)).scalars().all()

    assert len(jobs) == 1
    job = jobs[0]
    assert job.kind == "AGENT_RUN"
    assert job.status == "SUCCEEDED"
    # The job is attributed to a principal the identity vocabulary accepts, and cites the
    # run plus every artefact that really carries an id - no bare artefact label.
    assert job.principal == "public-api"
    assert f"agent_run:{run_id}" in list(job.output_refs_json)
    if strategy_version_id:
        assert f"strategy_version:{strategy_version_id}" in list(job.output_refs_json)
    assert all(":" in reference for reference in job.output_refs_json)
    assert job.input_hash
    assert "governed-research" in list(job.provenance_json)


def test_plan_validation_rejects_unknown_entity(client) -> None:
    response = client.post(
        "/api/agent/plans/validate",
        json={
            "plan": {
                "research_plan_id": "plan-bad-entity",
                "objective": "Test an unavailable entity.",
                "question": "Does Atlantis move the spread?",
                "entities": ["ent:market_hub:ATLANTIS"],
                "horizon": "D1",
                "analyses": [],
                "required_evidence": [],
            }
        },
    )
    body = response.json()["data"]
    assert body["ok"] is False
    assert "ENTITY_NOT_FOUND" in body["blockers"]


def _run_full_chain_research(client) -> str:
    """Run one governed research run that produces the complete artifact chain."""

    response = client.post(
        "/api/agent/research",
        json={
            "objective": "Is the NBP premium over TTF persistent today?",
            "agent_profile": "STRATEGY_RESEARCHER",
            "strategy_generation_allowed": True,
        },
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["stage"] == "READY_FOR_HUMAN_REVIEW"
    return data["agent_run_id"]


def test_replay_returns_every_persisted_artifact_with_lineage(client) -> None:
    """One replay request returns plan, findings, StrategyIR, validation,
    challenge report, and review pack with ids, lineage, rights, and identity."""

    run_id = _run_full_chain_research(client)

    replay = client.get(f"/api/agent/runs/{run_id}/replay")
    assert replay.status_code == 200
    data = replay.json()["data"]
    assert data["hidden_chain_of_thought"] is None
    assert data["review_entity_type"] == "agent_review_pack"

    chain = data["artifact_chain"]
    assert chain["complete"] is True
    assert chain["missing"] == []
    assert chain["present"] == list(agents.ARTIFACT_CHAIN_ORDER)
    assert chain["chain_hash"].startswith("sha256:")

    for name in agents.ARTIFACT_CHAIN_ORDER:
        envelope = data["artifacts"][name]
        assert envelope["present"] is True, name
        assert envelope["artifact_type"] == name
        assert envelope["operation_id"].startswith("agent.research."), name
        assert envelope["artifact_id"], name
        assert chain["artifact_ids"][name], name
        assert envelope["agent_run_id"] == run_id
        assert envelope["fixture"]["fixture_id"].startswith("fixture-")
        assert envelope["fixture"]["tool_invocation_ids"]
        assert envelope["replay_identity"]["replay_id"].startswith("replay-")
        assert envelope["replay_identity"]["content_hash"].startswith("sha256:")
        assert envelope["replay_identity"]["deterministic"] is True
        assert envelope["rights"]["entitlement_state"] == "NOT_APPLICABLE"
        assert envelope["rights"]["policy_boundary"] == "CapabilityRuntime"
        assert envelope["timestamps"]["created_at"]
        assert envelope["timestamps"]["run_started_at"]
        assert envelope["payload"] is not None
        assert envelope["hidden_chain_of_thought"] is None

    plan_envelope = data["artifacts"]["research_plan"]
    plan_id = plan_envelope["artifact_id"]
    assert plan_envelope["payload"]["research_plan_id"] == plan_id
    assert plan_envelope["payload"]["status"] == "VALIDATED"
    assert data["artifacts"]["research_plan"]["lineage"]["source_families"] == ["EEX_Sim"]

    findings = data["artifacts"]["findings"]
    assert findings["lineage"]["upstream_artifact_ids"] == [plan_id]
    assert all(item["finding_id"] for item in findings["payload"])
    assert findings["lineage"]["source_families"] == ["EEX_Sim"]

    strategy_ir = data["artifacts"]["strategy_ir"]
    assert strategy_ir["payload"]["schema_version"] == "strategy-ir/v1"
    assert strategy_ir["artifact_id"].startswith("strategy-ir-")

    validation = data["artifacts"]["validation"]["payload"]
    assert validation["plan_id"] == plan_id
    assert validation["plan_validation_source"].startswith("persisted:")
    assert validation["strategy_ir_validation"]["ok"] is True
    assert validation["strategy_ir_validation_source"] == "recomputed:validate_strategy_ir"
    assert validation["run_blockers"] == ["HUMAN_CONFIRMATION_REQUIRED"]

    challenge = data["artifacts"]["challenge_report"]["payload"]
    assert challenge["overall_result"] in {item.value for item in ChallengeResult}
    assert challenge["challenge_report_id"] == data["artifacts"]["challenge_report"]["artifact_id"]

    pack = data["artifacts"]["review_pack"]
    assert pack["payload"]["review_pack_id"] == data["final_output_reference"]
    packed_challenge = pack["payload"]["challenge_report"]
    assert packed_challenge["challenge_report_id"] == challenge["challenge_report_id"]
    assert pack["payload"]["human_confirmation"] == {
        "entity_type": "agent_review_pack",
        "entity_id": pack["artifact_id"],
        "decisions": [],
    }

    # Replay identity is deterministic: a second read returns the same identity.
    second = client.get(f"/api/agent/runs/{run_id}/replay").json()["data"]
    assert second["artifact_chain"] == chain
    assert second["artifacts"] == data["artifacts"]

    detail = client.get(f"/api/agent/runs/{run_id}").json()["data"]
    assert detail["artifact_chain"]["complete"] is True
    assert detail["artifact_chain"]["artifact_ids"]["review_pack"] == [pack["artifact_id"]]
    assert detail["review_entity_type"] == "agent_review_pack"


def test_replay_without_artifacts_returns_coherent_empty_shape(client) -> None:
    with Session(client.engine) as session:
        agents.create_agent_run(
            session,
            agent_run_id="agent-run-empty",
            principal_id="analyst-1",
            user_objective="Objective recorded before any artifact was produced.",
        )
        session.commit()

    replay = client.get("/api/agent/runs/agent-run-empty/replay")
    assert replay.status_code == 200
    data = replay.json()["data"]
    assert data["hidden_chain_of_thought"] is None
    assert data["artifact_chain"]["complete"] is False
    assert data["artifact_chain"]["missing"] == list(agents.ARTIFACT_CHAIN_ORDER)
    assert set(data["artifacts"]) == set(agents.ARTIFACT_CHAIN_ORDER)
    for name, envelope in data["artifacts"].items():
        assert envelope["present"] is False, name
        assert envelope["artifact_id"] is None
        assert envelope["artifact_ids"] == []
        assert envelope["payload"] is None
        assert envelope["lineage"]["source_families"] == []
        assert envelope["lineage"]["snapshot_ids"] == []
        assert envelope["rights"]["entitlement_state"] == "NOT_APPLICABLE"
        assert envelope["replay_identity"]["replay_id"].startswith("replay-")
    assert data["fixture"]["fixture_id"].startswith("fixture-")

    detail = client.get("/api/agent/runs/agent-run-empty").json()["data"]
    assert detail["artifact_chain"]["complete"] is False
    assert detail["artifact_chain"]["present"] == []


def test_review_pack_confirmation_is_recorded_and_replayed(client) -> None:
    run_id = _run_full_chain_research(client)
    replay = client.get(f"/api/agent/runs/{run_id}/replay").json()["data"]
    pack_id = replay["artifacts"]["review_pack"]["artifact_id"]

    decision = client.post(
        "/api/review/decisions",
        json={
            "entity_type": "agent_review_pack",
            "entity_id": pack_id,
            "actor": "trader-a",
            "decision": "accepted",
            "note": "evidence pack reviewed",
        },
    )
    assert decision.status_code == 200
    body = decision.json()["data"]
    assert body["entity_type"] == "agent_review_pack"
    assert body["entity_id"] == pack_id

    listed = client.get(
        "/api/review/decisions",
        params={"entity_type": "agent_review_pack", "entity_id": pack_id},
    )
    assert listed.status_code == 200
    assert [row["decision_id"] for row in listed.json()["data"]] == [body["decision_id"]]

    confirmed = client.get(f"/api/agent/runs/{run_id}/replay").json()["data"]
    confirmation = confirmed["artifacts"]["review_pack"]["payload"]["human_confirmation"]
    assert confirmation["entity_type"] == "agent_review_pack"
    assert [row["decision"] for row in confirmation["decisions"]] == ["accepted"]
    assert confirmation["decisions"][0]["actor"] == "trader-a"


def test_review_decision_rejects_unknown_entity_kind(client) -> None:
    response = client.post(
        "/api/review/decisions",
        json={
            "entity_type": "agent_replay",
            "entity_id": "agent-run-whatever",
            "actor": "trader-a",
            "decision": "accepted",
        },
    )
    assert response.status_code == 422
