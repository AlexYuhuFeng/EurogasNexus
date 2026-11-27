"""Deal capture over HTTP: import exchange exports, the blotter, the ETRM entry sheet, the
end-of-day check and close, and the daily pack (SMALL_DESK_PLAN section 4, steps 1-2).

Reads need ``portfolio.read`` and show only the caller's books (the ORM applies book scope);
writes (an import, a manual deal, a close, sending a pack, the pack schedule) need
``portfolio.write`` and are audited. The risk pack needs ``risk.limits.read`` as well. Nothing
here places, sends or pre-fills an order, nominates, settles or books (AGENTS.md rule 8).

交易捕获接口：导入、交易记录簿、ETRM 录入表、日终核对与日结、每日报告；仅限本人账簿，写入有审计。
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool

from eurogas_nexus.api.routes.public.portfolio_common import env as _env

router = APIRouter(tags=["deals"])

MAX_UPLOAD_BYTES = 16 * 1024 * 1024
_SOURCE = "runtime-postgresql:desk-deals"


def _require(request: Request, permission_name: str) -> Any:
    from eurogas_nexus.security.authorization import Permission, authorize

    permission = Permission(permission_name)
    principal = getattr(request.state, "identity", None)
    if principal is None or not authorize(principal, permission).allowed:
        raise HTTPException(status_code=403, detail={"code": "permission_denied",
                                                     "permission": permission.value})
    return principal


def _session_factory():
    from eurogas_nexus.db.session import get_session_factory, resolve_database_url

    if resolve_database_url() is None:
        raise HTTPException(status_code=503, detail={"code": "runtime_db_not_configured"})
    return get_session_factory()


def _run(work, *, commit: bool = False):
    """Run ``work(session)`` with the store's errors as HTTP answers."""

    from sqlalchemy.exc import SQLAlchemyError

    from eurogas_nexus.application.deal_capture import DealCaptureError
    from eurogas_nexus.security.portfolio_scope import BookScopeViolation

    factory = _session_factory()
    try:
        with factory() as session:
            result = work(session)
            if commit:
                session.commit()
            return result
    except DealCaptureError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.detail()) from exc
    except BookScopeViolation as exc:
        raise HTTPException(status_code=403, detail={"code": "book_outside_scope",
                                                     "message": str(exc)}) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "runtime_db_unavailable", "error_class": exc.__class__.__name__},
        ) from exc


def _today() -> date:
    return datetime.now(UTC).date()


async def _body(request: Request) -> bytes:
    body = await request.body()
    if len(body) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail={"code": "file_too_large",
                                                     "message": f"at most {MAX_UPLOAD_BYTES} "
                                                                "bytes"})
    return body


# ----------------------------------------------------------------------------- reads


@router.get("/api/desk/deals/formats")
def get_deal_formats(request: Request) -> dict:
    """The export layouts the desk can import, the ETRM sheet layout, and file errors.

    交易文件格式与 ETRM 录入表布局（可编辑的格式文件）。
    """

    from eurogas_nexus.application.deal_capture import formats_catalogue

    _require(request, "portfolio.read")
    data = formats_catalogue()
    return _env(data, request, "deal-formats", data["errors"])


@router.get("/api/desk/deals")
def get_deals(
    request: Request,
    day: date | None = Query(default=None, description="Trade date; default today (UTC)"),
    trader: str | None = Query(default=None, max_length=128),
    hub: str | None = Query(default=None, max_length=16),
    venue: str | None = Query(default=None, max_length=32),
    book_id: str | None = Query(default=None, max_length=64),
    format: str = Query(default="json", pattern="^(json|csv)$"),
):
    """The day's deal blotter: each deal with where it came from, unread rows, totals.

    当日交易记录簿：每笔交易的来源（文件与行号或手工录入）、无法读取的行、按枢纽与交割期汇总。
    """

    from eurogas_nexus.application.deal_capture import blotter, books_choice

    _require(request, "portfolio.read")
    when = day or _today()

    def work(session):
        data = blotter(session, day=when, trader=trader, hub=hub, venue=venue, book_id=book_id)
        data["books"] = books_choice(session)
        return data

    data = _run(work)
    if format == "csv":
        from eurogas_nexus.api.csv_export import csv_response

        rows = [{**{k: v for k, v in row.items() if k != "source"},
                 "source": (f"{row['source'].get('file_name')} line {row['source'].get('line')}"
                            if row["source"]["kind"] == "file" else
                            f"entered by hand by {row['source'].get('entered_by')}")}
                for row in data["deals"]]
        return csv_response(rows, report=f"deal-blotter-{when.isoformat()}")
    warnings = [] if not data["unreadable"] else [
        f"{len(data['unreadable'])} row(s) of the day's files could not be read"]
    return _env(data, request, _SOURCE, warnings)


@router.get("/api/desk/deals/history")
def get_deal_history(request: Request, deal_key: str = Query(min_length=3, max_length=200)
                     ) -> dict:
    """Every version of one deal, oldest first (corrections and cancellations kept)."""

    from eurogas_nexus.application.deal_capture import deal_history

    _require(request, "portfolio.read")
    return _env(_run(lambda session: deal_history(session, deal_key)), request, _SOURCE, [])


@router.get("/api/desk/deals/etrm-sheet")
def get_etrm_sheet(
    request: Request,
    day: date | None = Query(default=None),
    format: str = Query(default="xlsx", pattern="^(csv|xlsx)$"),
):
    """The day's deals laid out as the ETRM entry template (``etrm_entry_sheet.toml``).

    按 ETRM 录入模板布局生成当日交易（CSV 或 XLSX）。
    """

    from eurogas_nexus.api.csv_export import file_response
    from eurogas_nexus.application.deal_capture import etrm_sheet

    _require(request, "portfolio.read")
    when = day or _today()
    content, media, name = _run(lambda session: etrm_sheet(session, day=when,
                                                           file_format=format))
    return file_response(content, media_type=media, file_name=name, file_format=format)


@router.get("/api/desk/deals/pnl")
def get_deal_pnl(request: Request, day: date | None = Query(default=None)) -> dict:
    """Day, month and year to date P&L of captured deals by trader and hub (desk estimate).

    捕获交易的当日、月初至今与年初至今损益（交易台估算，按交易员与枢纽）。
    """

    from eurogas_nexus.application.caller import caller_of
    from eurogas_nexus.application.deal_capture import day_pnl, day_status

    _require(request, "portfolio.read")
    when = day or _today()

    def work(session):
        pnl = day_pnl(session, caller_of(request), day=when)
        public = {key: pnl[key] for key in ("business_date", "by_trader_hub", "totals",
                                            "not_valued", "simulated_marks", "method")}
        public["status"] = day_status(session, when)
        return public, pnl["warnings"]

    data, warnings = _run(work)
    return _env(data, request, _SOURCE, warnings)


@router.get("/api/desk/deals/pack")
def get_daily_pack(
    request: Request,
    day: date | None = Query(default=None),
    kind: str = Query(default="management", pattern="^(management|risk)$"),
    language: str = Query(default="en", pattern="^(en|zh-CN)$"),
    format: str = Query(default="pdf", pattern="^(pdf|xlsx)$"),
):
    """The daily pack as a file, for sending by hand (the same files the e-mail carries).

    每日报告文件（PDF 或 XLSX，中英文），可手工发送。
    """

    from eurogas_nexus.api.csv_export import file_response
    from eurogas_nexus.application.caller import caller_of
    from eurogas_nexus.application.daily_pack import pack_data, render

    _require(request, "portfolio.read")
    if kind == "risk":
        _require(request, "risk.limits.read")
    when = day or _today()

    def work(session):
        data = pack_data(session, caller_of(request), day=when)
        return render(data, kind, language)

    pdf, xlsx, name = _run(work)
    if format == "pdf":
        return file_response(pdf, media_type="application/pdf", file_name=f"{name}.pdf",
                             file_format="pdf")
    return file_response(
        xlsx, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        file_name=f"{name}.xlsx", file_format="xlsx")


@router.get("/api/desk/deals/pack-schedule")
def get_pack_schedule(request: Request) -> dict:
    """When the daily pack is sent by itself, and whether recipient lists exist."""

    from eurogas_nexus.application.daily_pack import KINDS, load_schedule, recipient_channels

    _require(request, "portfolio.read")

    def work(session):
        data = load_schedule(session)
        data["recipients"] = {kind: len(recipient_channels(session, kind)) for kind in KINDS}
        return data

    return _env(_run(work), request, _SOURCE, [])


# ----------------------------------------------------------------------------- writes


@router.post(
    "/api/desk/deals/import",
    openapi_extra={"requestBody": {"required": True, "content": {
        "text/csv": {"schema": {"type": "string"}},
        "application/octet-stream": {"schema": {"type": "string", "format": "binary"}}},
        "description": "The exchange export as sent by the exchange (CSV)"}},
)
async def post_deal_import(
    request: Request,
    book_id: str = Query(min_length=1, max_length=64),
    file_name: str = Query(default="upload.csv", min_length=1, max_length=256),
    format: str | None = Query(default=None, max_length=64,
                               description="A format name; omitted: recognised by headers"),
) -> dict:
    """Import an exchange export into a book: new, corrected, cancelled, repeated, unread.

    导入交易所导出文件：新增、更正、取消、重复与无法读取的行逐一报告。
    """

    from eurogas_nexus.application.caller import caller_of
    from eurogas_nexus.application.deal_capture import import_file

    _require(request, "portfolio.write")
    body = await _body(request)
    caller = caller_of(request)

    def work(session):
        return import_file(session, caller, body, file_name=file_name, book_id=book_id,
                           format_name=format, origin="upload").as_dict()

    data = await run_in_threadpool(lambda: _run(work, commit=True))
    warnings = [] if not data["problems"] else [
        f"{len(data['problems'])} row(s) could not be read; they are listed on the blotter"]
    return _env(data, request, _SOURCE, warnings)


class ManualDeal(BaseModel):
    """A deal entered by hand (canonical field names); marked as entered by hand."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    deal_key: str | None = Field(default=None, max_length=200)
    venue: str | None = Field(default=None, max_length=32)
    venue_trade_id: str | None = Field(default=None, max_length=128)
    trade_date: date | None = None
    trade_time: datetime | None = None
    trader: str | None = Field(default=None, max_length=128)
    counterparty: str | None = Field(default=None, max_length=160)
    cleared: bool | None = None
    hub: str | None = Field(default=None, max_length=16)
    product: str | None = Field(default=None, max_length=32)
    delivery_start: date | None = None
    delivery_end: date | None = None
    side: str | None = Field(default=None, pattern="^(buy|sell)$")
    volume: str | None = Field(default=None, max_length=32, pattern=r"^-?[0-9]+(\.[0-9]+)?$")
    volume_unit: str | None = Field(default=None, max_length=16)
    price: str | None = Field(default=None, max_length=32, pattern=r"^-?[0-9]+(\.[0-9]+)?$")
    price_unit: str | None = Field(default=None, max_length=16)
    physical: bool | None = None
    instrument: str | None = Field(default=None, max_length=16)
    fees: str | None = Field(default=None, max_length=32, pattern=r"^-?[0-9]+(\.[0-9]+)?$")
    fee_currency: str | None = Field(default=None, pattern="^[A-Z]{3}$")
    status: str | None = Field(default=None, pattern="^(live|cancelled)$")
    book: str = Field(min_length=1, max_length=64)


@router.post("/api/desk/deals/manual")
def post_manual_deal(body: ManualDeal, request: Request) -> dict:
    """Enter a broker or bilateral deal by hand, or correct or cancel one entered by hand.

    手工录入经纪或双边交易，或更正、取消手工交易（标注为手工录入并审计）。
    """

    from eurogas_nexus.application.caller import caller_of
    from eurogas_nexus.application.deal_capture import enter_manual_deal

    _require(request, "portfolio.write")
    values = body.model_dump(exclude_none=True)
    for name in ("cleared", "physical"):
        if name in values:
            values[name] = "yes" if values[name] else "no"
    for name in ("trade_date", "delivery_start", "delivery_end"):
        if name in values:
            values[name] = values[name].isoformat()
    if "trade_time" in values:
        moment = values["trade_time"]
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=UTC)
        values["trade_time"] = moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S")
    caller = caller_of(request)
    data = _run(lambda session: enter_manual_deal(session, caller, values), commit=True)
    return _env(data, request, _SOURCE, [])


class ResolveProblem(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    note: str = Field(min_length=3, max_length=300)


@router.post("/api/desk/deals/problems/{problem_id}/resolve")
def post_resolve_problem(problem_id: str, body: ResolveProblem, request: Request) -> dict:
    """Mark an unread row as dealt with (entered by hand, or not a deal), with a note."""

    from eurogas_nexus.application.caller import caller_of
    from eurogas_nexus.application.deal_capture import resolve_problem

    _require(request, "portfolio.write")
    caller = caller_of(request)
    data = _run(lambda session: resolve_problem(session, caller, problem_id, note=body.note),
                commit=True)
    return _env(data, request, _SOURCE, [])


@router.post(
    "/api/desk/deals/eod-check",
    openapi_extra={"requestBody": {"required": True, "content": {
        "text/csv": {"schema": {"type": "string"}}},
        "description": "The ETRM's trade export for the day (import_etrm_trades columns)"}},
)
async def post_eod_check(
    request: Request,
    day: date | None = Query(default=None),
    file_name: str = Query(default="etrm-export.csv", min_length=1, max_length=256),
) -> dict:
    """Compare the day's captured deals with the ETRM export; every difference listed.

    日终核对：当日捕获交易与 ETRM 导出逐项比对，全部差异列出（不写入）。
    """

    from eurogas_nexus.application.deal_capture import eod_check

    _require(request, "portfolio.read")
    body = await _body(request)
    try:
        text = body.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = body.decode("cp1252", errors="replace")
    when = day or _today()
    data = await run_in_threadpool(
        lambda: _run(lambda session: eod_check(session, day=when, etrm_text=text,
                                               etrm_file_name=file_name)))
    return _env(data, request, _SOURCE, [])


class CloseDay(BaseModel):
    model_config = ConfigDict(extra="forbid")
    day: date
    etrm_file_name: str = Field(min_length=1, max_length=256)
    etrm_csv: str = Field(min_length=1, max_length=MAX_UPLOAD_BYTES)
    #: Per difference id, the person's note on it (every difference needs one).
    acknowledgements: dict[str, str] = Field(default_factory=dict, max_length=5000)
    note: str | None = Field(default=None, max_length=500)


@router.post("/api/desk/deals/close")
def post_close_day(body: CloseDay, request: Request) -> dict:
    """Close the day once every difference is acknowledged by the signed-in person; audited.

    日结：每项差异均由当前登录人员确认后关闭当日，并记录在审计轨迹中。
    """

    from eurogas_nexus.application.caller import caller_of
    from eurogas_nexus.application.deal_capture import close_day

    _require(request, "portfolio.write")
    caller = caller_of(request)
    data = _run(lambda session: close_day(
        session, caller, day=body.day, etrm_text=body.etrm_csv,
        etrm_file_name=body.etrm_file_name, acknowledgements=body.acknowledgements,
        note=body.note), commit=True)
    return _env(data, request, _SOURCE, [])


class SendPack(BaseModel):
    model_config = ConfigDict(extra="forbid")
    day: date | None = None
    kinds: list[str] = Field(default_factory=lambda: ["management", "risk"], max_length=2)
    languages: list[str] = Field(default_factory=lambda: ["en", "zh-CN"], max_length=2)


@router.post("/api/desk/deals/pack/send")
def post_send_pack(body: SendPack, request: Request) -> dict:
    """Queue the daily packs for e-mail to the configured recipient lists (a trader's click).

    将每日报告加入邮件发送队列（发送至已配置的收件人列表）。
    """

    from eurogas_nexus.application.caller import caller_of
    from eurogas_nexus.application.daily_pack import queue_packs

    _require(request, "portfolio.write")
    if "risk" in body.kinds:
        _require(request, "risk.limits.read")
    caller = caller_of(request)
    data = _run(lambda session: queue_packs(
        session, caller, day=body.day or _today(), kinds=body.kinds,
        languages=body.languages, trigger="click"), commit=True)
    return _env({"queued": data}, request, _SOURCE, [])


class PackSchedule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool
    at_local: str = Field(default="18:30", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    timezone: str = Field(default="Europe/London", max_length=64)
    weekdays: list[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4], max_length=7)
    kinds: list[str] = Field(default_factory=lambda: ["management", "risk"], max_length=2)
    languages: list[str] = Field(default_factory=lambda: ["en", "zh-CN"], max_length=2)


@router.put("/api/desk/deals/pack-schedule")
def put_pack_schedule(body: PackSchedule, request: Request) -> dict:
    """Turn the scheduled daily pack on or off and set its time (audited)."""

    from eurogas_nexus.application.caller import caller_of
    from eurogas_nexus.application.daily_pack import save_schedule
    from eurogas_nexus.application.deal_capture import actor_of

    _require(request, "portfolio.write")
    actor = actor_of(caller_of(request))
    data = _run(lambda session: save_schedule(session, body.model_dump(), actor=actor,
                                              now=datetime.now(UTC)), commit=True)
    return _env(data, request, _SOURCE, [])
