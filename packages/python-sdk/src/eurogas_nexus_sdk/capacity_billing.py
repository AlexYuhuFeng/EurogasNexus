"""Typed SDK carriers for ``POST /api/research/capacity-billing``.

The backend's capacity-billing primitive is exact by construction: its numeric
inputs and outputs are decimal strings, its billing window is an explicit aware
interval, and its result keeps the original basis plus exact integer duration
microseconds. These models preserve that wire shape without importing backend
code and without performing any local financial arithmetic.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Mirrors the backend's stable model version. It is repeated here because the
# SDK must not import backend internals; the server remains the authority and
# refuses any value that does not match its own constant.
CAPACITY_BILLING_MODEL_VERSION = "capacity-billing/v1"


class CapacityBillingRequest(BaseModel):
    """One explicit capacity-billing request.

    Attributes:
        scenario_id: Caller-supplied scenario identifier; never resolved.
        tariff_id: Caller-supplied tariff identifier; never looked up.
        tariff_rate: Exact decimal string of the rate in ``tariff_unit``.
        currency: Currency required by ``tariff_unit`` (``EUR`` or ``GBP``).
        tariff_unit: Explicit capacity unit: ``EUR/(MWh/h)/h``,
            ``GBP/(MWh/h)/h`` or ``p/(kWh/h)/h``.
        booked_capacity_mwh_per_h: Exact decimal string of booked capacity.
        delivered_energy_mwh: Exact decimal string of delivered energy.
        billed_capacity_energy_mwh: Exact decimal string of billed capacity
            energy; the backend verifies it exactly against booked capacity
            times the actual UTC duration.
        billing_start: Timezone-aware start of the billing window.
        billing_end: Timezone-aware end of the billing window.
        source_references: Caller-supplied provenance references.
        model_version: Backend model version; the server refuses unsupported
            values with a stable code.
    """

    model_config = ConfigDict(extra="forbid")

    scenario_id: str = Field(max_length=128)
    tariff_id: str = Field(max_length=128)
    tariff_rate: str = Field(max_length=64)
    currency: str = Field(max_length=8)
    tariff_unit: str = Field(max_length=32)
    booked_capacity_mwh_per_h: str = Field(max_length=64)
    delivered_energy_mwh: str = Field(max_length=64)
    billed_capacity_energy_mwh: str = Field(max_length=64)
    billing_start: datetime
    billing_end: datetime
    source_references: list[str] = Field(max_length=64)
    model_version: str = Field(
        default=CAPACITY_BILLING_MODEL_VERSION, max_length=64
    )

    @field_validator("billing_start", "billing_end")
    @classmethod
    def _require_aware_datetime(cls, value: datetime) -> datetime:
        """Refuse a naive timestamp before it can be serialized ambiguously."""

        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("billing timestamps must be timezone-aware")
        return value


class CapacityBillingBasis(BaseModel):
    """Original explicit basis echoed by the backend.

    Attributes:
        tariff_rate: Exact decimal string of the supplied tariff rate.
        tariff_unit: Supplied capacity unit.
        booked_capacity_mwh_per_h: Exact decimal string of booked capacity.
        billed_capacity_energy_mwh: Exact decimal string of billed energy.
        delivered_energy_mwh: Exact decimal string of delivered energy.
        billing_start_utc: UTC-normalized billing-window start.
        billing_end_utc: UTC-normalized billing-window end.
        duration_microseconds: Exact integer duration in microseconds.
    """

    tariff_rate: str
    tariff_unit: str
    booked_capacity_mwh_per_h: str
    billed_capacity_energy_mwh: str
    delivered_energy_mwh: str
    billing_start_utc: datetime
    billing_end_utc: datetime
    duration_microseconds: int


class CapacityBillingResult(BaseModel):
    """Typed result of one exact capacity-billing calculation.

    Attributes:
        research_only: True; this is research decision support only.
        human_review_required: True; output needs human review before use.
        model_version: Backend capacity-billing model version.
        scenario_id: Caller-supplied scenario identifier.
        tariff_id: Caller-supplied tariff identifier.
        currency: Result currency.
        tariff_unit: Supplied capacity unit.
        tariff_rate: Exact decimal string of the supplied rate.
        booked_capacity_mwh_per_h: Exact decimal string of booked capacity.
        billed_capacity_energy_mwh: Exact decimal string of billed energy.
        delivered_energy_mwh: Exact decimal string of delivered energy.
        billing_start: UTC billing-window start.
        billing_end: UTC billing-window end.
        duration_microseconds: Exact integer duration in microseconds.
        duration_hours: Precision-limited display duration as an exact string.
        total_cost: Invoiced capacity cost as an exact decimal string.
        cost_per_delivered_mwh: Cost divided by delivered energy, as an exact
            decimal string. It is an allocation, not an energy-price
            conversion.
        basis: Original explicit calculation basis.
        provenance: Caller-supplied provenance references.
        source_references: Caller-supplied provenance references.
        assumptions: Backend assumptions.
        warnings: Stable backend warnings.
        lineage: Backend lineage identifiers.
        physical_readiness: Always ``NOT_ASSESSED`` for this research slice.
    """

    research_only: bool
    human_review_required: bool
    model_version: str
    scenario_id: str
    tariff_id: str
    currency: str
    tariff_unit: str
    tariff_rate: str
    booked_capacity_mwh_per_h: str
    billed_capacity_energy_mwh: str
    delivered_energy_mwh: str
    billing_start: datetime
    billing_end: datetime
    duration_microseconds: int
    duration_hours: str
    total_cost: str
    cost_per_delivered_mwh: str
    basis: CapacityBillingBasis
    provenance: list[str] = Field(default_factory=list)
    source_references: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    lineage: list[str] = Field(default_factory=list)
    physical_readiness: str
