"""GTS connector manifest (src-gts)."""

from __future__ import annotations

from eurogas_nexus.domain.connectors.manifest import ConnectorManifest
from eurogas_nexus.domain.connectors.operations import tariff_operations

MANIFEST = ConnectorManifest(
    source_id="src-gts",
    system="GTS",
    category="tariff",
    datasets=("netherlands-transmission-tariffs", "entry-exit"),
    description="Gasunie Transport Services Dutch transmission tariff references.",
    entitled=False,
    freshness_minutes=43200,
    operations=tariff_operations(),
)
