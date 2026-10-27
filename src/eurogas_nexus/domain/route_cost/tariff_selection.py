"""Tariff selection helpers.

费率选择规则：只允许"精确匹配"（同国、同 TSO、同点、同方向、同气体年、
同产品、同可靠性），绝不跨气体年或跨方向替换；非 FINAL 状态必须告警并
要求人工复核。

When the caller declares an explicit ``applicability_date`` the selector
requires a single authoritative row whose inclusive source bounds
(``effective_from <= applicability_date <= effective_to``) cover that date.
Row order is never an authority: inverted bounds, overlapping candidates at
the same highest status, and conflicting duplicate tariff ids refuse the
selection instead of picking the first row. Without an explicit date the
legacy status-priority selection is preserved for wire compatibility, but the
result discloses that applicability was not assessed and requires human
review. The selector never reads ``created_at``, the current clock or the gas
year as a date proxy.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime

from pydantic import BaseModel, Field

from eurogas_nexus.domain.route_cost.enums import (
    CapacityProduct,
    Firmness,
    TariffDirection,
    TariffStatus,
)
from eurogas_nexus.domain.route_cost.tariff_models import CapacityTariff

# 费率状态优先级：FINAL 最优，SIMULATOR_ONLY 最差；同匹配组内取优先级最高者。
STATUS_PRIORITY = {
    TariffStatus.FINAL: 0,
    TariffStatus.INDICATIVE: 1,
    TariffStatus.PROVISIONAL: 2,
    TariffStatus.DRAFT: 3,
    TariffStatus.SIMULATOR_ONLY: 4,
}

#: No exact-match tariff row exists for the declared exact key.
TARIFF_MISSING = "TARIFF_MISSING"

#: Warning carried by a selection made without an explicit applicability date.
TARIFF_APPLICABILITY_NOT_ASSESSED = "TARIFF_APPLICABILITY_NOT_ASSESSED"

#: No exact-match row covers the declared date (a period gap or out-of-period).
TARIFF_NOT_EFFECTIVE_ON_DATE = "TARIFF_NOT_EFFECTIVE_ON_DATE"

#: Two or more rows at the same highest status cover the declared date.
TARIFF_APPLICABILITY_AMBIGUOUS = "TARIFF_APPLICABILITY_AMBIGUOUS"

#: A candidate row declares ``effective_to`` before its ``effective_from``.
TARIFF_EFFECTIVE_BOUNDS_INVALID = "TARIFF_EFFECTIVE_BOUNDS_INVALID"

#: One tariff id appears with different row content inside the exact-match set.
TARIFF_DUPLICATE_ID_CONFLICT = "TARIFF_DUPLICATE_ID_CONFLICT"

#: The supplied applicability value is not a plain calendar date.
TARIFF_APPLICABILITY_DATE_INVALID = "TARIFF_APPLICABILITY_DATE_INVALID"

#: Selection failures that make route-level date applicability unverified.
#: The route-cost service blocks such a route (no partial total) instead of
#: treating the missing leg as an ordinary missing tariff.
APPLICABILITY_FAILURE_CODES = frozenset(
    {
        TARIFF_NOT_EFFECTIVE_ON_DATE,
        TARIFF_APPLICABILITY_AMBIGUOUS,
        TARIFF_EFFECTIVE_BOUNDS_INVALID,
        TARIFF_DUPLICATE_ID_CONFLICT,
        TARIFF_APPLICABILITY_DATE_INVALID,
    }
)


class CapacityTariffSelection(BaseModel):
    """Outcome of one tariff selection attempt.

    Attributes:
        status: ``SELECTED`` or ``MISSING``.
        selected_tariff: The chosen tariff, or None when missing.
        missing_inputs: Inputs that blocked selection (e.g. ``TARIFF_MISSING``).
        warnings: Non-blocking issues (e.g. non-FINAL status, or the legacy
            path's ``TARIFF_APPLICABILITY_NOT_ASSESSED`` disclosure).
        human_review_required: True when the result needs review.
    """

    status: str
    selected_tariff: CapacityTariff | None = None
    missing_inputs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    human_review_required: bool = False


def select_latest_tariff(
    tariffs: Sequence[CapacityTariff],
    *,
    country: str,
    tso: str,
    point_name: str,
    direction: TariffDirection,
    gas_year: str,
    capacity_product: CapacityProduct,
    firmness: Firmness,
    applicability_date: date | None = None,
) -> CapacityTariffSelection:
    """Select an exact matching tariff; never substitutes another gas year.

    精确匹配选择：同参数组内按状态优先级选取，绝不跨气体年/方向替代。

    Legacy mode (``applicability_date is None``) keeps the previous
    status-priority, first-row-wins behaviour and adds the explicit
    ``TARIFF_APPLICABILITY_NOT_ASSESSED`` warning plus mandatory human review.
    It never pretends the row was verified for a date.

    Explicit-date mode requires a plain calendar date. It validates every
    exact-match candidate's inclusive bounds, collapses fully identical rows
    sharing a tariff id, refuses same-id rows with different content, keeps
    only rows covering the date, then applies the existing status priority.
    A tie at the highest status is refused as ambiguous. No substitute row is
    ever selected from another period, gas year, point, direction, product or
    firmness.

    Args:
        tariffs: Candidate tariff rows (typically all rows of a document).
        country: Required country.
        tso: Required TSO.
        point_name: Required source point name.
        direction: Required direction.
        gas_year: Required gas year (no substitution allowed).
        capacity_product: Required capacity product.
        firmness: Required firmness.
        applicability_date: Explicit calendar date the selected tariff must
            cover, or ``None`` for the disclosed legacy path.

    Returns:
        ``SELECTED`` with the best-status exact match, or ``MISSING`` with a
        stable code and human_review_required when no row matches, no row
        covers the explicit date, the date is ambiguous, bounds are inverted,
        or a duplicate tariff id conflicts.
    """

    if applicability_date is not None and not _is_plain_date(applicability_date):
        return _missing_selection(TARIFF_APPLICABILITY_DATE_INVALID)

    matches = [
        tariff
        for tariff in tariffs
        if tariff.country == country
        and tariff.tso == tso
        and tariff.source_point_name == point_name
        and tariff.direction is direction
        and tariff.gas_year == gas_year
        and tariff.capacity_product is capacity_product
        and tariff.firmness is firmness
    ]
    if not matches:
        # 无精确匹配即 MISSING：宁可缺数据也不做近似替代。
        warnings = (
            [TARIFF_APPLICABILITY_NOT_ASSESSED]
            if applicability_date is None
            else []
        )
        return CapacityTariffSelection(
            status="MISSING",
            missing_inputs=[TARIFF_MISSING],
            warnings=warnings,
            human_review_required=True,
        )

    if applicability_date is None:
        # Legacy wire-compatible path: status priority and stable first-row
        # tie-break, explicitly disclosed as not date-assessed.
        selected = sorted(
            matches, key=lambda item: STATUS_PRIORITY[item.tariff_status]
        )[0]
        warnings = [TARIFF_APPLICABILITY_NOT_ASSESSED]
        human_review_required = True
        if selected.tariff_status is not TariffStatus.FINAL:
            warnings.append(f"TARIFF_STATUS_{selected.tariff_status.value}")
        return CapacityTariffSelection(
            status="SELECTED",
            selected_tariff=selected,
            warnings=warnings,
            human_review_required=human_review_required,
        )

    # Explicit date: source bounds must be internally coherent for every exact
    # candidate. An inverted row makes the source set untrustworthy, so it is
    # refused even when another row happens to cover the requested date.
    if any(
        tariff.effective_to is not None
        and tariff.effective_to < tariff.effective_from
        for tariff in matches
    ):
        return _missing_selection(TARIFF_EFFECTIVE_BOUNDS_INVALID)

    unique, duplicate_conflict = _unique_by_tariff_id(matches)
    if duplicate_conflict:
        return _missing_selection(TARIFF_DUPLICATE_ID_CONFLICT)

    eligible = [
        tariff
        for tariff in unique
        if tariff.effective_from <= applicability_date
        and (tariff.effective_to is None or tariff.effective_to >= applicability_date)
    ]
    if not eligible:
        return _missing_selection(TARIFF_NOT_EFFECTIVE_ON_DATE)

    highest_priority = min(
        STATUS_PRIORITY[tariff.tariff_status] for tariff in eligible
    )
    authoritative = [
        tariff
        for tariff in eligible
        if STATUS_PRIORITY[tariff.tariff_status] == highest_priority
    ]
    if len(authoritative) > 1:
        # Same status and both cover the date: status priority cannot choose,
        # and row order is not an authority.
        return _missing_selection(TARIFF_APPLICABILITY_AMBIGUOUS)

    selected = authoritative[0]
    warnings: list[str] = []
    human_review_required = False
    if selected.tariff_status is not TariffStatus.FINAL:
        # 非 FINAL 费率：结果可用但必须显式告警并强制人工复核。
        warnings.append(f"TARIFF_STATUS_{selected.tariff_status.value}")
        human_review_required = True

    return CapacityTariffSelection(
        status="SELECTED",
        selected_tariff=selected,
        warnings=warnings,
        human_review_required=human_review_required,
    )


def _is_plain_date(value: object) -> bool:
    """Whether ``value`` is a calendar date and not a datetime instant."""

    return isinstance(value, date) and not isinstance(value, datetime)


def _missing_selection(code: str) -> CapacityTariffSelection:
    """Return a fail-closed selection carrying one stable missing-input code."""

    return CapacityTariffSelection(
        status="MISSING",
        missing_inputs=[code],
        human_review_required=True,
    )


def _unique_by_tariff_id(
    matches: Sequence[CapacityTariff],
) -> tuple[list[CapacityTariff], bool]:
    """Collapse identical duplicate tariff ids; refuse conflicting duplicates.

    Fully identical duplicates are the same evidence repeated (for example a
    source row joined twice), so one copy is kept and cannot create a false
    ambiguity. The same id with different content no longer identifies one
    candidate and is refused instead of relying on row order.
    """

    by_id: dict[str, CapacityTariff] = {}
    unique: list[CapacityTariff] = []
    for tariff in matches:
        existing = by_id.get(tariff.tariff_id)
        if existing is None:
            by_id[tariff.tariff_id] = tariff
            unique.append(tariff)
        elif existing != tariff:
            return unique, True
    return unique, False
