"""CLI operator commands — SDK/API-backed, read-only by default."""

from __future__ import annotations

import json

from eurogas_nexus.cli.health import run_health_check
from eurogas_nexus.sdk.contracts import fetch_capacity_contracts, fetch_route_eligibility
from eurogas_nexus.sdk.glossary import fetch_glossary, fetch_term
from eurogas_nexus.sdk.lng import fetch_lng_observations, fetch_lng_terminals
from eurogas_nexus.sdk.market import fetch_fx_rates, fetch_market_observations, fetch_spreads
from eurogas_nexus.sdk.physical import fetch_capacity, fetch_flows, fetch_outages
from eurogas_nexus.sdk.reference_network import (
    fetch_edges,
    fetch_facilities,
    fetch_market_hubs,
    fetch_node,
    fetch_nodes,
)
from eurogas_nexus.sdk.runtime import fetch_runtime_db_status
from eurogas_nexus.sdk.sources import fetch_ingestion_runs, fetch_source, fetch_sources
from eurogas_nexus.sdk.storage import fetch_storage_observations, fetch_storage_sites
from eurogas_nexus.sdk.weather import (
    fetch_hdd_cdd,
    fetch_weather_observations,
    fetch_weather_stations,
)
from eurogas_nexus.sdk.workflows import fetch_brief, fetch_route_cost, fetch_shadow_run


def _to_json(data: object) -> str:
    """Serialize result to JSON string."""
    if hasattr(data, "model_dump"):
        return json.dumps(data.model_dump(), indent=2, default=str)
    if isinstance(data, list):
        return json.dumps(
            [d.model_dump() if hasattr(d, "model_dump") else d for d in data],
            indent=2, default=str,
        )
    return json.dumps(data, indent=2, default=str)


# --- Health ---

def cmd_health(base_url: str) -> str:
    return run_health_check(base_url)


def cmd_runtime_db(base_url: str) -> str:
    return _to_json(fetch_runtime_db_status(base_url))


# --- Reference Network ---

def cmd_nodes(base_url: str, *, country: str | None = None, node_type: str | None = None) -> list:
    return fetch_nodes(base_url, country=country, node_type=node_type)

def cmd_node(base_url: str, node_id: str) -> str:
    return _to_json(fetch_node(base_url, node_id))

def cmd_edges(base_url: str) -> list:
    return fetch_edges(base_url)

def cmd_facilities(base_url: str) -> list:
    return fetch_facilities(base_url)

def cmd_market_hubs(base_url: str) -> list:
    return fetch_market_hubs(base_url)


# --- Sources ---

def cmd_sources(base_url: str) -> list:
    return fetch_sources(base_url)

def cmd_source(base_url: str, source_id: str) -> str:
    return _to_json(fetch_source(base_url, source_id))

def cmd_ingestion_runs(base_url: str, *, source_id: str | None = None) -> list:
    return fetch_ingestion_runs(base_url, source_id=source_id)


# --- Market ---

def cmd_market(base_url: str) -> list:
    return fetch_market_observations(base_url)

def cmd_fx(base_url: str) -> list:
    return fetch_fx_rates(base_url)

def cmd_spreads(base_url: str) -> list:
    return fetch_spreads(base_url)


# --- Physical ---

def cmd_flows(base_url: str) -> list:
    return fetch_flows(base_url)

def cmd_capacity(base_url: str) -> list:
    return fetch_capacity(base_url)

def cmd_outages(base_url: str) -> list:
    return fetch_outages(base_url)


# --- LNG ---

def cmd_lng_terminals(base_url: str) -> list:
    return fetch_lng_terminals(base_url)

def cmd_lng_obs(base_url: str) -> list:
    return fetch_lng_observations(base_url)


# --- Storage ---

def cmd_storage_sites(base_url: str) -> list:
    return fetch_storage_sites(base_url)

def cmd_storage_obs(base_url: str) -> list:
    return fetch_storage_observations(base_url)


# --- Weather ---

def cmd_weather_stations(base_url: str) -> list:
    return fetch_weather_stations(base_url)

def cmd_weather_obs(base_url: str) -> list:
    return fetch_weather_observations(base_url)

def cmd_hdd_cdd(base_url: str) -> list:
    return fetch_hdd_cdd(base_url)


# --- Contracts ---

def cmd_capacity_contracts(base_url: str) -> list:
    return fetch_capacity_contracts(base_url)

def cmd_route_eligibility(base_url: str) -> list:
    return fetch_route_eligibility(base_url)


# --- Glossary ---

def cmd_glossary(base_url: str, *, lang: str = "en") -> list:
    return fetch_glossary(base_url, lang=lang)

def cmd_term(base_url: str, term: str, *, lang: str = "en") -> str:
    return _to_json(fetch_term(base_url, term, lang=lang))


# --- Workflows ---

def cmd_route_cost(base_url: str) -> str:
    return _to_json(fetch_route_cost(base_url))


def cmd_shadow_run(base_url: str) -> str:
    return _to_json(fetch_shadow_run(base_url))

def cmd_brief(base_url: str) -> str:
    return _to_json(fetch_brief(base_url))
