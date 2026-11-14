"""EEX_Sim connector manifest (src-eex-sim)."""

from __future__ import annotations

from eurogas_nexus.domain.connectors.manifest import ConnectorManifest
from eurogas_nexus.domain.dataops.contracts import FreshnessPolicy

MANIFEST = ConnectorManifest(
    source_id="src-eex-sim",
    system="EEX_Sim",
    category="price",
    datasets=("gas-spot", "day-ahead", "weekend", "month-ahead", "simulated"),
    description="EEX-shaped simulated gas market prices injected into the runtime DB "
    "at a continuous worker cadence for decision-support testing.",
    entitled=False,
    freshness_minutes=1,
    # Declared, not defaulted (FRESH-01); the values the registry default gave.
    operations={"freshness_policy": FreshnessPolicy(1, 2880, 4320)},
)
