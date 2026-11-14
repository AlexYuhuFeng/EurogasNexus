"""ICE_ENDEX connector manifest (src-ice-endex)."""

from __future__ import annotations

from eurogas_nexus.domain.connectors.manifest import ConnectorManifest
from eurogas_nexus.domain.dataops.contracts import FreshnessPolicy

MANIFEST = ConnectorManifest(
    source_id="src-ice-endex",
    system="ICE_ENDEX",
    category="price",
    datasets=("ttf-nbp-futures", "eua-uka-futures", "api2-coal-futures", "settlements"),
    description="ICE Endex futures settlements: TTF and NBP gas, EUA and UKA carbon, API2 "
    "Rotterdam coal and power. Licensed; imported from the customer's ICE "
    "Report Center export until a connector is licensed.",
    entitled=True,
    freshness_minutes=1440,
    # Declared, not defaulted (FRESH-01); the values the registry default gave.
    operations={"freshness_policy": FreshnessPolicy(1440, 2880, 4320)},
)
