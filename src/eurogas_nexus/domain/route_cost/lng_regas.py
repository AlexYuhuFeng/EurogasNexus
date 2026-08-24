"""LNG regas contract readiness and economics input checks.

LNG 再气化就绪度评估的唯一实现：检查终端准入、槽位/容量、定价基准
与 TSO 准入（全部 fail-closed），并给出跨月分摊；任何缺项都以
missing_inputs/warnings 上报，不静默放行。
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from eurogas_nexus.domain.constraints.access import inaccessible_tsos as _inaccessible_tsos
from eurogas_nexus.domain.ontology.vocabulary import DeliveryMode


class LngRegasScenario(BaseModel):
    """Input scenario for one LNG cargo regas readiness assessment.

    Attributes:
        contract_id: Upstream contract id.
        cargo_id: Cargo identifier.
        terminal_id: Terminal identifier.
        terminal_name: Terminal display name.
        terminal_operator: Terminal operator, or None.
        terminal_access_confirmed: Whether terminal access is confirmed.
        terminal_access_reference: Reference of the access confirmation.
        cargo_size_mwh: Cargo energy size, MWh.
        cargo_size_cubic_m: Cargo volume, m³, or None.
        cargo_arrival_window_start_utc: Earliest arrival.
        cargo_arrival_window_end_utc: Latest arrival.
        regas_slot_start_utc: Regas slot start, or None.
        regas_slot_end_utc: Regas slot end, or None.
        terminal_sendout_capacity_mwh_per_day: Send-out capacity, or None.
        terminal_storage_capacity_mwh: Storage capacity, or None.
        terminal_capacity_source_system: Capacity data source, or None.
        delivery_mode: Delivery mode of the regas output.
        physical_entry_point_name: Entry point for physical delivery.
        downstream_tso: Downstream TSO, or None.
        downstream_exit_point_name: Downstream exit point, or None.
        required_tso_access: TSO access codes required downstream.
        company_accessible_tsos: Company's accessible TSOs, or None.
        pricing_method: Pricing method tag (FIXED_PRICE/INDEX/FORMULA...).
        index_name: Index name when index-priced, or None.
        formula_description: Formula description when formula-priced, or None.
        fixed_price: Fixed price when fixed-priced, or None.
        price_currency: ISO 4217 code of the price.
        price_unit: Price unit.
        sale_hub: Sale hub, or None.
        destination_market: Destination market, or None.
        regas_fee_eur_mwh: Regas fee, or None.
        boil_off_allowance_pct: Boil-off allowance, or None.
        source_refs: Provenance references.
    """

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
    delivery_mode: DeliveryMode = DeliveryMode.TERMINAL_TITLE_TRANSFER
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
    """One month's share of the regas schedule.

    Attributes:
        month: Month label ``YYYY-MM``.
        days: Days of the slot falling in this month.
        allocated_mwh: Cargo MWh allocated to this month.
    """

    month: str
    days: float
    allocated_mwh: float


class LngRegasReadinessResult(BaseModel):
    """Readiness assessment output for one cargo.

    Attributes:
        contract_id: Echoed contract id.
        cargo_id: Echoed cargo id.
        terminal_id: Echoed terminal id.
        terminal_name: Echoed terminal name.
        terminal_access_status: CONFIRMED or MISSING_OR_UNCONFIRMED.
        delivery_mode: Echoed delivery mode.
        physical_entry_delivery_required: Whether downstream physical
            delivery is required.
        physical_entry_point_name: Entry point, or None.
        required_tso_access: Echoed access requirement.
        inaccessible_tsos: TSOs not accessible (fail-closed).
        pricing_basis_status: DEFINED or a missing-input code.
        estimated_regas_duration_days: Cargo / send-out capacity.
        available_slot_days: Slot length in days, or None.
        slot_capacity_mwh: Send-out capacity × slot days, or None.
        slot_capacity_shortfall_mwh: Cargo minus slot capacity, or None.
        crosses_month: Whether the slot spans two months.
        month_allocations: Monthly allocation breakdown.
        missing_inputs: Inputs that blocked the assessment.
        warnings: Non-blocking issues.
        source_refs: Echoed provenance.
        research_only: Always True.
        human_review_required: Always True.
    """

    contract_id: str
    cargo_id: str
    terminal_id: str
    terminal_name: str
    terminal_access_status: str
    delivery_mode: DeliveryMode
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


# 需要显式指数/参考名的定价方法集合（缺 index_name 即视为定价基准缺失）。
INDEX_PRICING_METHODS = {
    "ICIS",
    "BRENT",
    "TTF",
    "DAILY_INDEX",
    "MONTHLY_INDEX",
    "PLATTS",
}


def assess_lng_regas_readiness(scenario: LngRegasScenario) -> LngRegasReadinessResult:
    """Assess whether a cargo, terminal slot, capacity, and pricing basis are usable.

    评估船货/终端槽位/容量/定价基准是否可用（全部 fail-closed）。

    Args:
        scenario: LNG regas scenario with terminal, cargo, slot, capacity
            and pricing inputs.

    Returns:
        A LngRegasReadinessResult with access status, capacity math, month
        allocations and all missing inputs/warnings. Nothing is assumed
        present when absent.

    Raises:
        No exceptions; gaps are reported in the result.
    """

    missing: list[str] = []
    warnings: list[str] = []

    terminal_access_status = "CONFIRMED"
    if scenario.terminal_access_confirmed is not True:
        # 终端准入未确认：fail-closed，绝不能当作已准入。
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
    """Validate the pricing basis against the declared method.

    定价基准校验：指数定价缺指数名、公式定价缺公式描述、固定价缺
    价格值——分别上报对应缺失码并返回非 DEFINED 状态。
    """

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
    """Whether the delivery mode requires a downstream physical entry point."""

    return scenario.delivery_mode in {
        DeliveryMode.PHYSICAL_ENTRY_DELIVERY,
        DeliveryMode.DOWNSTREAM_PHYSICAL_DELIVERY,
    }


def _regas_duration_days(scenario: LngRegasScenario) -> float | None:
    """Regas duration = cargo / send-out capacity (days)."""

    capacity = scenario.terminal_sendout_capacity_mwh_per_day
    if capacity is None or capacity <= 0:
        return None
    return round(scenario.cargo_size_mwh / capacity, 4)


def _slot_days(scenario: LngRegasScenario) -> float | None:
    """Slot length in days (floor at zero)."""

    if scenario.regas_slot_start_utc is None or scenario.regas_slot_end_utc is None:
        return None
    seconds = (scenario.regas_slot_end_utc - scenario.regas_slot_start_utc).total_seconds()
    return round(max(seconds, 0) / 86400, 4)


def _slot_capacity(scenario: LngRegasScenario, slot_days: float | None) -> float | None:
    """Slot capacity = send-out capacity × slot days."""

    capacity = scenario.terminal_sendout_capacity_mwh_per_day
    if capacity is None or slot_days is None:
        return None
    return round(capacity * slot_days, 4)


def _cargo_window_outside_slot(scenario: LngRegasScenario) -> bool:
    """Whether the arrival window and the regas slot do not overlap."""

    if scenario.regas_slot_start_utc is None or scenario.regas_slot_end_utc is None:
        return False
    latest_start = max(scenario.cargo_arrival_window_start_utc, scenario.regas_slot_start_utc)
    earliest_end = min(scenario.cargo_arrival_window_end_utc, scenario.regas_slot_end_utc)
    return latest_start >= earliest_end


def _crosses_month(scenario: LngRegasScenario) -> bool:
    """Whether the regas slot spans two calendar months."""

    if scenario.regas_slot_start_utc is None or scenario.regas_slot_end_utc is None:
        return False
    return scenario.regas_slot_start_utc.month != scenario.regas_slot_end_utc.month


def _month_allocations(
    scenario: LngRegasScenario,
    duration_days: float | None,
) -> list[LngRegasMonthAllocation]:
    """Split the cargo across calendar months by send-out capacity.

    按月分摊船货：按槽位内每日送气能力切分到各自然月，直至船货分配完
    或槽位结束；缺少容量/槽位输入时返回空列表。

    Args:
        scenario: LNG regas scenario.
        duration_days: Estimated regas duration (from readiness checks).

    Returns:
        Monthly allocation slices (may be empty when inputs are missing).
    """

    if (
        duration_days is None
        or scenario.regas_slot_start_utc is None
        or scenario.regas_slot_end_utc is None
        or scenario.terminal_sendout_capacity_mwh_per_day is None
    ):
        return []
    start = scenario.regas_slot_start_utc
    # 分摊窗口按"实际再气化时长占槽位比例"截断，避免把槽位外天数计入。
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
    """First day of the next calendar month (midnight, same tz)."""

    year = value.year + 1 if value.month == 12 else value.year
    month = 1 if value.month == 12 else value.month + 1
    return value.replace(year=year, month=month, day=1, hour=0, minute=0, second=0, microsecond=0)


def _unique(values: list[str]) -> list[str]:
    """Deduplicate preserving first-seen order."""

    return list(dict.fromkeys(values))
