"""SDK client for the scheduled shadow research runtime."""

from __future__ import annotations

from pydantic import BaseModel, Field

from eurogas_nexus_sdk import _http


class ShadowMonitorDTO(BaseModel):
    shadow_monitor_id: str
    strategy_id: str
    strategy_version_id: str
    baseline_run_id: str | None = None
    state: str
    schedule: dict = Field(default_factory=dict)
    created_by: str
    created_at_utc: str
    activated_at_utc: str | None = None
    paused_at_utc: str | None = None
    retired_at_utc: str | None = None
    last_evaluation_at_utc: str | None = None
    next_evaluation_at_utc: str | None = None
    latest_evaluation_id: str | None = None
    consecutive_failures: int = 0
    health_state: str = "OK"
    cumulative_shadow_pnl_gbp: float = 0.0
    current_exposure_mwh_per_day: float = 0.0
    research_only: bool = True


class ShadowEvaluationDTO(BaseModel):
    shadow_evaluation_id: str
    shadow_monitor_id: str
    strategy_version_id: str
    scheduled_for_utc: str
    started_at_utc: str | None = None
    decision_time_utc: str | None = None
    completed_at_utc: str | None = None
    state: str
    gas_day: str | None = None
    snapshot_id: str | None = None
    candidate_id: str | None = None
    missing_inputs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    result: dict | None = None
    risk_checks: list[dict] = Field(default_factory=list)


class ShadowAlertDTO(BaseModel):
    alert_id: str
    shadow_monitor_id: str
    shadow_evaluation_id: str | None = None
    alert_type: str
    severity: str
    state: str
    fingerprint: str
    summary: str
    evidence_refs: list[str] = Field(default_factory=list)
    first_seen_at_utc: str
    last_seen_at_utc: str
    occurrence_count: int
    acknowledged_at_utc: str | None = None
    acknowledged_by: str | None = None
    resolved_at_utc: str | None = None


class ShadowDriftDTO(BaseModel):
    drift_snapshot_id: str
    shadow_monitor_id: str
    baseline_run_id: str | None = None
    observation_window: dict = Field(default_factory=dict)
    state: str
    metrics: list[dict] = Field(default_factory=list)
    sample_size: int
    explanation: str
    created_at_utc: str


class ShadowRuntimeStatusDTO(BaseModel):
    scheduler: str
    last_heartbeat_at_utc: str | None = None
    active_monitors: int
    pending_evaluations: int
    failed_evaluations_24h: int
    duplicate_claims_prevented: int


def create_monitor(
    base_url: str,
    *,
    strategy_version_id: str,
    schedule: dict,
    baseline_run_id: str | None = None,
    activate: bool = True,
) -> ShadowMonitorDTO:
    response = _http.post(
        f"{base_url}/api/shadow-monitors",
        json={
            "strategy_version_id": strategy_version_id,
            "baseline_run_id": baseline_run_id,
            "schedule": schedule,
            "activate": activate,
        },
        timeout=15,
    )
    response.raise_for_status()
    return ShadowMonitorDTO(**response.json()["data"])


def list_monitors(base_url: str) -> list[ShadowMonitorDTO]:
    response = _http.get(f"{base_url}/api/shadow-monitors", timeout=15)
    response.raise_for_status()
    return [ShadowMonitorDTO(**row) for row in response.json()["data"]]


def get_monitor(base_url: str, monitor_id: str) -> ShadowMonitorDTO:
    response = _http.get(f"{base_url}/api/shadow-monitors/{monitor_id}", timeout=15)
    response.raise_for_status()
    return ShadowMonitorDTO(**response.json()["data"])


def pause_monitor(base_url: str, monitor_id: str) -> ShadowMonitorDTO:
    response = _http.post(
        f"{base_url}/api/shadow-monitors/{monitor_id}/pause", json={}, timeout=15
    )
    response.raise_for_status()
    return ShadowMonitorDTO(**response.json()["data"])


def resume_monitor(base_url: str, monitor_id: str) -> ShadowMonitorDTO:
    response = _http.post(
        f"{base_url}/api/shadow-monitors/{monitor_id}/resume", json={}, timeout=15
    )
    response.raise_for_status()
    return ShadowMonitorDTO(**response.json()["data"])


def retire_monitor(base_url: str, monitor_id: str) -> ShadowMonitorDTO:
    response = _http.post(
        f"{base_url}/api/shadow-monitors/{monitor_id}/retire", json={}, timeout=15
    )
    response.raise_for_status()
    return ShadowMonitorDTO(**response.json()["data"])


def list_evaluations(base_url: str, monitor_id: str) -> list[ShadowEvaluationDTO]:
    response = _http.get(
        f"{base_url}/api/shadow-monitors/{monitor_id}/evaluations", timeout=15
    )
    response.raise_for_status()
    return [ShadowEvaluationDTO(**row) for row in response.json()["data"]]


def get_evaluation(base_url: str, evaluation_id: str) -> ShadowEvaluationDTO:
    response = _http.get(
        f"{base_url}/api/shadow-evaluations/{evaluation_id}", timeout=15
    )
    response.raise_for_status()
    return ShadowEvaluationDTO(**response.json()["data"])


def list_drift(base_url: str, monitor_id: str) -> list[ShadowDriftDTO]:
    response = _http.get(
        f"{base_url}/api/shadow-monitors/{monitor_id}/drift", timeout=15
    )
    response.raise_for_status()
    return [ShadowDriftDTO(**row) for row in response.json()["data"]]


def list_alerts(
    base_url: str,
    *,
    state: str | None = None,
    severity: str | None = None,
    monitor_id: str | None = None,
) -> list[ShadowAlertDTO]:
    params = {}
    if state:
        params["state"] = state
    if severity:
        params["severity"] = severity
    if monitor_id:
        params["monitor_id"] = monitor_id
    response = _http.get(f"{base_url}/api/shadow-alerts", params=params, timeout=15)
    response.raise_for_status()
    return [ShadowAlertDTO(**row) for row in response.json()["data"]]


def acknowledge_alert(base_url: str, alert_id: str, actor: str = "operator") -> ShadowAlertDTO:
    response = _http.post(
        f"{base_url}/api/shadow-alerts/{alert_id}/acknowledge",
        json={"actor": actor},
        timeout=15,
    )
    response.raise_for_status()
    return ShadowAlertDTO(**response.json()["data"])


def runtime_status(base_url: str) -> ShadowRuntimeStatusDTO:
    response = _http.get(f"{base_url}/api/shadow-runtime/status", timeout=15)
    response.raise_for_status()
    return ShadowRuntimeStatusDTO(**response.json()["data"])
