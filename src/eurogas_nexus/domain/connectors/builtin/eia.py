"""EIA connector manifest (src-eia)."""

from __future__ import annotations

from eurogas_nexus.domain.connectors.manifest import ConnectorManifest, ProviderCredentialSpec
from eurogas_nexus.domain.connectors.operations import rate_operations
from eurogas_nexus.domain.dataops.contracts import DatasetFreshness

MANIFEST = ConnectorManifest(
    source_id="src-eia",
    system="EIA",
    category="price",
    datasets=("henry-hub-spot",),
    description="US EIA open data: Henry Hub daily spot price (public domain; free API key). "
    "Reference for US LNG export economics.",
    entitled=False,
    freshness_minutes=1440,
    # Henry Hub spot through scripts/ops/ingest_eia.py, after EIA's daily update.
    operations={
        **rate_operations("17:10", "America/New_York"),
        "adapter_version": "eia-open-data-v2",
    },
    credentials=(ProviderCredentialSpec("EIA", "US EIA open data", ("EIA_API_KEY",)),),
    # The stored datasets and how old each one's newest period may be (FRESH-01).
    dataset_freshness=(
        DatasetFreshness(
            "Henry Hub (EIA)",
            264,
            792,
            "EIA updates Henry Hub spot weekly to daily, about a week behind.",
        ),
    ),
)
