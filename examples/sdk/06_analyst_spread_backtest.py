"""Analyst: build a TTF - THE month-ahead spread and backtest a z-score rule on the server."""

import os

from eurogas_nexus_sdk.research import analyse_spread, list_spread_series

BASE_URL = os.environ.get("EUROGAS_NEXUS_BASE_URL", "http://127.0.0.1:8000")

series = [s for s in list_spread_series(BASE_URL) if s["tenor"] == "month-ahead"]
print("month-ahead series:", ", ".join(f"{s['hub']} ({s['days']} d)" for s in series))

analysis = analyse_spread(
    BASE_URL,
    legs=[
        {"hub": "TTF", "tenor": "month-ahead", "weight": 1.0},
        {"hub": "THE", "tenor": "month-ahead", "weight": -1.0},
    ],
    rule={"kind": "zscore", "lookback": 20, "entry_z": 2.0, "exit_z": 0.5},
)
stats, metrics = analysis["statistics"], analysis["metrics"]
print(
    f"{analysis['labels']} in {analysis['unit']}:"
    f" last {stats['last']}, mean {stats['mean']}, z-score {stats['zscore_last']}"
)
print(
    f"rule: {metrics['trades']} trades, hit rate {metrics['hit_rate']},"
    f" total P&L {metrics['total_pnl']} {analysis['pnl_currency']}"
)
for limitation in analysis["limitations"]:
    print(f"limitation: {limitation}")
