"""ENTSOG transparency data connector shell (no live execution)."""

from eurogas_nexus.ingestion.connectors.base import ConnectorMetadata, MockConnector

ENTSOG_METADATA = ConnectorMetadata(
    source_system="ENTSOG",
    datasets=("flows", "capacity", "outages", "interconnection-points"),
    entitlement_required=False,
    polling_supported=True,
    request_mode_supported=True,
    freshness_expectation_minutes=60,
    export_restricted=True,
    research_only=True,
)


class EntsogConnector(MockConnector):
    """Mock ENTSOG connector — returns empty payloads by default."""

    def __init__(self) -> None:
        super().__init__("ENTSOG", ENTSOG_METADATA.datasets)
        self._metadata = ENTSOG_METADATA
