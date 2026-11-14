"""ECB_ESTR connector manifest (src-ecb-estr)."""

from __future__ import annotations

from eurogas_nexus.domain.connectors.manifest import ConnectorManifest
from eurogas_nexus.domain.connectors.operations import rate_operations
from eurogas_nexus.domain.dataops.contracts import DatasetFreshness

MANIFEST = ConnectorManifest(
    source_id="src-ecb-estr",
    system="ECB_ESTR",
    category="rates",
    datasets=("estr",),
    description="ECB euro short-term rate (€STR) from the ECB Data Portal: financing in EUR.",
    entitled=False,
    freshness_minutes=1440,
    operations=rate_operations("08:15", "Europe/Berlin"),
    # The stored datasets and how old each one's newest period may be (FRESH-01).
    dataset_freshness=(
        DatasetFreshness(
            "€STR (ECB)",
            120,
            360,
            "€STR for day D published 08:00 CET on the next TARGET business day.",
        ),
    ),
)
