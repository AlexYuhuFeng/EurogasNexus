"""Read-only /api/v1/contracts routes — capacity/route context (synthetic only)."""

from fastapi import APIRouter, Request

router = APIRouter(tags=["contracts"])


def _env(data: object, _request: Request) -> dict:
    return {"data": data, "meta": {"research_only": True, "human_review_required": True,
            "source_references": ["synthetic-fixture"], "warnings": [
                "Synthetic data only. Not an ETRM — no booking/nomination/execution semantics."
            ]}}


@router.get("/api/v1/contracts/capacity")
def list_capacity_contracts(request: Request) -> dict:
    return _env([
        {"contract_id": "cap-ctr-001", "route_name": "TTF-NCG",
         "from_node_id": "node-ttf", "to_node_id": "node-ncg",
         "capacity_boe_d": 500000.0, "unit": "boe/d",
         "start_utc": "2026-01-01T00:00:00Z", "end_utc": "2026-12-31T23:59:59Z",
         "status": "active", "counterparty": ""},
        {"contract_id": "cap-ctr-002", "route_name": "Zeebrugge-TTF",
         "from_node_id": "node-zeebrugge", "to_node_id": "node-ttf",
         "capacity_boe_d": 350000.0, "unit": "boe/d",
         "start_utc": "2026-04-01T00:00:00Z", "end_utc": "2026-09-30T23:59:59Z",
         "status": "active", "counterparty": ""},
        {"contract_id": "cap-ctr-003", "route_name": "Emden-NCG",
         "from_node_id": "node-emden", "to_node_id": "node-ncg",
         "capacity_boe_d": 200000.0, "unit": "boe/d",
         "start_utc": "2025-10-01T00:00:00Z", "end_utc": "2026-03-31T23:59:59Z",
         "status": "expiring", "counterparty": ""},
    ], request)


@router.get("/api/v1/contracts/routes")
def list_route_eligibility(request: Request) -> dict:
    return _env([
        {"route_id": "rte-001", "from_node_id": "node-ttf", "to_node_id": "node-ncg",
         "eligibility": "confirmed", "confidence": 0.95, "constraints": []},
        {"route_id": "rte-002", "from_node_id": "node-nbp", "to_node_id": "node-zeebrugge",
         "eligibility": "confirmed", "confidence": 0.90, "constraints": ["interconnector"]},
        {"route_id": "rte-003", "from_node_id": "node-peg", "to_node_id": "node-psv",
         "eligibility": "research_candidate", "confidence": 0.60,
         "constraints": ["transit-fees-unknown"]},
    ], request)
