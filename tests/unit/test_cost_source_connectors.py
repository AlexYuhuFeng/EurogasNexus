"""Cost-source connector skeleton tests."""

from eurogas_nexus.ingestion.connectors.cost_source import (
    JsonCostObservationConnector,
    lng_slot_skeleton,
    tso_tariff_skeleton,
)


def test_tso_tariff_skeleton_declares_metadata() -> None:
    connector = tso_tariff_skeleton()

    assert connector.metadata.source_system == "TSO_TARIFFS"
    assert "published_tariffs" in connector.metadata.datasets
    assert connector.metadata.entitlement_required is True


def test_lng_slot_skeleton_declares_metadata() -> None:
    connector = lng_slot_skeleton()

    assert connector.metadata.source_system == "LNG_SLOTS"
    assert "terminal_tariffs" in connector.metadata.datasets
    assert "slot_auctions" in connector.metadata.datasets


def test_skeletons_return_no_fabricated_observations() -> None:
    assert tso_tariff_skeleton().fetch_cost_observations() == ()
    assert lng_slot_skeleton().fetch_cost_observations() == ()

def test_json_connector_normalizes_public_feed() -> None:
    class Response:
        status_code = 200

        def json(self):
            return [
                {
                    "id": "cost-json-1",
                    "scope_type": "ROUTE",
                    "scope_id": "TTF-NBP",
                    "observation_type": "TSO_PUBLISHED",
                    "value": 1.23,
                    "currency": "EUR",
                    "unit": "MWh",
                    "effective_from_utc": "2026-01-01T00:00:00+00:00",
                    "source_system": "TSO_TARIFFS",
                    "source_reference": "https://example.test/tariff.json",
                }
            ]

    connector = JsonCostObservationConnector(
        source_system="TSO_TARIFFS",
        datasets=("published_tariffs",),
        url="https://example.test/tariff.json",
        http_get=lambda url: Response(),
    )

    observations = connector.fetch_cost_observations()

    assert len(observations) == 1
    assert observations[0].scope_type == "ROUTE"
    assert observations[0].value == 1.23

def test_extended_cost_source_skeletons_exist() -> None:
    from eurogas_nexus.ingestion.connectors.cost_source import (
        COST_SOURCE_SKELETONS,
        lng_auction_skeleton,
        secondary_transfer_skeleton,
    )

    assert secondary_transfer_skeleton().metadata.source_system == "SECONDARY_TRANSFER"
    assert lng_auction_skeleton().metadata.source_system == "LNG_AUCTIONS"
    assert set(COST_SOURCE_SKELETONS) >= {
        "TSO_TARIFFS",
        "LNG_SLOTS",
        "SECONDARY_TRANSFER",
        "LNG_AUCTIONS",
    }
