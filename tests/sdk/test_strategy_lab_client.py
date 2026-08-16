"""SDK strategy-lab client tests."""

from __future__ import annotations

import httpx

from eurogas_nexus.sdk.strategy_lab import (
    StrategyLabResult,
    StrategyRunDTO,
    StrategySummaryDTO,
    evaluate_strategy_lab,
    get_strategy_run,
    list_strategy_runs,
    strategy_summary,
)


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
                    "run_id": "run-abc123",
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
                    "paper_pnl_gbp": 42794.0,
                    "cumulative_pnl_gbp": 42794.0,
                    "hit": True,
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

    assert captured["url"] == "http://testserver/api/strategy-lab/evaluate"
    assert captured["json"]["strategy_id"] == "sap-icis-ocm"
    assert captured["timeout"] == 15
    assert isinstance(result, StrategyLabResult)
    assert result.run_id == "run-abc123"
    assert result.paper_pnl_gbp == 42794.0
    assert result.candidate_action_for_review == "REVIEW_HIGHER_OCM_ALLOCATION"


def test_strategy_lab_sdk_lists_runs(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_get(url: str, params: dict, timeout: int) -> httpx.Response:
        captured["url"] = url
        captured["params"] = params
        return httpx.Response(
            200,
            request=httpx.Request("GET", url),
            json={
                "data": [
                    {
                        "run_id": "run-1",
                        "strategy_id": "sap-icis-ocm",
                        "run_mode": "SHADOW_RUN",
                        "status": "SUCCESS",
                        "started_at_utc": "2026-07-22T10:00:00+00:00",
                        "finished_at_utc": None,
                        "paper_pnl_gbp": 100.0,
                        "cumulative_pnl_gbp": 100.0,
                        "hit": True,
                        "weighted_score": 0.4,
                        "allocation_targets": [],
                        "missing_inputs": [],
                        "warnings": [],
                        "source_refs": [],
                        "research_only": True,
                        "human_review_required": True,
                    }
                ]
            },
        )

    monkeypatch.setattr(httpx, "get", fake_get)

    result = list_strategy_runs("http://testserver", strategy_id="sap-icis-ocm")

    assert captured["url"] == "http://testserver/api/strategy-lab/runs"
    assert captured["params"]["strategy_id"] == "sap-icis-ocm"
    assert len(result) == 1
    assert isinstance(result[0], StrategyRunDTO)
    assert result[0].run_id == "run-1"


def test_strategy_lab_sdk_gets_run(monkeypatch) -> None:
    def fake_get(url: str, timeout: int) -> httpx.Response:
        return httpx.Response(
            200,
            request=httpx.Request("GET", url),
            json={
                "data": {
                    "run_id": "run-1",
                    "strategy_id": "sap-icis-ocm",
                    "run_mode": "SHADOW_RUN",
                    "status": "SUCCESS",
                    "started_at_utc": "2026-07-22T10:00:00+00:00",
                    "finished_at_utc": None,
                    "paper_pnl_gbp": 100.0,
                    "cumulative_pnl_gbp": 100.0,
                    "hit": True,
                    "weighted_score": 0.4,
                    "allocation_targets": [],
                    "missing_inputs": [],
                    "warnings": [],
                    "source_refs": [],
                    "research_only": True,
                    "human_review_required": True,
                }
            },
        )

    monkeypatch.setattr(httpx, "get", fake_get)

    result = get_strategy_run("http://testserver", "run-1")
    assert isinstance(result, StrategyRunDTO)
    assert result.run_id == "run-1"


def test_strategy_lab_sdk_summary(monkeypatch) -> None:
    def fake_get(url: str, params: dict, timeout: int) -> httpx.Response:
        return httpx.Response(
            200,
            request=httpx.Request("GET", url),
            json={
                "data": {
                    "strategy_id": "sap-icis-ocm",
                    "run_mode": None,
                    "run_count": 3,
                    "total_paper_pnl_gbp": 300.0,
                    "cumulative_pnl_gbp": 300.0,
                    "hit_rate": 0.6667,
                    "max_drawdown_gbp": 20.0,
                    "first_started_at_utc": "2026-07-20T09:00:00+00:00",
                    "last_started_at_utc": "2026-07-22T10:00:00+00:00",
                    "latest_status": "SUCCESS",
                }
            },
        )

    monkeypatch.setattr(httpx, "get", fake_get)

    result = strategy_summary("http://testserver", strategy_id="sap-icis-ocm")
    assert isinstance(result, StrategySummaryDTO)
    assert result.run_count == 3
    assert result.hit_rate == 0.6667
