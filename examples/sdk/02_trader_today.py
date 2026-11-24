"""Trader: prices and book from the Today read, in the server's own units."""

import os

from eurogas_nexus_sdk.desk import fetch_desk_today_result

BASE_URL = os.environ.get("EUROGAS_NEXUS_BASE_URL", "http://127.0.0.1:8000")

today = fetch_desk_today_result(BASE_URL).data

print(f"Today {today.gas_day} (front month {today.front_month})")
market = (today.row("key_figures") or {}).get("market") or {}
for hub in market.get("hubs", []):
    for tenor in ("day_ahead", "front_month"):
        figure = hub.get(tenor)
        if figure:
            flag = " [simulated]" if figure["simulated"] else ""
            print(
                f"  {figure['label']:<14} {figure['value']:>10.3f} {figure['unit']:<8}"
                f" {figure['state']}{flag}"
            )

book = today.row("book") or {}
print("Book against the market")
for hub in book.get("hubs", []):
    pnl = hub.get("day_pnl_change") or {}
    print(
        f"  {hub['hub']:<4} net open {hub['net_open_mwh']:>14,.0f} MWh"
        f"  day P&L change {pnl.get('value', float('nan')):>14,.0f} {pnl.get('unit', '')}"
    )

for figure in today.stale_figures:
    print(f"stale: {figure}")
