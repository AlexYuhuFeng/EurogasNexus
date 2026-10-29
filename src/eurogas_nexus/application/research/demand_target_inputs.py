"""Pure point-in-time mapper from National Gas revisions to demand-target rows.

The caller owns the database read and supplies the already-bounded ORM rows.  This
module performs no query, commit, activation or source-registry change.  It
re-applies the read contract as defence in depth: one allowlisted provider item,
one explicit CSV/REST copy, the fixed GB NTS throughput scope and native ``mscm``
unit, an inclusive gas-day window, and actual receipt availability no later than
an aware cutoff.

Blank values remain missing, never zero; an exact zero remains a legitimate
value.  Only a D+1 revision whose source explicitly says ``is_provisional=True``
can become a ``PROVISIONAL`` target, and only when the caller passes
``allow_provisional_targets=True``.  D+6 provisionality is unresolved, so those
revisions are refused instead of being forced into ACTUAL or ESTIMATED.  Source
quality ``A`` means AMENDED, which has no admitted target mapping here, so it is
refused rather than relabelled ACTUAL.

Revisions are ranked by their actual receipt availability within each gas day.
That integer revision is derived receipt order, not a provider revision number.
Every admitted revision is returned so the domain model can resolve the latest
revision genuinely available at each fold cutoff; this mapper never narrows the
result to the latest revision at its own outer cutoff.  Two distinct publications
with the same receipt time on the same gas day make selection ambiguous and are
refused rather than resolved lexically.  Original source quality, provisional
status, publication identity, raw hash and exact decimal text are retained in a
separate, immutable provenance mapping.  Its ``selected`` flag is only a hint that
a revision is latest at this mapper's cutoff, never an exclusion.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from types import MappingProxyType
from typing import TYPE_CHECKING

from eurogas_nexus.domain.research.weather_demand import (
    MAX_DEMAND_VALUE,
    DemandTargetQuality,
    DemandTargetRow,
    TargetScope,
    WeatherDemandInputError,
)
from eurogas_nexus.ingestion.national_gas_demand import ALLOWED_PROVIDER_ITEM_IDS

if TYPE_CHECKING:
    from eurogas_nexus.db.models.demand import NationalGasActualDemandRecord

SUPPORTED_SOURCE_FORMATS = frozenset({"CSV", "REST"})
SUPPORTED_REGION = "GB_NTS"
SUPPORTED_SOURCE_UNIT = "mscm"
TARGET_UNIT = "MSCM"
TARGET_SCOPE = TargetScope.GB_NTS_THROUGHPUT
REVISION_ORDER_BASIS = "DERIVED_RECEIPT_ORDER"
MAX_NATIVE_VALUE = Decimal(str(MAX_DEMAND_VALUE))
_EXACT_DECIMAL = re.compile(r"(?:0|[1-9][0-9]*)(?:\.[0-9]+)?\Z")


class DemandTargetInputError(WeatherDemandInputError):
    """Base typed refusal for the demand-target mapper."""

    code = "DEMAND_TARGET_INPUT_ERROR"

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(f"{self.code}: {message}")


class DemandTargetInputValidationError(DemandTargetInputError):
    """An explicit selection argument violates the frozen mapper contract."""

    code = "DEMAND_TARGET_INPUT_VALIDATION_ERROR"


class DemandTargetAmbiguityError(DemandTargetInputError):
    """Two distinct publications share one receipt time and cannot be ranked."""

    code = "AMBIGUOUS_RECEIPT_TIE"


class DemandTargetDuplicateConflict(DemandTargetInputError):
    """One immutable record id appeared with different content."""

    code = "DUPLICATE_RECORD_ID_CONFLICT"


class DemandTargetDiagnosticCode(StrEnum):
    """Stable, operator-safe reasons a revision was not admitted."""

    BLANK_VALUE = "BLANK_VALUE"
    SOURCE_QUALITY_AMENDED = "SOURCE_QUALITY_AMENDED"
    SOURCE_QUALITY_UNSUPPORTED = "SOURCE_QUALITY_UNSUPPORTED"
    PROVISIONAL_TARGET_NOT_ALLOWED = "PROVISIONAL_TARGET_NOT_ALLOWED"
    UNRESOLVED_TARGET_QUALITY = "UNRESOLVED_TARGET_QUALITY"
    PROVIDER_ITEM_MISMATCH = "PROVIDER_ITEM_MISMATCH"
    SOURCE_FORMAT_MISMATCH = "SOURCE_FORMAT_MISMATCH"
    GAS_DAY_OUTSIDE_WINDOW = "GAS_DAY_OUTSIDE_WINDOW"
    REGION_NOT_SUPPORTED = "REGION_NOT_SUPPORTED"
    UNIT_NOT_SUPPORTED = "UNIT_NOT_SUPPORTED"
    NAIVE_AVAILABILITY = "NAIVE_AVAILABILITY"
    NAIVE_RECEIPT_TIME = "NAIVE_RECEIPT_TIME"
    AVAILABLE_AFTER_CUTOFF = "AVAILABLE_AFTER_CUTOFF"
    AVAILABILITY_BEFORE_RECEIPT = "AVAILABILITY_BEFORE_RECEIPT"
    INVALID_NATIVE_VALUE = "INVALID_NATIVE_VALUE"
    DUPLICATE_RECORD_ID = "DUPLICATE_RECORD_ID"


@dataclass(frozen=True)
class DemandTargetDiagnostic:
    """One refused revision with a stable code and no inferred value."""

    code: DemandTargetDiagnosticCode
    record_id: str
    gas_day: date | None
    detail: str


@dataclass(frozen=True)
class DemandTargetProvenance:
    """Original source evidence retained separately from the model-facing row.

    ``selected`` only marks the latest admitted revision at the mapper's outer
    cutoff.  Earlier revisions stay in ``rows`` for the domain fitter's per-fold
    cutoff resolution, so ``selected=False`` is never an exclusion decision.
    """

    record_id: str
    source_publication_id: str
    provider_item_id: str
    source_format: str
    gas_day: date
    value_text: str
    value_decimal: Decimal
    unit: str
    quality_indicator: str | None
    provisional_status: str
    is_provisional: bool | None
    raw_sha256: str
    received_at: datetime
    available_at: datetime
    derived_revision: int
    revision_order_basis: str
    selected: bool


@dataclass(frozen=True)
class DemandTargetInputs:
    """Immutable admitted target revisions, source provenance and refusals."""

    rows: tuple[DemandTargetRow, ...]
    provenance_by_record_id: Mapping[str, DemandTargetProvenance]
    diagnostics: tuple[DemandTargetDiagnostic, ...]
    region: str = SUPPORTED_REGION
    scope: TargetScope = TARGET_SCOPE
    native_unit: str = TARGET_UNIT


@dataclass(frozen=True)
class _Selection:
    provider_item_id: str
    source_format: str
    gas_day_from: date
    gas_day_to: date
    available_at_utc: datetime
    allow_provisional_targets: bool


@dataclass(frozen=True)
class _AdmittedRevision:
    record: NationalGasActualDemandRecord
    value_text: str
    value_decimal: Decimal
    value_float: float
    quality: DemandTargetQuality
    available_at: datetime
    received_at: datetime


def build_demand_target_rows(
    records: Sequence[NationalGasActualDemandRecord],
    *,
    provider_item_id: str,
    source_format: str,
    gas_day_from: date,
    gas_day_to: date,
    available_at_utc: datetime,
    allow_provisional_targets: bool = False,
) -> DemandTargetInputs:
    """Map already-read revisions to every admitted point-in-time target.

    The explicit selection is validated independently of the repository so a
    caller cannot mix source formats, provider items, gas-day windows or receipt
    cutoffs.  Records that violate any part of that contract are reported as
    diagnostics and never silently coerced.  Every admitted revision is returned
    with its derived receipt rank so each downstream fold cutoff can resolve the
    latest revision actually available then; only revisions after this mapper's
    cutoff are excluded.  Provenance ``selected`` merely marks the latest
    revision at this cutoff and never removes an earlier revision from ``rows``.
    An equal-receipt publication tie is refused because choosing one would
    fabricate historical ranking evidence.
    """

    selection = _validate_selection(
        provider_item_id=provider_item_id,
        source_format=source_format,
        gas_day_from=gas_day_from,
        gas_day_to=gas_day_to,
        available_at_utc=available_at_utc,
        allow_provisional_targets=allow_provisional_targets,
    )

    admitted: list[_AdmittedRevision] = []
    diagnostics: list[DemandTargetDiagnostic] = []
    seen: dict[str, tuple[object, ...]] = {}

    for record in records:
        record_id = _record_id(record)
        signature = _record_signature(record)
        prior = seen.get(record_id)
        if prior is not None:
            if prior == signature:
                diagnostics.append(
                    _diagnostic(
                        DemandTargetDiagnosticCode.DUPLICATE_RECORD_ID,
                        record,
                        "identical duplicate record id was mapped once",
                    )
                )
                continue
            raise DemandTargetDuplicateConflict(
                "one immutable record id appeared with different source content"
            )
        seen[record_id] = signature

        revision, diagnostic = _admit(record, selection)
        if diagnostic is not None:
            diagnostics.append(diagnostic)
            continue
        if revision is not None:
            admitted.append(revision)

    by_gas_day: dict[date, list[_AdmittedRevision]] = {}
    for revision in admitted:
        by_gas_day.setdefault(revision.record.gas_day, []).append(revision)

    target_rows: list[DemandTargetRow] = []
    provenance: dict[str, DemandTargetProvenance] = {}
    for gas_day in sorted(by_gas_day):
        revisions = sorted(
            by_gas_day[gas_day],
            key=lambda item: (item.available_at, item.record.record_id),
        )
        _refuse_equal_receipt_tie(gas_day, revisions)
        for rank, revision in enumerate(revisions, start=1):
            latest_at_outer_cutoff = rank == len(revisions)
            provenance[revision.record.record_id] = _provenance(
                revision,
                derived_revision=rank,
                selected=latest_at_outer_cutoff,
            )
            target_rows.append(
                DemandTargetRow(
                    gas_day=revision.record.gas_day,
                    scope=TARGET_SCOPE,
                    region=SUPPORTED_REGION,
                    unit=TARGET_UNIT,
                    value=revision.value_float,
                    quality=revision.quality,
                    revision=rank,
                    revision_id=revision.record.record_id,
                    available_at=revision.available_at,
                    source_ref=(
                        f"NATIONAL_GAS:{selection.source_format}:"
                        f"{revision.record.source_publication_id}"
                    ),
                )
            )

    target_rows.sort(
        key=lambda row: (row.gas_day, row.available_at, row.revision_id)
    )
    ordered_diagnostics = tuple(
        sorted(
            diagnostics,
            key=lambda item: (
                item.gas_day or date.min,
                item.record_id,
                item.code.value,
            ),
        )
    )
    return DemandTargetInputs(
        rows=tuple(target_rows),
        provenance_by_record_id=MappingProxyType(dict(provenance)),
        diagnostics=ordered_diagnostics,
    )


def _validate_selection(
    *,
    provider_item_id: str,
    source_format: str,
    gas_day_from: date,
    gas_day_to: date,
    available_at_utc: datetime,
    allow_provisional_targets: bool,
) -> _Selection:
    if (
        not isinstance(provider_item_id, str)
        or provider_item_id not in ALLOWED_PROVIDER_ITEM_IDS
    ):
        raise DemandTargetInputValidationError(
            "provider_item_id must be one of the allowlisted National Gas actual-demand items"
        )
    if not isinstance(source_format, str) or source_format not in SUPPORTED_SOURCE_FORMATS:
        raise DemandTargetInputValidationError("source_format must be CSV or REST")
    for name, value in (("gas_day_from", gas_day_from), ("gas_day_to", gas_day_to)):
        if not isinstance(value, date) or isinstance(value, datetime):
            raise DemandTargetInputValidationError(f"{name} must be a calendar date")
        if not date(2000, 1, 1) <= value <= date(2100, 12, 31):
            raise DemandTargetInputValidationError(f"{name} is outside the supported range")
    if gas_day_from > gas_day_to:
        raise DemandTargetInputValidationError("gas_day_from must not be after gas_day_to")
    if (
        not isinstance(available_at_utc, datetime)
        or available_at_utc.tzinfo is None
        or available_at_utc.utcoffset() is None
    ):
        raise DemandTargetInputValidationError("available_at_utc must be an aware datetime")
    if not isinstance(allow_provisional_targets, bool):
        raise DemandTargetInputValidationError("allow_provisional_targets must be a bool")
    return _Selection(
        provider_item_id=provider_item_id,
        source_format=source_format,
        gas_day_from=gas_day_from,
        gas_day_to=gas_day_to,
        available_at_utc=available_at_utc.astimezone(UTC),
        allow_provisional_targets=allow_provisional_targets,
    )


def _admit(
    record: NationalGasActualDemandRecord,
    selection: _Selection,
) -> tuple[_AdmittedRevision | None, DemandTargetDiagnostic | None]:
    if getattr(record, "provider_item_id", None) != selection.provider_item_id:
        return None, _diagnostic(
            DemandTargetDiagnosticCode.PROVIDER_ITEM_MISMATCH,
            record,
            "provider item differs from the explicit selection",
        )
    if getattr(record, "source_format", None) != selection.source_format:
        return None, _diagnostic(
            DemandTargetDiagnosticCode.SOURCE_FORMAT_MISMATCH,
            record,
            "source format differs from the explicit selection",
        )

    gas_day = getattr(record, "gas_day", None)
    if (
        not isinstance(gas_day, date)
        or isinstance(gas_day, datetime)
        or not selection.gas_day_from <= gas_day <= selection.gas_day_to
    ):
        return None, _diagnostic(
            DemandTargetDiagnosticCode.GAS_DAY_OUTSIDE_WINDOW,
            record,
            "gas day is not a calendar date inside the inclusive selection window",
        )

    if getattr(record, "region", None) != SUPPORTED_REGION:
        return None, _diagnostic(
            DemandTargetDiagnosticCode.REGION_NOT_SUPPORTED,
            record,
            "only the fixed GB_NTS region is supported",
        )
    unit = getattr(record, "unit", None)
    if not isinstance(unit, str) or unit.strip().lower() != SUPPORTED_SOURCE_UNIT:
        return None, _diagnostic(
            DemandTargetDiagnosticCode.UNIT_NOT_SUPPORTED,
            record,
            "only the native mscm unit is supported",
        )

    available_at = _aware_utc(getattr(record, "available_at_utc", None))
    if available_at is None:
        return None, _diagnostic(
            DemandTargetDiagnosticCode.NAIVE_AVAILABILITY,
            record,
            "receipt availability must be an aware datetime",
        )
    if available_at > selection.available_at_utc:
        return None, _diagnostic(
            DemandTargetDiagnosticCode.AVAILABLE_AFTER_CUTOFF,
            record,
            "receipt availability is later than the explicit cutoff",
        )
    received_at = _aware_utc(getattr(record, "received_at_utc", None))
    if received_at is None:
        return None, _diagnostic(
            DemandTargetDiagnosticCode.NAIVE_RECEIPT_TIME,
            record,
            "actual receipt time must be an aware datetime",
        )
    if available_at < received_at:
        return None, _diagnostic(
            DemandTargetDiagnosticCode.AVAILABILITY_BEFORE_RECEIPT,
            record,
            "availability precedes actual receipt and cannot be claimed historically",
        )

    value_text = getattr(record, "value_text", None)
    if not isinstance(value_text, str):
        return None, _diagnostic(
            DemandTargetDiagnosticCode.INVALID_NATIVE_VALUE,
            record,
            "native value text is missing",
        )
    if bool(getattr(record, "value_is_blank", False)) or value_text == "":
        return None, _diagnostic(
            DemandTargetDiagnosticCode.BLANK_VALUE,
            record,
            "blank native value is missing, not zero",
        )
    if not _EXACT_DECIMAL.fullmatch(value_text):
        return None, _diagnostic(
            DemandTargetDiagnosticCode.INVALID_NATIVE_VALUE,
            record,
            "native value is not an exact non-negative decimal",
        )
    try:
        value_decimal = Decimal(value_text)
    except InvalidOperation:
        return None, _diagnostic(
            DemandTargetDiagnosticCode.INVALID_NATIVE_VALUE,
            record,
            "native value is not an exact non-negative decimal",
        )
    if (
        not value_decimal.is_finite()
        or value_decimal < 0
        or value_decimal > MAX_NATIVE_VALUE
    ):
        return None, _diagnostic(
            DemandTargetDiagnosticCode.INVALID_NATIVE_VALUE,
            record,
            "native value is not finite and bounded",
        )
    value_float = float(value_decimal)
    if not math.isfinite(value_float) or value_float > MAX_DEMAND_VALUE:
        return None, _diagnostic(
            DemandTargetDiagnosticCode.INVALID_NATIVE_VALUE,
            record,
            "native value cannot be represented as a finite bounded float",
        )

    quality, diagnostic = _target_quality(record, selection)
    if diagnostic is not None:
        return None, diagnostic
    if quality is None:
        return None, _diagnostic(
            DemandTargetDiagnosticCode.UNRESOLVED_TARGET_QUALITY,
            record,
            "target quality could not be resolved without inventing one",
        )

    return (
        _AdmittedRevision(
            record=record,
            value_text=value_text,
            value_decimal=value_decimal,
            value_float=value_float,
            quality=quality,
            available_at=available_at,
            received_at=received_at,
        ),
        None,
    )


def _target_quality(
    record: NationalGasActualDemandRecord,
    selection: _Selection,
) -> tuple[DemandTargetQuality | None, DemandTargetDiagnostic | None]:
    term = getattr(record, "term", None)
    is_provisional = getattr(record, "is_provisional", None)
    if term == "D+6" or is_provisional is None:
        return None, _diagnostic(
            DemandTargetDiagnosticCode.UNRESOLVED_TARGET_QUALITY,
            record,
            "D+6 provisionality is unresolved; no ACTUAL or ESTIMATED target is inferred",
        )
    if term != "D+1" or is_provisional is not True:
        return None, _diagnostic(
            DemandTargetDiagnosticCode.UNRESOLVED_TARGET_QUALITY,
            record,
            "term and provisional state do not resolve to an admitted target quality",
        )
    if not selection.allow_provisional_targets:
        return None, _diagnostic(
            DemandTargetDiagnosticCode.PROVISIONAL_TARGET_NOT_ALLOWED,
            record,
            "provisional target requires explicit caller permission",
        )

    quality_indicator = getattr(record, "quality_indicator", None)
    if quality_indicator in (None, ""):
        return DemandTargetQuality.PROVISIONAL, None
    if quality_indicator == "A":
        return None, _diagnostic(
            DemandTargetDiagnosticCode.SOURCE_QUALITY_AMENDED,
            record,
            "source quality A means AMENDED; it is not relabelled ACTUAL",
        )
    return None, _diagnostic(
        DemandTargetDiagnosticCode.SOURCE_QUALITY_UNSUPPORTED,
        record,
        "source quality has no admitted target-quality mapping",
    )


def _refuse_equal_receipt_tie(
    gas_day: date,
    revisions: Sequence[_AdmittedRevision],
) -> None:
    for previous, current in zip(revisions, revisions[1:], strict=False):
        if previous.available_at != current.available_at:
            continue
        raise DemandTargetAmbiguityError(
            f"ambiguous target selection for {gas_day.isoformat()}: "
            "distinct publications share one receipt availability"
        )


def _provenance(
    revision: _AdmittedRevision,
    *,
    derived_revision: int,
    selected: bool,
) -> DemandTargetProvenance:
    record = revision.record
    return DemandTargetProvenance(
        record_id=record.record_id,
        source_publication_id=record.source_publication_id,
        provider_item_id=record.provider_item_id,
        source_format=record.source_format,
        gas_day=record.gas_day,
        value_text=revision.value_text,
        value_decimal=revision.value_decimal,
        unit=record.unit,
        quality_indicator=record.quality_indicator,
        provisional_status=record.provisional_status,
        is_provisional=record.is_provisional,
        raw_sha256=record.raw_sha256,
        received_at=revision.received_at,
        available_at=revision.available_at,
        derived_revision=derived_revision,
        revision_order_basis=REVISION_ORDER_BASIS,
        selected=selected,
    )


def _record_id(record: NationalGasActualDemandRecord) -> str:
    record_id = getattr(record, "record_id", None)
    if not isinstance(record_id, str) or not record_id:
        raise DemandTargetInputValidationError("every record must carry a non-empty record id")
    return record_id


def _record_signature(record: NationalGasActualDemandRecord) -> tuple[object, ...]:
    return (
        getattr(record, "record_id", None),
        getattr(record, "source_publication_id", None),
        getattr(record, "provider_item_id", None),
        getattr(record, "source_format", None),
        getattr(record, "region", None),
        getattr(record, "term", None),
        getattr(record, "gas_day", None),
        getattr(record, "value_text", None),
        getattr(record, "value_is_blank", None),
        getattr(record, "unit", None),
        _time_key(getattr(record, "received_at_utc", None)),
        _time_key(getattr(record, "available_at_utc", None)),
        getattr(record, "quality_indicator", None),
        getattr(record, "provisional_status", None),
        getattr(record, "is_provisional", None),
        getattr(record, "raw_sha256", None),
    )


def _diagnostic(
    code: DemandTargetDiagnosticCode,
    record: NationalGasActualDemandRecord,
    detail: str,
) -> DemandTargetDiagnostic:
    record_id = getattr(record, "record_id", None)
    gas_day = getattr(record, "gas_day", None)
    return DemandTargetDiagnostic(
        code=code,
        record_id=record_id if isinstance(record_id, str) and record_id else "<unknown>",
        gas_day=(
            gas_day
            if isinstance(gas_day, date) and not isinstance(gas_day, datetime)
            else None
        ),
        detail=detail,
    )


def _aware_utc(value: object) -> datetime | None:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        return None
    return value.astimezone(UTC)


def _time_key(value: object) -> object:
    resolved = _aware_utc(value)
    return resolved if resolved is not None else value
