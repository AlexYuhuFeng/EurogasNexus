"""Stale-edit token contract for the mutable upstream-contract row.

`docs/engineering/CONTRACT_PAYMENT_INTEGRATION_PLAN.md` section 13: the
governed contract write compares an opaque token of the whole persisted row
before it captures, audits or mutates anything. These tests pin the token's
own contract:

* it covers exactly the persisted contract columns (a column added without a
  token-version decision fails here);
* every persisted category - economics, identity, display metadata, raw
  operator notes and the updated instant - changes it;
* one stored instant canonicalizes identically whether a driver returns it
  timezone-aware or naive;
* malformed supplied tokens are refused with the stable code, never compared
  as near-misses;
* values the contract does not declare are refused rather than guessed.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from eurogas_nexus.db.models.route_cost import UpstreamResourceContractRecord
from eurogas_nexus.domain.route_cost.contract_edit_token import (
    CONTRACT_EDIT_CONFLICT,
    CONTRACT_EDIT_TOKEN_FIELDS,
    CONTRACT_EDIT_TOKEN_MALFORMED,
    CONTRACT_EDIT_TOKEN_PREFIX,
    CONTRACT_EDIT_TOKEN_SCHEMA,
    ContractEditTokenError,
    canonical_contract_edit_token,
    validate_contract_edit_token,
)

_NOW = datetime(2026, 10, 2, 9, 30, 15, 123456, tzinfo=UTC)


def _state(**overrides: object) -> dict[str, object]:
    """One stored contract state covering exactly the declared token fields."""

    state: dict[str, object] = {
        "contract_id": "token-contract-2025",
        "contract_name": "Token TTF supply 2025",
        "resource_type": "PIPELINE_IMPORT",
        "delivery_point_name": "TTF",
        "gas_year": "2025+",
        "delivery_quantity_mwh_per_day": 125.5,
        "contract_price_gbp_mwh": 29.75,
        "settlement_frequency": "monthly",
        "upstream_payment_lag_days": 20,
        "screen_sale_cash_lag_days": 1,
        "delivery_tolerance_pct": 2.0,
        "nomination_tolerance_pct": 1.0,
        "tolerance_risk_allowance_gbp_mwh": 0.1,
        "annual_financing_rate_pct": 6.0,
        "owned_entry_capacity_mwh_per_day": None,
        "owned_exit_capacity_mwh_per_day": None,
        "allowed_exit_points": ["NBP", "TTF"],
        "eligible_sale_modes": ["TARGET_MARKET_SALE", "LOCAL_MARKET_SALE"],
        "notes": '{"operator_notes": "operator draft", "variable_cost_gbp_mwh": 0.75}',
        "created_at_utc": _NOW,
        "updated_at_utc": _NOW,
    }
    state.update(overrides)
    return state


def test_token_covers_exactly_every_persisted_contract_column() -> None:
    """A new column must be added to the token (or version the schema) explicitly."""

    columns = {column.name for column in UpstreamResourceContractRecord.__table__.columns}
    assert set(CONTRACT_EDIT_TOKEN_FIELDS) == columns
    assert len(CONTRACT_EDIT_TOKEN_FIELDS) == len(columns)


def test_equal_states_hash_to_one_token_and_the_schema_is_discriminated() -> None:
    first = canonical_contract_edit_token(_state())
    second = canonical_contract_edit_token(dict(_state()))

    assert first == second
    assert first.startswith(CONTRACT_EDIT_TOKEN_PREFIX)
    assert len(first) == len(CONTRACT_EDIT_TOKEN_PREFIX) + 64
    assert CONTRACT_EDIT_TOKEN_SCHEMA.startswith("upstream-contract-edit-token/")


@pytest.mark.parametrize(
    ("field", "changed"),
    [
        ("contract_id", "token-contract-2026"),
        ("contract_name", "Renamed supply"),
        ("resource_type", "LNG_REGAS"),
        ("delivery_point_name", "NBP"),
        ("gas_year", "2026+"),
        ("delivery_quantity_mwh_per_day", 130.0),
        ("contract_price_gbp_mwh", 31.5),
        ("settlement_frequency", "quarterly"),
        ("upstream_payment_lag_days", 21),
        ("screen_sale_cash_lag_days", 2),
        ("delivery_tolerance_pct", 2.5),
        ("nomination_tolerance_pct", 1.5),
        ("tolerance_risk_allowance_gbp_mwh", 0.2),
        ("annual_financing_rate_pct", 6.5),
        ("owned_entry_capacity_mwh_per_day", 0.0),
        ("owned_exit_capacity_mwh_per_day", 0.0),
        ("allowed_exit_points", ["NBP"]),
        ("eligible_sale_modes", ["LOCAL_MARKET_SALE"]),
        ("notes", '{"operator_notes": "renamed"}'),
        ("updated_at_utc", _NOW + timedelta(seconds=1)),
    ],
)
def test_every_persisted_field_changes_the_token(field: str, changed: object) -> None:
    """Economics *and* metadata/identity/instant changes all invalidate the token."""

    base = canonical_contract_edit_token(_state())
    assert canonical_contract_edit_token(_state(**{field: changed})) != base


def test_one_stored_instant_canonicalizes_across_driver_timezone_shapes() -> None:
    """PostgreSQL returns aware UTC; the SQLite fixture returns naive UTC."""

    aware = canonical_contract_edit_token(_state())
    naive_state = _state()
    naive_state["created_at_utc"] = _NOW.replace(tzinfo=None)
    naive_state["updated_at_utc"] = _NOW.replace(tzinfo=None)
    assert canonical_contract_edit_token(naive_state) == aware

    # The same instant in another offset is the same instant.
    offset_state = _state()
    offset = _NOW.astimezone(timezone(timedelta(hours=8)))
    offset_state["created_at_utc"] = offset
    offset_state["updated_at_utc"] = offset
    assert canonical_contract_edit_token(offset_state) == aware


def test_a_well_formed_token_is_returned_exactly_and_a_malformed_one_is_refused() -> None:
    token = canonical_contract_edit_token(_state())
    assert validate_contract_edit_token(token) == token

    for value in (
        None,
        42,
        "",
        "not-a-token",
        token.upper(),
        f" {token}",
        token + "\n",
        CONTRACT_EDIT_TOKEN_PREFIX + "g" * 64,
        CONTRACT_EDIT_TOKEN_PREFIX,
        CONTRACT_EDIT_TOKEN_PREFIX + "0" * 63,
        CONTRACT_EDIT_TOKEN_PREFIX + "0" * 65,
        "md5:" + "0" * 64,
    ):
        with pytest.raises(ContractEditTokenError) as refused:
            validate_contract_edit_token(value)
        assert refused.value.code == CONTRACT_EDIT_TOKEN_MALFORMED


def test_values_the_contract_does_not_declare_are_refused_not_guessed() -> None:
    unsupported = "contract_edit_token_state_value_unsupported"
    for bad_state, expected_code in (
        ({field: object() for field in CONTRACT_EDIT_TOKEN_FIELDS}, unsupported),
        (_state(notes=True), unsupported),
        (_state(contract_price_gbp_mwh=float("nan")), unsupported),
        (_state(allowed_exit_points=["NBP", 7]), unsupported),
        (_state(updated_at_utc={"not": "a datetime"}), unsupported),
    ):
        with pytest.raises(ContractEditTokenError) as refused:
            canonical_contract_edit_token(bad_state)
        assert refused.value.code == expected_code

    missing = _state()
    missing.pop("notes")
    with pytest.raises(ContractEditTokenError) as refused:
        canonical_contract_edit_token(missing)
    assert refused.value.code == "contract_edit_token_state_field_mismatch"

    with pytest.raises(ContractEditTokenError) as refused:
        canonical_contract_edit_token(_state(unexpected_field="x"))
    assert refused.value.code == "contract_edit_token_state_field_mismatch"


def test_the_public_refusal_codes_are_the_stable_protocol_codes() -> None:
    assert CONTRACT_EDIT_CONFLICT == "contract_edit_conflict"
    assert CONTRACT_EDIT_TOKEN_MALFORMED == "contract_edit_token_malformed"
