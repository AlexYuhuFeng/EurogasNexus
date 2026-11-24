"""Risk: net position, tightest limit and active outages that touch the book."""

import os

from eurogas_nexus_sdk.desk import fetch_desk_today_result
from eurogas_nexus_sdk.physical import fetch_outages_result

BASE_URL = os.environ.get("EUROGAS_NEXUS_BASE_URL", "http://127.0.0.1:8000")

today = fetch_desk_today_result(BASE_URL).data
key_figures = today.row("key_figures") or {}

position = (key_figures.get("position") or {}).get("today")
if position:
    print(f"{position['label']}: {position['value']:,.0f} {position['unit']}")

limit = key_figures.get("tightest_limit")
if limit:
    print(
        f"tightest limit: {limit['label']} {limit['value']:,.0f} {limit['unit']}"
        f" ({limit['utilisation_pct']} % used, {limit['status']})"
    )
    print(f"  method: {limit['method']['summary']}")

outages = fetch_outages_result(BASE_URL)
for event in outages.data:
    if event.status == "active":
        print(
            f"outage {event.facility_name} ({event.balancing_zone}):"
            f" {event.unavailable_gwh_d} GWh/d until {event.end_utc}"
        )
