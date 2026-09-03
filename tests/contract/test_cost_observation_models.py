"""Contract tests for generalized cost observations."""

from eurogas_nexus.domain.economics.cost_observation import (
    OBSERVATION_TYPES,
    SCOPE_TYPES,
    CostObservation,
    validate_cost_observation,
)


def _base() -> CostObservation:
    return CostObservation(
        observation_id="cost-test-001",
        scope_type="ROUTE",
        scope_id="TTF-NBP",
        observation_type="TSO_PUBLISHED",
        value=1.25,
        currency="EUR",
        unit="MWh",
        effective_from_utc="2026-10-01T00:00:00+00:00",
        source_system="ENTSOG_TARIFFS",
        source_reference="https://example.test/tariffs/2026",
    )


def test_cost_observation_accepts_published_tariff() -> None:
    validate_cost_observation(_base())


def test_cost_observation_accepts_contract_and_secondary_values() -> None:
    for observation_type in ["LONG_TERM_CONTRACT", "SECONDARY_TRANSFER", "AUCTION_BID"]:
        observation = _base()
        object.__setattr__(observation, "observation_type", observation_type)
        validate_cost_observation(observation)


def test_cost_observation_rejects_unknown_scope_type() -> None:
    observation = _base()
    object.__setattr__(observation, "scope_type", "INSTRUMENT")

    try:
        validate_cost_observation(observation)
    except ValueError as exc:
        assert "scope_type" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_cost_observation_rejects_negative_value() -> None:
    observation = _base()
    object.__setattr__(observation, "value", -1)

    try:
        validate_cost_observation(observation)
    except ValueError as exc:
        assert "non-negative" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_observation_type_registry_is_closed() -> None:
    assert "TSO_PUBLISHED" in OBSERVATION_TYPES
    assert "LONG_TERM_CONTRACT" in OBSERVATION_TYPES
    assert "SECONDARY_TRANSFER" in OBSERVATION_TYPES
    assert "AUCTION_BID" in OBSERVATION_TYPES
    assert "LNG_SLOT_BOOKING" in OBSERVATION_TYPES
    assert "MANUAL_OVERRIDE" in OBSERVATION_TYPES
    assert "ROUTE" in SCOPE_TYPES
    assert "POINT" in SCOPE_TYPES
    assert "LNG_TERMINAL" in SCOPE_TYPES
