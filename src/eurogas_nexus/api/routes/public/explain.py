""""Why?" next to an alert, an outage, a credit line, a mandate or a P&L figure; desk briefs.

``POST /api/analysis/explain`` takes only the object's kind and id; the server loads the
evidence the caller may see and returns two to four deterministic lines with their sources.
When the deployment enables a provider and the caller holds the analysis capability, the
model condenses them into one desk note that must pass ``application/ai_style`` checks;
otherwise the rule text is returned. The model never sees licensed rows the caller is not
entitled to, and every model call is audited under the caller's identity.

``POST /api/analysis/brief`` drafts the morning brief or end-of-day report from the same
reads (``application/desk_brief.py``) for a person to edit and send.

``POST /api/analysis/ask`` answers a question typed into the answer bar from the caller's
Today facts (``application/desk_ask.py``): the fact lines with their sources and as-of
always, and a checked model answer of two to five sentences when the model may be used.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from eurogas_nexus.api.dependencies.ai_authority import ai_authority_denial, ai_caller
from eurogas_nexus.api.routes.public.portfolio_common import env as _env

router = APIRouter(tags=["analysis"])


class ExplainRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subject: Literal["alert", "outage", "credit", "mandate", "pnl"]
    id: str = Field(min_length=1, max_length=200)
    language: Literal["en", "zh-CN"] = "en"


@router.post("/api/analysis/explain")
def post_explain(body: ExplainRequest, request: Request) -> dict:
    """Two or three sentences on why this object matters, with the evidence they rest on.

    解释"为什么"：基于证据的两三句话（规则文本，或经校验的模型简述）。
    """

    from sqlalchemy.exc import SQLAlchemyError

    from eurogas_nexus.application.caller import Caller
    from eurogas_nexus.application.explain import NotFound, explain
    from eurogas_nexus.db.session import get_session_factory, resolve_database_url

    if resolve_database_url() is None:
        raise HTTPException(status_code=503, detail={"code": "runtime_db_not_configured"})
    principal = ai_caller(request)
    model = _model_for(principal)
    try:
        with get_session_factory()() as session:
            result = explain(
                session,
                Caller(principal),
                body.subject,
                body.id,
                language=body.language,
                model=model,
            )
            if model is not None:
                _audit(session, request, principal, f"{body.subject}:{body.id}", result.basis,
                       model=model)
                session.commit()
    except NotFound as exc:
        raise HTTPException(status_code=404, detail={"code": "not_found"}) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "runtime_db_unavailable", "error_class": exc.__class__.__name__},
        ) from exc
    return _env(result.as_dict(), request, "runtime-postgresql", result.warnings)


class BriefRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["morning", "eod"] = "morning"
    language: Literal["en", "zh-CN"] = "en"


@router.post("/api/analysis/brief")
def post_brief(body: BriefRequest, request: Request) -> dict:
    """A morning brief or end-of-day draft from the caller's view of the desk, to edit and send.

    晨报/日终报告草稿：按调用者可见的数据分节生成，供人工编辑后发送。
    """

    from sqlalchemy.exc import SQLAlchemyError

    from eurogas_nexus.application.caller import Caller
    from eurogas_nexus.application.desk_brief import build_brief
    from eurogas_nexus.db.session import get_session_factory, resolve_database_url

    if resolve_database_url() is None:
        raise HTTPException(status_code=503, detail={"code": "runtime_db_not_configured"})
    principal = ai_caller(request)
    model = _model_for(principal, use="brief")
    try:
        with get_session_factory()() as session:
            brief = build_brief(
                session, Caller(principal), body.kind, model=model, language=body.language
            )
            if model is not None:
                _audit(session, request, principal, f"brief:{body.kind}", brief.lead_basis,
                       model=model)
                session.commit()
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "runtime_db_unavailable", "error_class": exc.__class__.__name__},
        ) from exc
    return _env(brief.as_dict(), request, "runtime-postgresql", brief.warnings)


class AskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=3, max_length=500)
    language: Literal["en", "zh-CN"] = "en"


@router.post("/api/analysis/ask")
def post_ask(body: AskRequest, request: Request) -> dict:
    """A question from the answer bar, answered from the facts the caller may already see.

    答案栏提问：依据调用者可见的"今日"事实作答；模型仅在规则与依据校验通过时给出简答。

    The facts are the Today read's (prices, outages, alerts, storage, the NW Europe balance;
    the book and limits only for a caller with ``portfolio.read``), each line with its source
    and as-of. ``ai`` says whether the model answered (``used``), was not available to this
    caller or deployment (``off``), or wrote text the checks refused (``refused``).
    """

    from sqlalchemy.exc import SQLAlchemyError

    from eurogas_nexus.application.caller import Caller
    from eurogas_nexus.application.desk_ask import ask
    from eurogas_nexus.application.desk_today import BALANCE_DAYS
    from eurogas_nexus.db.session import get_session_factory, resolve_database_url
    from eurogas_nexus.security.authorization import authorize

    if resolve_database_url() is None:
        raise HTTPException(status_code=503, detail={"code": "runtime_db_not_configured"})
    principal = ai_caller(request)
    model = _model_for(principal, answer=True, use="answer")
    book_allowed = authorize(principal, "portfolio.read").allowed

    def balance() -> dict | None:
        # The balance page's own read, so the answer and the page cannot disagree.
        from eurogas_nexus.api.routes.public.fundamentals import get_nwe_balance

        response = get_nwe_balance(request, days=1, history_days=max(7, BALANCE_DAYS),
                                   format="json")
        return response.get("data") if isinstance(response, dict) else None

    try:
        with get_session_factory()() as session:
            result = ask(
                session,
                Caller(principal),
                body.question,
                language=body.language,
                model=model,
                book_allowed=book_allowed,
                balance_reader=balance,
            )
            if model is not None and result.lines:
                _audit(session, request, principal, f"ask:{','.join(result.topics)}",
                       f"{result.basis}; ai={result.ai}", action="ai.ask", model=model)
                session.commit()
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "runtime_db_unavailable", "error_class": exc.__class__.__name__},
        ) from exc
    return _env(result.as_dict(), request, "runtime-postgresql:desk-today", result.warnings)


def _model_for(principal, *, answer: bool = False, use: str = "explain"):
    """A model call bound to the caller and one registered AI use, or ``None``.

    ``None`` when the deployment has no provider, the caller lacks the analysis capability,
    no key is stored, or the organisation switched the use off (GOV-1); the reader then gets
    the rule text. ``answer`` uses the answer budget (``ai_style.ANSWER_CALL``) instead of
    the note's. The returned :class:`GovernedModel` records each call's provenance for the
    audit row.
    """

    from eurogas_nexus.application.ai_controls import ai_use_enabled, governed_model
    from eurogas_nexus.application.ai_style import ANSWER_CALL, NOTE_CALL
    from eurogas_nexus.core.config import get_settings
    from eurogas_nexus.security.provider_keys import load_provider_api_key

    if not get_settings().llm_external_provider_enabled or ai_authority_denial(principal):
        return None
    if not ai_use_enabled(use):
        return None
    api_key = load_provider_api_key("DEEPSEEK") or load_provider_api_key("LLM")
    if not api_key:
        return None
    return governed_model(use, api_key=api_key, budget=ANSWER_CALL if answer else NOTE_CALL)


def _audit(
    session,
    request: Request,
    principal,
    resource: str,
    basis: str,
    *,
    action: str = "ai.explain",
    model=None,
) -> None:
    """Audit one AI request; with ``model``, its prompt version, model id and hashes (GOV-1)."""

    from eurogas_nexus.db.repositories.audit import record_audit_event

    request_id = getattr(request.state, "request_id", None)
    summary = model.audit_summary() if hasattr(model, "audit_summary") else None
    record_audit_event(
        session,
        event_type="governance.policy",
        principal=principal.principal_id[:64],
        action=action,
        resource=resource[:128],
        outcome=basis,
        severity="info",
        detail=f"{resource.split(':')[0]}; shown={basis}",
        source_system="analysis",
        now_utc=datetime.now(UTC),
        correlation_id=request_id[:64] if request_id else None,
        after_summary=summary,
    )
