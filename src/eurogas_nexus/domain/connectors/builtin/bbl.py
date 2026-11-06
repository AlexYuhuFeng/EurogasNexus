"""BBL connector manifest (src-bbl)."""

from __future__ import annotations

from eurogas_nexus.domain.connectors.manifest import ConnectorManifest
from eurogas_nexus.domain.connectors.operations import tariff_operations

MANIFEST = ConnectorManifest(
    source_id="src-bbl",
    system="BBL",
    category="tariff",
    datasets=("interconnector-tariffs", "forward-flow", "reverse-flow"),
    description="BBL Company public interconnector capacity tariff references.",
    entitled=False,
    freshness_minutes=43200,
    operations=tariff_operations(),
)
