"""Strategy-lab API tests."""

from __future__ import annotations

from fastapi.testclient import TestClient

from eurogas_nexus.api.app import create_app


def test_strategy_lab_evaluate_endpoint_returns_paper_allocation_targets() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/v1/strategy-lab/evaluate",
        json={
            "strategy_id": "sap-icis-ocm",
            "strategy_name": "SAP ICIS vs OCM",
            "run_mode": "SHADOW_RUN",
            "resource_contexts": [
                {
                    "resource_id": "easington-year",
                    "resource_name": "Easington gas year contract",
                    "available_quantity_mwh_per_day": 10000,
                    "all_in_cost_gbp_mwh": 24.0,
                    "required_tso_access": ["National Gas NTS"],
                    "company_accessible_tsos": ["National Gas NTS"],
                }
            ],
            "price_observations": [
                {
                    "observation_id": "sap-1",
                    "source_system": "operator-fixture",
                    "venue": "assessment",
                    "hub": "NBP",
                    "product": "day-ahead",
                    "price_name": "SAP",
                    "price_gbp_mwh": 27.0,
                    "observed_at_utc": "2026-01-15T16:00:00Z",
                    "delivery_start_utc": "2026-01-16T00:00:00Z",
                    "delivery_end_utc": "2026-01-17T00:00:00Z",
                    "bar_minutes": 5,
                    "source_reference": "fixture:sap",
                },
                {
                    "observation_id": "icis-1",
                    "source_system": "operator-fixture",
                    "venue": "assessment",
                    "hub": "NBP",
                    "product": "day-ahead",
                    "price_name": "ICIS_HEREN_DAY_AHEAD",
                    "price_gbp_mwh": 27.2,
                    "observed_at_utc": "2026-01-15T16:30:00Z",
                    "delivery_start_utc": "2026-01-16T00:00:00Z",
                    "delivery_end_utc": "2026-01-17T00:00:00Z",
                    "bar_minutes": 5,
                    "source_reference": "fixture:icis",
                },
                {
                    "observation_id": "ocm-1",
                    "source_system": "operator-fixture",
                    "venue": "ICE OCM",
                    "hub": "NBP",
                    "product": "within-day",
                    "price_name": "ICE_OCM",
                    "price_gbp_mwh": 29.4,
                    "observed_at_utc": "2026-01-15T16:45:00Z",
                    "delivery_start_utc": "2026-01-16T00:00:00Z",
                    "delivery_end_utc": "2026-01-17T00:00:00Z",
                    "bar_minutes": 5,
                    "source_reference": "fixture:ocm",
                },
            ],
            "components": [
                {
                    "component_id": "window",
                    "component_type": "OCM_VS_DAY_AHEAD",
                    "time_window_start": "15:00",
                    "time_window_end": "17:00",
                    "target_bar_minutes": 5,
                    "positive_spread_threshold_gbp_mwh": 0.2,
                }
            ],
            "risk_control": {"max_ocm_allocation_pct": 70, "min_day_ahead_allocation_pct": 20},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["meta"]["research_only"] is True
    assert body["meta"]["human_review_required"] is True
    assert body["data"]["candidate_action_for_review"] == "REVIEW_HIGHER_OCM_ALLOCATION"
    assert body["data"]["allocation_targets"][0]["market_bucket"] == "ICE_OCM"
    assert body["data"]["allocation_targets"][0]["target_quantity_mwh_per_day"] > 0
