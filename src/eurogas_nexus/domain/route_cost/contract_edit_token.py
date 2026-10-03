"""Opaque edit token for the mutable upstream-contract row (stale-edit protection).

The upstream contract row is the one mutable persisted state behind
``POST /api/route-cost/upstream-contracts``. The governed write can turn a
concurrent edit into evidenced overwrites, but neither a captured economic
revision nor its number can tell a governed writer whether the row it is about
to update is still the row it read: a later write may have changed display
metadata, the raw operator notes or the updated instant without allocating a
new economic revision. This module defines the token the contract read surfaces
return and the governed write compares under the existing row lock.

Design: a stable canonical JSON document - a schema discriminator plus every
persisted column of ``upstream_resource_contracts`` (identity, economics,
display metadata, raw operator notes, the declared payment-terms carrier,
created/updated instants) - hashed with SHA-256. Any persisted change, economic
or metadata-only, produces a different token.

Schema version history: ``v1`` covered the row before the S2b payment-terms
carrier existed. ``v2`` adds that column to the covered field set, so a token
loaded before the upgrade can never compare equal after it: a stale draft
holding a ``v1`` token is refused with the same stable conflict code and must
be reloaded. There is deliberately no fallback that compares a ``v1`` token on
the ``v2`` field set.

Honest limitations, stated rather than implied:

* the token is an integrity/identity check on the mutable row state within this
  deployment's storage - it is **not** a cryptographic signature, MAC or
  capability. Anyone who can read the row can recompute it, and it proves
  nothing about who wrote the state.
* it is **not** a monotonic lifecycle counter and carries no ordering: it cannot
  tell "newer" from "different", and it is not the captured revision number.
  A token only means "the same persisted row content as the read that produced
  it" (up to hash collision).
* it does not substitute for the still-proposed immutable revision lifecycle
  (``DRAFT|FROZEN|SUPERSEDED``): it guards the single mutable legacy row, not a
  revision graph.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime

#: Canonical schema discriminator of the edit-token document. Changing the
#: covered field set or the canonicalization requires a new version, so a token
#: from an older shape can never compare equal to a newer one. ``v2`` added
#: ``payment_terms_json`` to the covered columns (S2b), so every token loaded
#: from a pre-upgrade read is stale by construction and must be reloaded.
CONTRACT_EDIT_TOKEN_SCHEMA = "upstream-contract-edit-token/v2"

#: Token text prefix; the digest is lowercase hex SHA-256.
CONTRACT_EDIT_TOKEN_PREFIX = "sha256:"

#: Stable refusal code for a supplied token that is not a token this API issues.
CONTRACT_EDIT_TOKEN_MALFORMED = "contract_edit_token_malformed"

#: Stable refusal code for an edit precondition that does not match the stored
#: row state. This includes create-only requests against an existing identity,
#: token-bearing requests for a nonexistent identity, and a token whose covered
#: state the stored row no longer has.
CONTRACT_EDIT_CONFLICT = "contract_edit_conflict"

#: Every persisted column the token covers, in the table's own order. A focused
#: test asserts this tuple equals the model's column set, so a column added
#: without a token-version decision fails rather than silently escaping the
#: write precondition.
CONTRACT_EDIT_TOKEN_FIELDS = (
    "contract_id",
    "contract_name",
    "resource_type",
    "delivery_point_name",
    "gas_year",
    "delivery_quantity_mwh_per_day",
    "contract_price_gbp_mwh",
    "settlement_frequency",
    "upstream_payment_lag_days",
    "screen_sale_cash_lag_days",
    "delivery_tolerance_pct",
    "nomination_tolerance_pct",
    "tolerance_risk_allowance_gbp_mwh",
    "annual_financing_rate_pct",
    "owned_entry_capacity_mwh_per_day",
    "owned_exit_capacity_mwh_per_day",
    "allowed_exit_points",
    "eligible_sale_modes",
    "notes",
    "payment_terms_json",
    "created_at_utc",
    "updated_at_utc",
)

_HEX_DIGITS = frozenset("0123456789abcdef")


class ContractEditTokenError(ValueError):
    """An edit-token value, or the state it covers, is not this contract.

    Attributes:
        code: Stable machine-readable refusal code.
        detail: Human-readable explanation of the refused value.
    """

    def __init__(self, code: str, detail: str) -> None:
        """Build the refusal from a stable code and a human-readable detail."""

        self.code = code
        self.detail = detail
        super().__init__(f"{code} ({detail})")


def canonical_contract_edit_token(values: Mapping[str, object]) -> str:
    """Return the opaque edit token of one persisted contract state.

    Args:
        values: Exactly the :data:`CONTRACT_EDIT_TOKEN_FIELDS` mapping read from
            one stored row.

    Returns:
        ``sha256:<hex>`` over the canonical document.

    Raises:
        ContractEditTokenError: When the mapping's field set differs from the
            fixed schema, or a value cannot be canonicalized honestly (a bool,
            a non-finite float, a non-text list entry or an unsupported type).
    """

    return (
        CONTRACT_EDIT_TOKEN_PREFIX
        + hashlib.sha256(_canonical_document_text(values).encode("utf-8")).hexdigest()
    )


def validate_contract_edit_token(value: object) -> str:
    """Return an accepted token exactly as supplied, or refuse it.

    The accepted text is precisely what :func:`canonical_contract_edit_token`
    emits: ``sha256:`` followed by 64 lowercase hex characters. Whitespace
    padding, upper-case hex, another prefix and non-text values are refused with
    :data:`CONTRACT_EDIT_TOKEN_MALFORMED`, so a malformed precondition is
    reported as malformed rather than compared as a near-miss.

    Raises:
        ContractEditTokenError: When the value is not a well-formed token.
    """

    if not isinstance(value, str) or not value.startswith(CONTRACT_EDIT_TOKEN_PREFIX):
        raise ContractEditTokenError(
            CONTRACT_EDIT_TOKEN_MALFORMED,
            "the supplied edit token is not a token this API issues; read the"
            " contract again and use the token from that read",
        )
    digest = value[len(CONTRACT_EDIT_TOKEN_PREFIX) :]
    if len(digest) != 64 or any(char not in _HEX_DIGITS for char in digest):
        raise ContractEditTokenError(
            CONTRACT_EDIT_TOKEN_MALFORMED,
            "the supplied edit token is not a token this API issues; read the"
            " contract again and use the token from that read",
        )
    return value


def _canonical_document_text(values: Mapping[str, object]) -> str:
    """Serialize the covered state as canonical JSON (fixed field set, sorted keys)."""

    if not isinstance(values, Mapping):
        raise ContractEditTokenError(
            "contract_edit_token_state_invalid",
            f"edit-token state must be a mapping, got {type(values).__name__}",
        )
    keys = set(values)
    expected = set(CONTRACT_EDIT_TOKEN_FIELDS)
    if keys != expected:
        missing = sorted(str(key) for key in expected - keys)
        unexpected = sorted(str(key) for key in keys - expected)
        raise ContractEditTokenError(
            "contract_edit_token_state_field_mismatch",
            "edit-token state must cover exactly the persisted contract columns;"
            f" missing={missing} unexpected={unexpected}",
        )
    document = {
        "schema": CONTRACT_EDIT_TOKEN_SCHEMA,
        "state": {
            name: _canonical_value(values[name], name)
            for name in CONTRACT_EDIT_TOKEN_FIELDS
        },
    }
    return json.dumps(
        document,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _canonical_value(value: object, name: str) -> object:
    """Canonicalize one covered column value without guessing a type."""

    if value is None:
        return None
    if isinstance(value, bool):
        # bool is an int subclass; a stored boolean is not a canonical column value.
        raise ContractEditTokenError(
            "contract_edit_token_state_value_unsupported",
            f"{name} must not be a bool",
        )
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ContractEditTokenError(
                "contract_edit_token_state_value_unsupported",
                f"{name} must be a finite number",
            )
        return value
    if isinstance(value, str):
        return value
    if isinstance(value, datetime):
        return _canonical_instant_text(value)
    if isinstance(value, Sequence):
        entries = []
        for item in value:
            if not isinstance(item, str):
                raise ContractEditTokenError(
                    "contract_edit_token_state_value_unsupported",
                    f"{name} entries must be strings, got {type(item).__name__}",
                )
            entries.append(item)
        return entries
    raise ContractEditTokenError(
        "contract_edit_token_state_value_unsupported",
        f"{name} has unsupported type {type(value).__name__}",
    )


def _canonical_instant_text(value: datetime) -> str:
    """UTC-normalized ISO text of one stored instant.

    Every write path stores UTC instants. PostgreSQL returns them
    timezone-aware, while the focused SQLite fixture returns them naive; both
    readings of one stored instant therefore canonicalize to the same
    offset-less UTC text. A naive value is read as the UTC instant the storage
    contract says it is, not as local time.
    """

    if value.tzinfo is None or value.utcoffset() is None:
        return value.isoformat()
    return value.astimezone(UTC).replace(tzinfo=None).isoformat()
