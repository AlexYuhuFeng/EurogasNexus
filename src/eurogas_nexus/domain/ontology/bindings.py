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


# Slot -> column alignment for every bound concept.
#
# Every slot of a bound concept must have an explicit entry; the integrity
# test in tests/unit/test_ontology_binding_integrity.py enforces that each
# entry resolves to a real column on the bound table. Targets may be:
#   - a column name, e.g. "delivery_point_name"
#   - a JSON path, e.g. "metadata_json.hub" (base column must exist)
#   - "" (empty): deliberately derived/computed, not column-backed
#
# This map is the machine-checkable version of the audit's "~13/20 bindings
# inconsistent" finding: keeping it exhaustive turns drift into test failures.
CONCEPT_SLOT_COLUMN_MAPS: dict[str, dict[str, str]] = {
    "UpstreamResourceContract": {
        "delivery_point": "delivery_point_name",
        "gas_year": "gas_year",
        "available_quantity_mwh_per_day": "delivery_quantity_mwh_per_day",
        "all_in_cost_gbp_mwh": "contract_price_gbp_mwh",
        "settlement_frequency": "settlement_frequency",
        # delivery_mode is derived from resource_type at composition time.
        "delivery_mode": "resource_type",
    },
    "VirtualHub": {
        "hub": "hub_code",
        "market_area": "market_area",
        "valid_from": "valid_from_utc",
        "valid_to": "valid_to_utc",
        "superseded_by": "superseded_by_hub_id",
    },
    "ReferenceNode": {
        "node_type": "node_type",
        "country": "country",
        "lat": "lat",
        "lon": "lon",
    },
    "ReferenceEdge": {
        "from_node": "from_node_id",
        "to_node": "to_node_id",
        "edge_type": "edge_type",
    },
    "ReferenceFacility": {
        "facility_type": "facility_type",
        "country": "country",
    },
    "FlowObservation": {
        "point": "point_id",
        "kind": "kind",
        "direction": "direction",
        "flow_mcm_d": "flow_mcm_d",
        "source_system": "source_system",
        "freshness": "freshness",
    },
    "CapacityProfile": {
        "direction": "direction",
        "firmness": "firmness",
        "product": "capacity_product",
        "scope": "capacity_scope",
        "quantity_mwh_per_day": "capacity_mwh_per_day",
        "valid_from": "valid_from_utc",
        "valid_to": "valid_to_utc",
    },
    "TsoTariff": {
        "point": "point_id",
        "direction": "direction",
        # charge_type is derived from the tariff document split.
        "charge_type": "",
        "value": "tariff_value",
        "currency": "currency",
    },
    "CompanyTsoAccess": {
        "tso": "tso",
        # point is represented by market_area at access level.
        "point": "market_area",
    },
    "RouteCandidate": {
        "source_point": "start_point_name",
        "destination_market": "target_point_name",
        "required_tso_access": "required_tso_access",
    },
    "MarketObservation": {
        "hub": "metadata_json.hub",
        "product_tenor": "metadata_json.tenor",
        "product_kind": "metadata_json.product_kind",
        "price_type": "metadata_json.price_type",
        "price": "price",
        "currency": "currency",
        "unit": "unit",
        "source_system": "source_system",
        "source_reference": "source_reference",
        "freshness": "freshness",
        "quality_score": "quality_score",
        # entitlement_scope is evaluated by governance, not stored per row.
        "entitlement_scope": "",
    },
    "LiveMarketMark": {
        "venue": "venue",
        "hub": "hub",
        "product_tenor": "product",
        "bid_gbp_mwh": "bid_gbp_mwh",
        "ask_gbp_mwh": "ask_gbp_mwh",
        "last_gbp_mwh": "last_gbp_mwh",
    },
    "MarketQuote": {
        "bid": "bid_price",
        "ask": "ask_price",
        # size is split across bid/ask quantity columns.
        "size_mwh": "bid_quantity_mwh",
    },
    "FxObservation": {
        "pair": "pair",
        "rate": "rate",
        "value_date": "value_date",
    },
    "StrategyDefinition": {
        "components": "components",
        "risk_control": "risk_control",
    },
    "StrategyRun": {
        "strategy": "strategy_id",
        "mode": "run_mode",
        # paper_pnl_gbp lives inside the result snapshot JSON.
        "paper_pnl_gbp": "result_snapshot",
        "status": "status",
    },
    "StrategyAllocationTarget": {
        "market_bucket": "market_bucket",
        "target_allocation_pct": "target_allocation_pct",
        "target_quantity_mwh_per_day": "target_quantity_mwh_per_day",
    },
    "EntitlementDecision": {
        "scope": "scope",
        "allowed": "granted",
        "reason": "reason",
    },
    "GlossaryTerm": {
        "term": "term",
        "category": "category",
        "concept_id": "concept_id",
        "definition_en": "definition_en",
        "definition_zh_cn": "definition_zh_cn",
    },
    "GeneratedReport": {
        "report_id": "report_id",
        "title": "title",
    },
}
