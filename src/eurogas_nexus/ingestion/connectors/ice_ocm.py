"""ICE OCM market data connector shell (no live execution)."""

from eurogas_nexus.ingestion.connectors.base import ConnectorMetadata, MockConnector

ICE_OCM_METADATA = ConnectorMetadata(
    source_system="ICE_OCM",
    datasets=("within-day", "day-ahead", "prompt"),
    entitlement_required=True,
    polling_supported=True,
    request_mode_supported=True,
    freshness_expectation_minutes=1,
    export_restricted=True,
    research_only=True,
)


class IceOcmConnector(MockConnector):
    """Entitlement-safe ICE OCM shell; no provider call occurs until configured."""

    def __init__(self) -> None:
        super().__init__("ICE_OCM", ICE_OCM_METADATA.datasets)
        self._metadata = ICE_OCM_METADATA
