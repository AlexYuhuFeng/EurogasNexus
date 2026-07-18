"""SDK coverage for normalized quotes and intraday opportunities."""

import httpx

from eurogas_nexus.sdk.market import (
    fetch_intraday_opportunities_result,
    fetch_market_quotes_result,
)


def _response(url: str, data: list[dict]) -> httpx.Response:
    return httpx.Response(
        200,
        request=httpx.Request("GET", url),
        json={
            "data": data,
            "meta": {
                "research_only": True,
                "human_review_required": True,
                "source_references": ["runtime-postgresql"],
                "warnings": [],
            },
        },
    )


def test_sdk_reads_normalized_quotes_and_decision_snapshots(monkeypatch) -> None:
    def fake_get(url: str, *, params, timeout: float) -> httpx.Response:
        assert params is None
        assert timeout == 10.0
        if url.endswith("/market/quotes"):
            return _response(
                url,
                [
                    {
                        "quote_id": "quote-1",
                        "source_system": "EEX_Sim",
                        "source_record_id": "source-1",
                        "venue": "EEX",
                        "instrument_id": "EEX-TTF-DAY-AHEAD",
                        "hub": "TTF",
                        "product": "day-ahead",
                        "delivery_start_utc": "2026-07-19T05:00:00+00:00",
                        "delivery_end_utc": "2026-07-20T05:00:00+00:00",
                        "bid_price": 31.7,
                        "ask_price": 31.75,
                        "last_price": 31.72,
                        "bid_quantity_mwh": 800.0,
                        "ask_quantity_mwh": 750.0,
                        "currency": "EUR",
                        "unit": "MWh",
                        "observed_at_utc": "2026-07-18T09:30:00+00:00",
                        "received_at_utc": "2026-07-18T09:30:00+00:00",
                        "source_reference": "simulated://eex/quote-1",
                        "freshness": "simulated_live",
                        "quality_score": 0.62,
                        "simulated": True,
                        "metadata_json": {"price_level": "L1"},
                    }
                ],
            )
        return _response(
            url,
            [
                {
                    "opportunity_id": "opportunity-1",
                    "scan_id": "scan-1",
                    "opportunity_type": "CROSS_HUB_ROUTE_SPREAD",
                    "status": "ACTIONABLE_REVIEW",
                    "buy_quote_id": "quote-1",
                    "sell_quote_id": "quote-2",
                    "route_id": "ttf-bbl-nbp",
                    "route_name": "TTF -> BBL -> NBP",
                    "buy_venue": "EEX",
                    "sell_venue": "EEX",
                    "buy_hub": "TTF",
                    "sell_hub": "NBP",
                    "product": "day-ahead",
                    "delivery_start_utc": "2026-07-19T05:00:00+00:00",
                    "delivery_end_utc": "2026-07-20T05:00:00+00:00",
                    "comparison_currency": "EUR",
                    "comparison_unit": "MWh",
                    "buy_ask": 31.75,
                    "sell_bid": 33.15,
                    "gross_spread": 1.4,
                    "route_cost": 1.0,
                    "trading_cost": 0.02,
                    "risk_buffer": 0.03,
                    "net_margin": 0.35,
                    "max_quantity_mwh": 500.0,
                    "indicative_net_value": 175.0,
                    "quote_age_seconds": 0.0,
                    "confidence_score": 0.54,
                    "cost_components": [],
                    "source_refs": ["simulated://eex/quote-1"],
                    "assumptions": ["SIMULATED_L1_VISIBLE_DEPTH"],
                    "missing_inputs": [],
                    "warnings": ["SIMULATED_MARKET_DATA"],
                    "detected_at_utc": "2026-07-18T09:30:00+00:00",
                    "valid_until_utc": "2026-07-18T09:30:30+00:00",
                    "simulated": True,
                    "human_review_required": True,
                }
            ],
        )

    monkeypatch.setattr(httpx, "get", fake_get)

    quotes = fetch_market_quotes_result("https://nexus.example/")
    opportunities = fetch_intraday_opportunities_result("https://nexus.example")

    assert quotes.data[0].ask_price == 31.75
    assert quotes.data[0].metadata_json["price_level"] == "L1"
    assert opportunities.data[0].net_margin == 0.35
    assert opportunities.data[0].max_quantity_mwh == 500.0
    assert opportunities.data[0].human_review_required is True
    assert opportunities.meta.source_references == ["runtime-postgresql"]
