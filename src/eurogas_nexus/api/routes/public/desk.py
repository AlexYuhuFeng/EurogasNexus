"""The Today read: ``GET /api/desk/today`` (UX-05, STAB-02, FRESH-02), the gas day's status
writes and its reconciliation (``GET /api/desk/gas-day/{gas_day}/reconciliation``, SCHED-1).

What changed and does it touch us, from the data that exists, computed once on the server
(``application/desk_today.py``): key figures, what changed, the book against the market and
the fundamentals. A read: nothing is written, no model is called, and every figure is what
the caller may already see on its own page.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from eurogas_nexus.api.routes.public.portfolio_common import env as _env
from eurogas_nexus.application.refreshable_reads import FORMAT_DESCRIPTION, REFRESH_FORMAT_PATTERN
from eurogas_nexus.application.warm_views import ViewSpec, warm_view

router = APIRouter(tags=["desk"])


@router.get("/api/desk/today")
@warm_view(ViewSpec("desk.today", max_age_seconds=60, follows_deals=True))
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


class GasDayStatusRequest(BaseModel):
    """A nomination or terminal step's status, recorded by hand (labelled and audited)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    gas_day: date
    line_ref: str = Field(min_length=3, max_length=160)
    step: str = Field(min_length=3, max_length=32)
    status: str = Field(min_length=3, max_length=24)
    quantity_mwh: float | None = Field(default=None, ge=0, le=10_000_000)
    note: str | None = Field(default=None, max_length=500)


@router.post("/api/desk/gas-day/status")
def post_gas_day_status(body: GasDayStatusRequest, request: Request) -> dict:
    """Record a nomination or terminal step's status for today's or tomorrow's gas day.

    记录提名或码头步骤状态（手工录入，标注并审计）；不提交任何提名。

    Status tracking only: nothing is nominated or sent. The line must be in the caller's own
    gas day (the books their mandate covers, or every book they may see without one); the
    status is stored as entered by hand, with who and when, and an audit event is written.
    Needs ``gas_day.record`` (SCHEDULER or ANALYST).
    """

    from datetime import UTC, datetime

    from sqlalchemy.exc import SQLAlchemyError

    from eurogas_nexus.application.caller import caller_of
    from eurogas_nexus.application.gas_day_checklist import ChecklistError, record_status
    from eurogas_nexus.db.session import get_session_factory, resolve_database_url
    from eurogas_nexus.security.authorization import Permission, authorize

    principal = getattr(request.state, "identity", None)
    if principal is None or not authorize(principal, Permission.GAS_DAY_RECORD).allowed:
        raise HTTPException(
            status_code=403,
            detail={"code": "permission_denied", "permission": Permission.GAS_DAY_RECORD.value},
        )
    if resolve_database_url() is None:
        raise HTTPException(status_code=503, detail={"code": "runtime_db_not_configured"})
    try:
        with get_session_factory()() as session:
            result = record_status(
                session, caller_of(request), gas_day=body.gas_day, line_ref=body.line_ref,
                step=body.step, status=body.status, quantity_mwh=body.quantity_mwh,
                note=body.note, now=datetime.now(UTC),
            )
            session.commit()
    except ChecklistError as exc:
        status = 404 if exc.code == "line_not_in_scope" else 422
        raise HTTPException(status_code=status,
                            detail={"code": exc.code, "message": exc.detail}) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "runtime_db_unavailable", "error_class": exc.__class__.__name__},
        ) from exc
    return _env(result, request, "runtime-postgresql:desk-gas-day", [])


@router.get("/api/desk/gas-day/{gas_day}/reconciliation")
def get_gas_day_reconciliation(
    gas_day: date,
    request: Request,
    hub: str | None = Query(default=None, min_length=2, max_length=16),
    counterparty: str | None = Query(default=None, min_length=1, max_length=160),
    kind: str | None = Query(default=None, max_length=32),
    book_id: str | None = Query(default=None, min_length=1, max_length=64),
    breaks_only: bool = Query(default=False),
    format: str = Query(default="json", pattern=REFRESH_FORMAT_PATTERN,
                        description=FORMAT_DESCRIPTION),
):
    """Why the gas day's trades, confirmations and nominations disagree (SCHED-1).

    燃气日对账：按枢纽与交易对手核对交易、对手确认、提名与 TSO 匹配，逐项解释差异与下一步（只读）。

    Per hub (point) and counterparty: the bilateral deals delivering on the gas day, the
    counterparty's confirmation where imported, the nominated quantity and the TSO's matched
    quantity where the scheduling import holds them; each break with its arithmetic in plain
    words and the next thing to check, ordered by the time left to the hub's next cut-off and
    the MWh at risk, with an indicative cash-out at the approved rate. Scope is the caller's
    gas day (mandated books, else every book they may see); needs ``portfolio.read``.
    ``format=csv``: one row per break, fixed header (the GOV-1 export decision applies).
    Read only: nothing is nominated, confirmed or sent.
    """

    from datetime import UTC, datetime

    from sqlalchemy.exc import SQLAlchemyError

    from eurogas_nexus.application.caller import caller_of
    from eurogas_nexus.application.gas_day_reconciliation import (
        CSV_COLUMNS,
        ReconciliationError,
        csv_rows,
        reconciliation,
    )
    from eurogas_nexus.db.session import get_session_factory, resolve_database_url
    from eurogas_nexus.security.authorization import Permission, authorize

    principal = getattr(request.state, "identity", None)
    if principal is None or not authorize(principal, Permission.PORTFOLIO_READ).allowed:
        raise HTTPException(
            status_code=403,
            detail={"code": "permission_denied", "permission": Permission.PORTFOLIO_READ.value},
        )
    if resolve_database_url() is None:
        raise HTTPException(status_code=503, detail={"code": "runtime_db_not_configured"})
    try:
        with get_session_factory()() as session:
            payload = reconciliation(
                session, caller_of(request), gas_day, now=datetime.now(UTC), hub=hub,
                counterparty=counterparty, kind=kind, book_id=book_id, breaks_only=breaks_only,
            )
    except ReconciliationError as exc:
        status = 404 if exc.code == "book_not_in_scope" else 422
        raise HTTPException(status_code=status,
                            detail={"code": exc.code, "message": exc.detail}) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "runtime_db_unavailable", "error_class": exc.__class__.__name__},
        ) from exc
    if format == "csv":
        from eurogas_nexus.api.csv_export import csv_response

        return csv_response(csv_rows(payload), report=f"gas-day-reconciliation-{gas_day}",
                            columns=CSV_COLUMNS)
    return _env(payload, request, "runtime-postgresql:desk-gas-day-reconciliation", [])
