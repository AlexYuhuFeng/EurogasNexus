"""ICE_ENDEX_Sim connector manifest (src-ice-endex-sim)."""

from __future__ import annotations

from eurogas_nexus.domain.connectors.manifest import ConnectorManifest
from eurogas_nexus.domain.dataops.contracts import FreshnessPolicy

MANIFEST = ConnectorManifest(
    source_id="src-ice-endex-sim",
    system="ICE_ENDEX_Sim",
    category="price",
    datasets=("gas-option-settlements", "simulated"),
    description="ICE Endex-shaped simulated TTF option settlements (end of day, every strike, "
    "Black-76 implied volatility); outranked by any exchange or vendor option settlement.",
    entitled=False,
    freshness_minutes=1440,
    operations={"freshness_policy": FreshnessPolicy(1440, 2880, 4320)},
)
