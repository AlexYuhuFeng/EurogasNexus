"""Pure REST-only projection of National Gas actual-demand revisions.

No API, SQL, model fit, write or CSV ingestion occurs here.  Only stored REST
NTS actual-demand rows in mscm, received on or before an explicit aware cutoff,
become research targets.  Exact provider ``value_text`` is retained as evidence;
``DemandTargetRow.value`` is only a float approximation.  Amendment ``A`` is an
annotation, not proof, so accepted source actual rows are ``PROVISIONAL`` and
never final.  Blank is never zero.  Unknown quality, provisionality and zero
require explicit opt-ins; substitution needs a future policy and is refused.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum

from eurogas_nexus.domain.ontology.vocabulary import DemandTargetQuality, TargetScope
from eurogas_nexus.domain.research.weather_demand import DemandTargetRow

MAX_TARGET_VALUE = Decimal("1000000000")
_DECIMAL_RE = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?\Z")
_NEVER = datetime.min.replace(tzinfo=UTC)
# Approved National Gas REST NTS actual-demand catalogue.
_APPROVED = {
    "PUBOB637": ("D+1", "PROVISIONAL_INITIAL", True),
    "PUBOB652": ("D+6", "UNRESOLVED_D_PLUS_6", None),
}


class DemandInputError(ValueError):
    """Base refusal for an invalid projection or ambiguous rows."""

    code = "DEMAND_INPUT_ERROR"


class DemandInputContractError(DemandInputError):
    """The arguments violate the frozen contract."""

    code = "DEMAND_INPUT_CONTRACT_ERROR"


class AmbiguousDemandTargetError(DemandInputError):
    """Equally available conflicting revisions cannot be ordered silently."""

    code = "AMBIGUOUS_DEMAND_TARGET"


class DemandInputDiagnosticCode(StrEnum):
    """Stable reasons a source row did not become a demand target."""

    NON_REST_SOURCE = "NON_REST_SOURCE"
    WRONG_REGION = "WRONG_REGION"
    WRONG_UNIT = "WRONG_UNIT"
    UNAPPROVED_ITEM = "UNAPPROVED_ITEM"
    MALFORMED_RECORD = "MALFORMED_RECORD"
    RECEIVED_AFTER_CUTOFF = "RECEIVED_AFTER_CUTOFF"
    BLANK_VALUE = "BLANK_VALUE"
    ZERO_VALUE = "ZERO_VALUE"
    VALUE_OUT_OF_RANGE = "VALUE_OUT_OF_RANGE"
    UNKNOWN_QUALITY = "UNKNOWN_QUALITY"
    PROVISIONAL_NOT_ADMITTED = "PROVISIONAL_NOT_ADMITTED"
    SUBSTITUTED_NOT_SUPPORTED = "SUBSTITUTED_NOT_SUPPORTED"


@dataclass(frozen=True)
class DemandInputDiagnostic:
    """One rejected row, without claiming it is absent upstream."""

    code: DemandInputDiagnosticCode
    message: str
    record_id: str | None = None
    gas_day: date | None = None


@dataclass(frozen=True)
class RestDemandTargetEvidence:
    """Exact source evidence retained beside the approximate target value."""

    revision_id: str
    record_id: str
    source_publication_id: str
    provider_item_id: str
    term: str
    value_text: str
    value_decimal: Decimal
    quality_indicator_raw: str
    provisional_status: str
    is_provisional: bool | None
    received_at_utc: datetime
    provider_declared_clock_max: datetime | None


@dataclass(frozen=True)
class RestDemandTargetBundle:
    """Frozen admitted targets, exact evidence and row diagnostics."""

    targets: tuple[DemandTargetRow, ...]
    diagnostics: tuple[DemandInputDiagnostic, ...]
    evidence: tuple[RestDemandTargetEvidence, ...]


@dataclass(frozen=True)
class _Candidate:
    gas_day: date
    available_at: datetime
    received_at: datetime
    clock_max: datetime | None
    item: str
    term: str
    value_text: str
    value: Decimal
    quality_raw: str
    provisional_status: str
    is_provisional: bool | None
    record_id: str
    publication_id: str


def _text(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _utc(value: object, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise DemandInputContractError(f"{field_name} must be an aware UTC datetime")
    return value.astimezone(UTC)


def _diag(code: DemandInputDiagnosticCode, message: str, row: object) -> DemandInputDiagnostic:
    day = getattr(row, "gas_day", None)
    return DemandInputDiagnostic(
        code=code,
        message=message,
        record_id=_text(getattr(row, "record_id", None)),
        gas_day=day if isinstance(day, date) and not isinstance(day, datetime) else None,
    )


def _parse_clock(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(UTC)


def _provenance_clocks(provenance: object) -> tuple[datetime, ...]:
    if not isinstance(provenance, Mapping):
        return ()
    names = (
        "received_at_utc",
        "retrieved_at_utc",
        "available_at_utc",
        "provider_timestamp_upper_bound_utc",
        "applicable_at_utc",
        "generated_at_utc",
        "created_at_utc",
    )
    clocks: list[datetime] = []
    for name in names:
        clock = _parse_clock(provenance.get(name))
        if clock is not None:
            clocks.append(clock)
    return tuple(clocks)


def _stored_utc(value: object, provenance: object) -> datetime | None:
    """Normalize a stored UTC value; never guess for a naive SQLite value."""
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is not None and value.utcoffset() is not None:
        return value.astimezone(UTC)
    if value.tzinfo is not None:
        return None
    naive_utc = value.replace(tzinfo=UTC)
    return naive_utc if naive_utc in _provenance_clocks(provenance) else None


def _clock_max(provenance: object) -> datetime | None:
    if not isinstance(provenance, Mapping):
        return None
    bound = _parse_clock(provenance.get("provider_timestamp_upper_bound_utc"))
    if bound is not None:
        return bound
    clocks = [
        _parse_clock(provenance.get(name))
        for name in ("applicable_at_utc", "generated_at_utc", "created_at_utc")
    ]
    present = [clock for clock in clocks if clock is not None]
    return max(present) if present else None


def _project_one(
    row: object,
    *,
    cutoff: datetime,
    allow_unknown_quality: bool,
    allow_provisional: bool,
    allow_zero: bool,
) -> _Candidate | DemandInputDiagnostic:
    bad = DemandInputDiagnosticCode
    if getattr(row, "source_format", None) != "REST":
        return _diag(bad.NON_REST_SOURCE, "only stored REST rows are in scope", row)
    if getattr(row, "region", None) != "GB_NTS":
        return _diag(bad.WRONG_REGION, "only GB_NTS rows are accepted", row)
    if (_text(getattr(row, "unit", None)) or "").lower() != "mscm":
        return _diag(bad.WRONG_UNIT, "only native mscm rows are accepted", row)
    item = _text(getattr(row, "provider_item_id", None))
    series = _APPROVED.get(item or "")
    if series is None:
        return _diag(bad.UNAPPROVED_ITEM, "item is not an approved NTS series", row)
    expected_term, expected_status, expected_provisional = series
    term = _text(getattr(row, "term", None)) or expected_term
    if term != expected_term:
        return _diag(bad.MALFORMED_RECORD, "provider item and term disagree", row)
    gas_day = getattr(row, "gas_day", None)
    if (
        not isinstance(gas_day, date)
        or isinstance(gas_day, datetime)
        or not date(2000, 1, 1) <= gas_day <= date(2100, 12, 31)
    ):
        return _diag(bad.MALFORMED_RECORD, "gas_day is not a supported date", row)
    record_id = _text(getattr(row, "record_id", None))
    publication_id = _text(getattr(row, "source_publication_id", None))
    if record_id is None or publication_id is None:
        return _diag(bad.MALFORMED_RECORD, "record identities are required", row)
    provenance = getattr(row, "rest_provenance", None)
    received_raw = getattr(row, "received_at_utc", None)
    received = _stored_utc(received_raw, provenance)
    if received is None:
        if isinstance(received_raw, datetime) and received_raw.tzinfo is None:
            return _diag(
                bad.MALFORMED_RECORD,
                "naive receipt lacks explicit REST provenance UTC crosscheck",
                row,
            )
        return _diag(bad.MALFORMED_RECORD, "stored actual receipt must be aware UTC", row)
    available_raw = getattr(row, "available_at_utc", None)
    available = _stored_utc(available_raw, provenance)
    if available is None:
        if isinstance(available_raw, datetime) and available_raw.tzinfo is None:
            return _diag(
                bad.MALFORMED_RECORD,
                "naive availability lacks explicit REST provenance UTC crosscheck",
                row,
            )
        return _diag(bad.MALFORMED_RECORD, "stored availability must be aware UTC", row)
    if available < received:
        return _diag(bad.MALFORMED_RECORD, "stored availability cannot precede stored receipt", row)
    if received > cutoff:
        return _diag(bad.RECEIVED_AFTER_CUTOFF, "local receipt is after the cutoff", row)
    if available > cutoff:
        return _diag(bad.RECEIVED_AFTER_CUTOFF, "stored availability is after the cutoff", row)
    value_text = getattr(row, "value_text", None)
    if not isinstance(value_text, str):
        return _diag(bad.MALFORMED_RECORD, "value_text must be exact provider text", row)
    blank = getattr(row, "value_is_blank", False)
    if blank is True and value_text != "":
        return _diag(bad.MALFORMED_RECORD, "non-empty value cannot be marked blank", row)
    if blank is True or value_text.strip() == "":
        return _diag(bad.BLANK_VALUE, "blank has no physical zero interpretation", row)
    if (
        value_text != value_text.strip()
        or len(value_text) > 64
        or _DECIMAL_RE.fullmatch(value_text) is None
    ):
        return _diag(bad.MALFORMED_RECORD, "value_text is not exact decimal text", row)
    try:
        value = Decimal(value_text)
    except InvalidOperation:  # pragma: no cover - regex excludes this
        return _diag(bad.MALFORMED_RECORD, "value_text is not a decimal", row)
    if not value.is_finite() or not Decimal(0) <= value <= MAX_TARGET_VALUE:
        return _diag(bad.VALUE_OUT_OF_RANGE, "value is outside the supported range", row)
    if value == 0 and not allow_zero:
        return _diag(bad.ZERO_VALUE, "zero admission requires allow_zero=True", row)

    quality = getattr(row, "quality_indicator", None)
    quality = "" if quality is None else quality
    if not isinstance(quality, str):
        return _diag(bad.MALFORMED_RECORD, "quality indicator must be text", row)
    substituted = provenance.get("substituted_raw") if isinstance(provenance, Mapping) else None
    if substituted == "Y" or (
        isinstance(provenance, Mapping) and provenance.get("is_substituted") is True
    ):
        return _diag(bad.SUBSTITUTED_NOT_SUPPORTED, "substitution is not implemented", row)
    if quality.upper() == "S":
        return _diag(bad.SUBSTITUTED_NOT_SUPPORTED, "substitution is not implemented", row)
    if quality != "A" and not allow_unknown_quality:
        return _diag(bad.UNKNOWN_QUALITY, "unknown quality requires opt-in", row)
    if not allow_provisional:
        return _diag(bad.PROVISIONAL_NOT_ADMITTED, "provisionality requires opt-in", row)
    raw_provisional = getattr(row, "is_provisional", None)
    return _Candidate(
        gas_day=gas_day,
        available_at=available,
        received_at=received,
        clock_max=_clock_max(provenance),
        item=item or "",
        term=term,
        value_text=value_text,
        value=value,
        quality_raw=quality,
        provisional_status=_text(getattr(row, "provisional_status", None)) or expected_status,
        is_provisional=(
            raw_provisional if isinstance(raw_provisional, bool) else expected_provisional
        ),
        record_id=record_id,
        publication_id=publication_id,
    )


def _key(candidate: _Candidate) -> tuple[object, ...]:
    return (
        candidate.gas_day,
        candidate.available_at,
        candidate.clock_max or _NEVER,
        candidate.item,
        candidate.value_text,
        candidate.record_id,
    )


def project_rest_demand_targets(
    records: Iterable[object],
    *,
    cutoff: datetime,
    allow_unknown_quality: bool = False,
    allow_provisional: bool = False,
    allow_zero: bool = False,
) -> RestDemandTargetBundle:
    """Project stored REST revisions to cutoff-safe typed demand targets.

    Availability is the stored actual ``available_at_utc``, no earlier than the
    stored receipt and no later than the cutoff.  Equal availability/clock
    evidence with different values for one approved series and gas day raises a
    typed ambiguity instead of choosing a hash.  Revision ordinals are
    deterministic ordered positions.
    """

    cutoff = _utc(cutoff, "cutoff")
    for name, flag in (
        ("allow_unknown_quality", allow_unknown_quality),
        ("allow_provisional", allow_provisional),
        ("allow_zero", allow_zero),
    ):
        if not isinstance(flag, bool):
            raise DemandInputContractError(f"{name} must be an explicit boolean")
    if isinstance(records, (str, bytes, bytearray)):
        raise DemandInputContractError("records must be an iterable of stored rows")
    try:
        iterator = iter(records)
    except TypeError as exc:
        raise DemandInputContractError("records must be an iterable of stored rows") from exc

    candidates: list[_Candidate] = []
    diagnostics: list[DemandInputDiagnostic] = []
    seen: dict[tuple[str, str], _Candidate] = {}
    for index, row in enumerate(iterator):
        if index >= 10_000:
            raise DemandInputContractError("input exceeds 10000 stored rows")
        projected = _project_one(
            row,
            cutoff=cutoff,
            allow_unknown_quality=allow_unknown_quality,
            allow_provisional=allow_provisional,
            allow_zero=allow_zero,
        )
        if isinstance(projected, DemandInputDiagnostic):
            diagnostics.append(projected)
            continue
        identity = (projected.record_id, projected.publication_id)
        if identity in seen and seen[identity] != projected:
            raise AmbiguousDemandTargetError("one revision identity has conflicting content")
        if identity not in seen:
            seen[identity] = projected
            candidates.append(projected)

    if len({candidate.item for candidate in candidates}) > 1:
        raise DemandInputContractError("select one provider item; D+1 and D+6 cannot be mixed")

    grouped: dict[tuple[str, date], list[_Candidate]] = {}
    for candidate in candidates:
        grouped.setdefault((candidate.item, candidate.gas_day), []).append(candidate)
    ordinals: dict[_Candidate, int] = {}
    for group in grouped.values():
        ordered = sorted(group, key=_key)
        for previous, current in zip(ordered, ordered[1:], strict=False):
            if (
                previous.available_at == current.available_at
                and previous.clock_max == current.clock_max
                and previous.value_text != current.value_text
            ):
                raise AmbiguousDemandTargetError(
                    f"equally available conflicting revisions for {current.gas_day.isoformat()}"
                )
        ordinals.update({candidate: index for index, candidate in enumerate(ordered, 1)})

    targets: list[DemandTargetRow] = []
    evidence: list[RestDemandTargetEvidence] = []
    for candidate in sorted(candidates, key=_key):
        targets.append(
            DemandTargetRow(
                gas_day=candidate.gas_day,
                scope=TargetScope.GB_NTS_THROUGHPUT,
                region="GB_NTS",
                unit="mscm",
                value=float(candidate.value),
                quality=DemandTargetQuality.PROVISIONAL,
                revision=ordinals[candidate],
                revision_id=candidate.publication_id,
                available_at=candidate.available_at,
                source_ref=candidate.record_id,
            )
        )
        evidence.append(
            RestDemandTargetEvidence(
                revision_id=candidate.publication_id,
                record_id=candidate.record_id,
                source_publication_id=candidate.publication_id,
                provider_item_id=candidate.item,
                term=candidate.term,
                value_text=candidate.value_text,
                value_decimal=candidate.value,
                quality_indicator_raw=candidate.quality_raw,
                provisional_status=candidate.provisional_status,
                is_provisional=candidate.is_provisional,
                received_at_utc=candidate.received_at,
                provider_declared_clock_max=candidate.clock_max,
            )
        )
    return RestDemandTargetBundle(
        targets=tuple(targets), diagnostics=tuple(diagnostics), evidence=tuple(evidence)
    )
