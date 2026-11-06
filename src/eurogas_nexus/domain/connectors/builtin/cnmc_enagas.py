"""CNMCEnagas connector manifest (src-cnmc-enagas)."""

from __future__ import annotations

from eurogas_nexus.domain.connectors.manifest import ConnectorManifest
from eurogas_nexus.domain.connectors.operations import tariff_operations

MANIFEST = ConnectorManifest(
    source_id="src-cnmc-enagas",
    system="CNMCEnagas",
    category="tariff",
    datasets=("spain-access-tolls", "transmission", "regasification"),
    description="Spanish CNMC/Enagas gas access toll and tariff references.",
    entitled=False,
    freshness_minutes=43200,
    operations=tariff_operations(),
)
