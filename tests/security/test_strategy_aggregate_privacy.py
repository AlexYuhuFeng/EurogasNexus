"""Strategy ownership survives aggregate and agent entrypoints."""

from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.api.routes.public.analysis import _db_snapshot
from eurogas_nexus.core.config import Settings
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import StrategyRunRecord, StrategyVersionRecord
from eurogas_nexus.db.repositories.agents import create_agent_run
from eurogas_nexus.db.repositories.identity import (
    create_identity_api_key,
    create_identity_principal,
)
from eurogas_nexus.db.repositories.strategy_registry import create_strategy


def _fixture(tmp_path, monkeypatch):
    url = f"sqlite+pysqlite:///{tmp_path / 'aggregate.sqlite'}"
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    now = datetime.now(UTC)
    identities = []
    with Session(engine) as session:
        for name in ("owner", "reader"):
            row = create_identity_principal(
                session, name=name, display_name=name, role="ANALYST", data_scopes=[]
            )
            _, bearer = create_identity_api_key(session, row.principal_id, scopes=[])
            identities.append((row.principal_id, bearer))
        strategy = create_strategy(
            session,
            strategy_id="private-strategy",
            name="Secret strategy",
            created_by="spoofable-display-name",
            owner_principal_id=identities[0][0],
            description="",
            now_utc=now,
        )
        session.add(
            StrategyRunRecord(
                run_id="private-run",
                strategy_id=strategy.strategy_id,
                run_mode="SHADOW_RUN",
                status="COMPLETED",
                started_at_utc=now,
                input_snapshot={"secret": "private-input"},
                result_snapshot={"secret": "private-result"},
                source_refs=[],
                warnings=[],
                missing_inputs=[],
                research_only=True,
                human_review_required=True,
            )
        )
        session.add(
            StrategyVersionRecord(
                strategy_version_id="private-version",
                strategy_id=strategy.strategy_id,
                version_number=1,
                schema_version="1",
                status="FROZEN",
                hypothesis="Secret",
                definition_json={},
                created_by="owner",
                created_at_utc=now,
                content_hash="test",
                research_only=True,
            )
        )
        create_agent_run(
            session,
            agent_run_id="owner-agent",
            principal_id=identities[0][0],
            user_objective="private research",
        )
        create_agent_run(
            session,
            agent_run_id="reader-agent",
            principal_id=identities[1][0],
            user_objective="own research",
        )
        session.commit()
    return engine, identities


def _headers(bearer):
    return {"X-Eurogas-Api-Key": "test-public-api-token", "X-Eurogas-Identity": bearer}


def test_analysis_snapshot_filters_before_provider_context(tmp_path, monkeypatch):
    engine, identities = _fixture(tmp_path, monkeypatch)
    owner = _db_snapshot(principal_id=identities[0][0])
    assert [row["run_id"] for row in owner.strategy_runs] == ["private-run"]
    assert _db_snapshot(principal_id=identities[1][0]).strategy_runs == []
    assert _db_snapshot().strategy_runs == []
    # Public sharing lets a named reader see the projection, without changing ownership.
    from eurogas_nexus.db.models import StrategyRecord

    with Session(engine) as session:
        session.get(StrategyRecord, "private-strategy").visibility = "PUBLIC"
        session.commit()
    assert len(_db_snapshot(principal_id=identities[1][0]).strategy_runs) == 1
    engine.dispose()


def test_agent_run_history_is_owner_only_and_shared_strategy_is_not_writable(tmp_path, monkeypatch):
    engine, identities = _fixture(tmp_path, monkeypatch)
    client = TestClient(create_app(Settings(api_profile="release")))
    headers = _headers(identities[1][1])
    response = client.get("/api/agent/runs", headers=headers)
    assert response.status_code == 200
    assert [row["agent_run_id"] for row in response.json()["data"]] == ["reader-agent"]
    for suffix in ("", "/replay"):
        response = client.get("/api/agent/runs/owner-agent" + suffix, headers=headers)
        assert response.status_code == 404
        assert "private research" not in response.text
    from eurogas_nexus.db.models import StrategyRecord

    with Session(engine) as session:
        session.get(StrategyRecord, "private-strategy").visibility = "PUBLIC"
        session.commit()
    response = client.post(
        "/api/agent/research",
        headers=headers,
        json={
            "objective": "Test only",
            "frozen_strategy_version_id": "private-version",
            "strategy_generation_allowed": True,
        },
    )
    assert response.status_code == 404
    engine.dispose()


def test_portfolio_and_review_projections_hide_private_derivatives(tmp_path, monkeypatch):
    from eurogas_nexus.application.projections.portfolio_reads import pnl_snapshots
    from eurogas_nexus.application.projections.review_context import _resolve_evidence
    from eurogas_nexus.db.models import AgentReviewPackRecord, PortfolioPnlSnapshotRecord
    from eurogas_nexus.db.repositories.review import list_review_decisions, record_review_decision
    from eurogas_nexus.security.identity import AuthenticatedPrincipal

    engine, identities = _fixture(tmp_path, monkeypatch)
    now = datetime.now(UTC)
    with Session(engine) as session:
        for identifier, strategy in [("private-pnl", "private-strategy"), ("public-pnl", None)]:
            session.add(
                PortfolioPnlSnapshotRecord(
                    pnl_snapshot_id=identifier,
                    portfolio_id="portfolio",
                    strategy_id=strategy,
                    valuation_time_utc=now,
                    realized_pnl_gbp=1,
                    unrealized_pnl_gbp=2,
                    indicative_pnl_gbp=3,
                    cash_value_gbp=4,
                    market_value_gbp=5,
                    quantity_mwh=6,
                    valuation_basis="synthetic",
                    source_system="operator-input",
                    source_reference="test",
                    warnings=[],
                    research_only=True,
                    human_review_required=True,
                )
            )
        record_review_decision(
            session,
            entity_type="intraday_opportunity",
            entity_id="public",
            actor="owner",
            decision="accepted",
            note="public-note",
        )
        record_review_decision(
            session,
            entity_type="strategy_run",
            entity_id="private-run",
            actor="owner",
            decision="accepted",
            note="secret-note",
        )
        session.add(
            AgentReviewPackRecord(
                review_pack_id="owner-review-pack",
                agent_run_id="owner-agent",
                objective="Private owner review",
            )
        )
        session.flush()
        record_review_decision(
            session,
            entity_type="agent_review_pack",
            entity_id="owner-review-pack",
            actor="owner",
            decision="accepted",
            note="secret-agent-note",
        )
        session.commit()
        assert len(pnl_snapshots(session, principal_id=identities[0][0])) == 2
        assert [
            r.pnl_snapshot_id for r in pnl_snapshots(session, principal_id=identities[1][0])
        ] == ["public-pnl"]
        assert [
            r["entity_id"]
            for r in list_review_decisions(session, principal_id=identities[1][0], limit=1)
        ] == ["public"]  # Filter before limit: newer private rows cannot crowd out public rows.
        assert len(list_review_decisions(session, principal_id=identities[0][0])) == 3
        reader = AuthenticatedPrincipal(
            principal_id=identities[1][0],
            name="reader",
            principal_type="USER",
            role="ANALYST",
            status="ACTIVE",
            data_scopes=(),
        )
        for entity_type, entity_id in [
            ("strategy_run", "private-run"),
            ("agent_review_pack", "owner-review-pack"),
        ]:
            evidence = _resolve_evidence(session, reader, entity_type, entity_id, now_utc=now)
            assert evidence["artifact"] is None
            assert evidence["unavailable_reason"] == "EVIDENCE_NOT_FOUND"
    engine.dispose()


def test_direct_capability_cannot_mask_private_version_with_permitted_strategy(
    tmp_path, monkeypatch
):
    from types import SimpleNamespace

    from eurogas_nexus.application.agents.strategy_privacy import guard_strategy_capability

    engine, identities = _fixture(tmp_path, monkeypatch)
    with Session(engine) as session:
        create_strategy(
            session,
            strategy_id="reader-own",
            name="Own",
            description="",
            created_by="reader",
            owner_principal_id=identities[1][0],
            now_utc=datetime.now(UTC),
        )
        session.commit()
        context = SimpleNamespace(principal_id=identities[1][0])
        definition = SimpleNamespace(capability_id="strategy.get", capability_version="v1")
        assert (
            guard_strategy_capability(session, {"strategy_id": "reader-own"}, context, definition)
            is None
        )
        assert (
            guard_strategy_capability(
                session,
                {"strategy_id": "reader-own", "strategy_version_id": "private-version"},
                context,
                definition,
            )
            is not None
        )
        create = SimpleNamespace(capability_id="strategy.create_draft", capability_version="v1")
        assert (
            guard_strategy_capability(
                session, {"strategy_id": "new-custom-id"}, context, create, write=True
            )
            is None
        )
    engine.dispose()
