"""SDK client tests for the R31 portfolio-network optimization endpoint."""

from __future__ import annotations

from datetime import date

import httpx
from eurogas_nexus_sdk.optimization import optimize_portfolio_network


def _response(url: str, data: dict, meta: dict | None = None) -> httpx.Response:
    default_meta = {
        "source_references": ["runtime-postgresql"],
        "lineage": ["route_candidate:r"],
        "assumptions": ["test"],
        "missing_inputs": [],
        "warnings": [],
        "run_id": "opt-r31",
        "snapshot_id": "opt-r31",
        "decision_context": "RUNTIME_DECISION",
        "gas_day": "2026-01-01",
    }
    return httpx.Response(
        200,
        json={"data": data, "meta": meta or default_meta},
        request=httpx.Request("POST", url),
    )


def _result_data() -> dict:
    return {
        "status": "optimal",
        "objective_value_gbp": 227.0,
        "served_demand_mwh": 100.0,
        "unserved_demand_mwh": 0.0,
        "total_revenue_gbp": 2822.0,
        "total_supply_cost_gbp": 2510.0,
        "total_network_cost_gbp": 85.0,
        "edge_flows": [
            {
                "edge_id": "route:r",
                "route_id": "r",
                "quantity_mwh": 100.0,
                "tariff_gbp_mwh": 0.85,
                "cost_gbp": 85.0,
            }
        ],
        "allocations": [
            {
                "resource_id": "c1",
                "option_id": "route:r",
                "quantity_mwh": 100.0,
                "unit_margin_gbp_mwh": 2.27,
                "pnl_gbp": 227.0,
                "path_edge_ids": ["route:r"],
            }
        ],
        "contract_attributions": [
            {
                "contract_id": "c1",
                "quantity_mwh": 100.0,
                "revenue_gbp": 2822.0,
                "supply_cost_gbp": 2510.0,
                "network_cost_gbp": 85.0,
                "pnl_gbp": 227.0,
                "option_flows": [],
            }
        ],
        "warnings": [],
        "diagnostics": {"path_count": 1},
        "human_review_required": True,
    }


def test_optimize_portfolio_network_sends_metadata_only_and_parses_dto(
    monkeypatch,
) -> None:
    captured: dict = {}

    def fake_post(url: str, *, json, timeout: float, **kwargs) -> httpx.Response:
        captured["url"] = url
        captured["body"] = json
        captured["timeout"] = timeout
        return _response(url, _result_data())

    monkeypatch.setattr(httpx, "post", fake_post)

    result = optimize_portfolio_network(
        "http://example.test",
        portfolio_id="p1",
        gas_day=date(2026, 1, 1),
        capacity_product="ANNUAL",
        firmness="FIRM",
        max_market_price_age_hours=72,
    )

    assert result.data.status == "optimal"
    assert result.data.objective_value_gbp == 227.0
    assert result.data.contract_attributions[0]["contract_id"] == "c1"
    assert result.meta.run_id == "opt-r31"
    assert result.meta.snapshot_id == "opt-r31"
    assert captured["url"] == "http://example.test/api/optimization/portfolio-network"
    assert captured["body"] == {
        "portfolio_id": "p1",
        "gas_day": "2026-01-01",
        "capacity_product": "ANNUAL",
        "firmness": "FIRM",
        "max_market_price_age_hours": 72,
        "decision_context": "RUNTIME_DECISION",
    }
    # No fabricated network facts are ever present in an SDK request.
    assert "edges" not in captured["body"]
    assert "accessible_tsos" not in captured["body"]
    assert captured["timeout"] == 30.0


def test_optimize_portfolio_network_accepts_iso_gas_day_string(monkeypatch) -> None:
    captured: dict = {}

    def fake_post(url: str, *, json, timeout: float, **kwargs) -> httpx.Response:
        captured["body"] = json
        return _response(url, _result_data())

    monkeypatch.setattr(httpx, "post", fake_post)

    result = optimize_portfolio_network(
        "http://example.test",
        portfolio_id="p1",
        gas_day="2026-01-01",
    )

    assert result.data.status == "optimal"
    assert captured["body"]["gas_day"] == "2026-01-01"
