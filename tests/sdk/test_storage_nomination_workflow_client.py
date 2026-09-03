"""SDK client tests for R34 storage and nomination assessment workflows."""

from __future__ import annotations

from datetime import datetime, time

import httpx
from eurogas_nexus_sdk.optimization import (
    NominationInstructionInput,
    NominationWindowInput,
    StorageFacilityInput,
    StoragePeriodInput,
    optimize_nomination_window,
    optimize_storage_dispatch,
)


def _response(url: str, data: dict, meta: dict | None = None) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "data": data,
            "meta": meta
            or {
                "source_references": ["operator-input"],
                "warnings": [],
                "research_only": True,
                "human_review_required": True,
            },
        },
        request=httpx.Request("POST", url),
    )


def test_storage_dispatch_sdk_serializes_typed_inputs(monkeypatch) -> None:
    captured: dict = {}

    def fake_post(url: str, *, json, timeout: float, **kwargs) -> httpx.Response:
        captured["url"] = url
        captured["body"] = json
        return _response(
            url,
            {
                "status": "optimal",
                "objective_value_gbp": 100.0,
                "decisions": [],
                "terminal_inventory_mwh": 100.0,
                "warnings": [],
                "human_review_required": True,
            },
        )

    monkeypatch.setattr(httpx, "post", fake_post)

    result = optimize_storage_dispatch(
        "http://example.test",
        facility=StorageFacilityInput(
            initial_inventory_mwh=100,
            minimum_inventory_mwh=0,
            maximum_inventory_mwh=200,
            maximum_injection_mwh=50,
            maximum_withdrawal_mwh=50,
        ),
        periods=[StoragePeriodInput(period_id="p1", market_price_gbp_mwh=20)],
    )

    assert result.data.status == "optimal"
    assert captured["url"] == "http://example.test/api/optimization/storage-dispatch"
    assert captured["body"]["decision_context"] == "SANDBOX_SCENARIO"
    assert captured["body"]["facility"]["initial_inventory_mwh"] == 100
    assert captured["body"]["periods"][0]["period_id"] == "p1"


def test_nomination_window_sdk_serializes_datetime_and_time(monkeypatch) -> None:
    captured: dict = {}

    def fake_post(url: str, *, json, timeout: float, **kwargs) -> httpx.Response:
        captured["url"] = url
        captured["body"] = json
        return _response(
            url,
            {
                "status": "feasible",
                "final_quantity_mwh": 110.0,
                "decisions": [],
                "warnings": ["OUTSIDE_NOMINATION_WINDOW"],
                "human_review_required": True,
            },
        )

    monkeypatch.setattr(httpx, "post", fake_post)

    result = optimize_nomination_window(
        "http://example.test",
        initial_quantity_mwh=100,
        windows=[
            NominationWindowInput(
                window_id="w1",
                opens_at=time(0, 0),
                closes_at=time(6, 0),
                maximum_change_mwh=10,
            )
        ],
        instructions=[
            NominationInstructionInput(
                submitted_at=datetime(2026, 1, 1, 1, 0),
                requested_quantity_mwh=110,
            )
        ],
    )

    assert result.data.status == "feasible"
    assert captured["body"]["windows"][0]["opens_at"] == "00:00:00"
    assert captured["body"]["instructions"][0]["submitted_at"].startswith("2026-01-01T01:00:00")
