"""POST /api/portfolio/desk-replay: reconcile and compare, never execute (#48-#50)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from eurogas_nexus.api.app import create_app
from tests.unit.test_desk_replay_acceptance import _case


def test_the_route_returns_the_engine_result_with_a_fingerprint() -> None:
    client = TestClient(create_app())
    response = client.post("/api/portfolio/desk-replay", json=_case())
    assert response.status_code == 200, response.text
    body = response.json()
    data = body["data"]
    assert len(data["input_sha256"]) == 64
    assert float(data["resources"][0]["keep_plan_gap_mwh"]) == 140.0
    assert any("never executed" in warning for warning in body["meta"]["warnings"])


def test_invalid_evidence_is_a_422_with_a_reason() -> None:
    client = TestClient(create_app())
    case = _case()
    case["positions"][0]["mwh"] = "-5"
    response = client.post("/api/portfolio/desk-replay", json=case)
    assert response.status_code == 422
    assert response.json()["detail"]["error_code"] == "desk_replay_invalid"
