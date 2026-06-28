"""SDK route-cost client surface tests."""

import httpx


def test_route_cost_sdk_models_and_functions_importable() -> None:
    from eurogas_nexus.sdk.route_cost import (
        LngRegasReadinessResult,
        PortfolioOptimizationResult,
        RouteRecommendationResult,
        assess_lng_regas,
        calculate_route_cost,
        fetch_tso_tariffs,
        optimize_resource_pool,
        recommend_route_allocation,
    )

    assert callable(fetch_tso_tariffs)
    assert callable(calculate_route_cost)
    assert callable(recommend_route_allocation)
    assert callable(assess_lng_regas)
    assert callable(optimize_resource_pool)
    assert RouteRecommendationResult.model_fields
    assert LngRegasReadinessResult.model_fields
    assert PortfolioOptimizationResult.model_fields


def test_route_cost_sdk_uses_backend_api_only(monkeypatch) -> None:
    from eurogas_nexus.sdk.route_cost import recommend_route_allocation

    captured: dict[str, object] = {}

    def fake_post(url: str, json: dict, timeout: int) -> httpx.Response:
        captured["url"] = url
        captured["json"] = json
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={
                "data": {
                    "request_id": "sdk-route",
                    "status": "SUCCESS",
                    "total_requested_mwh_per_day": 100,
                    "total_allocated_mwh_per_day": 100,
                    "unallocated_mwh_per_day": 0,
                    "allocations": [
                        {
                            "route_id": "local-ttf-sale",
                            "route_name": "Sell locally at TTF",
                            "destination_market": "TTF",
                            "allocated_mwh_per_day": 100,
                            "route_cost": 0,
                            "currency": "EUR",
                            "unit": "EUR/MWh",
                            "sale_price": 31,
                            "netback": 31,
                            "rationale": ["selected_by_highest_executable_netback"],
                        }
                    ],
                    "excluded_routes": [],
                    "warnings": [],
                    "assumptions": [],
                    "research_only": True,
                    "human_review_required": True,
                },
                "meta": {
                    "research_only": True,
                    "human_review_required": True,
                    "source_references": [],
                    "warnings": [],
                },
            },
        )

    monkeypatch.setattr(httpx, "post", fake_post)

    result = recommend_route_allocation(
        "http://testserver",
        request_id="sdk-route",
        source_point_id="TTF",
        required_quantity_mwh_per_day=100,
        gas_year="2025+",
        capacity_product="ANNUAL",
        firmness="FIRM",
        candidates=[],
    )

    assert captured["url"] == "http://testserver/api/route-cost/recommend"
    assert result.request_id == "sdk-route"
    assert result.allocations[0].route_id == "local-ttf-sale"
