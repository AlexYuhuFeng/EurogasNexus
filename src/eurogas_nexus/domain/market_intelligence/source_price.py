"""Exact source-price authority for normalized market observations.

The EEX TTF NGP adapter retains the operator-published decimal text in
``metadata_json.index_value_exact`` and ``metadata_json.index_volume_mwh_exact``.
The persisted ``market_observations.price`` column is a Float, so a downstream
consumer that reads only that column sees the rounded binary value. This module
validates the retained text once and exposes a ``Decimal`` before any consumer
does arithmetic.

Boundaries:

- only a row whose own source identity *and* its metadata identity name the
  canonical EEX TTF NGP dataset can claim an exact source decimal;
- the exact text and the raw source text must both be plain, finite, bounded
  decimals and must agree numerically; the canonical float must equal
  ``float(exact)``;
- the exact string is returned verbatim as evidence. A float is never
  stringified and called exact;
- signed index values are valid (published indices can be negative);
- a non-EEX row keeps the existing float-only path and is explicitly labelled
  legacy provenance;
- the result is a volume-weighted reference index, never a bid/ask or an
  executable quote. This module does not read or change entitlement, time
  contracts, gas-day calendars or source rights.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

SOURCE_SYSTEM = "EEX"
SOURCE_REFERENCE = "eex-ttf-ngp-15-mins"
SOURCE_DATASET = "ttf-ngp-15min"
INDEX_NAME = "NGP"
UNIT = "EUR/MWh"
CURRENCY = "EUR"

EXACT_PRICE_KEY = "index_value_exact"
RAW_PRICE_KEY = "index_value_raw"
EXACT_VOLUME_KEY = "index_volume_mwh_exact"
RAW_VOLUME_KEY = "index_volume_raw"

STATUS_EXACT = "exact"
STATUS_LEGACY_FLOAT = "legacy_float"
STATUS_MISSING = "missing"
STATUS_INVALID = "invalid"

PROVENANCE_EXACT = "eex_ngp_exact_source_decimal"
PROVENANCE_LEGACY = "legacy_float_approximation"
PROVENANCE_INVALID = "unverified_float_claimed_exact_rejected"

FLOAT_PROVENANCE_EXACT = "canonical_float_of_validated_exact_decimal"
FLOAT_PROVENANCE_LEGACY = "legacy_float_approximation"
FLOAT_PROVENANCE_MISSING = "legacy_float_claimed_exact_missing"
FLOAT_PROVENANCE_INVALID = "unverified_float_claimed_exact_rejected"

PRICE_SEMANTICS_EXACT = "reference_index_never_an_executable_bid_or_ask"
PRICE_SEMANTICS_LEGACY = "unclassified_source_value_not_an_executable_quote_claim"

#: A retained exact value is a plain decimal of bounded length. The parser's own
#: canonical Float bound means a mapped EEX row cannot exceed roughly 1e308, but
#: these limits also stop a forged metadata string from becoming an unbounded
#: Decimal allocation or exponent.
MAX_EXACT_DECIMAL_CHARS = 512
MAX_EXACT_COEFFICIENT_DIGITS = 400
MAX_ADJUSTED_EXPONENT = 400
MIN_ADJUSTED_EXPONENT = -400

_PLAIN_DECIMAL = re.compile(r"^[+-]?(?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+)$")
_EXACT_KEYS = (EXACT_PRICE_KEY, RAW_PRICE_KEY, EXACT_VOLUME_KEY, RAW_VOLUME_KEY)


class _Refusal(Exception):
    """Internal: a claimed exact payload failed one validation rule."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class SourcePrice:
    """The resolved source-price evidence for one market observation.

    Attributes:
        status: ``exact``, ``legacy_float``, ``missing`` or ``invalid``.
        source_system: Row-level source system, when supplied.
        source_reference: Row-level source reference, when supplied.
        source_dataset: Metadata dataset, only when the EEX identity was checked.
        price_provenance: Stable description of where the price came from.
        price_float_provenance: Whether the canonical float came from a validated
            exact decimal, a legacy float, a missing claim or a refused claim.
        exact_decimal: Validated exact ``Decimal``, or None.
        exact_text: Retained exact text verbatim, or None.
        raw_text: Retained raw source text verbatim, or None.
        volume_decimal: Validated exact volume ``Decimal``, or None.
        volume_exact_text: Retained exact volume text verbatim, or None.
        volume_raw_text: Retained raw volume text verbatim, or None.
        volume_status: ``valid``, ``missing`` or ``not_applicable``.
        price_semantics: Source semantics (reference index, not a quote).
        executable_quote: ``False`` for a validated exact index, otherwise None.
        issue_code: Stable refusal/missing code, or None for a usable price.
        issue_detail: Bounded human-readable refusal/missing detail, or None.
    """

    status: str
    source_system: str | None
    source_reference: str | None
    source_dataset: str | None
    price_provenance: str
    price_float_provenance: str
    exact_decimal: Decimal | None = None
    exact_text: str | None = None
    raw_text: str | None = None
    volume_decimal: Decimal | None = None
    volume_exact_text: str | None = None
    volume_raw_text: str | None = None
    volume_status: str = "not_applicable"
    price_semantics: str = PRICE_SEMANTICS_LEGACY
    executable_quote: bool | None = None
    issue_code: str | None = None
    issue_detail: str | None = None

    @property
    def is_exact(self) -> bool:
        """Whether this price carries a validated exact source decimal."""

        return self.status == STATUS_EXACT and self.exact_decimal is not None


def resolve_source_price(
    *,
    source_system: str | None,
    source_reference: str | None,
    numeric_price: object,
    metadata: Mapping[str, object] | None,
    unit: str | None = None,
    currency: str | None = None,
) -> SourcePrice:
    """Resolve one observation's exact source price, or an explicit issue.

    Args:
        source_system: Row-level source system (``source_system`` column).
        source_reference: Row-level source reference (``source_reference`` column).
        numeric_price: Canonical numeric price (the Float column value).
        metadata: Stored ``metadata_json`` mapping.
        unit: Row unit, when available; an exact EEX row must still be EUR/MWh.
        currency: Row currency, when available; an exact EEX row must still be EUR.

    Returns:
        A :class:`SourcePrice`. A validated exact value has ``status="exact"`` and
        a ``Decimal`` plus its verbatim text evidence. A non-EEX row is
        ``legacy_float``. An EEX NGP row that claims exact metadata but fails a
        rule is ``invalid`` with a stable ``issue_code`` and no exact decimal;
        an EEX NGP row with no exact metadata is ``missing``. The caller must not
        fall back to the float for a missing or invalid claim without surfacing
        the code.

    Raises:
        No exceptions for malformed source data: every refusal is returned as an
        explicit status and code.
    """

    metadata_map: Mapping[str, object] = metadata if isinstance(metadata, Mapping) else {}
    system = _clean_text(source_system)
    reference = _clean_text(source_reference)
    is_eex_ngp_row = _same_token(system, SOURCE_SYSTEM) and _same_token(
        reference, SOURCE_REFERENCE
    )
    claims_exact = any(key in metadata_map for key in _EXACT_KEYS)

    if not is_eex_ngp_row:
        if claims_exact:
            return _invalid(
                source_system=system,
                source_reference=reference,
                code="exact_source_identity_mismatch",
                detail=(
                    "exact EEX metadata is present, but the row is not the canonical "
                    "EEX TTF NGP source"
                ),
            )
        return SourcePrice(
            status=STATUS_LEGACY_FLOAT,
            source_system=system,
            source_reference=reference,
            source_dataset=None,
            price_provenance=PROVENANCE_LEGACY,
            price_float_provenance=FLOAT_PROVENANCE_LEGACY,
        )

    if not claims_exact:
        return SourcePrice(
            status=STATUS_MISSING,
            source_system=system,
            source_reference=reference,
            source_dataset=_clean_text(metadata_map.get("source_dataset")),
            price_provenance=PROVENANCE_LEGACY,
            price_float_provenance=FLOAT_PROVENANCE_MISSING,
            price_semantics=_metadata_semantics(metadata_map),
            executable_quote=False,
            issue_code="exact_source_price_missing",
            issue_detail=(
                "the EEX TTF NGP row carries no index_value_exact metadata; the "
                "canonical float cannot be treated as an exact source decimal"
            ),
        )

    identity_error = _identity_error(
        metadata_map,
        unit=unit,
        currency=currency,
    )
    if identity_error is not None:
        code, detail = identity_error
        return _invalid(
            source_system=system,
            source_reference=reference,
            dataset=_clean_text(metadata_map.get("source_dataset")),
            code=code,
            detail=detail,
        )

    try:
        exact_text = _required_text(
            metadata_map.get(EXACT_PRICE_KEY),
            field="index_value_exact",
            prefix="exact_decimal",
        )
        exact_decimal = _bounded_decimal(
            exact_text,
            field="index_value_exact",
            prefix="exact_decimal",
        )
        raw_text = _required_text(
            metadata_map.get(RAW_PRICE_KEY),
            field="index_value_raw",
            prefix="exact_raw",
        )
        raw_decimal = _bounded_decimal(
            raw_text,
            field="index_value_raw",
            prefix="exact_raw",
        )
        if raw_decimal != exact_decimal:
            raise _Refusal(
                "exact_raw_mismatch",
                (
                    "index_value_raw and index_value_exact describe different values; "
                    "refusing contradictory exact provenance"
                ),
            )

        volume_exact_text: str | None = None
        volume_raw_text: str | None = None
        volume_decimal: Decimal | None = None
        volume_status = "missing"
        if EXACT_VOLUME_KEY in metadata_map or RAW_VOLUME_KEY in metadata_map:
            volume_exact_text = _required_text(
                metadata_map.get(EXACT_VOLUME_KEY),
                field="index_volume_mwh_exact",
                prefix="exact_volume",
            )
            volume_decimal = _bounded_decimal(
                volume_exact_text,
                field="index_volume_mwh_exact",
                prefix="exact_volume",
            )
            volume_raw_text = _required_text(
                metadata_map.get(RAW_VOLUME_KEY),
                field="index_volume_raw",
                prefix="exact_volume_raw",
            )
            volume_raw_decimal = _bounded_decimal(
                volume_raw_text,
                field="index_volume_raw",
                prefix="exact_volume_raw",
            )
            if volume_raw_decimal != volume_decimal:
                raise _Refusal(
                    "exact_volume_mismatch",
                    (
                        "index_volume_raw and index_volume_mwh_exact describe "
                        "different values; refusing contradictory volume provenance"
                    ),
                )
            if volume_decimal <= 0:
                raise _Refusal(
                    "exact_volume_not_positive",
                    "the retained exact volume is not positive; a priced NGP row "
                    "requires a positive volume",
                )
            volume_status = "valid"

        _validate_numeric_price(numeric_price, exact_decimal)
    except _Refusal as refusal:
        return _invalid(
            source_system=system,
            source_reference=reference,
            dataset=_clean_text(metadata_map.get("source_dataset")),
            code=refusal.code,
            detail=refusal.detail,
        )

    return SourcePrice(
        status=STATUS_EXACT,
        source_system=system,
        source_reference=reference,
        source_dataset=_clean_text(metadata_map.get("source_dataset")),
        price_provenance=PROVENANCE_EXACT,
        price_float_provenance=FLOAT_PROVENANCE_EXACT,
        exact_decimal=exact_decimal,
        exact_text=exact_text,
        raw_text=raw_text,
        volume_decimal=volume_decimal,
        volume_exact_text=volume_exact_text,
        volume_raw_text=volume_raw_text,
        volume_status=volume_status,
        price_semantics=_metadata_semantics(metadata_map),
        executable_quote=False,
    )


def _identity_error(
    metadata: Mapping[str, object],
    *,
    unit: str | None,
    currency: str | None,
) -> tuple[str, str] | None:
    """Check that metadata names the canonical EEX TTF NGP reference index."""

    if not _same_token(metadata.get("source_system"), SOURCE_SYSTEM):
        return (
            "exact_metadata_source_mismatch",
            "metadata source_system does not match the canonical EEX source",
        )
    if not _same_token(metadata.get("source_reference"), SOURCE_REFERENCE):
        return (
            "exact_metadata_reference_mismatch",
            "metadata source_reference does not match the canonical EEX TTF NGP source",
        )
    if not _same_token(metadata.get("source_dataset"), SOURCE_DATASET):
        return (
            "exact_metadata_dataset_mismatch",
            "metadata source_dataset does not match the canonical EEX TTF NGP dataset",
        )
    if not _same_token(metadata.get("index"), INDEX_NAME):
        return (
            "exact_metadata_index_mismatch",
            "metadata index is not the EEX NGP index",
        )
    if not _same_token(metadata.get("contract_type"), "index") or not _same_token(
        metadata.get("price_type"), "index"
    ):
        return (
            "exact_metadata_not_reference_index",
            "metadata does not describe an index contract and price type",
        )
    if metadata.get("executable_quote") is not False:
        return (
            "exact_metadata_executable_quote_claim",
            "metadata does not explicitly deny executable-quote semantics",
        )
    if metadata.get("simulated") is not False:
        return (
            "exact_metadata_simulated_claim",
            "metadata does not explicitly deny simulated-source semantics",
        )
    if unit is not None and not _same_token(unit, UNIT):
        return (
            "exact_unit_mismatch",
            "the row unit is not the EEX NGP source unit EUR/MWh",
        )
    if currency is not None and not _same_token(currency, CURRENCY):
        return (
            "exact_currency_mismatch",
            "the row currency is not the EEX NGP source currency EUR",
        )
    return None


def _validate_numeric_price(numeric_price: object, exact_decimal: Decimal) -> None:
    """Refuse a canonical float that is not the exact source value's float."""

    if isinstance(numeric_price, bool) or not isinstance(numeric_price, int | float):
        raise _Refusal(
            "exact_numeric_price_not_number",
            (
                "the canonical price is not a JSON number; a numeric token or a "
                "string cannot be accepted as exact-decimal evidence"
            ),
        )
    try:
        numeric_float = float(numeric_price)
    except (OverflowError, ValueError) as error:
        raise _Refusal(
            "exact_numeric_price_out_of_float_range",
            "the canonical price cannot be represented as a finite float",
        ) from error
    if not math.isfinite(numeric_float):
        raise _Refusal(
            "exact_numeric_price_not_finite",
            "the canonical price is not finite",
        )
    try:
        exact_float = float(exact_decimal)
    except (OverflowError, ValueError) as error:
        raise _Refusal(
            "exact_decimal_out_of_float_range",
            "the exact decimal cannot be represented as a finite canonical float",
        ) from error
    if not math.isfinite(exact_float):
        raise _Refusal(
            "exact_decimal_out_of_float_range",
            "the exact decimal cannot be represented as a finite canonical float",
        )
    if exact_float != numeric_float:
        raise _Refusal(
            "exact_numeric_price_mismatch",
            (
                "the canonical float price does not equal float(index_value_exact); "
                "refusing mismatched numeric and exact provenance"
            ),
        )


def _bounded_decimal(value: str, *, field: str, prefix: str) -> Decimal:
    """Parse one validated plain-decimal string under explicit bounds."""

    if len(value) > MAX_EXACT_DECIMAL_CHARS:
        raise _Refusal(
            f"{prefix}_too_long",
            (
                f"{field} has {len(value)} characters; the limit is "
                f"{MAX_EXACT_DECIMAL_CHARS}"
            ),
        )
    if _PLAIN_DECIMAL.fullmatch(value) is None:
        raise _Refusal(
            f"{prefix}_not_plain",
            f"{field} {_display(value)} is not a plain decimal",
        )
    try:
        parsed = Decimal(value)
    except InvalidOperation as error:
        raise _Refusal(
            f"{prefix}_not_plain",
            f"{field} {_display(value)} is not a plain decimal",
        ) from error
    if not parsed.is_finite():
        raise _Refusal(
            f"{prefix}_not_finite",
            f"{field} is not finite",
        )
    coefficient_digits = len(parsed.as_tuple().digits)
    if coefficient_digits > MAX_EXACT_COEFFICIENT_DIGITS:
        raise _Refusal(
            f"{prefix}_coefficient_too_large",
            (
                f"{field} has {coefficient_digits} coefficient digits; the limit is "
                f"{MAX_EXACT_COEFFICIENT_DIGITS}"
            ),
        )
    adjusted = parsed.adjusted()
    if adjusted > MAX_ADJUSTED_EXPONENT or adjusted < MIN_ADJUSTED_EXPONENT:
        raise _Refusal(
            f"{prefix}_exponent_out_of_bounds",
            (
                f"{field} has adjusted exponent {adjusted}; the allowed range is "
                f"{MIN_ADJUSTED_EXPONENT}..{MAX_ADJUSTED_EXPONENT}"
            ),
        )
    return parsed


def _invalid(
    *,
    source_system: str | None,
    source_reference: str | None,
    code: str,
    detail: str,
    dataset: str | None = None,
    price_semantics: str = PRICE_SEMANTICS_LEGACY,
) -> SourcePrice:
    """Build an explicit fail-closed result for a claimed exact payload."""

    return SourcePrice(
        status=STATUS_INVALID,
        source_system=source_system,
        source_reference=source_reference,
        source_dataset=dataset,
        price_provenance=PROVENANCE_INVALID,
        price_float_provenance=FLOAT_PROVENANCE_INVALID,
        price_semantics=price_semantics,
        issue_code=code,
        issue_detail=detail,
    )


def _required_text(value: object, *, field: str, prefix: str) -> str:
    """Require a string field, refusing a missing or non-string claim."""

    if not isinstance(value, str):
        raise _Refusal(
            f"{prefix}_not_string",
            f"{field} must be a string; found {type(value).__name__}",
        )
    if not value:
        raise _Refusal(f"{prefix}_empty", f"{field} is empty")
    return value


def _metadata_semantics(metadata: Mapping[str, object]) -> str:
    """Return the source's price semantics, or the conservative fallback."""

    value = metadata.get("price_semantics")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return PRICE_SEMANTICS_EXACT


def _same_token(value: object, expected: str) -> bool:
    """Case/space-insensitive identity comparison for validated metadata."""

    return isinstance(value, str) and value.strip().casefold() == expected.casefold()


def _clean_text(value: object) -> str | None:
    """Trimmed non-empty text, or None."""

    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _display(value: object) -> str:
    """Bound an echoed value so a hostile payload cannot flood an issue detail."""

    text = repr(value)
    return text if len(text) <= 80 else f"{text[:77]}..."
