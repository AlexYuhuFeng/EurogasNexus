"""Explicit payment terms of one upstream contract revision (S2a typed foundation).

S2a of ``docs/engineering/CONTRACT_PAYMENT_INTEGRATION_PLAN.md`` (section 15)
defines a strict, immutable, versioned declaration of what an operator states
about when contract payments fall due, plus its deterministic bounded
canonical JSON roundtrip. The module defines the type only — nothing is
persisted, exposed, rendered, resolved or valued — and the design rationale
lives in the integration plan.

Invariants:

* Terms are operator-supplied evidence, never a market default and never a
  legal conclusion; every item, date specification and calendar reference
  carries a mandatory, non-blank source reference.
* Exactly one date specification per item: ``EXPLICIT_DATE`` (ISO plain date
  plus evidence) or ``ANCHORED_RULE`` (reviewed anchor event, explicit
  non-negative integral offset, offset-day kind and business-day convention).
  No offset, convention or calendar is defaulted and no anchor fact inferred.
* Every item states ``flow_direction`` (``INFLOW``/``OUTFLOW`` from the
  contract-holder/reporting entity's perspective); no sign is inferred from
  ``cash_flow_category`` (a refund can reverse the usual sign), so future
  composition must validate signed amounts against the declared direction.
* ``calendar_reference`` is required when a count or roll needs it, refused
  when nothing does, and no amount, rate, FX, discount or day-count arithmetic
  lives here (it stays the shared dated-cash engine's responsibility).

Canonical replay: compact sorted-key UTF-8 JSON, item order and strings
preserved exactly as supplied. Decoding is the strict inverse and refuses
unknown fields or values, non-canonical spellings, duplicate item ids and
oversized input. Refusals carry stable codes and sanitized details: no
supplied value, field name or object repr is echoed back.

Persistence/API transition (S2b): terms are intended to travel inside an
immutable contract revision. The existing ``upstream-contract-revision/v1``
schema stays byte-identical (``payment_terms`` always null); the reviewed
``upstream-contract-revision/v2`` domain schema now allows this document in the
existing required ``payment_terms`` field (or ``null`` for "not stated";
omission and an empty schedule are invalid), while storage, write-path and
read-path integration remain unimplemented.

The module is pure: standard library plus the reviewed vocabulary and the
shared cash category enum; no I/O, no clock, no randomness.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import ClassVar, NoReturn, Self

from eurogas_nexus.domain.ontology.vocabulary import (
    BusinessDayConvention,
    PaymentAnchorEvent,
    PaymentDateSpecificationKind,
    PaymentFlowDirection,
    PaymentOffsetDayKind,
)
from eurogas_nexus.domain.research.cash_valuation import CashFlowLegCategory

#: Schema version of the canonical payment-terms document.
CONTRACT_PAYMENT_TERMS_SCHEMA_VERSION = "contract-payment-terms/v1"

# Storage guards, not market/legal/accounting rules: they bound one declared
# schedule, one text field and one integer offset.
MAX_PAYMENT_SCHEDULE_ITEMS = 1_000
MAX_PAYMENT_TERMS_TEXT_LENGTH = 2_000
MAX_ANCHOR_OFFSET_DAYS = 36_525

# Exact field sets of the canonical document and of each date shape; no field
# is optional and no extra field is accepted.
_TERMS_FIELDS = frozenset({"schema_version", "quantity_basis_reference", "items"})
_ITEM_FIELDS = frozenset(
    {"item_id", "cash_flow_category", "flow_direction", "source_reference", "date_specification"}
)
_EXPLICIT_DATE_FIELDS = frozenset({"kind", "final_payable_date", "source_reference"})
_ANCHORED_RULE_FIELDS = frozenset(
    {
        "kind", "anchor_event", "anchor_offset_days", "offset_day_kind",
        "business_day_convention", "calendar_reference", "source_reference",
    }
)

# Built-in names that may appear in a refusal detail; any other class name is
# caller data and is replaced by a fixed phrase.
_SAFE_TYPE_NAMES = frozenset(
    {
        "Decimal", "NoneType", "bool", "bytes", "date", "datetime", "dict",
        "float", "int", "list", "set", "str", "tuple",
    }
)


class ContractPaymentTermsError(ValueError):
    """Deterministic refusal to build or decode explicit payment terms.

    ``code`` is the stable machine-readable refusal; ``detail`` is a sanitized
    explanation that never echoes caller-supplied values or field names.
    """

    def __init__(self, code: str, detail: str) -> None:
        """Build the refusal from a stable code and a sanitized detail."""

        self.code = code
        self.detail = detail
        super().__init__(f"{code} ({detail})")


def _refuse(code: str, detail: str) -> NoReturn:
    """Raise one refusal with a stable code and a sanitized detail."""

    raise ContractPaymentTermsError(code, detail)


def _type_label(value: object) -> str:
    """Describe a value's type without echoing an arbitrary class name."""

    name = getattr(type(value), "__name__", "")
    return name if name in _SAFE_TYPE_NAMES else "an unsupported object type"


def _required_reference(value: object, name: str) -> str:
    """Return one non-blank reference/evidence string exactly as supplied."""

    if value is None:
        _refuse("reference_missing", f"{name} is required and must not be None")
    if not isinstance(value, str):
        _refuse("reference_not_string", f"{name} must be text, got {_type_label(value)}")
    if not value.strip():
        _refuse("reference_blank", f"{name} is blank; a declared rule must state its source")
    if len(value) > MAX_PAYMENT_TERMS_TEXT_LENGTH:
        _refuse(
            "reference_storage_bounds_exceeded",
            f"{name} exceeds the storage guard of {MAX_PAYMENT_TERMS_TEXT_LENGTH} characters",
        )
    _require_utf8(value)
    return value


def _required_item_id(value: object) -> str:
    """Return one non-blank item id, preserved exactly as supplied."""

    if value is None:
        _refuse("item_id_missing", "item_id is required and must not be None")
    if not isinstance(value, str):
        _refuse("item_id_not_string", f"item_id must be text, got {_type_label(value)}")
    if not value.strip():
        _refuse("item_id_blank", "item_id must not be blank")
    if len(value) > MAX_PAYMENT_TERMS_TEXT_LENGTH:
        _refuse(
            "item_id_storage_bounds_exceeded",
            f"item_id exceeds the storage guard of {MAX_PAYMENT_TERMS_TEXT_LENGTH} characters",
        )
    _require_utf8(value)
    return value


def _require_utf8(value: str) -> None:
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        _refuse("text_not_utf8", "Text must be encodable as valid UTF-8")


def _plain_date(value: object, name: str) -> date:
    """Return one plain calendar date; a ``datetime`` is refused explicitly."""

    if isinstance(value, datetime):
        _refuse(
            "date_is_datetime",
            f"{name} must be a plain calendar date; a datetime carries a time"
            " of day this schema does not declare",
        )
    if not isinstance(value, date):
        _refuse("date_not_date", f"{name} must be a calendar date, got {_type_label(value)}")
    return value


def _anchor_offset_days(value: object, name: str) -> int:
    """Return one explicit non-negative whole-day offset inside the guard."""

    if isinstance(value, bool) or not isinstance(value, int):
        _refuse("offset_not_int", f"{name} must be whole days, got {_type_label(value)}")
    if value < 0:
        _refuse(
            "offset_negative",
            f"{name} is negative; a declared offset states the anchor event and"
            " the sign explicitly, never an inferred one",
        )
    if value > MAX_ANCHOR_OFFSET_DAYS:
        _refuse(
            "offset_bounds_exceeded",
            f"{name} exceeds the storage guard of {MAX_ANCHOR_OFFSET_DAYS} days",
        )
    return value


def _enum_member(value: object, enum_type: type, name: str):
    """Return one reviewed vocabulary member; refusal code ``<name>_unknown``."""

    if not isinstance(value, enum_type):
        known = ", ".join(sorted(str(member) for member in enum_type))
        _refuse(
            f"{name}_unknown",
            f"{name} must be a {enum_type.__name__} member ({known}),"
            f" got {_type_label(value)}",
        )
    return value


def _validate_calendar_requirement(
    offset_day_kind: PaymentOffsetDayKind,
    business_day_convention: BusinessDayConvention,
    calendar_reference: object,
) -> None:
    """Require a calendar when a count or roll needs it; refuse an unused one."""

    needs_calendar = (
        offset_day_kind is PaymentOffsetDayKind.BUSINESS_DAYS
        or business_day_convention is not BusinessDayConvention.NONE
    )
    if needs_calendar:
        _required_reference(calendar_reference, "calendar_reference")
        return
    if calendar_reference is not None:
        _refuse(
            "calendar_reference_not_applicable",
            "calendar_reference is declared but neither a business-day count nor"
            " a roll convention uses it; remove it or declare the rule that needs it",
        )


@dataclass(frozen=True, slots=True)
class ExplicitPaymentDate:
    """A final payable date stated by the operator, with its evidence.

    ``final_payable_date`` is a plain calendar date serialized as
    ``YYYY-MM-DD``; ``source_reference`` is the mandatory evidence naming it.
    """

    final_payable_date: date
    source_reference: str

    kind: ClassVar[PaymentDateSpecificationKind] = PaymentDateSpecificationKind.EXPLICIT_DATE

    def __post_init__(self) -> None:
        """Validate the stated date and its mandatory evidence."""

        _plain_date(self.final_payable_date, "final_payable_date")
        _required_reference(self.source_reference, "source_reference")


@dataclass(frozen=True, slots=True)
class AnchoredPaymentRule:
    """A declared payment-date rule anchored to an explicit reviewed event.

    The rule states an anchor event and an explicit offset; it never states,
    computes or implies the anchor date itself. ``calendar_reference`` is
    required when the offset counts business days or a roll convention is
    declared, and ``None`` otherwise.
    """

    anchor_event: PaymentAnchorEvent
    anchor_offset_days: int
    offset_day_kind: PaymentOffsetDayKind
    business_day_convention: BusinessDayConvention
    source_reference: str
    calendar_reference: str | None = None

    kind: ClassVar[PaymentDateSpecificationKind] = PaymentDateSpecificationKind.ANCHORED_RULE

    def __post_init__(self) -> None:
        """Validate the explicit rule, its evidence and its calendar needs."""

        _enum_member(self.anchor_event, PaymentAnchorEvent, "anchor_event")
        _anchor_offset_days(self.anchor_offset_days, "anchor_offset_days")
        _enum_member(self.offset_day_kind, PaymentOffsetDayKind, "offset_day_kind")
        _enum_member(
            self.business_day_convention, BusinessDayConvention, "business_day_convention"
        )
        _required_reference(self.source_reference, "source_reference")
        _validate_calendar_requirement(
            self.offset_day_kind,
            self.business_day_convention,
            self.calendar_reference,
        )


#: Exactly-one-shape union a schedule item declares.
PaymentDateSpecification = ExplicitPaymentDate | AnchoredPaymentRule


@dataclass(frozen=True, slots=True)
class PaymentScheduleItem:
    """One declared payable line of a payment schedule.

    ``item_id`` is stable per schedule (duplicates are refused);
    ``cash_flow_category`` is the shared frozen cash-flow category;
    ``flow_direction`` states INFLOW/OUTFLOW from the contract-holder /
    reporting entity's perspective — mandatory, never inferred from the
    category (a refund can reverse the usual sign), and future composition
    must validate signed amounts against it; ``source_reference`` is mandatory
    evidence; ``date_specification`` is exactly one of
    :class:`ExplicitPaymentDate` or :class:`AnchoredPaymentRule`.
    """

    item_id: str
    cash_flow_category: CashFlowLegCategory
    flow_direction: PaymentFlowDirection
    source_reference: str
    date_specification: PaymentDateSpecification

    def __post_init__(self) -> None:
        """Validate identity, category, direction, evidence and date shape."""

        _required_item_id(self.item_id)
        _enum_member(self.cash_flow_category, CashFlowLegCategory, "cash_flow_category")
        _enum_member(self.flow_direction, PaymentFlowDirection, "flow_direction")
        _required_reference(self.source_reference, "source_reference")
        if not isinstance(self.date_specification, (ExplicitPaymentDate, AnchoredPaymentRule)):
            _refuse(
                "date_specification_not_recognized",
                "date_specification must be an ExplicitPaymentDate or an"
                " AnchoredPaymentRule; exactly one shape is declared",
            )

    def canonical_document(self) -> dict[str, object]:
        """Return the canonical, JSON-ready body of this item (fresh copies)."""

        return {
            "item_id": self.item_id,
            "cash_flow_category": str(self.cash_flow_category),
            "flow_direction": str(self.flow_direction),
            "source_reference": self.source_reference,
            "date_specification": _specification_document(self.date_specification),
        }


@dataclass(frozen=True, slots=True)
class ContractPaymentTerms:
    """Operator-declared payment terms of one upstream contract revision.

    ``quantity_basis_reference`` is declared, never assumed; ``items`` are the
    declared payable lines in meaningful order (an empty schedule is refused:
    absent terms are represented by missing terms, never by an empty
    declaration); ``schema_version`` is fixed to this module's version.
    """

    quantity_basis_reference: str
    items: tuple[PaymentScheduleItem, ...]
    schema_version: str = CONTRACT_PAYMENT_TERMS_SCHEMA_VERSION

    def __post_init__(self) -> None:
        """Validate the schedule and deep-freeze its item sequence."""

        if self.schema_version != CONTRACT_PAYMENT_TERMS_SCHEMA_VERSION:
            _refuse(
                "schema_version_mismatch",
                "schema_version is fixed at"
                f" {CONTRACT_PAYMENT_TERMS_SCHEMA_VERSION} for this module",
            )
        _required_reference(self.quantity_basis_reference, "quantity_basis_reference")
        items = self.items
        if isinstance(items, (str, bytes)) or not isinstance(items, Sequence):
            _refuse(
                "items_not_sequence",
                f"items must be a sequence of PaymentScheduleItem, got {_type_label(items)}",
            )
        materialized = tuple(items)
        if not materialized:
            _refuse(
                "schedule_empty",
                "at least one declared item is required; absent terms are"
                " represented by missing payment terms, not an empty schedule",
            )
        if len(materialized) > MAX_PAYMENT_SCHEDULE_ITEMS:
            _refuse(
                "schedule_bounds_exceeded",
                f"items has {len(materialized)} entries; the guard allows"
                f" {MAX_PAYMENT_SCHEDULE_ITEMS}",
            )
        seen_ids: set[str] = set()
        for position, item in enumerate(materialized):
            if not isinstance(item, PaymentScheduleItem):
                _refuse(
                    "item_not_recognized",
                    f"items[{position}] must be a PaymentScheduleItem, got {_type_label(item)}",
                )
            if item.item_id in seen_ids:
                _refuse(
                    "item_id_duplicate",
                    f"items[{position}] declares an item_id that was already"
                    " declared; one declared line is counted exactly once",
                )
            seen_ids.add(item.item_id)
        object.__setattr__(self, "items", materialized)

    def canonical_document(self) -> dict[str, object]:
        """Return the canonical, JSON-ready body (order and strings preserved)."""

        return {
            "schema_version": self.schema_version,
            "quantity_basis_reference": self.quantity_basis_reference,
            "items": [item.canonical_document() for item in self.items],
        }

    def canonical_json(self) -> str:
        """Return the canonical JSON text of this schedule (sorted, compact)."""

        return json.dumps(
            self.canonical_document(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )

    @classmethod
    def from_canonical_document(cls, document: Mapping[str, object]) -> Self:
        """Rebuild a schedule from a canonical document (strict decode).

        Exact field sets for the document and for each declared date shape,
        reviewed enum names, JSON integer offsets (never booleans), canonical
        plain ISO date spellings and present evidence, so a stored declaration
        can never be silently half-read.
        """

        if not isinstance(document, Mapping):
            _refuse(
                "canonical_not_mapping",
                f"document must be a mapping, got {_type_label(document)}",
            )
        _check_field_set(document, _TERMS_FIELDS, "canonical")
        version = document["schema_version"]
        if version != CONTRACT_PAYMENT_TERMS_SCHEMA_VERSION:
            _refuse(
                "canonical_schema_version_mismatch",
                "document schema_version is not the version this module declares"
                f" ({CONTRACT_PAYMENT_TERMS_SCHEMA_VERSION})",
            )
        basis = _required_reference(
            document["quantity_basis_reference"], "quantity_basis_reference"
        )
        raw_items = document["items"]
        if isinstance(raw_items, (str, bytes)) or not isinstance(raw_items, Sequence):
            _refuse(
                "canonical_items_not_sequence",
                f"items must be a JSON array of declared items, got {_type_label(raw_items)}",
            )
        if len(raw_items) > MAX_PAYMENT_SCHEDULE_ITEMS:
            _refuse(
                "schedule_bounds_exceeded",
                f"items has {len(raw_items)} entries; the guard allows"
                f" {MAX_PAYMENT_SCHEDULE_ITEMS}",
            )
        items = tuple(_decode_item(entry, position) for position, entry in enumerate(raw_items))
        return cls(quantity_basis_reference=basis, items=items)


def _specification_document(specification: PaymentDateSpecification) -> dict[str, object]:
    """Serialize one date specification with its discriminator and evidence."""

    if isinstance(specification, ExplicitPaymentDate):
        return {
            "kind": str(specification.kind),
            "final_payable_date": specification.final_payable_date.isoformat(),
            "source_reference": specification.source_reference,
        }
    return {
        "kind": str(specification.kind),
        "anchor_event": str(specification.anchor_event),
        "anchor_offset_days": specification.anchor_offset_days,
        "offset_day_kind": str(specification.offset_day_kind),
        "business_day_convention": str(specification.business_day_convention),
        "calendar_reference": specification.calendar_reference,
        "source_reference": specification.source_reference,
    }


def _check_field_set(
    mapping: Mapping[object, object], expected: frozenset[str], label: str
) -> None:
    """Refuse any mapping whose field set is not exactly the schema's.

    Only fixed schema labels and counts appear in the refusal; caller-supplied
    field names are never echoed, and a malformed mapping whose keys cannot be
    collected is refused with the same stable code instead of raising.
    """

    try:
        keys = set(mapping)
    except TypeError as exc:
        raise ContractPaymentTermsError(
            "canonical_field_set_mismatch",
            f"{label} must declare exactly the schema fields {sorted(expected)};"
            " the supplied keys cannot be read as field names",
        ) from exc
    if keys != expected:
        _refuse(
            "canonical_field_set_mismatch",
            f"{label} must declare exactly the schema fields {sorted(expected)};"
            f" missing={len(expected - keys)}, unexpected={len(keys - expected)}",
        )


def _decode_item(entry: object, position: int) -> PaymentScheduleItem:
    """Decode one item mapping with its exact field set and single date shape."""

    where = f"items[{position}]"
    if not isinstance(entry, Mapping):
        _refuse(
            "canonical_item_not_mapping",
            f"{where} must be a JSON object, got {_type_label(entry)}",
        )
    _check_field_set(entry, _ITEM_FIELDS, where)
    return PaymentScheduleItem(
        item_id=_required_item_id(entry["item_id"]),
        cash_flow_category=_decode_enum(
            entry["cash_flow_category"], CashFlowLegCategory, "cash_flow_category", where
        ),
        flow_direction=_decode_enum(
            entry["flow_direction"], PaymentFlowDirection, "flow_direction", where
        ),
        source_reference=_required_reference(
            entry["source_reference"], f"{where}.source_reference"
        ),
        date_specification=_decode_specification(
            entry["date_specification"], f"{where}.date_specification"
        ),
    )


def _decode_specification(specification: object, label: str) -> PaymentDateSpecification:
    """Decode exactly one discriminated date specification shape."""

    if not isinstance(specification, Mapping):
        _refuse(
            "canonical_date_specification_not_mapping",
            f"{label} must be a JSON object, got {_type_label(specification)}",
        )
    if "kind" not in specification:
        _refuse("canonical_kind_missing", f"{label}.kind is required")
    kind = specification["kind"]
    if not isinstance(kind, str) or kind not in {
        member.value for member in PaymentDateSpecificationKind
    }:
        _refuse(
            "canonical_kind_unknown",
            f"{label}.kind must be one of"
            f" {sorted(member.value for member in PaymentDateSpecificationKind)}",
        )
    if kind == PaymentDateSpecificationKind.EXPLICIT_DATE.value:
        _check_field_set(specification, _EXPLICIT_DATE_FIELDS, label)
        return ExplicitPaymentDate(
            final_payable_date=_canonical_iso_date(
                specification["final_payable_date"], f"{label}.final_payable_date"
            ),
            source_reference=_required_reference(
                specification["source_reference"], f"{label}.source_reference"
            ),
        )
    _check_field_set(specification, _ANCHORED_RULE_FIELDS, label)
    calendar = specification["calendar_reference"]
    if calendar is not None:
        calendar = _required_reference(calendar, f"{label}.calendar_reference")
    return AnchoredPaymentRule(
        anchor_event=_decode_enum(
            specification["anchor_event"], PaymentAnchorEvent, "anchor_event", label
        ),
        anchor_offset_days=_decode_offset(
            specification["anchor_offset_days"], f"{label}.anchor_offset_days"
        ),
        offset_day_kind=_decode_enum(
            specification["offset_day_kind"], PaymentOffsetDayKind, "offset_day_kind", label
        ),
        business_day_convention=_decode_enum(
            specification["business_day_convention"],
            BusinessDayConvention,
            "business_day_convention",
            label,
        ),
        source_reference=_required_reference(
            specification["source_reference"], f"{label}.source_reference"
        ),
        calendar_reference=calendar,
    )


def _decode_enum(value: object, enum_type: type, name: str, context: str):
    """Decode one canonical enum name; refusal code ``canonical_<name>_unknown``."""

    label = f"{context}.{name}"
    if not isinstance(value, str):
        _refuse(
            f"canonical_{name}_unknown",
            f"{label} must be a string member of {enum_type.__name__},"
            f" got {_type_label(value)}",
        )
    try:
        return enum_type(value)
    except ValueError as exc:
        known = ", ".join(sorted(str(member) for member in enum_type))
        raise ContractPaymentTermsError(
            f"canonical_{name}_unknown",
            f"{label} must be one of the reviewed {enum_type.__name__} names ({known})",
        ) from exc


def _decode_offset(value: object, label: str) -> int:
    """Decode one canonical whole-day offset; booleans are never integers here."""

    if isinstance(value, bool) or not isinstance(value, int):
        _refuse(
            "canonical_offset_not_int",
            f"{label} must be a JSON integer number of days, got {_type_label(value)}",
        )
    return value


def _canonical_iso_date(value: object, label: str) -> date:
    """Decode one canonical ISO ``YYYY-MM-DD`` plain-date spelling."""

    if not isinstance(value, str):
        _refuse(
            "canonical_date_not_string",
            f"{label} must be an ISO date string, got {_type_label(value)}",
        )
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ContractPaymentTermsError(
            "canonical_date_invalid",
            f"{label} is not a valid calendar date in ISO form",
        ) from exc
    if parsed.isoformat() != value:
        _refuse(
            "canonical_date_not_plain_iso",
            f"{label} must use the canonical YYYY-MM-DD spelling; compact,"
            " padded or datetime spellings are not accepted",
        )
    return parsed
