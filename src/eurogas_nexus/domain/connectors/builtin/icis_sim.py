"""ICIS_Sim connector manifest (src-icis-sim)."""

from __future__ import annotations

from eurogas_nexus.domain.connectors.manifest import ConnectorManifest
from eurogas_nexus.domain.dataops.contracts import FreshnessPolicy

MANIFEST = ConnectorManifest(
    source_id="src-icis-sim",
    system="ICIS_Sim",
    category="price",
    datasets=("heren-assessments", "day-ahead", "daily-assessment", "simulated"),
    description=(
        "ICIS Heren-shaped simulated daily assessment rows injected into market observations."
    ),
    entitled=False,
    freshness_minutes=1440,
    # Declared, not defaulted (FRESH-01); the values the registry default gave.
    operations={"freshness_policy": FreshnessPolicy(1440, 2880, 4320)},
)
