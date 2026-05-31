"""In-code UK demo tariff data used only when no runtime DB is configured."""

# ruff: noqa: E501

from __future__ import annotations

from datetime import date

from eurogas_nexus.domain.route_cost.enums import (
    CapacityProduct,
    Firmness,
    TariffDirection,
    TariffStatus,
)
from eurogas_nexus.domain.route_cost.tariff_models import CapacityTariff
from eurogas_nexus.domain.route_cost.uk_rules import (
    NATIONAL_GAS_TARIFF_URL,
    UK_BACTON_GDN_EXIT_POINT_NAME,
    UK_EASINGTON_POINT_NAME,
)

DOCUMENT_ID = "uk_ng_nts_transportation_charges_oct_2025"
DOCUMENT_REF = (
    "National Gas Transmission Notice of Gas Transmission Transportation Charges "
    "Issue 1.0 issued 31 July 2025"
)


def demo_uk_capacity_tariffs() -> list[CapacityTariff]:
    """Return public UK tariff examples for DB-free development only."""

    return [
        _tariff("2025/26", UK_EASINGTON_POINT_NAME, "uk-ng-nts-easington-beach", "ENTRY", 0.1086, "FINAL", 12),
        _tariff(
            "2026/27",
            UK_EASINGTON_POINT_NAME,
            "uk-ng-nts-easington-beach",
            "ENTRY",
            0.1157,
            "INDICATIVE",
            12,
        ),
        _tariff("2027/28", UK_EASINGTON_POINT_NAME, "uk-ng-nts-easington-beach", "ENTRY", 0.1227, "INDICATIVE", 12),
        _tariff("2028/29", UK_EASINGTON_POINT_NAME, "uk-ng-nts-easington-beach", "ENTRY", 0.1101, "INDICATIVE", 12),
        _tariff("2029/30", UK_EASINGTON_POINT_NAME, "uk-ng-nts-easington-beach", "ENTRY", 0.1176, "INDICATIVE", 12),
        _tariff("2025/26", UK_BACTON_GDN_EXIT_POINT_NAME, "uk-ng-nts-bacton-gdn-ea", "EXIT", 0.0299, "FINAL", 15),
        _tariff("2026/27", UK_BACTON_GDN_EXIT_POINT_NAME, "uk-ng-nts-bacton-gdn-ea", "EXIT", 0.0348, "INDICATIVE", 15),
    ]


def _tariff(
    gas_year: str,
    point_name: str,
    point_id: str,
    direction: str,
    value: float,
    status: str,
    page: int,
) -> CapacityTariff:
    return CapacityTariff(
        tariff_id=(
            f"{point_id}-{direction.lower()}-{gas_year.replace('/', '-')}-"
            "firm-daily"
        ),
        document_id=DOCUMENT_ID,
        country="UK",
        tso="National Gas NTS",
        market_area="NTS",
        gas_year=gas_year,
        point_id=point_id,
        source_point_name=point_name,
        direction=TariffDirection(direction),
        capacity_product=CapacityProduct.DAILY,
        firmness=Firmness.FIRM,
        tariff_value=value,
        currency="GBP",
        unit="p/kWh/day",
        effective_from=date(int("20" + gas_year[:2]), 10, 1),
        effective_to=None,
        tariff_status=TariffStatus(status),
        source_table=(
            "Table 4 Entry Capacity Reserve Prices"
            if direction == "ENTRY"
            else "Table 8 NTS TO Exit (Flat) Capacity Charges"
        ),
        source_page=page,
        source_refs=[
            DOCUMENT_REF,
            "National Gas effective from 1 October 2025",
            (
                "National Gas Table 4 Entry Capacity Reserve Prices"
                if direction == "ENTRY"
                else "National Gas Table 8 NTS TO Exit (Flat) Capacity Charges"
            ),
            f"National Gas source URL {NATIONAL_GAS_TARIFF_URL}",
        ],
        manual_review_required=status != "FINAL",
    )
