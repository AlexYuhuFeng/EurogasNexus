"""Pure parser and canonical mapping for the EEX TTF NGP reference-index CSV.

Official source page (EEX gas market transparency):
``https://www.eex.com/en/markets/natural-gas/gas-market-transparency``. The page links the
operator-downloadable file ``https://gasandregistry.eex.com/Gas/NGP/TTF_NGP_15_Mins.csv``. A
bounded read verified a UTF-8 CSV with BOM, semicolon delimiter and this header::

    Gasday;IndexValue (€/MWh);IndexVolume (MWh);Status;Timestamp Let

with rows shaped ``DD/MM/YYYY;decimal;decimal;Final NGP|Temporary NGP;DD/MM/YYYY HH:MM``.

What this module is — and deliberately is not:

- It is a *pure* parser: no network I/O, no database, no scheduler, no automatic writes and no
  CLI default change. The caller supplies the file text and receives raw-preserving records
  plus the canonical ``market_observations``-shaped rows the existing public-source ingestion
  path (``scripts/ops/ingest_public_sources.py``) persists once the gates below are satisfied.
- The values are EEX volume-weighted **reference indices**, marked final or temporary. They are
  never executable bid/ask quotes, and a missing or zero-volume value is never a tradable zero.
- The zone of the ``Timestamp Let`` column is **not established** against official EEX
  methodology in this repository. Unless the caller supplies an explicitly *evidenced* governed
  timezone contract, records keep the raw timestamp and are returned as
  ``pending_source_timezone``; canonical conversion is refused rather than stamped with the host
  machine's zone (the M1-P0 rule, ``docs/data/SOURCE_TIMEZONE_CONTRACT.md``).
- A wall clock that the proven zone makes ambiguous (DST fall-back) or nonexistent (DST
  spring-forward gap) has no official EEX fold/gap rule here, so the row is *refused* with a
  stable reason (``ambiguous_local_timestamp`` / ``nonexistent_local_timestamp``) instead of
  being folded, shifted or host-resolved. The shared timezone module is not changed.
- The delivery meaning of the ``Gasday`` column is a *second, independent* unproven contract:
  canonical mapping requires a separately evidenced gas-day calendar contract naming an existing
  registered calendar id, and refuses by default with ``unproven_gas_day_calendar``. Publication
  timezone evidence is never treated as delivery calendar proof.
- Canonical rows carry no unearned freshness or quality: an explicit
  ``freshness="unknown"`` (the accepted unknown representation of
  :class:`eurogas_nexus.domain.observations.market.ObservationFreshness`) and
  ``quality_score=0.0`` marked ``quality_assessed: false`` in metadata, because no source
  freshness/quality expectation is proven. Values whose exact ``Decimal`` overflows the
  canonical Float price column are refused (``index_value_float_overflow``), never written as
  ``inf``.
- EEX is registered as a licensed, entitlement-controlled source whose certification is
  unverified; this adapter neither certifies rights nor enables scheduled live ingestion.
  Evidence and limits: ``docs/data/EEX_NGP_SOURCE_CONTRACT.md``.
"""

from __future__ import annotations

import csv
import io
import math
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any
from zoneinfo import ZoneInfo

from eurogas_nexus.domain.ingestion.source_timezone import (
    SourceTimezoneContract,
    contract_for,
    parse_source_instant,
    resolve_payload_zone,
)
from eurogas_nexus.domain.market.gas_day import GAS_DAY_CALENDARS, gas_day_start_for_date
from eurogas_nexus.domain.observations.market import ObservationFreshness

SOURCE_SYSTEM = "EEX"
SOURCE_DATASET = "ttf-ngp-15min"
SOURCE_REFERENCE = "eex-ttf-ngp-15-mins"
SOURCE_PAGE_URL = "https://www.eex.com/en/markets/natural-gas/gas-market-transparency"
SOURCE_FILE_URL = "https://gasandregistry.eex.com/Gas/NGP/TTF_NGP_15_Mins.csv"
MARKET_VENUE = "EEX"
HUB = "TTF"
PRODUCT = "TTF NGP"
UNIT = "EUR/MWh"
CURRENCY = "EUR"
DELIMITER = ";"

#: The header the official file carried when the source shape was verified (2026-09-29). Compared
#: after BOM removal, whitespace collapsing, case folding and ``€`` -> ``EUR``; order and column
#: count are part of the check, because a renamed or reordered column must not be mapped by guess.
EXPECTED_HEADER = (
    "Gasday",
    "IndexValue (€/MWh)",
    "IndexVolume (MWh)",
    "Status",
    "Timestamp Let",
)

STATUS_FINAL = "final"
STATUS_TEMPORARY = "temporary"
STATUS_TOKENS = {"final ngp": STATUS_FINAL, "temporary ngp": STATUS_TEMPORARY}


def _normalize_header_cell(cell: str) -> str:
    """Normalize one header cell for the strict comparison (BOM, ``€``, spacing, case)."""

    text = cell.replace("\ufeff", "").replace("€", "EUR")
    return re.sub(r"\s+", " ", text).strip().casefold()


_EXPECTED_HEADER_NORMALIZED = tuple(_normalize_header_cell(cell) for cell in EXPECTED_HEADER)
_GAS_DAY_PATTERN = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$")
_TIMESTAMP_PATTERN = re.compile(r"^(\d{2})/(\d{2})/(\d{4}) (\d{2}):(\d{2})$")
#: The verified file shape says ``decimal``; a plain decimal keeps locale/format surprises
#: (comma decimals, separators, exponent notation) out instead of silently reinterpreting them.
_DECIMAL_PATTERN = re.compile(r"^[+-]?(?:\d+(?:\.\d+)?|\.\d+)$")


class EexNgpParseError(ValueError):
    """A payload that cannot be trusted as a whole, or a canonical conversion that is refused.

    ``code`` is stable so an operator or test can assert *which* rule refused. Row-level problems
    that leave the payload interpretable are returned as :class:`EexNgpRowRejection` instead.
    """

    def __init__(self, code: str, message: str, *, row_number: int | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.row_number = row_number


class EexNgpNormalization(StrEnum):
    """Whether a record could be placed in time under an evidenced timezone contract."""

    CANONICAL = "canonical"
    PENDING_SOURCE_TIMEZONE = "pending_source_timezone"


@dataclass(frozen=True)
class EexNgpRecord:
    """One EEX TTF NGP row with its raw source fields preserved.

    ``timestamp_local`` is the published wall-clock value, not an instant: it is only placed in
    time (``publication_time_utc``) when a governed timezone contract proves the zone.
    """

    row_number: int
    gas_day: date
    gas_day_raw: str
    timestamp_raw: str
    timestamp_local: datetime
    publication_time_utc: datetime | None
    normalization_status: EexNgpNormalization
    status: str
    status_raw: str
    index_value: Decimal | None
    index_value_raw: str
    index_volume: Decimal | None
    index_volume_raw: str
    observation_id: str
    source_record_id: str

    @property
    def is_provisional(self) -> bool:
        """Whether the source marked the row ``Temporary NGP`` (never final)."""

        return self.status == STATUS_TEMPORARY

    @property
    def unavailable_reason(self) -> str | None:
        """Why the row cannot yield a price: zero/missing volume or a missing index value.

        A zero or missing volume makes the volume-weighted index unavailable; it must not be
        turned into a zero price, even when the source itself printed ``0`` as the index value.
        """

        if self.index_value is None:
            return "missing_index_value"
        if self.index_volume is None:
            return "missing_index_volume"
        if self.index_volume == 0:
            return "zero_volume"
        return None

    @property
    def price_available(self) -> bool:
        """Whether the row carries a usable index value (some volume traded)."""

        return self.unavailable_reason is None


@dataclass(frozen=True)
class EexNgpRowRejection:
    """A row that could not be validated; the payload stays interpretable and the row is visible."""

    row_number: int
    reason: str
    detail: str


@dataclass(frozen=True)
class EexNgpGasDayCalendarContract:
    """A separately evidenced delivery calendar for the ``Gasday`` column.

    The ``Gasday`` column is a *delivery-day* label. This repository has not verified that EEX
    labels its NGP gas days on the CAM convention, so canonical mapping accepts a calendar only
    through this contract: an existing registered calendar id (see
    :data:`eurogas_nexus.domain.market.gas_day.GAS_DAY_CALENDARS`) plus the evidence that ties
    this source to it. This is deliberately *not* derivable from the ``Timestamp Let`` timezone
    evidence: publication timing and delivery calendar are independent questions, and neither
    contract's caller-supplied text certifies official EEX approval by itself.

    Attributes:
        calendar_id: An existing calendar version id from ``GAS_DAY_CALENDARS``.
        evidence: Where the source-to-calendar claim comes from; must not be blank.
    """

    calendar_id: str
    evidence: str


@dataclass(frozen=True)
class EexNgpParseResult:
    """The parsed payload: preserved records, row-level rejections and the contract used."""

    records: tuple[EexNgpRecord, ...]
    rejections: tuple[EexNgpRowRejection, ...]
    retrieved_at_utc: datetime
    timezone_contract: SourceTimezoneContract
    blank_lines_skipped: int = 0


class _RowRefusal(Exception):
    """Internal: one row failed validation; its reason code and detail are recorded."""

    def __init__(self, reason: str, detail: str) -> None:
        super().__init__(detail)
        self.reason = reason
        self.detail = detail


def parse_eex_ttf_ngp_csv(
    csv_text: str,
    *,
    retrieved_at_utc: datetime | None = None,
    timezone_contract: SourceTimezoneContract | None = None,
) -> EexNgpParseResult:
    """Parse one operator-supplied EEX TTF NGP CSV without network or database access.

    Args:
        csv_text: The file text, BOM included or not.
        retrieved_at_utc: When the operator retrieved the file. Must be timezone-aware; a naive
            value is refused, because reading a clock as UTC is the assumption this adapter
            refuses to make. Defaults to the current UTC time.
        timezone_contract: An explicitly evidenced governed contract for ``Timestamp Let``.
            Defaults to the repository declaration, which proves no zone yet: records then carry
            ``pending_source_timezone`` and canonical conversion is refused.

    Returns:
        Records preserving every raw source field, row-level rejections, and the contract used.

    Raises:
        EexNgpParseError: For a payload-level defect (empty payload, unverified header, duplicate
            key), a misuse of the governed contract, or a naive retrieval timestamp.
    """

    retrieved_at = _resolve_retrieved_at(retrieved_at_utc)
    contract = _resolve_timezone_contract(timezone_contract)
    zone = resolve_payload_zone(contract, None)

    rows = _read_csv_rows(csv_text)
    _validate_header(rows[0][1])

    records: list[EexNgpRecord] = []
    rejections: list[EexNgpRowRejection] = []
    blank_lines_skipped = 0
    seen: dict[tuple[date, datetime, str], int] = {}
    for row_number, row in rows[1:]:
        if not any(cell.strip() for cell in row):
            blank_lines_skipped += 1
            continue
        try:
            record = _parse_row(row_number, row, contract=contract, zone=zone)
        except _RowRefusal as refusal:
            rejections.append(
                EexNgpRowRejection(
                    row_number=row_number, reason=refusal.reason, detail=refusal.detail
                )
            )
            continue
        key = (record.gas_day, record.timestamp_local, record.status)
        duplicate_of = seen.get(key)
        if duplicate_of is not None:
            raise EexNgpParseError(
                "duplicate_observation_key",
                (
                    f"rows {duplicate_of} and {row_number} repeat gas day "
                    f"{record.gas_day.isoformat()}, timestamp {record.timestamp_raw!r} and status "
                    f"{record.status_raw!r}; refusing to deduplicate a same-key revision silently."
                ),
                row_number=row_number,
            )
        seen[key] = row_number
        records.append(record)

    return EexNgpParseResult(
        records=tuple(records),
        rejections=tuple(rejections),
        retrieved_at_utc=retrieved_at,
        timezone_contract=contract,
        blank_lines_skipped=blank_lines_skipped,
    )


def eex_ttf_ngp_market_observations(
    result: EexNgpParseResult,
    *,
    gas_day_calendar_contract: EexNgpGasDayCalendarContract | None = None,
) -> list[dict[str, Any]]:
    """Canonical ``market_observations``-shaped rows for a fully canonical, fully priced payload.

    Two independent evidences must both be present, and neither substitutes for the other:

    - every record must already be placed in time through the evidenced publication-timezone
      contract used by :func:`parse_eex_ttf_ngp_csv`;
    - ``gas_day_calendar_contract`` must supply the evidenced delivery calendar for the
      ``Gasday`` column (:class:`EexNgpGasDayCalendarContract`); without one the payload is
      refused with ``unproven_gas_day_calendar``, because publication-timezone evidence proves
      nothing about which delivery day the source labels ``Gasday``.

    The payload is refused whole — never partially written, never filled with fabricated zeros —
    when the calendar contract is missing, unattested or unregistered, when rows were rejected,
    when any record is still pending a source timezone, when a value overflows the canonical
    Float column (``index_value_float_overflow``), or when no row carries a usable price.
    Records with zero or missing volume stay visible on the parse result and are deliberately
    not mapped to a price observation.

    Rows are returned ``freshness="unknown"`` with an explicitly unassessed ``quality_score``
    (0.0 plus ``quality_assessed: false`` in metadata): no source freshness or quality
    expectation is proven, so none is awarded.
    """

    calendar_contract = _resolve_gas_day_calendar_contract(gas_day_calendar_contract)
    if result.rejections:
        raise EexNgpParseError(
            "rejected_rows_present",
            (
                f"{len(result.rejections)} row(s) were rejected; refusing to canonicalize a "
                "partial payload."
            ),
        )
    pending = [
        record.observation_id
        for record in result.records
        if record.normalization_status is not EexNgpNormalization.CANONICAL
    ]
    if pending:
        raise EexNgpParseError(
            "unproven_publication_timezone",
            (
                "the Timestamp Let zone is not proven for "
                f"{', '.join(pending[:3])}; canonical conversion is refused rather than stamped "
                "with the host machine's zone."
            ),
        )
    rows: list[dict[str, Any]] = []
    for record in result.records:
        index_value = record.index_value
        publication_time_utc = record.publication_time_utc
        if not record.price_available or index_value is None or publication_time_utc is None:
            continue
        rows.append(
            _observation_row(
                record,
                index_value=index_value,
                publication_time_utc=publication_time_utc,
                retrieved_at_utc=result.retrieved_at_utc,
                timezone_evidence=result.timezone_contract.evidence,
                gas_day_calendar_contract=calendar_contract,
            )
        )
    if not rows:
        raise EexNgpParseError(
            "no_priced_rows",
            (
                "no row carried a usable index value with positive volume; refusing to treat an "
                "all-unavailable payload as empty data."
            ),
        )
    return rows


def _observation_row(
    record: EexNgpRecord,
    *,
    index_value: Decimal,
    publication_time_utc: datetime,
    retrieved_at_utc: datetime,
    timezone_evidence: str,
    gas_day_calendar_contract: EexNgpGasDayCalendarContract,
) -> dict[str, Any]:
    calendar_id = gas_day_calendar_contract.calendar_id
    return {
        "observation_id": record.observation_id,
        "market_venue": MARKET_VENUE,
        "product": PRODUCT,
        "price": _canonical_price(record, index_value),
        "unit": UNIT,
        "currency": CURRENCY,
        "period_start_utc": gas_day_start_for_date(record.gas_day, calendar=calendar_id),
        "period_end_utc": gas_day_start_for_date(
            record.gas_day + timedelta(days=1), calendar=calendar_id
        ),
        "observed_at_utc": publication_time_utc,
        "source_system": SOURCE_SYSTEM,
        "source_reference": SOURCE_REFERENCE,
        "source_record_id": record.source_record_id,
        # No proven source freshness/quality expectation: unknown, not unearned "live"/1.0.
        "freshness": ObservationFreshness.UNKNOWN.value,
        "quality_score": 0.0,
        "research_only": True,
        "metadata_json": {
            "source_system": SOURCE_SYSTEM,
            "source_reference": SOURCE_REFERENCE,
            "source_dataset": SOURCE_DATASET,
            "source_page_url": SOURCE_PAGE_URL,
            "source_file_url": SOURCE_FILE_URL,
            # EEX live data, never the EEX_Sim simulator family.
            "simulated": False,
            "hub": HUB,
            "market_area": HUB,
            "product_detail": "TTF NGP volume-weighted reference index",
            "index": "NGP",
            "index_type": "volume_weighted_reference_index",
            # A reference index, not a future, a spot quote, or an executable bid/ask.
            "contract_type": "index",
            "price_type": "index",
            "price_semantics": "reference_index_never_an_executable_bid_or_ask",
            "executable_quote": False,
            # Raw gas day, revision status, publication vs ingestion semantics.
            "gas_day": record.gas_day.isoformat(),
            "gas_day_raw": record.gas_day_raw,
            # The delivery calendar is a separately evidenced contract, never inferred from the
            # publication timestamp evidence above.
            "gas_day_calendar": calendar_id,
            "gas_day_calendar_evidence": gas_day_calendar_contract.evidence,
            "period_basis": "gas_day_declared_calendar",
            "revision_status": record.status,
            "revision_status_raw": record.status_raw,
            "provisional": record.is_provisional,
            "publication_timestamp_raw": record.timestamp_raw,
            "publication_time_utc": publication_time_utc.isoformat(),
            "publication_timezone_evidence": timezone_evidence,
            "retrieved_at_utc": retrieved_at_utc.isoformat(),
            # Freshness/quality were not assessed against a proven source expectation.
            "freshness_basis": "no_proven_source_freshness_expectation",
            "quality_assessed": False,
            "quality_score_basis": "unassessed",
            "index_value_raw": record.index_value_raw,
            "index_value_exact": str(index_value),
            "index_volume_raw": record.index_volume_raw,
            "index_volume_mwh_exact": str(record.index_volume),
            # Licensed source: nothing in this adapter certifies rights for live ingestion.
            "entitlement_scope": "licensed",
            "license_controlled": True,
            "certification_stage": "unverified",
        },
    }


def _parse_row(
    row_number: int,
    row: list[str],
    *,
    contract: SourceTimezoneContract,
    zone: ZoneInfo | None,
) -> EexNgpRecord:
    if len(row) != len(EXPECTED_HEADER):
        raise _RowRefusal(
            "malformed_row",
            (f"expected {len(EXPECTED_HEADER)} semicolon-separated fields, found {len(row)}"),
        )
    gas_day_raw, value_raw, volume_raw, status_raw, timestamp_raw = (cell.strip() for cell in row)
    gas_day = _parse_gas_day(gas_day_raw)
    if gas_day is None:
        raise _RowRefusal("invalid_gas_day", f"gas day {gas_day_raw!r} is not DD/MM/YYYY")
    timestamp_local = _parse_local_timestamp(timestamp_raw)
    if timestamp_local is None:
        raise _RowRefusal(
            "invalid_timestamp", f"timestamp {timestamp_raw!r} is not DD/MM/YYYY HH:MM"
        )
    status = STATUS_TOKENS.get(_normalize_token(status_raw))
    if status is None:
        raise _RowRefusal("unknown_status", f"status {status_raw!r} is not a known NGP status")
    index_value = _parse_decimal(value_raw, field="index_value")
    index_volume = _parse_decimal(volume_raw, field="index_volume")
    if index_volume is not None and index_volume < 0:
        raise _RowRefusal("negative_index_volume", f"index volume {volume_raw!r} is negative")

    publication_time_utc = None
    if zone is not None:
        # Reuse the one timezone rule (M1-P0) for unique wall clocks; the DST edges are refused
        # here rather than folded/shifted, because no official EEX fold/gap rule is established
        # (and the shared parser is not changed for every other source).
        publication_time_utc = _place_publication_instant(
            timestamp_local, contract=contract, zone=zone
        )
    normalization_status = (
        EexNgpNormalization.CANONICAL
        if publication_time_utc is not None
        else EexNgpNormalization.PENDING_SOURCE_TIMEZONE
    )
    record_key = f"{gas_day.isoformat()}-{timestamp_local.strftime('%Y%m%dT%H%M')}-{status}"
    return EexNgpRecord(
        row_number=row_number,
        gas_day=gas_day,
        gas_day_raw=gas_day_raw,
        timestamp_raw=timestamp_raw,
        timestamp_local=timestamp_local,
        publication_time_utc=publication_time_utc,
        normalization_status=normalization_status,
        status=status,
        status_raw=status_raw,
        index_value=index_value,
        index_value_raw=value_raw,
        index_volume=index_volume,
        index_volume_raw=volume_raw,
        observation_id=f"eex-ngp-ttf-{record_key}",
        source_record_id=record_key,
    )


def _place_publication_instant(
    timestamp_local: datetime,
    *,
    contract: SourceTimezoneContract,
    zone: ZoneInfo,
) -> datetime:
    """Place one wall clock in the proven zone, refusing DST-ambiguous and DST-gap wall times.

    The round trip probes both folds (``fold=0``/``fold=1``) of the naive wall clock: an instant
    is admissible only when converting it back from UTC lands on the same wall clock. A wall
    clock that round-trips for no fold does not exist (spring-forward gap); one that round-trips
    for both folds to *different* instants occurs twice (fall-back hour). ``zoneinfo`` would
    silently shift the former forward and fold the latter to ``fold=0``; that is not an official
    EEX rule for ``Timestamp Let``, so both are refused as row-level, stable reasons.
    """

    round_tripped = [
        timestamp_local.replace(tzinfo=zone, fold=fold).astimezone(UTC) for fold in (0, 1)
    ]
    valid = [
        instant
        for instant in round_tripped
        if instant.astimezone(zone).replace(tzinfo=None) == timestamp_local
    ]
    if not valid:
        raise _RowRefusal(
            "nonexistent_local_timestamp",
            (
                f"timestamp {timestamp_local.isoformat()} does not exist on the {zone.key} "
                "clock (daylight-saving gap), and no official gap rule is established; refusing "
                "the row rather than silently shifting the wall clock."
            ),
        )
    if len(set(valid)) > 1:
        raise _RowRefusal(
            "ambiguous_local_timestamp",
            (
                f"timestamp {timestamp_local.isoformat()} occurs twice on the {zone.key} clock "
                "(daylight-saving fall-back), and no official fold rule is established; refusing "
                "the row rather than silently choosing one of the two instants."
            ),
        )
    # A unique wall clock: reuse the one shared timezone rule for the conversion.
    instant = parse_source_instant(timestamp_local.isoformat(), contract=contract, zone=zone)
    if instant is None:  # Defensive: timestamp_local is always a parsed wall clock here.
        raise _RowRefusal(
            "invalid_timestamp",
            f"timestamp {timestamp_local.isoformat()!r} could not be read as an instant",
        )
    return instant


def _canonical_price(record: EexNgpRecord, index_value: Decimal) -> float:
    """The canonical Float price, refusing an exact decimal that overflows it (never ``inf``)."""

    price = float(index_value)
    if not math.isfinite(price):
        raise EexNgpParseError(
            "index_value_float_overflow",
            (
                f"the index value of {record.observation_id!r} is finite as an exact decimal "
                f"({len(record.index_value_raw)} characters) but overflows the canonical Float "
                "price column; refusing to write an infinite price."
            ),
        )
    return price


def _resolve_gas_day_calendar_contract(
    contract: EexNgpGasDayCalendarContract | None,
) -> EexNgpGasDayCalendarContract:
    """The caller's evidenced delivery calendar, or a declared refusal.

    There is no default: this repository has not verified how EEX labels NGP delivery days, and
    the publication-timezone contract is not evidence for it. Only an existing registered
    calendar id with non-blank evidence is accepted.
    """

    if contract is None:
        raise EexNgpParseError(
            "unproven_gas_day_calendar",
            (
                "the EEX NGP Gasday delivery calendar is not proven; canonical mapping requires "
                "a separately evidenced EexNgpGasDayCalendarContract naming an existing calendar "
                "id, because publication-timezone evidence proves nothing about the delivery "
                "day."
            ),
        )
    if contract.calendar_id not in GAS_DAY_CALENDARS:
        registered = ", ".join(sorted(GAS_DAY_CALENDARS))
        raise EexNgpParseError(
            "unregistered_gas_day_calendar",
            (
                f"gas-day calendar {contract.calendar_id!r} is not registered; use an existing "
                f"calendar id ({registered}) rather than inventing a rule."
            ),
        )
    if not contract.evidence.strip():
        raise EexNgpParseError(
            "unattested_gas_day_calendar",
            (
                "an evidenced gas-day calendar contract must state its evidence; a caller note "
                "alone does not certify that the source labels its delivery days on this "
                "calendar."
            ),
        )
    return contract


def _read_csv_rows(csv_text: str) -> list[tuple[int, list[str]]]:
    text = csv_text.lstrip("\ufeff")
    if not text.strip():
        raise EexNgpParseError("empty_payload", "the EEX TTF NGP payload is empty.")
    reader = csv.reader(io.StringIO(text), delimiter=DELIMITER)
    return [(row_number, row) for row_number, row in enumerate(reader, start=1)]


def _validate_header(header: list[str]) -> None:
    normalized = tuple(_normalize_header_cell(cell) for cell in header)
    if normalized != _EXPECTED_HEADER_NORMALIZED:
        raise EexNgpParseError(
            "unexpected_header",
            (
                f"the EEX TTF NGP CSV header is not the verified five-column layout "
                f"{EXPECTED_HEADER!r}; found {tuple(header)!r}."
            ),
        )


def _resolve_retrieved_at(value: datetime | None) -> datetime:
    retrieved_at = value or datetime.now(UTC)
    if retrieved_at.tzinfo is None or retrieved_at.utcoffset() is None:
        raise EexNgpParseError(
            "naive_retrieval_timestamp",
            (
                "retrieved_at_utc must be timezone-aware; a naive value would be read as UTC, and "
                "the adapter refuses to guess any clock."
            ),
        )
    return retrieved_at.astimezone(UTC)


def _resolve_timezone_contract(
    timezone_contract: SourceTimezoneContract | None,
) -> SourceTimezoneContract:
    if timezone_contract is None:
        return contract_for(SOURCE_SYSTEM, SOURCE_DATASET)
    if timezone_contract.source_system != SOURCE_SYSTEM:
        raise EexNgpParseError(
            "timezone_contract_source_mismatch",
            (
                f"the supplied timezone contract declares source "
                f"{timezone_contract.source_system!r}; this adapter maps {SOURCE_SYSTEM!r}."
            ),
        )
    if not timezone_contract.supports(SOURCE_DATASET):
        raise EexNgpParseError(
            "timezone_contract_dataset_mismatch",
            (
                f"the supplied timezone contract does not cover dataset {SOURCE_DATASET!r}; a "
                "contract for another dataset proves nothing about this one."
            ),
        )
    if timezone_contract.declared_zone is not None and not timezone_contract.evidence.strip():
        raise EexNgpParseError(
            "unattested_timezone_contract",
            (
                "a governed contract that declares a zone must state its evidence; the adapter "
                "never invents a provider zone."
            ),
        )
    return timezone_contract


def _parse_gas_day(value: str) -> date | None:
    match = _GAS_DAY_PATTERN.fullmatch(value)
    if match is None:
        return None
    day, month, year = (int(part) for part in match.groups())
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _parse_local_timestamp(value: str) -> datetime | None:
    match = _TIMESTAMP_PATTERN.fullmatch(value)
    if match is None:
        return None
    day, month, year, hour, minute = (int(part) for part in match.groups())
    try:
        return datetime(year, month, day, hour, minute)
    except ValueError:
        return None


def _parse_decimal(value: str, *, field: str) -> Decimal | None:
    if not value:
        return None
    if _DECIMAL_PATTERN.fullmatch(value) is None:
        raise _RowRefusal(f"invalid_{field}", f"{field} {value!r} is not a decimal number")
    try:
        parsed = Decimal(value)
    except InvalidOperation as error:
        raise _RowRefusal(
            f"invalid_{field}", f"{field} {value!r} is not a decimal number"
        ) from error
    if not parsed.is_finite():
        raise _RowRefusal(f"invalid_{field}", f"{field} {value!r} is not a finite number")
    return parsed


def _normalize_token(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()
