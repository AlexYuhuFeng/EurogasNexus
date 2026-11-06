"""Kpler connector manifest (src-kpler)."""

from __future__ import annotations

from eurogas_nexus.domain.connectors.manifest import ConnectorManifest, ProviderCredentialSpec
from eurogas_nexus.domain.connectors.operations import licensed_operations

MANIFEST = ConnectorManifest(
    source_id="src-kpler",
    system="Kpler",
    category="price",
    datasets=("lng-flows", "cargo-tracking", "market-data"),
    description="Kpler licensed LNG and market intelligence feeds.",
    entitled=True,
    freshness_minutes=60,
    operations=licensed_operations(60, 180, 720),
    credentials=(ProviderCredentialSpec("Kpler", "Kpler", implemented=False),),
)
