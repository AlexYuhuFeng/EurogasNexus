"""Typed relations — the L1 declarative relationship model.

Each relation is a (subject, predicate, object) triple with cardinality, so the
graph of the domain is machine-readable rather than prose.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Relation:
    """A typed relationship between two concepts.

    类型化关系三元组 (subject, predicate, object) 及基数约束，供本体
    图与校验工具机器可读地消费，而不是散落在文档散文里。

    Attributes:
        subject: Source concept id.
        predicate: Relationship name (e.g. ``feeds``, ``requires``).
        object: Target concept id.
        cardinality: Cardinality expression, e.g. ``"1"``, ``"0..1"``,
            ``"0..n"``.
        note: Optional clarifying note (e.g. additional participants).
    """

    subject: str  # concept_id
    predicate: str
    object: str  # concept_id
    cardinality: str = "0..n"  # e.g. "1", "0..1", "0..n"
    note: str = ""


RELATIONS: tuple[Relation, ...] = (
    Relation("UpstreamResourceContract", "feeds", "ResourcePool", "0..n"),
    Relation("ResourcePool", "allocates_to", "RouteCandidate", "0..n"),
    Relation(
        "RouteCandidate",
        "requires",
        "TsoTariff",
        "0..n",
        "plus CapacityProfile and CompanyTsoAccess",
    ),
    Relation("RouteCandidate", "consumes", "MarketObservation", "0..n"),
    Relation("RouteCandidate", "consumes", "LiveMarketMark", "0..n"),
    Relation("VirtualHub", "is_price_anchor_of", "MarketArea", "1"),
    Relation("MarketArea", "contains", "ReferenceNode", "0..n"),
    Relation("InterconnectionPoint", "links", "MarketArea", "2"),
    Relation("ReferenceNode", "connects_via", "ReferenceEdge", "0..n"),
    Relation("LngRegasScenario", "requires", "StorageFacility", "0..1"),
    Relation("StorageFacility", "injects_into", "MarketArea", "0..1"),
    Relation("StorageFacility", "withdraws_into", "MarketArea", "0..1"),
    Relation("Nomination", "has", "ReferenceNode", "1"),
    Relation("StrategyRun", "evaluates", "ResourcePool", "0..1"),
    Relation("StrategyRun", "consumes", "MarketObservation", "0..n"),
    Relation("EntitlementDecision", "governs", "MarketObservation", "0..n"),
    Relation("WeatherObservation", "drives", "MarketArea", "0..n"),
)
