"""Audited public European corridor tariff references.

The rows in this module are manually transcribed from official public tariff
documents and are used for local PostgreSQL test seeding and deterministic
route-cost tests. They are not synthetic fallback data.
"""

from __future__ import annotations

from datetime import date

from eurogas_nexus.domain.route_cost.enums import (
    CapacityProduct,
    Firmness,
    PointType,
    TariffDirection,
    TariffStatus,
)
from eurogas_nexus.domain.route_cost.tariff_models import CapacityTariff, TariffPoint

BBL_DOCUMENT_ID = "bbl-company-tariffs-gas-year-2025-plus"
IUK_DOCUMENT_ID = "iuk-charging-statement-issue-75"

BBL_TARIFF_URL = "https://bblcompany.com/tariffs/tariffs-gas-year-2025-and-beyond"
IUK_TARIFF_URL = (
    "https://www.fluxys.com/-/media/project/fluxys/public/corporate/fluxyscom/"
    "documents/iuk/charging-statements/int-charging-statement---issue-75.pdf"
)


def published_european_corridor_tariffs() -> list[CapacityTariff]:
    """Return official public corridor tariff rows audited for V1."""

    return [
        CapacityTariff(
            tariff_id="bbl-2025-plus-forward-annual-firm",
            document_id=BBL_DOCUMENT_ID,
            country="NL",
            tso="BBL Company",
            market_area="BBL",
            gas_year="2025+",
            point_id="bbl-forward-nl-gb",
            source_point_name="BBL Forward Flow NL to GB",
            direction=TariffDirection.EXIT,
            capacity_product=CapacityProduct.ANNUAL,
            firmness=Firmness.FIRM,
            tariff_value=1.0,
            currency="EUR",
            unit="EUR/MWh",
            effective_from=date(2025, 10, 1),
            effective_to=None,
            tariff_status=TariffStatus.FINAL,
            source_table="BBL tariffs gas year 2025 and beyond, forward flow annual reserve price",
            source_page=None,
            source_refs=[BBL_TARIFF_URL],
            manual_review_required=False,
        ),
        CapacityTariff(
            tariff_id="bbl-2025-plus-reverse-annual-firm",
            document_id=BBL_DOCUMENT_ID,
            country="GB",
            tso="BBL Company",
            market_area="BBL",
            gas_year="2025+",
            point_id="bbl-reverse-gb-nl",
            source_point_name="BBL Reverse Flow GB to NL",
            direction=TariffDirection.ENTRY,
            capacity_product=CapacityProduct.ANNUAL,
            firmness=Firmness.FIRM,
            tariff_value=1.0,
            currency="EUR",
            unit="EUR/MWh",
            effective_from=date(2025, 10, 1),
            effective_to=None,
            tariff_status=TariffStatus.FINAL,
            source_table="BBL tariffs gas year 2025 and beyond, reverse flow annual reserve price",
            source_page=None,
            source_refs=[BBL_TARIFF_URL],
            manual_review_required=False,
        ),
        CapacityTariff(
            tariff_id="iuk-2026-27-uk-be-bacton-entry-annual-firm",
            document_id=IUK_DOCUMENT_ID,
            country="GB",
            tso="Interconnector UK",
            market_area="IUK",
            gas_year="2026/27",
            point_id="iuk-bacton-entry",
            source_point_name="IUK Bacton Entry",
            direction=TariffDirection.ENTRY,
            capacity_product=CapacityProduct.ANNUAL,
            firmness=Firmness.FIRM,
            tariff_value=0.035827,
            currency="GBP",
            unit="p/(kWh/h)/h",
            effective_from=date(2026, 5, 28),
            effective_to=None,
            tariff_status=TariffStatus.FINAL,
            source_table="IUK Charging Statement Issue 75, Annual Firm Capacity 2026/27",
            source_page=5,
            source_refs=[IUK_TARIFF_URL],
            manual_review_required=False,
        ),
        CapacityTariff(
            tariff_id="iuk-2026-27-uk-be-zeebrugge-exit-annual-firm",
            document_id=IUK_DOCUMENT_ID,
            country="BE",
            tso="Interconnector UK",
            market_area="IUK",
            gas_year="2026/27",
            point_id="iuk-zeebrugge-exit",
            source_point_name="IUK Zeebrugge Exit",
            direction=TariffDirection.EXIT,
            capacity_product=CapacityProduct.ANNUAL,
            firmness=Firmness.FIRM,
            tariff_value=0.035827,
            currency="GBP",
            unit="p/(kWh/h)/h",
            effective_from=date(2026, 5, 28),
            effective_to=None,
            tariff_status=TariffStatus.FINAL,
            source_table="IUK Charging Statement Issue 75, Annual Firm Capacity 2026/27",
            source_page=5,
            source_refs=[IUK_TARIFF_URL],
            manual_review_required=False,
        ),
        CapacityTariff(
            tariff_id="iuk-2026-27-be-uk-zeebrugge-entry-annual-firm",
            document_id=IUK_DOCUMENT_ID,
            country="BE",
            tso="Interconnector UK",
            market_area="IUK",
            gas_year="2026/27",
            point_id="iuk-zeebrugge-entry",
            source_point_name="IUK Zeebrugge Entry",
            direction=TariffDirection.ENTRY,
            capacity_product=CapacityProduct.ANNUAL,
            firmness=Firmness.FIRM,
            tariff_value=0.035827,
            currency="GBP",
            unit="p/(kWh/h)/h",
            effective_from=date(2026, 5, 28),
            effective_to=None,
            tariff_status=TariffStatus.FINAL,
            source_table="IUK Charging Statement Issue 75, Annual Firm Capacity 2026/27",
            source_page=5,
            source_refs=[IUK_TARIFF_URL],
            manual_review_required=False,
        ),
        CapacityTariff(
            tariff_id="iuk-2026-27-be-uk-bacton-exit-annual-firm",
            document_id=IUK_DOCUMENT_ID,
            country="GB",
            tso="Interconnector UK",
            market_area="IUK",
            gas_year="2026/27",
            point_id="iuk-bacton-exit",
            source_point_name="IUK Bacton Exit",
            direction=TariffDirection.EXIT,
            capacity_product=CapacityProduct.ANNUAL,
            firmness=Firmness.FIRM,
            tariff_value=0.035827,
            currency="GBP",
            unit="p/(kWh/h)/h",
            effective_from=date(2026, 5, 28),
            effective_to=None,
            tariff_status=TariffStatus.FINAL,
            source_table="IUK Charging Statement Issue 75, Annual Firm Capacity 2026/27",
            source_page=5,
            source_refs=[IUK_TARIFF_URL],
            manual_review_required=False,
        ),
    ]


def published_european_corridor_points() -> list[TariffPoint]:
    """Return points covered by the audited public corridor tariff rows."""

    return [
        TariffPoint(
            point_id="bbl-forward-nl-gb",
            source_point_name="BBL Forward Flow NL to GB",
            canonical_point_id="bbl-forward-nl-gb",
            country="NL",
            tso="BBL Company",
            market_area="BBL",
            point_type=PointType.INTERCONNECTION,
            hub_binding="TTF/NBP",
            source_refs=[BBL_TARIFF_URL],
            manual_review_required=False,
        ),
        TariffPoint(
            point_id="bbl-reverse-gb-nl",
            source_point_name="BBL Reverse Flow GB to NL",
            canonical_point_id="bbl-reverse-gb-nl",
            country="GB",
            tso="BBL Company",
            market_area="BBL",
            point_type=PointType.INTERCONNECTION,
            hub_binding="NBP/TTF",
            source_refs=[BBL_TARIFF_URL],
            manual_review_required=False,
        ),
        TariffPoint(
            point_id="iuk-bacton-entry",
            source_point_name="IUK Bacton Entry",
            canonical_point_id="iuk-bacton-entry",
            country="GB",
            tso="Interconnector UK",
            market_area="IUK",
            point_type=PointType.INTERCONNECTION,
            hub_binding="NBP/ZTP",
            source_refs=[IUK_TARIFF_URL],
            manual_review_required=False,
        ),
        TariffPoint(
            point_id="iuk-zeebrugge-entry",
            source_point_name="IUK Zeebrugge Entry",
            canonical_point_id="iuk-zeebrugge-entry",
            country="BE",
            tso="Interconnector UK",
            market_area="IUK",
            point_type=PointType.INTERCONNECTION,
            hub_binding="ZTP/NBP",
            source_refs=[IUK_TARIFF_URL],
            manual_review_required=False,
        ),
    ]
