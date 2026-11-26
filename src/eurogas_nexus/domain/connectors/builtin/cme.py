"""CME connector manifest (src-cme)."""

from __future__ import annotations

from eurogas_nexus.domain.connectors.manifest import ConnectorManifest
from eurogas_nexus.domain.dataops.contracts import FreshnessPolicy

MANIFEST = ConnectorManifest(
    source_id="src-cme",
    system="CME",
    category="price",
    datasets=("henry-hub-futures", "settlements", "gas-option-settlements"),
    description="CME NYMEX Henry Hub futures settlements and gas option settlements. "
    "Licensed (CME DataMine).",
    entitled=True,
    freshness_minutes=1440,
    # Declared, not defaulted (FRESH-01); the values the registry default gave.
    operations={"freshness_policy": FreshnessPolicy(1440, 2880, 4320)},
)
