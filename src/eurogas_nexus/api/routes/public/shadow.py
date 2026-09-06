"""Shadow research runtime public API.

These endpoints manage scheduled non-executing shadow research. No path in
this module can place an order, amend a trade, or submit a nomination.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

router = APIRouter(tags=["shadow-runtime"])


class ShadowMonitorCreateRequest(BaseModel):
    """Create and optionally activate one shadow monitor."""

    strategy_version_id: str = Field(min_length=1, max_length=128)
    baseline_run_id: str | None = Field(default=None, max_length=128)
    schedule: dict = Field(default_factory=dict)
    activate: bool = True


class ShadowAcknowledgeRequest(BaseModel):
    """Acknowledge a shadow alert (I saw this; not an approval)."""

    actor: str = Field(default="operator", max_length=64)


@router.post("/api/shadow-monitors")
def post_shadow_monitor(
    body: ShadowMonitorCreateRequest, request: Request
) -> dict:
    """Create/activate a shadow monitor after preflight validation."""

    from eurogas_nexus.application.shadow_runtime import create_shadow_monitor

    with _session() as session:
        try:
            data = create_shadow_monitor(
                session,
                strategy_version_id=body.strategy_version_id,
                baseline_run_id=body.baseline_run_id,
                schedule_json=body.schedule,
                created_by=_requested_by(request),
                activate=body.activate,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail={"code": "shadow_activation_blocked", "message": str(exc)},
            ) from exc
    _audit_action(
        request,
        "shadow.monitor.create",
        f"shadow_monitor:{data['shadow_monitor_id']}",
        "created",
    )
    return _env(data, request, source="runtime-postgresql")


@router.get("/api/shadow-monitors")
def get_shadow_monitors(
    request: Request,
    state: str | None = Query(default=None, max_length=32),
) -> dict:
    """List persisted shadow monitors."""

    from eurogas_nexus.db.repositories import shadow

    with _session() as session:
        data = shadow.list_monitors(session, state=state)
    return _env(data, request, source="runtime-postgresql")


@router.get("/api/shadow-monitors/{monitor_id}")
def get_shadow_monitor(monitor_id: str, request: Request) -> dict:
    """Return one shadow monitor, or 404."""

    from eurogas_nexus.db.repositories import shadow

    with _session() as session:
        row = shadow.get_monitor(session, monitor_id)
        if row is None:
            raise HTTPException(
                status_code=404, detail=f"Unknown shadow monitor: {monitor_id}"
            )
        data = shadow.monitor_payload(row)
    return _env(data, request, source="runtime-postgresql")


@router.post("/api/shadow-monitors/{monitor_id}/pause")
def pause_shadow_monitor(monitor_id: str, request: Request) -> dict:
    """Pause future scheduled evaluations without deleting history."""

    from eurogas_nexus.application.shadow_runtime import pause_monitor

    with _session() as session:
        try:
            data = pause_monitor(session, monitor_id=monitor_id)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    _audit_action(request, "shadow.monitor.pause", f"shadow_monitor:{monitor_id}", "paused")
    return _env(data, request, source="operator-input")


@router.post("/api/shadow-monitors/{monitor_id}/resume")
def resume_shadow_monitor(monitor_id: str, request: Request) -> dict:
    """Resume a paused/blocked monitor with a future schedule."""

    from eurogas_nexus.application.shadow_runtime import resume_monitor

    with _session() as session:
        try:
            data = resume_monitor(session, monitor_id=monitor_id)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    _audit_action(request, "shadow.monitor.resume", f"shadow_monitor:{monitor_id}", "resumed")
    return _env(data, request, source="operator-input")


@router.post("/api/shadow-monitors/{monitor_id}/retire")
def retire_shadow_monitor(monitor_id: str, request: Request) -> dict:
    """Retire a monitor; history and open alerts are preserved."""

    from eurogas_nexus.application.shadow_runtime import retire_monitor

    with _session() as session:
        try:
            data = retire_monitor(session, monitor_id=monitor_id)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    _audit_action(request, "shadow.monitor.retire", f"shadow_monitor:{monitor_id}", "retired")
    return _env(data, request, source="operator-input")


@router.get("/api/shadow-monitors/{monitor_id}/evaluations")
def get_shadow_evaluations(
    monitor_id: str,
    request: Request,
    limit: int = Query(default=100, ge=1, le=500),
) -> dict:
    """List evaluation history for one monitor."""

    from eurogas_nexus.db.repositories import shadow

    with _session() as session:
        if shadow.get_monitor(session, monitor_id) is None:
            raise HTTPException(
                status_code=404, detail=f"Unknown shadow monitor: {monitor_id}"
            )
        data = [
            row
            for row in shadow.list_evaluations(
                session, monitor_id=monitor_id, limit=limit
            )
            if _evaluation_visible(request, row)
        ]
    return _env(data, request, source="runtime-postgresql")


@router.get("/api/shadow-evaluations/{evaluation_id}")
def get_shadow_evaluation(evaluation_id: str, request: Request) -> dict:
    """Return one evaluation plus its risk checks."""

    from eurogas_nexus.db.repositories import shadow

    with _session() as session:
        row = shadow.get_evaluation(session, evaluation_id)
        if row is None:
            raise HTTPException(
                status_code=404, detail=f"Unknown shadow evaluation: {evaluation_id}"
            )
        data = shadow.evaluation_payload(row)
        data["risk_checks"] = shadow.list_risk_checks(session, evaluation_id)
        if row.candidate_id:
            candidate = shadow.get_candidate(session, row.candidate_id)
            if candidate is not None:
                data["candidate"] = shadow.candidate_payload(candidate)
    _require_evaluation_visible(request, data)
    return _env(data, request, source="runtime-postgresql")


@router.get("/api/shadow-monitors/{monitor_id}/drift")
def get_shadow_drift(monitor_id: str, request: Request) -> dict:
    """Return persisted drift snapshots for one monitor."""

    from eurogas_nexus.db.repositories import shadow

    with _session() as session:
        if shadow.get_monitor(session, monitor_id) is None:
            raise HTTPException(
                status_code=404, detail=f"Unknown shadow monitor: {monitor_id}"
            )
        data = shadow.list_drift_snapshots(session, monitor_id=monitor_id)
    return _env(data, request, source="runtime-postgresql")


@router.get("/api/shadow-alerts")
def get_shadow_alerts(
    request: Request,
    state: str | None = Query(default=None, max_length=32),
    severity: str | None = Query(default=None, max_length=16),
    monitor_id: str | None = Query(default=None, max_length=128),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict:
    """List persisted shadow alerts."""

    from eurogas_nexus.db.repositories import shadow

    with _session() as session:
        data = shadow.list_alerts(
            session,
            state=state,
            severity=severity,
            monitor_id=monitor_id,
            limit=limit,
        )
    return _env(data, request, source="runtime-postgresql")


@router.post("/api/shadow-alerts/{alert_id}/acknowledge")
def acknowledge_shadow_alert(
    alert_id: str,
    body: ShadowAcknowledgeRequest,
    request: Request,
) -> dict:
    """Acknowledge one shadow alert; never bypasses a risk blocker."""

    from eurogas_nexus.db.repositories import shadow

    with _session() as session:
        try:
            data = shadow.acknowledge_alert(
                session,
                alert_id=alert_id,
                acknowledged_by=body.actor,
                now_utc=datetime.now(UTC),
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _env(data, request, source="operator-input")


@router.get("/api/shadow-runtime/status")
def get_shadow_runtime_status(request: Request) -> dict:
    """Return scheduler heartbeat/runtime health summary."""

    from eurogas_nexus.db.repositories import shadow

    with _session() as session:
        data = shadow.runtime_status_payload(session)
    return _env(data, request, source="runtime-postgresql")




def _evaluation_visible(request: Request, data: dict) -> bool:
    from eurogas_nexus.api.dependencies.row_entitlement import current_principal
    from eurogas_nexus.domain.dataops.entitlement import derived_result_access

    return (
        derived_result_access(
            current_principal(request),
            data.get("source_systems") or [],
        ).outcome.value
        == "ALLOWED"
    )


def _require_evaluation_visible(request: Request, data: dict) -> None:
    if not _evaluation_visible(request, data):
        raise HTTPException(
            status_code=403,
            detail={
                "error": "entitlement_denied",
                "reason": "Shadow evaluation contains restricted source evidence (fail-closed).",
                "research_only": True,
                "human_review_required": True,
            },
        )

def _audit_action(request: Request, action: str, resource: str, outcome: str) -> None:
    try:
        from eurogas_nexus.application.audit_service import record_audit_event

        record_audit_event(
            event_type="governance.strategy",
            action=action,
            resource=resource,
            principal=_requested_by(request),
            outcome=outcome,
            severity="info",
            source_system="shadow-runtime",
        )
    except Exception:
        return


# --- session/envelope helpers ---------------------------------------------


class _ShadowSession:
    def __enter__(self):
        from eurogas_nexus.db.session import get_session_factory

        self.session = get_session_factory()()
        return self.session

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self.session.commit()
        else:
            self.session.rollback()
        self.session.close()


def _session():
    from eurogas_nexus.db.session import resolve_database_url

    if resolve_database_url() is None:
        raise HTTPException(
            status_code=503,
            detail={"code": "runtime_db_unavailable", "message": "Runtime DB is not configured."},
        )
    return _ShadowSession()


def _requested_by(request: Request) -> str:
    identity = getattr(request.state, "identity", None)
    if identity is not None and getattr(identity, "principal_id", None):
        return str(identity.principal_id)
    return "operator"


def _env(data, _request: Request, *, source: str) -> dict:
    return {
        "data": data,
        "meta": {
            "research_only": True,
            "human_review_required": True,
            "source_references": [source],
            "warnings": [],
        },
    }
