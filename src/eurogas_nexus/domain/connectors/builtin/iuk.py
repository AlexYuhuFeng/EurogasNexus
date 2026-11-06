"""IUK connector manifest (src-iuk)."""

from __future__ import annotations

from eurogas_nexus.domain.connectors.manifest import ConnectorManifest
from eurogas_nexus.domain.connectors.operations import tariff_operations

MANIFEST = ConnectorManifest(
    source_id="src-iuk",
    system="IUK",
    category="tariff",
    datasets=("interconnector-tariffs", "bacton", "zeebrugge"),
    description="Interconnector UK public charging statement and capacity tariff references.",
    entitled=False,
    freshness_minutes=43200,
    operations=tariff_operations(),
)
