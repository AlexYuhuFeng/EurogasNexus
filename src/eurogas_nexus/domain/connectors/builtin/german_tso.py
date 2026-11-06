"""GermanTSO connector manifest (src-german-tso)."""

from __future__ import annotations

from eurogas_nexus.domain.connectors.manifest import ConnectorManifest
from eurogas_nexus.domain.connectors.operations import tariff_operations

MANIFEST = ConnectorManifest(
    source_id="src-german-tso",
    system="GermanTSO",
    category="tariff",
    datasets=("germany-transmission-tariffs", "the-market-area", "entry-exit"),
    description="German gas transmission tariff references for THE market-area routing.",
    entitled=False,
    freshness_minutes=43200,
    operations=tariff_operations(),
)
