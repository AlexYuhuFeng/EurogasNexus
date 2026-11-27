"""API tests for the CR-15 capability catalogue and invoke boundary."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from eurogas_nexus.api.app import create_app
from eurogas_nexus.security.permissions import Permission, permission_for_path

#: A dormant capability (design basis 2, I.3): its routes are served for these tests only.
pytestmark = pytest.mark.deferred_capabilities


@pytest.fixture()
def client() -> TestClient:
    return TestClient(create_app())


def test_agent_paths_have_declared_permissions() -> None:
    assert permission_for_path("/api/capabilities") == Permission.READ
    assert permission_for_path("/api/capabilities/x/invoke") == Permission.GOVERNED


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


def test_a_call_without_a_resolved_caller_is_refused_not_given_every_scope():
    from types import SimpleNamespace

    from fastapi import HTTPException

    from eurogas_nexus.api.routes.public.agents import _principal

    request = SimpleNamespace(state=SimpleNamespace())
    with pytest.raises(HTTPException) as refused:
        _principal(request)
    assert refused.value.status_code == 401
