"""BOE connector manifest (src-boe)."""

from __future__ import annotations

from eurogas_nexus.domain.connectors.manifest import ConnectorManifest
from eurogas_nexus.domain.connectors.operations import rate_operations

MANIFEST = ConnectorManifest(
    source_id="src-boe",
    system="BOE",
    category="rates",
    datasets=("sonia",),
    description="Bank of England SONIA overnight fixing (Interactive Database series "
    "IUDSOIA): financing and early-cash valuation in GBP. Free; attribution.",
    entitled=False,
    freshness_minutes=1440,
    # Benchmark overnight rates, run by the scheduler through scripts/ops/ingest_interest_rates.py
    # once a business day after each administrator publishes.
    operations=rate_operations("10:15", "Europe/London"),
)
