"""EEX connector manifest (src-eex)."""

from __future__ import annotations

from eurogas_nexus.domain.connectors.manifest import ConnectorManifest, ProviderCredentialSpec
from eurogas_nexus.domain.connectors.operations import exchange_operations

MANIFEST = ConnectorManifest(
    source_id="src-eex",
    system="EEX",
    category="price",
    datasets=("gas-futures", "gas-spot", "screen-trades", "settlements"),
    description="European Energy Exchange gas market prices and screen observations.",
    entitled=True,
    freshness_minutes=1,
    operations=exchange_operations("EEX"),
    credentials=(
        ProviderCredentialSpec(
            "EEX", "EEX", implemented=False, note="Licensed feed; connector pending."
        ),
    ),
)
