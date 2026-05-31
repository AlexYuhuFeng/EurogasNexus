"""SDK strategy-lab client tests."""

from __future__ import annotations

import httpx

from eurogas_nexus.sdk.strategy_lab import StrategyLabResult, evaluate_strategy_lab


def test_strategy_lab_sdk_posts_to_backend_api(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_post(url: str, json: dict, timeout: int) -> httpx.Response:
        captured["url"] = url
        captured["json"] = json
        captured["timeout"] = timeout
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={
                "data": {
                    "strategy_id": "sap-icis-ocm",
                    "strategy_name": "SAP ICIS vs OCM",
                    "run_mode": "SHADOW_RUN",
                    "status": "SUCCESS",
                    "weighted_score": 0.42,
                    "day_ahead_average_gbp_mwh": 27.1,
                    "intraday_average_gbp_mwh": 29.2,
                    "intraday_vs_day_ahead_spread_gbp_mwh": 2.1,
                    "allocation_targets": [
                        {
                            "market_bucket": "ICE_OCM",
                            "target_allocation_pct": 62.6,
                            "target_quantity_mwh_per_day": 6260,
                            "reference_price_gbp_mwh": 29.2,
                            "expected_margin_gbp_mwh": 5.2,
                            "rationale": ["paper target"],
                        }
                    ],
                    "missing_inputs": [],
                    "warnings": [],
                    "source_refs": ["fixture:ocm"],
                    "candidate_action_for_review": "REVIEW_HIGHER_OCM_ALLOCATION",
                    "research_only": True,
                    "human_review_required": True,
                }
            },
        )

    monkeypatch.setattr(httpx, "post", fake_post)

    result = evaluate_strategy_lab(
        "http://testserver",
        strategy_id="sap-icis-ocm",
        strategy_name="SAP ICIS vs OCM",
        run_mode="SHADOW_RUN",
        resource_contexts=[],
        price_observations=[],
        components=[],
    )

    assert captured["url"] == "http://testserver/api/v1/strategy-lab/evaluate"
    assert captured["json"]["strategy_id"] == "sap-icis-ocm"
    assert captured["timeout"] == 15
    assert isinstance(result, StrategyLabResult)
    assert result.candidate_action_for_review == "REVIEW_HIGHER_OCM_ALLOCATION"
