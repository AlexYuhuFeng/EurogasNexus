"""CLI operator commands — SDK/API-backed, read-only by default.

CLI 命令层：全部经由 SDK 调用后端 API（不直连 DB、不导入领域内部模块），
默认只读；优化类命令从 JSON 文件读取沙箱请求体。每个 cmd_* 是薄封装，
把 SDK 结果序列化为 JSON/列表供 CLI 打印。
"""

from __future__ import annotations

import json
from pathlib import Path

from eurogas_nexus_sdk.analysis import ask_analysis
from eurogas_nexus_sdk.contracts import fetch_capacity_contracts, fetch_route_eligibility
from eurogas_nexus_sdk.credentials import fetch_credential_providers
from eurogas_nexus_sdk.glossary import fetch_glossary, fetch_term
from eurogas_nexus_sdk.lng import fetch_lng_observations, fetch_lng_terminals
from eurogas_nexus_sdk.market import fetch_fx_rates, fetch_market_observations, fetch_spreads
from eurogas_nexus_sdk.optimization import (
    fetch_optimization_run,
    optimize_capacity,
    optimize_contracts,
    optimize_resource_pool,
    optimize_route,
)
from eurogas_nexus_sdk.physical import fetch_capacity, fetch_flows, fetch_outages
from eurogas_nexus_sdk.reference_network import (
    fetch_edges,
    fetch_facilities,
    fetch_market_hubs,
    fetch_node,
    fetch_nodes,
)
from eurogas_nexus_sdk.review import fetch_review_decisions
from eurogas_nexus_sdk.runtime import fetch_runtime_db_status
from eurogas_nexus_sdk.sources import fetch_ingestion_runs, fetch_source, fetch_sources
from eurogas_nexus_sdk.storage import fetch_storage_observations, fetch_storage_sites
from eurogas_nexus_sdk.strategy_lab import list_strategy_runs, strategy_summary
from eurogas_nexus_sdk.weather import (
    fetch_hdd_cdd,
    fetch_weather_observations,
    fetch_weather_stations,
)

from eurogas_nexus.cli.health import run_health_check


def _to_json(data: object) -> str:
    """Serialize result to JSON string.

    Args:
        data: SDK result (pydantic model, list, or plain value).

    Returns:
        Indented JSON string.
    """

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
    """Run the API health check and return its report text."""

    return run_health_check(base_url)


def cmd_runtime_db(base_url: str) -> str:
    """Fetch and print the runtime DB connectivity status as JSON."""

    return _to_json(fetch_runtime_db_status(base_url))


# --- Reference Network ---

def cmd_nodes(base_url: str, *, country: str | None = None, node_type: str | None = None) -> list:
    """List reference nodes, optionally filtered by country and node type."""

    return fetch_nodes(base_url, country=country, node_type=node_type)

def cmd_node(base_url: str, node_id: str) -> str:
    """Fetch one reference node by id as JSON."""

    return _to_json(fetch_node(base_url, node_id))

def cmd_edges(base_url: str) -> list:
    """List reference edges."""

    return fetch_edges(base_url)

def cmd_facilities(base_url: str) -> list:
    """List reference facilities."""

    return fetch_facilities(base_url)

def cmd_market_hubs(base_url: str) -> list:
    """List reference market hubs."""

    return fetch_market_hubs(base_url)


# --- Sources ---

def cmd_sources(base_url: str) -> list:
    """List registered source systems."""

    return fetch_sources(base_url)

def cmd_source(base_url: str, source_id: str) -> str:
    """Fetch one source system by id as JSON."""

    return _to_json(fetch_source(base_url, source_id))

def cmd_ingestion_runs(base_url: str, *, source_id: str | None = None) -> list:
    """List ingestion runs, optionally filtered by source."""

    return fetch_ingestion_runs(base_url, source_id=source_id)


# --- Market ---

def cmd_market(base_url: str) -> list:
    """List market observations."""

    return fetch_market_observations(base_url)

def cmd_fx(base_url: str) -> list:
    """List FX observations."""

    return fetch_fx_rates(base_url)

def cmd_spreads(base_url: str) -> list:
    """List intraday cross-hub spreads."""

    return fetch_spreads(base_url)


# --- Physical ---

def cmd_flows(base_url: str) -> list:
    """List physical flow observations."""

    return fetch_flows(base_url)

def cmd_capacity(base_url: str) -> list:
    """List capacity observations."""

    return fetch_capacity(base_url)

def cmd_outages(base_url: str) -> list:
    """List outage records."""

    return fetch_outages(base_url)


# --- LNG ---

def cmd_lng_terminals(base_url: str) -> list:
    """List LNG terminals."""

    return fetch_lng_terminals(base_url)

def cmd_lng_obs(base_url: str) -> list:
    """List LNG terminal observations."""

    return fetch_lng_observations(base_url)


# --- Storage ---

def cmd_storage_sites(base_url: str) -> list:
    """List storage sites."""

    return fetch_storage_sites(base_url)

def cmd_storage_obs(base_url: str) -> list:
    """List storage observations."""

    return fetch_storage_observations(base_url)


# --- Weather ---

def cmd_weather_stations(base_url: str) -> list:
    """List weather stations."""

    return fetch_weather_stations(base_url)

def cmd_weather_obs(base_url: str) -> list:
    """List weather observations."""

    return fetch_weather_observations(base_url)

def cmd_hdd_cdd(base_url: str) -> list:
    """List HDD/CDD series."""

    return fetch_hdd_cdd(base_url)


# --- Contracts ---

def cmd_capacity_contracts(base_url: str) -> list:
    """List capacity profile contracts."""

    return fetch_capacity_contracts(base_url)

def cmd_route_eligibility(base_url: str) -> list:
    """List route eligibility context."""

    return fetch_route_eligibility(base_url)


# --- Glossary ---

def cmd_glossary(base_url: str, *, lang: str = "en") -> list:
    """List glossary terms in the requested language."""

    return fetch_glossary(base_url, lang=lang)

def cmd_term(base_url: str, term: str, *, lang: str = "en") -> str:
    """Fetch one glossary term by name/id/alias as JSON."""

    return _to_json(fetch_term(base_url, term, lang=lang))


# --- Strategy Lab ---

def cmd_strategy_runs(base_url: str, *, strategy_id: str | None = None) -> list:
    """List strategy runs, optionally filtered by strategy."""

    return list_strategy_runs(base_url, strategy_id=strategy_id)

def cmd_strategy_summary(base_url: str, *, strategy_id: str | None = None) -> object:
    """Fetch the strategy-run summary."""

    return strategy_summary(base_url, strategy_id=strategy_id)


# --- Optimization (P2: sandbox requests from JSON files) ---

OPTIMIZATION_KINDS = ("route", "resource-pool", "capacity", "contracts")


def cmd_optimize(base_url: str, *, kind: str, input_path: str) -> dict:
    """Run one sandbox optimization from a JSON request file.

    Args:
        base_url: API base URL.
        kind: Optimization kind (route/resource-pool/capacity/contracts).
        input_path: JSON request file path.

    Returns:
        The result payload dict.

    Raises:
        ValueError: When the kind is unknown.
    """

    if kind not in OPTIMIZATION_KINDS:
        choices = ", ".join(OPTIMIZATION_KINDS)
        raise ValueError(f"unknown optimization kind {kind!r}; choose {choices}")
    payload = json.loads(Path(input_path).read_text(encoding="utf-8"))
    if kind == "route":
        result = optimize_route(base_url, **payload)
    elif kind == "resource-pool":
        result = optimize_resource_pool(base_url, **payload)
    elif kind == "capacity":
        result = optimize_capacity(base_url, **payload)
    else:
        result = optimize_contracts(base_url, **payload)
    return result.data.model_dump()


def cmd_optimization_run(base_url: str, run_id: str) -> dict:
    """Read one persisted optimization run (evidence).

    Args:
        base_url: API base URL.
        run_id: Persisted run id.

    Returns:
        The run payload dict.
    """

    return fetch_optimization_run(base_url, run_id).data.model_dump()


# --- Analysis (P2) ---

def cmd_analyze(
    base_url: str,
    *,
    question: str,
    task: str = "DB_INQUIRY",
    invoke_provider: bool = False,
) -> dict:
    """Run a governed analysis query (provider disabled in trial/release).

    Args:
        base_url: API base URL.
        question: Analyst question.
        task: Analysis task kind.
        invoke_provider: Whether to request LLM synthesis.

    Returns:
        The AnalysisResult payload dict.
    """

    result = ask_analysis(
        base_url,
        question=question,
        task=task,
        invoke_provider=invoke_provider,
    )
    return result.model_dump()


# --- Registry reads (previously defined but unregistered) ---

def cmd_credential_providers(base_url: str) -> list:
    """List credential providers with their status."""

    return fetch_credential_providers(base_url).data


def cmd_review_decisions(base_url: str, *, limit: int = 100) -> list:
    """List trader review decisions.

    Args:
        base_url: API base URL.
        limit: Max rows.

    Returns:
        Review decision list.
    """

    return fetch_review_decisions(base_url, limit=limit).data
