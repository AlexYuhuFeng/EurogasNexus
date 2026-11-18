"""LNG terminal tariff register connector manifest (src-lng-terminal-tariffs, CP-11)."""

from __future__ import annotations

from eurogas_nexus.domain.connectors.manifest import ConnectorManifest
from eurogas_nexus.domain.connectors.operations import tariff_operations

MANIFEST = ConnectorManifest(
    source_id="src-lng-terminal-tariffs",
    system="LNG_TERMINAL_TARIFFS",
    category="tariff",
    datasets=("regas-slot-tariffs", "cargo-class-tariffs", "gas-in-kind", "slot-terms"),
    description=(
        "Regulated LNG terminal tariffs and slot terms as the operators publish them (Fluxys "
        "LNG, Elengy, DET), versioned by document and reviewed before use. Read only for "
        "operators whose reuse permission the firm has recorded."
    ),
    entitled=False,
    freshness_minutes=43200,
    # Read by scripts/ops/refresh_lng_terminal_tariffs.py once an operator is permitted; a
    # register an operator keeps, so no freshness alarm before any operator is permitted.
    integration="manual_register",
    operations=tariff_operations(),
)
