"""Platts connector manifest (src-platts)."""

from __future__ import annotations

from eurogas_nexus.domain.connectors.manifest import ConnectorManifest, ProviderCredentialSpec
from eurogas_nexus.domain.connectors.operations import licensed_operations

MANIFEST = ConnectorManifest(
    source_id="src-platts",
    system="Platts",
    category="price",
    datasets=("assessments", "forward-curves", "indices"),
    description="Platts licensed gas price assessments and curves.",
    entitled=True,
    freshness_minutes=1440,
    operations=licensed_operations(1440, 2880, 4320),
    credentials=(ProviderCredentialSpec("Platts", "Platts", implemented=False),),
)
