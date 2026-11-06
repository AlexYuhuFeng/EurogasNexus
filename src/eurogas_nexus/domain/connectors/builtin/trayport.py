"""Trayport connector manifest (src-trayport)."""

from __future__ import annotations

from eurogas_nexus.domain.connectors.manifest import ConnectorManifest, ProviderCredentialSpec
from eurogas_nexus.domain.dataops.contracts import (
    AccessMode,
    FreshnessPolicy,
    LicensedDataPolicy,
    SourceClass,
)

MANIFEST = ConnectorManifest(
    source_id="src-trayport",
    system="Trayport",
    category="price",
    datasets=("broker-screens", "market-data", "screen-orders"),
    description="Trayport screen and broker market data.",
    entitled=True,
    freshness_minutes=1,
    operations={
        "source_class": SourceClass.BROKER,
        "access_mode": AccessMode.SOCKET_FEED,
        "certification_required": True,
        "freshness_policy": FreshnessPolicy(1, 5, 30),
        "licensed_data": LicensedDataPolicy(),
    },
    credentials=(ProviderCredentialSpec("Trayport", "Trayport", implemented=False),),
)
