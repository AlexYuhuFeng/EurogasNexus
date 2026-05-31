"""UK route-cost tariff model tests."""

from datetime import date

from eurogas_nexus.domain.route_cost.enums import (
    CapacityProduct,
    Firmness,
    PointType,
    TariffDirection,
    TariffStatus,
)
from eurogas_nexus.domain.route_cost.tariff_models import (
    CapacityTariff,
    TariffPoint,
    TariffSourceDocument,
)


def test_capacity_tariff_preserves_source_metadata() -> None:
    document = TariffSourceDocument(
        document_id="uk_ng_nts_transportation_charges_oct_2025",
        country="UK",
        tso="National Gas NTS",
        market_area="NTS",
        source_url="https://example.test/tariff.pdf",
        document_title="Notice of Gas Transmission Transportation Charges",
        published_date=date(2025, 7, 31),
        effective_from=date(2025, 10, 1),
        effective_to=None,
        gas_years_covered=["2025/26", "2026/27"],
        status=TariffStatus.FINAL,
        parser_status="manual_fixture",
        manual_review_required=True,
        source_refs=["Table 4 Entry Capacity Reserve Prices"],
    )
    point = TariffPoint(
        point_id="uk-ng-nts-easington-beach",
        source_point_name="Easington Beach Terminal",
        country="UK",
        tso="National Gas NTS",
        market_area="NTS",
        point_type=PointType.BEACH,
        is_virtual=False,
        is_physical=True,
        source_refs=document.source_refs,
        manual_review_required=True,
    )
    tariff = CapacityTariff(
        tariff_id="uk-ng-nts-easington-entry-2025-26-firm-daily",
        document_id=document.document_id,
        country="UK",
        tso="National Gas NTS",
        market_area="NTS",
        gas_year="2025/26",
        point_id=point.point_id,
        source_point_name=point.source_point_name,
        direction=TariffDirection.ENTRY,
        capacity_product=CapacityProduct.DAILY,
        firmness=Firmness.FIRM,
        tariff_value=0.1086,
        currency="GBP",
        unit="p/kWh/day",
        effective_from=date(2025, 10, 1),
        effective_to=None,
        tariff_status=TariffStatus.FINAL,
        source_table="Table 4 Entry Capacity Reserve Prices",
        source_page=12,
        source_refs=["page 12"],
        manual_review_required=True,
    )

    assert tariff.tariff_value == 0.1086
    assert tariff.unit == "p/kWh/day"
    assert tariff.source_refs == ["page 12"]
    assert tariff.tariff_status is TariffStatus.FINAL

