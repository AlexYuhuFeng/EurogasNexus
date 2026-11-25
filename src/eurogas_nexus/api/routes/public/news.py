"""News, policy and geopolitical events (NEWS-1).

``GET /api/news`` lists items from the registered public sources (REMIT messages the platform
holds, official feeds whose terms permit reuse), filtered by hub, country, event type, source
or time, with the items that touch the caller's book first. ``GET /api/news/{item_id}`` returns
one item with its source and terms, the exposures it touches, related items and the
deterministic note with its citations. ``POST /api/news/{item_id}/note`` asks for the AI note
("what this means for my book"): governed as the AI use ``news_note`` (switch, provider,
caller's analysis capability), every sentence cited and checked; when the model is off or its
note is refused, the rule note stands and the response says which the reader sees.

Decision support only: nothing is traded, nominated or sent.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict

from eurogas_nexus.api.routes.public.portfolio_common import env as _env

router = APIRouter(tags=["news"])


def _book_access(request: Request) -> bool:
    from eurogas_nexus.api.dependencies.row_entitlement import current_principal
    from eurogas_nexus.security.authorization import authorize

    principal = current_principal(request)
    return principal is not None and authorize(principal, "portfolio.read").allowed


def _db_unavailable(exc: Exception) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={"code": "runtime_db_unavailable", "error_class": exc.__class__.__name__},
    )


@router.get("/api/news")
def list_news(
    request: Request,
    hub: str | None = Query(default=None, max_length=16, description="Hub code, e.g. TTF"),
    country: str | None = Query(default=None, max_length=2, description="ISO 3166 alpha-2"),
    type: str | None = Query(  # noqa: A002 - the documented filter name
        default=None, max_length=24,
        description="outage, sanction, policy, weather, strike or geopolitical",
    ),
    source: str | None = Query(default=None, max_length=48, description="Registry source id"),
    since: str | None = Query(default=None, max_length=40, description="ISO 8601 instant"),
    mine: bool = Query(default=False, description="Only items that touch my book"),
    order: str = Query(default="relevance", description="relevance (my book first) or time"),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict:
    """News and events from registered public sources, my book's first.

    新闻与事件：来自登记的公开来源，触及我账簿的条目优先。
    """

    from sqlalchemy.exc import SQLAlchemyError

    from eurogas_nexus.application.news_reads import (
        NewsQueryError,
        list_items,
        parse_filters,
        sources_state,
    )
    from eurogas_nexus.db.session import get_session_factory, resolve_database_url
    from eurogas_nexus.security.portfolio_scope import visible_book_ids

    try:
        filters = parse_filters(hub=hub, country=country, event_type=type, source=source,
                                since=since, mine=mine, order=order, limit=limit)
    except NewsQueryError as exc:
        raise HTTPException(status_code=422, detail={"code": exc.code,
                                                     "message": exc.message}) from exc
    if resolve_database_url() is None:
        envelope = _env([], request, "runtime-db-not-configured",
                        ["Runtime DB is not configured; news is unavailable."])
        envelope["meta"]["sources"] = []
        return envelope
    book_allowed = _book_access(request)
    try:
        with get_session_factory()() as session:
            visible = visible_book_ids(session) if book_allowed else set()
            rows = list_items(session, filters, book_allowed=book_allowed,
                              visible_books=visible, now=datetime.now(UTC))
            sources = sources_state(session)
    except SQLAlchemyError as exc:
        raise _db_unavailable(exc) from exc
    warnings = [] if book_allowed else [
        "Matches to the book are shown only to a caller who may read the portfolio."
    ]
    envelope = _env(rows, request, "runtime-postgresql:news", warnings)
    envelope["meta"].update({"sources": sources, "order": filters.order,
                             "advisory": "Decision support: a person decides."})
    return envelope


@router.get("/api/news/{item_id}")
def get_news_item(item_id: str, request: Request) -> dict:
    """One item: its source and terms, what it touches in my book, related items and the
    rule note with its citations.

    单条新闻：来源与条款、触及的账簿敞口、相关条目及带引用的规则说明。
    """

    from sqlalchemy.exc import SQLAlchemyError

    from eurogas_nexus.application.news_reads import item_detail
    from eurogas_nexus.db.session import get_session_factory, resolve_database_url
    from eurogas_nexus.security.portfolio_scope import visible_book_ids

    if resolve_database_url() is None:
        raise HTTPException(status_code=503, detail={"code": "runtime_db_not_configured"})
    book_allowed = _book_access(request)
    try:
        with get_session_factory()() as session:
            visible = visible_book_ids(session) if book_allowed else set()
            detail = item_detail(session, item_id[:40], book_allowed=book_allowed,
                                 visible_books=visible, now=datetime.now(UTC))
    except SQLAlchemyError as exc:
        raise _db_unavailable(exc) from exc
    if detail is None:
        raise HTTPException(status_code=404, detail={"code": "not_found"})
    return _env(detail, request, "runtime-postgresql:news", [])


class NoteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    language: Literal["en", "zh-CN"] = "en"


@router.post("/api/news/{item_id}/note")
def post_news_note(item_id: str, body: NoteRequest, request: Request) -> dict:
    """"What this means for my book": the AI note when allowed and grounded, else the rule note.

    "对我的账簿意味着什么"：模型简述须逐句引用并通过依据校验，否则返回规则文本。
    """

    from sqlalchemy.exc import SQLAlchemyError

    from eurogas_nexus.api.routes.public.explain import _audit, _model_for
    from eurogas_nexus.application.news_note import assemble, build_evidence, model_note
    from eurogas_nexus.application.news_reads import item_dict
    from eurogas_nexus.application.news_relevance import firm_exposures, matches
    from eurogas_nexus.db.models import NewsItemRecord
    from eurogas_nexus.db.session import get_session_factory, resolve_database_url
    from eurogas_nexus.domain.ai.register import ai_use
    from eurogas_nexus.security.portfolio_scope import visible_book_ids

    if resolve_database_url() is None:
        raise HTTPException(status_code=503, detail={"code": "runtime_db_not_configured"})
    from eurogas_nexus.api.dependencies.ai_authority import ai_caller

    principal = ai_caller(request)
    model = _model_for(principal, use="news_note")
    book_allowed = _book_access(request)
    now = datetime.now(UTC)
    try:
        with get_session_factory()() as session:
            row = session.get(NewsItemRecord, item_id[:40])
            if row is None:
                raise HTTPException(status_code=404, detail={"code": "not_found"})
            item = item_dict(row)
            visible = visible_book_ids(session) if book_allowed else set()
            found = (matches(item, firm_exposures(session, now=now), visible)
                     if book_allowed else [])
            evidence = build_evidence(session, item, found, row)
            ai = None if model is None else model_note(model, evidence, language=body.language)
            note = assemble(item, found, evidence, ai=ai,
                            prompt_version=ai_use("news_note").prompt_version,
                            language=body.language)
            if model is not None:
                _audit(session, request, principal, f"news:{row.item_id}",
                       f"{note['basis']}; ai={note['ai']['status']}", action="ai.news_note",
                       model=model)
                session.commit()
    except SQLAlchemyError as exc:
        raise _db_unavailable(exc) from exc
    warnings = []
    if note["ai"]["status"] == "refused":
        warnings.append("The AI note did not pass the grounding check; the rule note is shown.")
    return _env({"item_id": item_id, **note}, request, "runtime-postgresql:news", warnings)
