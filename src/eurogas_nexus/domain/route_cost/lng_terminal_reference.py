"""Versioned LNG terminal-reference contract and offline source comparison.

This module governs *informational* operator-publication facts. It does not grant
terminal access or capacity rights, does not establish technical readiness, and does
not perform energy, volume, FX, hours/day or capacity conversions. It performs no
network, database or environment access; callers supply explicit local JSON or bytes.

The committed manifest is intentionally empty. Researched operator candidates remain
research evidence until a separate structured promotion is reviewed.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from datetime import date, datetime, timedelta
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from types import MappingProxyType
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    ValidationInfo,
    field_validator,
    model_validator,
)

MANIFEST_SCHEMA_VERSION = "eurogas.lng-terminal-reference/1"
MANIFEST_MODEL_VERSION = "lng-terminal-reference-model/1"
EMPTY_MANIFEST_NOTE = (
    "Empty informational reference manifest. Researched operator-publication candidates "
    "await separate structured promotion and review; this file asserts no official fact, "
    "right, booking, technical availability or readiness."
)
MAX_REFERENCE_BYTES = 10 * 1024 * 1024
MAX_CANDIDATE_BYTES = 10 * 1024 * 1024
MAX_QUOTATION_WORDS = 25
MAX_DECIMAL_INTEGER_DIGITS = 18
MAX_DECIMAL_FRACTION_DIGITS = 18

StableId = Annotated[
    str,
    Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"),
]
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_DECIMAL_RE = re.compile(r"^(?:0|[1-9][0-9]*)(?:\.([0-9]+))?$")
_MONEY_PER_ENERGY_RE = re.compile(r"^[A-Z]{3}/MWh$")


class LngReferenceErrorCode(StrEnum):
    """Stable refusal codes; callers may branch on these without parsing prose."""

    MANIFEST_PATH_INVALID = "MANIFEST_PATH_INVALID"
    MANIFEST_NOT_FOUND = "MANIFEST_NOT_FOUND"
    MANIFEST_NOT_A_FILE = "MANIFEST_NOT_A_FILE"
    MANIFEST_TOO_LARGE = "MANIFEST_TOO_LARGE"
    MANIFEST_UTF8_INVALID = "MANIFEST_UTF8_INVALID"
    MANIFEST_BOM_NOT_ALLOWED = "MANIFEST_BOM_NOT_ALLOWED"
    MANIFEST_JSON_INVALID = "MANIFEST_JSON_INVALID"
    MANIFEST_SCHEMA_INVALID = "MANIFEST_SCHEMA_INVALID"
    CANDIDATE_PATH_INVALID = "CANDIDATE_PATH_INVALID"
    CANDIDATE_NOT_FOUND = "CANDIDATE_NOT_FOUND"
    CANDIDATE_NOT_A_FILE = "CANDIDATE_NOT_A_FILE"
    CANDIDATE_TOO_LARGE = "CANDIDATE_TOO_LARGE"
    CANDIDATE_EMPTY = "CANDIDATE_EMPTY"
    CANDIDATE_PAYLOAD_INVALID = "CANDIDATE_PAYLOAD_INVALID"
    UNKNOWN_SOURCE = "UNKNOWN_SOURCE"
    INVALID_SOURCE_ID = "INVALID_SOURCE_ID"
    INVALID_RETRIEVED_AT = "INVALID_RETRIEVED_AT"
    INVALID_SCENARIO_DATE = "INVALID_SCENARIO_DATE"
    INVALID_PARAMETER = "INVALID_PARAMETER"
    INVALID_QUANTITY_BASIS = "INVALID_QUANTITY_BASIS"
    INVALID_TERMINAL_ID = "INVALID_TERMINAL_ID"
    INVALID_SIZE_LIMIT = "INVALID_SIZE_LIMIT"
    CLI_ARGUMENT_INVALID = "CLI_ARGUMENT_INVALID"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class LngTerminalReferenceError(ValueError):
    """A bounded, safe refusal with a stable machine-readable code."""

    def __init__(self, code: LngReferenceErrorCode | str, message: str) -> None:
        self.code = code.value if isinstance(code, LngReferenceErrorCode) else str(code)
        self.message = message
        super().__init__(f"{self.code}: {message}")


class FactReviewStatus(StrEnum):
    """Candidate facts are never scenario-eligible; reviewed facts require provenance."""

    CANDIDATE = "CANDIDATE"
    REVIEWED = "REVIEWED"


class QuantityBasis(StrEnum):
    """Distinct measurement bases. No member is converted into another."""

    LIQUID_LNG_M3_PER_HOUR = "LIQUID_LNG_M3_PER_HOUR"
    ACTUAL_GAS_M3_PER_HOUR = "ACTUAL_GAS_M3_PER_HOUR"
    NORMAL_GAS_NM3_PER_HOUR = "NORMAL_GAS_NM3_PER_HOUR"
    ENERGY_MWH_PER_HOUR = "ENERGY_MWH_PER_HOUR"
    ENERGY_GWH_PER_DAY = "ENERGY_GWH_PER_DAY"
    DURATION_HOURS = "DURATION_HOURS"
    TANK_CAPACITY_PERCENT_PER_DAY = "TANK_CAPACITY_PERCENT_PER_DAY"
    CARGO_ENERGY_PERCENT = "CARGO_ENERGY_PERCENT"
    MONEY_PER_ENERGY = "MONEY_PER_ENERGY"


class FactParameter(StrEnum):
    """Terminal fact parameters with deliberately narrow basis compatibility."""

    VESSEL_UNLOADING_MAX_RATE = "VESSEL_UNLOADING_MAX_RATE"
    VESSEL_UNLOADING_RATE = "VESSEL_UNLOADING_RATE"
    UNLOADING_RATE = "UNLOADING_RATE"
    SENDOUT_CAPACITY = "SENDOUT_CAPACITY"
    MINIMUM_SENDOUT_RATE = "MINIMUM_SENDOUT_RATE"
    REGASIFICATION_CAPACITY = "REGASIFICATION_CAPACITY"
    TANK_EVAPORATION_RATE = "TANK_EVAPORATION_RATE"
    EVAPORATION_RATE = "EVAPORATION_RATE"
    CARGO_ENERGY_LOSS_RATE = "CARGO_ENERGY_LOSS_RATE"
    RETAINED_FUEL_RATE = "RETAINED_FUEL_RATE"
    VESSEL_DISCHARGE_DURATION = "VESSEL_DISCHARGE_DURATION"
    TERMINAL_FEE = "TERMINAL_FEE"


_SENDOUT_BASES = frozenset(
    {
        QuantityBasis.ACTUAL_GAS_M3_PER_HOUR,
        QuantityBasis.NORMAL_GAS_NM3_PER_HOUR,
        QuantityBasis.ENERGY_MWH_PER_HOUR,
        QuantityBasis.ENERGY_GWH_PER_DAY,
    }
)
_ENERGY_RATE_BASES = frozenset(
    {QuantityBasis.ENERGY_MWH_PER_HOUR, QuantityBasis.ENERGY_GWH_PER_DAY}
)
_UNLOADING_BASES = frozenset({QuantityBasis.LIQUID_LNG_M3_PER_HOUR})
_TANK_EVAPORATION_BASES = frozenset({QuantityBasis.TANK_CAPACITY_PERCENT_PER_DAY})
_CARGO_ENERGY_BASES = frozenset({QuantityBasis.CARGO_ENERGY_PERCENT})

PARAMETER_BASIS_COMPATIBILITY: Mapping[FactParameter, frozenset[QuantityBasis]] = (
    MappingProxyType(
        {
            FactParameter.VESSEL_UNLOADING_MAX_RATE: _UNLOADING_BASES,
            FactParameter.VESSEL_UNLOADING_RATE: _UNLOADING_BASES,
            FactParameter.UNLOADING_RATE: _UNLOADING_BASES,
            FactParameter.SENDOUT_CAPACITY: _SENDOUT_BASES,
            FactParameter.MINIMUM_SENDOUT_RATE: _SENDOUT_BASES,
            FactParameter.REGASIFICATION_CAPACITY: _ENERGY_RATE_BASES,
            FactParameter.TANK_EVAPORATION_RATE: _TANK_EVAPORATION_BASES,
            FactParameter.EVAPORATION_RATE: _TANK_EVAPORATION_BASES,
            FactParameter.CARGO_ENERGY_LOSS_RATE: _CARGO_ENERGY_BASES,
            FactParameter.RETAINED_FUEL_RATE: _CARGO_ENERGY_BASES,
            FactParameter.VESSEL_DISCHARGE_DURATION: frozenset(
                {QuantityBasis.DURATION_HOURS}
            ),
            FactParameter.TERMINAL_FEE: frozenset({QuantityBasis.MONEY_PER_ENERGY}),
        }
    )
)

_UNIT_VARIANTS: Mapping[QuantityBasis, frozenset[str]] = MappingProxyType(
    {
        QuantityBasis.LIQUID_LNG_M3_PER_HOUR: frozenset(
            {
                "m3/h",
                "m3/h lng",
                "m3/h of lng",
                "m3/hour",
                "m3/hour lng",
                "m3/hour of lng",
                "m3 per hour lng",
                "m3 per hour of lng",
            }
        ),
        QuantityBasis.ACTUAL_GAS_M3_PER_HOUR: frozenset(
            {
                "m3/h",
                "m3/h actual",
                "m3/h actual gas",
                "m3/h gas",
                "actual m3/h",
                "actual gas m3/h",
                "m3 per hour actual",
                "m3 per hour actual gas",
            }
        ),
        QuantityBasis.NORMAL_GAS_NM3_PER_HOUR: frozenset(
            {
                "nm3/h",
                "nm3/hour",
                "nm3 per hour",
                "m3(n)/h",
                "m3 (n)/h",
                "m3(n)/hour",
                "m3 (n)/hour",
                "normal m3/h",
                "normal m3/hour",
                "normal cubic meters per hour",
                "normal cubic metres per hour",
            }
        ),
        QuantityBasis.ENERGY_MWH_PER_HOUR: frozenset(
            {"mwh/h", "mwh/hour", "mwh per hour"}
        ),
        QuantityBasis.ENERGY_GWH_PER_DAY: frozenset(
            {"gwh/d", "gwh/day", "gwh per day"}
        ),
        QuantityBasis.DURATION_HOURS: frozenset({"h", "hr", "hrs", "hour", "hours"}),
        QuantityBasis.TANK_CAPACITY_PERCENT_PER_DAY: frozenset(
            {
                "%/d",
                "%/day",
                "% per day",
                "% tank capacity/day",
                "% tank capacity per day",
                "% of tank capacity/day",
                "% of tank capacity per day",
                "percent tank capacity per day",
                "percent of tank capacity per day",
            }
        ),
        QuantityBasis.CARGO_ENERGY_PERCENT: frozenset(
            {
                "%",
                "% cargo energy",
                "% of cargo energy",
                "percent cargo energy",
                "percent of cargo energy",
            }
        ),
    }
)


class _ReferenceModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class LngTerminalSource(_ReferenceModel):
    """One captured official publication, not proof of its authenticity or authority."""

    source_id: StableId
    official_url: Annotated[str, Field(min_length=1, max_length=2048)]
    operator: Annotated[str, Field(min_length=1, max_length=256)]
    document_title: Annotated[str, Field(min_length=1, max_length=512)]
    publication_version: Annotated[str, Field(min_length=1, max_length=256)]
    captured_sha256: str
    retrieved_at_utc: datetime
    published_date: date | None = None
    applicability_notes: Annotated[str, Field(min_length=1, max_length=2048)]

    @field_validator("operator", "document_title", "publication_version", "applicability_notes")
    @classmethod
    def _require_source_text(cls, value: str, info: ValidationInfo) -> str:
        return _require_non_blank(value, info.field_name)

    @field_validator("official_url")
    @classmethod
    def _require_official_https_url(cls, value: str) -> str:
        _require_non_blank(value, "official_url")
        if any(character.isspace() for character in value):
            raise ValueError("official_url must not contain whitespace")
        if "?" in value:
            raise ValueError("official_url must not contain a query string")
        if "#" in value:
            raise ValueError("official_url must not contain a fragment")
        try:
            parsed = urlsplit(value)
            hostname = parsed.hostname
        except ValueError as exc:
            raise ValueError("official_url is not a valid URL") from exc
        if parsed.scheme.lower() != "https":
            raise ValueError("official_url must use HTTPS")
        if not parsed.netloc or not hostname:
            raise ValueError("official_url must include a host")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("official_url must not contain credentials")
        return value

    @field_validator("captured_sha256", mode="before")
    @classmethod
    def _require_sha256(cls, value: object) -> str:
        if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
            raise ValueError("captured_sha256 must be 64 lowercase hexadecimal characters")
        return value

    @field_validator("retrieved_at_utc")
    @classmethod
    def _require_retrieved_at_utc(cls, value: datetime) -> datetime:
        return _require_aware_utc(value, "retrieved_at_utc")


class LngTerminalFact(_ReferenceModel):
    """One operator-publication claim with exact value and explicit measurement basis."""

    fact_id: StableId
    terminal_id: StableId
    parameter: FactParameter
    value: Annotated[str, Field(min_length=1, max_length=40)]
    original_value_text: Annotated[str, Field(min_length=1, max_length=256)]
    original_unit: Annotated[str, Field(min_length=1, max_length=128)]
    quantity_basis: QuantityBasis
    quotation: Annotated[str, Field(min_length=1, max_length=512)]
    source_id: StableId
    applicability_notes: Annotated[str, Field(min_length=1, max_length=2048)]
    effective_from: date | None = None
    effective_to: date | None = None
    review_status: FactReviewStatus
    reviewed_by: Annotated[str, Field(min_length=1, max_length=256)] | None = None
    reviewed_at: datetime | None = None

    @field_validator("value", mode="before")
    @classmethod
    def _require_exact_decimal_string(cls, value: object) -> str:
        if type(value) is not str:
            raise ValueError("value must be an exact decimal string, never a float or number")
        match = _DECIMAL_RE.fullmatch(value)
        if match is None:
            raise ValueError(
                "value must be a plain non-negative decimal string without exponent notation"
            )
        integer_part, _, fraction = value.partition(".")
        if len(integer_part) > MAX_DECIMAL_INTEGER_DIGITS:
            raise ValueError("value integer coefficient is too large")
        if fraction and len(fraction) > MAX_DECIMAL_FRACTION_DIGITS:
            raise ValueError("value fractional coefficient is too large")
        return value

    @field_validator(
        "original_value_text",
        "original_unit",
        "quotation",
        "applicability_notes",
    )
    @classmethod
    def _require_fact_text(cls, value: str, info: ValidationInfo) -> str:
        return _require_non_blank(value, info.field_name)

    @field_validator("reviewed_by")
    @classmethod
    def _require_reviewer_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _require_non_blank(value, "reviewed_by")

    @field_validator("reviewed_at")
    @classmethod
    def _require_reviewed_at_utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return _require_aware_utc(value, "reviewed_at")

    @model_validator(mode="after")
    def _validate_fact_contract(self) -> LngTerminalFact:
        allowed_bases = PARAMETER_BASIS_COMPATIBILITY[self.parameter]
        if self.quantity_basis not in allowed_bases:
            raise ValueError(
                f"parameter {self.parameter.value} is incompatible with "
                f"quantity_basis {self.quantity_basis.value}"
            )
        if not _unit_matches_basis(self.original_unit, self.quantity_basis):
            raise ValueError(
                f"original_unit is inconsistent with quantity_basis "
                f"{self.quantity_basis.value}"
            )
        if len(self.quotation.split()) > MAX_QUOTATION_WORDS:
            raise ValueError(
                f"quotation must not exceed {MAX_QUOTATION_WORDS} words per source"
            )
        if self.effective_from is None and self.effective_to is not None:
            raise ValueError("effective_to cannot be set when effective_from is unknown")
        if (
            self.effective_from is not None
            and self.effective_to is not None
            and self.effective_to < self.effective_from
        ):
            raise ValueError("effective_to must not precede effective_from")
        if self.review_status is FactReviewStatus.REVIEWED:
            if self.reviewed_by is None:
                raise ValueError("REVIEWED facts require reviewed_by")
            if self.reviewed_at is None:
                raise ValueError("REVIEWED facts require reviewed_at")
        else:
            if self.reviewed_by is not None or self.reviewed_at is not None:
                raise ValueError("CANDIDATE facts must not carry reviewer metadata")
        return self

    @property
    def has_known_applicability_start(self) -> bool:
        """Whether the effective interval has a declared start.

        An unknown start is not replaced by the source retrieval time. A known start
        with no end remains open-ended.
        """

        return self.effective_from is not None

    def applies_on(self, scenario_date: date) -> bool:
        """Return whether the known effective interval covers ``scenario_date``.

        This returns False when the start is unknown; callers must distinguish that
        state with :meth:`has_known_applicability_start`.
        """

        if self.effective_from is None or scenario_date < self.effective_from:
            return False
        return self.effective_to is None or scenario_date <= self.effective_to


class LngTerminalReferenceManifest(_ReferenceModel):
    """Strict, immutable manifest with explicit schema and model versions."""

    schema_version: Literal["eurogas.lng-terminal-reference/1"]
    model_version: Literal["lng-terminal-reference-model/1"]
    notes: Annotated[str, Field(min_length=1, max_length=4096)]
    sources: tuple[LngTerminalSource, ...]
    facts: tuple[LngTerminalFact, ...]

    @field_validator("notes")
    @classmethod
    def _require_notes(cls, value: str) -> str:
        return _require_non_blank(value, "notes")

    @model_validator(mode="after")
    def _validate_manifest_references(self) -> LngTerminalReferenceManifest:
        source_ids = [source.source_id for source in self.sources]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("duplicate source_id in manifest")
        fact_ids = [fact.fact_id for fact in self.facts]
        if len(fact_ids) != len(set(fact_ids)):
            raise ValueError("duplicate fact_id in manifest")

        source_by_id = {source.source_id: source for source in self.sources}
        quotation_words_by_source: dict[str, int] = {}
        for fact in self.facts:
            source = source_by_id.get(fact.source_id)
            if source is None:
                raise ValueError(f"fact {fact.fact_id} refers to dangling source_id")
            if (
                fact.review_status is FactReviewStatus.REVIEWED
                and fact.reviewed_at is not None
                and fact.reviewed_at < source.retrieved_at_utc
            ):
                raise ValueError(
                    f"fact {fact.fact_id} reviewed_at precedes source retrieval"
                )
            quotation_words_by_source[fact.source_id] = (
                quotation_words_by_source.get(fact.source_id, 0)
                + len(fact.quotation.split())
            )

        for source_id, word_count in quotation_words_by_source.items():
            if word_count > MAX_QUOTATION_WORDS:
                raise ValueError(
                    f"quotations for source {source_id} exceed "
                    f"{MAX_QUOTATION_WORDS} words across the manifest"
                )
        return self


class LngFactLookupStatus(StrEnum):
    """Explicit lookup outcomes; no ambiguous or unknown fact is auto-selected."""

    REVIEWED_FACT_FOUND = "REVIEWED_FACT_FOUND"
    NO_REVIEWED_FACT = "NO_REVIEWED_FACT"
    NO_APPLICABLE_REVIEWED_FACT = "NO_APPLICABLE_REVIEWED_FACT"
    APPLICABILITY_UNKNOWN = "APPLICABILITY_UNKNOWN"
    AMBIGUOUS_REVIEWED_FACTS = "AMBIGUOUS_REVIEWED_FACTS"


class LngFactLookup(_ReferenceModel):
    """Reviewed scenario lookup result, including explicit non-selection states."""

    status: LngFactLookupStatus
    terminal_id: str
    parameter: FactParameter
    quantity_basis: QuantityBasis
    scenario_date: date
    reviewed_facts: tuple[LngTerminalFact, ...]
    applicable_fact_ids: tuple[str, ...]
    unknown_applicability_fact_ids: tuple[str, ...]
    selected_fact: LngTerminalFact | None = None
    warnings: tuple[str, ...] = ()


class SourceChangeStatus(StrEnum):
    """A byte-comparison result; only a review candidate can result from a change."""

    UNCHANGED = "UNCHANGED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class LngTerminalSourceChange(_ReferenceModel):
    """Offline source comparison evidence. This never mutates the manifest."""

    status: SourceChangeStatus
    source_id: str
    official_url: str
    operator: str
    document_title: str
    publication_version: str
    before_sha256: str
    after_sha256: str
    candidate_byte_length: int
    candidate_retrieved_at_utc: datetime
    source_retrieved_at_utc: datetime
    affected_fact_ids: tuple[str, ...]
    warnings: tuple[str, ...]
    auto_replace: Literal[False] = False
    semantic_change_established: Literal[False] = False


def load_lng_terminal_reference_manifest(
    path: str | Path,
) -> LngTerminalReferenceManifest:
    """Load an explicit UTF-8 JSON manifest from one bounded local file.

    The loader performs strict JSON parsing and model validation. It does not read
    environment variables, make network calls, mutate the file or consult a database.

    Args:
        path: Local manifest path.

    Returns:
        The validated immutable manifest.

    Raises:
        LngTerminalReferenceError: With a stable code for unreadable, oversized,
            non-UTF-8, malformed or schema-invalid input.
    """

    manifest_path = _coerce_local_path(path, LngReferenceErrorCode.MANIFEST_PATH_INVALID)
    payload = _read_bounded_file(
        manifest_path,
        max_bytes=MAX_REFERENCE_BYTES,
        code_not_found=LngReferenceErrorCode.MANIFEST_NOT_FOUND,
        code_not_a_file=LngReferenceErrorCode.MANIFEST_NOT_A_FILE,
        code_too_large=LngReferenceErrorCode.MANIFEST_TOO_LARGE,
    )
    return loads_lng_terminal_reference_manifest(payload)


def loads_lng_terminal_reference_manifest(
    payload: str | bytes,
) -> LngTerminalReferenceManifest:
    """Parse and validate manifest JSON that has already been read locally.

    ``str`` input is assumed to have been decoded as strict UTF-8 by the caller.
    ``bytes`` input is decoded here with strict UTF-8 and a leading BOM is refused.
    """

    if isinstance(payload, bytes):
        if payload.startswith(b"\xef\xbb\xbf"):
            raise LngTerminalReferenceError(
                LngReferenceErrorCode.MANIFEST_BOM_NOT_ALLOWED,
                "manifest must be UTF-8 without a byte-order mark",
            )
        if len(payload) > MAX_REFERENCE_BYTES:
            raise LngTerminalReferenceError(
                LngReferenceErrorCode.MANIFEST_TOO_LARGE,
                f"manifest exceeds {MAX_REFERENCE_BYTES} bytes",
            )
        try:
            text = payload.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise LngTerminalReferenceError(
                LngReferenceErrorCode.MANIFEST_UTF8_INVALID,
                "manifest is not valid UTF-8",
            ) from exc
    elif isinstance(payload, str):
        if payload.startswith("\ufeff"):
            raise LngTerminalReferenceError(
                LngReferenceErrorCode.MANIFEST_BOM_NOT_ALLOWED,
                "manifest must not start with a byte-order mark",
            )
        if len(payload.encode("utf-8")) > MAX_REFERENCE_BYTES:
            raise LngTerminalReferenceError(
                LngReferenceErrorCode.MANIFEST_TOO_LARGE,
                f"manifest exceeds {MAX_REFERENCE_BYTES} bytes",
            )
        text = payload
    else:
        raise LngTerminalReferenceError(
            LngReferenceErrorCode.MANIFEST_SCHEMA_INVALID,
            "manifest payload must be UTF-8 text or bytes",
        )

    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LngTerminalReferenceError(
            LngReferenceErrorCode.MANIFEST_JSON_INVALID,
            f"manifest JSON is invalid at line {exc.lineno}, column {exc.colno}",
        ) from exc
    if not isinstance(raw, dict):
        raise LngTerminalReferenceError(
            LngReferenceErrorCode.MANIFEST_SCHEMA_INVALID,
            "manifest JSON root must be an object",
        )
    try:
        return LngTerminalReferenceManifest.model_validate(raw)
    except ValidationError as exc:
        raise LngTerminalReferenceError(
            LngReferenceErrorCode.MANIFEST_SCHEMA_INVALID,
            _validation_summary(exc),
        ) from exc


def dump_lng_terminal_reference_manifest(
    manifest: LngTerminalReferenceManifest,
) -> str:
    """Return deterministic UTF-8 JSON text for an already validated manifest."""

    payload = manifest.model_dump(mode="json")
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def parse_retrieved_at_utc(raw: str) -> datetime:
    """Parse an explicit ISO-8601 retrieval instant with a UTC offset.

    Naive values and non-zero offsets are refused. Publication dates and unknown
    effective dates are intentionally not substituted with this value.
    """

    if type(raw) is not str or not raw.strip():
        raise LngTerminalReferenceError(
            LngReferenceErrorCode.INVALID_RETRIEVED_AT,
            "retrieved-at must be an explicit ISO-8601 UTC timestamp",
        )
    text = raw.strip()
    if text.endswith(("Z", "z")):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise LngTerminalReferenceError(
            LngReferenceErrorCode.INVALID_RETRIEVED_AT,
            "retrieved-at is not a valid ISO-8601 timestamp",
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise LngTerminalReferenceError(
            LngReferenceErrorCode.INVALID_RETRIEVED_AT,
            "retrieved-at must be timezone-aware UTC",
        )
    return parsed


def lookup_reviewed_lng_terminal_fact(
    manifest: LngTerminalReferenceManifest,
    *,
    terminal_id: str,
    parameter: FactParameter | str,
    quantity_basis: QuantityBasis | str,
    scenario_date: date,
) -> LngFactLookup:
    """Look up reviewed facts for exactly one parameter and quantity basis.

    Candidate facts are excluded. Reviewed facts with an unknown effective start are
    reported as ``APPLICABILITY_UNKNOWN`` rather than assumed applicable. If more
    than one reviewed fact is applicable, the result is ``AMBIGUOUS_REVIEWED_FACTS``
    and no fact is selected. Nothing is averaged, converted or replaced.
    """

    _require_manifest_instance(manifest)
    normalized_terminal_id = _require_terminal_id(terminal_id)
    normalized_parameter = _coerce_parameter(parameter)
    normalized_basis = _coerce_quantity_basis(quantity_basis)
    _require_scenario_date(scenario_date)

    matching = tuple(
        fact
        for fact in manifest.facts
        if fact.review_status is FactReviewStatus.REVIEWED
        and fact.terminal_id == normalized_terminal_id
        and fact.parameter is normalized_parameter
        and fact.quantity_basis is normalized_basis
    )
    matching_candidates = tuple(
        fact
        for fact in manifest.facts
        if fact.review_status is FactReviewStatus.CANDIDATE
        and fact.terminal_id == normalized_terminal_id
        and fact.parameter is normalized_parameter
        and fact.quantity_basis is normalized_basis
    )
    warnings: list[str] = []
    if matching_candidates:
        warnings.append("CANDIDATE_FACTS_EXCLUDED_FROM_REVIEWED_SELECTION")

    if not matching:
        return LngFactLookup(
            status=LngFactLookupStatus.NO_REVIEWED_FACT,
            terminal_id=normalized_terminal_id,
            parameter=normalized_parameter,
            quantity_basis=normalized_basis,
            scenario_date=scenario_date,
            reviewed_facts=(),
            applicable_fact_ids=(),
            unknown_applicability_fact_ids=(),
            selected_fact=None,
            warnings=tuple(warnings),
        )

    unknown = tuple(fact for fact in matching if not fact.has_known_applicability_start)
    applicable = tuple(
        fact
        for fact in matching
        if fact.has_known_applicability_start and fact.applies_on(scenario_date)
    )
    unknown_ids = tuple(fact.fact_id for fact in unknown)
    applicable_ids = tuple(fact.fact_id for fact in applicable)

    if len(applicable) > 1:
        status = LngFactLookupStatus.AMBIGUOUS_REVIEWED_FACTS
        warnings.append("MULTIPLE_REVIEWED_FACTS_ARE_APPLICABLE")
    elif unknown:
        status = LngFactLookupStatus.APPLICABILITY_UNKNOWN
        warnings.append("EFFECTIVE_APPLICABILITY_INTERVAL_UNKNOWN")
    elif len(applicable) == 1:
        status = LngFactLookupStatus.REVIEWED_FACT_FOUND
    else:
        status = LngFactLookupStatus.NO_APPLICABLE_REVIEWED_FACT
        warnings.append("REVIEWED_FACTS_NOT_APPLICABLE_ON_SCENARIO_DATE")

    selected = applicable[0] if status is LngFactLookupStatus.REVIEWED_FACT_FOUND else None
    return LngFactLookup(
        status=status,
        terminal_id=normalized_terminal_id,
        parameter=normalized_parameter,
        quantity_basis=normalized_basis,
        scenario_date=scenario_date,
        reviewed_facts=matching,
        applicable_fact_ids=applicable_ids,
        unknown_applicability_fact_ids=unknown_ids,
        selected_fact=selected,
        warnings=tuple(warnings),
    )


def inspect_candidate_lng_terminal_facts(
    manifest: LngTerminalReferenceManifest,
    *,
    terminal_id: str | None = None,
    parameter: FactParameter | str | None = None,
    quantity_basis: QuantityBasis | str | None = None,
) -> tuple[LngTerminalFact, ...]:
    """Return candidate facts for informational inspection only.

    Candidates are not scenario-eligible, do not become reviewed through inspection,
    and retain their original value, unit, quotation and unknown dates.
    """

    _require_manifest_instance(manifest)
    normalized_terminal_id = (
        _require_terminal_id(terminal_id) if terminal_id is not None else None
    )
    normalized_parameter = _coerce_parameter(parameter) if parameter is not None else None
    normalized_basis = (
        _coerce_quantity_basis(quantity_basis) if quantity_basis is not None else None
    )
    return tuple(
        fact
        for fact in manifest.facts
        if fact.review_status is FactReviewStatus.CANDIDATE
        and (normalized_terminal_id is None or fact.terminal_id == normalized_terminal_id)
        and (normalized_parameter is None or fact.parameter is normalized_parameter)
        and (normalized_basis is None or fact.quantity_basis is normalized_basis)
    )


def read_lng_terminal_candidate_file(
    path: str | Path,
    *,
    max_bytes: int = MAX_CANDIDATE_BYTES,
) -> bytes:
    """Read one bounded local candidate file without hashing or network access."""

    limit = _validate_size_limit(max_bytes)
    candidate_path = _coerce_local_path(
        path,
        LngReferenceErrorCode.CANDIDATE_PATH_INVALID,
    )
    return _read_bounded_file(
        candidate_path,
        max_bytes=limit,
        code_not_found=LngReferenceErrorCode.CANDIDATE_NOT_FOUND,
        code_not_a_file=LngReferenceErrorCode.CANDIDATE_NOT_A_FILE,
        code_too_large=LngReferenceErrorCode.CANDIDATE_TOO_LARGE,
    )


def compare_lng_terminal_source_bytes(
    manifest: LngTerminalReferenceManifest,
    *,
    source_id: str,
    candidate_bytes: bytes,
    retrieved_at_utc: datetime,
    max_bytes: int = MAX_CANDIDATE_BYTES,
) -> LngTerminalSourceChange:
    """Compare bounded local candidate bytes with one preserved source hash.

    A changed hash produces a ``REVIEW_REQUIRED`` candidate. It does not establish a
    semantic change, alter the manifest, review any fact, replace a source, or prove
    authenticity. Empty payloads and oversized payloads are refused. No network path
    exists in this function.
    """

    _require_manifest_instance(manifest)
    limit = _validate_size_limit(max_bytes)
    normalized_source_id = _require_source_id(source_id)
    try:
        candidate_time = _require_aware_utc(retrieved_at_utc, "retrieved_at_utc")
    except ValueError as exc:
        raise LngTerminalReferenceError(
            LngReferenceErrorCode.INVALID_RETRIEVED_AT,
            "retrieved_at_utc must be timezone-aware UTC",
        ) from exc
    source = next(
        (item for item in manifest.sources if item.source_id == normalized_source_id),
        None,
    )
    if source is None:
        raise LngTerminalReferenceError(
            LngReferenceErrorCode.UNKNOWN_SOURCE,
            "candidate source_id is not present in the manifest",
        )
    if not isinstance(candidate_bytes, (bytes, bytearray)):
        raise LngTerminalReferenceError(
            LngReferenceErrorCode.CANDIDATE_PAYLOAD_INVALID,
            "candidate payload must be bytes",
        )
    candidate_payload = bytes(candidate_bytes)
    if len(candidate_payload) > limit:
        raise LngTerminalReferenceError(
            LngReferenceErrorCode.CANDIDATE_TOO_LARGE,
            f"candidate payload exceeds {limit} bytes",
        )
    if not candidate_payload:
        raise LngTerminalReferenceError(
            LngReferenceErrorCode.CANDIDATE_EMPTY,
            "empty candidate payload is refused and cannot prove source absence",
        )

    candidate_hash = sha256(candidate_payload).hexdigest()
    changed = candidate_hash != source.captured_sha256
    affected_fact_ids = tuple(
        sorted(fact.fact_id for fact in manifest.facts if fact.source_id == source.source_id)
    )
    warnings = [
        "SOURCE_HASH_COMPARISON_DOES_NOT_PROVE_AUTHENTICITY_OR_AUTHORITY",
    ]
    if changed:
        status = SourceChangeStatus.REVIEW_REQUIRED
        warnings.append("BYTE_CHANGE_REQUIRES_REVIEW_NOT_AUTOMATIC_REPLACEMENT")
    else:
        status = SourceChangeStatus.UNCHANGED
        warnings.append("UNCHANGED_BYTES_DO_NOT_CONFIRM_CURRENT_APPLICABILITY")
    if not affected_fact_ids:
        warnings.append("NO_REFERENCE_FACTS_REFERENCE_SOURCE")

    return LngTerminalSourceChange(
        status=status,
        source_id=source.source_id,
        official_url=source.official_url,
        operator=source.operator,
        document_title=source.document_title,
        publication_version=source.publication_version,
        before_sha256=source.captured_sha256,
        after_sha256=candidate_hash,
        candidate_byte_length=len(candidate_payload),
        candidate_retrieved_at_utc=candidate_time,
        source_retrieved_at_utc=source.retrieved_at_utc,
        affected_fact_ids=affected_fact_ids,
        warnings=tuple(warnings),
    )


def _require_non_blank(value: str, field_name: str) -> str:
    if not value.strip():
        raise ValueError(f"{field_name} must not be blank")
    return value


def _require_aware_utc(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError(f"{field_name} must be timezone-aware UTC")
    return value


def _normalize_unit(unit: str) -> str:
    normalized = unit.strip().lower().replace("³", "3").replace("²", "2")
    normalized = normalized.replace("％", "%").replace("_", " ")
    normalized = re.sub(r"\s*/\s*", "/", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def _unit_matches_basis(unit: str, basis: QuantityBasis) -> bool:
    if basis is QuantityBasis.MONEY_PER_ENERGY:
        return _MONEY_PER_ENERGY_RE.fullmatch(unit.strip()) is not None
    allowed_units = _UNIT_VARIANTS.get(basis)
    if allowed_units is None:
        return False
    return _normalize_unit(unit) in allowed_units


def _validation_summary(exc: ValidationError) -> str:
    messages: list[str] = []
    for error in exc.errors(include_url=False)[:5]:
        location = ".".join(str(part) for part in error["loc"])
        messages.append(f"{location}: {error['msg']}" if location else error["msg"])
    return "manifest schema is invalid: " + "; ".join(messages)


def _coerce_local_path(path: str | Path, code: LngReferenceErrorCode) -> Path:
    try:
        return Path(path)
    except TypeError as exc:
        raise LngTerminalReferenceError(code, "path must be a local filesystem path") from exc


def _read_bounded_file(
    path: Path,
    *,
    max_bytes: int,
    code_not_found: LngReferenceErrorCode,
    code_not_a_file: LngReferenceErrorCode,
    code_too_large: LngReferenceErrorCode,
) -> bytes:
    try:
        exists = path.exists()
    except (OSError, ValueError) as exc:
        raise LngTerminalReferenceError(
            code_not_found,
            "local file could not be inspected",
        ) from exc
    if not exists:
        raise LngTerminalReferenceError(code_not_found, "local file does not exist")
    try:
        is_file = path.is_file()
    except (OSError, ValueError) as exc:
        raise LngTerminalReferenceError(
            code_not_found,
            "local file could not be inspected",
        ) from exc
    if not is_file:
        raise LngTerminalReferenceError(code_not_a_file, "local path is not a file")
    try:
        size = path.stat().st_size
    except (OSError, ValueError) as exc:
        raise LngTerminalReferenceError(
            code_not_found,
            "local file could not be inspected",
        ) from exc
    if size > max_bytes:
        raise LngTerminalReferenceError(
            code_too_large,
            f"local file exceeds {max_bytes} bytes",
        )
    try:
        payload = path.read_bytes()
    except (OSError, ValueError) as exc:
        raise LngTerminalReferenceError(
            code_not_found,
            "local file could not be read",
        ) from exc
    if len(payload) > max_bytes:
        raise LngTerminalReferenceError(
            code_too_large,
            f"local file exceeds {max_bytes} bytes",
        )
    return payload


def _validate_size_limit(max_bytes: int) -> int:
    if (
        isinstance(max_bytes, bool)
        or not isinstance(max_bytes, int)
        or max_bytes <= 0
        or max_bytes > MAX_CANDIDATE_BYTES
    ):
        raise LngTerminalReferenceError(
            LngReferenceErrorCode.INVALID_SIZE_LIMIT,
            f"size limit must be a positive integer at most {MAX_CANDIDATE_BYTES}",
        )
    return max_bytes


def _require_manifest_instance(
    manifest: LngTerminalReferenceManifest,
) -> LngTerminalReferenceManifest:
    if not isinstance(manifest, LngTerminalReferenceManifest):
        raise LngTerminalReferenceError(
            LngReferenceErrorCode.MANIFEST_SCHEMA_INVALID,
            "a validated reference manifest is required",
        )
    return manifest


def _require_terminal_id(terminal_id: str) -> str:
    if type(terminal_id) is not str or not terminal_id.strip():
        raise LngTerminalReferenceError(
            LngReferenceErrorCode.INVALID_TERMINAL_ID,
            "terminal_id must be a non-blank string",
        )
    return terminal_id


def _require_source_id(source_id: str) -> str:
    if type(source_id) is not str or not source_id.strip():
        raise LngTerminalReferenceError(
            LngReferenceErrorCode.INVALID_SOURCE_ID,
            "source_id must be a non-blank string",
        )
    return source_id


def _coerce_parameter(parameter: FactParameter | str) -> FactParameter:
    if isinstance(parameter, FactParameter):
        return parameter
    try:
        return FactParameter(str(parameter).strip().upper())
    except (TypeError, ValueError) as exc:
        raise LngTerminalReferenceError(
            LngReferenceErrorCode.INVALID_PARAMETER,
            "parameter is not a supported terminal fact parameter",
        ) from exc


def _coerce_quantity_basis(quantity_basis: QuantityBasis | str) -> QuantityBasis:
    if isinstance(quantity_basis, QuantityBasis):
        return quantity_basis
    try:
        return QuantityBasis(str(quantity_basis).strip().upper())
    except (TypeError, ValueError) as exc:
        raise LngTerminalReferenceError(
            LngReferenceErrorCode.INVALID_QUANTITY_BASIS,
            "quantity_basis is not a supported measurement basis",
        ) from exc


def _require_scenario_date(scenario_date: date) -> date:
    if isinstance(scenario_date, datetime) or not isinstance(scenario_date, date):
        raise LngTerminalReferenceError(
            LngReferenceErrorCode.INVALID_SCENARIO_DATE,
            "scenario_date must be a calendar date",
        )
    return scenario_date


__all__ = [
    "EMPTY_MANIFEST_NOTE",
    "MANIFEST_MODEL_VERSION",
    "MANIFEST_SCHEMA_VERSION",
    "MAX_CANDIDATE_BYTES",
    "MAX_QUOTATION_WORDS",
    "MAX_REFERENCE_BYTES",
    "PARAMETER_BASIS_COMPATIBILITY",
    "FactParameter",
    "FactReviewStatus",
    "LngFactLookup",
    "LngFactLookupStatus",
    "LngReferenceErrorCode",
    "LngTerminalFact",
    "LngTerminalReferenceError",
    "LngTerminalReferenceManifest",
    "LngTerminalSource",
    "LngTerminalSourceChange",
    "QuantityBasis",
    "SourceChangeStatus",
    "compare_lng_terminal_source_bytes",
    "dump_lng_terminal_reference_manifest",
    "inspect_candidate_lng_terminal_facts",
    "load_lng_terminal_reference_manifest",
    "loads_lng_terminal_reference_manifest",
    "lookup_reviewed_lng_terminal_fact",
    "parse_retrieved_at_utc",
    "read_lng_terminal_candidate_file",
]
