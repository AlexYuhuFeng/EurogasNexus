"""Gas option settlements: the smile per contract and front-month volatility series.

Read-only market context: the desk does not trade options, but implied volatility, the
25-delta risk reversal and butterfly and the put/call open-interest ratio say how the market
prices risk. Rows are filtered by the caller's data scopes before anything is computed, and
each contract's smile comes from one source chosen by precedence (exchange settlement >
licensed vendor > simulated). See ``docs/data/GAS_OPTION_SETTLEMENTS.md``.

天然气期权结算：按合约的波动率微笑与近月波动率序列（只读市场背景，先授权过滤后计算）。
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from eurogas_nexus.api.dependencies.row_entitlement import current_principal
from eurogas_nexus.application.option_surface import (
    OptionHistoryTooLarge,
    metric_series,
    option_rows,
    summaries_by_day,
)
from eurogas_nexus.application.projections.market_reads import filter_entitled_rows
from eurogas_nexus.domain.market.units import HUB_NATIVE_PRICE_UNIT

router = APIRouter(tags=["market"])

SIMULATED_WARNING = (
    "SIMULATED: some contracts come from the demo simulator (ICE_ENDEX_Sim); their "
    "settlements and volatilities are synthetic and are not market prices."
)
NO_DATA_WARNING = (
    "No option settlements you are entitled to are stored for this hub and period. Option "
    "settlements are licensed: import your exchange or vendor end-of-day file with "
    "scripts/ops/import_option_settlements.py."
)
PRECEDENCE_RULE = "exchange settlement > licensed vendor > simulated, per contract and trade date"


def _env(data: Any, warnings: list[str]) -> dict:
    return {
        "data": data,
        "meta": {
            "research_only": True,
            "human_review_required": True,
            "source_references": ["runtime-postgresql:option_settlements"],
            "source_precedence": PRECEDENCE_RULE,
            "pricing_model": "Black-76 (European options on futures)",
            "warnings": list(dict.fromkeys(warnings)),
        },
    }


def _hub(value: str) -> str:
    hub = value.strip().upper()
    if hub not in HUB_NATIVE_PRICE_UNIT:
        raise HTTPException(
            status_code=422,
            detail={"code": "unknown_hub", "message": f"{value!r} is not a gas hub"},
        )
    return hub


def _entitled_rows(request: Request, hub: str, first: date, last: date) -> list[dict[str, Any]]:
    from eurogas_nexus.db.session import get_session_factory, resolve_database_url

    if not resolve_database_url():
        return []
    try:
        from sqlalchemy.exc import SQLAlchemyError

        with get_session_factory()() as session:
            rows = option_rows(session, hubs=[hub], first=first, last=last)
    except OptionHistoryTooLarge as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "runtime_db_unavailable", "message": "runtime database unavailable"},
        ) from exc
    return filter_entitled_rows(current_principal(request), rows, source_key="source_system")


@router.get("/api/market/options/surface")
def option_surface(
    request: Request,
    hub: str = Query(default="TTF", max_length=8),
    trade_date: date | None = None,
    lookback_days: int = Query(default=10, ge=1, le=60),
) -> dict:
    """Each contract's smile and metrics on the latest trade date on or before ``trade_date``.

    Returns per contract: the chosen source and the sources it outranked, the underlying,
    expiry, premium style, ATM implied volatility, 25-delta risk reversal and butterfly
    (volatility points), the put/call open-interest ratio and every strike's call and put
    settlement with its implied volatility (or the reason there is none).
    """

    hub = _hub(hub)
    anchor = trade_date or datetime.now(UTC).date()
    rows = _entitled_rows(request, hub, anchor - timedelta(days=lookback_days), anchor)
    if not rows:
        return _env({"hub": hub, "trade_date": None, "contracts": []}, [NO_DATA_WARNING])
    latest = max(row["trade_date"] for row in rows)
    by_day = summaries_by_day(row for row in rows if row["trade_date"] == latest)
    contracts = by_day.get((hub, latest), [])
    warnings = [SIMULATED_WARNING] if any(item["simulated"] for item in contracts) else []
    return _env({"hub": hub, "trade_date": latest.isoformat(), "contracts": contracts}, warnings)


@router.get("/api/market/options/metrics")
def option_metrics(
    request: Request,
    hub: str = Query(default="TTF", max_length=8),
    tenor: str = Query(default="M1", pattern=r"^M[1-6]$"),
    days: int = Query(default=90, ge=1, le=730),
    end: date | None = None,
) -> dict:
    """Daily ATM vol, RR25, BF25 and put/call OI ratio of one hub's ``M<n>`` option contract."""

    hub = _hub(hub)
    last = end or datetime.now(UTC).date()
    rows = _entitled_rows(request, hub, last - timedelta(days=days), last)
    points = metric_series(rows, hub=hub, tenor=tenor)
    warnings = [] if points else [NO_DATA_WARNING]
    if any(point["simulated"] for point in points):
        warnings.append(SIMULATED_WARNING)
    return _env(
        {
            "hub": hub,
            "tenor": tenor,
            "units": {
                "atm_iv_pct": "%",
                "rr25_vol_pts": "vol pts",
                "bf25_vol_pts": "vol pts",
                "put_call_oi_ratio": "ratio",
            },
            "points": points,
        },
        warnings,
    )
