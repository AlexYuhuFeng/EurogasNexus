"""Weather data connector shell (no live execution)."""

from eurogas_nexus.ingestion.connectors.base import ConnectorMetadata, MockConnector

WEATHER_METADATA = ConnectorMetadata(
    source_system="Weather",
    datasets=("temperature", "hdd", "cdd", "forecast"),
    entitlement_required=True,
    polling_supported=True,
    request_mode_supported=True,
    freshness_expectation_minutes=60,
    export_restricted=True,
    research_only=True,
)


class WeatherConnector(MockConnector):
    """Mock Weather connector — returns empty payloads by default."""

    def __init__(self) -> None:
        super().__init__("Weather", WEATHER_METADATA.datasets)
        self._metadata = WEATHER_METADATA
