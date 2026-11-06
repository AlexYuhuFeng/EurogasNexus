"""NGX connector manifest (src-ngx)."""

from __future__ import annotations

from eurogas_nexus.domain.connectors.manifest import ConnectorManifest

MANIFEST = ConnectorManifest(
    source_id="src-ngx",
    system="NGX",
    category="price",
    datasets=("aeco-indices", "settlements"),
    description="NGX (ICE) Canadian gas: AECO-C/NIT indices and settlements. Licensed.",
    entitled=True,
    freshness_minutes=1440,
)
