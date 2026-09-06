"""Constrained Strategy IR / DSL (CR-15).

The LLM may draft this JSON/YAML-serializable specification, but it can never
write arbitrary executable Python. Compilation maps the validated IR into the
existing CR-03 ``StrategyVersionDefinition`` so backtest/shadow consume the
same immutable domain model.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from eurogas_nexus.domain.ontology.vocabulary import (
    ParameterType,
    StrategyComponentType,
)
from eurogas_nexus.domain.strategy_lab.registry import (
    DataRequirements,
    EconomicAssumptions,
    ParameterDefinition,
    RiskControlSpec,
    StrategyComponentSpec,
    StrategyVersionDefinition,
)

STRATEGY_IR_SCHEMA_VERSION = "strategy-ir/v1"

_SUPPORTED_COMPONENT_TYPES = {item.value for item in StrategyComponentType}
_SUPPORTED_PRODUCTS = frozenset(
    {"DAY_AHEAD", "WITHIN_DAY", "MONTH_AHEAD", "WEEKEND", "BALANCE_OF_MONTH"}
)


class StrategyIROperator(StrEnum):
    GT = "GT"
    GTE = "GTE"
    LT = "LT"
    LTE = "LTE"
    EQ = "EQ"
    BETWEEN = "BETWEEN"


class StrategyIRCondition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feature_id: str
    operator: StrategyIROperator
    value: float
    value_2: float | None = None
    unit: str


class StrategyIRParameter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parameter_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{1,127}$")
    name: str = ""
    parameter_type: ParameterType
    unit: str | None = None
    default_value: Any = None
    min_value: float | None = None
    max_value: float | None = None
    allowed_values: list[str] = Field(default_factory=list)
    optimization_allowed: bool = False
    sensitivity_allowed: bool = False


class StrategyIRSizing(BaseModel):
    model_config = ConfigDict(extra="forbid")

    method: str = Field(pattern="^(RESOURCE_PERCENTAGE|FIXED_QUANTITY)$")
    max_pct: float = Field(default=20.0, ge=0, le=100)
    max_quantity_mwh_per_day: float | None = Field(default=None, ge=0)


class StrategyIRRiskControls(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_ocm_allocation_pct: float = Field(default=80.0, ge=0, le=100)
    min_day_ahead_allocation_pct: float = Field(default=10.0, ge=0, le=100)
    max_single_market_volume_mwh_per_day: float | None = Field(default=None, ge=0)
    min_expected_margin_gbp_mwh: float | None = None
    stop_shadow_run_loss_gbp: float | None = None
    require_tso_access: bool = True


class StrategyIREconomicAssumptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transaction_cost_policy: str = "EXPLICIT_ZERO_UNMODELED"
    fx_policy: str = "AS_OF_OR_LATEST_WITH_WARNING"
    missing_data_policy: str = "BLOCK_OR_PARTIAL"
    capacity_policy: str = "UNKNOWN_BLOCKS"
    fill_price_policy: str = "NEXT_ELIGIBLE"


class StrategyIRDataRequirements(BaseModel):
    model_config = ConfigDict(extra="forbid")

    series_ids: list[str] = Field(default_factory=list)
    max_source_age_seconds: int | None = Field(default=None, ge=0)
    require_fx: bool = False
    require_capacity: bool = False
    require_tariffs: bool = False


class StrategyIRComponent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    component_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{1,127}$")
    component_type: StrategyComponentType
    weight: float = Field(default=1.0, ge=0, le=100)
    conditions: list[StrategyIRCondition] = Field(default_factory=list)


class StrategyIRUniverse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    origin_hub: str = Field(min_length=2, max_length=32)
    destination_hub: str = Field(min_length=2, max_length=32)
    product: str = Field(default="DAY_AHEAD")
    currency: str = Field(default="GBP", max_length=8)


class StrategyIR(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = STRATEGY_IR_SCHEMA_VERSION
    hypothesis: str = Field(min_length=8, max_length=4000)
    universe: StrategyIRUniverse
    components: list[StrategyIRComponent] = Field(default_factory=list)
    parameters: list[StrategyIRParameter] = Field(default_factory=list)
    sizing: StrategyIRSizing = Field(default_factory=StrategyIRSizing)
    risk_controls: StrategyIRRiskControls = Field(default_factory=StrategyIRRiskControls)
    economic_assumptions: StrategyIREconomicAssumptions = Field(
        default_factory=StrategyIREconomicAssumptions
    )
    data_requirements: StrategyIRDataRequirements = Field(
        default_factory=StrategyIRDataRequirements
    )
    evaluation_windows: list[dict[str, str]] = Field(default_factory=list)


class StrategyIRValidationIssue(BaseModel):
    code: str
    detail: str
    field: str | None = None


class StrategyIRValidationResult(BaseModel):
    ok: bool
    issues: list[StrategyIRValidationIssue] = Field(default_factory=list)

    def add(self, code: str, detail: str, field: str | None = None) -> None:
        self.issues.append(StrategyIRValidationIssue(code=code, detail=detail, field=field))
        self.ok = False


def validate_strategy_ir(
    strategy_ir: StrategyIR,
    *,
    feature_catalog: dict[str, dict[str, Any]] | None = None,
    available_series: set[str] | None = None,
) -> StrategyIRValidationResult:
    """Semantically validate an IR before compilation.

    Checks features/versions/units/entities/products/operators/parameter ranges/
    sizing/risk controls/data requirements. Only valid IR may compile.
    """

    result = StrategyIRValidationResult(ok=True)
    features = feature_catalog or {}

    if (
        strategy_ir.universe.origin_hub.casefold()
        == strategy_ir.universe.destination_hub.casefold()
    ):
        result.add("STRATEGY_INVALID", "origin and destination hub are identical", "universe")
    if strategy_ir.universe.product not in _SUPPORTED_PRODUCTS:
        result.add(
            "INVALID_PRODUCT", f"unsupported product {strategy_ir.universe.product!r}", "universe"
        )
    if not strategy_ir.components:
        result.add("STRATEGY_INVALID", "at least one component is required", "components")
    for index, component in enumerate(strategy_ir.components):
        if component.component_type.value not in _SUPPORTED_COMPONENT_TYPES:
            result.add(
                "STRATEGY_INVALID",
                f"unsupported component type {component.component_type.value!r}",
                f"components.{index}",
            )
        for condition in component.conditions:
            metadata = features.get(condition.feature_id)
            if metadata is None:
                result.add(
                    "UNKNOWN_FEATURE",
                    f"feature {condition.feature_id!r} is unknown",
                    f"components.{index}.conditions",
                )
                continue
            output_unit = str(metadata.get("output_unit") or "")
            if output_unit and condition.unit != output_unit:
                result.add(
                    "INVALID_UNIT",
                    (
                        f"feature {condition.feature_id!r} unit mismatch: "
                        f"{condition.unit!r} != {output_unit!r}"
                    ),
                    f"components.{index}.conditions",
                )
            if condition.operator == StrategyIROperator.BETWEEN and condition.value_2 is None:
                result.add(
                    "STRATEGY_INVALID", "BETWEEN requires value_2", f"components.{index}.conditions"
                )
    for index, parameter in enumerate(strategy_ir.parameters):
        if parameter.parameter_type in {ParameterType.DECIMAL, ParameterType.INTEGER}:
            if (
                parameter.min_value is not None
                and parameter.max_value is not None
                and parameter.min_value > parameter.max_value
            ):
                result.add("STRATEGY_INVALID", "parameter min > max", f"parameters.{index}")
            if parameter.default_value is not None:
                try:
                    numeric = float(parameter.default_value)
                except (TypeError, ValueError):
                    result.add(
                        "STRATEGY_INVALID",
                        "non-numeric default for numeric parameter",
                        f"parameters.{index}",
                    )
                    continue
                if parameter.min_value is not None and numeric < float(parameter.min_value):
                    result.add("STRATEGY_INVALID", "default below min", f"parameters.{index}")
                if parameter.max_value is not None and numeric > float(parameter.max_value):
                    result.add("STRATEGY_INVALID", "default above max", f"parameters.{index}")
        if parameter.parameter_type == ParameterType.ENUM and not parameter.allowed_values:
            result.add(
                "STRATEGY_INVALID", "ENUM parameter requires allowed_values", f"parameters.{index}"
            )
    for series_id in strategy_ir.data_requirements.series_ids:
        if available_series is not None and series_id not in available_series:
            result.add(
                "DATA_MISSING", f"required series {series_id!r} is unavailable", "data_requirements"
            )
    if (
        strategy_ir.risk_controls.max_ocm_allocation_pct
        < strategy_ir.risk_controls.min_day_ahead_allocation_pct
    ):
        result.add(
            "STRATEGY_INVALID",
            "OCM allocation cap below minimum day-ahead allocation",
            "risk_controls",
        )
    return result


def compile_strategy_ir(strategy_ir: StrategyIR) -> StrategyVersionDefinition:
    """Compile a validated StrategyIR into the existing CR-03 domain model.

    The caller must run semantic validation first. Compilation never adds an
    execution path; it only maps research semantics into StrategyVersion.
    """

    components: list[StrategyComponentSpec] = []
    for component in strategy_ir.components:
        components.append(
            StrategyComponentSpec(
                component_id=component.component_id,
                component_type=component.component_type.value,
                role="signal",
                hubs=[strategy_ir.universe.origin_hub, strategy_ir.universe.destination_hub],
                tenors=[strategy_ir.universe.product.casefold()],
                required_evidence=list(strategy_ir.data_requirements.series_ids),
                extension_json={
                    "weight": component.weight,
                    "conditions": [item.model_dump(mode="json") for item in component.conditions],
                    "strategy_ir_schema_version": STRATEGY_IR_SCHEMA_VERSION,
                },
            )
        )

    parameters = [
        ParameterDefinition(
            parameter_id=item.parameter_id,
            name=item.name or item.parameter_id,
            type=item.parameter_type,
            unit=item.unit,
            min_value=item.min_value,
            max_value=item.max_value,
            allowed_values=item.allowed_values,
            optimization_allowed=item.optimization_allowed,
            sensitivity_allowed=item.sensitivity_allowed,
        )
        for item in strategy_ir.parameters
    ]
    parameter_values = {
        item.parameter_id: item.default_value
        for item in strategy_ir.parameters
        if item.default_value is not None
    }

    risk = strategy_ir.risk_controls
    economics = strategy_ir.economic_assumptions
    data = strategy_ir.data_requirements
    return StrategyVersionDefinition(
        components=components,
        parameter_definitions=parameters,
        parameter_values=parameter_values,
        risk_controls=RiskControlSpec(
            max_ocm_allocation_pct=risk.max_ocm_allocation_pct,
            min_day_ahead_allocation_pct=risk.min_day_ahead_allocation_pct,
            max_single_market_volume_mwh_per_day=risk.max_single_market_volume_mwh_per_day,
            min_expected_margin_gbp_mwh=risk.min_expected_margin_gbp_mwh,
            stop_shadow_run_loss_gbp=risk.stop_shadow_run_loss_gbp,
            require_tso_access=risk.require_tso_access,
        ),
        economic_assumptions=EconomicAssumptions(
            transaction_cost_policy=economics.transaction_cost_policy,
            fx_policy=economics.fx_policy,
            missing_data_policy=economics.missing_data_policy,
            capacity_policy=economics.capacity_policy,
            fill_price_policy=economics.fill_price_policy,
        ),
        data_requirements=DataRequirements(
            hubs=[strategy_ir.universe.origin_hub, strategy_ir.universe.destination_hub],
            delivery_products=[strategy_ir.universe.product],
            source_classes=["published", "operator-input"],
            max_source_age_seconds=data.max_source_age_seconds,
            currencies=[strategy_ir.universe.currency],
            require_fx=data.require_fx,
            require_capacity=data.require_capacity,
            require_tariffs=data.require_tariffs,
        ),
        evaluation_windows=list(strategy_ir.evaluation_windows),
    )


def example_strategy_ir() -> StrategyIR:
    """Deterministic example used by tests/docs; no hidden defaults."""

    return StrategyIR(
        hypothesis=(
            "Transport-adjusted NBP premium may persist under constrained "
            "UK import capacity."
        ),
        universe=StrategyIRUniverse(
            origin_hub="TTF", destination_hub="NBP", product="DAY_AHEAD", currency="GBP"
        ),
        components=[
            StrategyIRComponent(
                component_id="nbp-premium",
                component_type=StrategyComponentType.OCM_VS_DAY_AHEAD,
                weight=1.0,
                conditions=[
                    StrategyIRCondition(
                        feature_id="NBP_TTF_DA_SPREAD",
                        operator=StrategyIROperator.GT,
                        value=1.5,
                        unit="EUR/MWh",
                    )
                ],
            )
        ],
        parameters=[
            StrategyIRParameter(
                parameter_id="premium_threshold",
                name="Premium threshold",
                parameter_type=ParameterType.DECIMAL,
                unit="GBP/MWh",
                default_value=1.5,
                min_value=0.0,
                max_value=10.0,
                sensitivity_allowed=True,
            )
        ],
        sizing=StrategyIRSizing(method="RESOURCE_PERCENTAGE", max_pct=20.0),
        data_requirements=StrategyIRDataRequirements(
            series_ids=[
                "market.price.NBP.DAY_AHEAD",
                "market.price.TTF.DAY_AHEAD",
                "market.fx.EUR.GBP",
            ],
            require_fx=True,
        ),
    )
