"""Published TSO tariffs from ENTSOG price the crossings route pricing walks."""

from __future__ import annotations

import importlib.util
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import eurogas_nexus.db.models  # noqa: F401  (registers every table)
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import TsoTariffRecord
from eurogas_nexus.db.repositories.route_cost import _tariff_from_record
from eurogas_nexus.domain.route_cost.route_adjacency import apply_route_adjacency
from eurogas_nexus.domain.route_cost.route_cost_service import calculate_route_cost
from eurogas_nexus.domain.route_cost.schemas import RouteCostScenario, RouteTariffLeg
from eurogas_nexus.ingestion.entsog_tariffs import (
    entsog_tariff_rows,
    per_mwh_at_full_load,
    tariff_points,
)
from eurogas_nexus.ingestion.entsog_transport import fetch_entsog_dataset
from eurogas_nexus.reference_data.network_bundle import load_bundle

DOWNLOADED = date(2026, 11, 17)
RECEIVED = datetime(2026, 11, 17, 9, tzinfo=UTC)


def record(point, operator, direction, value, start, end, **extra):
    """An ENTSOG tariffsfulls record in the shape the platform publishes (read 2026-11-17)."""

    return {
        "id": f"{operator}{point}{direction}{start}",
        "pointKey": point,
        "operatorKey": operator,
        "directionKey": direction,
        "productType": "Yearly",
        "tariffCapacityType": "Firm",
        "periodFrom": f"{start}T06:00:00+01:00",
        "periodTo": f"{end}T06:00:00+01:00",
        "applicableTariffInCommonUnitValue": str(value),
        "applicableTariffInCommonUnitUnit": "Euro/(kWh/h)/d",
        "applicableTariffPerLocalCurrencyKWhDValue": "0.13",
        "applicableTariffPerLocalCurrencyKWhDUnit": "GBP/(kWh/d)/y",
        "fromBZ": "UK",
        "toBZ": "IUK",
        "isArchived": False,
        **extra,
    }


# NBP -> ZTP through IUK, as ENTSOG published the 2026/27 and 2026 periods.
IUK_CROSSING = [
    record("ITP-00005", "UK-TSO-0001", "exit", 0.00001599, "2026-10-01", "2027-10-01"),
    record("ITP-00005", "UK-TSO-0003", "entry", 0.00996903, "2026-10-01", "2027-10-01"),
    record("ITP-00061", "UK-TSO-0003", "exit", 0.00996903, "2026-10-01", "2027-10-01"),
    record("ITP-00061", "BE-TSO-0001", "entry", 0.00220548, "2026-01-01", "2027-01-01"),
]


@pytest.fixture(scope="module")
def bundle():
    return load_bundle()


def test_a_published_tariff_becomes_a_register_row_named_like_the_route_leg(bundle):
    rows, counts = entsog_tariff_rows(
        IUK_CROSSING, bundle=bundle, downloaded=DOWNLOADED, received_at=RECEIVED
    )
    assert counts["conflicting"] == 0
    by_key = {(row["tso"], row["point_id"], row["direction"]): row for row in rows}
    iuk = by_key[("Interconnector", "ITP-00005", "ENTRY")]
    assert iuk["source_point_name"] == "Bacton (IUK)" and iuk["country"] == "GB"
    # EUR per kWh/h per day at full load: x 1000 kWh/MWh / 24 h.
    assert iuk["tariff_value"] == pytest.approx(0.00996903 * 1000 / 24)
    assert iuk["unit"] == "EUR/MWh" and iuk["currency"] == "EUR"
    assert iuk["gas_year"] == "2026/27"
    assert iuk["effective_from"].date() == date(2026, 10, 1)
    assert iuk["effective_to"].date() == date(2027, 9, 30)
    assert iuk["tariff_status"] == "FINAL" and iuk["manual_review_required"] is False
    assert "ENTSOG TP [17-11-2026] https://transparency.entsog.eu/" in iuk["source_refs"]
    assert by_key[("Fluxys Belgium", "ITP-00061", "ENTRY")]["gas_year"] == "2026"
    assert per_mwh_at_full_load(0.01342699) == pytest.approx(0.5594579, rel=1e-6)


def test_a_period_of_any_shape_has_a_label_that_fits_the_register(bundle):
    rows, _ = entsog_tariff_rows(
        [record("ITP-00137", "FR-TSO-0003", "entry", 0.0085, "2026-04-01", "2027-04-01")],
        bundle=bundle,
        downloaded=DOWNLOADED,
        received_at=RECEIVED,
    )
    assert rows[0]["gas_year"] == "2026-04..27-03"
    assert all(len(row["gas_year"]) <= 16 for row in rows)  # tso_tariffs.gas_year


def test_a_later_period_is_indicative_and_nothing_is_estimated(bundle):
    rows, counts = entsog_tariff_rows(
        [
            record("ITP-00005", "UK-TSO-0003", "entry", 0.01, "2027-10-01", "2028-10-01"),
            record(
                "ITP-00005",
                "UK-TSO-0003",
                "entry",
                0.01,
                "2026-10-01",
                "2027-10-01",
                productType="Quarterly",
            ),
            record(
                "ITP-00005",
                "UK-TSO-0003",
                "entry",
                0.01,
                "2026-10-01",
                "2027-10-01",
                isArchived=True,
            ),
            record("ITP-00005", "UK-TSO-0003", "exit", "", "2026-10-01", "2027-10-01"),
            record(
                "ITP-00005",
                "UK-TSO-0003",
                "exit",
                0.01,
                "2026-10-01",
                "2027-10-01",
                applicableTariffInCommonUnitUnit="Euro/(kWh/d)/y",
            ),
            record("ITP-99999", "UK-TSO-0003", "exit", 0.01, "2026-10-01", "2027-10-01"),
        ],
        bundle=bundle,
        downloaded=DOWNLOADED,
        received_at=RECEIVED,
    )
    assert [row["tariff_status"] for row in rows] == ["INDICATIVE"]
    assert rows[0]["manual_review_required"] is True
    assert counts == {
        "product_not_stored": 1,
        "archived": 1,
        "value_or_period_missing": 1,
        "unit_not_common": 1,
        "point_outside_adjacency": 1,
        "conflicting": 0,
    }


def test_two_publications_of_one_tariff_that_disagree_are_both_refused(bundle):
    rows, counts = entsog_tariff_rows(
        [
            record("ITP-00005", "UK-TSO-0003", "entry", 0.01, "2026-10-01", "2027-10-01"),
            {
                **record("ITP-00005", "UK-TSO-0003", "entry", 0.02, "2026-10-01", "2027-10-01"),
                "id": "other",
            },
        ],
        bundle=bundle,
        downloaded=DOWNLOADED,
        received_at=RECEIVED,
    )
    assert rows == [] and counts["conflicting"] == 1


def test_published_tariffs_price_nbp_to_ztp_through_iuk(bundle):
    rows, _ = entsog_tariff_rows(
        IUK_CROSSING, bundle=bundle, downloaded=DOWNLOADED, received_at=RECEIVED
    )
    tariffs = [_tariff_from_record(TsoTariffRecord(**row)) for row in rows]
    [candidate] = apply_route_adjacency(
        [
            {
                "route_id": "nbp-ztp",
                "start_point_name": "NBP",
                "target_point_name": "ZTP",
                "route_legs": [],
            }
        ]
    )
    legs = [RouteTariffLeg.model_validate(leg) for leg in candidate["route_legs"]]
    result = calculate_route_cost(
        RouteCostScenario(
            scenario_id="nbp-ztp",
            source_resource_type="PIPELINE_IMPORT",
            start_point_id="NBP",
            target_hub_or_point_id="ZTP",
            business_model="CROSS_BORDER_TRANSFER",
            delivery_mode="BORDER_TRANSFER",
            gas_year=legs[0].gas_year,
            tariff_applicability_date=date(2026, 11, 17),
            capacity_product="ANNUAL",
            firmness="FIRM",
            tariff_legs=legs,
        ),
        tariffs,
    )
    assert result.status == "SUCCESS", result.missing_inputs
    expected = sum(
        per_mwh_at_full_load(float(r["applicableTariffInCommonUnitValue"])) for r in IUK_CROSSING
    )
    assert result.total_cost == pytest.approx(expected, abs=1e-4)  # the engine rounds to 4 dp
    assert result.unit == "EUR/MWh"


def test_the_tariff_read_covers_every_point_route_pricing_crosses(bundle):
    points = tariff_points(bundle)
    assert {"ITP-00005", "ITP-00061", "ITP-00063", "ITP-00207", "ITP-10012"} <= set(points)


def test_a_point_without_published_tariffs_is_an_empty_complete_read():
    def answer(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"message": "No result found"})

    with httpx.Client(transport=httpx.MockTransport(answer)) as client:
        result = fetch_entsog_dataset(
            client, "tariffsfulls", filters={"pointKey": "ITP-00063"}, sleep=lambda _: None
        )
    assert result.complete and result.record_count == 0
    assert result.stop_reason == "provider_no_result"
    assert result.pages and result.received_at_utc is not None


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
            [record("ITP-00207", "UK-TSO-0004", "exit", 0.0288, "2026-10-01", "2027-10-01")],
            bundle=load_bundle(),
            downloaded=DOWNLOADED,
            received_at=RECEIVED,
        )
        session.add_all(TsoTariffRecord(**row) for row in rows)
        session.flush()
        assert seed.retire_simulated_tariffs(session) == 1
        left = {(row.tso, row.direction) for row in simulated}
        assert left == {("GTS", "EXIT"), ("National Gas TSO", "ENTRY")}
