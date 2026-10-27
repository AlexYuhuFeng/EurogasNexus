"""Validation tests plus golden checks of the committed LNG terminal-reference manifest.

Synthetic fixtures exercise validation edge cases and are never promoted into the
committed manifest. ``CAPTURED_SOURCES`` and ``CAPTURED_FACTS`` assert the metadata and
claims already committed; they are not new source evidence, terminal rights or
readiness.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import UTC, date, datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path

import pytest
from pydantic import ValidationError

from eurogas_nexus.domain.route_cost import lng_terminal_reference as reference
from eurogas_nexus.domain.route_cost.lng_terminal_reference import (
    MANIFEST_MODEL_VERSION,
    MANIFEST_SCHEMA_VERSION,
    MAX_CANDIDATE_BYTES,
    FactParameter,
    FactReviewStatus,
    LngFactLookupStatus,
    LngReferenceErrorCode,
    LngTerminalFact,
    LngTerminalReferenceError,
    LngTerminalReferenceManifest,
    LngTerminalSource,
    QuantityBasis,
    SourceChangeStatus,
    compare_lng_terminal_source_bytes,
    dump_lng_terminal_reference_manifest,
    inspect_candidate_lng_terminal_facts,
    load_lng_terminal_reference_manifest,
    loads_lng_terminal_reference_manifest,
    lookup_reviewed_lng_terminal_fact,
    parse_retrieved_at_utc,
    read_lng_terminal_candidate_file,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
CLI = REPO_ROOT / "scripts/ops/compare_lng_terminal_reference.py"
COMMITTED_MANIFEST = REPO_ROOT / "data/reference/lng_terminal_reference_manifest.json"
CAPTURE_BYTES = b"synthetic captured operator page bytes\n"
CAPTURE_SHA256 = sha256(CAPTURE_BYTES).hexdigest()
RETRIEVED_AT = datetime(2026, 10, 27, 9, 0, tzinfo=UTC)
REVIEWED_AT = datetime(2026, 10, 27, 10, 0, tzinfo=UTC)

# Golden metadata from the preserved captures named in the committed candidate
# manifest. These are assertions about the committed records, not new source evidence.
CAPTURED_SOURCES: dict[str, dict[str, object]] = {
    "gate-operational": {
        "official_url": "https://www.gateterminal.com/en/commercial/operational-data/",
        "operator": "Gate terminal",
        "document_title": "Operational data",
        "captured_sha256": (
            "222f6d89f422fd8f33fbd4959461fa4b49959be744d2850b55dfb36fd860f205"
        ),
        "retrieved_at_utc": datetime(2026, 10, 27, 14, 13, 49, 470061, tzinfo=UTC),
    },
    "gate-faq": {
        "official_url": "https://www.gateterminal.com/en/gate-terminal/faq/",
        "operator": "Gate terminal",
        "document_title": "FAQ",
        "captured_sha256": (
            "e7bcff83d859b7f9025450d11ea6e6f48c58f33abea78abcc5ecc657f681752f"
        ),
        "retrieved_at_utc": datetime(2026, 10, 27, 14, 14, 45, 979968, tzinfo=UTC),
    },
    "dunkerque-infrastructure": {
        "official_url": "https://www.fluxys.com/en/about-us/dunkerque-lng/infrastructure",
        "operator": "Dunkerque LNG",
        "document_title": "Dunkerque LNG Infrastructure",
        "captured_sha256": (
            "aca9b21f8bb8cb705481e2016e910f2ceea411000fa3bf61adb16832e64a82ad"
        ),
        "retrieved_at_utc": datetime(2026, 10, 27, 14, 13, 49, 505751, tzinfo=UTC),
    },
    "grain-operational": {
        "official_url": "https://www.grainlng.com/operational-information",
        "operator": "Grain LNG",
        "document_title": "Operational information",
        "captured_sha256": (
            "9243ff6f925f5ae2e5a3dcda66d309ec6a6cd7fc3c83efe5c43614e4b64dfc5e"
        ),
        "retrieved_at_utc": datetime(2026, 10, 27, 14, 13, 49, 931386, tzinfo=UTC),
    },
    "southhook-operations": {
        "official_url": "https://www.southhooklng.com/operations/what-we-do/",
        "operator": "South Hook LNG",
        "document_title": "What We Do",
        "captured_sha256": (
            "792b29e57c4f306c177ce7f4796171e9f4341085b2107249a8fe18c669bfa22c"
        ),
        "retrieved_at_utc": datetime(2026, 10, 27, 14, 13, 49, 640660, tzinfo=UTC),
    },
}

CAPTURED_FACTS: dict[str, dict[str, object]] = {
    "gate-vessel-unloading-max": {
        "terminal_id": "gate-terminal",
        "parameter": FactParameter.VESSEL_UNLOADING_MAX_RATE,
        "value": "12500",
        "original_value_text": "12.500 m3/h of LNG",
        "original_unit": "m3/h of LNG",
        "quantity_basis": QuantityBasis.LIQUID_LNG_M3_PER_HOUR,
        "quotation": "Max. Vessel discharge rate is 12.500 m3/h of LNG",
        "source_id": "gate-operational",
    },
    "gate-minimum-sendout": {
        "terminal_id": "gate-terminal",
        "parameter": FactParameter.MINIMUM_SENDOUT_RATE,
        "value": "139000",
        "original_value_text": "139.000 m3(n)/h",
        "original_unit": "m3(n)/h",
        "quantity_basis": QuantityBasis.NORMAL_GAS_NM3_PER_HOUR,
        "quotation": "Min delivery rate of the terminal is 139.000 m3(n)/h",
        "source_id": "gate-operational",
    },
    "gate-tank-evaporation": {
        "terminal_id": "gate-terminal",
        "parameter": FactParameter.TANK_EVAPORATION_RATE,
        "value": "0.07",
        "original_value_text": "approximately 0.07% of the tank capacity per day",
        "original_unit": "% of tank capacity per day",
        "quantity_basis": QuantityBasis.TANK_CAPACITY_PERCENT_PER_DAY,
        "quotation": "approximately 0.07% of the tank capacity per day",
        "source_id": "gate-faq",
    },
    "dunkerque-vessel-unloading-max": {
        "terminal_id": "dunkerque-lng",
        "parameter": FactParameter.VESSEL_UNLOADING_MAX_RATE,
        "value": "14000",
        "original_value_text": "14,000 m³ per hour",
        "original_unit": "m³ per hour",
        "quantity_basis": QuantityBasis.LIQUID_LNG_M3_PER_HOUR,
        "quotation": "maximum flow rate of 14,000 m³ per hour",
        "source_id": "dunkerque-infrastructure",
    },
    "grain-regasification-equipment-645": {
        "terminal_id": "grain-lng",
        "parameter": FactParameter.REGASIFICATION_CAPACITY,
        "value": "645",
        "original_value_text": "645 GWh/d",
        "original_unit": "GWh/d",
        "quantity_basis": QuantityBasis.ENERGY_GWH_PER_DAY,
        "quotation": "capable of regasifying 645 GWh/d",
        "source_id": "grain-operational",
    },
    "grain-primary-capacity-654": {
        "terminal_id": "grain-lng",
        "parameter": FactParameter.REGASIFICATION_CAPACITY,
        "value": "654",
        "original_value_text": "circa 654 GWh/d",
        "original_unit": "GWh/d",
        "quantity_basis": QuantityBasis.ENERGY_GWH_PER_DAY,
        "quotation": "circa 654 GWh/d regasification capacity",
        "source_id": "grain-operational",
    },
    "southhook-vessel-discharge-duration": {
        "terminal_id": "south-hook-lng",
        "parameter": FactParameter.VESSEL_DISCHARGE_DURATION,
        "value": "24",
        "original_value_text": "up to 24 hours",
        "original_unit": "hours",
        "quantity_basis": QuantityBasis.DURATION_HOURS,
        "quotation": "discharge process which can take up to 24 hours",
        "source_id": "southhook-operations",
    },
}


def _source(**overrides: object) -> LngTerminalSource:
    data: dict[str, object] = {
        "source_id": "synthetic-source-a",
        "official_url": "https://example.invalid/synthetic-terminal-page",
        "operator": "Synthetic Operator",
        "document_title": "Synthetic terminal page",
        "publication_version": "UNDATED_PAGE",
        "captured_sha256": CAPTURE_SHA256,
        "retrieved_at_utc": RETRIEVED_AT,
        "published_date": None,
        "applicability_notes": "Synthetic source scope; not operator evidence.",
    }
    data.update(overrides)
    return LngTerminalSource(**data)


def _fact(**overrides: object) -> LngTerminalFact:
    data: dict[str, object] = {
        "fact_id": "synthetic-gate-unloading-max",
        "terminal_id": "synthetic-terminal-a",
        "parameter": FactParameter.VESSEL_UNLOADING_MAX_RATE,
        "value": "12.500",
        "original_value_text": "12.500 m3/h of LNG",
        "original_unit": "m3/h of LNG",
        "quantity_basis": QuantityBasis.LIQUID_LNG_M3_PER_HOUR,
        "quotation": "Synthetic quoted operator statement",
        "source_id": "synthetic-source-a",
        "applicability_notes": "Synthetic test claim; no official applicability.",
        "effective_from": date(2026, 1, 1),
        "effective_to": None,
        "review_status": FactReviewStatus.REVIEWED,
        "reviewed_by": "synthetic-reviewer",
        "reviewed_at": REVIEWED_AT,
    }
    data.update(overrides)
    return LngTerminalFact(**data)


def _candidate_fact(**overrides: object) -> LngTerminalFact:
    data: dict[str, object] = {
        "fact_id": "synthetic-candidate-unloading",
        "review_status": FactReviewStatus.CANDIDATE,
        "reviewed_by": None,
        "reviewed_at": None,
        "effective_from": None,
        "effective_to": None,
        "quotation": "Synthetic candidate quotation",
    }
    data.update(overrides)
    return _fact(**data)


def _manifest(
    *,
    sources: list[LngTerminalSource] | None = None,
    facts: list[LngTerminalFact] | None = None,
) -> LngTerminalReferenceManifest:
    return LngTerminalReferenceManifest(
        schema_version=MANIFEST_SCHEMA_VERSION,
        model_version=MANIFEST_MODEL_VERSION,
        notes="Synthetic-only test manifest; no official fact is asserted.",
        sources=tuple([_source()] if sources is None else sources),
        facts=tuple([_fact()] if facts is None else facts),
    )


def _run_cli(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=90,
    )


def test_manifest_roundtrip_preserves_versions_and_exact_value() -> None:
    manifest = _manifest()
    document = json.loads(dump_lng_terminal_reference_manifest(manifest))
    loaded = loads_lng_terminal_reference_manifest(json.dumps(document))

    assert loaded == manifest
    assert document["schema_version"] == MANIFEST_SCHEMA_VERSION
    assert document["model_version"] == MANIFEST_MODEL_VERSION
    assert loaded.sources[0].publication_version == "UNDATED_PAGE"
    assert loaded.sources[0].published_date is None
    assert loaded.facts[0].value == "12.500"
    assert loaded.facts[0].effective_from == date(2026, 1, 1)
    assert loaded.facts[0].effective_to is None


def test_models_are_frozen_and_immutable() -> None:
    manifest = _manifest()
    with pytest.raises(ValidationError):
        manifest.notes = "changed"
    with pytest.raises(ValidationError):
        manifest.sources[0].captured_sha256 = "0" * 64
    with pytest.raises(ValidationError):
        manifest.facts[0].value = "0.000"


def test_committed_manifest_has_five_sources_and_seven_candidate_facts() -> None:
    manifest = load_lng_terminal_reference_manifest(COMMITTED_MANIFEST)

    assert manifest.schema_version == MANIFEST_SCHEMA_VERSION
    assert manifest.model_version == MANIFEST_MODEL_VERSION
    assert len(manifest.sources) == 5
    assert len(manifest.facts) == 7
    assert {source.source_id for source in manifest.sources} == set(CAPTURED_SOURCES)
    assert {fact.fact_id for fact in manifest.facts} == set(CAPTURED_FACTS)
    assert "CANDIDATE" in manifest.notes
    assert "No fact is REVIEWED" in manifest.notes

    for source in manifest.sources:
        expected = CAPTURED_SOURCES[source.source_id]
        assert source.official_url == expected["official_url"]
        assert source.operator == expected["operator"]
        assert source.document_title == expected["document_title"]
        assert source.published_date is None
        assert source.publication_version == "UNDATED_PAGE"
        assert source.retrieved_at_utc == expected["retrieved_at_utc"]
        assert source.captured_sha256 == expected["captured_sha256"]
        assert re.fullmatch(r"[0-9a-f]{64}", source.captured_sha256)

    for fact in manifest.facts:
        assert fact.review_status is FactReviewStatus.CANDIDATE
        assert fact.reviewed_by is None
        assert fact.reviewed_at is None
        assert fact.effective_from is None
        assert fact.effective_to is None
        assert fact.has_known_applicability_start is False


def test_committed_candidate_facts_preserve_values_raw_text_and_units() -> None:
    manifest = load_lng_terminal_reference_manifest(COMMITTED_MANIFEST)
    facts = {fact.fact_id: fact for fact in manifest.facts}

    assert set(facts) == set(CAPTURED_FACTS)
    for fact_id, expected in CAPTURED_FACTS.items():
        fact = facts[fact_id]
        for field, expected_value in expected.items():
            assert getattr(fact, field) == expected_value

    evaporation = facts["gate-tank-evaporation"]
    grain_equipment = facts["grain-regasification-equipment-645"]
    grain_primary = facts["grain-primary-capacity-654"]
    south_hook = facts["southhook-vessel-discharge-duration"]
    assert evaporation.quantity_basis is QuantityBasis.TANK_CAPACITY_PERCENT_PER_DAY
    assert evaporation.quantity_basis is not QuantityBasis.CARGO_ENERGY_PERCENT
    assert "Equipment subsection" in grain_equipment.applicability_notes
    assert "Primary-market subsection" in grain_primary.applicability_notes
    assert "jetty" in south_hook.applicability_notes
    assert {fact.fact_id for fact in manifest.facts if fact.source_id == "gate-operational"} == {
        "gate-vessel-unloading-max",
        "gate-minimum-sendout",
    }
    assert {fact.fact_id for fact in manifest.facts if fact.source_id == "grain-operational"} == {
        "grain-regasification-equipment-645",
        "grain-primary-capacity-654",
    }


def test_committed_candidates_are_excluded_from_reviewed_scenario_lookup() -> None:
    manifest = load_lng_terminal_reference_manifest(COMMITTED_MANIFEST)

    for fact in manifest.facts:
        result = lookup_reviewed_lng_terminal_fact(
            manifest,
            terminal_id=fact.terminal_id,
            parameter=fact.parameter,
            quantity_basis=fact.quantity_basis,
            scenario_date=date(2026, 10, 27),
        )
        assert result.status is LngFactLookupStatus.NO_REVIEWED_FACT
        assert result.reviewed_facts == ()
        assert result.selected_fact is None
        assert "CANDIDATE_FACTS_EXCLUDED_FROM_REVIEWED_SELECTION" in result.warnings

    inspected = inspect_candidate_lng_terminal_facts(manifest)
    assert len(inspected) == 7
    assert all(fact.review_status is FactReviewStatus.CANDIDATE for fact in inspected)


def test_committed_grain_capacity_claims_remain_distinct_candidates() -> None:
    manifest = load_lng_terminal_reference_manifest(COMMITTED_MANIFEST)

    grain = inspect_candidate_lng_terminal_facts(
        manifest,
        terminal_id="grain-lng",
        parameter=FactParameter.REGASIFICATION_CAPACITY,
        quantity_basis=QuantityBasis.ENERGY_GWH_PER_DAY,
    )

    assert [fact.fact_id for fact in grain] == [
        "grain-regasification-equipment-645",
        "grain-primary-capacity-654",
    ]
    assert {fact.value for fact in grain} == {"645", "654"}
    assert {fact.quotation for fact in grain} == {
        "capable of regasifying 645 GWh/d",
        "circa 654 GWh/d regasification capacity",
    }
    assert all(fact.review_status is FactReviewStatus.CANDIDATE for fact in grain)


@pytest.mark.parametrize(
    ("source_id", "affected_fact_ids"),
    [
        ("gate-operational", ("gate-minimum-sendout", "gate-vessel-unloading-max")),
        ("gate-faq", ("gate-tank-evaporation",)),
        ("dunkerque-infrastructure", ("dunkerque-vessel-unloading-max",)),
        (
            "grain-operational",
            ("grain-primary-capacity-654", "grain-regasification-equipment-645"),
        ),
        ("southhook-operations", ("southhook-vessel-discharge-duration",)),
    ],
)
def test_committed_source_change_lists_affected_facts_without_mutation(
    source_id: str,
    affected_fact_ids: tuple[str, ...],
) -> None:
    manifest = load_lng_terminal_reference_manifest(COMMITTED_MANIFEST)
    before = dump_lng_terminal_reference_manifest(manifest)

    result = compare_lng_terminal_source_bytes(
        manifest,
        source_id=source_id,
        candidate_bytes=b"changed official publication bytes\n",
        retrieved_at_utc=datetime(2026, 10, 28, 12, 0, tzinfo=UTC),
    )

    assert result.status is SourceChangeStatus.REVIEW_REQUIRED
    assert result.source_id == source_id
    assert result.before_sha256 == CAPTURED_SOURCES[source_id]["captured_sha256"]
    assert result.affected_fact_ids == affected_fact_ids
    assert result.auto_replace is False
    assert result.semantic_change_established is False
    assert dump_lng_terminal_reference_manifest(manifest) == before
    assert all(fact.review_status is FactReviewStatus.CANDIDATE for fact in manifest.facts)


@pytest.mark.parametrize(
    "bad_value",
    [12.5, float("nan"), float("inf"), True, "1e3", "9" * 19, "-1", "0.", "1.5.0"],
)
def test_exact_decimal_refuses_float_nonfinite_exponent_and_huge_coefficient(
    bad_value: object,
) -> None:
    with pytest.raises(ValidationError):
        _fact(value=bad_value)


def test_exact_decimal_preserves_trailing_zeros() -> None:
    normal = _fact(
        fact_id="synthetic-sendout-normal",
        parameter=FactParameter.MINIMUM_SENDOUT_RATE,
        value="139.000",
        original_value_text="139.000 m3(n)/h",
        original_unit="m3(n)/h",
        quantity_basis=QuantityBasis.NORMAL_GAS_NM3_PER_HOUR,
    )
    evaporation = _fact(
        fact_id="synthetic-evaporation",
        parameter=FactParameter.EVAPORATION_RATE,
        value="0.0700",
        original_value_text="approximately 0.0700% of tank capacity per day",
        original_unit="% of tank capacity per day",
        quantity_basis=QuantityBasis.TANK_CAPACITY_PERCENT_PER_DAY,
    )

    assert normal.value == "139.000"
    assert evaporation.value == "0.0700"


def test_provenance_reviewer_dates_urls_and_references_are_validated() -> None:
    with pytest.raises(ValidationError):
        _source(operator=" ")
    with pytest.raises(ValidationError):
        _source(official_url="http://example.invalid/page")
    with pytest.raises(ValidationError):
        _source(official_url="https://user:secret@example.invalid/page")
    with pytest.raises(ValidationError):
        _source(official_url="https://example.invalid/page?token=secret")
    with pytest.raises(ValidationError):
        _source(official_url="https://example.invalid/page#fragment")
    with pytest.raises(ValidationError):
        _source(retrieved_at_utc=datetime(2026, 10, 27, 9, 0))
    with pytest.raises(ValidationError):
        _source(captured_sha256="0" * 63)
    with pytest.raises(ValidationError):
        _source(captured_sha256="A" * 64)
    with pytest.raises(ValidationError):
        _fact(applicability_notes=" ")
    with pytest.raises(ValidationError):
        _fact(reviewed_by=None)
    with pytest.raises(ValidationError):
        _fact(reviewed_at=None)
    with pytest.raises(ValidationError):
        _fact(reviewed_at=datetime(2026, 10, 27, 10, 0))
    with pytest.raises(ValidationError):
        _fact(reviewed_at=datetime(2026, 10, 27, 10, 0, tzinfo=timezone(timedelta(hours=2))))
    with pytest.raises(ValidationError):
        _candidate_fact(reviewed_by="synthetic-reviewer")
    with pytest.raises(ValidationError):
        _fact(extra_field="not-allowed")
    with pytest.raises(ValidationError):
        _manifest(sources=[_source(), _source()], facts=[])
    with pytest.raises(ValidationError):
        _manifest(facts=[_fact(), _fact()])
    with pytest.raises(ValidationError):
        _manifest(facts=[_fact(source_id="synthetic-missing-source")])
    with pytest.raises(ValidationError):
        _manifest(facts=[_fact(reviewed_at=datetime(2026, 10, 27, 8, 0, tzinfo=UTC))])


def test_effective_interval_validation_keeps_unknown_separate_from_retrieval() -> None:
    unknown = _fact(
        fact_id="synthetic-unknown-applicability",
        effective_from=None,
        effective_to=None,
    )
    source = _source()

    assert source.published_date is None
    assert source.retrieved_at_utc == RETRIEVED_AT
    assert unknown.effective_from is None
    assert unknown.effective_to is None
    assert unknown.has_known_applicability_start is False
    assert unknown.applies_on(date(2026, 6, 1)) is False
    with pytest.raises(ValidationError):
        _fact(effective_from=None, effective_to=date(2026, 12, 31))
    with pytest.raises(ValidationError):
        _fact(
            effective_from=date(2026, 12, 31),
            effective_to=date(2026, 1, 1),
        )


@pytest.mark.parametrize(
    ("parameter", "basis", "unit"),
    [
        (
            FactParameter.VESSEL_UNLOADING_MAX_RATE,
            QuantityBasis.ENERGY_GWH_PER_DAY,
            "GWh/d",
        ),
        (
            FactParameter.SENDOUT_CAPACITY,
            QuantityBasis.LIQUID_LNG_M3_PER_HOUR,
            "m3/h of LNG",
        ),
        (
            FactParameter.TANK_EVAPORATION_RATE,
            QuantityBasis.CARGO_ENERGY_PERCENT,
            "% of cargo energy",
        ),
        (
            FactParameter.RETAINED_FUEL_RATE,
            QuantityBasis.TANK_CAPACITY_PERCENT_PER_DAY,
            "% of tank capacity per day",
        ),
        (
            FactParameter.SENDOUT_CAPACITY,
            QuantityBasis.NORMAL_GAS_NM3_PER_HOUR,
            "MWh/h",
        ),
        (
            FactParameter.VESSEL_UNLOADING_MAX_RATE,
            QuantityBasis.LIQUID_LNG_M3_PER_HOUR,
            "Nm3/h",
        ),
        (
            FactParameter.SENDOUT_CAPACITY,
            QuantityBasis.ACTUAL_GAS_M3_PER_HOUR,
            "Nm3/h",
        ),
        (
            FactParameter.REGASIFICATION_CAPACITY,
            QuantityBasis.ENERGY_GWH_PER_DAY,
            "m3/h",
        ),
    ],
)
def test_parameter_basis_and_unit_mismatches_are_refused(
    parameter: FactParameter,
    basis: QuantityBasis,
    unit: str,
) -> None:
    with pytest.raises(ValidationError):
        _fact(parameter=parameter, quantity_basis=basis, original_unit=unit)


def test_distinct_measurement_bases_remain_distinct() -> None:
    liquid = _fact()
    actual = _fact(
        fact_id="synthetic-sendout-actual",
        parameter=FactParameter.SENDOUT_CAPACITY,
        value="140.000",
        original_value_text="140.000 actual m3/h",
        original_unit="actual m3/h",
        quantity_basis=QuantityBasis.ACTUAL_GAS_M3_PER_HOUR,
    )
    normal = _fact(
        fact_id="synthetic-sendout-normal",
        parameter=FactParameter.SENDOUT_CAPACITY,
        value="139.000",
        original_value_text="139.000 m3(n)/h",
        original_unit="m3(n)/h",
        quantity_basis=QuantityBasis.NORMAL_GAS_NM3_PER_HOUR,
    )
    energy = _fact(
        fact_id="synthetic-regas-energy",
        parameter=FactParameter.REGASIFICATION_CAPACITY,
        value="645",
        original_value_text="645 GWh/d",
        original_unit="GWh/d",
        quantity_basis=QuantityBasis.ENERGY_GWH_PER_DAY,
    )
    tank_percent = _fact(
        fact_id="synthetic-tank-percent",
        parameter=FactParameter.EVAPORATION_RATE,
        value="0.07",
        original_value_text="approximately 0.07% of tank capacity per day",
        original_unit="% of tank capacity per day",
        quantity_basis=QuantityBasis.TANK_CAPACITY_PERCENT_PER_DAY,
    )
    cargo_percent = _fact(
        fact_id="synthetic-cargo-percent",
        parameter=FactParameter.RETAINED_FUEL_RATE,
        value="0.07",
        original_value_text="synthetic 0.07% of cargo energy",
        original_unit="% of cargo energy",
        quantity_basis=QuantityBasis.CARGO_ENERGY_PERCENT,
    )
    duration = _fact(
        fact_id="synthetic-duration",
        parameter=FactParameter.VESSEL_DISCHARGE_DURATION,
        value="24",
        original_value_text="up to 24 hours",
        original_unit="hours",
        quantity_basis=QuantityBasis.DURATION_HOURS,
    )

    assert liquid.quantity_basis is QuantityBasis.LIQUID_LNG_M3_PER_HOUR
    assert actual.quantity_basis is QuantityBasis.ACTUAL_GAS_M3_PER_HOUR
    assert normal.quantity_basis is QuantityBasis.NORMAL_GAS_NM3_PER_HOUR
    assert energy.quantity_basis is QuantityBasis.ENERGY_GWH_PER_DAY
    assert tank_percent.quantity_basis is QuantityBasis.TANK_CAPACITY_PERCENT_PER_DAY
    assert cargo_percent.quantity_basis is QuantityBasis.CARGO_ENERGY_PERCENT
    assert duration.quantity_basis is QuantityBasis.DURATION_HOURS


def test_fee_requires_explicit_currency_per_energy_unit() -> None:
    fee = _fact(
        fact_id="synthetic-fee",
        parameter=FactParameter.TERMINAL_FEE,
        value="1.25",
        original_value_text="1.25 EUR/MWh",
        original_unit="EUR/MWh",
        quantity_basis=QuantityBasis.MONEY_PER_ENERGY,
    )
    assert fee.original_unit == "EUR/MWh"

    for unit in ("EUR", "eur/MWh", "EUR/GJ", "MWh"):
        with pytest.raises(ValidationError):
            _fact(
                fact_id=f"synthetic-fee-{unit}",
                parameter=FactParameter.TERMINAL_FEE,
                quantity_basis=QuantityBasis.MONEY_PER_ENERGY,
                original_unit=unit,
            )


def test_quotation_limit_is_per_source_across_manifest() -> None:
    quote_13_words = " ".join(f"word{index}" for index in range(13))

    with pytest.raises(ValidationError):
        _fact(quotation=" ".join(f"word{index}" for index in range(26)))
    with pytest.raises(ValidationError):
        _manifest(
            facts=[
                _fact(fact_id="synthetic-quote-one", quotation=quote_13_words),
                _fact(fact_id="synthetic-quote-two", quotation=quote_13_words),
            ]
        )


def test_candidate_is_inspectable_but_excluded_from_reviewed_lookup() -> None:
    candidate = _candidate_fact()
    manifest = _manifest(sources=[_source()], facts=[candidate])

    lookup = lookup_reviewed_lng_terminal_fact(
        manifest,
        terminal_id=candidate.terminal_id,
        parameter=candidate.parameter,
        quantity_basis=candidate.quantity_basis,
        scenario_date=date(2026, 6, 1),
    )
    inspected = inspect_candidate_lng_terminal_facts(manifest)

    assert lookup.status is LngFactLookupStatus.NO_REVIEWED_FACT
    assert lookup.selected_fact is None
    assert lookup.reviewed_facts == ()
    assert "CANDIDATE_FACTS_EXCLUDED_FROM_REVIEWED_SELECTION" in lookup.warnings
    assert inspected == (candidate,)
    assert inspected[0].review_status is FactReviewStatus.CANDIDATE


def test_reviewed_lookup_requires_exact_basis_and_distinguishes_unknown_interval() -> None:
    unknown = _fact(
        fact_id="synthetic-unknown-applicability",
        effective_from=None,
        effective_to=None,
    )
    manifest = _manifest(sources=[_source()], facts=[unknown])

    result = lookup_reviewed_lng_terminal_fact(
        manifest,
        terminal_id=unknown.terminal_id,
        parameter=unknown.parameter,
        quantity_basis=unknown.quantity_basis,
        scenario_date=date(2026, 6, 1),
    )
    wrong_basis = lookup_reviewed_lng_terminal_fact(
        manifest,
        terminal_id=unknown.terminal_id,
        parameter=unknown.parameter,
        quantity_basis=QuantityBasis.NORMAL_GAS_NM3_PER_HOUR,
        scenario_date=date(2026, 6, 1),
    )

    assert result.status is LngFactLookupStatus.APPLICABILITY_UNKNOWN
    assert result.selected_fact is None
    assert result.unknown_applicability_fact_ids == (unknown.fact_id,)
    assert "EFFECTIVE_APPLICABILITY_INTERVAL_UNKNOWN" in result.warnings
    assert wrong_basis.status is LngFactLookupStatus.NO_REVIEWED_FACT


def test_reviewed_lookup_finds_one_known_applicable_fact_and_expiry_is_explicit() -> None:
    fact = _fact(effective_to=date(2026, 12, 31))
    manifest = _manifest(sources=[_source()], facts=[fact])

    found = lookup_reviewed_lng_terminal_fact(
        manifest,
        terminal_id=fact.terminal_id,
        parameter=fact.parameter,
        quantity_basis=fact.quantity_basis,
        scenario_date=date(2026, 6, 1),
    )
    expired = lookup_reviewed_lng_terminal_fact(
        manifest,
        terminal_id=fact.terminal_id,
        parameter=fact.parameter,
        quantity_basis=fact.quantity_basis,
        scenario_date=date(2027, 1, 1),
    )

    assert found.status is LngFactLookupStatus.REVIEWED_FACT_FOUND
    assert found.selected_fact == fact
    assert expired.status is LngFactLookupStatus.NO_APPLICABLE_REVIEWED_FACT
    assert expired.selected_fact is None
    assert "REVIEWED_FACTS_NOT_APPLICABLE_ON_SCENARIO_DATE" in expired.warnings


def test_unknown_interval_blocks_selection_when_another_fact_is_applicable() -> None:
    known = _fact(fact_id="synthetic-known")
    unknown = _fact(
        fact_id="synthetic-unknown",
        effective_from=None,
        effective_to=None,
    )
    manifest = _manifest(sources=[_source()], facts=[known, unknown])

    result = lookup_reviewed_lng_terminal_fact(
        manifest,
        terminal_id=known.terminal_id,
        parameter=known.parameter,
        quantity_basis=known.quantity_basis,
        scenario_date=date(2026, 6, 1),
    )

    assert result.status is LngFactLookupStatus.APPLICABILITY_UNKNOWN
    assert result.selected_fact is None
    assert result.applicable_fact_ids == (known.fact_id,)
    assert result.unknown_applicability_fact_ids == (unknown.fact_id,)


def test_ambiguous_reviewed_same_basis_facts_are_not_averaged_or_replaced() -> None:
    equipment = _fact(
        fact_id="synthetic-regas-645",
        parameter=FactParameter.REGASIFICATION_CAPACITY,
        value="645",
        original_value_text="645 GWh/d",
        original_unit="GWh/d",
        quantity_basis=QuantityBasis.ENERGY_GWH_PER_DAY,
        quotation="Synthetic equipment capacity quotation",
    )
    primary = _fact(
        fact_id="synthetic-regas-654",
        parameter=FactParameter.REGASIFICATION_CAPACITY,
        value="654",
        original_value_text="circa 654 GWh/d",
        original_unit="GWh/d",
        quantity_basis=QuantityBasis.ENERGY_GWH_PER_DAY,
        quotation="Synthetic primary capacity quotation",
    )
    manifest = _manifest(sources=[_source()], facts=[equipment, primary])

    result = lookup_reviewed_lng_terminal_fact(
        manifest,
        terminal_id=equipment.terminal_id,
        parameter=equipment.parameter,
        quantity_basis=equipment.quantity_basis,
        scenario_date=date(2026, 6, 1),
    )

    assert result.status is LngFactLookupStatus.AMBIGUOUS_REVIEWED_FACTS
    assert result.selected_fact is None
    assert result.applicable_fact_ids == (equipment.fact_id, primary.fact_id)
    assert {fact.value for fact in result.reviewed_facts} == {"645", "654"}
    assert "MULTIPLE_REVIEWED_FACTS_ARE_APPLICABLE" in result.warnings


def test_source_comparison_unchanged_is_not_a_review_or_mutation() -> None:
    manifest = _manifest()
    before = dump_lng_terminal_reference_manifest(manifest)

    result = compare_lng_terminal_source_bytes(
        manifest,
        source_id="synthetic-source-a",
        candidate_bytes=CAPTURE_BYTES,
        retrieved_at_utc=datetime(2026, 10, 28, 12, 0, tzinfo=UTC),
    )

    assert result.status is SourceChangeStatus.UNCHANGED
    assert result.before_sha256 == result.after_sha256 == CAPTURE_SHA256
    assert result.auto_replace is False
    assert result.semantic_change_established is False
    assert result.affected_fact_ids == ("synthetic-gate-unloading-max",)
    assert "UNCHANGED_BYTES_DO_NOT_CONFIRM_CURRENT_APPLICABILITY" in result.warnings
    assert dump_lng_terminal_reference_manifest(manifest) == before


def test_source_comparison_byte_change_requires_review_and_never_replaces() -> None:
    manifest = _manifest()
    before = dump_lng_terminal_reference_manifest(manifest)
    changed_bytes = b"synthetic changed page bytes\n"

    result = compare_lng_terminal_source_bytes(
        manifest,
        source_id="synthetic-source-a",
        candidate_bytes=changed_bytes,
        retrieved_at_utc=datetime(2026, 10, 28, 12, 0, tzinfo=UTC),
    )

    assert result.status is SourceChangeStatus.REVIEW_REQUIRED
    assert result.before_sha256 == CAPTURE_SHA256
    assert result.after_sha256 == sha256(changed_bytes).hexdigest()
    assert result.before_sha256 != result.after_sha256
    assert result.auto_replace is False
    assert result.semantic_change_established is False
    assert "BYTE_CHANGE_REQUIRES_REVIEW_NOT_AUTOMATIC_REPLACEMENT" in result.warnings
    assert manifest.sources[0].captured_sha256 == CAPTURE_SHA256
    assert manifest.facts[0].review_status is FactReviewStatus.REVIEWED
    assert dump_lng_terminal_reference_manifest(manifest) == before


def test_source_comparison_refuses_unknown_empty_oversized_naive_and_bad_limit() -> None:
    manifest = _manifest()
    retrieved = datetime(2026, 10, 28, 12, 0, tzinfo=UTC)

    with pytest.raises(LngTerminalReferenceError) as unknown:
        compare_lng_terminal_source_bytes(
            manifest,
            source_id="synthetic-unknown-source",
            candidate_bytes=b"x",
            retrieved_at_utc=retrieved,
        )
    assert unknown.value.code == LngReferenceErrorCode.UNKNOWN_SOURCE.value

    with pytest.raises(LngTerminalReferenceError) as empty:
        compare_lng_terminal_source_bytes(
            manifest,
            source_id="synthetic-source-a",
            candidate_bytes=b"",
            retrieved_at_utc=retrieved,
        )
    assert empty.value.code == LngReferenceErrorCode.CANDIDATE_EMPTY.value

    with pytest.raises(LngTerminalReferenceError) as oversized:
        compare_lng_terminal_source_bytes(
            manifest,
            source_id="synthetic-source-a",
            candidate_bytes=b"12345",
            retrieved_at_utc=retrieved,
            max_bytes=4,
        )
    assert oversized.value.code == LngReferenceErrorCode.CANDIDATE_TOO_LARGE.value

    with pytest.raises(LngTerminalReferenceError) as naive:
        compare_lng_terminal_source_bytes(
            manifest,
            source_id="synthetic-source-a",
            candidate_bytes=b"x",
            retrieved_at_utc=datetime(2026, 10, 28, 12, 0),
        )
    assert naive.value.code == LngReferenceErrorCode.INVALID_RETRIEVED_AT.value

    with pytest.raises(LngTerminalReferenceError) as bad_limit:
        compare_lng_terminal_source_bytes(
            manifest,
            source_id="synthetic-source-a",
            candidate_bytes=b"x",
            retrieved_at_utc=retrieved,
            max_bytes=0,
        )
    assert bad_limit.value.code == LngReferenceErrorCode.INVALID_SIZE_LIMIT.value


def test_local_candidate_read_is_bounded(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate.bin"
    candidate.write_bytes(b"12345")

    with pytest.raises(LngTerminalReferenceError) as too_large:
        read_lng_terminal_candidate_file(candidate, max_bytes=4)
    assert too_large.value.code == LngReferenceErrorCode.CANDIDATE_TOO_LARGE.value

    with pytest.raises(LngTerminalReferenceError) as missing:
        read_lng_terminal_candidate_file(tmp_path / "missing.bin")
    assert missing.value.code == LngReferenceErrorCode.CANDIDATE_NOT_FOUND.value


def test_loader_roundtrip_from_disk_and_strict_refusals(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _manifest()
    path = tmp_path / "manifest.json"
    path.write_text(dump_lng_terminal_reference_manifest(manifest), encoding="utf-8")
    assert load_lng_terminal_reference_manifest(path) == manifest

    with pytest.raises(LngTerminalReferenceError) as missing:
        load_lng_terminal_reference_manifest(tmp_path / "missing.json")
    assert missing.value.code == LngReferenceErrorCode.MANIFEST_NOT_FOUND.value

    with pytest.raises(LngTerminalReferenceError) as bom:
        loads_lng_terminal_reference_manifest(b"\xef\xbb\xbf{}")
    assert bom.value.code == LngReferenceErrorCode.MANIFEST_BOM_NOT_ALLOWED.value

    with pytest.raises(LngTerminalReferenceError) as utf8:
        loads_lng_terminal_reference_manifest(b"\xff")
    assert utf8.value.code == LngReferenceErrorCode.MANIFEST_UTF8_INVALID.value

    with pytest.raises(LngTerminalReferenceError) as malformed:
        loads_lng_terminal_reference_manifest(b"{")
    assert malformed.value.code == LngReferenceErrorCode.MANIFEST_JSON_INVALID.value

    with pytest.raises(LngTerminalReferenceError) as root:
        loads_lng_terminal_reference_manifest("[]")
    assert root.value.code == LngReferenceErrorCode.MANIFEST_SCHEMA_INVALID.value

    document = json.loads(dump_lng_terminal_reference_manifest(manifest))
    document["extra"] = "not allowed"
    with pytest.raises(LngTerminalReferenceError) as extra:
        loads_lng_terminal_reference_manifest(json.dumps(document))
    assert extra.value.code == LngReferenceErrorCode.MANIFEST_SCHEMA_INVALID.value

    monkeypatch.setattr(reference, "MAX_REFERENCE_BYTES", 10)
    with pytest.raises(LngTerminalReferenceError) as oversized:
        loads_lng_terminal_reference_manifest(dump_lng_terminal_reference_manifest(manifest))
    assert oversized.value.code == LngReferenceErrorCode.MANIFEST_TOO_LARGE.value


def test_explicit_utc_retrieval_parser_refuses_naive_and_offsets() -> None:
    parsed = parse_retrieved_at_utc("2026-10-27T12:00:00Z")
    assert parsed == datetime(2026, 10, 27, 12, 0, tzinfo=UTC)
    assert parsed.tzinfo is not None

    for value in ("2026-10-27T12:00:00", "2026-10-27T12:00:00+02:00", "not-a-time"):
        with pytest.raises(LngTerminalReferenceError) as invalid:
            parse_retrieved_at_utc(value)
        assert invalid.value.code == LngReferenceErrorCode.INVALID_RETRIEVED_AT.value


def test_cli_unchanged_and_changed_exit_codes(tmp_path: Path) -> None:
    old_bytes = CAPTURE_BYTES
    changed_bytes = b"synthetic changed page bytes\n"
    old_path = tmp_path / "old.bin"
    changed_path = tmp_path / "changed.bin"
    manifest_path = tmp_path / "manifest.json"
    old_path.write_bytes(old_bytes)
    changed_path.write_bytes(changed_bytes)
    source = _source(captured_sha256=sha256(old_bytes).hexdigest())
    manifest = _manifest(sources=[source], facts=[_fact()])
    manifest_text = dump_lng_terminal_reference_manifest(manifest)
    manifest_path.write_text(manifest_text, encoding="utf-8")
    base_args = [
        "--manifest",
        str(manifest_path),
        "--source-id",
        source.source_id,
        "--retrieved-at",
        "2026-10-27T12:00:00Z",
    ]

    unchanged = _run_cli([*base_args, "--candidate-file", str(old_path)])
    changed = _run_cli([*base_args, "--candidate-file", str(changed_path)])

    assert unchanged.returncode == 0
    assert "Traceback" not in unchanged.stderr
    unchanged_payload = json.loads(unchanged.stdout)
    assert unchanged_payload["status"] == "UNCHANGED"
    assert unchanged_payload["auto_replace"] is False

    assert changed.returncode == 2
    assert "Traceback" not in changed.stderr
    changed_payload = json.loads(changed.stdout)
    assert changed_payload["status"] == "REVIEW_REQUIRED"
    assert changed_payload["auto_replace"] is False
    assert changed_payload["semantic_change_established"] is False
    assert changed_payload["affected_fact_ids"] == ["synthetic-gate-unloading-max"]
    assert manifest_path.read_text(encoding="utf-8") == manifest_text


def test_cli_refusals_are_safe_json_and_exit_one(tmp_path: Path) -> None:
    manifest = _manifest()
    manifest_path = tmp_path / "manifest.json"
    candidate_path = tmp_path / "candidate.bin"
    bad_manifest_path = tmp_path / "bad.json"
    empty_path = tmp_path / "empty.bin"
    huge_path = tmp_path / "huge.bin"
    manifest_path.write_text(
        dump_lng_terminal_reference_manifest(manifest),
        encoding="utf-8",
    )
    candidate_path.write_bytes(CAPTURE_BYTES)
    bad_manifest_path.write_text("{", encoding="utf-8")
    empty_path.write_bytes(b"")
    huge_path.write_bytes(b"x" * (MAX_CANDIDATE_BYTES + 1))
    def run(
        manifest_arg: Path,
        candidate_arg: Path,
        *,
        source_id: str = "synthetic-source-a",
        retrieved_at: str = "2026-10-27T12:00:00Z",
    ) -> tuple[int, dict]:
        completed = _run_cli(
            [
                "--manifest",
                str(manifest_arg),
                "--source-id",
                source_id,
                "--candidate-file",
                str(candidate_arg),
                "--retrieved-at",
                retrieved_at,
            ]
        )
        assert "Traceback" not in completed.stderr
        return completed.returncode, json.loads(completed.stdout)

    malformed_code, malformed_payload = run(bad_manifest_path, candidate_path)
    naive_code, naive_payload = run(
        manifest_path,
        candidate_path,
        retrieved_at="2026-10-27T12:00:00",
    )
    empty_code, empty_payload = run(manifest_path, empty_path)
    huge_code, huge_payload = run(manifest_path, huge_path)
    unknown_code, unknown_payload = run(
        manifest_path,
        candidate_path,
        source_id="synthetic-unknown-source",
    )

    assert malformed_code == 1
    assert malformed_payload["error_code"] == LngReferenceErrorCode.MANIFEST_JSON_INVALID.value
    assert naive_code == 1
    assert naive_payload["error_code"] == LngReferenceErrorCode.INVALID_RETRIEVED_AT.value
    assert empty_code == 1
    assert empty_payload["error_code"] == LngReferenceErrorCode.CANDIDATE_EMPTY.value
    assert huge_code == 1
    assert huge_payload["error_code"] == LngReferenceErrorCode.CANDIDATE_TOO_LARGE.value
    assert unknown_code == 1
    assert unknown_payload["error_code"] == LngReferenceErrorCode.UNKNOWN_SOURCE.value
    for payload in (
        malformed_payload,
        naive_payload,
        empty_payload,
        huge_payload,
        unknown_payload,
    ):
        assert payload["status"] == "ERROR"
        assert payload["auto_replace"] is False


def test_cli_missing_argument_is_a_json_error(tmp_path: Path) -> None:
    completed = _run_cli(["--manifest", str(tmp_path / "manifest.json")])

    assert completed.returncode == 1
    assert "Traceback" not in completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["error_code"] == LngReferenceErrorCode.CLI_ARGUMENT_INVALID.value
