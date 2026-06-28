"""Route-cost tariff model tests."""

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


def test_capacity_tariff_preserves_european_corridor_source_metadata() -> None:
    document = TariffSourceDocument(
        document_id="bbl-company-tariffs-gas-year-2025-plus",
        country="NL",
        tso="BBL Company",
        market_area="BBL",
        source_url="https://bblcompany.com/tariffs/tariffs-gas-year-2025-and-beyond",
        document_title="BBL tariffs gas year 2025 and beyond",
        published_date=date(2025, 10, 1),
        effective_from=date(2025, 10, 1),
        effective_to=None,
        gas_years_covered=["2025+"],
        status=TariffStatus.FINAL,
        parser_status="manual_audited_public_reference",
        manual_review_required=False,
        source_refs=["BBL annual reserve price"],
    )
    point = TariffPoint(
        point_id="bbl-forward-nl-gb",
        source_point_name="BBL Forward Flow NL to GB",
        country="NL",
        tso="BBL Company",
        market_area="BBL",
        point_type=PointType.INTERCONNECTION,
        is_virtual=False,
        is_physical=True,
        source_refs=document.source_refs,
        manual_review_required=False,
    )
    tariff = CapacityTariff(
        tariff_id="bbl-2025-plus-forward-annual-firm",
        document_id=document.document_id,
        country="NL",
        tso="BBL Company",
        market_area="BBL",
        gas_year="2025+",
        point_id=point.point_id,
        source_point_name=point.source_point_name,
        direction=TariffDirection.EXIT,
        capacity_product=CapacityProduct.ANNUAL,
        firmness=Firmness.FIRM,
        tariff_value=1.0,
        currency="EUR",
        unit="EUR/MWh",
        effective_from=date(2025, 10, 1),
        effective_to=None,
        tariff_status=TariffStatus.FINAL,
        source_table="BBL forward flow annual reserve price",
        source_page=None,
        source_refs=["BBL annual reserve price"],
        manual_review_required=False,
    )

    assert tariff.tariff_value == 1.0
    assert tariff.unit == "EUR/MWh"
    assert tariff.source_refs == ["BBL annual reserve price"]
    assert tariff.tariff_status is TariffStatus.FINAL
