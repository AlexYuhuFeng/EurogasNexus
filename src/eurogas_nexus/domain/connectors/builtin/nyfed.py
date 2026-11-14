"""NYFED connector manifest (src-nyfed)."""

from __future__ import annotations

from eurogas_nexus.domain.connectors.manifest import ConnectorManifest
from eurogas_nexus.domain.connectors.operations import rate_operations
from eurogas_nexus.domain.dataops.contracts import DatasetFreshness

MANIFEST = ConnectorManifest(
    source_id="src-nyfed",
    system="NYFED",
    category="rates",
    datasets=("sofr",),
    description="Federal Reserve Bank of New York SOFR from the Markets API: financing in "
    "USD for LNG and cross-currency contracts. Free; attribution.",
    entitled=False,
    freshness_minutes=1440,
    operations=rate_operations("08:30", "America/New_York"),
    # The stored datasets and how old each one's newest period may be (FRESH-01).
    dataset_freshness=(
        DatasetFreshness(
            "SOFR (NY Fed)",
            120,
            360,
            "SOFR for day D published 08:00 New York on the next business day.",
        ),
    ),
)
