"""Ownership and parity gate for the reviewed LNG domain vocabulary.

The 2026-10-27 architecture review split the LNG vocabulary into two reviewed
ownership classes:

- gas/energy semantics (``LngEnergyStageKind``, ``LngDownstreamChargeBasis``,
  terminal ``QuantityBasis`` and terminal ``FactParameter``) have one canonical
  definition in ``eurogas_nexus.domain.ontology.vocabulary`` and are re-exported
  by their original modules so existing import paths keep working;
- reference-contract control codes (``FactReviewStatus``,
  ``LngFactLookupStatus``, ``LngReferenceErrorCode`` and ``SourceChangeStatus``)
  deliberately remain owned by the terminal-reference contract and are
  review-listed in ``test_domain_enum_ontology_gate.py``.

Reviewed decision: ``docs/architecture/LNG_VOCABULARY_OWNERSHIP.md``. These
tests are identity/member/value parity plus focused domain/reference
regressions; a blanket ontology-gate exemption is not accepted.
"""

from __future__ import annotations

import ast
import json
from datetime import UTC, date, datetime
from decimal import Decimal
from hashlib import sha256
from pathlib import Path

import pytest

from eurogas_nexus.domain.ontology import vocabulary
from eurogas_nexus.domain.research import lng_cargo_economics, lng_energy_balance
from eurogas_nexus.domain.route_cost import lng_terminal_reference

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "src"
VOCABULARY_PATH = SOURCE / "eurogas_nexus" / "domain" / "ontology" / "vocabulary.py"

_SEMANTIC_ENUMS = (
    (
        vocabulary.LngEnergyStageKind,
        lng_energy_balance.LngEnergyStageKind,
        (
            ("CARGO_TRANSFER", "cargo_transfer"),
            ("SHIPPING", "shipping"),
            ("STORAGE", "storage"),
            ("REGASIFICATION", "regasification"),
            ("OTHER", "other"),
        ),
    ),
    (
        vocabulary.LngDownstreamChargeBasis,
        lng_cargo_economics.LngDownstreamChargeBasis,
        (
            ("INVOICED_CASH", "invoiced_cash"),
            ("IN_KIND", "in_kind"),
            ("UNKNOWN", "unknown"),
        ),
    ),
    (
        vocabulary.QuantityBasis,
        lng_terminal_reference.QuantityBasis,
        (
            ("LIQUID_LNG_M3_PER_HOUR", "LIQUID_LNG_M3_PER_HOUR"),
            ("ACTUAL_GAS_M3_PER_HOUR", "ACTUAL_GAS_M3_PER_HOUR"),
            ("NORMAL_GAS_NM3_PER_HOUR", "NORMAL_GAS_NM3_PER_HOUR"),
            ("ENERGY_MWH_PER_HOUR", "ENERGY_MWH_PER_HOUR"),
            ("ENERGY_GWH_PER_DAY", "ENERGY_GWH_PER_DAY"),
            ("DURATION_HOURS", "DURATION_HOURS"),
            (
                "TANK_CAPACITY_PERCENT_PER_DAY",
                "TANK_CAPACITY_PERCENT_PER_DAY",
            ),
            ("CARGO_ENERGY_PERCENT", "CARGO_ENERGY_PERCENT"),
            ("MONEY_PER_ENERGY", "MONEY_PER_ENERGY"),
        ),
    ),
    (
        vocabulary.FactParameter,
        lng_terminal_reference.FactParameter,
        (
            ("VESSEL_UNLOADING_MAX_RATE", "VESSEL_UNLOADING_MAX_RATE"),
            ("VESSEL_UNLOADING_RATE", "VESSEL_UNLOADING_RATE"),
            ("UNLOADING_RATE", "UNLOADING_RATE"),
            ("SENDOUT_CAPACITY", "SENDOUT_CAPACITY"),
            ("MINIMUM_SENDOUT_RATE", "MINIMUM_SENDOUT_RATE"),
            ("REGASIFICATION_CAPACITY", "REGASIFICATION_CAPACITY"),
            ("TANK_EVAPORATION_RATE", "TANK_EVAPORATION_RATE"),
            ("EVAPORATION_RATE", "EVAPORATION_RATE"),
            ("CARGO_ENERGY_LOSS_RATE", "CARGO_ENERGY_LOSS_RATE"),
            ("RETAINED_FUEL_RATE", "RETAINED_FUEL_RATE"),
            ("VESSEL_DISCHARGE_DURATION", "VESSEL_DISCHARGE_DURATION"),
            ("TERMINAL_FEE", "TERMINAL_FEE"),
        ),
    ),
)

_CONTROL_ENUMS = (
    (
        lng_terminal_reference.FactReviewStatus,
        (
            ("CANDIDATE", "CANDIDATE"),
            ("REVIEWED", "REVIEWED"),
        ),
    ),
    (
        lng_terminal_reference.LngFactLookupStatus,
        (
            ("REVIEWED_FACT_FOUND", "REVIEWED_FACT_FOUND"),
            ("NO_REVIEWED_FACT", "NO_REVIEWED_FACT"),
            (
                "NO_APPLICABLE_REVIEWED_FACT",
                "NO_APPLICABLE_REVIEWED_FACT",
            ),
            ("APPLICABILITY_UNKNOWN", "APPLICABILITY_UNKNOWN"),
            (
                "AMBIGUOUS_REVIEWED_FACTS",
                "AMBIGUOUS_REVIEWED_FACTS",
            ),
        ),
    ),
    (
        lng_terminal_reference.LngReferenceErrorCode,
        (
            ("MANIFEST_PATH_INVALID", "MANIFEST_PATH_INVALID"),
            ("MANIFEST_NOT_FOUND", "MANIFEST_NOT_FOUND"),
            ("MANIFEST_NOT_A_FILE", "MANIFEST_NOT_A_FILE"),
            ("MANIFEST_TOO_LARGE", "MANIFEST_TOO_LARGE"),
            ("MANIFEST_UTF8_INVALID", "MANIFEST_UTF8_INVALID"),
            ("MANIFEST_BOM_NOT_ALLOWED", "MANIFEST_BOM_NOT_ALLOWED"),
            ("MANIFEST_JSON_INVALID", "MANIFEST_JSON_INVALID"),
            ("MANIFEST_SCHEMA_INVALID", "MANIFEST_SCHEMA_INVALID"),
            ("CANDIDATE_PATH_INVALID", "CANDIDATE_PATH_INVALID"),
            ("CANDIDATE_NOT_FOUND", "CANDIDATE_NOT_FOUND"),
            ("CANDIDATE_NOT_A_FILE", "CANDIDATE_NOT_A_FILE"),
            ("CANDIDATE_TOO_LARGE", "CANDIDATE_TOO_LARGE"),
            ("CANDIDATE_EMPTY", "CANDIDATE_EMPTY"),
            ("CANDIDATE_PAYLOAD_INVALID", "CANDIDATE_PAYLOAD_INVALID"),
            ("UNKNOWN_SOURCE", "UNKNOWN_SOURCE"),
            ("INVALID_SOURCE_ID", "INVALID_SOURCE_ID"),
            ("INVALID_RETRIEVED_AT", "INVALID_RETRIEVED_AT"),
            ("INVALID_SCENARIO_DATE", "INVALID_SCENARIO_DATE"),
            ("INVALID_PARAMETER", "INVALID_PARAMETER"),
            ("INVALID_QUANTITY_BASIS", "INVALID_QUANTITY_BASIS"),
            ("INVALID_TERMINAL_ID", "INVALID_TERMINAL_ID"),
            ("INVALID_SIZE_LIMIT", "INVALID_SIZE_LIMIT"),
            ("CLI_ARGUMENT_INVALID", "CLI_ARGUMENT_INVALID"),
            ("INTERNAL_ERROR", "INTERNAL_ERROR"),
        ),
    ),
    (
        lng_terminal_reference.SourceChangeStatus,
        (
            ("UNCHANGED", "UNCHANGED"),
            ("REVIEW_REQUIRED", "REVIEW_REQUIRED"),
        ),
    ),
)

_ORIGIN_MODULES = (
    (
        "eurogas_nexus.domain.research.lng_energy_balance",
        vocabulary.LngEnergyStageKind.__name__,
    ),
    (
        "eurogas_nexus.domain.research.lng_cargo_economics",
        vocabulary.LngDownstreamChargeBasis.__name__,
    ),
    (
        "eurogas_nexus.domain.route_cost.lng_terminal_reference",
        vocabulary.QuantityBasis.__name__,
    ),
    (
        "eurogas_nexus.domain.route_cost.lng_terminal_reference",
        vocabulary.FactParameter.__name__,
    ),
)


@pytest.mark.parametrize(
    ("canonical", "reexported"),
    [(canonical, reexported) for canonical, reexported, _ in _SEMANTIC_ENUMS],
)
def test_semantic_enum_reexports_are_the_canonical_objects(
    canonical: type, reexported: type
) -> None:
    assert reexported is canonical
    assert canonical.__module__ == vocabulary.__name__
    assert reexported.__module__ == vocabulary.__name__


@pytest.mark.parametrize(
    ("canonical", "reexported", "expected"),
    _SEMANTIC_ENUMS,
)
def test_semantic_member_names_values_and_identity_are_preserved(
    canonical: type,
    reexported: type,
    expected: tuple[tuple[str, str], ...],
) -> None:
    assert [
        (name, member.value) for name, member in canonical.__members__.items()
    ] == list(expected)
    assert [
        (name, member.value) for name, member in reexported.__members__.items()
    ] == list(expected)
    for name, value in expected:
        member = canonical[name]
        assert reexported[name] is member
        assert member.value == value
        assert str(member) == value


@pytest.mark.parametrize(
    ("control", "expected"),
    _CONTROL_ENUMS,
)
def test_reference_contract_control_enums_stay_with_their_contract(
    control: type,
    expected: tuple[tuple[str, str], ...],
) -> None:
    assert control.__module__ == lng_terminal_reference.__name__
    assert not hasattr(vocabulary, control.__name__)
    assert [
        (name, member.value) for name, member in control.__members__.items()
    ] == list(expected)


@pytest.mark.parametrize(("module_name", "enum_name"), _ORIGIN_MODULES)
def test_origin_modules_reexport_without_redefining_semantic_enums(
    module_name: str, enum_name: str
) -> None:
    module_path = SOURCE / Path(*module_name.split(".")).with_suffix(".py")
    tree = ast.parse(
        module_path.read_text(encoding="utf-8"),
        filename=str(module_path),
    )
    defined_classes = [
        node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)
    ]
    assert enum_name not in defined_classes


def test_vocabulary_defines_each_semantic_enum_exactly_once() -> None:
    tree = ast.parse(
        VOCABULARY_PATH.read_text(encoding="utf-8"),
        filename=str(VOCABULARY_PATH),
    )
    defined_classes = [
        node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)
    ]
    for canonical, _, _ in _SEMANTIC_ENUMS:
        assert defined_classes.count(canonical.__name__) == 1


def test_energy_balance_keeps_consumed_energy_and_physical_loss_separate() -> None:
    stages = (
        lng_energy_balance.LngEnergyStage(
            stage_id="shipping",
            kind=lng_energy_balance.LngEnergyStageKind.SHIPPING,
            input_energy_mwh=Decimal("1000"),
            output_energy_mwh=Decimal("990"),
            consumed_energy_mwh=Decimal("6"),
            physical_loss_energy_mwh=Decimal("4"),
            source_references=("synthetic:energy:shipping",),
        ),
        lng_energy_balance.LngEnergyStage(
            stage_id="regasification",
            kind=lng_energy_balance.LngEnergyStageKind.REGASIFICATION,
            input_energy_mwh=Decimal("990"),
            output_energy_mwh=Decimal("985"),
            consumed_energy_mwh=Decimal("3"),
            physical_loss_energy_mwh=Decimal("2"),
            source_references=("synthetic:energy:regasification",),
        ),
    )

    result = lng_energy_balance.compute_lng_energy_balance(
        lng_energy_balance.LngEnergyBalanceInput(
            purchased_energy_mwh=Decimal("1000"),
            delivered_energy_mwh=Decimal("985"),
            energy_basis_reference="synthetic:energy-basis",
            energy_unit="MWh",
            stages=stages,
        )
    )

    assert result.model_version == "lng-energy-balance/v1"
    assert result.energy_unit == "MWh"
    assert result.total_consumed_energy_mwh == Decimal("9")
    assert result.physical_loss_energy_mwh == Decimal("6")
    assert result.total_reduction_energy_mwh == Decimal("15")
    assert result.total_consumed_energy_mwh != result.physical_loss_energy_mwh
    assert (
        "CONSUMED_ENERGY_AND_PHYSICAL_LOSS_DISCLOSED_SEPARATELY_NOT_MONETIZED"
        in result.warnings
    )


def _terminal_manifest_payload(
    *,
    captured_sha256: str = "0" * 64,
) -> dict[str, object]:
    return {
        "schema_version": "eurogas.lng-terminal-reference/1",
        "model_version": "lng-terminal-reference-model/1",
        "notes": "Synthetic ownership-parity fixture; CANDIDATE fact only.",
        "sources": [
            {
                "source_id": "SRC-1",
                "official_url": "https://example.invalid/terminal-reference",
                "operator": "Synthetic Operator",
                "document_title": "Synthetic terminal reference",
                "publication_version": "2026-10-27",
                "captured_sha256": captured_sha256,
                "retrieved_at_utc": "2026-10-27T00:00:00Z",
                "applicability_notes": "Synthetic contract fixture only.",
            }
        ],
        "facts": [
            {
                "fact_id": "FACT-1",
                "terminal_id": "TERM-1",
                "parameter": "SENDOUT_CAPACITY",
                "value": "645",
                "original_value_text": "645",
                "original_unit": "GWh/d",
                "quantity_basis": "ENERGY_GWH_PER_DAY",
                "quotation": "Synthetic quoted terminal sendout capacity.",
                "source_id": "SRC-1",
                "applicability_notes": "Synthetic candidate fact.",
                "review_status": "CANDIDATE",
            }
        ],
    }


def _load_terminal_manifest(
    *,
    captured_sha256: str = "0" * 64,
) -> lng_terminal_reference.LngTerminalReferenceManifest:
    payload = json.dumps(_terminal_manifest_payload(captured_sha256=captured_sha256))
    return lng_terminal_reference.loads_lng_terminal_reference_manifest(
        payload.encode("utf-8")
    )


def test_terminal_reference_uses_canonical_semantic_enums() -> None:
    manifest = _load_terminal_manifest()
    fact = manifest.facts[0]

    assert fact.parameter is vocabulary.FactParameter.SENDOUT_CAPACITY
    assert fact.quantity_basis is vocabulary.QuantityBasis.ENERGY_GWH_PER_DAY
    assert isinstance(fact.parameter, vocabulary.FactParameter)
    assert isinstance(fact.quantity_basis, vocabulary.QuantityBasis)

    lookup = lng_terminal_reference.lookup_reviewed_lng_terminal_fact(
        manifest,
        terminal_id="TERM-1",
        parameter="SENDOUT_CAPACITY",
        quantity_basis="ENERGY_GWH_PER_DAY",
        scenario_date=date(2026, 10, 27),
    )
    assert lookup.status is lng_terminal_reference.LngFactLookupStatus.NO_REVIEWED_FACT
    assert lookup.selected_fact is None
    assert "CANDIDATE_FACTS_EXCLUDED_FROM_REVIEWED_SELECTION" in lookup.warnings


def test_terminal_parameter_basis_compatibility_is_unchanged() -> None:
    compatibility = lng_terminal_reference.PARAMETER_BASIS_COMPATIBILITY

    assert set(compatibility) == set(vocabulary.FactParameter)
    for allowed_bases in compatibility.values():
        assert allowed_bases <= set(vocabulary.QuantityBasis)

    assert compatibility[vocabulary.FactParameter.SENDOUT_CAPACITY] == frozenset(
        {
            vocabulary.QuantityBasis.ACTUAL_GAS_M3_PER_HOUR,
            vocabulary.QuantityBasis.NORMAL_GAS_NM3_PER_HOUR,
            vocabulary.QuantityBasis.ENERGY_MWH_PER_HOUR,
            vocabulary.QuantityBasis.ENERGY_GWH_PER_DAY,
        }
    )
    assert compatibility[vocabulary.FactParameter.VESSEL_UNLOADING_MAX_RATE] == frozenset(
        {vocabulary.QuantityBasis.LIQUID_LNG_M3_PER_HOUR}
    )
    assert compatibility[vocabulary.FactParameter.REGASIFICATION_CAPACITY] == frozenset(
        {
            vocabulary.QuantityBasis.ENERGY_MWH_PER_HOUR,
            vocabulary.QuantityBasis.ENERGY_GWH_PER_DAY,
        }
    )


def test_terminal_measurement_bases_do_not_cross_match() -> None:
    assert lng_terminal_reference._unit_matches_basis(
        "m3/h lng", vocabulary.QuantityBasis.LIQUID_LNG_M3_PER_HOUR
    )
    assert not lng_terminal_reference._unit_matches_basis(
        "m3/h lng", vocabulary.QuantityBasis.ACTUAL_GAS_M3_PER_HOUR
    )
    assert lng_terminal_reference._unit_matches_basis(
        "Nm3/h", vocabulary.QuantityBasis.NORMAL_GAS_NM3_PER_HOUR
    )
    assert not lng_terminal_reference._unit_matches_basis(
        "Nm3/h", vocabulary.QuantityBasis.ACTUAL_GAS_M3_PER_HOUR
    )


def test_terminal_reference_control_codes_keep_their_contract_behaviour() -> None:
    source_bytes = b"synthetic-reference-bytes"
    manifest = _load_terminal_manifest(captured_sha256=sha256(source_bytes).hexdigest())
    retrieved_at = datetime(2026, 10, 27, 12, 0, tzinfo=UTC)

    unchanged = lng_terminal_reference.compare_lng_terminal_source_bytes(
        manifest,
        source_id="SRC-1",
        candidate_bytes=source_bytes,
        retrieved_at_utc=retrieved_at,
    )
    assert unchanged.status is lng_terminal_reference.SourceChangeStatus.UNCHANGED
    assert unchanged.auto_replace is False

    changed = lng_terminal_reference.compare_lng_terminal_source_bytes(
        manifest,
        source_id="SRC-1",
        candidate_bytes=b"changed-reference-bytes",
        retrieved_at_utc=retrieved_at,
    )
    assert changed.status is lng_terminal_reference.SourceChangeStatus.REVIEW_REQUIRED
    assert changed.auto_replace is False
    assert changed.semantic_change_established is False

    with pytest.raises(lng_terminal_reference.LngTerminalReferenceError) as exc_info:
        lng_terminal_reference.loads_lng_terminal_reference_manifest(b"{")
    assert (
        exc_info.value.code
        == lng_terminal_reference.LngReferenceErrorCode.MANIFEST_JSON_INVALID.value
    )


def _economics_only_input(
    *,
    charge_basis: lng_cargo_economics.LngDownstreamChargeBasis,
) -> lng_cargo_economics.LngEconomicsOnlyInput:
    valuation_date = date(2026, 10, 27)
    return lng_cargo_economics.LngEconomicsOnlyInput(
        contract_id="CONTRACT-1",
        cargo_id="CARGO-1",
        terminal_id="TERM-1",
        resource_id="RESOURCE-1",
        valuation_date=valuation_date,
        reporting_currency="EUR",
        energy_basis_reference="synthetic:energy-basis",
        energy_unit="MWh",
        purchased_energy_mwh=Decimal("1000"),
        delivered_energy_mwh=Decimal("1000"),
        purchase_unit_price_eur_per_mwh=Decimal("20"),
        sale_unit_price_eur_per_mwh=Decimal("25"),
        purchase_price_source_reference="synthetic:purchase-price",
        sale_price_source_reference="synthetic:sale-price",
        purchase_basis="FOB",
        purchase_included_cost_items=(),
        cost_scope_statement="Synthetic ownership-parity scope.",
        purchase_payment_date=valuation_date,
        sale_payment_date=valuation_date,
        downstream_costs=(
            lng_cargo_economics.LngEconomicsOnlyCostInput(
                cost_id="terminal-fee",
                category=lng_cargo_economics.LngCashLegCategory.REGAS,
                amount_eur=Decimal("100"),
                payment_date=valuation_date,
                source_reference="synthetic:terminal-fee",
                charge_basis=charge_basis,
            ),
        ),
        energy_stages=(
            lng_energy_balance.LngEnergyStage(
                stage_id="cargo-transfer",
                kind=lng_energy_balance.LngEnergyStageKind.CARGO_TRANSFER,
                input_energy_mwh=Decimal("1000"),
                output_energy_mwh=Decimal("1000"),
                consumed_energy_mwh=Decimal("0"),
                physical_loss_energy_mwh=Decimal("0"),
                source_references=("synthetic:energy:cargo-transfer",),
            ),
        ),
        discount_factors=(
            lng_cargo_economics.LngCashDiscountFactorInput(
                payment_date=valuation_date,
                factor=Decimal("1"),
                curve_reference="synthetic:flat-curve",
                source_reference="synthetic:discount-factor",
                as_of=valuation_date,
            ),
        ),
    )


def test_economics_only_uses_canonical_charge_basis_without_readiness() -> None:
    result = lng_cargo_economics.compute_lng_economics_only(
        _economics_only_input(
            charge_basis=lng_cargo_economics.LngDownstreamChargeBasis.INVOICED_CASH
        )
    )

    assert result.model_version == "lng-economics-only/v1"
    assert result.energy_unit == "MWh"
    assert result.physical_readiness == "NOT_ASSESSED"
    assert result.readiness_assessed is False
    assert result.total_consumed_energy_mwh == Decimal("0")
    assert result.physical_loss_energy_mwh == Decimal("0")
    assert result.total_reduction_energy_mwh == Decimal("0")
    assert result.cargo_margin_eur == Decimal("4900")
    assert result.net_present_value_eur == Decimal("4900")


def test_economics_only_still_refuses_in_kind_charge_basis() -> None:
    with pytest.raises(lng_cargo_economics.LngEconomicsOnlyError) as exc_info:
        lng_cargo_economics.compute_lng_economics_only(
            _economics_only_input(
                charge_basis=lng_cargo_economics.LngDownstreamChargeBasis.IN_KIND
            )
        )

    assert "IN_KIND_COST_NOT_A_CASH_CHARGE" in exc_info.value.codes
