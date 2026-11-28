"""The regas auction desk over HTTP (Desk -> Cargoes -> Regas auctions).

Reads need ``portfolio.read`` and show only the caller's books (the ORM applies book scope);
writes (open a case, change it, save a snapshot, close it) need ``portfolio.write`` and are
audited. The what-if reads the one position source and the limits service read-only (limits
rows need ``risk.limits.read`` as everywhere). Nothing here bids, places, sends or pre-fills an
order, nominates or books (AGENTS.md rule 8).

再气化档期竞拍接口：读取限本人账簿；写入需交易权限并记入审计；不出价、不下单、不提名、不记账。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from eurogas_nexus.api.routes.public.portfolio_common import env as _env

router = APIRouter(tags=["regas-auctions"])

_SOURCE = "runtime-postgresql:desk-regas-auctions"


def _require(request: Request, permission_name: str) -> Any:
    from eurogas_nexus.security.authorization import Permission, authorize

    permission = Permission(permission_name)
    principal = getattr(request.state, "identity", None)
    if principal is None or not authorize(principal, permission).allowed:
        raise HTTPException(status_code=403, detail={"code": "permission_denied",
                                                     "permission": permission.value})
    return principal


def _run(work, *, commit: bool = False):
    from sqlalchemy.exc import SQLAlchemyError

    from eurogas_nexus.application.regas_auction import RegasAuctionCaseError
    from eurogas_nexus.db.session import get_session_factory, resolve_database_url
    from eurogas_nexus.domain.deals.formats import FormatError
    from eurogas_nexus.domain.lng.regas_auction import RegasAuctionError
    from eurogas_nexus.security.portfolio_scope import BookScopeViolation

    if resolve_database_url() is None:
        raise HTTPException(status_code=503, detail={"code": "runtime_db_not_configured"})
    try:
        with get_session_factory()() as session:
            result = work(session)
            if commit:
                session.commit()
            return result
    except RegasAuctionCaseError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.detail()) from exc
    except (RegasAuctionError, FormatError) as exc:
        raise HTTPException(status_code=422, detail={"code": "case_invalid",
                                                     "message": str(exc)}) from exc
    except BookScopeViolation as exc:
        raise HTTPException(status_code=403, detail={"code": "book_outside_scope",
                                                     "message": str(exc)}) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail={
            "code": "runtime_db_unavailable", "error_class": exc.__class__.__name__}) from exc


class CaseBody(BaseModel):
    """A case's inputs; ``application/regas_auction.normalise`` checks every value."""

    model_config = ConfigDict(extra="forbid")
    book_id: str | None = Field(default=None, max_length=64)
    version: int | None = Field(default=None, ge=1)
    title: str | None = Field(default=None, max_length=200)
    terminal: dict[str, Any]
    slot: dict[str, Any]
    auction: dict[str, Any]
    owner: dict[str, Any]
    offer: dict[str, Any]
    profile: dict[str, Any] | None = None
    delay_days: int | None = Field(default=None, ge=0, le=31)
    costs: dict[str, Any] | None = None
    prices: dict[str, Any] | None = None
    fx: str | None = Field(default=None, max_length=32)
    rate_pct: str | None = Field(default=None, max_length=32)


class SnapshotBody(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    note: str = Field(default="", max_length=500)


class CloseBody(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    outcome: str = Field(pattern="^(won|lost|lapsed)$")
    note: str = Field(min_length=3, max_length=1000)


def _values(body: CaseBody) -> dict[str, Any]:
    return body.model_dump(exclude={"book_id", "version"}, exclude_none=True)


@router.get("/api/desk/regas-auctions")
def get_cases(request: Request, state: str | None = Query(default=None,
                                                          pattern="^(open|won|lost|lapsed)$")
              ) -> dict:
    """The desk's regas auction cases, open first, with what a new case is picked from.

    交易台再气化竞拍案例（进行中优先），以及新案例可选的接收站、货主与账簿。
    """

    from eurogas_nexus.application.regas_auction import choices, list_cases

    _require(request, "portfolio.read")
    data = _run(lambda session: {"cases": list_cases(session, state=state),
                                 "choices": choices(session)})
    return _env(data, request, _SOURCE, [])


@router.post("/api/desk/regas-auctions")
def post_case(body: CaseBody, request: Request) -> dict:
    """Open a case when an auction is announced (audited).

    竞拍公告后建立案例（记入审计）。
    """

    from eurogas_nexus.application.caller import caller_of
    from eurogas_nexus.application.regas_auction import create_case

    _require(request, "portfolio.write")
    caller = caller_of(request)
    data = _run(lambda session: create_case(session, caller, body.book_id, _values(body)),
                commit=True)
    return _env(data, request, _SOURCE, [])


@router.get("/api/desk/regas-auctions/{case_id}")
def get_case(case_id: str, request: Request) -> dict:
    """The case and its answer now: the most to bid, headroom, what drives it, the hedges.

    案例及当前结论：最高出价、余量、驱动因素与对冲。
    """

    from eurogas_nexus.application.caller import caller_of
    from eurogas_nexus.application.regas_auction import case_answer

    _require(request, "portfolio.read")
    caller = caller_of(request)
    data = _run(lambda session: case_answer(session, caller, case_id))
    warnings = []
    if data["answer"].get("simulated"):
        warnings.append("Simulated prices: an illustration, not a bid level.")
    return _env(data, request, _SOURCE, warnings)


@router.put("/api/desk/regas-auctions/{case_id}")
def put_case(case_id: str, body: CaseBody, request: Request) -> dict:
    """Change a case's inputs (the auction level, an entered cost, a price by hand); audited.

    修改案例输入（竞拍价位、手工成本或价格），记入审计。
    """

    from eurogas_nexus.application.caller import caller_of
    from eurogas_nexus.application.regas_auction import update_case

    _require(request, "portfolio.write")
    if body.version is None:
        raise HTTPException(status_code=422, detail={"code": "version_required",
                                                     "message": "send the version you read"})
    caller = caller_of(request)
    data = _run(lambda session: update_case(session, caller, case_id, _values(body),
                                            version=body.version), commit=True)
    return _env(data, request, _SOURCE, [])


@router.get("/api/desk/regas-auctions/{case_id}/snapshots")
def get_snapshots(case_id: str, request: Request) -> dict:
    """Every snapshot saved during the window, oldest first.

    竞拍期间保存的全部快照。
    """

    from eurogas_nexus.application.regas_auction import snapshots

    _require(request, "portfolio.read")
    data = _run(lambda session: {"snapshots": snapshots(session, case_id)})
    return _env(data, request, _SOURCE, [])


@router.post("/api/desk/regas-auctions/{case_id}/snapshots")
def post_snapshot(case_id: str, body: SnapshotBody, request: Request) -> dict:
    """Keep the answer a trader acted on: inputs, prices with times and sources, result.

    保存交易员据以操作的结论：输入、价格（含时间与来源）与结果。
    """

    from eurogas_nexus.application.caller import caller_of
    from eurogas_nexus.application.regas_auction import save_snapshot

    _require(request, "portfolio.write")
    caller = caller_of(request)
    data = _run(lambda session: save_snapshot(session, caller, case_id, note=body.note),
                commit=True)
    return _env(data, request, _SOURCE, [])


@router.post("/api/desk/regas-auctions/{case_id}/close")
def post_close(case_id: str, body: CloseBody, request: Request) -> dict:
    """Close the case won, lost or lapsed with a note (audited; a won slot is not booked).

    以中标、落标或失效结案并备注（记入审计；中标档期不自动记账）。
    """

    from eurogas_nexus.application.caller import caller_of
    from eurogas_nexus.application.regas_auction import close_case

    _require(request, "portfolio.write")
    caller = caller_of(request)
    data = _run(lambda session: close_case(session, caller, case_id, outcome=body.outcome,
                                           note=body.note), commit=True)
    return _env(data, request, _SOURCE, [])


@router.get("/api/desk/regas-auctions/{case_id}/what-if")
def get_what_if(case_id: str, request: Request) -> dict:
    """The slot and its hedges put on, read-only: position, mandates and the owner's credit.

    假设中标并完成对冲（只读）：头寸、授权与货主信用额度的变化；不记账。
    """

    from eurogas_nexus.application.caller import caller_of
    from eurogas_nexus.application.regas_auction import what_if

    _require(request, "portfolio.read")
    caller = caller_of(request)
    data = _run(lambda session: what_if(session, caller, case_id))
    return _env(data, request, _SOURCE, ["A what-if: nothing is booked, ordered or nominated."])


@router.get("/api/desk/regas-auctions/{case_id}/report")
def get_report(
    case_id: str,
    request: Request,
    language: str = Query(default="en", pattern="^(en|zh-CN)$"),
    format: str = Query(default="pdf", pattern="^(pdf|xlsx)$"),
):
    """The case on one page, PDF or XLSX, English or Chinese, for the emailed risk pack.

    案例单页报告（PDF 或 XLSX，中英文），可随风险报告邮件发送。
    """

    from eurogas_nexus.api.csv_export import file_response
    from eurogas_nexus.application.caller import caller_of
    from eurogas_nexus.application.regas_auction import report

    _require(request, "portfolio.read")
    caller = caller_of(request)
    pdf, xlsx, name = _run(lambda session: report(session, caller, case_id, lang=language))
    if format == "pdf":
        return file_response(pdf, media_type="application/pdf", file_name=f"{name}.pdf",
                             file_format="pdf")
    return file_response(
        xlsx, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        file_name=f"{name}.xlsx", file_format="xlsx")
