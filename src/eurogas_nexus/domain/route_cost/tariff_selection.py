"""Tariff selection helpers.

费率选择规则：只允许"精确匹配"（同国、同 TSO、同点、同方向、同气体年、
同产品、同可靠性），绝不跨气体年或跨方向替换；非 FINAL 状态必须告警并
要求人工复核。
"""

from __future__ import annotations

from collections.abc import Sequence

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


class CapacityTariffSelection(BaseModel):
    """Outcome of one tariff selection attempt.

    Attributes:
        status: ``SELECTED`` or ``MISSING``.
        selected_tariff: The chosen tariff, or None when missing.
        missing_inputs: Inputs that blocked selection (e.g. ``TARIFF_MISSING``).
        warnings: Non-blocking issues (e.g. non-FINAL status).
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
) -> CapacityTariffSelection:
    """Select an exact matching tariff; never substitutes another gas year.

    精确匹配选择：同参数组内按状态优先级选取，绝不跨气体年/方向替代。

    Args:
        tariffs: Candidate tariff rows (typically all rows of a document).
        country: Required country.
        tso: Required TSO.
        point_name: Required source point name.
        direction: Required direction.
        gas_year: Required gas year (no substitution allowed).
        capacity_product: Required capacity product.
        firmness: Required firmness.

    Returns:
        ``SELECTED`` with the best-status exact match, or ``MISSING`` with
        ``TARIFF_MISSING`` and human_review_required when no row matches.
        A non-FINAL selection carries a status warning and requires review.
    """

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
        return CapacityTariffSelection(
            status="MISSING",
            missing_inputs=["TARIFF_MISSING"],
            human_review_required=True,
        )

    selected = sorted(matches, key=lambda item: STATUS_PRIORITY[item.tariff_status])[0]
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
