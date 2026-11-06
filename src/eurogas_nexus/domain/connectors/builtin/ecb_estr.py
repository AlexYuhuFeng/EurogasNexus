"""ECB_ESTR connector manifest (src-ecb-estr)."""

from __future__ import annotations

from eurogas_nexus.domain.connectors.manifest import ConnectorManifest
from eurogas_nexus.domain.connectors.operations import rate_operations

MANIFEST = ConnectorManifest(
    source_id="src-ecb-estr",
    system="ECB_ESTR",
    category="rates",
    datasets=("estr",),
    description="ECB euro short-term rate (€STR) from the ECB Data Portal: financing in EUR.",
    entitled=False,
    freshness_minutes=1440,
    operations=rate_operations("08:15", "Europe/Berlin"),
)
