"""SDK optimization client tests (P1 coverage closure)."""

import httpx
import pytest

from eurogas_nexus.sdk.optimization import (
    NetworkEdgeInput,
    SupplyResourceInput,
    fetch_optimization_run,
    optimize_capacity,
    optimize_contracts,
    optimize_resource_pool,
    optimize_route,
)


def _response(url: str, data: dict, meta: dict | None = None) -> httpx.Response:
    default_meta = {"source_references": ["operator-input"], "warnings": []}
    return httpx.Response(
        200,
        json={"data": data, "meta": meta or default_meta},
        request=httpx.Request("POST", url),
    )


def test_optimize_route_returns_typed_result(monkeypatch) -> None:
    captured: dict = {}

    def fake_post(url: str, *, json, timeout: float, **kwargs) -> httpx.Response:
        captured["body"] = json
        return _response(
            url,
            {
                "status": "optimal",
                "edge_ids": ["ab", "bc"],
                "nodes": ["A", "B", "C"],
                "total_cost_gbp_mwh": 2.5,
                "bottleneck_capacity_mwh": 80.0,
                "warnings": [],
                "human_review_required": True,
            },
        )

    monkeypatch.setattr(httpx, "post", fake_post)

    result = optimize_route(
        "http://example.test",
        source="A",
        target="C",
        required_capacity_mwh=50,
        edges=[
            NetworkEdgeInput(
                edge_id="ab",
                source="A",
                target="B",
                tariff_gbp_mwh=1.0,
                available_capacity_mwh=100,
            )
        ],
    )

    assert result.data.status == "optimal"
    assert result.data.edge_ids == ["ab", "bc"]
    assert result.data.total_cost_gbp_mwh == 2.5
    assert captured["body"]["source"] == "A"
    assert captured["body"]["decision_context"] == "SANDBOX_SCENARIO"


def test_optimize_resource_pool_supports_runtime_decision(monkeypatch) -> None:
    captured: dict = {}

    def fake_post(url: str, *, json, timeout: float, **kwargs) -> httpx.Response:
        captured["body"] = json
        return _response(
            url,
            {
                "status": "optimal",
                "objective_value_gbp": 100.0,
                "allocations": [],
                "dispatches": [],
                "unmet_minimum_take_mwh": 0.0,
                "unsold_volume_mwh": 0.0,
                "warnings": [],
                "diagnostics": {"resource_count": 1},
                "human_review_required": True,
            },
            meta={
                "source_references": ["runtime-postgresql"],
                "warnings": [],
                "run_id": "opt-abc",
                "snapshot_id": "opt-abc",
                "decision_context": "RUNTIME_DECISION",
            },
        )

    monkeypatch.setattr(httpx, "post", fake_post)

    result = optimize_resource_pool(
        "http://example.test",
        resources=[],
        sale_options=[],
        decision_context="RUNTIME_DECISION",
        portfolio_id="p1",
    )

    assert result.data.status == "optimal"
    assert result.meta.run_id == "opt-abc"
    assert result.meta.source_references == ["runtime-postgresql"]


def test_optimize_capacity_and_contracts(monkeypatch) -> None:
    def fake_post(url: str, *, json, timeout: float, **kwargs) -> httpx.Response:
        if url.endswith("/capacity"):
            return _response(
                url,
                {
                    "status": "optimal",
                    "selected_product_ids": ["annual"],
                    "total_capacity_mwh": 100.0,
                    "total_cost_gbp": 50.0,
                    "excess_capacity_mwh": 0.0,
                    "warnings": [],
                    "human_review_required": True,
                },
            )
        return _response(
            url,
            {
                "status": "feasible",
                "objective_value_gbp": 10.0,
                "allocations": [],
                "dispatches": [],
                "unmet_minimum_take_mwh": 0.0,
                "unsold_volume_mwh": 0.0,
                "warnings": ["UNSERVED_DEMAND_REMAINS"],
                "diagnostics": {},
                "human_review_required": True,
            },
        )

    monkeypatch.setattr(httpx, "post", fake_post)

    capacity = optimize_capacity(
        "http://example.test",
        products=[{"product_id": "annual", "capacity_mwh": 100, "fixed_cost_gbp": 50}],
        required_capacity_mwh=100,
    )
    assert capacity.data.selected_product_ids == ["annual"]

    contracts = optimize_contracts(
        "http://example.test",
        resources=[SupplyResourceInput(resource_id="r", available_mwh=100, unit_cost_gbp_mwh=20)],
        market_price_gbp_mwh=25,
        demand_limit_mwh=100,
    )
    assert contracts.data.status == "feasible"


def test_fetch_optimization_run_evidence(monkeypatch) -> None:
    def fake_get(url: str, *, timeout: float, **kwargs) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": {
                    "run_id": "opt-abc",
                    "optimization_type": "resource_pool",
                    "decision_context": "RUNTIME_DECISION",
                    "status": "SUCCESS",
                    "input_snapshot": {"portfolio_id": "p1"},
                    "output_snapshot": {"status": "optimal"},
                    "source_refs": ["runtime-postgresql"],
                    "warnings": [],
                    "created_at_utc": "2026-07-01T12:00:00+00:00",
                    "research_only": True,
                    "human_review_required": True,
                },
                "meta": {"source_references": ["optimization_runs"], "warnings": []},
            },
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(httpx, "get", fake_get)

    run = fetch_optimization_run("http://example.test", "opt-abc")

    assert run.data.decision_context == "RUNTIME_DECISION"
    assert run.data.input_snapshot["portfolio_id"] == "p1"


def test_optimize_resource_pool_rejects_mixed_input_types() -> None:
    with pytest.raises(TypeError, match="expected dict or pydantic model"):
        from eurogas_nexus.sdk.optimization import _as_dict

        _as_dict(42)
