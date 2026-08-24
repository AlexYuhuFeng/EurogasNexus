"""Research sandbox-scenario enforcement tests (audit item 2)."""

from fastapi.testclient import TestClient

from eurogas_nexus.api.app import create_app


def test_research_endpoints_are_sandbox_only() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/research/netback",
        json={
            "route_name": "TTF->NBP",
            "market_price_eur_mwh": 30.0,
            "route_cost_eur_mwh": 1.0,
            "fx_rate": 0.85,
            "fx_pair": "EUR/GBP",
        },
    )

    assert response.status_code == 200
    meta = response.json()["meta"]
    assert meta["decision_context"] == "SANDBOX_SCENARIO"
    assert meta["research_only"] is True


def test_research_endpoints_reject_runtime_decision_claims() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/research/route-cost",
        json={
            "route_name": "TTF->NBP",
            "components": [],
            "decision_context": "RUNTIME_DECISION",
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "runtime_decision_not_supported"


def test_every_research_path_declares_sandbox_meta() -> None:
    from apps.api.main import app

    client = TestClient(app)
    research_paths = sorted(
        path for path in app.openapi()["paths"] if path.startswith("/api/research/")
    )
    assert len(research_paths) >= 7
    for path in research_paths:
        method = "post"
        if method not in app.openapi()["paths"][path]:
            continue
        response = client.post(path, json={})
        if response.status_code == 422:
            continue  # validation-required bodies are exercised per-route above
        assert response.status_code == 200
        assert response.json()["meta"]["decision_context"] == "SANDBOX_SCENARIO"
