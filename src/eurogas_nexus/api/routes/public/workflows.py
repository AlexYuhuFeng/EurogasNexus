"""Read-only /api/workflows routes (DEPRECATED legacy shells).

These routes expose the V1 workflow surface while the concrete workflow
implementations move behind PostgreSQL-backed route-cost, portfolio, strategy,
market, physical, LNG, storage, analysis, and report modules. They must not
return static market or strategy values.

All routes in this module are legacy shells: every operation is marked
``deprecated`` in the OpenAPI contract and returns a deprecation notice plus
the ``DEPRECATED_WORKFLOW_SHELL`` warning. Consumers should use the
domain-specific ``/api`` endpoints instead.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter(tags=["workflows"])


@router.get("/api/workflows/route-cost", deprecated=True)
def route_cost(request: Request) -> dict:
    return _blocked("route-cost", request)


@router.get("/api/workflows/netback", deprecated=True)
def netback(request: Request) -> dict:
    return _blocked("netback", request)


@router.get("/api/workflows/feasibility", deprecated=True)
def feasibility(request: Request) -> dict:
    return _blocked("feasibility", request)


@router.get("/api/workflows/allocation", deprecated=True)
def allocation(request: Request) -> dict:
    return _blocked("allocation", request)


@router.get("/api/workflows/monitoring", deprecated=True)
def monitoring(request: Request) -> dict:
    return _blocked("monitoring", request)


@router.get("/api/workflows/nowcast", deprecated=True)
def nowcast(request: Request) -> dict:
    return _blocked("nowcast", request)


@router.get("/api/workflows/backtest", deprecated=True)
def backtest(request: Request) -> dict:
    return _blocked("backtest", request)


@router.get("/api/workflows/shadow-run", deprecated=True)
def shadow_run(request: Request) -> dict:
    return _blocked("shadow-run", request)


@router.get("/api/workflows/llm-analysis", deprecated=True)
def llm_analysis(request: Request) -> dict:
    return _blocked("llm-analysis", request)


@router.get("/api/workflows/brief", deprecated=True)
def brief(request: Request) -> dict:
    return _blocked("brief", request)


def _blocked(workflow_id: str, _request: Request) -> dict:
    return {
        "data": {
            "workflow_id": workflow_id,
            "status": "BLOCKED",
            "code": "RUNTIME_DATA_REQUIRED",
            "deprecated": True,
            "deprecation_notice": (
                "The /api/workflows surface is a deprecated legacy shell. Use "
                "the domain-specific /api endpoints instead."
            ),
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
            "warnings": [
                "RUNTIME_DB_NOT_CONFIGURED",
                "STATIC_WORKFLOW_FIXTURE_REMOVED",
                "DEPRECATED_WORKFLOW_SHELL",
            ],
        },
    }
