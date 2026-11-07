""""Why?" next to an alert, an outage, a credit line, a mandate or a P&L figure; desk briefs.

``POST /api/analysis/explain`` takes only the object's kind and id; the server loads the
evidence the caller may see and returns two to four deterministic lines with their sources.
When the deployment enables a provider and the caller holds the analysis capability, the
model condenses them into one desk note that must pass ``application/ai_style`` checks;
otherwise the rule text is returned. The model never sees licensed rows the caller is not
entitled to, and every model call is audited under the caller's identity.

``POST /api/analysis/brief`` drafts the morning brief or end-of-day report from the same
reads (``application/desk_brief.py``) for a person to edit and send.
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
                _audit(session, request, principal, f"{body.subject}:{body.id}", result.basis)
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
    model = _model_for(principal)
    try:
        with get_session_factory()() as session:
            brief = build_brief(
                session, Caller(principal), body.kind, model=model, language=body.language
            )
            if model is not None:
                _audit(session, request, principal, f"brief:{body.kind}", brief.lead_basis)
                session.commit()
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "runtime_db_unavailable", "error_class": exc.__class__.__name__},
        ) from exc
    return _env(brief.as_dict(), request, "runtime-postgresql", brief.warnings)


def _model_for(principal):
    """A model call bound to the caller, or ``None`` when the model may not be used."""

    from eurogas_nexus.core.config import get_settings
    from eurogas_nexus.llm import invoke_deepseek
    from eurogas_nexus.security.provider_keys import load_provider_api_key

    if not get_settings().llm_external_provider_enabled or ai_authority_denial(principal):
        return None
    api_key = load_provider_api_key("DEEPSEEK") or load_provider_api_key("LLM")
    if not api_key:
        return None

    def call(messages):
        result = invoke_deepseek(
            api_key=api_key,
            messages=messages,
            temperature=0.1,
            max_tokens=300,
            timeout_seconds=15.0,
        )
        return result.content if result.status == "success" else None

    return call


def _audit(session, request: Request, principal, resource: str, basis: str) -> None:
    from eurogas_nexus.db.repositories.audit import record_audit_event

    request_id = getattr(request.state, "request_id", None)
    record_audit_event(
        session,
        event_type="governance.policy",
        principal=principal.principal_id[:64],
        action="ai.explain",
        resource=resource[:128],
        outcome=basis,
        severity="info",
        detail=f"{resource.split(':')[0]}; shown={basis}",
        source_system="analysis",
        now_utc=datetime.now(UTC),
        correlation_id=request_id[:64] if request_id else None,
    )
