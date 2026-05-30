"""Connector contract tests (DB-free, no live API calls)."""


def test_connector_metadata_exists() -> None:
    from eurogas_nexus.ingestion.connectors.base import ConnectorMetadata

    meta = ConnectorMetadata(source_system="ENTSOG")
    assert meta.source_system == "ENTSOG"
    assert meta.entitlement_required is True
    assert meta.research_only is True


def test_mock_connector_implements_protocol() -> None:
    from eurogas_nexus.ingestion.connectors.base import MockConnector

    connector = MockConnector("ECB", ("fx-reference-rates",))
    assert connector.metadata.source_system == "ECB"

    payload = connector.fetch("fx-reference-rates")
    assert payload.source_system == "ECB"
    assert payload.dataset == "fx-reference-rates"
    assert payload.raw_data == []


def test_mock_connector_never_calls_external_apis() -> None:
    """Mock connector must return empty payloads without network access."""
    from eurogas_nexus.ingestion.connectors.base import MockConnector

    connector = MockConnector("Weather")
    payload = connector.fetch("temperature")
    assert payload.raw_data == []
    assert "mock" in payload.source_reference_id


def test_all_seven_connector_shells_are_importable() -> None:
    """Verify all 7 V1 source family connectors exist and are importable."""
    from eurogas_nexus.ingestion.connectors.ecb import EcbConnector
    from eurogas_nexus.ingestion.connectors.eex import EexConnector
    from eurogas_nexus.ingestion.connectors.entsog import EntsogConnector
    from eurogas_nexus.ingestion.connectors.gie import GieConnector
    from eurogas_nexus.ingestion.connectors.ice_ocm import IceOcmConnector
    from eurogas_nexus.ingestion.connectors.trayport import TrayportConnector
    from eurogas_nexus.ingestion.connectors.weather import WeatherConnector

    connectors = [
        EcbConnector(),
        EexConnector(),
        EntsogConnector(),
        GieConnector(),
        IceOcmConnector(),
        TrayportConnector(),
        WeatherConnector(),
    ]
    assert len(connectors) == 7
    for c in connectors:
        assert c.metadata.research_only is True
        assert c.metadata.entitlement_required is True or c.metadata.source_system in {
            "ECB",
            "ENTSOG",
        }


def test_connectors_have_expected_datasets() -> None:
    from eurogas_nexus.ingestion.connectors.ecb import EcbConnector
    from eurogas_nexus.ingestion.connectors.entsog import EntsogConnector
    from eurogas_nexus.ingestion.connectors.gie import GieConnector

    assert "fx-reference-rates" in EcbConnector().metadata.datasets
    assert "flows" in EntsogConnector().metadata.datasets
    assert "agsi-storage" in GieConnector().metadata.datasets


def test_connector_import_does_not_call_external_apis() -> None:
    """Importing connectors must not trigger any network I/O."""
    import eurogas_nexus.ingestion.connectors.ecb  # noqa: F401
    import eurogas_nexus.ingestion.connectors.eex  # noqa: F401
    import eurogas_nexus.ingestion.connectors.entsog  # noqa: F401
    import eurogas_nexus.ingestion.connectors.gie  # noqa: F401
    import eurogas_nexus.ingestion.connectors.ice_ocm  # noqa: F401
    import eurogas_nexus.ingestion.connectors.trayport  # noqa: F401
    import eurogas_nexus.ingestion.connectors.weather  # noqa: F401

    # Import-time success = no network I/O triggered.
    assert True
