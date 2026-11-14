"""NGX connector manifest (src-ngx)."""

from __future__ import annotations

from eurogas_nexus.domain.connectors.manifest import ConnectorManifest
from eurogas_nexus.domain.dataops.contracts import FreshnessPolicy

MANIFEST = ConnectorManifest(
    source_id="src-ngx",
    system="NGX",
    category="price",
    datasets=("aeco-indices", "settlements"),
    description="NGX (ICE) Canadian gas: AECO-C/NIT indices and settlements. Licensed.",
    entitled=True,
    freshness_minutes=1440,
    # Declared, not defaulted (FRESH-01); the values the registry default gave.
    operations={"freshness_policy": FreshnessPolicy(1440, 2880, 4320)},
)
