"""Tariff selection helpers."""

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

STATUS_PRIORITY = {
    TariffStatus.FINAL: 0,
    TariffStatus.INDICATIVE: 1,
    TariffStatus.PROVISIONAL: 2,
    TariffStatus.DRAFT: 3,
    TariffStatus.SIMULATOR_ONLY: 4,
}


class CapacityTariffSelection(BaseModel):
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
    """Select an exact matching tariff; never substitutes another gas year."""

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
        return CapacityTariffSelection(
            status="MISSING",
            missing_inputs=["TARIFF_MISSING"],
            human_review_required=True,
        )

    selected = sorted(matches, key=lambda item: STATUS_PRIORITY[item.tariff_status])[0]
    warnings: list[str] = []
    human_review_required = False
    if selected.tariff_status is not TariffStatus.FINAL:
        warnings.append(f"TARIFF_STATUS_{selected.tariff_status.value}")
        human_review_required = True

    return CapacityTariffSelection(
        status="SELECTED",
        selected_tariff=selected,
        warnings=warnings,
        human_review_required=human_review_required,
    )

