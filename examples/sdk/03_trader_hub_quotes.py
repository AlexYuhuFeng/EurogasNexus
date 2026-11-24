"""Trader: bid/ask board for the nearest products at two hubs.

``bid_price``/``ask_price`` are normalised to ``currency`` per ``unit`` (for NBP that is GBP per
MWh, not pence per therm). The quotation the venue used is kept in ``metadata_json`` when the
source provides it (``native_unit``, ``native_bid``, ``native_ask``).
"""

import os

from eurogas_nexus_sdk.market import fetch_market_quotes_result

BASE_URL = os.environ.get("EUROGAS_NEXUS_BASE_URL", "http://127.0.0.1:8000")
HUBS = ("TTF", "NBP")

result = fetch_market_quotes_result(BASE_URL)
print(f"{len(result.data)} quotes returned")

for hub in HUBS:
    quotes = sorted((q for q in result.data if q.hub == hub), key=lambda q: q.delivery_start_utc)
    for quote in quotes[:4]:
        native = quote.metadata_json
        native_text = (
            f"  native {native['native_bid']}/{native['native_ask']} {native['native_unit']}"
            if "native_unit" in native
            else ""
        )
        flag = " [simulated]" if quote.simulated else ""
        print(
            f"{hub:<4} {quote.product:<12} {quote.bid_price:>9.4f}/{quote.ask_price:<9.4f}"
            f" {quote.currency}/{quote.unit}{native_text}{flag}"
        )
