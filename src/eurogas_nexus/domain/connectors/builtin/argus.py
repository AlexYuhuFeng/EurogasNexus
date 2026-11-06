"""Argus connector manifest (src-argus)."""

from __future__ import annotations

from eurogas_nexus.domain.connectors.manifest import ConnectorManifest, ProviderCredentialSpec
from eurogas_nexus.domain.connectors.operations import licensed_operations

MANIFEST = ConnectorManifest(
    source_id="src-argus",
    system="Argus",
    category="price",
    datasets=("assessments", "indices", "curves"),
    description="Argus licensed gas assessments and market references.",
    entitled=True,
    freshness_minutes=1440,
    operations=licensed_operations(1440, 2880, 4320),
    credentials=(ProviderCredentialSpec("Argus", "Argus", implemented=False),),
)
