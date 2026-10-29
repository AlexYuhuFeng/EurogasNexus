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

By default, revisions are ranked by their actual receipt availability within each
gas day.  That integer revision is derived receipt order, not a provider revision
number.  Every admitted revision is returned so the domain model can resolve the
latest revision genuinely available at each fold cutoff; this mapper never
narrows the result to the latest revision at its own outer cutoff.  Two distinct
publications with the same receipt time on the same gas day make selection
ambiguous and are refused rather than resolved lexically.

An explicit opt-in ``DERIVED_REST_APPLICABILITY_ORDER_V1`` policy instead ranks
admitted REST rows by one consensus provider applicability instant.  It is
accepted only when the persisted National Gas REST identity and provenance are
complete, the three offset-bearing provider clocks agree as UTC instants, and the
consensus instant is not later than actual receipt.  It never falls back to the
maximum clock, receipt time, a lexical order or a provider revision number.
Equal source instants for competing publications remain ambiguous.  The default
receipt policy and its refusal behaviour are unchanged.

Original source quality, provisional status, publication identity, raw hash and
exact decimal text are retained in a separate, immutable provenance mapping.  Its
``selected`` flag is only a hint that a revision is latest at this mapper's
cutoff, never an exclusion.  Source applicability is not first public
availability and does not admit a row historically; folds still filter by actual
receipt through the domain core.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
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
from eurogas_nexus.ingestion.national_gas_rest import (
    API_URL as REST_API_URL,
)
from eurogas_nexus.ingestion.national_gas_rest import (
    EVIDENCE_BASIS as REST_EVIDENCE_BASIS,
)
from eurogas_nexus.ingestion.national_gas_rest import (
    HASH_SCHEMA as REST_HASH_SCHEMA,
)
from eurogas_nexus.ingestion.national_gas_rest import (
    SERIES_KEY as REST_SERIES_KEY,
)
from eurogas_nexus.ingestion.national_gas_rest import (
    SOURCE_SYSTEM as REST_SOURCE_SYSTEM,
)

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


class RevisionOrderPolicy(StrEnum):
    """Explicit revision-ranking policy for admitted target rows."""

    DERIVED_RECEIPT_ORDER = REVISION_ORDER_BASIS
    DERIVED_REST_APPLICABILITY_ORDER_V1 = "DERIVED_REST_APPLICABILITY_ORDER_V1"


# Discoverable compatibility spelling for callers that name the policy by domain.
DemandTargetRevisionOrderPolicy = RevisionOrderPolicy


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
    REST_ORDER_PROVENANCE_MISSING = "REST_ORDER_PROVENANCE_MISSING"
    REST_ORDER_PROVENANCE_MALFORMED = "REST_ORDER_PROVENANCE_MALFORMED"
    REST_ORDER_IDENTITY_MISMATCH = "REST_ORDER_IDENTITY_MISMATCH"
    SOURCE_CLOCK_MISSING = "SOURCE_CLOCK_MISSING"
    NAIVE_SOURCE_CLOCK = "NAIVE_SOURCE_CLOCK"
    MALFORMED_SOURCE_CLOCK = "MALFORMED_SOURCE_CLOCK"
    SOURCE_CLOCK_INCONSISTENT = "SOURCE_CLOCK_INCONSISTENT"
    SOURCE_CLOCKS_DISAGREE = "SOURCE_CLOCKS_DISAGREE"
    SOURCE_CLOCK_AFTER_RECEIPT = "SOURCE_CLOCK_AFTER_RECEIPT"


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
    source_order_at_utc: datetime | None = None
    source_order_method_basis: str | None = None

    @property
    def source_order_basis(self) -> str | None:
        """Compatibility alias for the chosen source-order method basis."""

        return self.source_order_method_basis


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
    revision_order_policy: RevisionOrderPolicy


@dataclass(frozen=True)
class _AdmittedRevision:
    record: NationalGasActualDemandRecord
    value_text: str
    value_decimal: Decimal
    value_float: float
    quality: DemandTargetQuality
    available_at: datetime
    received_at: datetime
    source_order_at_utc: datetime | None


def build_demand_target_rows(
    records: Sequence[NationalGasActualDemandRecord],
    *,
    provider_item_id: str,
    source_format: str,
    gas_day_from: date,
    gas_day_to: date,
    available_at_utc: datetime,
    allow_provisional_targets: bool = False,
    revision_order_policy: RevisionOrderPolicy = (
        RevisionOrderPolicy.DERIVED_RECEIPT_ORDER
    ),
) -> DemandTargetInputs:
    """Map already-read revisions to every admitted point-in-time target.

    The explicit selection is validated independently of the repository so a
    caller cannot mix source formats, provider items, gas-day windows or receipt
    cutoffs.  Records that violate any part of that contract are reported as
    diagnostics and never silently coerced.  Every admitted revision is returned
    with its derived rank so each downstream fold cutoff can resolve the latest
    revision actually available then; only revisions after this mapper's cutoff
    are excluded.

    The default ``DERIVED_RECEIPT_ORDER`` preserves receipt ranking and its
    equal-receipt ambiguity refusal.  The opt-in
    ``DERIVED_REST_APPLICABILITY_ORDER_V1`` accepts only complete persisted REST
    evidence: fixed source identity, three individually consistent offset-bearing
    and normalized clocks, one consensus UTC instant, and no source time after
    actual receipt.  It ranks by that instant alone; a later receipt cannot make
    an older provider record win.  Missing or disagreeing evidence is a typed
    diagnostic, never a guessed fallback.  Provenance ``selected`` merely marks
    the latest revision at this cutoff and never removes an earlier revision from
    ``rows``.
    """

    selection = _validate_selection(
        provider_item_id=provider_item_id,
        source_format=source_format,
        gas_day_from=gas_day_from,
        gas_day_to=gas_day_to,
        available_at_utc=available_at_utc,
        allow_provisional_targets=allow_provisional_targets,
        revision_order_policy=revision_order_policy,
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
    source_order = (
        selection.revision_order_policy
        is RevisionOrderPolicy.DERIVED_REST_APPLICABILITY_ORDER_V1
    )
    for gas_day in sorted(by_gas_day):
        if source_order:
            revisions = sorted(
                by_gas_day[gas_day],
                key=lambda item: (
                    _required_source_order_instant(item),
                    item.record.record_id,
                ),
            )
            _refuse_equal_source_order_tie(gas_day, revisions)
        else:
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
                    source_ref=_source_ref(selection, revision.record),
                )
            )

    if source_order:
        target_rows.sort(
            key=lambda row: (row.gas_day, row.revision, row.revision_id)
        )
    else:
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
    revision_order_policy: RevisionOrderPolicy,
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
    if isinstance(revision_order_policy, RevisionOrderPolicy):
        resolved_policy = revision_order_policy
    else:
        try:
            resolved_policy = RevisionOrderPolicy(revision_order_policy)
        except (TypeError, ValueError) as exc:
            raise DemandTargetInputValidationError(
                "revision_order_policy must be a supported revision-order policy"
            ) from exc
    if (
        resolved_policy
        is RevisionOrderPolicy.DERIVED_REST_APPLICABILITY_ORDER_V1
        and source_format != "REST"
    ):
        raise DemandTargetInputValidationError(
            "DERIVED_REST_APPLICABILITY_ORDER_V1 requires the REST source format"
        )
    return _Selection(
        provider_item_id=provider_item_id,
        source_format=source_format,
        gas_day_from=gas_day_from,
        gas_day_to=gas_day_to,
        available_at_utc=available_at_utc.astimezone(UTC),
        allow_provisional_targets=allow_provisional_targets,
        revision_order_policy=resolved_policy,
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

    source_order_at_utc: datetime | None = None
    if (
        selection.revision_order_policy
        is RevisionOrderPolicy.DERIVED_REST_APPLICABILITY_ORDER_V1
    ):
        source_order_at_utc, diagnostic = _rest_order_evidence(
            record,
            available_at=available_at,
            received_at=received_at,
        )
        if diagnostic is not None:
            return None, diagnostic

    return (
        _AdmittedRevision(
            record=record,
            value_text=value_text,
            value_decimal=value_decimal,
            value_float=value_float,
            quality=quality,
            available_at=available_at,
            received_at=received_at,
            source_order_at_utc=source_order_at_utc,
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


_REST_PROVENANCE_KEYS = frozenset(
    {
        "source_format",
        "source_system",
        "hash_schema",
        "series_key",
        "region",
        "publication_id",
        "publication_name",
        "term",
        "provisional_status",
        "is_provisional",
        "applicable_for_raw",
        "applicable_at_raw",
        "applicable_at_utc",
        "applicable_at_wall_clock_naive",
        "generated_at_raw",
        "generated_at_utc",
        "generated_at_wall_clock_naive",
        "created_at_raw",
        "created_at_utc",
        "created_at_wall_clock_naive",
        "provider_timestamp_upper_bound_utc",
        "evidence_basis",
        "quality_indicator_raw",
        "quality_flag",
        "substituted_raw",
        "is_substituted",
        "value_text",
        "value_decimal",
        "value_is_blank",
        "unit",
        "received_at_utc",
        "available_at_utc",
        "ingested_at_utc",
        "published_at_utc",
        "raw_sha256",
        "source_url",
    }
)
_REST_SOURCE_CLOCK_KEYS = frozenset(
    {
        f"{prefix}_at_{suffix}"
        for prefix in ("applicable", "generated", "created")
        for suffix in ("raw", "utc", "wall_clock_naive")
    }
)


class _RestOrderEvidenceError(Exception):
    """Internal typed source-order evidence failure converted to a diagnostic."""

    def __init__(self, code: DemandTargetDiagnosticCode, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(detail)


def _rest_order_evidence(
    record: NationalGasActualDemandRecord,
    *,
    available_at: datetime,
    received_at: datetime,
) -> tuple[datetime | None, DemandTargetDiagnostic | None]:
    try:
        return (
            _rest_source_order_instant(
                record,
                available_at=available_at,
                received_at=received_at,
            ),
            None,
        )
    except _RestOrderEvidenceError as exc:
        return None, _diagnostic(exc.code, record, exc.detail)


def _rest_source_order_instant(
    record: NationalGasActualDemandRecord,
    *,
    available_at: datetime,
    received_at: datetime,
) -> datetime:
    if getattr(record, "source_format", None) != "REST":
        raise _RestOrderEvidenceError(
            DemandTargetDiagnosticCode.REST_ORDER_IDENTITY_MISMATCH,
            "source-order policy requires the REST source representation",
        )
    if getattr(record, "source_url", None) != REST_API_URL:
        raise _RestOrderEvidenceError(
            DemandTargetDiagnosticCode.REST_ORDER_IDENTITY_MISMATCH,
            "REST source URL is not the fixed official API origin",
        )
    if getattr(record, "hash_schema", None) != REST_HASH_SCHEMA:
        raise _RestOrderEvidenceError(
            DemandTargetDiagnosticCode.REST_ORDER_IDENTITY_MISMATCH,
            "REST hash schema is not the approved publication namespace",
        )
    if getattr(record, "provider_item_id", None) not in ALLOWED_PROVIDER_ITEM_IDS:
        raise _RestOrderEvidenceError(
            DemandTargetDiagnosticCode.REST_ORDER_IDENTITY_MISMATCH,
            "REST provider item is not an approved National Gas series",
        )

    provenance = getattr(record, "rest_provenance", None)
    if provenance is None:
        raise _RestOrderEvidenceError(
            DemandTargetDiagnosticCode.REST_ORDER_PROVENANCE_MISSING,
            "REST row has no persisted provenance",
        )
    if not isinstance(provenance, Mapping):
        raise _RestOrderEvidenceError(
            DemandTargetDiagnosticCode.REST_ORDER_PROVENANCE_MALFORMED,
            "persisted REST provenance is not a JSON object",
        )

    missing = _REST_PROVENANCE_KEYS.difference(provenance)
    if missing:
        clock_missing = missing.intersection(_REST_SOURCE_CLOCK_KEYS)
        raise _RestOrderEvidenceError(
            (
                DemandTargetDiagnosticCode.SOURCE_CLOCK_MISSING
                if clock_missing
                else DemandTargetDiagnosticCode.REST_ORDER_PROVENANCE_MALFORMED
            ),
            f"persisted REST provenance is missing {', '.join(sorted(missing))}",
        )

    _require_rest_identity(provenance["source_format"], "REST", "source_format")
    _require_rest_identity(
        provenance["source_system"], REST_SOURCE_SYSTEM, "source_system"
    )
    _require_rest_identity(provenance["hash_schema"], REST_HASH_SCHEMA, "hash_schema")
    _require_rest_identity(provenance["series_key"], REST_SERIES_KEY, "series_key")
    _require_rest_identity(provenance["region"], SUPPORTED_REGION, "region")
    _require_rest_identity(
        provenance["publication_id"],
        getattr(record, "provider_item_id", None),
        "publication_id",
    )
    _require_rest_identity(
        provenance["publication_name"],
        getattr(record, "label", None),
        "publication_name",
    )
    _require_rest_identity(provenance["term"], getattr(record, "term", None), "term")
    _require_rest_identity(
        provenance["provisional_status"],
        getattr(record, "provisional_status", None),
        "provisional_status",
    )
    _require_rest_identity(
        provenance["is_provisional"],
        getattr(record, "is_provisional", None),
        "is_provisional",
    )
    _require_rest_identity(
        provenance["applicable_for_raw"],
        getattr(record, "gas_day", None).isoformat(),
        "applicable_for_raw",
    )
    _require_rest_identity(
        provenance["value_text"], getattr(record, "value_text", None), "value_text"
    )
    _require_rest_identity(
        provenance["value_is_blank"],
        bool(getattr(record, "value_is_blank", False)),
        "value_is_blank",
    )
    expected_decimal = (
        None
        if getattr(record, "value_text", None) == ""
        else str(Decimal(record.value_text))
    )
    _require_rest_identity(
        provenance["value_decimal"], expected_decimal, "value_decimal"
    )
    _require_rest_identity(provenance["unit"], getattr(record, "unit", None), "unit")
    _require_rest_identity(
        provenance["raw_sha256"], getattr(record, "raw_sha256", None), "raw_sha256"
    )
    _require_rest_identity(
        provenance["source_url"], getattr(record, "source_url", None), "source_url"
    )
    _require_rest_identity(
        provenance["evidence_basis"], REST_EVIDENCE_BASIS, "evidence_basis"
    )
    _require_rest_identity(provenance["published_at_utc"], None, "published_at_utc")

    quality_raw = provenance["quality_indicator_raw"]
    if not isinstance(quality_raw, str):
        raise _RestOrderEvidenceError(
            DemandTargetDiagnosticCode.REST_ORDER_PROVENANCE_MALFORMED,
            "persisted quality_indicator_raw must be text",
        )
    expected_quality_flag = {"": "UNKNOWN", "A": "AMENDED", "S": "SUBSTITUTED"}.get(
        quality_raw
    )
    if expected_quality_flag is None:
        raise _RestOrderEvidenceError(
            DemandTargetDiagnosticCode.REST_ORDER_IDENTITY_MISMATCH,
            "persisted quality indicator is not the approved REST raw value",
        )
    _require_rest_identity(
        quality_raw, getattr(record, "quality_indicator", None) or "", "quality_indicator"
    )
    _require_rest_identity(
        provenance["quality_flag"], expected_quality_flag, "quality_flag"
    )

    substituted_raw = provenance["substituted_raw"]
    if substituted_raw not in {"", "Y", "N"}:
        raise _RestOrderEvidenceError(
            DemandTargetDiagnosticCode.REST_ORDER_PROVENANCE_MALFORMED,
            "persisted substituted_raw is not blank, Y, or N",
        )
    expected_substituted = {"": None, "Y": True, "N": False}[substituted_raw]
    _require_rest_identity(
        provenance["is_substituted"], expected_substituted, "is_substituted"
    )

    for field, record_field in (
        ("received_at_utc", "received_at_utc"),
        ("available_at_utc", "available_at_utc"),
        ("ingested_at_utc", "ingested_at_utc"),
    ):
        parsed = _parse_normalized_clock(provenance[field], field)
        actual = _aware_utc(getattr(record, record_field, None))
        if actual is None:
            raise _RestOrderEvidenceError(
                DemandTargetDiagnosticCode.REST_ORDER_IDENTITY_MISMATCH,
                f"{record_field} is not an aware datetime",
            )
        _require_rest_identity(parsed, actual, field)

    instants: dict[str, datetime] = {}
    walls: dict[str, datetime] = {}
    for prefix in ("applicable", "generated", "created"):
        raw_key = f"{prefix}_at_raw"
        raw_clock = _clock_text(provenance[raw_key], raw_key)
        raw_clock_value = _parse_offset_clock(raw_clock, raw_key)
        raw_instant = raw_clock_value.astimezone(UTC)
        normalized = _parse_normalized_clock(
            provenance[f"{prefix}_at_utc"], f"{prefix}_at_utc"
        )
        if normalized != raw_instant:
            raise _RestOrderEvidenceError(
                DemandTargetDiagnosticCode.SOURCE_CLOCK_INCONSISTENT,
                f"{prefix}_at_utc disagrees with its offset-bearing raw clock",
            )
        wall = _parse_wall_clock(
            provenance[f"{prefix}_at_wall_clock_naive"],
            f"{prefix}_at_wall_clock_naive",
        )
        if wall != raw_clock_value.replace(tzinfo=None):
            raise _RestOrderEvidenceError(
                DemandTargetDiagnosticCode.SOURCE_CLOCK_INCONSISTENT,
                f"{prefix}_at_wall_clock_naive disagrees with its raw clock",
            )
        instants[prefix] = raw_instant
        walls[prefix] = wall

    for prefix in ("applicable", "generated"):
        _require_rest_identity(
            getattr(record, f"{prefix}_at_raw", None),
            provenance[f"{prefix}_at_raw"],
            f"{prefix}_at_raw",
        )
        model_wall = getattr(record, f"{prefix}_at_naive", None)
        if (
            not isinstance(model_wall, datetime)
            or model_wall.tzinfo is not None
            or model_wall.utcoffset() is not None
        ):
            raise _RestOrderEvidenceError(
                DemandTargetDiagnosticCode.SOURCE_CLOCK_INCONSISTENT,
                f"{prefix}_at_naive must preserve the provider wall clock as naive",
            )
        _require_rest_identity(model_wall, walls[prefix], f"{prefix}_at_naive")

    if len(set(instants.values())) != 1:
        raise _RestOrderEvidenceError(
            DemandTargetDiagnosticCode.SOURCE_CLOCKS_DISAGREE,
            "applicableAt, generatedTimeStamp and createdDate are not one UTC instant",
        )
    source_order_at = instants["applicable"]
    upper_bound = _parse_normalized_clock(
        provenance["provider_timestamp_upper_bound_utc"],
        "provider_timestamp_upper_bound_utc",
    )
    if upper_bound != source_order_at:
        raise _RestOrderEvidenceError(
            DemandTargetDiagnosticCode.SOURCE_CLOCK_INCONSISTENT,
            "provider timestamp upper bound is not the consensus source instant",
        )
    if source_order_at > received_at:
        raise _RestOrderEvidenceError(
            DemandTargetDiagnosticCode.SOURCE_CLOCK_AFTER_RECEIPT,
            "source applicability instant is later than actual receipt",
        )
    if source_order_at > available_at:
        raise _RestOrderEvidenceError(
            DemandTargetDiagnosticCode.SOURCE_CLOCK_AFTER_RECEIPT,
            "source applicability instant is later than actual availability",
        )
    return source_order_at


def _require_rest_identity(actual: object, expected: object, field: str) -> None:
    if actual != expected:
        raise _RestOrderEvidenceError(
            DemandTargetDiagnosticCode.REST_ORDER_IDENTITY_MISMATCH,
            f"persisted REST {field} does not match the immutable source row",
        )


def _clock_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise _RestOrderEvidenceError(
            DemandTargetDiagnosticCode.SOURCE_CLOCK_MISSING,
            f"{field} is missing",
        )
    return value


def _parse_offset_clock(value: object, field: str) -> datetime:
    raw = _clock_text(value, field)
    try:
        parsed = datetime.fromisoformat(raw)
    except (TypeError, ValueError) as exc:
        raise _RestOrderEvidenceError(
            DemandTargetDiagnosticCode.MALFORMED_SOURCE_CLOCK,
            f"{field} is not an ISO timestamp",
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise _RestOrderEvidenceError(
            DemandTargetDiagnosticCode.NAIVE_SOURCE_CLOCK,
            f"{field} must carry an explicit UTC offset",
        )
    return parsed


def _parse_normalized_clock(value: object, field: str) -> datetime:
    parsed = _parse_offset_clock(value, field)
    if parsed.utcoffset() != timedelta(0):
        raise _RestOrderEvidenceError(
            DemandTargetDiagnosticCode.SOURCE_CLOCK_INCONSISTENT,
            f"{field} is not normalized to UTC",
        )
    return parsed.astimezone(UTC)


def _parse_wall_clock(value: object, field: str) -> datetime:
    raw = _clock_text(value, field)
    try:
        parsed = datetime.fromisoformat(raw)
    except (TypeError, ValueError) as exc:
        raise _RestOrderEvidenceError(
            DemandTargetDiagnosticCode.MALFORMED_SOURCE_CLOCK,
            f"{field} is not an ISO wall clock",
        ) from exc
    if parsed.tzinfo is not None or parsed.utcoffset() is not None:
        raise _RestOrderEvidenceError(
            DemandTargetDiagnosticCode.MALFORMED_SOURCE_CLOCK,
            f"{field} must be a naive provider wall clock",
        )
    return parsed.replace(tzinfo=None)


def _required_source_order_instant(revision: _AdmittedRevision) -> datetime:
    source_order_at = revision.source_order_at_utc
    if source_order_at is None:
        raise DemandTargetInputError(
            "source-order policy admitted a revision without source evidence"
        )
    return source_order_at


def _refuse_equal_source_order_tie(
    gas_day: date,
    revisions: Sequence[_AdmittedRevision],
) -> None:
    for previous, current in zip(revisions, revisions[1:], strict=False):
        if previous.source_order_at_utc != current.source_order_at_utc:
            continue
        raise DemandTargetAmbiguityError(
            f"ambiguous target selection for {gas_day.isoformat()}: "
            "distinct publications share one source applicability instant"
        )


def _source_ref(selection: _Selection, record: NationalGasActualDemandRecord) -> str:
    reference = f"NATIONAL_GAS:{selection.source_format}:{record.source_publication_id}"
    if (
        selection.revision_order_policy
        is RevisionOrderPolicy.DERIVED_REST_APPLICABILITY_ORDER_V1
    ):
        return f"{reference}:{selection.revision_order_policy.value}"
    return reference


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
    if revision.source_order_at_utc is None:
        revision_order_basis = REVISION_ORDER_BASIS
        source_order_method_basis = None
    else:
        revision_order_basis = (
            RevisionOrderPolicy.DERIVED_REST_APPLICABILITY_ORDER_V1.value
        )
        source_order_method_basis = revision_order_basis
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
        revision_order_basis=revision_order_basis,
        selected=selected,
        source_order_at_utc=revision.source_order_at_utc,
        source_order_method_basis=source_order_method_basis,
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
