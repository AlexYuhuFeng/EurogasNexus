"""LNG regas contract readiness and economics input checks."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class LngRegasDeliveryMode(StrEnum):
    TERMINAL_TITLE_TRANSFER = "TERMINAL_TITLE_TRANSFER"
    VIRTUAL_HUB_SALE = "VIRTUAL_HUB_SALE"
    PHYSICAL_ENTRY_DELIVERY = "PHYSICAL_ENTRY_DELIVERY"
    DOWNSTREAM_PHYSICAL_DELIVERY = "DOWNSTREAM_PHYSICAL_DELIVERY"


class LngRegasScenario(BaseModel):
    contract_id: str
    cargo_id: str
    terminal_id: str
    terminal_name: str
    terminal_operator: str | None = None
    terminal_access_confirmed: bool | None = None
    terminal_access_reference: str | None = None
    cargo_size_mwh: float
    cargo_size_cubic_m: float | None = None
    cargo_arrival_window_start_utc: datetime
    cargo_arrival_window_end_utc: datetime
    regas_slot_start_utc: datetime | None = None
    regas_slot_end_utc: datetime | None = None
    terminal_sendout_capacity_mwh_per_day: float | None = None
    terminal_storage_capacity_mwh: float | None = None
    terminal_capacity_source_system: str | None = None
    delivery_mode: LngRegasDeliveryMode = LngRegasDeliveryMode.TERMINAL_TITLE_TRANSFER
    physical_entry_point_name: str | None = None
    downstream_tso: str | None = None
    downstream_exit_point_name: str | None = None
    required_tso_access: list[str] = Field(default_factory=list)
    company_accessible_tsos: list[str] | None = None
    pricing_method: str
    index_name: str | None = None
    formula_description: str | None = None
    fixed_price: float | None = None
    price_currency: str = "EUR"
    price_unit: str = "MWh"
    sale_hub: str | None = None
    destination_market: str | None = None
    regas_fee_eur_mwh: float | None = None
    boil_off_allowance_pct: float | None = None
    source_refs: list[str] = Field(default_factory=list)


class LngRegasMonthAllocation(BaseModel):
    month: str
    days: float
    allocated_mwh: float


class LngRegasReadinessResult(BaseModel):
    contract_id: str
    cargo_id: str
    terminal_id: str
    terminal_name: str
    terminal_access_status: str
    delivery_mode: LngRegasDeliveryMode
    physical_entry_delivery_required: bool
    physical_entry_point_name: str | None = None
    required_tso_access: list[str] = Field(default_factory=list)
    inaccessible_tsos: list[str] = Field(default_factory=list)
    pricing_basis_status: str
    estimated_regas_duration_days: float | None = None
    available_slot_days: float | None = None
    slot_capacity_mwh: float | None = None
    slot_capacity_shortfall_mwh: float | None = None
    crosses_month: bool = False
    month_allocations: list[LngRegasMonthAllocation] = Field(default_factory=list)
    missing_inputs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    research_only: bool = True
    human_review_required: bool = True


INDEX_PRICING_METHODS = {
    "ICIS",
    "BRENT",
    "TTF",
    "DAILY_INDEX",
    "MONTHLY_INDEX",
    "PLATTS",
}


def assess_lng_regas_readiness(scenario: LngRegasScenario) -> LngRegasReadinessResult:
    """Assess whether a cargo, terminal slot, capacity, and pricing basis are usable."""

    missing: list[str] = []
    warnings: list[str] = []

    terminal_access_status = "CONFIRMED"
    if scenario.terminal_access_confirmed is not True:
        terminal_access_status = "MISSING_OR_UNCONFIRMED"
        missing.append("TERMINAL_ACCESS_NOT_CONFIRMED")
    if not scenario.terminal_access_reference:
        warnings.append("TERMINAL_ACCESS_REFERENCE_MISSING")

    pricing_basis_status = _pricing_basis_status(scenario, missing)
    if not scenario.terminal_capacity_source_system:
        missing.append("TERMINAL_CAPACITY_SOURCE_MISSING")
    if scenario.terminal_sendout_capacity_mwh_per_day is None:
        missing.append("TERMINAL_SENDOUT_CAPACITY_MISSING")
    if scenario.regas_slot_start_utc is None or scenario.regas_slot_end_utc is None:
        missing.append("REGAS_SLOT_WINDOW_MISSING")

    duration_days = _regas_duration_days(scenario)
    available_slot_days = _slot_days(scenario)
    slot_capacity = _slot_capacity(scenario, available_slot_days)
    shortfall = None
    if slot_capacity is not None:
        shortfall = max(round(scenario.cargo_size_mwh - slot_capacity, 4), 0.0)
        if shortfall > 0:
            missing.append("REGAS_SLOT_CAPACITY_SHORTFALL")
    if _cargo_window_outside_slot(scenario):
        missing.append("CARGO_TERMINAL_WINDOW_MISMATCH")
    physical_entry_required = _physical_entry_delivery_required(scenario)
    if physical_entry_required and not scenario.physical_entry_point_name:
        missing.append("PHYSICAL_ENTRY_POINT_MISSING")
    inaccessible_tsos = _inaccessible_tsos(
        scenario.required_tso_access,
        scenario.company_accessible_tsos,
    )
    if inaccessible_tsos:
        missing.extend(f"TSO_ACCESS_MISSING:{tso}" for tso in inaccessible_tsos)
        warnings.append("REGAS_ROUTE_BLOCKED_BY_TSO_ACCESS")

    crosses_month = _crosses_month(scenario)
    allocations = _month_allocations(scenario, duration_days)
    if crosses_month:
        warnings.append("REGAS_WINDOW_CROSSES_MONTH")
    if scenario.boil_off_allowance_pct is None:
        warnings.append("BOIL_OFF_ALLOWANCE_NOT_PROVIDED")
    if scenario.regas_fee_eur_mwh is None:
        warnings.append("REGAS_FEE_NOT_PROVIDED")

    return LngRegasReadinessResult(
        contract_id=scenario.contract_id,
        cargo_id=scenario.cargo_id,
        terminal_id=scenario.terminal_id,
        terminal_name=scenario.terminal_name,
        terminal_access_status=terminal_access_status,
        delivery_mode=scenario.delivery_mode,
        physical_entry_delivery_required=physical_entry_required,
        physical_entry_point_name=scenario.physical_entry_point_name,
        required_tso_access=scenario.required_tso_access,
        inaccessible_tsos=inaccessible_tsos,
        pricing_basis_status=pricing_basis_status,
        estimated_regas_duration_days=duration_days,
        available_slot_days=available_slot_days,
        slot_capacity_mwh=slot_capacity,
        slot_capacity_shortfall_mwh=shortfall,
        crosses_month=crosses_month,
        month_allocations=allocations,
        missing_inputs=_unique(missing),
        warnings=_unique(warnings),
        source_refs=scenario.source_refs,
        research_only=True,
        human_review_required=True,
    )


def _pricing_basis_status(scenario: LngRegasScenario, missing: list[str]) -> str:
    method = scenario.pricing_method.strip().upper()
    if method in INDEX_PRICING_METHODS and not scenario.index_name:
        missing.append("PRICE_INDEX_NAME_MISSING")
        return "INDEX_REFERENCE_MISSING"
    if method == "FORMULA" and not scenario.formula_description:
        missing.append("PRICE_FORMULA_DESCRIPTION_MISSING")
        return "FORMULA_MISSING"
    if method == "FIXED_PRICE" and scenario.fixed_price is None:
        missing.append("FIXED_PRICE_MISSING")
        return "FIXED_PRICE_MISSING"
    return "DEFINED"


def _physical_entry_delivery_required(scenario: LngRegasScenario) -> bool:
    return scenario.delivery_mode in {
        LngRegasDeliveryMode.PHYSICAL_ENTRY_DELIVERY,
        LngRegasDeliveryMode.DOWNSTREAM_PHYSICAL_DELIVERY,
    }


def _inaccessible_tsos(
    required_tso_access: list[str],
    company_accessible_tsos: list[str] | None,
) -> list[str]:
    if company_accessible_tsos is None:
        return []
    allowed = {item.strip().lower() for item in company_accessible_tsos if item.strip()}
    return [
        tso
        for tso in required_tso_access
        if tso.strip() and tso.strip().lower() not in allowed
    ]


def _regas_duration_days(scenario: LngRegasScenario) -> float | None:
    capacity = scenario.terminal_sendout_capacity_mwh_per_day
    if capacity is None or capacity <= 0:
        return None
    return round(scenario.cargo_size_mwh / capacity, 4)


def _slot_days(scenario: LngRegasScenario) -> float | None:
    if scenario.regas_slot_start_utc is None or scenario.regas_slot_end_utc is None:
        return None
    seconds = (scenario.regas_slot_end_utc - scenario.regas_slot_start_utc).total_seconds()
    return round(max(seconds, 0) / 86400, 4)


def _slot_capacity(scenario: LngRegasScenario, slot_days: float | None) -> float | None:
    capacity = scenario.terminal_sendout_capacity_mwh_per_day
    if capacity is None or slot_days is None:
        return None
    return round(capacity * slot_days, 4)


def _cargo_window_outside_slot(scenario: LngRegasScenario) -> bool:
    if scenario.regas_slot_start_utc is None or scenario.regas_slot_end_utc is None:
        return False
    latest_start = max(scenario.cargo_arrival_window_start_utc, scenario.regas_slot_start_utc)
    earliest_end = min(scenario.cargo_arrival_window_end_utc, scenario.regas_slot_end_utc)
    return latest_start >= earliest_end


def _crosses_month(scenario: LngRegasScenario) -> bool:
    if scenario.regas_slot_start_utc is None or scenario.regas_slot_end_utc is None:
        return False
    return scenario.regas_slot_start_utc.month != scenario.regas_slot_end_utc.month


def _month_allocations(
    scenario: LngRegasScenario,
    duration_days: float | None,
) -> list[LngRegasMonthAllocation]:
    if (
        duration_days is None
        or scenario.regas_slot_start_utc is None
        or scenario.regas_slot_end_utc is None
        or scenario.terminal_sendout_capacity_mwh_per_day is None
    ):
        return []
    start = scenario.regas_slot_start_utc
    slot_fraction = min(duration_days / (_slot_days(scenario) or 1), 1)
    end = min(
        scenario.regas_slot_end_utc,
        start + (scenario.regas_slot_end_utc - start) * slot_fraction,
    )
    allocations: list[LngRegasMonthAllocation] = []
    cursor = start
    remaining_mwh = scenario.cargo_size_mwh
    while cursor < end and remaining_mwh > 0:
        next_month = _first_day_next_month(cursor)
        segment_end = min(end, next_month)
        days = (segment_end - cursor).total_seconds() / 86400
        allocated = min(days * scenario.terminal_sendout_capacity_mwh_per_day, remaining_mwh)
        allocations.append(
            LngRegasMonthAllocation(
                month=f"{cursor.year:04d}-{cursor.month:02d}",
                days=round(days, 4),
                allocated_mwh=round(allocated, 4),
            )
        )
        remaining_mwh -= allocated
        cursor = segment_end
    return allocations


def _first_day_next_month(value: datetime) -> datetime:
    year = value.year + 1 if value.month == 12 else value.year
    month = 1 if value.month == 12 else value.month + 1
    return value.replace(year=year, month=month, day=1, hour=0, minute=0, second=0, microsecond=0)


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))
