"""EEX market data connector shell (no live execution)."""

from eurogas_nexus.ingestion.connectors.base import ConnectorMetadata, MockConnector

EEX_METADATA = ConnectorMetadata(
    source_system="EEX",
    datasets=("power-futures", "gas-futures", "spot", "settlement"),
    entitlement_required=True,
    polling_supported=False,
    request_mode_supported=True,
    freshness_expectation_minutes=15,
    export_restricted=True,
    research_only=True,
)


class EexConnector(MockConnector):
    """Mock EEX connector — returns empty payloads by default."""

    def __init__(self) -> None:
        super().__init__("EEX", EEX_METADATA.datasets)
        self._metadata = EEX_METADATA
