"""Trayport_Sim connector manifest (src-trayport-sim)."""

from __future__ import annotations

from eurogas_nexus.domain.connectors.manifest import ConnectorManifest

MANIFEST = ConnectorManifest(
    source_id="src-trayport-sim",
    system="Trayport_Sim",
    category="price",
    datasets=("broker-screens", "within-day", "day-ahead", "simulated"),
    description="Trayport-shaped simulated broker-screen marks injected through "
    "the canonical runtime DB path at a realtime worker cadence.",
    entitled=False,
    freshness_minutes=1,
)
