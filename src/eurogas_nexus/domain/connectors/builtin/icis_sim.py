"""ICIS_Sim connector manifest (src-icis-sim)."""

from __future__ import annotations

from eurogas_nexus.domain.connectors.manifest import ConnectorManifest

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
)
