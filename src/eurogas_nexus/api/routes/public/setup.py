"""First-run setup (Admin): the welcome flow's pages and the installation's setup state.

``GET /api/setup`` answers the pages, what each source needs and where the flow stands;
``PUT /api/setup`` records progress (in progress, completed, dismissed). Both ADMIN. Keys
entered in the flow go to ``PUT /api/credentials/{provider}`` and approvals to
``POST /api/sources/{source_id}/approve``: this route stores neither.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from eurogas_nexus.security.authorization import Permission, authorize
from eurogas_nexus.security.rate_limit import require_admin_rate_limit

router = APIRouter(tags=["setup"], dependencies=[Depends(require_admin_rate_limit)])


class SetupUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["in_progress", "completed", "dismissed"]
    step: str | None = Field(default=None, max_length=32)


def _admin(request: Request):
    principal = getattr(request.state, "identity", None)
    if principal is None:
        raise HTTPException(status_code=401, detail={"error": "principal_missing"})
    if not authorize(principal, Permission.IDENTITY_MANAGE).allowed:
        raise HTTPException(status_code=403, detail={"error": "permission_denied"})
    return principal


def _require_db() -> None:
    from eurogas_nexus.db.session import resolve_database_url

    if resolve_database_url() is None:
        raise HTTPException(
            status_code=503,
            detail={"code": "runtime_db_required", "message": "Setup needs the runtime DB."},
        )


def _env(data) -> dict:
    return {"data": data, "meta": {"research_only": False, "human_review_required": False}}


def _view(session) -> dict:
    from eurogas_nexus.application import first_run_setup as setup
    from eurogas_nexus.security.credentials import credential_store_configured

    state = setup.setup_state(session)
    return {
        "state": state,
        "show_on_sign_in": setup.show_on_sign_in(state),
        "catalogue": setup.setup_catalogue(),
        # Keys are stored encrypted with EUROGAS_NEXUS_SECRET_KEY; without it none can be saved.
        "key_storage_ready": credential_store_configured(),
        # Whether this deployment lets AI call an external model at all (forced off in trial
        # and release unless IT turns it on); a key can be stored either way.
        "ai_external_enabled": _ai_external_enabled(),
        # The LNG page's terminal tariffs item: what is held and from which source.
        "terminal_tariffs": setup.terminal_tariff_facts(session),
    }


def _ai_external_enabled() -> bool:
    from eurogas_nexus.core.config import Settings

    try:
        return bool(Settings.from_env().llm_external_provider_enabled)
    except Exception:  # noqa: BLE001 - a malformed setting reads as off
        return False


@router.get("/api/setup")
def read_setup(request: Request) -> dict:
    """The welcome flow's pages and the installation's setup state (ADMIN)."""

    from eurogas_nexus.db.session import get_session_factory

    _admin(request)
    _require_db()
    with get_session_factory()() as session:
        return _env(_view(session))


@router.put("/api/setup")
def write_setup(body: SetupUpdate, request: Request) -> dict:
    """Record the flow's progress: in progress (with the step), completed or dismissed."""

    from eurogas_nexus.application import first_run_setup as setup
    from eurogas_nexus.db.session import get_session_factory

    admin = _admin(request)
    _require_db()
    with get_session_factory()() as session:
        try:
            setup.update_setup_state(
                session, status=body.status, step=body.step, actor=admin.principal_id
            )
        except setup.SetupError as exc:
            session.rollback()
            raise HTTPException(
                status_code=422, detail={"code": "setup_invalid", "message": str(exc)}
            ) from exc
        session.commit()
        return _env(_view(session))
