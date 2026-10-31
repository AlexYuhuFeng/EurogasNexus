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

from eurogas_nexus.api.dependencies.row_entitlement import current_principal
from eurogas_nexus.application.projections.market_reads import filter_entitled_rows
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


def _price_unit(currency: str, unit: str) -> str:
    """``EUR/MWh`` whether the stored unit already names the currency or not."""

    return unit if "/" in unit else f"{currency}/{unit}"


#: A spread reads daily closes; this bounds the rows one request may load (about ten years
#: of daily closes for 40 series, or less history when intraday ticks are stored too).
MAX_OBSERVATION_ROWS = 150_000


def _daily_rows(
    request: Request, date_from: date | None = None, date_to: date | None = None
) -> list[dict[str, Any]]:
    """Entitled gas-price observations reduced to one close per series per trade date.

    Only per-MWh prices in the requested window are read, and only the columns used.

    Raises:
        HTTPException: 422 ``spread_window_too_large`` above :data:`MAX_OBSERVATION_ROWS`.
    """

    from datetime import UTC, datetime, time, timedelta

    from sqlalchemy import func
    from sqlalchemy.exc import SQLAlchemyError

    from eurogas_nexus.db.models import MarketObservationRecord
    from eurogas_nexus.db.session import get_session_factory, resolve_database_url

    if resolve_database_url() is None:
        return []
    try:
        with get_session_factory()() as session:
            query = session.query(
                MarketObservationRecord.product,
                MarketObservationRecord.price,
                MarketObservationRecord.unit,
                MarketObservationRecord.currency,
                MarketObservationRecord.observed_at_utc,
                MarketObservationRecord.source_system,
                MarketObservationRecord.metadata_json,
            ).filter(func.upper(MarketObservationRecord.unit).like("%MWH%"))
            # SQLite stores these timestamps without an offset; compare like with like.
            naive = session.get_bind().dialect.name == "sqlite"

            def bound(day: date) -> datetime:
                moment = datetime.combine(day, time.min, tzinfo=UTC)
                return moment.replace(tzinfo=None) if naive else moment

            if date_from:
                query = query.filter(MarketObservationRecord.observed_at_utc >= bound(date_from))
            if date_to:
                query = query.filter(
                    MarketObservationRecord.observed_at_utc < bound(date_to + timedelta(days=1))
                )
            records = (
                query.order_by(MarketObservationRecord.observed_at_utc)
                .limit(MAX_OBSERVATION_ROWS + 1)
                .all()
            )
            if len(records) > MAX_OBSERVATION_ROWS:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "code": "spread_window_too_large",
                        "message": "too many observations in this window; narrow the dates",
                    },
                )
            rows = []
            for record in records:
                metadata = record.metadata_json or {}
                hub = str(metadata.get("hub") or record.product.split(" ")[0]).upper()
                tenor = str(metadata.get("tenor") or record.product).lower()
                rows.append(
                    {
                        "hub": hub,
                        "tenor": tenor,
                        "source_system": record.source_system,
                        "currency": record.currency,
                        "unit": _price_unit(record.currency, record.unit),
                        "day": record.observed_at_utc.date(),
                        "price": float(record.price),
                        "simulated": bool(metadata.get("simulated"))
                        or record.source_system.endswith("_Sim"),
                    }
                )
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "runtime_db_unavailable", "error_class": exc.__class__.__name__},
        ) from exc
    return filter_entitled_rows(current_principal(request), rows, source_key="source_system")


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
