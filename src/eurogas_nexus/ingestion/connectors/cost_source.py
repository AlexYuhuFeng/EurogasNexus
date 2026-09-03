"""Cost-source connector framework for TSO tariffs and LNG regas slots.

Real connectors implement ``fetch_cost_observations``. Skeleton connectors
return empty payloads until a source adapter is approved and credentialed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from eurogas_nexus.domain.economics.cost_observation import CostObservation
from eurogas_nexus.ingestion.connectors.base import ConnectorMetadata


class CostSourceConnector(Protocol):
    """Protocol for connectors that produce cost observations."""

    @property
    def metadata(self) -> ConnectorMetadata:
        """Source metadata including freshness expectations."""

        ...

    def fetch_cost_observations(self) -> tuple[CostObservation, ...]:
        """Fetch current cost observations (never mutates runtime rows)."""

        ...


@dataclass(frozen=True)
class SkeletonCostSourceConnector:
    """Skeleton TSO/LNG cost-source connector.

    It declares the source family and returns no observations until the real
    adapter is implemented and credentialed. This is the safe default for
    offline development and for uncredentialed production deployments.
    """

    source_system: str
    datasets: tuple[str, ...]
    freshness_expectation_minutes: int = 1440

    @property
    def metadata(self) -> ConnectorMetadata:
        """Metadata for the skeleton source."""

        return ConnectorMetadata(
            source_system=self.source_system,
            datasets=self.datasets,
            entitlement_required=True,
            freshness_expectation_minutes=self.freshness_expectation_minutes,
        )

    def fetch_cost_observations(self) -> tuple[CostObservation, ...]:
        """Return an empty observation set (skeleton source)."""

        return ()


def tso_tariff_skeleton() -> SkeletonCostSourceConnector:
    """Return a TSO tariff connector skeleton."""

    return SkeletonCostSourceConnector(
        source_system="TSO_TARIFFS",
        datasets=("published_tariffs",),
        freshness_expectation_minutes=1440,
    )


def lng_slot_skeleton() -> SkeletonCostSourceConnector:
    """Return an LNG regas slot connector skeleton."""

    return SkeletonCostSourceConnector(
        source_system="LNG_SLOTS",
        datasets=("terminal_tariffs", "slot_auctions"),
        freshness_expectation_minutes=1440,
    )


class JsonCostObservationConnector:
    """Machine-readable JSON cost-source connector.

    The source URL and HTTP getter are injected so production uses the bounded
    backend HTTP client while tests use a fake. The connector does not mutate
    runtime rows; it returns normalized domain observations.
    """

    def __init__(
        self,
        *,
        source_system: str,
        datasets: tuple[str, ...],
        url: str,
        http_get=None,
    ) -> None:
        self._source_system = source_system
        self._datasets = datasets
        self._url = url
        self._http_get = http_get

    @property
    def metadata(self) -> ConnectorMetadata:
        """Metadata for this machine-readable connector."""

        return ConnectorMetadata(
            source_system=self._source_system,
            datasets=self._datasets,
            entitlement_required=False,
            polling_supported=True,
            request_mode_supported=True,
            freshness_expectation_minutes=1440,
            export_restricted=False,
        )

    def fetch_cost_observations(self) -> tuple[CostObservation, ...]:
        """Fetch and normalize the configured JSON cost-observation feed."""

        if not self._url:
            return ()
        response = self._http_get(self._url)
        if getattr(response, "status_code", 200) != 200:
            return ()
        payload = response.json() if hasattr(response, "json") else response
        records = payload if isinstance(payload, list) else payload.get("items", [])
        observations = tuple(_cost_observation_from_json(record) for record in records)
        return tuple(observations)


def _cost_observation_from_json(record: dict) -> CostObservation:
    """Map a normalized JSON record to the domain cost observation."""

    return CostObservation(
        observation_id=str(record.get("observation_id") or record.get("id") or ""),
        scope_type=str(record.get("scope_type") or "ROUTE").upper(),
        scope_id=str(record.get("scope_id") or ""),
        observation_type=str(record.get("observation_type") or "TSO_PUBLISHED").upper(),
        value=float(record.get("value") or 0.0),
        currency=str(record.get("currency") or "EUR"),
        unit=str(record.get("unit") or "MWh"),
        direction=record.get("direction"),
        capacity_product=record.get("capacity_product"),
        firmness=record.get("firmness"),
        gas_year=record.get("gas_year"),
        effective_from_utc=str(record.get("effective_from_utc") or ""),
        effective_to_utc=record.get("effective_to_utc"),
        source_system=str(record.get("source_system") or "TSO_TARIFFS"),
        source_reference=str(record.get("source_reference") or ""),
        document_id=record.get("document_id"),
        entitlement_scope=tuple(record.get("entitlement_scope") or []),
        status=str(record.get("status") or "ACTIVE"),
        manual_review_required=bool(record.get("manual_review_required", True)),
        superseded_by=record.get("superseded_by"),
        created_at_utc=str(record.get("created_at_utc") or ""),
    )


def secondary_transfer_skeleton() -> SkeletonCostSourceConnector:
    """Return a secondary-capacity transfer connector skeleton."""

    return SkeletonCostSourceConnector(
        source_system="SECONDARY_TRANSFER",
        datasets=("secondary_capacity", "transfer_prices"),
        freshness_expectation_minutes=1440,
    )


def lng_auction_skeleton() -> SkeletonCostSourceConnector:
    """Return an LNG regas slot auction connector skeleton."""

    return SkeletonCostSourceConnector(
        source_system="LNG_AUCTIONS",
        datasets=("slot_auctions", "auction_clearing_prices"),
        freshness_expectation_minutes=1440,
    )


COST_SOURCE_SKELETONS = {
    "TSO_TARIFFS": tso_tariff_skeleton,
    "LNG_SLOTS": lng_slot_skeleton,
    "SECONDARY_TRANSFER": secondary_transfer_skeleton,
    "LNG_AUCTIONS": lng_auction_skeleton,
}
