"""SDK client for /api/workflows."""

from __future__ import annotations

import httpx


def _get(url: str) -> dict:
    response = httpx.get(url, timeout=10)
    response.raise_for_status()
    return response.json()


def fetch_route_cost(base_url: str) -> dict:
    return _get(f"{base_url}/api/workflows/route-cost")


def fetch_shadow_run(base_url: str) -> dict:
    return _get(f"{base_url}/api/workflows/shadow-run")


def fetch_brief(base_url: str) -> dict:
    return _get(f"{base_url}/api/workflows/brief")


def fetch_workflow_list(base_url: str) -> list[dict]:
    """Return available workflow endpoint names."""

    return [
        {"name": "route-cost", "method": "GET"},
        {"name": "netback", "method": "GET"},
        {"name": "feasibility", "method": "GET"},
        {"name": "allocation", "method": "GET"},
        {"name": "monitoring", "method": "GET"},
        {"name": "nowcast", "method": "GET"},
        {"name": "backtest", "method": "GET"},
        {"name": "shadow-run", "method": "GET"},
        {"name": "llm-analysis", "method": "GET"},
        {"name": "brief", "method": "GET"},
    ]
