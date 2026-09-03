"""Connector contracts and shells for supported source families."""

from eurogas_nexus.ingestion.connectors.base import Connector, MockConnector
from eurogas_nexus.ingestion.connectors.cost_source import (
    COST_SOURCE_SKELETONS,
    CostSourceConnector,
    JsonCostObservationConnector,
    lng_auction_skeleton,
    lng_slot_skeleton,
    secondary_transfer_skeleton,
    tso_tariff_skeleton,
)

__all__ = [
    "COST_SOURCE_SKELETONS",
    "Connector",
    "CostSourceConnector",
    "JsonCostObservationConnector",
    "MockConnector",
    "lng_auction_skeleton",
    "lng_slot_skeleton",
    "secondary_transfer_skeleton",
    "tso_tariff_skeleton",
]
