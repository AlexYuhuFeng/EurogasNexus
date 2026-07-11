"""Trayport market data connector shell (no live execution)."""

from eurogas_nexus.ingestion.connectors.base import ConnectorMetadata, MockConnector

TRAYPORT_METADATA = ConnectorMetadata(
    source_system="Trayport",
    datasets=("market-data",),
    entitlement_required=True,
    polling_supported=False,
    request_mode_supported=True,
    freshness_expectation_minutes=1,
    export_restricted=True,
    research_only=True,
)


class TrayportConnector(MockConnector):
    """Entitlement-safe Trayport shell; no provider call occurs until configured."""

    def __init__(self) -> None:
        super().__init__("Trayport", TRAYPORT_METADATA.datasets)
        self._metadata = TRAYPORT_METADATA
