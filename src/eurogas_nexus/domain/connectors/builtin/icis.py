"""ICIS connector manifest (src-icis)."""

from __future__ import annotations

from eurogas_nexus.domain.connectors.manifest import ConnectorManifest, ProviderCredentialSpec
from eurogas_nexus.domain.connectors.operations import licensed_operations

MANIFEST = ConnectorManifest(
    source_id="src-icis",
    system="ICIS",
    category="price",
    datasets=("heren-assessments", "day-ahead", "indices", "curves"),
    description="ICIS Heren licensed gas assessments and reference prices.",
    entitled=True,
    freshness_minutes=1440,
    operations=licensed_operations(1440, 2880, 4320),
    credentials=(ProviderCredentialSpec("ICIS", "ICIS", implemented=False),),
)
