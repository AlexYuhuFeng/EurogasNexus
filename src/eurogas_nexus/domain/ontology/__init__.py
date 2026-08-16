"""European natural-gas domain ontology — the rigorous, typed skeleton.

This package is the single authoritative definition of the domain's:

  - controlled vocabulary (``vocabulary.py``)
  - action taxonomy (``actions.py``)
  - typed concepts (``concepts.py``)
  - typed relations (``relations.py``)
  - computable constraints (``constraints.py``, delegating to ``domain.constraints``)

Discipline (per the ontology methodology):

  - This is a *contract* (versioned code), not a runtime data store.
  - PostgreSQL remains the runtime truth for **data instances**; this package is
    the truth for **semantic structure** (what a hub/route/constraint means).
  - The human-readable glossary stays a separate display layer and must not be
    treated as the correctness backbone.
"""

from eurogas_nexus.domain.ontology.actions import ActionKind, ForbiddenAction
from eurogas_nexus.domain.ontology.bindings import CONCEPT_TABLE_BINDINGS
from eurogas_nexus.domain.ontology.concepts import CONCEPTS, Concept, Slot
from eurogas_nexus.domain.ontology.constraints import CONSTRAINTS, Constraint
from eurogas_nexus.domain.ontology.relations import RELATIONS, Relation
from eurogas_nexus.domain.ontology.vocabulary import (
    BusinessModel,
    CandidateAction,
    CapacityProduct,
    CapacityScope,
    CostComponentType,
    Currency,
    DeliveryMode,
    EdgeType,
    FacilityType,
    Firmness,
    FlowKind,
    MarketHub,
    NodeType,
    PointType,
    PriceDataKind,
    PriceType,
    ProductKind,
    ProductTenor,
    ReviewDecisionValue,
    ReviewEntityType,
    SourceResourceType,
    StrategyComponentType,
    StrategyRunMode,
    TariffDirection,
    TariffStatus,
)

# L4 institutional guardrails (policy boundaries, not computable constraints).
GUARDRAILS: tuple[str, ...] = (
    "PostgreSQL is runtime source of truth",
    "clients access data through API/SDK only",
    "LLM providers are not source of truth",
    "outputs are decision support and human review required",
    "no order entry, routing, execution, trade capture, or nomination submission",
)


class Ontology:
    """Read-only namespace exposing the domain ontology as one object."""

    concepts = CONCEPTS
    relations = RELATIONS
    constraints = CONSTRAINTS
    guardrails = GUARDRAILS
    bindings = CONCEPT_TABLE_BINDINGS
    actions = ActionKind
    forbidden_actions = ForbiddenAction


ONTOLOGY = Ontology()

__all__ = [
    "ONTOLOGY",
    "ActionKind",
    "ForbiddenAction",
    "Concept",
    "Slot",
    "Relation",
    "Constraint",
    "CONCEPTS",
    "RELATIONS",
    "CONSTRAINTS",
    "GUARDRAILS",
    "CONCEPT_TABLE_BINDINGS",
    "MarketHub",
    "NodeType",
    "EdgeType",
    "FacilityType",
    "CandidateAction",
    "ProductTenor",
    "ProductKind",
    "PriceType",
    "PriceDataKind",
    "CapacityProduct",
    "CapacityScope",
    "Firmness",
    "FlowKind",
    "DeliveryMode",
    "Currency",
    "TariffStatus",
    "TariffDirection",
    "PointType",
    "BusinessModel",
    "SourceResourceType",
    "CostComponentType",
    "StrategyRunMode",
    "StrategyComponentType",
    "ReviewDecisionValue",
    "ReviewEntityType",
]
