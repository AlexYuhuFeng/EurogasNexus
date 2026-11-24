"""LNG trader: each firm cargo at sea, its slot, what moved, and the months its gas lands in."""

import os

from eurogas_nexus_sdk.lng_cargo_plan import fetch_cargo_plan, fetch_cargo_plans

BASE_URL = os.environ.get("EUROGAS_NEXUS_BASE_URL", "http://127.0.0.1:8000")

board = fetch_cargo_plans(BASE_URL)
if not board:
    print("No firm cargoes in transit (an ETRM import of the firm's cargoes fills this).")
for line in board:
    print(f"{line['cargo_id']}: slot {line.get('slot_status')}, next: {line.get('next')}")
    if line.get("headline"):
        print(f"  last change: {line['headline']}")
    plan = fetch_cargo_plan(BASE_URL, line["cargo_id"])
    for month in plan.months:
        print(
            f"  {month.hub} {month.month}: physical {month.physical_mwh:>12,.0f} MWh"
            f"  hedged {month.hedge_mwh:>12,.0f}  net {month.net_mwh:>12,.0f}"
        )
