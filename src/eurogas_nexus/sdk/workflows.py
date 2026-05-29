"""SDK client for /api/v1/workflows (GET fixtures)."""

import httpx


def _get(url: str) -> dict:
    r = httpx.get(url, timeout=10)
    r.raise_for_status()
    return r.json()


def fetch_route_cost(base_url: str) -> dict:
    return _get(f"{base_url}/api/v1/workflows/route-cost")

def fetch_shadow_run(base_url: str) -> dict:
    return _get(f"{base_url}/api/v1/workflows/shadow-run")

def fetch_brief(base_url: str) -> dict:
    return _get(f"{base_url}/api/v1/workflows/brief")

def fetch_workflow_list(base_url: str) -> list[dict]:
    """Return available workflow fixture names (not a real API — metadata helper)."""
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
