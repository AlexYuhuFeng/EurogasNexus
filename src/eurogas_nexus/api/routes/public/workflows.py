"""Read-only /api/workflows routes.

These routes expose the V1 workflow surface while the concrete workflow
implementations move behind PostgreSQL-backed route-cost, portfolio, strategy,
market, physical, LNG, storage, analysis, and report modules. They must not
return static market or strategy values.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter(tags=["workflows"])


@router.get("/api/workflows/route-cost")
def route_cost(request: Request) -> dict:
    return _blocked("route-cost", request)


@router.get("/api/workflows/netback")
def netback(request: Request) -> dict:
    return _blocked("netback", request)


@router.get("/api/workflows/feasibility")
def feasibility(request: Request) -> dict:
    return _blocked("feasibility", request)


@router.get("/api/workflows/allocation")
def allocation(request: Request) -> dict:
    return _blocked("allocation", request)


@router.get("/api/workflows/monitoring")
def monitoring(request: Request) -> dict:
    return _blocked("monitoring", request)


@router.get("/api/workflows/nowcast")
def nowcast(request: Request) -> dict:
    return _blocked("nowcast", request)


@router.get("/api/workflows/backtest")
def backtest(request: Request) -> dict:
    return _blocked("backtest", request)


@router.get("/api/workflows/shadow-run")
def shadow_run(request: Request) -> dict:
    return _blocked("shadow-run", request)


@router.get("/api/workflows/llm-analysis")
def llm_analysis(request: Request) -> dict:
    return _blocked("llm-analysis", request)


@router.get("/api/workflows/brief")
def brief(request: Request) -> dict:
    return _blocked("brief", request)


def _blocked(workflow_id: str, _request: Request) -> dict:
    return {
        "data": {
            "workflow_id": workflow_id,
            "status": "BLOCKED",
            "code": "RUNTIME_DATA_REQUIRED",
            "message": (
                "This workflow requires PostgreSQL-backed runtime data and a "
                "specific implementation endpoint. Static workflow payloads are "
                "not part of the V1 runtime contract."
            ),
            "next_steps": [
                "Use the domain-specific /api endpoints.",
                "Ingest source data into PostgreSQL.",
                "Run the relevant strategy or report workflow before reading results.",
            ],
        },
        "meta": {
            "research_only": True,
            "human_review_required": True,
            "source_references": ["runtime-db-not-configured"],
            "warnings": ["RUNTIME_DB_NOT_CONFIGURED", "STATIC_WORKFLOW_FIXTURE_REMOVED"],
        },
    }
