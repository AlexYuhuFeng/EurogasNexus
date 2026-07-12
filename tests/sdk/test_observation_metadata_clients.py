"""SDK observation clients preserve canonical fields and response metadata."""

import httpx
import pytest

from eurogas_nexus.sdk._transport import SdkProtocolError
from eurogas_nexus.sdk.market import fetch_market_observations_result
from eurogas_nexus.sdk.physical import fetch_capacity_result
from eurogas_nexus.sdk.sources import fetch_sources_result


def _response(url: str, data: object, *, warnings: list[str] | None = None) -> httpx.Response:
    return httpx.Response(
        200,
        request=httpx.Request("GET", url),
        json={
            "data": data,
            "meta": {
                "research_only": True,
                "human_review_required": True,
                "source_references": ["runtime-postgresql"],
                "warnings": warnings or [],
            },
        },
    )


def test_physical_capacity_result_preserves_direction_and_metadata(monkeypatch) -> None:
    def fake_get(url: str, *, params, timeout: float) -> httpx.Response:
        assert url == "https://nexus.example/api/physical/capacity"
        assert params is None
        assert timeout == 10.0
        return _response(
            url,
            [
                {
                    "observation_id": "cap-1",
                    "point_id": "point-1",
                    "point_name": "Bacton",
                    "direction": "entry",
                    "capacity_type": "technical",
                    "capacity_mcm_d": 12.5,
                    "original_value": 145000.0,
                    "original_unit": "kWh/h",
                    "period_start_utc": "2026-07-11T05:00:00+00:00",
                    "period_end_utc": "2026-07-12T05:00:00+00:00",
                    "observed_at_utc": "2026-07-11T12:00:00+00:00",
                    "source_system": "ENTSOG",
                    "source_reference": "entsog://capacity/cap-1",
                    "freshness": "current",
                    "research_only": True,
                }
            ],
            warnings=["review capacity product"],
        )

    monkeypatch.setattr(httpx, "get", fake_get)

    result = fetch_capacity_result("https://nexus.example")

    assert result.data[0].direction == "entry"
    assert result.data[0].source_system == "ENTSOG"
    assert result.meta.warnings == ["review capacity product"]
    assert result.meta.source_references == ["runtime-postgresql"]


def test_market_and_source_results_preserve_operational_provenance(monkeypatch) -> None:
    def fake_get(url: str, *, params, timeout: float) -> httpx.Response:
        if url.endswith("/market/observations"):
            return _response(
                url,
                [
                    {
                        "observation_id": "price-1",
                        "market_venue": "Trayport",
                        "product": "TTF Within-day",
                        "price": 34.2,
                        "unit": "EUR/MWh",
                        "currency": "EUR",
                        "period_start_utc": "2026-07-11T05:00:00+00:00",
                        "period_end_utc": "2026-07-12T05:00:00+00:00",
                        "observed_at_utc": "2026-07-11T12:00:00+00:00",
                        "source_system": "Trayport_Sim",
                        "source_reference": "simulated://trayport/price-1",
                        "source_record_id": "price-1",
                        "freshness": "current",
                        "quality_score": 0.95,
                        "metadata_json": {"simulated": True},
                    }
                ],
            )
        return _response(
            url,
            [
                {
                    "source_id": "trayport",
                    "source_system": "Trayport",
                    "datasets": ["market_prices"],
                    "workflow_ready": True,
                    "operational_status": "active_simulated",
                    "effective_source_system": "Trayport_Sim",
                    "effective_record_count": 50,
                }
            ],
        )

    monkeypatch.setattr(httpx, "get", fake_get)

    market = fetch_market_observations_result("https://nexus.example/")
    sources = fetch_sources_result("https://nexus.example")

    assert market.data[0].source_system == "Trayport_Sim"
    assert market.data[0].metadata_json["simulated"] is True
    assert sources.data[0].workflow_ready is True
    assert sources.data[0].effective_record_count == 50


def test_sdk_reports_non_json_protocol_errors(monkeypatch) -> None:
    def fake_get(url: str, *, params, timeout: float) -> httpx.Response:
        return httpx.Response(
            200,
            request=httpx.Request("GET", url),
            headers={"content-type": "text/html"},
            text="<!doctype html><title>proxy error</title>",
        )

    monkeypatch.setattr(httpx, "get", fake_get)

    with pytest.raises(SdkProtocolError, match="non-JSON"):
        fetch_sources_result("https://nexus.example")
