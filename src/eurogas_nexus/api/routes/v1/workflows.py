"""Read-only /api/v1/workflows routes — research workflow fixtures."""

from fastapi import APIRouter, Request

router = APIRouter(tags=["workflows"])

_EM = {"research_only": True, "human_review_required": True,
       "source_references": ["synthetic-fixture"], "warnings": ["Synthetic data only."]}


def _env(data: object) -> dict:
    return {"data": data, "meta": dict(_EM)}


@router.get("/api/v1/workflows/route-cost")
def route_cost(request: Request) -> dict:
    return _env({
        "result_id": "rc-001", "route_name": "TTF-NCG", "from_node_id": "node-ttf",
        "to_node_id": "node-ncg", "total_cost_eur_mwh": 2.35, "total_cost_boe": 0.40,
        "route_km": 200.0, "cost_components": [
            {"component_id": "c1", "component_type": "tariff", "amount": 1.50,
             "unit": "EUR/MWh", "currency": "EUR", "description": "Entry/exit tariff"},
            {"component_id": "c2", "component_type": "fuel", "amount": 0.85,
             "unit": "EUR/MWh", "currency": "EUR", "description": "Fuel gas"},
        ],
    })


@router.get("/api/v1/workflows/netback")
def netback(request: Request) -> dict:
    return _env({
        "result_id": "nb-001", "route_name": "TTF-NBP", "from_market": "TTF",
        "to_market": "NBP", "market_price_eur_mwh": 42.50, "route_cost_eur_mwh": 1.80,
        "netback_eur_mwh": 40.70, "fx_rate": 0.8510,
    })


@router.get("/api/v1/workflows/feasibility")
def feasibility(request: Request) -> dict:
    return _env({
        "result_id": "feas-001", "route_name": "TTF-NCG", "status": "feasible",
        "blockers": [], "conditions": ["within technical capacity limits"],
    })


@router.get("/api/v1/workflows/allocation")
def allocation(request: Request) -> dict:
    return _env({
        "result_id": "alloc-001", "scenario_name": "Winter 2026 Base",
        "total_demand_boe_d": 5000000, "total_allocated_boe_d": 4800000,
        "unallocated_boe_d": 200000, "candidates": [
            {"candidate_id": "c1", "route_name": "TTF-NCG", "allocated_volume_boe_d": 3000000,
             "price_eur_mwh": 40.50, "rank": 1},
            {"candidate_id": "c2", "route_name": "Emden-NCG", "allocated_volume_boe_d": 1800000,
             "price_eur_mwh": 41.20, "rank": 2},
        ],
    })


@router.get("/api/v1/workflows/monitoring")
def monitoring(request: Request) -> dict:
    return _env([
        {"alert_id": "alt-001", "alert_type": "capacity_constraint", "severity": "warning",
         "message": "Mallnow capacity reduced to 45 mcm/d", "related_entity_id": "node-mallnow"},
        {"alert_id": "alt-002", "alert_type": "price_spike", "severity": "info",
         "message": "TTF day-ahead above 45 EUR/MWh", "related_entity_id": "hub-ttf"},
    ])


@router.get("/api/v1/workflows/nowcast")
def nowcast(request: Request) -> dict:
    return _env({
        "result_id": "nc-001", "market": "TTF",
        "period_start_utc": "2026-05-30T00:00:00Z", "period_end_utc": "2026-05-31T00:00:00Z",
        "base_demand_boe_d": 4200000, "weather_adjustment_boe_d": 150000,
        "adjusted_demand_boe_d": 4350000, "hdd": 1.0, "cdd": 0.0,
    })


@router.get("/api/v1/workflows/backtest")
def backtest(request: Request) -> dict:
    return _env({
        "result_id": "bt-001", "strategy_name": "Winter TTF-NBP spread",
        "start_utc": "2025-10-01T00:00:00Z", "end_utc": "2026-03-31T23:59:59Z",
        "total_return_eur": 125000.0, "sharpe_ratio": 1.45, "max_drawdown_pct": 12.5,
        "trade_count": 48, "win_rate_pct": 62.5,
    })


@router.get("/api/v1/workflows/shadow-run")
def shadow_run(request: Request) -> dict:
    return _env({
        "result_id": "sr-001", "strategy_name": "NBP-PEG spread shadow",
        "status": "active", "started_at_utc": "2026-05-01T00:00:00Z",
        "elapsed_days": 28, "paper_pnl_eur": 8500.0, "signal_count": 12,
        "candidates": [
            {"ranking_id": "r1", "route_name": "NBP-Zeebrugge", "rank": 1, "score": 0.85,
             "action": "research_candidate"},
        ],
    })


@router.get("/api/v1/workflows/llm-analysis")
def llm_analysis(request: Request) -> dict:
    return _env({
        "analysis_id": "llm-001", "topic": "TTF summer 2026 outlook",
        "market_context": "TTF month-ahead at 42.50 EUR/MWh, storage at 62%",
        "analysis_text": "Current storage levels and mild weather suggest downward pressure...",
        "citations": ["GIE AGSI: storage fill data 2026-05-29", "ENTSOG: flow data 2026-05-29"],
        "llm_provider": "", "llm_model": "",
        "prompt_snapshot": "[Prompt snapshot would appear here — LLM provider not configured.]",
    })


@router.get("/api/v1/workflows/brief")
def brief(request: Request) -> dict:
    return _env({
        "brief_id": "brief-001", "title": "European Gas Weekly — 2026-W22",
        "summary": "Mild weather and healthy storage keep prices range-bound...",
        "sections": [
            {"heading": "Market Overview", "content": "TTF month-ahead stable at ~42 EUR/MWh."},
            {"heading": "Supply", "content": "Norwegian flows steady. LNG send-out elevated."},
            {"heading": "Demand", "content": "Below seasonal norm. HDD accumulation minimal."},
            {"heading": "Outlook", "content": "Monitoring scheduled Mallnow maintenance."},
        ],
        "glossary_terms": ["TTF", "HDD", "MCM", "send-out"],
        "author": "Eurogas Nexus (synthetic)",
    })
