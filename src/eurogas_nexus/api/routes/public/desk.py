"""The Today read: ``GET /api/desk/today`` (UX-05, STAB-02, FRESH-02).

What changed and does it touch us, from the data that exists, computed once on the server
(``application/desk_today.py``): key figures, what changed, the book against the market and
the fundamentals. A read: nothing is written, no model is called, and every figure is what
the caller may already see on its own page.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from eurogas_nexus.api.routes.public.portfolio_common import env as _env

router = APIRouter(tags=["desk"])


@router.get("/api/desk/today")
def get_today(request: Request) -> dict:
    """Today: prices and day change, positions, the tightest limit, alerts and outages,
    the book against the market, storage and the NW Europe balance.

    今日概览：价格与日变动、头寸、最紧的限额、告警与停运、账簿对市场、储气与西北欧平衡。

    Each figure carries ``unit``, ``as_of``, ``state`` (current, late, stale, never, manual)
    and ``simulated``; ``stale_figures`` names the late and stale ones. A section with no
    data carries ``empty`` with the reason and the next action.
    """

    from sqlalchemy.exc import SQLAlchemyError

    from eurogas_nexus.application.caller import caller_of
    from eurogas_nexus.application.desk_today import BALANCE_DAYS, build_today
    from eurogas_nexus.application.projections.daily_closes import shared_daily_rows
    from eurogas_nexus.db.session import get_session_factory, resolve_database_url

    if resolve_database_url() is None:
        return _env({}, request, "runtime-db-not-configured", ["RUNTIME_DB_NOT_CONFIGURED"])

    def balance() -> dict | None:
        # The balance page's own read, so the two cannot disagree.
        from eurogas_nexus.api.routes.public.fundamentals import get_nwe_balance

        response = get_nwe_balance(request, days=1, history_days=max(7, BALANCE_DAYS),
                                   format="json")
        return response.get("data") if isinstance(response, dict) else None

    try:
        # The book, credit lines and mandates read the same closes: once, not three times.
        with shared_daily_rows(), get_session_factory()() as session:
            data = build_today(session, caller_of(request), balance_reader=balance)
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "runtime_db_unavailable", "error_class": exc.__class__.__name__},
        ) from exc
    return _env(data, request, "runtime-postgresql:desk-today", data["warnings"])
