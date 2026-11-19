"""Published TSO tariffs from ENTSOG price the crossings route pricing walks.

Fixtures have the shape ENTSOG TP ``tariffsfulls`` publishes (read 19-11-2026); every number
is made up.
"""

from __future__ import annotations

import importlib.util
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import eurogas_nexus.db.models  # noqa: F401  (registers every table)
from eurogas_nexus.application.route_tariff_cost import price_leg, route_cost
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import TsoTariffRecord
from eurogas_nexus.db.repositories.route_cost import _tariff_from_record
from eurogas_nexus.domain.market.fx_forward import Delivery
from eurogas_nexus.domain.route_cost.route_adjacency import apply_route_adjacency
from eurogas_nexus.domain.route_cost.route_cost_service import calculate_route_cost
from eurogas_nexus.domain.route_cost.schemas import RouteCostScenario, RouteTariffLeg
from eurogas_nexus.ingestion.entsog_tariffs import (
    entsog_tariff_rows,
    read_points,
    tariff_points,
)
from eurogas_nexus.ingestion.entsog_transport import fetch_entsog_dataset
from eurogas_nexus.reference_data.network_bundle import load_bundle

DOWNLOADED = date(2026, 11, 19)
RECEIVED = datetime(2026, 11, 19, 9, tzinfo=UTC)
DEC_26 = Delivery(date(2026, 12, 1), date(2026, 12, 31), "month", "Dec-26")
_PERIOD_LETTER = {"Yearly": "y", "Quarterly": "q", "Monthly": "m", "Daily": "d", "WithinDay": "h"}


def record(
    point,
    operator,
    direction,
    per_kwh_h,
    start,
    end,
    *,
    product="Yearly",
    currency="EUR",
    eur_rate=1.0,
    days=365,
    product_from=None,
    product_to=None,
    capacity_unit="kWh/h",
    **extra,
):
    """A ``tariffsfulls`` record whose four figures and common unit agree (made-up numbers)."""

    letter = _PERIOD_LETTER[product]
    eur_h = per_kwh_h * eur_rate
    common = eur_h / days if letter in "yqm" else eur_h
    common_unit = "Euro/(kWh/h)/h" if letter == "h" else "Euro/(kWh/h)/d"
    return {
        "id": f"{operator}{point}{direction}{product}{start}{product_from}",
        "pointKey": point,
        "pointLabel": f"label {point}",
        "operatorKey": operator,
        "operator": f"operator {operator}",
        "countryCode": "XX",
        "directionKey": direction,
        "productType": product,
        "tariffCapacityType": "Firm",
        "tariffCapacityUnit": capacity_unit,
        "periodFrom": f"{start}T06:00:00+01:00",
        "periodTo": f"{end}T06:00:00+01:00",
        "productPeriodFrom": f"{product_from or start}T06:00:00+01:00",
        "productPeriodTo": f"{product_to or end}T06:00:00+01:00",
        "multiplier": "N/A",
        "seasonalFactor": "N/A",
        "discountForInterruptibleCapacityValue": "N/A",
        "operatorCurrency": currency,
        "applicableTariffPerLocalCurrencyKWhHValue": str(per_kwh_h),
        "applicableTariffPerLocalCurrencyKWhHUnit": f"{currency}/(kWh/h)/{letter}",
        "applicableTariffPerLocalCurrencyKWhDValue": str(per_kwh_h / 24),
        "applicableTariffPerLocalCurrencyKWhDUnit": f"{currency}/(kWh/d)/{letter}",
        "applicableTariffPerEURKWhHValue": str(eur_h),
        "applicableTariffPerEURKWhHUnit": f"Euro/(kWh/h)/{letter}",
        "applicableTariffInCommonUnitValue": str(common),
        "applicableTariffInCommonUnitUnit": common_unit,
        "applicableTariffRemarks": "",
        "exchangeRateReferenceDate": "N/A",
        "fromBZ": "Netherlands",
        "toBZ": "DE THE BZ",
        "isArchived": False,
        **extra,
    }


#: TTF -> THE at VIP TTF-THE-H: the GTS exit and the Gasunie Deutschland entry (made up).
TTF_THE = [
    record("ITP-10012", "NL-TSO-0001", "exit", 4.0, "2026-01-01", "2027-01-01"),
    record("ITP-10012", "DE-TSO-0005", "entry", 6.0, "2026-01-01", "2027-01-01"),
]


@pytest.fixture(scope="module")
def bundle():
    return load_bundle()


def rows_of(records, bundle, **kwargs):
    return entsog_tariff_rows(
        records, bundle=bundle, downloaded=DOWNLOADED, received_at=RECEIVED, **kwargs
    )


def test_the_register_keeps_what_the_operator_published(bundle):
    rows, counts = rows_of(TTF_THE, bundle)
    assert counts["conflicting"] == 0 and counts["common_unit_disagrees"] == 0
    by_key = {(row["tso"], row["point_id"], row["direction"]): row for row in rows}
    gud = by_key[("Gasunie Deutschland", "ITP-10012", "ENTRY")]
    assert gud["source_point_name"] == "VIP TTF-THE-H"
    # Stored as published: per kWh/h per year, in the operator's currency. Not per MWh.
    assert (gud["tariff_value"], gud["unit"], gud["currency"]) == (6.0, "EUR/(kWh/h)/y", "EUR")
    assert gud["capacity_product"] == "ANNUAL" and gud["firmness"] == "FIRM"
    assert gud["gas_year"] == "2026"
    assert gud["effective_from"].date() == date(2026, 1, 1)
    assert gud["effective_to"].date() == date(2026, 12, 31)
    assert gud["tariff_status"] == "FINAL" and gud["manual_review_required"] is False
    refs = " | ".join(gud["source_refs"])
    assert "ENTSOG TP [19-11-2026] https://transparency.entsog.eu/" in gud["source_refs"]
    assert "entsog:tariffsfulls:" in refs and "multiplier N/A" in refs and "common:" in refs


def test_every_standard_product_is_stored_for_its_own_period(bundle):
    records = [
        record(
            "ITP-10012",
            "NL-TSO-0001",
            "exit",
            0.5,
            "2026-01-01",
            "2027-01-01",
            product="Monthly",
            days=30,
            product_from="2026-11-01",
            product_to="2026-12-01",
        ),
        record(
            "ITP-10012",
            "NL-TSO-0001",
            "exit",
            1.2,
            "2026-01-01",
            "2027-01-01",
            product="Quarterly",
            days=92,
            product_from="2026-10-01",
            product_to="2027-01-01",
        ),
        record(
            "ITP-10012",
            "NL-TSO-0001",
            "exit",
            0.02,
            "2026-01-01",
            "2027-01-01",
            product="Daily",
            days=1,
        ),
        record(
            "ITP-10012",
            "NL-TSO-0001",
            "exit",
            0.001,
            "2026-01-01",
            "2027-01-01",
            product="WithinDay",
            days=1,
        ),
    ]
    rows, counts = rows_of(records, bundle)
    products = {row["capacity_product"]: row for row in rows}
    assert set(products) == {"MONTHLY", "QUARTERLY", "DAILY", "WITHIN_DAY"}
    november = products["MONTHLY"]
    assert november["unit"] == "EUR/(kWh/h)/m"
    assert november["effective_from"].date() == date(2026, 11, 1)
    assert november["effective_to"].date() == date(2026, 11, 30)
    assert products["WITHIN_DAY"]["unit"] == "EUR/(kWh/h)/h"
    assert products["DAILY"]["effective_to"].date() == date(2026, 12, 31)


def test_a_gb_operator_keeps_its_currency_and_capacity_unit(bundle):
    [row], _ = rows_of(
        [
            record(
                "ITP-00005",
                "UK-TSO-0003",
                "entry",
                3.0,
                "2026-10-01",
                "2027-10-01",
                currency="GBP",
                eur_rate=1.16,
                capacity_unit="kWh/d",
            )
        ],
        bundle,
    )
    assert (row["tso"], row["currency"]) == ("Interconnector", "GBP")
    assert row["tariff_value"] == pytest.approx(3.0 / 24) and row["unit"] == "GBP/(kWh/d)/y"
    assert row["gas_year"] == "2026/27"


def test_figures_that_disagree_are_not_stored_and_nothing_is_rescaled(bundle):
    good = record("ITP-10012", "NL-TSO-0001", "exit", 4.0, "2026-01-01", "2027-01-01")
    basis_mislabel = {**good, "applicableTariffPerLocalCurrencyKWhDValue": "4.0"}
    common_24 = {**good, "applicableTariffInCommonUnitValue": str(4.0 / 365 * 24)}
    common_far = {**good, "applicableTariffInCommonUnitValue": "0.00001"}
    short_far = {
        **record(
            "ITP-10012",
            "NL-TSO-0001",
            "exit",
            0.02,
            "2026-01-01",
            "2027-01-01",
            product="Daily",
            days=1,
        ),
        "applicableTariffInCommonUnitValue": "0.00001",
    }
    rows, counts = rows_of([basis_mislabel, common_24, short_far], bundle)
    assert rows == [] and counts["figures_disagree"] == 3
    [kept], counts = rows_of([common_far], bundle)
    # Only ENTSOG's common unit is off: a yearly price is kept, as indicative, for review.
    assert kept["tariff_status"] == "INDICATIVE" and kept["manual_review_required"] is True
    assert counts["common_unit_disagrees"] == 1
    assert any(ref.startswith("check:") for ref in kept["source_refs"])


def test_a_later_period_is_indicative_and_unoffered_or_empty_rows_are_counted(bundle):
    rows, counts = rows_of(
        [
            record("ITP-10012", "DE-TSO-0005", "entry", 6.5, "2027-01-01", "2028-01-01"),
            {
                **record("ITP-10012", "DE-TSO-0005", "exit", 6.0, "2026-01-01", "2027-01-01"),
                "isArchived": True,
            },
            {
                **record("ITP-10012", "NL-TSO-0001", "entry", 4.0, "2026-01-01", "2027-01-01"),
                "applicableTariffPerLocalCurrencyKWhHValue": "N/A",
                "applicableTariffPerLocalCurrencyKWhDValue": "N/A",
                "applicableTariffRemarks": "Product Not Available",
            },
            record("ITP-99999", "NL-TSO-0001", "exit", 4.0, "2026-01-01", "2027-01-01"),
            {
                **record("ITP-10012", "NL-TSO-0001", "exit", 4.0, "2026-01-01", "2027-01-01"),
                "productType": "Weekly",
            },
        ],
        bundle,
    )
    assert [row["tariff_status"] for row in rows] == ["INDICATIVE"]
    assert counts["archived"] == 1 and counts["product_not_offered"] == 1
    assert counts["point_outside_adjacency"] == 1 and counts["product_not_stored"] == 1


def test_two_yearly_prices_in_one_tariff_period_hold_for_their_product_periods(bundle):
    # NaTran's April-March period: one yearly price from April, another from October.
    april = record(
        "ITP-00526",
        "FR-TSO-0003",
        "entry",
        3.0,
        "2026-04-01",
        "2027-04-01",
        product_from="2026-04-01",
        product_to="2026-10-01",
    )
    october = record(
        "ITP-00526",
        "FR-TSO-0003",
        "entry",
        3.2,
        "2026-04-01",
        "2027-04-01",
        product_from="2026-10-01",
        product_to="2027-04-01",
    )
    rows, counts = rows_of([april, october], bundle)
    assert counts["conflicting"] == 0
    spans = sorted(
        (row["effective_from"].date(), row["effective_to"].date(), row["tariff_value"])
        for row in rows
    )
    assert spans == [
        (date(2026, 4, 1), date(2026, 9, 30), 3.0),
        (date(2026, 10, 1), date(2027, 3, 31), 3.2),
    ]
    assert {row["gas_year"] for row in rows} == {"2026-04..27-03"}


def test_two_publications_of_one_tariff_that_disagree_are_both_refused(bundle):
    one = record(
        "ITP-10012",
        "NL-TSO-0001",
        "exit",
        0.5,
        "2026-01-01",
        "2027-01-01",
        product="Monthly",
        days=30,
        product_from="2026-11-01",
        product_to="2026-12-01",
    )
    other = {
        **record(
            "ITP-10012",
            "NL-TSO-0001",
            "exit",
            0.6,
            "2026-01-01",
            "2027-01-01",
            product="Monthly",
            days=30,
            product_from="2026-11-01",
            product_to="2026-12-01",
        ),
        "id": "other",
    }
    rows, counts = rows_of([one, other], bundle)
    assert rows == [] and counts["conflicting"] == 1


def test_national_gas_figures_on_entsog_are_refused(bundle):
    rows, counts = rows_of(
        [record("ITP-00005", "UK-TSO-0001", "exit", 0.005, "2026-10-01", "2027-10-01")], bundle
    )
    assert rows == [] and counts["operator_refused"] == 1


def test_points_outside_the_bundle_keep_entsog_names(bundle):
    [row], _ = rows_of(
        [
            {
                **record("ITP-00040", "IT-TSO-0001", "entry", 2.0, "2026-10-01", "2027-10-01"),
                "pointLabel": "Tarvisio (IT) / Arnoldstein (AT)",
                "operator": "Snam Rete Gas",
                "countryCode": "IT",
                "toBZ": "Italy",
            }
        ],
        bundle,
    )
    assert row["source_point_name"] == "Tarvisio (IT) / Arnoldstein (AT)"
    assert (row["tso"], row["country"], row["market_area"]) == ("Snam Rete Gas", "IT", "Italy")


def test_the_read_covers_the_graph_and_the_corridor_lng_and_landing_points(bundle):
    graph = set(tariff_points(bundle))
    assert {"ITP-00005", "ITP-00061", "ITP-00063", "ITP-00207", "ITP-10012"} <= graph
    every = set(read_points(bundle))
    assert graph <= every
    # Tarvisio (CEGH-PSV), VIP PIRINEOS (PEG-PVB), Gate LNG, Easington (Norway).
    assert {"ITP-00040", "ITP-00304", "LNG-00027", "ITP-00091"} <= every


def test_published_tariffs_price_ttf_to_the_through_the_route_engine(bundle):
    rows, _ = rows_of(TTF_THE, bundle)
    tariffs = [_tariff_from_record(TsoTariffRecord(**row)) for row in rows]
    # Read per MWh at 100 % load factor when the engine reads the register.
    assert {t.unit for t in tariffs} == {"EUR/MWh"}
    [candidate] = apply_route_adjacency(
        [
            {
                "route_id": "ttf-the",
                "start_point_name": "TTF",
                "target_point_name": "THE",
                "route_legs": [],
            }
        ]
    )
    legs = [RouteTariffLeg.model_validate(leg) for leg in candidate["route_legs"]]
    result = calculate_route_cost(
        RouteCostScenario(
            scenario_id="ttf-the",
            source_resource_type="PIPELINE_IMPORT",
            start_point_id="TTF",
            target_hub_or_point_id="THE",
            business_model="CROSS_BORDER_TRANSFER",
            delivery_mode="BORDER_TRANSFER",
            gas_year=legs[0].gas_year,
            tariff_applicability_date=date(2026, 11, 19),
            capacity_product="ANNUAL",
            firmness="FIRM",
            tariff_legs=legs,
        ),
        tariffs,
    )
    assert result.status == "SUCCESS", result.missing_inputs
    assert result.total_cost == pytest.approx((4.0 + 6.0) / 8.76, abs=1e-4)
    assert result.unit == "EUR/MWh"


def test_route_tariff_cost_reads_the_published_figure_per_mwh(bundle):
    rows, _ = rows_of(TTF_THE, bundle)
    cost = route_cost("TTF", "THE", DEC_26, rows)
    assert cost.complete and cost.input_class == "sourced"
    assert cost.total == pytest.approx((4.0 + 6.0) / 8.76)
    exit_leg = cost.legs[0].as_dict()
    assert exit_leg["published"] == "4 EUR/(kWh/h)/y" and "365 days" in exit_leg["basis"]
    half = route_cost("TTF", "THE", DEC_26, rows, load_factor=0.5)
    assert half.total == pytest.approx(2 * cost.total)
    # No monthly row is held: a monthly booking is missing, never priced from the yearly one.
    monthly = route_cost("TTF", "THE", DEC_26, rows, product="MONTHLY")
    assert monthly.total is None and monthly.input_class == "missing"
    assert len(monthly.missing_legs()) == 2


def test_a_leg_whose_unit_is_not_understood_is_missing_with_the_reason(bundle):
    rows, _ = rows_of(TTF_THE, bundle)
    rows = [{**row, "unit": "EUR/(kWh/h)/w"} if row["direction"] == "EXIT" else row for row in rows]
    graph_leg = route_cost("TTF", "THE", DEC_26, rows).legs
    unreadable = [leg for leg in graph_leg if leg.note]
    assert unreadable and unreadable[0].value is None
    assert "unit not understood" in unreadable[0].note


def test_the_firmest_publication_wins_when_two_cover_the_day(bundle):
    rows, _ = rows_of(TTF_THE, bundle)
    gts_exit = next(row for row in rows if row["direction"] == "EXIT")
    simulated = {
        **gts_exit,
        "tariff_id": "demo-sim",
        "tariff_status": "SIMULATOR_ONLY",
        "tariff_value": 0.1,
        "unit": "EUR/MWh",
    }
    cost = route_cost("TTF", "THE", DEC_26, [simulated, *rows])
    assert cost.input_class == "sourced"
    spec = type(
        "Spec",
        (),
        {
            "point_key": "ITP-10012",
            "point_name": "VIP TTF-THE-H",
            "tso": "GTS",
            "direction": "EXIT",
            "role": "market_area_exit",
        },
    )
    leg = price_leg(spec, [simulated], date(2026, 12, 1))
    assert leg.input_class == "simulated" and leg.value == pytest.approx(0.1)


def test_a_point_without_published_tariffs_is_an_empty_complete_read_that_names_its_query():
    def answer(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"message": "No result found"})

    with httpx.Client(transport=httpx.MockTransport(answer)) as client:
        result = fetch_entsog_dataset(
            client, "tariffsfulls", filters={"pointKey": "ITP-00063"}, sleep=lambda _: None
        )
    assert result.complete and result.record_count == 0
    assert result.stop_reason == "provider_no_result"
    assert result.pages and result.received_at_utc is not None
    # The empty page says which query it answers (the resume marker of the tariff read).
    assert result.pages[0].payload["meta"]["query"] == {"pointKey": "ITP-00063"}


def test_simulated_demo_tariffs_step_aside_for_published_ones():
    path = Path(__file__).resolve().parents[2] / "scripts" / "demo" / "seed_demo_desk.py"
    spec = importlib.util.spec_from_file_location("seed_demo_desk_tariffs", path)
    seed = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(seed)
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        seed._seed_cross_border_position(session, RECEIVED, DOWNLOADED)
        session.flush()
        simulated = session.query(TsoTariffRecord).filter(
            TsoTariffRecord.document_id == seed.SIMULATED_TARIFF_DOCUMENT
        )
        assert {row.tariff_status for row in simulated} == {"SIMULATOR_ONLY"}
        assert simulated.count() == 3
        rows, _ = entsog_tariff_rows(
            [record("ITP-00207", "UK-TSO-0004", "exit", 8.0, "2026-10-01", "2027-10-01")],
            bundle=load_bundle(),
            downloaded=DOWNLOADED,
            received_at=RECEIVED,
        )
        session.add_all(TsoTariffRecord(**row) for row in rows)
        session.flush()
        assert seed.retire_simulated_tariffs(session) == 1
        left = {(row.tso, row.direction) for row in simulated}
        assert left == {("GTS", "EXIT"), ("National Gas TSO", "ENTRY")}
