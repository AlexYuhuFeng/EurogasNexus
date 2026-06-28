"""SDK portfolio client tests."""

import httpx

from eurogas_nexus.sdk.portfolio import (
    PortfolioLiveSummary,
    fetch_live_summary,
    fetch_pnl_snapshots,
    fetch_screen_orders,
)


def test_portfolio_sdk_targets_screen_order_endpoint(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_get(url: str, timeout: int) -> httpx.Response:
        captured["url"] = url
        captured["timeout"] = timeout
        return httpx.Response(
            200,
            request=httpx.Request("GET", url),
            json={"data": [_screen_order_payload()]},
        )

    monkeypatch.setattr(httpx, "get", fake_get)

    result = fetch_screen_orders("http://testserver")

    assert captured["url"] == "http://testserver/api/portfolio/screen-orders"
    assert captured["timeout"] == 10
    assert result[0].venue == "ICE OCM"
    assert result[0].research_only is True


def test_portfolio_sdk_targets_pnl_snapshot_endpoint(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_get(url: str, timeout: int) -> httpx.Response:
        captured["url"] = url
        return httpx.Response(
            200,
            request=httpx.Request("GET", url),
            json={"data": [_pnl_payload()]},
        )

    monkeypatch.setattr(httpx, "get", fake_get)

    result = fetch_pnl_snapshots("http://testserver")

    assert captured["url"] == "http://testserver/api/portfolio/pnl-snapshots"
    assert result[0].indicative_pnl_gbp == 5400


def test_portfolio_sdk_targets_live_summary_endpoint(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_get(url: str, timeout: int) -> httpx.Response:
        captured["url"] = url
        return httpx.Response(
            200,
            request=httpx.Request("GET", url),
            json={
                "data": {
                    "portfolio_id": "portfolio-demo",
                    "latest_valuation_time_utc": "2026-06-01T08:30:00Z",
                    "total_realized_pnl_gbp": 1200,
                    "total_unrealized_pnl_gbp": 4200,
                    "total_indicative_pnl_gbp": 5400,
                    "total_cash_value_gbp": 1800,
                    "open_order_count": 1,
                    "filled_order_count": 0,
                    "warnings": [],
                    "research_only": True,
                    "human_review_required": True,
                }
            },
        )

    monkeypatch.setattr(httpx, "get", fake_get)

    result = fetch_live_summary("http://testserver")

    assert captured["url"] == "http://testserver/api/portfolio/live-summary"
    assert isinstance(result, PortfolioLiveSummary)
    assert result.total_cash_value_gbp == 1800


def _screen_order_payload() -> dict:
    return {
        "order_observation_id": "ord-1",
        "provider_id": "ICE_OCM",
        "venue": "ICE OCM",
        "account_label": "demo-screen",
        "external_order_id": "demo-001",
        "side": "SELL",
        "order_type": "LIMIT",
        "hub": "NBP",
        "product": "Within-day",
        "contract_code": "NBP-WD-20260601",
        "delivery_start_utc": "2026-06-01T06:00:00Z",
        "delivery_end_utc": "2026-06-02T06:00:00Z",
        "price": 28.4,
        "currency": "GBP",
        "unit": "GBP/MWh",
        "quantity_mwh": 5000,
        "filled_quantity_mwh": 2500,
        "remaining_quantity_mwh": 2500,
        "status": "PARTIALLY_FILLED",
        "observed_at_utc": "2026-06-01T08:30:00Z",
        "source_system": "fixture",
        "source_reference": "fixture:order",
        "linked_strategy_id": "sap-icis-ocm",
        "linked_resource_id": "ttf-bbl-portfolio",
        "research_only": True,
        "human_review_required": True,
    }


def _pnl_payload() -> dict:
    return {
        "pnl_snapshot_id": "pnl-1",
        "portfolio_id": "portfolio-demo",
        "resource_id": "ttf-bbl-portfolio",
        "strategy_id": "sap-icis-ocm",
        "valuation_time_utc": "2026-06-01T08:30:00Z",
        "realized_pnl_gbp": 1200,
        "unrealized_pnl_gbp": 4200,
        "indicative_pnl_gbp": 5400,
        "cash_value_gbp": 1800,
        "market_value_gbp": 142000,
        "quantity_mwh": 10000,
        "valuation_basis": "live-bid-mark",
        "source_system": "fixture",
        "source_reference": "fixture:pnl",
        "warnings": [],
        "research_only": True,
        "human_review_required": True,
    }
