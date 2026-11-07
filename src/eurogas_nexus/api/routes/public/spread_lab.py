"""/api/research spread lab: daily series catalogue and spread analysis.

The loading here is thin: daily closes per (hub, tenor, source) come from the runtime
market observations, filtered by the caller's data entitlements, and the analysis is
the pure :mod:`eurogas_nexus.domain.research.spread_analysis` engine.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from eurogas_nexus.domain.research.spread_analysis import (
    SpreadAnalysisError,
    SpreadLeg,
    SpreadRule,
    analyse_spread,
)

router = APIRouter(tags=["research"])


class SpreadLegInput(BaseModel):
    hub: str = Field(min_length=2, max_length=16)
    tenor: str = Field(min_length=2, max_length=32)
    source_system: str | None = Field(default=None, max_length=64)
    weight: float = Field(default=1.0, allow_inf_nan=False)


class SpreadRuleInput(BaseModel):
    kind: str = "zscore"
    lookback: int = 20
    entry_z: float = Field(default=2.0, allow_inf_nan=False)
    exit_z: float = Field(default=0.5, allow_inf_nan=False)
    low: float | None = Field(default=None, allow_inf_nan=False)
    high: float | None = Field(default=None, allow_inf_nan=False)
    volume_mwh_per_day: float = Field(default=1_000.0, allow_inf_nan=False)
    cost_per_mwh: float = Field(default=0.02, allow_inf_nan=False)


class SpreadAnalysisInput(BaseModel):
    legs: list[SpreadLegInput] = Field(min_length=1, max_length=4)
    date_from: date | None = None
    date_to: date | None = None
    rule: SpreadRuleInput = Field(default_factory=SpreadRuleInput)


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


def _daily_rows(
    request: Any, date_from: date | None = None, date_to: date | None = None
) -> list[dict[str, Any]]:
    """Daily closes for the caller, with HTTP errors for an oversize window or a down store."""

    from sqlalchemy.exc import SQLAlchemyError

    from eurogas_nexus.application.projections.daily_closes import (
        ObservationWindowTooLarge,
        daily_rows,
    )

    try:
        return daily_rows(request, date_from, date_to)
    except ObservationWindowTooLarge as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "spread_window_too_large",
                "message": "too many observations in this window; narrow the dates",
            },
        ) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "runtime_db_unavailable", "error_class": exc.__class__.__name__},
        ) from exc


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

    计算 1–4 条日度序列的加权价差、统计量及声明式规则回测（无前视偏差）。

    Raises:
        HTTPException: 422 ``spread_analysis_invalid`` (unknown series, mixed units,
            too little overlap, bad rule).
    """

    rows = _daily_rows(request, body.date_from, body.date_to)
    legs: list[SpreadLeg] = []
    units: set[str] = set()
    simulated = False
    for leg in body.legs:
        hub, tenor = leg.hub.strip().upper(), leg.tenor.strip().lower()
        closes: dict[date, float] = {}
        for row in rows:
            if row["hub"] != hub or row["tenor"] != tenor:
                continue
            if leg.source_system and row["source_system"] != leg.source_system:
                continue
            if body.date_from and row["day"] < body.date_from:
                continue
            if body.date_to and row["day"] > body.date_to:
                continue
            closes[row["day"]] = row["price"]  # rows are time-ordered: last one wins
            units.add(row["unit"])
            simulated = simulated or row["simulated"]
        if not closes:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "spread_analysis_invalid",
                    "message": f"no entitled daily series for {hub} {tenor}"
                    + (f" from {leg.source_system}" if leg.source_system else ""),
                },
            )
        source = f" ({leg.source_system})" if leg.source_system else ""
        legs.append(SpreadLeg(f"{hub} {tenor}{source}", leg.weight, closes))
    if len(units) > 1:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "spread_analysis_invalid",
                "message": "legs are quoted in different units "
                f"({', '.join(sorted(units))}); convert first or pick same-unit series",
            },
        )
    try:
        analysis = analyse_spread(
            legs, SpreadRule(**body.rule.model_dump()), simulated_sources=simulated
        )
    except SpreadAnalysisError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "spread_analysis_invalid", "message": str(exc)},
        ) from exc
    payload = analysis.as_dict()
    payload["unit"] = next(iter(units))
    return _env(payload, warnings=list(analysis.limitations))
