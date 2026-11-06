"""NationalGasNTS connector manifest (src-national-gas-nts)."""

from __future__ import annotations

from eurogas_nexus.domain.connectors.manifest import ConnectorManifest
from eurogas_nexus.domain.connectors.operations import tariff_operations

MANIFEST = ConnectorManifest(
    source_id="src-national-gas-nts",
    system="NationalGasNTS",
    category="tariff",
    datasets=("transportation-statement", "entry-tariffs", "exit-tariffs", "commodity-charges"),
    description="National Gas NTS transportation tariff references for explicit-leg route costing.",
    entitled=False,
    freshness_minutes=43200,
    operations=tariff_operations(),
)
