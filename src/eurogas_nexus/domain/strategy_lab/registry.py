"""Versioned strategy-research registry domain.

A strategy is a long-lived research identity. A StrategyVersion is an immutable
semantic definition. A StrategyRun is an immutable evaluation of one exact
version against one exact evidence context. These types are pure domain
contracts and carry no execution semantics.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from eurogas_nexus.domain.ontology.vocabulary import (
    ParameterType,
    StrategyLifecycleStatus,
    StrategyRunStatus,
    StrategyRunType,
    StrategyVersionStatus,
)

__all__ = [
    "ParameterType",
    "StrategyLifecycleStatus",
    "StrategyRunStatus",
    "StrategyRunType",
    "StrategyVersionStatus",
]

STRATEGY_SCHEMA_VERSION = "strategy-definition/v1"
RUN_SCHEMA_VERSION = "strategy-run-manifest/v1"


class StrategyComponentSpec(BaseModel):
    """Typed strategy component.

    ``extension_json`` is reserved for future component semantics, not for the
    primary representation.
    """

    component_id: str = Field(min_length=1, max_length=128)
    component_type: str = Field(min_length=1, max_length=64)
    role: str = "signal"
    hubs: list[str] = Field(default_factory=list)
    tenors: list[str] = Field(default_factory=list)
    price_basis: str | None = None
    resource_id: str | None = None
    parameter_refs: list[str] = Field(default_factory=list)
    required_evidence: list[str] = Field(default_factory=list)
    extension_json: dict[str, Any] = Field(default_factory=dict)


class ParameterDefinition(BaseModel):
    parameter_id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=128)
    type: ParameterType
    unit: str | None = None
    description: str = ""
    min_value: float | int | None = None
    max_value: float | int | None = None
    allowed_values: list[str] = Field(default_factory=list)
    optimization_allowed: bool = False
    sensitivity_allowed: bool = False


class RiskControlSpec(BaseModel):
    max_ocm_allocation_pct: float = Field(default=80.0, ge=0, le=100)
    min_day_ahead_allocation_pct: float = Field(default=10.0, ge=0, le=100)
    max_single_market_volume_mwh_per_day: float | None = Field(default=None, ge=0)
    min_expected_margin_gbp_mwh: float | None = None
    stop_shadow_run_loss_gbp: float | None = None
    require_tso_access: bool = True


class EconomicAssumptions(BaseModel):
    transaction_cost_policy: str = "EXPLICIT_ZERO_UNMODELED"
    bid_ask_policy: str = "MID"
    slippage_policy: str = "UNMODELED"
    transport_cost_policy: str = "ROUTE_COST_REQUIRED"
    balancing_allowance_policy: str = "RESOURCE_DEFINED"
    fx_policy: str = "AS_OF_OR_LATEST_WITH_WARNING"
    tariff_source: str = "PUBLISHED_OR_OPERATOR"
    missing_data_policy: str = "BLOCK_OR_PARTIAL"
    capacity_policy: str = "UNKNOWN_BLOCKS"


class DataRequirements(BaseModel):
    hubs: list[str] = Field(default_factory=list)
    delivery_products: list[str] = Field(default_factory=list)
    price_bases: list[str] = Field(default_factory=list)
    source_classes: list[str] = Field(default_factory=list)
    max_source_age_seconds: int | None = None
    currencies: list[str] = Field(default_factory=list)
    require_fx: bool = False
    require_resources: bool = False
    require_capacity: bool = False
    require_tariffs: bool = False


class StrategyVersionDefinition(BaseModel):
    """Semantic definition stored in one immutable StrategyVersion."""

    components: list[StrategyComponentSpec] = Field(default_factory=list)
    parameter_definitions: list[ParameterDefinition] = Field(default_factory=list)
    parameter_values: dict[str, Any] = Field(default_factory=dict)
    risk_controls: RiskControlSpec = Field(default_factory=RiskControlSpec)
    economic_assumptions: EconomicAssumptions = Field(default_factory=EconomicAssumptions)
    data_requirements: DataRequirements = Field(default_factory=DataRequirements)
    evaluation_windows: list[dict[str, Any]] = Field(default_factory=list)

    def semantic_payload(self) -> dict[str, Any]:
        return {
            "components": [component.model_dump(mode="json") for component in self.components],
            "parameter_definitions": [
                definition.model_dump(mode="json")
                for definition in self.parameter_definitions
            ],
            "parameter_values": self.parameter_values,
            "risk_controls": self.risk_controls.model_dump(mode="json"),
            "economic_assumptions": self.economic_assumptions.model_dump(mode="json"),
            "data_requirements": self.data_requirements.model_dump(mode="json"),
            "evaluation_windows": self.evaluation_windows,
        }

    def content_hash(self) -> str:
        return canonical_content_hash(self.semantic_payload())


class StrategyRunManifest(BaseModel):
    """Effective-input evidence for one StrategyRun.

    The manifest is the reproducibility contract: it carries the exact run
    identity, strategy version identity and content hash, the complete
    strategy definition, parameters and assumptions, evidence snapshot, time
    boundary and engine/application provenance.
    """

    run_id: str
    run_type: StrategyRunType
    run_mode: str
    strategy_id: str
    strategy_name: str
    strategy_version_id: str
    version_number: int
    strategy_version_content_hash: str
    strategy_definition: dict[str, Any] = Field(default_factory=dict)
    schema_version: str = RUN_SCHEMA_VERSION
    strategy_schema_version: str = STRATEGY_SCHEMA_VERSION
    parameters: dict[str, Any] = Field(default_factory=dict)
    assumptions: dict[str, Any] = Field(default_factory=dict)
    parameter_values: dict[str, Any] = Field(default_factory=dict)
    economic_assumptions: dict[str, Any] = Field(default_factory=dict)
    evidence: dict[str, Any] = Field(default_factory=dict)
    time_boundary: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)
    evaluation_start_utc: datetime | None = None
    evaluation_end_utc: datetime | None = None
    data_cutoff_utc: datetime | None = None
    dataset_snapshot_id: str | None = None
    source_refs: list[str] = Field(default_factory=list)
    fx_observation_refs: list[str] = Field(default_factory=list)
    resource_snapshot_refs: list[str] = Field(default_factory=list)
    engine_version: str = "strategy-lab-evaluator/v1"
    backtest_engine_version: str | None = None
    application_version: str = "0.5.0"
    git_commit_sha: str | None = None
    deterministic_seed: str | None = None
    requested_by: str = "operator"
    trigger_type: str = "manual"
    correlation_request_id: str | None = None
    research_only: bool = True
    human_review_required: bool = True

    def semantic_payload(self) -> dict[str, Any]:
        """Canonical content used for the manifest hash.

        Run identity and wall-clock execution timestamps are stored in the
        manifest JSON but are intentionally excluded here: the hash identifies
        the effective reproducibility inputs, so two otherwise-identical
        evaluations of the same frozen version/evidence/seed produce the same
        hash even when their run ids and wall-clock times differ.
        """

        return {
            "run_type": self.run_type.value,
            "run_mode": self.run_mode,
            "strategy_id": self.strategy_id,
            "strategy_name": self.strategy_name,
            "strategy_version_id": self.strategy_version_id,
            "version_number": self.version_number,
            "strategy_version_content_hash": self.strategy_version_content_hash,
            "strategy_definition": self.strategy_definition,
            "schema_version": self.schema_version,
            "strategy_schema_version": self.strategy_schema_version,
            "parameters": self.parameters,
            "assumptions": self.assumptions,
            "parameter_values": self.parameter_values,
            "economic_assumptions": self.economic_assumptions,
            "evidence": self.evidence,
            "time_boundary": {
                "data_cutoff_utc": self.time_boundary.get("data_cutoff_utc")
            },
            "context": self.context,
            "data_cutoff_utc": _iso_or_none(self.data_cutoff_utc),
            "dataset_snapshot_id": self.dataset_snapshot_id,
            "source_refs": sorted(set(self.source_refs)),
            "fx_observation_refs": sorted(set(self.fx_observation_refs)),
            "resource_snapshot_refs": sorted(set(self.resource_snapshot_refs)),
            "engine_version": self.engine_version,
            "backtest_engine_version": self.backtest_engine_version,
            "application_version": self.application_version,
            "git_commit_sha": self.git_commit_sha,
            "deterministic_seed": self.deterministic_seed,
            "research_only": self.research_only,
            "human_review_required": self.human_review_required,
        }

    def content_hash(self) -> str:
        return canonical_content_hash(self.semantic_payload())


def canonical_content_hash(value: Any) -> str:
    """Return a deterministic SHA-256 hash over canonical semantic JSON.

    Hashes are audit/reproducibility identifiers, not security signatures.
    """

    canonical = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return f"sha256:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"


def valid_version_transition(
    current: StrategyVersionStatus,
    target: StrategyVersionStatus,
) -> bool:
    return (current, target) in {
        (StrategyVersionStatus.DRAFT, StrategyVersionStatus.FROZEN),
        (StrategyVersionStatus.DRAFT, StrategyVersionStatus.RETIRED),
        (StrategyVersionStatus.FROZEN, StrategyVersionStatus.RETIRED),
    }


def _iso_or_none(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()
