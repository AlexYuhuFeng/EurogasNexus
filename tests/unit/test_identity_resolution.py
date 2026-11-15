"""ONT-02: one identity resolver; unknown identifiers are quarantined and listed, never guessed."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.application.desk_text import hub_for_zone
from eurogas_nexus.application.identity_resolution import (
    entsog_reference_identities,
    identity_report,
    load_resolver,
    record_identities,
)
from eurogas_nexus.application.physical_native_rates import serialize_native_rate
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import FlowObservationRecord, SourceEntityMappingRecord
from eurogas_nexus.db.repositories.research import upsert_source_entity_mapping
from eurogas_nexus.domain.ontology.source_identity import (
    BUILTIN_SOURCE_IDENTITIES,
    mapping_index,
    resolve_identifier,
)
from eurogas_nexus.ingestion.entsog_native_units import parse_entsog_native_rate

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "eurogas_nexus"

#: The call sites that took a hub from a product's first word or a substring (ONT-02).
FORMER_HEURISTIC_SITES = (
    "application/projections/daily_closes.py",
    "application/storage_nomination_composition.py",
    "db/repositories/backtest.py",
    "domain/market_intelligence/normalized_view.py",
    "domain/route_cost/portfolio_network.py",
    "application/contract_intake.py",
    "application/desk_text.py",
)


def test_the_heuristic_call_sites_are_gone() -> None:
    first_word = re.compile(r"\.split\((\" \")?\)\[0\]")
    for relative in FORMER_HEURISTIC_SITES:
        text = (SRC / relative).read_text(encoding="utf-8")
        assert not first_word.search(text), relative
        assert "n.upper() in upper" not in text and "if hub in upper" not in text, relative


def test_built_in_identifiers_resolve_and_unknown_ones_are_quarantined() -> None:
    assert resolve_identifier("src-gie", "gie_storage_country", "DE").canonical_entity_id == (
        "ent:storage_site:DE"
    )
    assert resolve_identifier("src-gie", "gie_storage_country", "eu").resolved
    assert resolve_identifier("src-entsoe", "bidding_zone", "DE_LU").basis == "builtin"
    assert resolve_identifier(
        "src-national-gas-demand", "national_gas_publication", "PUBOB637"
    ).resolved
    unknown = resolve_identifier("src-gie", "gie_storage_country", "Deutschland")
    assert (unknown.canonical_entity_id, unknown.basis, unknown.reason) == (
        None, "quarantined", "unknown_identifier"
    )
    assert resolve_identifier("src-gie", "gie_storage_country", " ").reason == "empty_identifier"
    # No prefix or case guessing: "de" is not "DE".
    assert not resolve_identifier("src-gie", "gie_storage_country", "de").resolved


def test_two_mappings_for_one_identifier_are_ambiguous_not_the_first_row() -> None:
    index = mapping_index(BUILTIN_SOURCE_IDENTITIES)
    index[("src-x", "entsog_point", "P1")] = {"ent:point:A", "ent:point:B"}
    resolution = resolve_identifier("src-x", "entsog_point", "P1", mappings=index)
    assert resolution.reason == "ambiguous_identifier" and not resolution.resolved


def test_zone_text_names_a_hub_only_as_a_word() -> None:
    assert hub_for_zone("NETHERLANDS") is None  # used to read THE out of "neTHErlands"
    assert hub_for_zone("TTF") == "TTF"
    assert hub_for_zone("DE-GASPOOL") == "THE"


@pytest.fixture
def session():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db


def _flow(observation_id: str, point: str, operator: str) -> FlowObservationRecord:
    day = datetime(2026, 11, 10, 5, tzinfo=UTC)
    native = serialize_native_rate(parse_entsog_native_rate("1000.0", "kWh/d"))
    return FlowObservationRecord(
        observation_id=observation_id, point_id=point, point_name=point, direction="entry",
        kind="actual", flow_mcm_d=None, original_value=1000.0, original_unit="kWh/d",
        period_start_utc=day, period_end_utc=day + timedelta(days=1),
        observed_at_utc=day + timedelta(days=1), source_system="ENTSOG",
        source_reference="t", freshness="daily", research_only=True,
        metadata_json={"operatorKey": operator},
        normalizer_version=native["normalizer_version"], native_rate_json=native,
    )


def test_entsog_keys_resolve_through_the_reference_mappings_and_the_rest_are_listed(session):
    identities = entsog_reference_identities(
        [{"source_system": "ENTSOG", "source_record_id": "ITP-00106", "name": "Zeebrugge ZPT"}],
        [{"point_key": "ITP-00106", "point_name": "Zeebrugge ZPT",
          "operator_key": "BE-TSO-0001", "operator_name": "Fluxys Belgium"}],
    )
    first = record_identities(session, identities)
    again = record_identities(session, identities)
    assert first == {"identities": 2, "entities_added": 2, "mappings_added": 2}
    assert again["mappings_added"] == 0  # idempotent
    session.add_all([
        _flow("a", "ITP-00106", "BE-TSO-0001"),
        _flow("b", "ITP-99999", "BE-TSO-0001"),
        _flow("c", "ITP-99999", "XX-TSO-0001"),
    ])
    session.commit()
    resolver = load_resolver(session)
    assert resolver.resolve("src-entsog", "entsog_point", "ITP-00106").canonical_entity_id == (
        "ent:point:ITP-00106"
    )
    report = identity_report(session, resolver)["src-entsog"]
    assert (report["checked"], report["resolved"]) == (4, 2)
    assert report["unresolved"] == [
        {"entity_type": "entsog_point", "identifier": "ITP-99999",
         "reason": "unknown_identifier", "count": 2, "withheld": True},
        {"entity_type": "entsog_operator", "identifier": "XX-TSO-0001",
         "reason": "unknown_identifier", "count": 1, "withheld": True},
    ]


def test_a_deployment_delivery_point_mapping_resolves_a_contract_hub(session):
    from eurogas_nexus.db.repositories.research import upsert_canonical_entity

    upsert_canonical_entity(
        session, canonical_entity_id="ent:market_hub:TTF", entity_type="market_hub",
        canonical_code="TTF", display_name="TTF",
    )
    upsert_source_entity_mapping(
        session, mapping_id="map:desk:dp:groningen", canonical_entity_id="ent:market_hub:TTF",
        source_id="desk", source_entity_type="delivery_point",
        source_identifier="Groningen exit", valid_from_utc=datetime(2020, 1, 1, tzinfo=UTC),
    )
    session.commit()
    resolver = load_resolver(session)
    assert resolver.hub("Groningen exit, NL").hub == "TTF"
    assert resolver.hub("Somewhere, Netherlands").hub is None  # never a default hub
    assert session.query(SourceEntityMappingRecord).count() == 1
