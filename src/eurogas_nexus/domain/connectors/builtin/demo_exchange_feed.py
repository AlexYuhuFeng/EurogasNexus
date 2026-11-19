"""Demo exchange feed (simulated) connector manifest (src-demo-exchange-feed).

The demo server's continuous feed (``scripts/demo/exchange_feed.py --continuous``): two-sided
WD/DA quotes, trade prints and session statistics for TTF and NBP, delivered through the tick
ingestion a licensed feed adapter uses. Demo profile only; every row is simulated.
"""

from __future__ import annotations

from eurogas_nexus.domain.connectors.manifest import ConnectorManifest
from eurogas_nexus.domain.dataops.contracts import FreshnessPolicy

MANIFEST = ConnectorManifest(
    source_id="src-demo-exchange-feed",
    system="DEMO_Sim",
    category="price",
    datasets=("prompt-quotes", "trade-prints", "session-statistics", "simulated"),
    description="Demo exchange feed (simulated): bursty two-sided WD/DA quotes with size, trade "
    "prints, VWAP and volume for TTF and NBP, with planted prompt cases on a schedule. Demo "
    "only; never a market price.",
    entitled=False,
    freshness_minutes=1,
    operations={"freshness_policy": FreshnessPolicy(1, 60, 720)},
)
