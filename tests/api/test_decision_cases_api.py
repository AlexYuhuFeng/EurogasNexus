"""Decision Case API tests (Architecture V2 Wave 6).

The endpoints exist to make decision evidence reviewable and human-owned. These
tests pin the two rules that make that real: a case cannot be decided without
evidence (and the refusal lists the blockers), and the recorded actor is the
authenticated identity rather than a caller-supplied string.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.core.config import Settings
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.repositories.identity import (
    create_identity_api_key,
    create_identity_principal,
)

PUBLIC_TOKEN = "test-public-api-token"


def _prepare(tmp_path, monkeypatch) -> str:
    db_path = tmp_path / "decision.sqlite"
    database_url = f"sqlite+pysqlite:///{db_path.as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    return database_url


def _identity(database_url: str, *, name: str, role: str) -> str:
    with Session(create_engine(database_url, future=True)) as session:
        row = create_identity_principal(
            session,
            name=name,
            display_name=name.title(),
            role=role,
            data_scopes=[],
        )
        _key, bearer = create_identity_api_key(session, row.principal_id, display_name="decision-test")
        session.commit()
    return bearer


def _headers(bearer: str) -> dict[str, str]:
    return {"X-Eurogas-Api-Key": PUBLIC_TOKEN, "X-Eurogas-Identity": bearer}


def test_a_case_cannot_be_decided_before_it_has_evidence(tmp_path, monkeypatch) -> None:
    database_url = _prepare(tmp_path, monkeypatch)
    reviewer = _identity(database_url, name="decision-reviewer", role="REVIEWER")
    analyst = _identity(database_url, name="decision-analyst", role="ANALYST")
    client = TestClient(create_app(Settings(api_profile="release")))

    created = client.post(
        "/api/decision-cases",
        headers=_headers(analyst),
        json={
            "objective": "Decide where tomorrow's NBP resource should go.",
            "gas_day": "2026-09-15",
            "delivery_product": "day-ahead",
            "hub_id": "NBP",
        },
    )
    assert created.status_code == 200
    case = created.json()["data"]
    case_id = case["case_id"]
    assert case["status"] == "DRAFT"
    assert case["decidable"] is False
    assert case["evidence"] == []
    assert "evidence_required" in case["blockers"]
    assert case["created_by"] == "decision-analyst"

    refused = client.post(
        f"/api/decision-cases/{case_id}/decisions",
        headers=_headers(reviewer),
        json={"outcome": "accepted", "note": "Looks fine."},
    )
    assert refused.status_code == 409
    detail = refused.json()["detail"]
    assert detail["error"] == "case_not_decidable"
    assert "evidence_required" in detail["blockers"]


def test_evidence_then_decision_then_reopen(tmp_path, monkeypatch) -> None:
    database_url = _prepare(tmp_path, monkeypatch)
    reviewer = _identity(database_url, name="decision-reviewer", role="REVIEWER")
    analyst = _identity(database_url, name="decision-analyst", role="ANALYST")
    client = TestClient(create_app(Settings(api_profile="release")))

    case_id = client.post(
        "/api/decision-cases",
        headers=_headers(analyst),
        json={"objective": "Route choice for the gas day.", "gas_day": "2026-09-15"},
    ).json()["data"]["case_id"]

    with_evidence = client.post(
        f"/api/decision-cases/{case_id}/evidence",
        headers=_headers(analyst),
        json={
            "kind": "ROUTE_RECOMMENDATION",
            "ref": "route-rec-9",
            "label": "NBP recommendation",
            "as_of_utc": "2026-09-15T06:00:00+00:00",
            "snapshot_id": "snap-42",
        },
    )
    assert with_evidence.status_code == 200
    payload = with_evidence.json()["data"]
    assert payload["status"] == "OPEN"
    assert payload["decidable"] is True
    assert payload["reproducible"] is True
    assert payload["snapshot_id"] == "snap-42"

    # The same evidence twice is not duplicated.
    client.post(
        f"/api/decision-cases/{case_id}/evidence",
        headers=_headers(analyst),
        json={"kind": "ROUTE_RECOMMENDATION", "ref": "route-rec-9"},
    )
    reloaded = client.get(f"/api/decision-cases/{case_id}", headers=_headers(analyst)).json()["data"]
    assert len(reloaded["evidence"]) == 1

    recorded = client.post(
        f"/api/decision-cases/{case_id}/decisions",
        headers=_headers(reviewer),
        json={"outcome": "accepted", "note": "Capacity confirmed."},
    )
    assert recorded.status_code == 200
    decided = recorded.json()["data"]
    assert decided["status"] == "DECIDED"
    assert decided["records"][-1]["actor"] == "decision-reviewer"
    assert decided["records"][-1]["evidence_refs"] == ["route-rec-9"]

    reopened = client.post(f"/api/decision-cases/{case_id}/reopen", headers=_headers(reviewer))
    assert reopened.status_code == 200
    reopened_case = reopened.json()["data"]
    assert reopened_case["status"] == "REOPENED"
    # History is preserved, never deleted.
    assert len(reopened_case["records"]) == 1

    listed = client.get("/api/decision-cases", headers=_headers(analyst)).json()["data"]
    assert [row["case_id"] for row in listed] == [case_id]
    assert listed[0]["record_count"] == 1
    assert listed[0]["last_record"]["outcome"] == "accepted"


def test_an_ai_interpretation_run_is_citable_evidence(tmp_path, monkeypatch) -> None:
    """The Decision Case chain names an AI Findings/Challenge stage (W6-01 section 1).

    A governed AI interpretation is therefore citable - as an interpretation, by reference,
    beside the deterministic artefacts - and citing it does not make the case decidable on
    its own terms any differently: the evidence is still what a human decides against.
    """

    database_url = _prepare(tmp_path, monkeypatch)
    analyst = _identity(database_url, name="ai-evidence-analyst", role="ANALYST")
    client = TestClient(create_app(Settings(api_profile="release")))

    case_id = client.post(
        "/api/decision-cases",
        headers=_headers(analyst),
        json={"objective": "Challenge the carry assumption.", "gas_day": "2026-09-15"},
    ).json()["data"]["case_id"]

    attached = client.post(
        f"/api/decision-cases/{case_id}/evidence",
        headers=_headers(analyst),
        json={
            "kind": "AI_ANALYSIS",
            "ref": "monitoring-analysis-abc123",
            "label": "Ask: is the NBP premium persistent",
            "as_of_utc": "2026-09-15T06:00:00+00:00",
        },
    )

    assert attached.status_code == 200
    payload = attached.json()["data"]
    assert payload["decidable"] is True
    assert [item["kind"] for item in payload["evidence"]] == ["AI_ANALYSIS"]
    assert payload["evidence"][0]["ref"] == "monitoring-analysis-abc123"

    # The kind is the vocabulary's own value, so a client that reads it back sees the code
    # it sent rather than a normalised stand-in.
    reloaded = client.get(f"/api/decision-cases/{case_id}", headers=_headers(analyst)).json()["data"]
    assert reloaded["evidence"][0]["kind"] == "AI_ANALYSIS"


def test_the_actor_is_the_authenticated_identity_and_not_a_body_field(tmp_path, monkeypatch) -> None:
    database_url = _prepare(tmp_path, monkeypatch)
    reviewer = _identity(database_url, name="real-reviewer", role="REVIEWER")
    analyst = _identity(database_url, name="decision-analyst", role="ANALYST")
    client = TestClient(create_app(Settings(api_profile="release")))

    case_id = client.post(
        "/api/decision-cases",
        headers=_headers(analyst),
        json={"objective": "Objective", "snapshot_id": "snap-1"},
    ).json()["data"]["case_id"]

    client.post(
        f"/api/decision-cases/{case_id}/evidence",
        headers=_headers(analyst),
        json={"kind": "MARKET_CONTEXT", "ref": "market-ctx-1", "snapshot_id": "snap-1"},
    )

    # A spoofed actor in the body is ignored: the payload schema has no actor field.
    recorded = client.post(
        f"/api/decision-cases/{case_id}/decisions",
        headers=_headers(reviewer),
        json={"outcome": "rejected", "note": "Timing not confirmed.", "actor": "someone.else"},
    )
    assert recorded.status_code == 200
    assert recorded.json()["data"]["records"][-1]["actor"] == "real-reviewer"


def test_unknown_case_and_unknown_values_are_explicit(tmp_path, monkeypatch) -> None:
    database_url = _prepare(tmp_path, monkeypatch)
    analyst = _identity(database_url, name="decision-analyst", role="ANALYST")
    client = TestClient(create_app(Settings(api_profile="release")))

    missing = client.get("/api/decision-cases/case-does-not-exist", headers=_headers(analyst))
    assert missing.status_code == 404
    assert missing.json()["detail"]["error"] == "unknown_decision_case"

    unknown_kind = client.post(
        "/api/decision-cases/case-does-not-exist/evidence",
        headers=_headers(analyst),
        json={"kind": "NOT_A_KIND", "ref": "x"},
    )
    assert unknown_kind.status_code == 422

    empty_objective = client.post(
        "/api/decision-cases",
        headers=_headers(analyst),
        json={"objective": ""},
    )
    assert empty_objective.status_code == 422
