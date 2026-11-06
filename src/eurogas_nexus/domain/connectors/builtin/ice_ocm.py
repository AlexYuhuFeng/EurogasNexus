"""ICE_OCM connector manifest (src-ice-ocm)."""

from __future__ import annotations

from eurogas_nexus.domain.connectors.manifest import ConnectorManifest, ProviderCredentialSpec
from eurogas_nexus.domain.connectors.operations import exchange_operations

MANIFEST = ConnectorManifest(
    source_id="src-ice-ocm",
    system="ICE_OCM",
    category="price",
    datasets=("within-day", "day-ahead", "screen-orders", "live-marks"),
    description="ICE OCM live within-day and day-ahead market observations.",
    entitled=True,
    freshness_minutes=1,
    operations=exchange_operations("ICE_OCM"),
    credentials=(ProviderCredentialSpec("ICE_OCM", "ICE OCM", implemented=False),),
)
