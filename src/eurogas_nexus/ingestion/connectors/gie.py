"""GIE AGSI/ALSI storage and LNG connector shell (no live execution)."""

from eurogas_nexus.ingestion.connectors.base import ConnectorMetadata, MockConnector

GIE_METADATA = ConnectorMetadata(
    source_system="GIE",
    datasets=("agsi-storage", "alsi-lng"),
    entitlement_required=True,
    polling_supported=True,
    request_mode_supported=True,
    freshness_expectation_minutes=60,
    export_restricted=True,
    research_only=True,
)


class GieConnector(MockConnector):
    """Mock GIE connector — returns empty payloads by default."""

    def __init__(self) -> None:
        super().__init__("GIE", GIE_METADATA.datasets)
        self._metadata = GIE_METADATA
