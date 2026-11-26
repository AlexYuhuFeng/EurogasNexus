"""Reviewed public transmission tariffs: record, four-eyes review, pricing, retirement.

The store is in-memory SQLite; every figure is made up.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import eurogas_nexus.db.models  # noqa: F401  (registers every table)
from eurogas_nexus.application import simulated_tariffs
from eurogas_nexus.application import tso_tariff_entries as entries
from eurogas_nexus.application.route_tariff_cost import (
    load_tariff_rows,  # noqa: F401  (the register read the leg read defaults to)
    public_tariff_for_leg,
    route_cost,
)
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import AuditEventRecord, TsoTariffEntryRecord, TsoTariffRecord
from eurogas_nexus.domain.market.fx_forward import Delivery
from eurogas_nexus.ingestion.entsog_tariffs import entsog_tariff_rows
from eurogas_nexus.reference_data.network_bundle import load_bundle
from tests.unit.test_entsog_tariffs import record

NOW = datetime(2026, 11, 19, 10, tzinfo=UTC)
DEC_26 = Delivery(date(2026, 12, 1), date(2026, 12, 31), "month", "Dec-26")


def national_gas_exit(**overrides):
    """National Gas's IP exit charge at Bacton (IUK), as an administrator reads it (made up)."""

    return {
        "operator_key": "UK-TSO-0001",
        "point_key": "ITP-00005",
        "direction": "EXIT",
        "capacity_product": "ANNUAL",
        "firmness": "FIRM",
        "tariff_value": 0.04,
        "unit": "p/kWh/d",
        "currency": "GBP",
        "valid_from": "2026-10-01",
        "valid_to": "2027-09-30",
        "published_status": "FINAL",
        "source_url": "https://www.example.org/ip-reserve-prices-2026.pdf",
        "published_on": "2026-05-29",
        "source_location": "page 2, table 1, Bacton IP exit",
        **overrides,
    }


@pytest.fixture()
def session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def register_rows(session):
    return [
        {
            c: getattr(row, c)
            for c in (
                "tariff_id",
                "tso",
                "point_id",
                "direction",
                "gas_year",
                "tariff_value",
                "currency",
                "unit",
                "effective_from",
                "effective_to",
                "tariff_status",
                "source_table",
                "capacity_product",
                "firmness",
            )
        }
        for row in session.query(TsoTariffRecord).all()
    ]


def test_a_candidate_prices_as_indicative_and_a_second_person_makes_it_reviewed(session):
    made = entries.record_entry(session, national_gas_exit(), actor="ops.alice", now_utc=NOW)
    assert made["state"] == "CANDIDATE" and made["tso"] == "National Gas TSO"
    assert made["point_name"] == "Bacton (IUK)" and made["gas_year"] == "2026/27"
    leg = public_tariff_for_leg(
        "ITP-00005", "EXIT", "National Gas TSO", date(2026, 12, 1), rows=register_rows(session)
    )
    # 0.04 p/kWh/d = 0.0004 GBP per kWh per day = 0.4 GBP/MWh at 100 % load factor.
    assert leg.value == pytest.approx(0.4) and leg.currency == "GBP"
    assert leg.input_class == "indicative"
    assert leg.source_kind == "public tariff, awaiting review"

    with pytest.raises(entries.TariffEntryError) as refused:
        entries.review_entry(session, made["entry_id"], reviewer="ops.alice", now_utc=NOW)
    assert refused.value.code == "four_eyes"
    reviewed = entries.review_entry(session, made["entry_id"], reviewer="ops.bob", now_utc=NOW)
    assert reviewed["state"] == "REVIEWED" and reviewed["reviewed_by"] == "ops.bob"
    leg = public_tariff_for_leg(
        "ITP-00005", "EXIT", "National Gas TSO", date(2026, 12, 1), rows=register_rows(session)
    )
    assert leg.input_class == "sourced" and leg.source_kind == "reviewed public tariff"
    actions = {row.action for row in session.query(AuditEventRecord).all()}
    assert {"tso_tariff_entry.record", "tso_tariff_entry.review"} <= actions


def test_the_entry_completes_a_route_ENTSOG_leaves_open(session):
    bundle = load_bundle()
    published, _ = entsog_tariff_rows(
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
            ),
            record(
                "ITP-00061",
                "UK-TSO-0003",
                "exit",
                3.0,
                "2026-10-01",
                "2027-10-01",
                currency="GBP",
                eur_rate=1.16,
            ),
            record("ITP-00061", "BE-TSO-0001", "entry", 0.8, "2026-01-01", "2027-01-01"),
        ],
        bundle=bundle,
        downloaded=date(2026, 11, 19),
        received_at=NOW,
    )
    session.add_all(TsoTariffRecord(**row) for row in published)
    session.flush()
    before = route_cost("NBP", "ZTP", DEC_26, register_rows(session), fx={"GBP": 1.15})
    assert not before.complete and before.missing_legs() == ["Bacton (IUK) exit (National Gas TSO)"]
    made = entries.record_entry(session, national_gas_exit(), actor="ops.alice", now_utc=NOW)
    entries.review_entry(session, made["entry_id"], reviewer="ops.bob", now_utc=NOW)
    after = route_cost("NBP", "ZTP", DEC_26, register_rows(session), fx={"GBP": 1.15})
    assert after.complete and after.total is not None and after.currency == "EUR"


@pytest.mark.parametrize(
    ("override", "code"),
    [
        ({"operator_key": "XX-TSO-9999"}, "operator_unknown"),
        ({"point_key": "ITP-99999"}, "point_unknown"),
        ({"operator_key": "DK-TSO-0001"}, "operator_not_at_point"),
        ({"unit": "p/therm"}, "unit_not_understood"),
        ({"currency": "EUR"}, "currency_mismatch"),
        ({"valid_to": "2026-01-01"}, "period_invalid"),
        ({"published_on": "2027-01-01"}, "published_on_future"),
        ({"source_url": "http://example.org"}, "source_url_invalid"),
        ({"source_location": " "}, "source_location_required"),
        ({"tariff_value": -1}, "value_invalid"),
        ({"published_status": "maybe"}, "status_invalid"),
    ],
)
def test_an_entry_names_what_it_needs(session, override, code):
    with pytest.raises(entries.TariffEntryError) as refused:
        entries.record_entry(session, national_gas_exit(**override), actor="a", now_utc=NOW)
    assert refused.value.code == code


def test_a_leg_entsog_publishes_is_not_entered_and_two_entries_do_not_overlap(session):
    published, _ = entsog_tariff_rows(
        [record("ITP-10012", "NL-TSO-0001", "exit", 4.0, "2026-01-01", "2027-01-01")],
        bundle=load_bundle(),
        downloaded=date(2026, 11, 19),
        received_at=NOW,
    )
    session.add_all(TsoTariffRecord(**row) for row in published)
    session.flush()
    gts_exit = national_gas_exit(
        operator_key="NL-TSO-0001",
        point_key="ITP-10012",
        unit="EUR/(kWh/h)/y",
        currency="EUR",
        valid_from="2026-01-01",
        valid_to="2026-12-31",
    )
    with pytest.raises(entries.TariffEntryError) as refused:
        entries.record_entry(session, gts_exit, actor="a", now_utc=NOW)
    assert refused.value.code == "published_row_held"
    entries.record_entry(session, national_gas_exit(), actor="a", now_utc=NOW)
    with pytest.raises(entries.TariffEntryError) as refused:
        entries.record_entry(session, national_gas_exit(), actor="b", now_utc=NOW)
    assert refused.value.code == "entry_exists"


def test_an_ingested_published_row_retires_the_entry_and_a_withdrawn_one_stops_pricing(session):
    made = entries.record_entry(
        session,
        national_gas_exit(
            operator_key="NL-TSO-0001",
            point_key="ITP-10012",
            unit="EUR/(kWh/h)/y",
            currency="EUR",
            valid_from="2027-01-01",
            valid_to="2027-12-31",
        ),
        actor="a",
        now_utc=NOW,
    )
    entries.review_entry(session, made["entry_id"], reviewer="b", now_utc=NOW)
    published, _ = entsog_tariff_rows(
        [record("ITP-10012", "NL-TSO-0001", "exit", 4.2, "2027-01-01", "2028-01-01")],
        bundle=load_bundle(),
        downloaded=date(2026, 11, 19),
        received_at=NOW,
    )
    session.add_all(TsoTariffRecord(**row) for row in published)
    session.flush()
    assert entries.retire_superseded_entries(session, now_utc=NOW) == 1
    row = session.get(TsoTariffEntryRecord, made["entry_id"])
    assert row.state == "RETIRED" and "entsog-nl-tso-0001" in row.closed_reason
    assert session.get(TsoTariffRecord, entries.mirror_id(made["entry_id"])) is None
    assert entries.retire_superseded_entries(session, now_utc=NOW) == 0

    other = entries.record_entry(session, national_gas_exit(), actor="a", now_utc=NOW)
    with pytest.raises(entries.TariffEntryError):
        entries.withdraw_entry(session, other["entry_id"], actor="a", reason=" ")
    entries.withdraw_entry(session, other["entry_id"], actor="a", reason="typo in the value")
    assert session.get(TsoTariffRecord, entries.mirror_id(other["entry_id"])) is None


def test_a_reviewed_entry_retires_a_simulated_leg_and_a_candidate_does_not(session):
    for row in simulated_tariffs.simulated_tariff_records(
        today=date(2026, 11, 19), now=NOW, gas_year="2026/27", source_ref="demo"
    ):
        session.add(TsoTariffRecord(**row))
    session.flush()
    made = entries.record_entry(session, national_gas_exit(), actor="a", now_utc=NOW)
    assert simulated_tariffs.retire_simulated_tariffs(session) == 0
    entries.review_entry(session, made["entry_id"], reviewer="b", now_utc=NOW)
    # The leg's yearly, monthly and daily simulated rows all go.
    assert simulated_tariffs.retire_simulated_tariffs(session) == len(
        simulated_tariffs.SIMULATED_PRODUCT_MULTIPLIERS
    )
    left = {
        (row.tso, row.point_id, row.direction)
        for row in session.query(TsoTariffRecord).filter(
            TsoTariffRecord.document_id == simulated_tariffs.SIMULATED_TARIFF_DOCUMENT
        )
    }
    assert ("National Gas TSO", "ITP-00005", "EXIT") not in left
    assert len(left) == len(simulated_tariffs.SIMULATED_TARIFF_LEGS) - 1


def test_the_view_lists_the_legs_that_block_drawn_routes_first(session):
    view = entries.entries_view(session, today=date(2026, 11, 19))
    first = view["missing"][0]
    assert first["can_be_entered"] and first["drawn"] and first["kind"] == "crossing"
    keys = {(item["point_key"], item["tso"], item["direction"]) for item in view["missing"]}
    assert ("ITP-00005", "National Gas TSO", "EXIT") in keys
    unknown = [item for item in view["missing"] if not item["can_be_entered"]]
    assert all(item["why_not"] for item in unknown)
    assert view["missing"].index(unknown[0]) > view["missing"].index(first)
    points = {item["point_key"]: item for item in view["choices"]["points"]}
    assert {"operator_key": "UK-TSO-0001", "directions": ["ENTRY", "EXIT"]} in points["ITP-00005"][
        "operators"
    ]


def test_every_simulated_leg_is_a_leg_the_graph_prices():
    from eurogas_nexus.reference_data.network_adjacency import shipped_market_area_graph

    graph = shipped_market_area_graph()
    named = set()
    for start in graph.hub_names:
        for target in graph.neighbours(start):
            for crossing in graph.crossings(start, target):
                for spec in graph.legs(crossing):
                    for tso in spec.tso.split(" / "):
                        named.add((tso, spec.point_key, spec.direction))
    for _country, tso, point, _name, direction, _value in simulated_tariffs.SIMULATED_TARIFF_LEGS:
        assert (tso, point, direction) in named, (tso, point, direction)


def test_every_unit_the_entry_form_offers_is_one_the_pricing_reads():
    import re
    from pathlib import Path

    from eurogas_nexus.domain.route_cost.tariff_units import parse_unit

    model = Path(__file__).resolve().parents[2] / "clients/web/src/app/model/tariffEntryModel.ts"
    block = model.read_text(encoding="utf-8").split("ENTRY_UNITS", 1)[1].split("};", 1)[0]
    for currency, units in re.findall(r"(\w+): \[([^\]]+)\]", block):
        for unit in re.findall(r'"([^"]+)"', units):
            parsed = parse_unit(unit)
            assert parsed is not None and parsed.currency == currency, unit
