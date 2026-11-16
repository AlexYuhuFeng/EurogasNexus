"""Market reports: generate, list, reopen and read as HTML (``/api/reports/...``).

A report is assembled from the catalogue's sections (``application/reports``), each read
through the entitled service its page uses, as the caller. The model may only reword a
section's rule commentary under the checked-note path, and only when the deployment enables
a provider and the caller holds the analysis capability. Every generated report is stored
once and can be reopened; reading it re-checks that the reader may see its sources and
books. Nothing here trades, nominates or settles.

- ``GET  /api/reports/catalogue``          kinds, sections, chart types, default plans
- ``POST /api/reports/plan``               a question to a validated, editable plan
- ``POST /api/reports/market``             generate (and store) a report
- ``GET  /api/reports/market``             stored reports the caller may open
- ``GET  /api/reports/market/{report_id}`` metadata of one report
- ``GET  /api/reports/market/{report_id}/html`` the report as one self-contained HTML file
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field

from eurogas_nexus.api.dependencies.ai_authority import ai_caller
from eurogas_nexus.api.routes.public.portfolio_common import env as _env

router = APIRouter(tags=["reports"])

PDF_NOTE = (
    "PDF is produced by printing the HTML (Print / Save as PDF in the viewer or any browser); "
    "the print stylesheet sets A4 pages, repeated table headers and unclipped charts."
)


class ReportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["daily", "weekly", "monthly", "situation", "ask"] = "daily"
    variant: Literal["morning", "eod"] | None = None
    audience: Literal["internal", "shareable"] = "internal"
    sections: list[str] | None = Field(default=None, max_length=20)
    hubs: list[str] | None = Field(default=None, max_length=8)
    countries: list[str] | None = Field(default=None, max_length=7)
    period_start: str | None = Field(default=None, max_length=10)
    period_end: str | None = Field(default=None, max_length=10)
    alert_id: str | None = Field(default=None, max_length=128)
    outage_id: str | None = Field(default=None, max_length=128)
    question: str | None = Field(default=None, max_length=500)
    language: Literal["en", "zh-CN"] = "en"
    use_model: bool = True


class PlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=3, max_length=500)
    audience: Literal["internal", "shareable"] = "internal"
    language: Literal["en", "zh-CN"] = "en"
    use_model: bool = True


def _db():
    from eurogas_nexus.db.session import get_session_factory, resolve_database_url

    if resolve_database_url() is None:
        raise HTTPException(status_code=503, detail={"code": "runtime_db_not_configured"})
    return get_session_factory()()


def balance_reader():
    """The NW Europe balance page's own read, for the report's balance section."""

    from eurogas_nexus.api.routes.public.fundamentals import get_nwe_balance

    response = get_nwe_balance(None, days=14, history_days=400, format="json")
    return response.get("data") if isinstance(response, dict) else None


def _unavailable(exc: Exception) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={"code": "runtime_db_unavailable", "error_class": exc.__class__.__name__},
    )


@router.get("/api/reports/catalogue")
def get_report_catalogue(request: Request) -> dict:
    """The report kinds and the sections a report is assembled from.

    报告目录：报告类型、可选章节、各章节的数据来源与图表类型。
    """

    from eurogas_nexus.application.reports.catalogue import catalogue_payload

    return _env({**catalogue_payload(), "pdf": PDF_NOTE}, request, "report-catalogue", [])


@router.post("/api/reports/plan")
def post_report_plan(body: PlanRequest, request: Request) -> dict:
    """Map a question to a report plan the user can edit before generating.

    将问题映射为可编辑的报告计划（结构化、经目录校验；无模型时使用关键词规则）。
    """

    from eurogas_nexus.api.routes.public.explain import _model_for
    from eurogas_nexus.application.reports.plan import plan_for_question

    principal = ai_caller(request)
    model = _model_for(principal) if body.use_model else None
    proposal = plan_for_question(body.question, audience=body.audience, model=model)
    return _env(proposal, request, "report-plan", [])


@router.post("/api/reports/market")
def post_market_report(body: ReportRequest, request: Request) -> dict:
    """Generate a market report as the caller, store it and return its metadata.

    生成市场报告：按调用者的数据权限与账簿范围组装、存档并返回元数据。
    """

    from sqlalchemy.exc import SQLAlchemyError

    from eurogas_nexus.api.routes.public.explain import _audit, _model_for
    from eurogas_nexus.application.caller import Caller
    from eurogas_nexus.application.reports.catalogue import PlanError
    from eurogas_nexus.application.reports.engine import ReportRefused, generate_report

    principal = ai_caller(request)
    model = _model_for(principal) if body.use_model else None
    raw = body.model_dump(exclude={"language", "use_model"}, exclude_none=True)
    trigger = {"type": "user"}
    if body.alert_id:
        trigger = {"type": "alert", "alert_id": body.alert_id}
    elif body.outage_id:
        trigger = {"type": "outage", "outage_id": body.outage_id}
    try:
        with _db() as session:
            report = generate_report(session, Caller(principal), raw, model=model,
                                     language=body.language, trigger=trigger,
                                     balance_reader=balance_reader)
            if model is not None:
                use = report.snapshot["model_use"]
                _audit(session, request, principal, f"report:{report.report_id}",
                       f"rewrote {use['passed']}/{use['attempted']}")
                session.commit()
    except PlanError as exc:
        raise HTTPException(status_code=422,
                            detail={"code": exc.code, "message": str(exc)}) from exc
    except ReportRefused as exc:
        raise HTTPException(status_code=422, detail={"code": exc.code, "message": str(exc),
                                                     **exc.detail}) from exc
    except SQLAlchemyError as exc:
        raise _unavailable(exc) from exc
    return _env({**report.metadata(), "pdf": PDF_NOTE,
                 "html_url": f"/api/reports/market/{report.report_id}/html"},
                request, "runtime-postgresql:market-report", [])


@router.get("/api/reports/market")
def list_market_reports(
    request: Request,
    kind: str | None = Query(None, pattern="^(daily|weekly|monthly|situation|ask)$"),
    limit: int = Query(50, ge=1, le=200),
) -> dict:
    """Stored reports the caller may open, newest first.

    已存档报告（仅列出调用者可查看的报告）。
    """

    from sqlalchemy.exc import SQLAlchemyError

    from eurogas_nexus.application.caller import Caller
    from eurogas_nexus.application.reports.store import list_reports

    try:
        with _db() as session:
            rows = list_reports(session, Caller(ai_caller(request)), kind=kind, limit=limit)
    except SQLAlchemyError as exc:
        raise _unavailable(exc) from exc
    return _env(rows, request, "runtime-postgresql:market-report", [])


def _record(session, report_id: str, request: Request):
    from eurogas_nexus.application.caller import Caller
    from eurogas_nexus.application.reports.store import reader_may_see
    from eurogas_nexus.db.models import MarketReportRecord

    record = session.get(MarketReportRecord, report_id)
    if record is None:
        raise HTTPException(status_code=404, detail={"code": "report_not_found"})
    allowed, reason = reader_may_see(session, record, Caller(ai_caller(request)))
    if not allowed:
        # Nothing about the report's contents is echoed to a reader who may not see it.
        raise HTTPException(status_code=403, detail={"code": reason})
    return record


@router.get("/api/reports/market/{report_id}")
def get_market_report(report_id: str, request: Request) -> dict:
    """One stored report's metadata: plan, sections, sources, model use, hashes.

    单份报告的元数据（计划、章节、来源、模型使用与哈希）。
    """

    from sqlalchemy.exc import SQLAlchemyError

    from eurogas_nexus.application.reports.store import metadata

    try:
        with _db() as session:
            data = metadata(_record(session, report_id, request))
    except SQLAlchemyError as exc:
        raise _unavailable(exc) from exc
    return _env({**data, "pdf": PDF_NOTE}, request, "runtime-postgresql:market-report", [])


@router.get("/api/reports/market/{report_id}/html", response_class=HTMLResponse)
def get_market_report_html(report_id: str, request: Request) -> HTMLResponse:
    """The stored report as one self-contained HTML file (print it for the PDF).

    报告 HTML（自包含；打印即得 PDF）。
    """

    from sqlalchemy.exc import SQLAlchemyError

    try:
        with _db() as session:
            record = _record(session, report_id, request)
            html, title = record.html, record.title
    except SQLAlchemyError as exc:
        raise _unavailable(exc) from exc
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in title)[:80]
    return HTMLResponse(
        html,
        headers={
            "Content-Disposition": f'inline; filename="{safe}.html"',
            # The report runs no remote code and loads nothing: a strict policy costs nothing.
            "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; "
            "script-src 'unsafe-inline'; img-src data:; frame-ancestors 'self'",
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )
