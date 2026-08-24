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
    guardrails = GUARDRAILS
    bindings = CONCEPT_TABLE_BINDINGS
    actions = ActionKind
    forbidden_actions = ForbiddenAction

    @property
    def constraints(self):
        """Lazily expose the computable-constraint registry.

        延迟导入：constraints 模块会经 domain.constraints.access 反向依赖
        本包 vocabulary，此处若急切导入会造成包初始化环（见 __getattr__）。
        """

        from eurogas_nexus.domain.ontology.constraints import CONSTRAINTS

        return CONSTRAINTS


ONTOLOGY = Ontology()


def __getattr__(name: str):
    """Lazily expose the computable-constraint registry.

    ``ontology.constraints`` imports ``domain.constraints.access``, which
    itself imports ``ontology.vocabulary``; an eager import here would create
    a package-initialization cycle (access.py partially initialized). Deferring
    the import keeps ``from eurogas_nexus.domain.ontology import CONSTRAINTS``
    working via PEP 562.
    """

    if name in {"CONSTRAINTS", "Constraint"}:
        from eurogas_nexus.domain.ontology.constraints import (
            CONSTRAINTS,
            Constraint,
        )

        return {"CONSTRAINTS": CONSTRAINTS, "Constraint": Constraint}[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


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
