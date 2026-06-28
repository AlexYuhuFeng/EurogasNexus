"""European public tariff reference tests."""

from eurogas_nexus.domain.route_cost.enums import (
    CapacityProduct,
    Firmness,
    TariffDirection,
    TariffStatus,
)
from eurogas_nexus.domain.route_cost.european_public_tariffs import (
    BBL_DOCUMENT_ID,
    IUK_DOCUMENT_ID,
    published_european_corridor_tariffs,
)


def test_public_corridor_tariffs_include_bbl_forward_and_reverse_annual_rows() -> None:
    tariffs = published_european_corridor_tariffs()

    bbl = [tariff for tariff in tariffs if tariff.document_id == BBL_DOCUMENT_ID]

    assert {tariff.source_point_name for tariff in bbl} == {
        "BBL Forward Flow NL to GB",
        "BBL Reverse Flow GB to NL",
    }
    assert {tariff.tariff_value for tariff in bbl} == {1.0}
    assert {tariff.currency for tariff in bbl} == {"EUR"}
    assert {tariff.unit for tariff in bbl} == {"EUR/MWh"}
    assert {tariff.capacity_product for tariff in bbl} == {CapacityProduct.ANNUAL}
    assert {tariff.firmness for tariff in bbl} == {Firmness.FIRM}
    assert {tariff.tariff_status for tariff in bbl} == {TariffStatus.FINAL}
    assert all("bblcompany.com" in " ".join(tariff.source_refs) for tariff in bbl)


def test_public_corridor_tariffs_include_iuk_2026_27_annual_firm_points() -> None:
    tariffs = published_european_corridor_tariffs()

    iuk = [tariff for tariff in tariffs if tariff.document_id == IUK_DOCUMENT_ID]

    assert {tariff.source_point_name for tariff in iuk} == {
        "IUK Bacton Entry",
        "IUK Zeebrugge Exit",
        "IUK Zeebrugge Entry",
        "IUK Bacton Exit",
    }
    assert {tariff.direction for tariff in iuk} == {
        TariffDirection.ENTRY,
        TariffDirection.EXIT,
    }
    assert {tariff.tariff_value for tariff in iuk} == {0.035827}
    assert {tariff.currency for tariff in iuk} == {"GBP"}
    assert {tariff.unit for tariff in iuk} == {"p/(kWh/h)/h"}
    assert {tariff.gas_year for tariff in iuk} == {"2026/27"}
    assert all("fluxys.com" in " ".join(tariff.source_refs) for tariff in iuk)
