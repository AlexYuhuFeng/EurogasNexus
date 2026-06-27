"""SDK route-cost client surface tests."""

import httpx


def test_route_cost_sdk_models_and_functions_importable() -> None:
    from eurogas_nexus.sdk.route_cost import (
        EasingtonContractOptionsResult,
        LngRegasReadinessResult,
        PortfolioOptimizationResult,
        assess_lng_regas,
        compare_easington_contract_options,
        fetch_uk_easington_tariffs,
        optimize_resource_pool,
    )

    assert callable(fetch_uk_easington_tariffs)
    assert callable(assess_lng_regas)
    assert callable(optimize_resource_pool)
    assert callable(compare_easington_contract_options)
    assert EasingtonContractOptionsResult.model_fields
    assert LngRegasReadinessResult.model_fields
    assert PortfolioOptimizationResult.model_fields


def test_route_cost_sdk_uses_backend_api_only(monkeypatch) -> None:
    from eurogas_nexus.sdk.route_cost import compare_easington_contract_options

    captured: dict[str, object] = {}

    def fake_post(url: str, json: dict, timeout: int) -> httpx.Response:
        captured["url"] = url
        captured["json"] = json
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={
                "data": {
                    "contract_id": "sdk-contract",
                    "gas_year": "2025/26",
                    "delivery_point_name": "Easington Beach Terminal",
                    "delivery_quantity_mwh_per_day": 10000,
                    "delivery_tolerance_pct": 2,
                    "nomination_tolerance_pct": 1,
                    "delivery_tolerance_mwh": 200,
                    "nomination_tolerance_mwh": 100,
                    "options": [],
                    "missing_inputs": [],
                    "warnings": [],
                    "source_refs": [],
                    "research_only": True,
                    "human_review_required": False,
                },
                "meta": {
                    "research_only": True,
                    "human_review_required": False,
                    "source_references": [],
                    "warnings": [],
                },
            },
        )

    monkeypatch.setattr(httpx, "post", fake_post)

    result = compare_easington_contract_options(
        "http://testserver",
        contract_id="sdk-contract",
        gas_year="2025/26",
        delivery_quantity_mwh_per_day=10000,
        contract_price_gbp_mwh=25,
        nbp_sale_price_gbp_mwh=28,
        physical_exit_sale_price_gbp_mwh=28.5,
        tolerance_risk_allowance_gbp_mwh=0.1,
    )

    assert captured["url"] == "http://testserver/api/route-cost/uk/easington/options"
    assert result.contract_id == "sdk-contract"
