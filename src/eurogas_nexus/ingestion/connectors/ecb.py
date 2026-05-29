"""ECB FX reference rates connector shell (no live execution)."""

from eurogas_nexus.ingestion.connectors.base import ConnectorMetadata, MockConnector

ECB_METADATA = ConnectorMetadata(
    source_system="ECB",
    datasets=("fx-reference-rates",),
    entitlement_required=False,
    polling_supported=False,
    request_mode_supported=True,
    freshness_expectation_minutes=1440,
    export_restricted=False,
    research_only=True,
)


class EcbConnector(MockConnector):
    """Mock ECB FX connector — returns empty payloads by default."""

    def __init__(self) -> None:
        super().__init__("ECB", ("fx-reference-rates",))
        self._metadata = ECB_METADATA
