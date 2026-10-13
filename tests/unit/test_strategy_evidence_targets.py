"""Typed per-leg evidence declarations (CR-04 temporal amendment).

``StrategyComponentSpec.evidence_targets`` is the frozen declaration that
target-aware historical selection (engine/2) uses. This file pins the schema and
its validation: explicit fixed UTC intervals and rolling gas-day targets with an
explicit canonical calendar and 0/1 offset. Month/quarter rolls are not a
supported basis and are refused rather than approximated.

The two hash tests here are the compatibility contract. A component that
declares nothing must serialize *exactly* as it did before the field existed,
so pre-amendment definition hashes do not move; a declared target is semantic
input, so it must move the hash. An EXPLICIT_INTERVAL declaration likewise
serializes exactly as it did before GAS_DAY (and its calendar/offset) existed.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from eurogas_nexus.domain.strategy_lab.registry import (
    StrategyComponentSpec,
    StrategyEvidenceTarget,
    StrategyVersionDefinition,
)

# The definition hash produced by the pre-amendment implementation for the
# legacy component below. It is pinned as a literal, not recomputed: recomputing
# would move with the code and could not detect a serializer regression.
LEGACY_DEFINITION_HASH = "sha256:7c76f3b6b65d856503053bdf49dd0a53bcb05fad23422aed082d906ed75e889f"

DEFAULT_BASIS = "EXPLICIT_INTERVAL"


def _legacy_component(**overrides) -> StrategyComponentSpec:
    payload = {
        "component_id": "ocm-da-1",
        "component_type": "OCM_VS_DAY_AHEAD",
        "hubs": ["NBP"],
        "tenors": ["within-day", "day-ahead"],
        "extension_json": {
            "weight": 1.0,
            "day_ahead_price_names": ["SAP"],
            "intraday_price_names": ["ICE_OCM"],
            "positive_spread_threshold_gbp_mwh": 0.0,
            "negative_spread_threshold_gbp_mwh": 0.0,
            "target_bar_minutes": 5,
        },
    }
    payload.update(overrides)
    return StrategyComponentSpec(**payload)


def _target(**overrides) -> dict:
    payload = {
        "leg_id": "day_ahead",
        "price_names": ["SAP"],
        "role": "DELIVERY_PRICE",
        "hub": "NBP",
        "tenor": "day-ahead",
        "price_basis": "MID",
        "target_basis": DEFAULT_BASIS,
        "delivery_start_utc": "2026-10-01T05:00:00Z",
        "delivery_end_utc": "2026-10-02T05:00:00Z",
    }
    payload.update(overrides)
    return payload


def _declared_component(*targets: dict, **overrides) -> StrategyComponentSpec:
    return _legacy_component(
        evidence_targets=[StrategyEvidenceTarget.model_validate(item) for item in targets],
        **overrides,
    )


# --- hash compatibility -----------------------------------------------------


def test_a_component_without_declarations_keeps_the_legacy_hash_exactly() -> None:
    definition = StrategyVersionDefinition(components=[_legacy_component()])

    assert definition.content_hash() == LEGACY_DEFINITION_HASH
    # Not merely hash-equal: the stored payload has no evidence_targets key at
    # all, exactly as before the field existed.
    stored = definition.model_dump(mode="json")
    assert "evidence_targets" not in stored["components"][0]
    assert json.dumps(stored, sort_keys=True).find("evidence_targets") == -1


def test_other_optional_fields_are_not_excluded_with_the_new_field() -> None:
    # The omission is specific to the new declaration. price_basis/resource_id
    # are None in the legacy definition and must still be serialized.
    stored = _legacy_component().model_dump(mode="json")

    assert stored["price_basis"] is None
    assert stored["resource_id"] is None
    assert stored["parameter_refs"] == []
    assert stored["required_evidence"] == []


def test_a_declared_target_changes_the_definition_hash() -> None:
    legacy = StrategyVersionDefinition(components=[_legacy_component()])
    declared = StrategyVersionDefinition(components=[_declared_component(_target())])

    assert declared.content_hash() != legacy.content_hash()
    stored = declared.model_dump(mode="json")
    assert stored["components"][0]["evidence_targets"][0]["leg_id"] == "day_ahead"


def test_changing_a_declared_target_changes_the_hash_again() -> None:
    first = StrategyVersionDefinition(components=[_declared_component(_target())])
    moved = StrategyVersionDefinition(
        components=[
            _declared_component(
                _target(delivery_end_utc="2026-10-03T05:00:00Z"),
            )
        ]
    )

    assert first.content_hash() != moved.content_hash()


# --- typed validation -------------------------------------------------------


def test_a_valid_declaration_round_trips_utc_endpoints() -> None:
    target = StrategyEvidenceTarget.model_validate(_target())
    assert target.delivery_start_utc == datetime(2026, 10, 1, 5, 0, tzinfo=UTC)
    assert target.delivery_end_utc == datetime(2026, 10, 2, 5, 0, tzinfo=UTC)

    component = _declared_component(_target())
    stored = component.model_dump(mode="json")
    restored = StrategyComponentSpec.model_validate(stored)

    assert restored == component
    assert restored.evidence_targets is not None
    assert restored.evidence_targets[0].delivery_start_utc == datetime(
        2026, 10, 1, 5, 0, tzinfo=UTC
    )
    assert stored["evidence_targets"][0]["delivery_start_utc"] == "2026-10-01T05:00:00Z"


def test_a_non_utc_offset_is_preserved_as_the_same_instant() -> None:
    shifted = timezone(timedelta(hours=2))
    target = StrategyEvidenceTarget.model_validate(
        _target(
            delivery_start_utc=datetime(2026, 10, 1, 7, 0, tzinfo=shifted),
            delivery_end_utc=datetime(2026, 10, 2, 7, 0, tzinfo=shifted),
        )
    )

    assert target.delivery_start_utc == datetime(2026, 10, 1, 5, 0, tzinfo=UTC)


def test_a_naive_timestamp_is_refused() -> None:
    with pytest.raises(ValidationError):
        StrategyEvidenceTarget.model_validate(
            _target(delivery_start_utc="2026-10-01T05:00:00")
        )


@pytest.mark.parametrize(
    "start,end",
    [
        ("2026-10-02T05:00:00Z", "2026-10-01T05:00:00Z"),
        ("2026-10-01T05:00:00Z", "2026-10-01T05:00:00Z"),
    ],
)
def test_an_unordered_or_empty_interval_is_refused(start: str, end: str) -> None:
    with pytest.raises(ValidationError):
        StrategyEvidenceTarget.model_validate(
            _target(delivery_start_utc=start, delivery_end_utc=end)
        )


@pytest.mark.parametrize(
    "overrides",
    [
        {"leg_id": ""},
        {"leg_id": "   "},
        {"hub": ""},
        {"tenor": " "},
        {"price_basis": ""},
        {"price_names": []},
        {"price_names": ["SAP", "SAP"]},
        {"price_names": ["SAP", "  "]},
        {"role": ""},
    ],
)
def test_incomplete_or_duplicate_declarations_are_refused(overrides: dict) -> None:
    with pytest.raises(ValidationError):
        StrategyEvidenceTarget.model_validate(_target(**overrides))


@pytest.mark.parametrize(
    "basis",
    ["GAS_DAY", "ROLLING_GAS_DAY", "TENOR_ROLL", "", "explicit_interval"],
)
def test_an_unsupported_target_basis_is_refused(basis: str) -> None:
    # GAS_DAY without the required explicit calendar/offset is incomplete and is
    # refused; month/quarter rolls and any other unknown basis have no
    # convention validation, so they are refused rather than approximated.
    with pytest.raises(ValidationError):
        StrategyEvidenceTarget.model_validate(_target(target_basis=basis))


def _gas_day_target(**overrides) -> dict:
    payload = _target(
        target_basis="GAS_DAY",
        delivery_start_utc=None,
        delivery_end_utc=None,
        calendar_id="EU-CAM-UTC-2025",
        gas_day_offset=1,
    )
    payload.update(overrides)
    return payload


def test_a_rolling_gas_day_target_requires_calendar_and_offset() -> None:
    target = StrategyEvidenceTarget.model_validate(_gas_day_target())

    assert target.calendar_id == "EU-CAM-UTC-2025"
    assert target.gas_day_offset == 1
    assert target.delivery_start_utc is None
    assert target.delivery_end_utc is None


@pytest.mark.parametrize(
    ("overrides", "match"),
    [
        ({"calendar_id": None}, "calendar_id"),
        ({"calendar_id": "EU-CAM-2025"}, "EU-CAM-UTC-2025"),
        ({"gas_day_offset": None}, "gas_day_offset"),
        ({"gas_day_offset": 2}, "gas_day_offset"),
        ({"gas_day_offset": True}, "gas_day_offset"),
        (
            {
                "delivery_start_utc": "2026-10-01T05:00:00Z",
                "delivery_end_utc": "2026-10-02T05:00:00Z",
            },
            "no explicit delivery endpoints",
        ),
    ],
)
def test_an_incomplete_rolling_target_is_refused(overrides: dict, match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        StrategyEvidenceTarget.model_validate(_gas_day_target(**overrides))


def test_a_rolling_target_serializes_without_endpoints() -> None:
    target = StrategyEvidenceTarget.model_validate(_gas_day_target())
    stored = target.model_dump(mode="json")

    assert "delivery_start_utc" not in stored
    assert "delivery_end_utc" not in stored
    assert stored["calendar_id"] == "EU-CAM-UTC-2025"
    assert stored["gas_day_offset"] == 1
    assert StrategyEvidenceTarget.model_validate(stored) == target


def test_an_explicit_target_does_not_gain_rolling_fields() -> None:
    stored = StrategyEvidenceTarget.model_validate(_target()).model_dump(mode="json")

    assert "calendar_id" not in stored
    assert "gas_day_offset" not in stored


def test_a_rolling_target_moves_the_definition_hash() -> None:
    explicit = StrategyVersionDefinition(components=[_declared_component(_target())])
    rolling = StrategyVersionDefinition(
        components=[_declared_component(_gas_day_target())]
    )

    assert rolling.content_hash() != explicit.content_hash()


def test_an_unknown_declaration_field_is_refused() -> None:
    # Ignored semantics are worse than a refusal: an unread field would look
    # declared while having no effect.
    with pytest.raises(ValidationError):
        StrategyEvidenceTarget.model_validate(_target(rolling_convention="GAS_DAY"))


def test_a_reference_level_declares_its_validity_interval() -> None:
    target = StrategyEvidenceTarget.model_validate(
        _target(role="REFERENCE_LEVEL", price_names=["SAP_ASSESSMENT"])
    )

    assert target.role.value == "REFERENCE_LEVEL"
    assert target.delivery_end_utc > target.delivery_start_utc


# --- component-level uniqueness --------------------------------------------


def test_a_duplicate_leg_id_is_refused() -> None:
    with pytest.raises(ValidationError, match="duplicate leg_id"):
        _declared_component(_target(), _target(price_names=["OTHER"]))


def test_a_price_name_declared_by_two_legs_is_refused() -> None:
    with pytest.raises(ValidationError, match="more than one leg"):
        _declared_component(_target(), _target(leg_id="intraday", role="REFERENCE_LEVEL"))


def test_distinct_legs_may_declare_distinct_names() -> None:
    component = _declared_component(
        _target(),
        _target(leg_id="intraday", price_names=["ICE_OCM"], tenor="within-day"),
    )

    assert component.evidence_targets is not None
    assert [target.leg_id for target in component.evidence_targets] == [
        "day_ahead",
        "intraday",
    ]


def test_declarations_are_optional_so_legacy_definitions_still_parse() -> None:
    component = StrategyComponentSpec.model_validate(
        {"component_id": "c1", "component_type": "OCM_VS_DAY_AHEAD"}
    )
    assert component.evidence_targets is None

    empty = StrategyComponentSpec.model_validate(
        {"component_id": "c1", "component_type": "OCM_VS_DAY_AHEAD", "evidence_targets": []}
    )
    # An empty list is stored as declared-and-empty, not silently dropped.
    assert empty.model_dump(mode="json")["evidence_targets"] == []


def test_case_insensitive_series_cannot_claim_two_targets() -> None:
    with pytest.raises(ValidationError, match="distinct"):
        StrategyEvidenceTarget.model_validate(_target(price_names=["SAP", "sap"]))
    with pytest.raises(ValidationError, match="more than one leg"):
        _legacy_component(
            evidence_targets=[_target(), _target(leg_id="other", price_names=["sap"])]
        )


def test_component_serializer_honours_projection_options() -> None:
    component = _legacy_component(evidence_targets=[_target()])
    assert component.model_dump(include={"component_id"}) == {"component_id": "ocm-da-1"}
    assert "evidence_targets" not in component.model_dump(exclude={"evidence_targets"})
