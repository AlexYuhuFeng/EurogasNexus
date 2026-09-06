"""SDK client for the versioned strategy registry.

These methods are research/decision-support only. The backend never creates
orders, trades or nominations from strategy-registry artifacts.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from eurogas_nexus_sdk import _http
from eurogas_nexus_sdk.strategy_lab import StrategyRunDTO


class StrategyDTO(BaseModel):
    """Long-lived strategy research identity."""

    strategy_id: str
    name: str
    description: str
    lifecycle_status: str
    current_version_id: str | None = None
    created_by: str
    created_at_utc: str
    updated_at_utc: str
    retired_at_utc: str | None = None
    tags: list[str] = Field(default_factory=list)
    research_only: bool = True


class StrategyVersionDTO(BaseModel):
    """Immutable semantic version of a strategy."""

    strategy_version_id: str
    strategy_id: str
    version_number: int
    schema_version: str
    status: str
    hypothesis: str
    definition_json: dict
    parent_version_id: str | None = None
    created_by: str
    created_at_utc: str
    frozen_at_utc: str | None = None
    content_hash: str
    research_only: bool = True


def list_strategies(base_url: str, *, limit: int = 200) -> list[StrategyDTO]:
    """List strategy identities, newest first."""

    response = _http.get(
        f"{base_url}/api/strategies", params={"limit": str(limit)}, timeout=15
    )
    response.raise_for_status()
    return [StrategyDTO(**row) for row in response.json()["data"]]


def create_strategy(
    base_url: str,
    *,
    name: str,
    strategy_id: str | None = None,
    description: str = "",
    tags: list[str] | None = None,
) -> StrategyDTO:
    """Create a strategy identity and return the stored row."""

    payload: dict = {"name": name, "description": description, "tags": tags or []}
    if strategy_id:
        payload["strategy_id"] = strategy_id
    response = _http.post(f"{base_url}/api/strategies", json=payload, timeout=15)
    response.raise_for_status()
    return StrategyDTO(**response.json()["data"])


def update_strategy(
    base_url: str,
    strategy_id: str,
    *,
    name: str | None = None,
    description: str | None = None,
    tags: list[str] | None = None,
) -> StrategyDTO:
    """Update editable metadata of a strategy research identity."""

    payload: dict = {}
    if name is not None:
        payload["name"] = name
    if description is not None:
        payload["description"] = description
    if tags is not None:
        payload["tags"] = tags
    response = _http.patch(
        f"{base_url}/api/strategies/{strategy_id}/metadata", json=payload, timeout=15
    )
    response.raise_for_status()
    return StrategyDTO(**response.json()["data"])


def get_strategy(base_url: str, strategy_id: str) -> StrategyDTO:
    """Fetch one strategy identity."""

    response = _http.get(f"{base_url}/api/strategies/{strategy_id}", timeout=15)
    response.raise_for_status()
    return StrategyDTO(**response.json()["data"])


def list_strategy_versions(
    base_url: str, strategy_id: str, *, limit: int = 100
) -> list[StrategyVersionDTO]:
    """List semantic versions for one strategy, newest first."""

    response = _http.get(
        f"{base_url}/api/strategies/{strategy_id}/versions",
        params={"limit": str(limit)},
        timeout=15,
    )
    response.raise_for_status()
    return [StrategyVersionDTO(**row) for row in response.json()["data"]]


def create_strategy_version(
    base_url: str,
    strategy_id: str,
    *,
    definition: dict,
    hypothesis: str = "",
    strategy_name: str | None = None,
    run_mode: str = "SHADOW_RUN",
    resource_contexts: list[dict] | None = None,
    price_observations: list[dict] | None = None,
    existing_shadow_pnl_gbp: float = 0.0,
) -> StrategyVersionDTO:
    """Create a new draft semantic version for a strategy.

    resource_contexts and price_observations are optional legacy
    evaluation inputs that the current evaluator requires. They are stored in
    the immutable version definition and hashed as part of it.
    """

    payload: dict = {
        "definition": definition,
        "hypothesis": hypothesis,
        "run_mode": run_mode,
        "resource_contexts": resource_contexts or [],
        "price_observations": price_observations or [],
        "existing_shadow_pnl_gbp": existing_shadow_pnl_gbp,
    }
    if strategy_name is not None:
        payload["strategy_name"] = strategy_name
    response = _http.post(
        f"{base_url}/api/strategies/{strategy_id}/versions",
        json=payload,
        timeout=15,
    )
    response.raise_for_status()
    return StrategyVersionDTO(**response.json()["data"])


def update_draft_version(
    base_url: str,
    version_id: str,
    *,
    definition: dict,
    hypothesis: str = "",
    strategy_name: str | None = None,
    run_mode: str = "BACKTEST",
    resource_contexts: list[dict] | None = None,
    price_observations: list[dict] | None = None,
) -> StrategyVersionDTO:
    """Replace a DRAFT version definition. Frozen versions are immutable."""

    payload: dict = {
        "definition": definition,
        "hypothesis": hypothesis,
        "run_mode": run_mode,
        "resource_contexts": resource_contexts or [],
        "price_observations": price_observations or [],
    }
    if strategy_name is not None:
        payload["strategy_name"] = strategy_name
    response = _http.put(
        f"{base_url}/api/strategy-versions/{version_id}/draft", json=payload, timeout=15
    )
    response.raise_for_status()
    return StrategyVersionDTO(**response.json()["data"])


def get_strategy_version(base_url: str, version_id: str) -> StrategyVersionDTO:
    """Fetch one strategy version."""

    response = _http.get(f"{base_url}/api/strategy-versions/{version_id}", timeout=15)
    response.raise_for_status()
    return StrategyVersionDTO(**response.json()["data"])


def freeze_strategy_version(base_url: str, version_id: str) -> StrategyVersionDTO:
    """Freeze a draft version, making it immutable."""

    response = _http.post(
        f"{base_url}/api/strategy-versions/{version_id}/freeze", json={}, timeout=15
    )
    response.raise_for_status()
    return StrategyVersionDTO(**response.json()["data"])


def fork_strategy_version(
    base_url: str,
    version_id: str,
    *,
    definition: dict | None = None,
    hypothesis: str | None = None,
) -> StrategyVersionDTO:
    """Fork a frozen version into a new draft."""

    payload: dict = {}
    if definition is not None:
        payload["definition"] = definition
    if hypothesis is not None:
        payload["hypothesis"] = hypothesis
    response = _http.post(
        f"{base_url}/api/strategy-versions/{version_id}/fork", json=payload, timeout=15
    )
    response.raise_for_status()
    return StrategyVersionDTO(**response.json()["data"])


def create_strategy_run(
    base_url: str,
    *,
    strategy_version_id: str,
    run_type: str = "EVALUATION",
    deterministic_seed: str | None = None,
    trigger_type: str = "MANUAL",
    correlation_request_id: str | None = None,
    evaluation_period_start_utc: str | None = None,
    evaluation_period_end_utc: str | None = None,
    economic_assumptions: dict | None = None,
    parameter_values: dict | None = None,
    experiment_id: str | None = None,
) -> StrategyRunDTO:
    """Evaluate or backtest one frozen strategy version.

    ``BACKTEST`` additionally requires ``evaluation_period_start_utc`` and
    ``evaluation_period_end_utc``; the backend enforces as-of temporal rules
    and persists decision events/series/attribution.
    """

    payload: dict = {
        "strategy_version_id": strategy_version_id,
        "run_type": run_type,
        "trigger_type": trigger_type,
    }
    if deterministic_seed is not None:
        payload["deterministic_seed"] = deterministic_seed
    if correlation_request_id is not None:
        payload["correlation_request_id"] = correlation_request_id
    if evaluation_period_start_utc is not None:
        payload["evaluation_period_start_utc"] = evaluation_period_start_utc
    if evaluation_period_end_utc is not None:
        payload["evaluation_period_end_utc"] = evaluation_period_end_utc
    if economic_assumptions is not None:
        payload["economic_assumptions"] = economic_assumptions
    if parameter_values is not None:
        payload["parameter_values"] = parameter_values
    if experiment_id is not None:
        payload["experiment_id"] = experiment_id
    response = _http.post(f"{base_url}/api/strategy-runs", json=payload, timeout=30)
    response.raise_for_status()
    return StrategyRunDTO(**response.json()["data"])


class BacktestDecisionEventDTO(BaseModel):
    """Persisted decision event of one backtest run."""

    event_id: str
    run_id: str
    experiment_id: str | None = None
    decision_sequence: int
    decision_time_utc: str
    gas_day: str
    gas_day_start_utc: str
    gas_day_end_utc: str
    outcome: str
    gross_indicative_pnl_gbp: float = 0.0
    modeled_costs_gbp: float = 0.0
    net_indicative_pnl_gbp: float = 0.0
    cumulative_net_indicative_pnl_gbp: float = 0.0
    ending_exposure_mwh_per_day: float = 0.0
    allocation_targets: list[dict] = Field(default_factory=list)
    missing_inputs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    price_evidence_refs: list[str] = Field(default_factory=list)
    fx_evidence_refs: list[str] = Field(default_factory=list)
    cost_evidence_refs: list[str] = Field(default_factory=list)
    resource_evidence_refs: list[str] = Field(default_factory=list)
    cost_trace: list[dict] = Field(default_factory=list)
    attribution: list[dict] = Field(default_factory=list)
    research_only: bool = True
    human_review_required: bool = True


class BacktestSeriesPointDTO(BaseModel):
    """Persisted cumulative net PnL/exposure series point."""

    series_point_id: str
    run_id: str
    decision_sequence: int
    decision_time_utc: str
    gas_day: str
    gross_indicative_pnl_gbp: float
    modeled_costs_gbp: float
    net_indicative_pnl_gbp: float
    cumulative_net_indicative_pnl_gbp: float
    ending_exposure_mwh_per_day: float
    drawdown_gbp: float = 0.0
    research_only: bool = True


class BacktestAttributionDTO(BaseModel):
    """Persisted backtest attribution row."""

    attribution_id: str
    run_id: str
    event_id: str
    decision_time_utc: str
    dimension: str
    key: str
    gross_indicative_pnl_gbp: float
    modeled_costs_gbp: float
    net_indicative_pnl_gbp: float
    quantity_mwh_per_day: float | None = None
    source_refs: list[str] = Field(default_factory=list)
    research_only: bool = True


class BacktestExperimentDTO(BaseModel):
    """Lightweight SINGLE_RUN experiment group."""

    experiment_id: str
    strategy_id: str
    base_strategy_version_id: str
    name: str
    hypothesis: str = ""
    experiment_type: str = "SINGLE_RUN"
    evaluation_period: dict = Field(default_factory=dict)
    run_ids: list[str] = Field(default_factory=list)
    status: str = "ACTIVE"
    created_by: str = "operator"
    created_at_utc: str
    updated_at_utc: str
    research_only: bool = True


def create_experiment(
    base_url: str,
    *,
    strategy_id: str,
    base_strategy_version_id: str,
    name: str,
    evaluation_period_start_utc: str,
    evaluation_period_end_utc: str,
    hypothesis: str = "",
    experiment_id: str | None = None,
) -> BacktestExperimentDTO:
    """Create a lightweight SINGLE_RUN backtest experiment group."""

    payload: dict = {
        "strategy_id": strategy_id,
        "base_strategy_version_id": base_strategy_version_id,
        "name": name,
        "hypothesis": hypothesis,
        "evaluation_period_start_utc": evaluation_period_start_utc,
        "evaluation_period_end_utc": evaluation_period_end_utc,
    }
    if experiment_id:
        payload["experiment_id"] = experiment_id
    response = _http.post(f"{base_url}/api/backtest-experiments", json=payload, timeout=15)
    response.raise_for_status()
    return BacktestExperimentDTO(**response.json()["data"])


def list_experiments(base_url: str) -> list[BacktestExperimentDTO]:
    """List persisted backtest experiments."""

    response = _http.get(f"{base_url}/api/backtest-experiments", timeout=15)
    response.raise_for_status()
    return [BacktestExperimentDTO(**row) for row in response.json()["data"]]


def get_experiment(base_url: str, experiment_id: str) -> BacktestExperimentDTO:
    """Fetch one persisted backtest experiment."""

    response = _http.get(
        f"{base_url}/api/backtest-experiments/{experiment_id}", timeout=15
    )
    response.raise_for_status()
    return BacktestExperimentDTO(**response.json()["data"])


def list_run_events(base_url: str, run_id: str) -> list[BacktestDecisionEventDTO]:
    """Fetch persisted backtest decision events for one run."""

    response = _http.get(f"{base_url}/api/strategy-runs/{run_id}/events", timeout=15)
    response.raise_for_status()
    return [BacktestDecisionEventDTO(**row) for row in response.json()["data"]]


def list_run_series(base_url: str, run_id: str) -> list[BacktestSeriesPointDTO]:
    """Fetch the persisted cumulative net PnL/exposure series."""

    response = _http.get(f"{base_url}/api/strategy-runs/{run_id}/series", timeout=15)
    response.raise_for_status()
    return [BacktestSeriesPointDTO(**row) for row in response.json()["data"]]


def list_run_attribution(base_url: str, run_id: str) -> list[BacktestAttributionDTO]:
    """Fetch persisted backtest attribution rows."""

    response = _http.get(
        f"{base_url}/api/strategy-runs/{run_id}/attribution", timeout=15
    )
    response.raise_for_status()
    return [BacktestAttributionDTO(**row) for row in response.json()["data"]]


def list_strategy_runs(
    base_url: str,
    *,
    strategy_id: str | None = None,
    strategy_version_id: str | None = None,
    run_type: str | None = None,
    limit: int = 100,
) -> list[StrategyRunDTO]:
    """List registry strategy runs, newest first."""

    params = {"limit": str(limit)}
    if strategy_id:
        params["strategy_id"] = strategy_id
    if strategy_version_id:
        params["strategy_version_id"] = strategy_version_id
    if run_type:
        params["run_type"] = run_type
    response = _http.get(f"{base_url}/api/strategy-runs", params=params, timeout=15)
    response.raise_for_status()
    return [StrategyRunDTO(**row) for row in response.json()["data"]]


def get_strategy_run(base_url: str, run_id: str) -> StrategyRunDTO:
    """Fetch one strategy run by id."""

    response = _http.get(f"{base_url}/api/strategy-runs/{run_id}", timeout=15)
    response.raise_for_status()
    return StrategyRunDTO(**response.json()["data"])
