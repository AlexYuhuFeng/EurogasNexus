"""CR-09 entitlement propagation API tests (release profile identities)."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.core.config import Settings
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import (
    FlowObservationRecord,
    RouteCandidateRecord,
    StrategyRunRecord,
)
from eurogas_nexus.db.repositories.identity import (
    create_identity_api_key,
    create_identity_principal,
)

PUBLIC_TOKEN = "test-public-api-token"


def _release_client(db_url: str) -> tuple[TestClient, dict[str, str]]:
    client = TestClient(create_app(Settings(api_profile="release")))
    return client, {"X-Eurogas-Api-Key": PUBLIC_TOKEN}


def _create_principal(session: Session, scopes: list[str]) -> str:
    principal = create_identity_principal(
        session,
        name=f"scope-{scopes[0].lower()}",
        display_name="Scoped Principal",
        role="ANALYST",
        data_scopes=scopes,
    )
    _, bearer = create_identity_api_key(
        session,
        principal.principal_id,
        display_name="test-key",
    )
    return bearer


def _flow(observation_id: str, source_system: str, now: datetime) -> FlowObservationRecord:
    return FlowObservationRecord(
        observation_id=observation_id,
        point_id=f"point-{observation_id}",
        point_name=observation_id,
        direction="entry",
        kind="actual",
        flow_mcm_d=1.0,
        original_value=1.0,
        original_unit="mcm/d",
        period_start_utc=now,
        period_end_utc=now,
        observed_at_utc=now,
        source_system=source_system,
        source_reference=f"test:{observation_id}",
        source_record_id=observation_id,
        freshness="live",
        research_only=True,
    )


def test_physical_flow_rows_respect_principal_scope(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "physical-entitlement.sqlite"
    database_url = f"sqlite+pysqlite:///{db_path.as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)

    now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    with Session(engine) as session:
        session.add(_flow("flow-public", "ENTSOG", now))
        session.add(_flow("flow-licensed", "EEX", now))
        bearer = _create_principal(session, ["ENTSOG"])
        session.commit()

    client, headers = _release_client(database_url)
    response = client.get(
        "/api/physical/flows",
        headers={**headers, "X-Eurogas-Identity": bearer},
    )

    assert response.status_code == 200
    rows = response.json()["data"]
    assert [row["observation_id"] for row in rows] == ["flow-public"]
    assert "flow-licensed" not in {row["observation_id"] for row in rows}


def test_route_candidate_derived_results_cannot_bypass_scope(
    tmp_path, monkeypatch,
) -> None:
    db_path = tmp_path / "route-entitlement.sqlite"
    database_url = f"sqlite+pysqlite:///{db_path.as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)

    now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    with Session(engine) as session:
        session.add(
            RouteCandidateRecord(
                route_id="route-entsog",
                route_name="Public route",
                start_point_name="TTF",
                target_point_name="NBP",
                business_model="transport",
                route_legs=[],
                required_tso_access=["ENTSOG"],
                source_systems=["ENTSOG"],
                active=True,
                created_at_utc=now,
            )
        )
        session.add(
            RouteCandidateRecord(
                route_id="route-eex",
                route_name="Licensed route",
                start_point_name="TTF",
                target_point_name="THE",
                business_model="transport",
                route_legs=[],
                required_tso_access=["EEX"],
                source_systems=["EEX"],
                active=True,
                created_at_utc=now,
            )
        )
        bearer = _create_principal(session, ["ENTSOG"])
        session.commit()

    client, headers = _release_client(database_url)
    response = client.get(
        "/api/route-cost/route-candidates",
        headers={**headers, "X-Eurogas-Identity": bearer},
    )

    assert response.status_code == 200
    body = response.json()["data"]
    assert [row["route_id"] for row in body["route_candidates"]] == ["route-entsog"]


def test_strategy_run_evidence_respects_principal_scope(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "strategy-entitlement.sqlite"
    database_url = f"sqlite+pysqlite:///{db_path.as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)

    now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    with Session(engine) as session:
        session.add(
            StrategyRunRecord(
                run_id="run-eex",
                strategy_id="strategy-eex",
                run_type="EVALUATION",
                run_mode="SHADOW_RUN",
                status="COMPLETED",
                started_at_utc=now,
                input_snapshot={},
                result_snapshot={},
                source_refs=["eex-source"],
                warnings=[],
                missing_inputs=[],
                research_only=True,
                human_review_required=True,
                manifest_json={
                    "evidence": {
                        "source_systems": ["EEX"],
                    }
                },
            )
        )
        bearer = _create_principal(session, ["ENTSOG"])
        session.commit()

    client, headers = _release_client(database_url)
    response = client.get(
        "/api/strategy-runs/run-eex",
        headers={**headers, "X-Eurogas-Identity": bearer},
    )

    assert response.status_code == 403
    assert response.json()["detail"]["error"] == "entitlement_denied"
