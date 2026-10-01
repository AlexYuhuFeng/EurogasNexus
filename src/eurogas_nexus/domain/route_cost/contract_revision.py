"""Immutable economic snapshot of one upstream resource contract revision.

S1a of ``docs/engineering/CONTRACT_PAYMENT_INTEGRATION_PLAN.md`` (repository
baseline ``1676b98``): the immutable economic payload a future contract
revision will persist, plus a strict mapping from today's legacy contract
payload. This slice defines the contract only — there is no DB model,
migration, table, repository write, API, UI, audit or concurrency change.

Why: an upstream contract is currently one mutable row whose ``notes`` JSON
carries three economic costs, so a valuation cannot cite an immutable economic
record and a display rename is indistinguishable from a price change. The
snapshot separates them: :class:`ContractDisplayMetadata` holds what a desk
sees and never enters the economic hash;
:class:`UpstreamContractEconomicSnapshot` holds the economic content with an
explicit ``schema_version`` and a canonical deterministic hash suitable for
replay.

Boundaries and non-claims (see the plan's missing-input policy):

* No payment terms are inferred. ``payment_terms`` is always ``null`` in this
  schema version: the legacy lag integers are captured verbatim as legacy cash
  lags, never as dates, anchors, calendars or day counts.
* No historical validity is invented. No effective/recorded date is part of
  the snapshot; the legacy row's ``updated_at_utc`` is the last row update
  time, not migration time, and it says nothing about when the economics
  applied. A capture time belongs to future persistence and the historic
  validity of these values is unknown.
* No business validation is duplicated. The payload carries no sign or range
  policy (the current write path refuses negative prices); the legacy mapper
  records stored values verbatim and never clamps them the way the optimizer's
  ``non_negative_number`` does. Missing optional values stay ``null``, never
  ``0``.
* No ontology type is added. Field names follow the existing
  ``UpstreamResourceContract`` binding and the current payload; no new
  ``StrEnum`` or ontology concept is introduced, so no ontology review is
  needed yet (plan section 2.6 keeps that decision open).
* No arithmetic moves. The legacy optimizer and its payloads are untouched.

Numeric discipline: economic values are exact ``Decimal`` values or ``None``;
``bool``, floats and non-finite values are refused by the payload. The single
place where a legacy binary float becomes a ``Decimal`` is the legacy mapping
helper, which uses the shortest round-trip decimal string (``str(float)``).
``legacy_float64`` is the legacy *capture precision ceiling*, not a claim that
every captured value was literally a float: legacy ints and exact decimal
strings convert losslessly and stay under the same ceiling label, because the
original typed precision of a value stored as a binary float is not
recoverable.

Canonical replay: every ``Decimal`` serializes as an exact decimal string, list
order is preserved, the schema version and ``payment_terms: null`` are always
included, and :meth:`UpstreamContractEconomicSnapshot.content_hash` is SHA-256
over that canonical JSON (sorted keys, no insignificant whitespace, UTF-8).
Serialization is memory-safe: a generous documented storage guard — never a
market or accounting rule — refuses a coefficient or plain-notation length
beyond what this schema could store *before* any value is formatted, so a
pathological value such as ``Decimal("1e999999999")`` cannot allocate
unbounded memory. Decoding is the strict inverse: it accepts only the exact
plain-notation spelling serialization produces (no whitespace padding,
underscores, plus sign or exponent notation). The hash is an integrity/identity
check for an immutable revision — never a signature.

Boundary with the current notes parser: ``db/repositories/route_cost.py`` and
``application/resource_pool.py`` parse the same notes column, but this pure
domain module must not import ``db``/``application`` (Architecture V2
dependency direction), so the JSON-object-or-empty semantics are re-implemented
here with one deliberate difference: a non-empty notes value that is not a JSON
object is recorded as an explicit mapping issue instead of being silently
treated as empty. ``tests/unit/test_contract_revision_payload.py`` asserts the
structured note field names stay in sync with the repository.

The module is pure: standard library only, no I/O, no clock, no randomness;
identical inputs produce byte-identical canonical JSON and hashes.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Self

CONTRACT_REVISION_SCHEMA_VERSION = "upstream-contract-revision/v1"

#: Reviewed provenance labels for the numeric representation of a snapshot.
#: ``legacy_float64`` is the legacy capture path's precision ceiling: a value
#: stored as a binary float (or a JSON number read back as one) is captured via
#: its shortest round-trip string and its original typed precision is not
#: recoverable. It does not mean every value was literally a float — legacy
#: ints and exact decimal strings convert losslessly and stay under this
#: ceiling. New captures use ``exact_decimal``.
SOURCE_PRECISION_EXACT_DECIMAL = "exact_decimal"
SOURCE_PRECISION_LEGACY_FLOAT64 = "legacy_float64"

_REVIEWED_SOURCE_PRECISIONS = frozenset(
    {SOURCE_PRECISION_EXACT_DECIMAL, SOURCE_PRECISION_LEGACY_FLOAT64}
)

#: Stable mapping-issue codes recorded inside the economic snapshot.
LEGACY_NOTES_NOT_STRUCTURED = "legacy_notes_not_structured_json"
LEGACY_STRUCTURED_VALUE_CONFLICT = "legacy_structured_value_conflict"

#: Stable refusal code for a decimal value outside the storage guards below.
DECIMAL_STORAGE_BOUNDS_EXCEEDED = "decimal_storage_bounds_exceeded"

#: Stable refusal code for a canonical-document decimal spelling that is not
#: the exact plain-notation text this module serializes.
CANONICAL_DECIMAL_NOT_CANONICAL = "canonical_decimal_not_canonical"

#: Generous serialization/storage guards — deliberately NOT market, credit or
#: accounting rules, and not tied to any business range. They only bound the
#: memory a single decimal value may demand when it becomes canonical
#: plain-notation text, so a pathological coefficient or exponent such as
#: ``Decimal("1e999999999")`` is refused before ``format(value, "f")`` can try
#: to allocate its multi-gigabyte plain representation. Realistic contract
#: values sit many orders of magnitude inside these bounds.
MAX_DECIMAL_COEFFICIENT_DIGITS = 10_000
MAX_DECIMAL_PLAIN_TEXT_LENGTH = 100_000

#: Legacy notes keys that hold economic costs. Must stay in sync with
#: ``db/repositories/route_cost.py::_STRUCTURED_NOTE_FIELDS``; the focused test
#: suite fails on drift.
_STRUCTURED_ECONOMIC_NOTE_FIELDS = (
    "variable_cost_gbp_mwh",
    "regas_fee_gbp_mwh",
    "fuel_loss_allowance_pct",
)

_REQUIRED_DECIMAL_FIELDS = (
    "delivery_quantity_mwh_per_day",
    "contract_price_gbp_mwh",
    "delivery_tolerance_pct",
    "nomination_tolerance_pct",
    "annual_financing_rate_pct",
)
_OPTIONAL_COLUMN_DECIMAL_FIELDS = (
    "tolerance_risk_allowance_gbp_mwh",
    "owned_entry_capacity_mwh_per_day",
    "owned_exit_capacity_mwh_per_day",
)
_OPTIONAL_DECIMAL_FIELDS = (
    *_OPTIONAL_COLUMN_DECIMAL_FIELDS,
    *_STRUCTURED_ECONOMIC_NOTE_FIELDS,
)
_DECIMAL_FIELD_NAMES = (*_REQUIRED_DECIMAL_FIELDS, *_OPTIONAL_DECIMAL_FIELDS)
_LAG_FIELD_NAMES = ("upstream_payment_lag_days", "screen_sale_cash_lag_days")
_TEXT_FIELD_NAMES = (
    "contract_id",
    "resource_type",
    "delivery_point_name",
    "gas_year",
    "settlement_frequency",
)
_LIST_FIELD_NAMES = ("allowed_exit_points", "eligible_sale_modes")
_CANONICAL_DOCUMENT_FIELDS = frozenset(
    {
        "schema_version",
        "payment_terms",
        "numeric_source_precision",
        "mapping_issues",
        *_TEXT_FIELD_NAMES,
        *_DECIMAL_FIELD_NAMES,
        *_LAG_FIELD_NAMES,
        *_LIST_FIELD_NAMES,
    }
)


class ContractRevisionPayloadError(ValueError):
    """Deterministic refusal to build, map or decode a revision payload.

    Attributes:
        code: Stable machine-readable refusal code.
        detail: Human-readable explanation of the refused value.
    """

    def __init__(self, code: str, detail: str) -> None:
        """Build the refusal from a stable code and a human-readable detail."""

        self.code = code
        self.detail = detail
        super().__init__(f"{code} ({detail})")


def _required_text(value: object, name: str) -> str:
    """Return one required, non-blank text field.

    Args:
        value: Raw field value.
        name: Field name used in refusal details.

    Returns:
        The text exactly as supplied (never stripped or coerced).

    Raises:
        ContractRevisionPayloadError: When the value is missing, not a string
            or blank.
    """

    if value is None:
        raise ContractRevisionPayloadError(
            "text_field_missing", f"{name} is required and must not be None"
        )
    if not isinstance(value, str):
        raise ContractRevisionPayloadError(
            "text_not_string", f"{name} must be str, got {type(value).__name__}"
        )
    if not value.strip():
        raise ContractRevisionPayloadError(
            "text_field_blank", f"{name} must not be blank"
        )
    return value


def _optional_text(value: object, name: str) -> str | None:
    """Return one optional text field: ``None`` when absent, validated otherwise."""

    if value is None:
        return None
    return _required_text(value, name)


def _decimal_storage_guard(value: Decimal, name: str) -> None:
    """Refuse one finite decimal outside the storage guards, before formatting.

    Inspects ``value.as_tuple()`` only: the coefficient digit count and the
    plain-notation length are computed with integer arithmetic, so checking a
    pathological value such as ``Decimal("1e999999999")`` is cheap and cannot
    allocate. The projection is a conservative upper bound of
    ``len(format(value, "f"))`` and is exact for every value except zero with a
    positive exponent, which the guard refuses beyond the bound rather than
    relying on the formatter's "0" special case. Zero is not exempt:
    ``Decimal("0e999999999")`` and ``Decimal("0e-999999999")`` are both
    refused.

    The bounds are storage/serialization guards, never market or accounting
    rules: realistic contract values sit many orders of magnitude inside them,
    and they exist only so serializing a revision cannot allocate unbounded
    memory.

    Raises:
        ContractRevisionPayloadError: With code
            :data:`DECIMAL_STORAGE_BOUNDS_EXCEEDED` when the coefficient digit
            count or the projected plain-notation length exceeds the guard.
    """

    sign, digits, exponent = value.as_tuple()
    coefficient_digits = len(digits)
    if exponent >= 0:
        projected_length = coefficient_digits + exponent
    elif coefficient_digits > -exponent:
        projected_length = coefficient_digits + 1
    else:
        projected_length = 2 - exponent
    if sign:
        projected_length += 1
    if (
        coefficient_digits > MAX_DECIMAL_COEFFICIENT_DIGITS
        or projected_length > MAX_DECIMAL_PLAIN_TEXT_LENGTH
    ):
        raise ContractRevisionPayloadError(
            DECIMAL_STORAGE_BOUNDS_EXCEEDED,
            f"{name} has {coefficient_digits} coefficient digits and needs up"
            f" to {projected_length} plain-notation characters; the storage"
            f" guard allows {MAX_DECIMAL_COEFFICIENT_DIGITS} digits and"
            f" {MAX_DECIMAL_PLAIN_TEXT_LENGTH} characters",
        )


def _finite_decimal(value: object, name: str) -> Decimal:
    """Return one exact finite ``Decimal`` inside the storage guards.

    Refuses bool, float, text, non-finite values and decimals whose coefficient
    or plain-notation length exceeds the storage guard.

    任何非 ``Decimal`` 表示（含 bool/float/str/int）或非有限值都拒绝，避免
    把不可恢复的二进制精度伪装成精确值；旧浮点转换只允许发生在旧数据映射
    路径（``_legacy_decimal``）。超出存储上界的系数或指数同样拒绝，避免
    格式化时分配巨量内存。
    """

    if isinstance(value, bool):
        raise ContractRevisionPayloadError(
            "number_bool_rejected", f"{name} is a bool; booleans are never numbers here"
        )
    if not isinstance(value, Decimal):
        raise ContractRevisionPayloadError(
            "number_not_decimal",
            f"{name} must be an exact Decimal, got {type(value).__name__}",
        )
    if not value.is_finite():
        raise ContractRevisionPayloadError(
            "number_non_finite", f"{name} must be finite, got {value}"
        )
    _decimal_storage_guard(value, name)
    return value


def _optional_finite_decimal(value: object, name: str) -> Decimal | None:
    """Return ``None`` for an absent optional value, else one exact finite Decimal."""

    if value is None:
        return None
    return _finite_decimal(value, name)


def _lag_days(value: object, name: str) -> int:
    """Return one whole-day lag count; refuse bools, floats and other types."""

    if isinstance(value, bool) or not isinstance(value, int):
        raise ContractRevisionPayloadError(
            "lag_days_not_int",
            f"{name} must be a whole number of days, got {type(value).__name__}",
        )
    return value


def _required_lag_days(value: object, name: str) -> int:
    """Return one required whole-day lag, refusing ``None`` as missing."""

    if value is None:
        raise ContractRevisionPayloadError(
            "lag_days_missing",
            f"{name} is required by the current contract schema but is missing",
        )
    return _lag_days(value, name)


def _frozen_text_tuple(value: object, name: str) -> tuple[str, ...]:
    """Copy a sequence of strings into a fresh tuple without altering entries.

    Raises:
        ContractRevisionPayloadError: When the value is not a non-string
            sequence or contains a non-string entry.
    """

    if isinstance(value, str | bytes) or not isinstance(value, Sequence):
        raise ContractRevisionPayloadError(
            "text_list_not_sequence",
            f"{name} must be a sequence of strings, got {type(value).__name__}",
        )
    items: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str):
            raise ContractRevisionPayloadError(
                "text_list_item_not_string",
                f"{name}[{index}] must be str, got {type(item).__name__}",
            )
        items.append(item)
    return tuple(items)


def _required_text_list(value: object, name: str) -> tuple[str, ...]:
    """Return one required ordered string list, refusing ``None`` as missing."""

    if value is None:
        raise ContractRevisionPayloadError(
            "list_field_missing",
            f"{name} is required by the current contract schema but is missing",
        )
    return _frozen_text_tuple(value, name)


def _plain_decimal_text(value: Decimal, name: str) -> str:
    """Serialize one finite decimal in exact plain notation, memory-safely.

    ``format(value, "f")`` is exact (no rounding) and independent of the ambient
    decimal context; unlike ``str(Decimal)`` it never uses exponent notation, so
    a canonical document reads the same to any parser. The storage guard runs
    first, so formatting a pathological value cannot allocate unbounded memory.

    Raises:
        ContractRevisionPayloadError: When the value is not finite or exceeds
            the storage guards.
    """

    if not value.is_finite():
        raise ContractRevisionPayloadError(
            "number_non_finite", f"{name} must be finite, got {value}"
        )
    _decimal_storage_guard(value, name)
    return format(value, "f")


def _decimal_text(value: Decimal | None, name: str) -> str | None:
    """Serialize one optional value as an exact plain-notation decimal string."""

    if value is None:
        return None
    return _plain_decimal_text(value, name)


@dataclass(frozen=True, slots=True)
class ContractDisplayMetadata:
    """Display side of one legacy contract: never part of the economic hash.

    Attributes:
        contract_name: Operator-visible contract name.
        operator_notes: The stored notes text exactly as read (JSON text or free
            text), or ``None`` when the notes column is empty. Document
            references, tags and operator prose currently live inside this text;
            they are display metadata and never change the economic snapshot.
    """

    contract_name: str
    operator_notes: str | None = None

    def __post_init__(self) -> None:
        """Validate the display fields without altering them."""

        _required_text(self.contract_name, "contract_name")
        _optional_text(self.operator_notes, "operator_notes")


@dataclass(frozen=True, slots=True)
class UpstreamContractEconomicSnapshot:
    """Immutable economic content of one upstream contract revision (S1a).

    Every field is economic or structural contract content. Display metadata is
    deliberately absent (:class:`ContractDisplayMetadata`), and so are dates:
    this schema version records no effective/recorded validity and no payment
    terms (``payment_terms`` is always ``null``), because none may be inferred
    from the legacy lag integers.

    Attributes:
        contract_id: Stable upstream contract identity (the existing
            ``upstream_resource_contracts.contract_id``).
        resource_type: Resource type classification; it determines the delivery
            mode when the resource pool is composed.
        delivery_point_name: Delivery point of the contract.
        gas_year: Gas year the contract is captured for.
        delivery_quantity_mwh_per_day: Daily delivery quantity (exact decimal).
        contract_price_gbp_mwh: All-in contract price (exact decimal).
        settlement_frequency: Settlement frequency tag as recorded.
        upstream_payment_lag_days: Legacy upstream payment lag in whole days,
            captured verbatim. It is *not* a payment term, date rule, calendar
            or day count and must never be converted into a date here.
        screen_sale_cash_lag_days: Legacy screen-sale cash lag in whole days,
            captured verbatim with the same non-claim.
        delivery_tolerance_pct: Delivery tolerance percentage.
        nomination_tolerance_pct: Nomination tolerance percentage.
        annual_financing_rate_pct: Annual financing rate percentage used by the
            legacy early-cash allowance.
        allowed_exit_points: Ordered allowed exit points; order is preserved.
        eligible_sale_modes: Ordered eligible sale modes; order is preserved.
        tolerance_risk_allowance_gbp_mwh: Optional tolerance risk allowance;
            ``None`` means not recorded, never ``0``.
        owned_entry_capacity_mwh_per_day: Optional owned entry capacity;
            ``None`` means not recorded, never ``0``.
        owned_exit_capacity_mwh_per_day: Optional owned exit capacity; ``None``
            means not recorded, never ``0``.
        variable_cost_gbp_mwh: Optional variable cost, captured from the legacy
            structured notes when present; ``None`` means unknown, never ``0``.
        regas_fee_gbp_mwh: Optional regas fee, same null-not-zero rule.
        fuel_loss_allowance_pct: Optional fuel-loss allowance, same rule.
        numeric_source_precision: Provenance label for the numeric
            representation of the decimals in this snapshot (see
            ``SOURCE_PRECISION_*``); ``legacy_float64`` labels the legacy
            capture ceiling, not a per-value type check.
        mapping_issues: Ordered stable codes describing how the legacy mapping
            had to qualify this record (for example unparseable notes).
        schema_version: Fixed payload schema version, included in the hash.
        payment_terms: Always ``None`` in this schema version: explicit
            unavailability, not an omitted value.
    """

    contract_id: str
    resource_type: str
    delivery_point_name: str
    gas_year: str
    delivery_quantity_mwh_per_day: Decimal
    contract_price_gbp_mwh: Decimal
    settlement_frequency: str
    upstream_payment_lag_days: int
    screen_sale_cash_lag_days: int
    delivery_tolerance_pct: Decimal
    nomination_tolerance_pct: Decimal
    annual_financing_rate_pct: Decimal
    allowed_exit_points: tuple[str, ...]
    eligible_sale_modes: tuple[str, ...]
    tolerance_risk_allowance_gbp_mwh: Decimal | None = None
    owned_entry_capacity_mwh_per_day: Decimal | None = None
    owned_exit_capacity_mwh_per_day: Decimal | None = None
    variable_cost_gbp_mwh: Decimal | None = None
    regas_fee_gbp_mwh: Decimal | None = None
    fuel_loss_allowance_pct: Decimal | None = None
    numeric_source_precision: str = SOURCE_PRECISION_EXACT_DECIMAL
    mapping_issues: tuple[str, ...] = ()
    schema_version: str = field(init=False, default=CONTRACT_REVISION_SCHEMA_VERSION)
    payment_terms: None = field(init=False, default=None)

    def __post_init__(self) -> None:
        """Validate every field and deep-freeze the sequence fields.

        Raises:
            ContractRevisionPayloadError: When a required field is missing, a
                numeric value is not an exact finite ``Decimal`` (bools and
                floats included), a lag is not a whole number, a list entry is
                not a string, the schema version or source precision is
                unknown, or payment terms were supplied.
        """

        for name in _TEXT_FIELD_NAMES:
            _required_text(getattr(self, name), name)
        for name in _REQUIRED_DECIMAL_FIELDS:
            if getattr(self, name) is None:
                raise ContractRevisionPayloadError(
                    "number_field_missing", f"{name} is required and must not be None"
                )
            _finite_decimal(getattr(self, name), name)
        for name in _OPTIONAL_DECIMAL_FIELDS:
            _optional_finite_decimal(getattr(self, name), name)
        for name in _LAG_FIELD_NAMES:
            _lag_days(getattr(self, name), name)
        for name in _LIST_FIELD_NAMES:
            object.__setattr__(
                self, name, _frozen_text_tuple(getattr(self, name), name)
            )
        object.__setattr__(
            self,
            "mapping_issues",
            _frozen_text_tuple(self.mapping_issues, "mapping_issues"),
        )
        precision = self.numeric_source_precision
        if not isinstance(precision, str) or precision not in _REVIEWED_SOURCE_PRECISIONS:
            raise ContractRevisionPayloadError(
                "source_precision_unknown",
                f"numeric_source_precision must be one of "
                f"{sorted(_REVIEWED_SOURCE_PRECISIONS)}, got {precision!r}",
            )
        if self.schema_version != CONTRACT_REVISION_SCHEMA_VERSION:
            raise ContractRevisionPayloadError(
                "schema_version_mismatch",
                f"schema_version is fixed at {CONTRACT_REVISION_SCHEMA_VERSION!r}"
                " for this module",
            )
        if self.payment_terms is not None:
            raise ContractRevisionPayloadError(
                "payment_terms_present",
                "payment_terms is always None in this schema version; terms"
                " arrive in a later reviewed slice",
            )

    def canonical_document(self) -> dict[str, object]:
        """Return the canonical, JSON-ready body of this snapshot.

        Every ``Decimal`` becomes an exact decimal string, lists keep their
        recorded order, and the schema version and ``payment_terms: null`` are
        always present. The returned dict and its lists are fresh copies.

        Returns:
            A JSON-ready document whose key set is fixed by this schema version.
        """

        document: dict[str, object] = {
            "schema_version": self.schema_version,
            "contract_id": self.contract_id,
            "resource_type": self.resource_type,
            "delivery_point_name": self.delivery_point_name,
            "gas_year": self.gas_year,
            "settlement_frequency": self.settlement_frequency,
            "upstream_payment_lag_days": self.upstream_payment_lag_days,
            "screen_sale_cash_lag_days": self.screen_sale_cash_lag_days,
            "allowed_exit_points": list(self.allowed_exit_points),
            "eligible_sale_modes": list(self.eligible_sale_modes),
            "numeric_source_precision": self.numeric_source_precision,
            "mapping_issues": list(self.mapping_issues),
            "payment_terms": None,
        }
        for name in _DECIMAL_FIELD_NAMES:
            document[name] = _decimal_text(getattr(self, name), name)
        return document

    def canonical_json(self) -> str:
        """Return the canonical JSON text hashed by :meth:`content_hash`."""

        return json.dumps(
            self.canonical_document(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )

    def content_hash(self) -> str:
        """Return ``sha256:<hex>`` over the canonical JSON of this snapshot.

        The hash covers the recorded economic content — schema version, stable
        contract identity, every captured field, numeric source precision and
        mapping issues — and deliberately excludes display metadata. It is
        independent of payload key order and of the ambient decimal context,
        and it is an integrity/identity check for an immutable revision, never
        a signature.
        """

        digest = hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()
        return f"sha256:{digest}"

    @classmethod
    def from_canonical_document(cls, document: Mapping[str, object]) -> Self:
        """Rebuild a snapshot from a canonical document (strict decode).

        Strict so a persisted revision cannot be silently half-read: the field
        set must match exactly, decimal fields must be exact strings (never
        JSON numbers), list entries must be strings, lags must be integers and
        ``payment_terms`` must be null.

        Args:
            document: A document produced by :meth:`canonical_document` (or the
                parsed form of :meth:`canonical_json`).

        Returns:
            The rebuilt snapshot.

        Raises:
            ContractRevisionPayloadError: When the document is not a valid
                canonical snapshot of this schema version.
        """

        if not isinstance(document, Mapping):
            raise ContractRevisionPayloadError(
                "canonical_not_mapping",
                f"document must be a mapping, got {type(document).__name__}",
            )
        keys = set(document)
        if keys != _CANONICAL_DOCUMENT_FIELDS:
            missing = sorted(str(key) for key in _CANONICAL_DOCUMENT_FIELDS - keys)
            unexpected = sorted(str(key) for key in keys - _CANONICAL_DOCUMENT_FIELDS)
            raise ContractRevisionPayloadError(
                "canonical_field_set_mismatch",
                f"missing={missing} unexpected={unexpected}",
            )
        version = document["schema_version"]
        if version != CONTRACT_REVISION_SCHEMA_VERSION:
            raise ContractRevisionPayloadError(
                "canonical_schema_version_mismatch",
                f"document schema_version is {version!r}, expected"
                f" {CONTRACT_REVISION_SCHEMA_VERSION!r}",
            )
        if document["payment_terms"] is not None:
            raise ContractRevisionPayloadError(
                "canonical_payment_terms_present",
                "canonical payment_terms must be null in this schema version",
            )
        numbers = {
            name: _canonical_decimal(document[name], name)
            for name in _DECIMAL_FIELD_NAMES
        }
        lags: dict[str, int] = {}
        for name in _LAG_FIELD_NAMES:
            value = document[name]
            if isinstance(value, bool) or not isinstance(value, int):
                raise ContractRevisionPayloadError(
                    "canonical_lag_not_int",
                    f"{name} must be a JSON integer, got {type(value).__name__}",
                )
            lags[name] = value
        precision = document["numeric_source_precision"]
        if not isinstance(precision, str) or precision not in _REVIEWED_SOURCE_PRECISIONS:
            raise ContractRevisionPayloadError(
                "canonical_source_precision_unknown",
                f"numeric_source_precision is {precision!r}",
            )
        return cls(
            contract_id=_required_text(document["contract_id"], "contract_id"),
            resource_type=_required_text(document["resource_type"], "resource_type"),
            delivery_point_name=_required_text(
                document["delivery_point_name"], "delivery_point_name"
            ),
            gas_year=_required_text(document["gas_year"], "gas_year"),
            settlement_frequency=_required_text(
                document["settlement_frequency"], "settlement_frequency"
            ),
            allowed_exit_points=_frozen_text_tuple(
                document["allowed_exit_points"], "allowed_exit_points"
            ),
            eligible_sale_modes=_frozen_text_tuple(
                document["eligible_sale_modes"], "eligible_sale_modes"
            ),
            mapping_issues=_frozen_text_tuple(
                document["mapping_issues"], "mapping_issues"
            ),
            numeric_source_precision=precision,
            **numbers,
            **lags,
        )


def _canonical_decimal(value: object, name: str) -> Decimal | None:
    """Decode one canonical decimal field: exact plain-notation string or ``null``.

    The string must equal the text this module serializes. Whitespace padding,
    underscores, an explicit plus sign and exponent notation are non-canonical
    spellings and are refused, so decoding is a true round trip of the exact
    ``format(parsed, "f")`` output rather than a loose parse.
    """

    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, str):
        raise ContractRevisionPayloadError(
            "canonical_decimal_not_string",
            f"{name} must be an exact decimal string or null, got"
            f" {type(value).__name__}",
        )
    if not value:
        raise ContractRevisionPayloadError(
            "canonical_decimal_not_string", f"{name} must not be an empty decimal string"
        )
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise ContractRevisionPayloadError(
            "canonical_decimal_invalid",
            f"{name} text {value!r} is not a decimal number",
        ) from exc
    if not parsed.is_finite():
        raise ContractRevisionPayloadError(
            "number_non_finite", f"{name} text {value!r} is not finite"
        )
    canonical = _plain_decimal_text(parsed, name)
    if canonical != value:
        raise ContractRevisionPayloadError(
            CANONICAL_DECIMAL_NOT_CANONICAL,
            f"{name} text {value!r} is not the canonical plain-notation"
            " spelling; whitespace, underscores, a plus sign and exponent"
            " notation are not accepted, and the text must equal what"
            " serialization produces",
        )
    return parsed


def _legacy_decimal(value: object, name: str) -> Decimal:
    """Convert one legacy stored numeric into an exact ``Decimal``.

    This is the single place where a legacy binary ``float`` becomes a
    ``Decimal``: it uses the shortest round-trip decimal string (``str(value)``),
    which preserves the recorded value but cannot recover the original typed
    decimal precision (``Decimal(0.1) != Decimal("0.1")``). Ints and exact
    decimal strings convert without loss; ``bool``, non-finite and unsupported
    types refuse instead of being coerced.
    """

    if isinstance(value, bool):
        raise ContractRevisionPayloadError(
            "number_bool_rejected", f"{name} is a bool; booleans are never numbers here"
        )
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ContractRevisionPayloadError(
                "number_non_finite", f"{name} is {value!r} and cannot be captured exactly"
            )
        return Decimal(str(value))
    if isinstance(value, str):
        try:
            parsed = Decimal(value.strip())
        except InvalidOperation as exc:
            raise ContractRevisionPayloadError(
                "number_text_invalid", f"{name} text {value!r} is not a decimal number"
            ) from exc
        if not parsed.is_finite():
            raise ContractRevisionPayloadError(
                "number_non_finite", f"{name} text {value!r} is not finite"
            )
        return parsed
    raise ContractRevisionPayloadError(
        "number_unsupported_type",
        f"{name} has unsupported type {type(value).__name__}",
    )


def _legacy_optional_decimal(value: object, name: str) -> Decimal | None:
    """Return an exact Decimal for a present legacy value, or ``None`` when absent."""

    if value is None:
        return None
    return _legacy_decimal(value, name)


def _legacy_notes(
    value: object,
) -> tuple[str | None, Mapping[str, object] | None, str | None]:
    """Split a legacy notes value into display text and structured JSON object.

    Returns:
        ``(operator_notes_text, structured_notes_or_None, issue_code_or_None)``.
        A non-empty value that is not a JSON object yields an explicit issue
        instead of an empty dict, so structured costs are never silently erased.
    """

    if value is None:
        return None, None, None
    if isinstance(value, Mapping):
        # Synthetic mapping input (the runtime column is Text): render a
        # display-only canonical text; economics are read from the mapping.
        text = json.dumps(
            dict(value), sort_keys=True, ensure_ascii=False, default=str
        )
        return text, value, None
    if isinstance(value, str):
        if not value.strip():
            return None, None, None
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return value, None, LEGACY_NOTES_NOT_STRUCTURED
        if not isinstance(parsed, dict):
            return value, None, LEGACY_NOTES_NOT_STRUCTURED
        return value, parsed, None
    return None, None, LEGACY_NOTES_NOT_STRUCTURED


def _legacy_structured_number(
    contract: Mapping[str, object],
    structured_notes: Mapping[str, object] | None,
    name: str,
    issues: list[str],
) -> Decimal | None:
    """Resolve one structured notes cost with the current parser's precedence.

    The top-level payload field wins (matching
    ``application/resource_pool.py::portfolio_resource_from_contract``); when a
    *different* value also sits in the notes JSON, the conflict is recorded as
    ``LEGACY_STRUCTURED_VALUE_CONFLICT`` rather than silently discarded.
    """

    from_payload = _legacy_optional_decimal(contract.get(name), name)
    from_notes = (
        _legacy_optional_decimal(structured_notes.get(name), f"notes.{name}")
        if structured_notes is not None
        else None
    )
    if from_payload is not None and from_notes is not None and from_payload != from_notes:
        issues.append(LEGACY_STRUCTURED_VALUE_CONFLICT)
    return from_payload if from_payload is not None else from_notes


@dataclass(frozen=True, slots=True)
class LegacyContractSnapshot:
    """One legacy contract split into display metadata and economic content.

    Attributes:
        display_metadata: What a desk sees; never part of the economic hash.
        economic_snapshot: Immutable economic content for the future revision.
    """

    display_metadata: ContractDisplayMetadata
    economic_snapshot: UpstreamContractEconomicSnapshot


def map_legacy_contract_payload(contract: Mapping[str, object]) -> LegacyContractSnapshot:
    """Map one current upstream-contract payload into its two parts.

    Accepts the payload shapes the runtime already produces: the repository read
    payload (structured notes costs merged to the top level) and a stored record
    whose ``notes`` text still carries the costs, with the current parser's
    precedence (top-level field first, then notes). The mapping is strict and
    non-guessing:

    * required fields of the current (NOT NULL) contract schema must be present
      and well-typed, or the mapping refuses;
    * optional fields and absent structured-note costs stay ``None``, never
      ``0`` (the legacy optimizer's absent-is-zero behaviour is untouched);
    * ``bool``, non-finite and unparseable numeric values refuse instead of
      being coerced or dropped;
    * non-empty notes that are not a JSON object do not erase costs: costs stay
      ``None`` and ``LEGACY_NOTES_NOT_STRUCTURED`` is recorded, so an explicit
      top-level cost can still be captured;
    * the snapshot is labelled ``legacy_float64``: that is the legacy capture
      path's precision ceiling (a value stored as a binary float cannot be
      recovered exactly), not a claim that every value was literally a float —
      legacy ints and exact decimal strings convert losslessly;
    * lists keep their recorded order and are copied into fresh tuples.

    The legacy row's ``updated_at_utc`` is deliberately not captured: it is the
    last row update time, not migration time, and it says nothing about when
    the economics applied. A capture time belongs to future persistence and the
    historic validity of the values is unknown, so this schema version records
    no dates at all.

    Args:
        contract: Legacy contract payload mapping (repository read payload or
            stored record shape).

    Returns:
        The display metadata and the immutable economic snapshot.

    Raises:
        ContractRevisionPayloadError: When the payload is not a mapping or a
            required field is missing, blank, of the wrong type, a bool or a
            non-finite number.
    """

    if not isinstance(contract, Mapping):
        raise ContractRevisionPayloadError(
            "payload_not_mapping",
            f"legacy contract payload must be a mapping, got {type(contract).__name__}",
        )

    notes_text, structured_notes, notes_issue = _legacy_notes(contract.get("notes"))
    issues: list[str] = []
    if notes_issue is not None:
        issues.append(notes_issue)

    display_metadata = ContractDisplayMetadata(
        contract_name=_required_text(contract.get("contract_name"), "contract_name"),
        operator_notes=notes_text,
    )

    numbers: dict[str, Decimal | None] = {}
    for name in _REQUIRED_DECIMAL_FIELDS:
        if name not in contract or contract[name] is None:
            raise ContractRevisionPayloadError(
                "number_field_missing",
                f"{name} is required by the current contract schema but is missing",
            )
        numbers[name] = _legacy_decimal(contract[name], name)
    for name in _OPTIONAL_COLUMN_DECIMAL_FIELDS:
        numbers[name] = _legacy_optional_decimal(contract.get(name), name)
    for name in _STRUCTURED_ECONOMIC_NOTE_FIELDS:
        numbers[name] = _legacy_structured_number(
            contract, structured_notes, name, issues
        )

    economic_snapshot = UpstreamContractEconomicSnapshot(
        contract_id=_required_text(contract.get("contract_id"), "contract_id"),
        resource_type=_required_text(contract.get("resource_type"), "resource_type"),
        delivery_point_name=_required_text(
            contract.get("delivery_point_name"), "delivery_point_name"
        ),
        gas_year=_required_text(contract.get("gas_year"), "gas_year"),
        settlement_frequency=_required_text(
            contract.get("settlement_frequency"), "settlement_frequency"
        ),
        allowed_exit_points=_required_text_list(
            contract.get("allowed_exit_points"), "allowed_exit_points"
        ),
        eligible_sale_modes=_required_text_list(
            contract.get("eligible_sale_modes"), "eligible_sale_modes"
        ),
        upstream_payment_lag_days=_required_lag_days(
            contract.get("upstream_payment_lag_days"), "upstream_payment_lag_days"
        ),
        screen_sale_cash_lag_days=_required_lag_days(
            contract.get("screen_sale_cash_lag_days"), "screen_sale_cash_lag_days"
        ),
        numeric_source_precision=SOURCE_PRECISION_LEGACY_FLOAT64,
        mapping_issues=tuple(issues),
        **numbers,
    )
    return LegacyContractSnapshot(
        display_metadata=display_metadata,
        economic_snapshot=economic_snapshot,
    )
