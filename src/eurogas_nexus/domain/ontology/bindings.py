"""Concept → PostgreSQL table bindings (seed ↔ binding discipline).

Each entry maps a typed concept to the runtime table that stores its data
instances. Concepts without a direct table (derived aggregates such as
``ResourcePool``, abstract taxonomies such as ``MarketArea``/``Nomination``,
and enum-like concepts) are intentionally absent here — they are views over the
bound tables, not separate sources of truth.
"""

CONCEPT_TABLE_BINDINGS: dict[str, str] = {
    "UpstreamResourceContract": "upstream_resource_contracts",
    "VirtualHub": "reference_market_hubs",
    "ReferenceNode": "reference_nodes",
    "ReferenceEdge": "reference_edges",
    "ReferenceFacility": "reference_facilities",
    "FlowObservation": "flow_observations",
    "CapacityProfile": "capacity_profiles",
    "TsoTariff": "tso_tariffs",
    "CompanyTsoAccess": "company_tso_access",
    "RouteCandidate": "route_candidates",
    "MarketObservation": "market_observations",
    "LiveMarketMark": "live_market_marks",
    "MarketQuote": "market_quotes",
    "FxObservation": "fx_observations",
    "StrategyDefinition": "strategy_definitions",
    "StrategyRun": "strategy_runs",
    "StrategyAllocationTarget": "strategy_allocation_targets",
    "EntitlementDecision": "entitlement_decisions",
    "GlossaryTerm": "glossary_terms",
    "GeneratedReport": "generated_reports",
}
