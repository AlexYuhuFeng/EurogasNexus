"""FluxysBelgium connector manifest (src-fluxys-belgium)."""

from __future__ import annotations

from eurogas_nexus.domain.connectors.manifest import ConnectorManifest
from eurogas_nexus.domain.connectors.operations import tariff_operations

MANIFEST = ConnectorManifest(
    source_id="src-fluxys-belgium",
    system="FluxysBelgium",
    category="tariff",
    datasets=("belgium-transmission-tariffs", "ztp", "interconnection"),
    description="Fluxys Belgium transmission tariff references for ZTP and border routing.",
    entitled=False,
    freshness_minutes=43200,
    operations=tariff_operations(),
)
