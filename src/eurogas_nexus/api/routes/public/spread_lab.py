"""/api/research spread lab: daily series catalogue and spread analysis.

Thin: the history and its backtest are :mod:`eurogas_nexus.application.spread_history` (shared
with Research → Spreads); this module answers HTTP.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from eurogas_nexus.application.spread_history import (
    RouteCostInput,
    SpreadAnalysisInput,
    SpreadHistoryError,
    SpreadLegInput,
    SpreadRuleInput,
    daily_rows_for,
    spread_history,
)

__all__ = ["RouteCostInput", "SpreadAnalysisInput", "SpreadLegInput", "SpreadRuleInput",
           "router", "run_spread_analysis"]

router = APIRouter(tags=["research"])


def _env(data: object, *, warnings: list[str] | None = None) -> dict:
    return {
        "data": data,
        "meta": {
            "research_only": True,
            "human_review_required": True,
            "source_references": ["runtime-postgresql"],
            "warnings": warnings or [],
        },
    }


def _daily_rows(request: Any, date_from=None, date_to=None) -> list[dict[str, Any]]:
    """Daily closes for the caller, with HTTP errors for an oversize window or a down store."""

    try:
        return daily_rows_for(request, date_from, date_to)
    except SpreadHistoryError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.get("/api/research/spread-series")
def list_spread_series(request: Request) -> dict:
    """Daily close series available to the caller: hub, tenor, source, unit and range.

    返回调用者有权访问的日度收盘序列目录（枢纽/期限/来源/单位/日期范围）。
    """

    catalogue: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in _daily_rows(request):
        key = (row["hub"], row["tenor"], row["source_system"])
        entry = catalogue.setdefault(
            key,
            {
                "hub": row["hub"],
                "tenor": row["tenor"],
                "source_system": row["source_system"],
                "currency": row["currency"],
                "unit": row["unit"],
                "first": row["day"],
                "last": row["day"],
                "days": set(),
                "simulated": row["simulated"],
            },
        )
        entry["first"] = min(entry["first"], row["day"])
        entry["last"] = max(entry["last"], row["day"])
        entry["days"].add(row["day"])
    series = [
        {
            **entry,
            "first": entry["first"].isoformat(),
            "last": entry["last"].isoformat(),
            "days": len(entry["days"]),
        }
        for entry in sorted(catalogue.values(), key=lambda item: (item["hub"], item["tenor"]))
    ]
    return _env(series)


@router.post("/api/research/spread-analysis")
def run_spread_analysis(body: SpreadAnalysisInput, request: Request) -> dict:
    """Weighted spread of 1-4 daily series, its statistics and a declared-rule backtest.

    See :func:`eurogas_nexus.application.spread_history.spread_history`.
    计算 1–4 条日度序列的加权价差、统计量及声明式规则回测。

    Raises:
        HTTPException: 422 ``spread_analysis_invalid``; 503 when the store is down.
    """

    try:
        return spread_history(body, request)
    except SpreadHistoryError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
