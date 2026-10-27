"""Typed SDK carriers for ``POST /api/research/lng-economics-only``.

The backend's economics-only composition is exact by construction: every cash
amount, energy quantity and discount factor travels as a decimal string, dates
travel as ISO calendar dates, and the ordered explicit energy stages are echoed
back with their charged-basis cash costs. These models preserve that wire shape
without importing backend code and without performing any local financial or
energy arithmetic.

The result always reports ``physical_readiness='NOT_ASSESSED'`` and
``readiness_assessed=False``: this capability is research decision support, not
a delivery-feasibility, terminal-slot, storage-right or nomination assessment.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field

# Mirrors the backend's stable model version. It is repeated here because the
# SDK must not import backend internals; the server remains the authority and
# refuses any value that does not match its own constant.
LNG_ECONOMICS_ONLY_MODEL_VERSION = "lng-economics-only/v1"


class LngEconomicsOnlyDiscountFactorRequest(BaseModel):
    """One explicit discount factor for one payment date.

    Attributes:
        payment_date: Cash date the factor discounts.
        factor: Exact decimal string; never inferred from a curve.
        curve_reference: Curve reference the factor came from.
        source_reference: Provenance of the factor.
        as_of: Factor date.
    """

    model_config = ConfigDict(extra="forbid")

    payment_date: date
    factor: str = Field(max_length=64)
    curve_reference: str = Field(max_length=256)
    source_reference: str = Field(max_length=256)
    as_of: date


class LngEconomicsOnlyDownstreamCostRequest(BaseModel):
    """One explicitly invoiced downstream cash cost.

    Attributes:
        cost_id: Unique item id within the request.
        category: Cost category from the shared cash-leg vocabulary.
        amount_eur: Exact decimal string of the nonnegative EUR total.
        payment_date: Cash date.
        source_reference: Provenance of the invoiced amount.
        charge_basis: Declared charge nature; only ``invoiced_cash`` is a cash
            expense. The server refuses ``in_kind`` and ``unknown``.
    """

    model_config = ConfigDict(extra="forbid")

    cost_id: str = Field(max_length=128)
    category: str = Field(max_length=64)
    amount_eur: str = Field(max_length=64)
    payment_date: date
    source_reference: str = Field(max_length=256)
    charge_basis: str = Field(max_length=32)


class LngEconomicsOnlyEnergyStageRequest(BaseModel):
    """One explicit stage of the ordered LNG cargo energy chain.

    Attributes:
        stage_id: Unique stage id within the chain.
        kind: Declared stage kind.
        input_energy_mwh: Exact decimal string of the positive stage input.
        output_energy_mwh: Exact decimal string of the positive stage output.
        consumed_energy_mwh: Exact decimal string of nonnegative consumed
            energy.
        physical_loss_energy_mwh: Exact decimal string of nonnegative physical
            loss.
        source_references: Provenance references for the stage.
    """

    model_config = ConfigDict(extra="forbid")

    stage_id: str = Field(max_length=128)
    kind: str = Field(max_length=64)
    input_energy_mwh: str = Field(max_length=64)
    output_energy_mwh: str = Field(max_length=64)
    consumed_energy_mwh: str = Field(max_length=64)
    physical_loss_energy_mwh: str = Field(max_length=64)
    source_references: list[str] = Field(max_length=64)


class LngEconomicsOnlyRequest(BaseModel):
    """One explicit economics-only research request.

    All amounts are decimal strings and all dates are calendar dates; the SDK
    performs no conversion, defaulting or financial arithmetic. The request
    deliberately carries no readiness scenario and no authority claim.
    """

    model_config = ConfigDict(extra="forbid")

    contract_id: str = Field(max_length=128)
    cargo_id: str = Field(max_length=128)
    terminal_id: str = Field(max_length=128)
    resource_id: str = Field(max_length=128)
    valuation_date: date
    reporting_currency: str = Field(max_length=8)
    energy_basis_reference: str = Field(max_length=256)
    energy_unit: str = Field(max_length=32)
    purchased_energy_mwh: str = Field(max_length=64)
    delivered_energy_mwh: str = Field(max_length=64)
    purchase_unit_price_eur_per_mwh: str = Field(max_length=64)
    sale_unit_price_eur_per_mwh: str = Field(max_length=64)
    purchase_price_source_reference: str = Field(max_length=256)
    sale_price_source_reference: str = Field(max_length=256)
    purchase_basis: str = Field(max_length=8)
    purchase_included_cost_items: list[str] = Field(max_length=64)
    cost_scope_statement: str = Field(max_length=1000)
    purchase_payment_date: date
    sale_payment_date: date
    downstream_costs: list[LngEconomicsOnlyDownstreamCostRequest] = Field(
        max_length=256
    )
    energy_stages: list[LngEconomicsOnlyEnergyStageRequest] = Field(
        max_length=256
    )
    discount_factors: list[LngEconomicsOnlyDiscountFactorRequest] = Field(
        max_length=256
    )
    model_version: str = Field(
        default=LNG_ECONOMICS_ONLY_MODEL_VERSION, max_length=64
    )


class LngEconomicsOnlyLegValuation(BaseModel):
    """One normalized, discounted cash-flow leg echoed by the backend."""

    leg_id: str
    category: str
    payment_date: date
    currency: str
    signed_amount: str
    cash_amount_reporting_ccy: str
    present_value_reporting_ccy: str
    discount_factor: str
    discount_curve_reference: str
    discount_source_reference: str
    discount_as_of: date
    source_reference: str
    fx_rate_reporting_per_leg: str
    fx_source_reference: str | None = None
    fx_as_of: date | None = None
    description: str = ""


class LngEconomicsOnlyCashValuation(BaseModel):
    """Embedded bounded cash-valuation result."""

    model_version: str
    contract_id: str
    cargo_id: str
    terminal_id: str
    resource_id: str
    valuation_date: date
    reporting_currency: str
    leg_valuations: list[LngEconomicsOnlyLegValuation] = Field(
        default_factory=list
    )
    total_undiscounted_cash_reporting_ccy: str
    net_present_value_reporting_ccy: str
    assumptions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    source_references: list[str] = Field(default_factory=list)
    lineage: list[str] = Field(default_factory=list)
    research_only: bool
    human_review_required: bool


class LngEconomicsOnlyEnergyStage(BaseModel):
    """One explicit energy stage echoed by the backend."""

    stage_id: str
    kind: str
    input_energy_mwh: str
    output_energy_mwh: str
    consumed_energy_mwh: str
    physical_loss_energy_mwh: str
    source_references: list[str] = Field(default_factory=list)


class LngEconomicsOnlyEnergyBalance(BaseModel):
    """Explicit ordered energy balance echoed by the backend."""

    model_version: str
    purchased_energy_mwh: str
    delivered_energy_mwh: str
    energy_basis_reference: str
    energy_unit: str
    total_consumed_energy_mwh: str
    physical_loss_energy_mwh: str
    total_reduction_energy_mwh: str
    stage_count: int
    stages: list[LngEconomicsOnlyEnergyStage] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    source_references: list[str] = Field(default_factory=list)
    research_only: bool
    human_review_required: bool


class LngEconomicsOnlyResult(BaseModel):
    """Typed result of one LNG economics-only composition.

    Every amount remains a decimal string exactly as the backend serialized it.
    ``physical_readiness`` is always ``NOT_ASSESSED`` and
    ``readiness_assessed`` is always false for this capability.
    """

    research_only: bool
    human_review_required: bool
    model_version: str
    action: str
    contract_id: str
    cargo_id: str
    terminal_id: str
    resource_id: str
    valuation_date: date
    reporting_currency: str
    energy_basis_reference: str
    energy_unit: str
    purchased_energy_mwh: str
    delivered_energy_mwh: str
    total_consumed_energy_mwh: str
    physical_loss_energy_mwh: str
    total_reduction_energy_mwh: str
    purchase_basis: str
    purchase_included_cost_items: list[str] = Field(default_factory=list)
    cost_scope_statement: str
    purchase_unit_price_eur_per_mwh: str
    sale_unit_price_eur_per_mwh: str
    unit_netback_eur_per_purchased_mwh: str
    sale_basis_eur_per_delivered_mwh: str
    purchase_outlay_eur: str
    sale_proceeds_eur: str
    total_downstream_costs_eur: str
    cargo_margin_eur: str
    margin_reconciliation_gap_eur: str
    margin_reconciliation_tolerance_eur: str
    net_present_value_eur: str
    total_undiscounted_cash_eur: str
    cash_valuation: LngEconomicsOnlyCashValuation
    energy_balance: LngEconomicsOnlyEnergyBalance
    physical_readiness: str
    readiness_assessed: bool
    assumptions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    source_references: list[str] = Field(default_factory=list)
    lineage: list[str] = Field(default_factory=list)


__all__ = [
    "LNG_ECONOMICS_ONLY_MODEL_VERSION",
    "LngEconomicsOnlyCashValuation",
    "LngEconomicsOnlyDiscountFactorRequest",
    "LngEconomicsOnlyDownstreamCostRequest",
    "LngEconomicsOnlyEnergyBalance",
    "LngEconomicsOnlyEnergyStage",
    "LngEconomicsOnlyEnergyStageRequest",
    "LngEconomicsOnlyLegValuation",
    "LngEconomicsOnlyRequest",
    "LngEconomicsOnlyResult",
]
