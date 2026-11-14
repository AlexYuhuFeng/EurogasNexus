"""ICE_OCM_Sim connector manifest (src-ice-ocm-sim)."""

from __future__ import annotations

from eurogas_nexus.domain.connectors.manifest import ConnectorManifest
from eurogas_nexus.domain.dataops.contracts import FreshnessPolicy

MANIFEST = ConnectorManifest(
    source_id="src-ice-ocm-sim",
    system="ICE_OCM_Sim",
    category="price",
    datasets=("within-day", "day-ahead", "screen-marks", "simulated"),
    description="ICE OCM-shaped simulated within-day and day-ahead marks injected "
    "through the runtime DB path at a high-frequency worker cadence.",
    entitled=False,
    freshness_minutes=1,
    # Declared, not defaulted (FRESH-01); the values the registry default gave.
    operations={"freshness_policy": FreshnessPolicy(1, 2880, 4320)},
)
