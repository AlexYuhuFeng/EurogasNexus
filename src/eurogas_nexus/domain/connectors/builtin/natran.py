"""NaTran connector manifest (src-natran)."""

from __future__ import annotations

from eurogas_nexus.domain.connectors.manifest import ConnectorManifest
from eurogas_nexus.domain.connectors.operations import tariff_operations

MANIFEST = ConnectorManifest(
    source_id="src-natran",
    system="NaTran",
    category="tariff",
    datasets=("france-transmission-tariffs", "entry-exit", "peg"),
    description="French transmission tariff references for NaTran/GRTgaz/Terega context.",
    entitled=False,
    freshness_minutes=43200,
    operations=tariff_operations(),
)
