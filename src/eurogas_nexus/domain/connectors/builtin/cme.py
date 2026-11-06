"""CME connector manifest (src-cme)."""

from __future__ import annotations

from eurogas_nexus.domain.connectors.manifest import ConnectorManifest

MANIFEST = ConnectorManifest(
    source_id="src-cme",
    system="CME",
    category="price",
    datasets=("henry-hub-futures", "settlements"),
    description="CME NYMEX Henry Hub futures settlements. Licensed (CME DataMine).",
    entitled=True,
    freshness_minutes=1440,
)
