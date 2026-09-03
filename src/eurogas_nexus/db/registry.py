"""Required-table registry tied to Alembic migration revisions (import-safe)."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import MetaData, inspect
from sqlalchemy.engine import Engine

from eurogas_nexus.db.base import Base


@dataclass(frozen=True)
class RequiredTable:
    """A table that must exist after its associated migration is applied."""

    name: str
    introduced_in: str  # migration revision id


# Ordered by revision so operators can audit progressively.
REQUIRED_TABLES: tuple[RequiredTable, ...] = (
    RequiredTable(name="alembic_version", introduced_in="0001_m2_baseline"),
    RequiredTable(name="ingestion_runs", introduced_in="0002_m4_create_ingestion_runs"),
    RequiredTable(name="reference_nodes", introduced_in="0003_r3_reference_network"),
    RequiredTable(name="reference_edges", introduced_in="0003_r3_reference_network"),
    RequiredTable(name="reference_facilities", introduced_in="0003_r3_reference_network"),
    RequiredTable(name="reference_market_hubs", introduced_in="0003_r3_reference_network"),
    RequiredTable(
        name="reference_tso_access_points",
        introduced_in="0011_reference_source_lineage",
    ),
    RequiredTable(name="node_facility_mappings", introduced_in="0003_r3_reference_network"),
    RequiredTable(name="topology_market_mappings", introduced_in="0003_r3_reference_network"),
    RequiredTable(name="market_observations", introduced_in="0004_r16_observation_tables"),
    RequiredTable(name="market_quotes", introduced_in="0014_intraday_decision_feed"),
    RequiredTable(name="fx_observations", introduced_in="0006_route_cost_decision_support"),
    RequiredTable(name="flow_observations", introduced_in="0004_r16_observation_tables"),
    RequiredTable(
        name="capacity_observations",
        introduced_in="0012_entsog_capacity",
    ),
    RequiredTable(name="audit_events", introduced_in="0004_r16_observation_tables"),
    RequiredTable(name="entitlement_decisions", introduced_in="0004_r16_observation_tables"),
    RequiredTable(name="storage_observations", introduced_in="0005_public_source_credentials"),
    RequiredTable(name="lng_observations", introduced_in="0005_public_source_credentials"),
    RequiredTable(name="provider_credentials", introduced_in="0005_public_source_credentials"),
    RequiredTable(name="tso_tariffs", introduced_in="0006_route_cost_decision_support"),
    RequiredTable(
        name="upstream_resource_contracts",
        introduced_in="0006_route_cost_decision_support",
    ),
    RequiredTable(name="capacity_profiles", introduced_in="0006_route_cost_decision_support"),
    RequiredTable(name="route_candidates", introduced_in="0006_route_cost_decision_support"),
    RequiredTable(name="live_market_marks", introduced_in="0006_route_cost_decision_support"),
    RequiredTable(name="company_tso_access", introduced_in="0014_intraday_decision_feed"),
    RequiredTable(
        name="intraday_opportunities",
        introduced_in="0014_intraday_decision_feed",
    ),
    RequiredTable(
        name="monitoring_alerts",
        introduced_in="0015_llm_monitoring_alerts",
    ),
    RequiredTable(name="glossary_terms", introduced_in="0006_route_cost_decision_support"),
    RequiredTable(name="strategy_definitions", introduced_in="0007_strategy_lab_foundation"),
    RequiredTable(name="strategy_runs", introduced_in="0007_strategy_lab_foundation"),
    RequiredTable(name="strategy_allocation_targets", introduced_in="0007_strategy_lab_foundation"),
    RequiredTable(name="strategy_alerts", introduced_in="0007_strategy_lab_foundation"),
    RequiredTable(name="analysis_runs", introduced_in="0008_analysis_reporting"),
    RequiredTable(name="generated_reports", introduced_in="0008_analysis_reporting"),
    RequiredTable(name="review_decisions", introduced_in="0017_review_decisions"),
    RequiredTable(
        name="provider_certifications",
        introduced_in="0018_provider_certifications",
    ),
    RequiredTable(
        name="optimization_runs",
        introduced_in="0019_ontology_slots_optimization",
    ),
    RequiredTable(
        name="raw_payload_archives",
        introduced_in="0021_raw_payload_archives",
    ),
    RequiredTable(
        name="identity_principals",
        introduced_in="0022_identity_api_keys",
    ),
    RequiredTable(
        name="identity_api_keys",
        introduced_in="0022_identity_api_keys",
    ),
    RequiredTable(
        name="storage_facility_masters",
        introduced_in="0023_storage_nomination_masters",
    ),
    RequiredTable(
        name="storage_inventory_observations",
        introduced_in="0023_storage_nomination_masters",
    ),
    RequiredTable(
        name="nomination_window_masters",
        introduced_in="0023_storage_nomination_masters",
    ),
    RequiredTable(
        name="cost_observations",
        introduced_in="0024_cost_observations",
    ),
    RequiredTable(
        name="screen_order_observations",
        introduced_in="0009_market_positioning",
    ),
    RequiredTable(
        name="portfolio_pnl_snapshots",
        introduced_in="0009_market_positioning",
    ),
)


def required_table_names() -> list[str]:
    """Return the ordered list of required table names."""
    return [t.name for t in REQUIRED_TABLES]


def list_required_tables() -> tuple[str, ...]:
    """Return DB table names required by the current runtime schema contract."""
    return tuple(t.name for t in REQUIRED_TABLES)


def get_metadata() -> MetaData:
    """Return SQLAlchemy metadata after importing model declarations."""

    import eurogas_nexus.db.models  # noqa: F401

    return Base.metadata


def list_missing_required_tables(engine: Engine, *, schema: str | None = None) -> tuple[str, ...]:
    """Inspect the connected database for missing required tables."""

    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names(schema=schema))
    return tuple(table for table in list_required_tables() if table not in existing_tables)
