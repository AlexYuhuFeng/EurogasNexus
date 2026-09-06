"""Canonical energy ontology for research datasets.

The ontology is deliberately lightweight and executable: concepts are typed
domain schemas and controlled vocabularies, not an unused RDF mirror. RDF/graph
serialization may be an adapter later; semantics must live here first.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

ONTOLOGY_SCHEMA_VERSION = "energy-ontology/v1"


class CanonicalEntityType(StrEnum):
    """Canonical entity classes used by series/features/datasets."""

    MARKET_HUB = "market_hub"
    MARKET_AREA = "market_area"
    MARKET_VENUE = "market_venue"
    DELIVERY_PRODUCT = "delivery_product"
    CONTRACT_PRODUCT = "contract_product"
    PRICE_BASIS = "price_basis"
    NETWORK_NODE = "network_node"
    PIPELINE = "pipeline"
    INTERCONNECTOR = "interconnector"
    INFRASTRUCTURE_ASSET = "infrastructure_asset"
    LNG_TERMINAL = "lng_terminal"
    STORAGE_FACILITY = "storage_facility"
    PRODUCTION_SOURCE = "production_source"
    PORTFOLIO = "portfolio"
    RESOURCE = "resource"
    COMMERCIAL_TERM = "commercial_term"
    CONTRACT = "contract"
    ROUTE = "route"
    ROUTE_SEGMENT = "route_segment"
    TARIFF = "tariff"
    ACCESS_RIGHT = "access_right"
    SOURCE = "source"
    TRANSFORMATION = "transformation"
    STRATEGY = "strategy"
    STRATEGY_VERSION = "strategy_version"
    TARGET_DEFINITION = "target_definition"
    FEATURE_DEFINITION = "feature_definition"
    DATASET_SPEC = "dataset_spec"
    DATASET_SNAPSHOT = "dataset_snapshot"


@dataclass(frozen=True)
class OntologyConcept:
    """One named concept in the canonical energy ontology."""

    concept_id: str
    entity_type: CanonicalEntityType
    name: str
    description: str
    relationships: tuple[tuple[str, str, str], ...] = ()

    def triplets(self) -> list[dict[str, str]]:
        return [
            {
                "subject": self.concept_id,
                "predicate": predicate,
                "object": target,
            }
            for predicate, target, _ in self.relationships
        ]


@dataclass(frozen=True)
class OntologyVersion:
    """A versioned ontology snapshot carried by dataset metadata."""

    version: str = ONTOLOGY_SCHEMA_VERSION
    concepts: tuple[OntologyConcept, ...] = field(default_factory=tuple)

    def concept_ids(self) -> list[str]:
        return [concept.concept_id for concept in self.concepts]


def canonical_entity_id(entity_type: CanonicalEntityType | str, code: str) -> str:
    """Derive a stable canonical entity identifier.

    Example: ``canonical_entity_id("market_hub", "NBP")`` ->
    ``ent:market_hub:NBP``. Identity is not display-name matching.
    """

    normalized_type = str(entity_type).strip().lower().replace(" ", "_")
    normalized_code = str(code).strip().upper().replace(" ", "_")
    if not normalized_code:
        raise ValueError("canonical entity code is required")
    return f"ent:{normalized_type}:{normalized_code}"


CORE_CONCEPTS: tuple[OntologyConcept, ...] = (
    OntologyConcept(
        "MarketHub",
        CanonicalEntityType.MARKET_HUB,
        "Market hub",
        "A canonical gas trading hub such as TTF, NBP, THE, PEG, ZTP, or PSV.",
        (
            ("belongs_to", "MarketArea", "each hub belongs to one market area"),
            ("traded_at", "MarketVenue", "hub prices are observed at venues"),
        ),
    ),
    OntologyConcept(
        "MarketArea",
        CanonicalEntityType.MARKET_AREA,
        "Market area",
        "A balancing/entry market area.",
    ),
    OntologyConcept(
        "MarketVenue",
        CanonicalEntityType.MARKET_VENUE,
        "Market venue",
        "Exchange, broker screen, or assessment venue. A venue is not a hub.",
    ),
    OntologyConcept(
        "DeliveryProduct",
        CanonicalEntityType.DELIVERY_PRODUCT,
        "Delivery product",
        "Tenor/delivery identity: within-day, day-ahead, weekend, month-ahead.",
    ),
    OntologyConcept(
        "PriceObservation",
        CanonicalEntityType.PRICE_BASIS,
        "Price observation",
        "Observed price for one entity/product/unit/source at one time.",
    ),
    OntologyConcept(
        "NetworkNode",
        CanonicalEntityType.NETWORK_NODE,
        "Network node",
        "Physical or reference network point.",
    ),
    OntologyConcept(
        "Interconnector",
        CanonicalEntityType.INTERCONNECTOR,
        "Interconnector",
        "Cross-border pipeline with direction and access semantics.",
    ),
    OntologyConcept(
        "Resource",
        CanonicalEntityType.RESOURCE,
        "Resource",
        "Commercial supply/resource term in a portfolio.",
        (
            ("located_at", "NetworkNode", "resource delivery point"),
            ("priced_by", "PriceBasis", "resource pricing basis"),
        ),
    ),
    OntologyConcept(
        "Route",
        CanonicalEntityType.ROUTE,
        "Route",
        "Route from a resource/start point to a target market.",
        (
            ("originates_at", "Resource", "route starts at a resource/point"),
            ("terminates_at", "MarketHub", "route ends at a hub"),
            ("uses_segment", "RouteSegment", "route consists of segments"),
        ),
    ),
    OntologyConcept(
        "Strategy",
        CanonicalEntityType.STRATEGY,
        "Strategy",
        "Long-lived research identity with immutable versions.",
        (
            ("observes", "FeatureDefinition", "strategy reads features"),
            ("requires", "DataRequirement", "strategy declares data needs"),
        ),
    ),
    OntologyConcept(
        "DatasetSnapshot",
        CanonicalEntityType.DATASET_SNAPSHOT,
        "Dataset snapshot",
        "Immutable materialization of a DatasetSpec at one source cutoff.",
        (
            ("derived_from", "DatasetSpec", "snapshot materializes a spec"),
            ("uses_ontology", "OntologyVersion", "snapshot records ontology version"),
        ),
    ),
)
