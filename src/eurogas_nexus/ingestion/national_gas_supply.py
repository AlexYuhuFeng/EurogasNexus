"""Great Britain storage and LNG from the National Gas data portal (keyless CSV).

GIE AGSI/ALSI carry Great Britain rows with no values. This adapter fills the GB
side from the same public National Gas download endpoint the NTS demand adapter
uses (``national_gas_demand``: fixed origin, exact header, bounded transport).

Publication items (all energy in kWh, "Data Item" label in quotes):

=============  =====================================================  ==========================
id             label                                                  stored as
=============  =====================================================  ==========================
PUBOBJ330      Storage, Daily Aggregated Stock level, D+1             storage ``inventory_twh``
PUBOBJ336      LNG, Daily Aggregated Stock level, D+1                 LNG ``inventory_twh``
PUBOBJ517      Allocations, Energy, Storage Entry Total, D+2          storage ``withdrawal_twh_d``
PUBOBJ521      Allocations, Energy, Storage Exit Total, D+2           storage ``injection_twh_d``
PUBOBJ518      Allocations, Energy, LNG Importation Total, D+2        LNG ``send_out_twh_d``
PUBOBJ1149     Nominations, ... Storage Entry Total                   provisional withdrawal
PUBOBJ1155     Nominations, ... Storage Exit Total                    provisional injection
PUBOBJ1150     Nominations, ... LNG Importation Total                 provisional send-out
=============  =====================================================  ==========================

Rules, each checked against published numbers:

* Allocations and nominations: "Applicable For" is the gas day.
* The two "Daily Aggregated Stock level, D+1" items are labelled with the
  publication day. A row with Applicable For = X is the closing stock of gas
  day X-1 and is stored on gas day X-1. Evidence: GB storage stock labelled
  10/11/2026 was 10,406.7 GWh and labelled 11/11/2026 was 9,969.1 GWh, a fall of
  437.6 GWh, while the storage entry allocation for gas day 10/11/2026 was
  437.3 GWh. The LNG stock fell 583.7 GWh over the same labels against a
  send-out allocation of 581.3 GWh for gas day 10/11/2026.
* The allocation (D+2) is used when present. Otherwise the end-of-day
  prevailing nomination (published D+1 04:00) is used and recorded as
  ``nomination_provisional``; nominations tracked allocations within about
  0.1% (LNG, gas day 10/11/2026: nomination 581.25 GWh, allocation 581.31 GWh).
  A nomination applicable on the gas day itself is a within-day figure and is
  never used.
* LNG send-out is the importation into the NTS, not the "LNG Daily Aggregated
  Inflows/Outflows" items, which are net tank stock change including cargo
  unloading.
* No working capacity is published, so ``working_capacity_twh`` and
  ``fill_pct`` stay ``None``; LNG ``dtmi_twh`` stays ``None``.

The parser is pure. ``observed_at_utc`` is the caller's receipt instant.
"""

from __future__ import annotations

import csv
import io
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Final
from urllib.parse import urlencode

from eurogas_nexus.domain.market.gas_day import EU_CAM_UTC_CALENDAR
from eurogas_nexus.domain.market.units import convert_energy
from eurogas_nexus.ingestion.national_gas_demand import (
    DEFAULT_MAX_ATTEMPTS,
    DEFAULT_TIMEOUT_SECONDS,
    DOWNLOAD_URL,
    EXPECTED_HEADER,
    MAX_WINDOW_DAYS,
    SOURCE_SYSTEM,
    NationalGasDemandError,
    _decode_payload,
    _parse_naive,
    _parse_quality,
    _require_aware_utc,
    _validate_value,
    fetch_official_csv,
    gas_day_period_utc,
)

if TYPE_CHECKING:  # pragma: no cover - import used only by static type checkers
    import httpx

SOURCE_DATASET: Final = "NG-SUPPLY"
SOURCE_REFERENCE: Final = "national-gas-data-portal"
COUNTRY: Final = "GB"
STORAGE_FACILITY_ID: Final = "GB-NTS-STORAGE"
STORAGE_FACILITY_NAME: Final = "Great Britain storage (National Gas)"
LNG_TERMINAL_ID: Final = "GB-NTS-LNG"
LNG_TERMINAL_NAME: Final = "Great Britain LNG (National Gas)"
ALLOCATION: Final = "allocation"
NOMINATION: Final = "nomination_provisional"
STOCK: Final = "stock_level_d_plus_1"
STOCK_LABEL_NOTE: Final = (
    "Stock level D+1 is labelled with the publication day: Applicable For X is the "
    "closing stock of gas day X-1 and is stored on gas day X-1."
)


class NationalGasSupplyError(NationalGasDemandError):
    """A stable, operator-safe supply source or contract failure."""


@dataclass(frozen=True)
class SupplyItem:
    """One allowlisted publication item and where its value goes."""

    item_id: str
    label: str
    table: str  # "storage" or "lng"
    field: str
    basis: str


ITEMS: Final = (
    SupplyItem("PUBOBJ330", "Storage, Daily Aggregated Stock level, D+1",
               "storage", "inventory_twh", STOCK),
    SupplyItem("PUBOBJ336", "LNG, Daily Aggregated Stock level, D+1",
               "lng", "inventory_twh", STOCK),
    SupplyItem("PUBOBJ517", "Allocations, Energy, Storage Entry Total, D+2",
               "storage", "withdrawal_twh_d", ALLOCATION),
    SupplyItem("PUBOBJ521", "Allocations, Energy, Storage Exit Total, D+2",
               "storage", "injection_twh_d", ALLOCATION),
    SupplyItem("PUBOBJ518", "Allocations, Energy, LNG Importation Total, D+2",
               "lng", "send_out_twh_d", ALLOCATION),
    SupplyItem("PUBOBJ1149",
               "Nominations, Aggregate Prevailing Nomination, Storage Entry Total",
               "storage", "withdrawal_twh_d", NOMINATION),
    SupplyItem("PUBOBJ1155",
               "Nominations, Aggregate Prevailing Nomination, Storage Exit Total",
               "storage", "injection_twh_d", NOMINATION),
    SupplyItem("PUBOBJ1150",
               "Nominations, Aggregate Prevailing Nomination, LNG Importation Total",
               "lng", "send_out_twh_d", NOMINATION),
)
ITEM_BY_LABEL: Final = {item.label: item for item in ITEMS}
STORAGE_FIELDS: Final = ("inventory_twh", "withdrawal_twh_d", "injection_twh_d")
LNG_FIELDS: Final = ("inventory_twh", "send_out_twh_d")
#: kWh -> TWh from the unit authority, held as a decimal so 9969071446 kWh is 9.969071446.
KWH_TO_TWH: Final = Decimal(repr(convert_energy(1.0, "kWh", "TWh")))


@dataclass(frozen=True)
class _Reading:
    item: SupplyItem
    gas_day: date
    twh: float
    applicable_at_raw: str
    applicable_at: datetime
    generated_at: datetime
    quality: str | None


@dataclass(frozen=True)
class SupplyDownload:
    """Parsed storage and LNG rows from one bounded download."""

    storage_rows: list[dict[str, Any]]
    lng_rows: list[dict[str, Any]]
    source_url: str
    received_at_utc: datetime


def request_window(first_gas_day: date, last_gas_day: date) -> tuple[date, date]:
    """The publication window (Applicable For) that covers the gas days.

    The stock for ``last_gas_day`` is labelled the day after, so the window runs one
    day past the last gas day.
    """

    if isinstance(first_gas_day, datetime) or isinstance(last_gas_day, datetime):
        raise NationalGasSupplyError("INVALID_WINDOW", "gas days must be calendar dates")
    if first_gas_day > last_gas_day:
        raise NationalGasSupplyError("INVALID_WINDOW", "first gas day is after the last")
    date_to = last_gas_day + timedelta(days=1)
    if (date_to - first_gas_day).days + 1 > MAX_WINDOW_DAYS:
        raise NationalGasSupplyError(
            "INVALID_WINDOW", f"window must not exceed {MAX_WINDOW_DAYS} days"
        )
    return first_gas_day, date_to


def build_supply_url(first_gas_day: date, last_gas_day: date) -> str:
    """The one download URL for every supply item over the gas days."""

    date_from, date_to = request_window(first_gas_day, last_gas_day)
    query = urlencode(
        {
            "applicableFor": "Y",
            "dateFrom": date_from.isoformat(),
            "dateTo": date_to.isoformat(),
            "dateType": "GASDAY",
            "latestFlag": "Y",
            "ids": ",".join(item.item_id for item in ITEMS),
            "type": "CSV",
        }
    )
    return f"{DOWNLOAD_URL}?{query}"


def parse_national_gas_supply_csv(
    payload: bytes | str,
    *,
    first_gas_day: date,
    last_gas_day: date,
    received_at_utc: datetime,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Parse the supply CSV into ``(storage_rows, lng_rows)`` for the gas days.

    Header drift, an unknown label, a malformed value or date, and a row outside the
    publication window are errors. A stock labelled the first publication day (gas
    day before ``first_gas_day``) and flows for the day after ``last_gas_day`` are
    outside the requested gas days and are left out, so a later run over a different
    window never blanks a field it did not fetch.
    """

    date_from, date_to = request_window(first_gas_day, last_gas_day)
    received = _require_aware_utc(received_at_utc, "received_at_utc")
    text, _ = _decode_payload(payload)
    if not text.strip():
        raise NationalGasSupplyError("EMPTY_RESPONSE", "download contained no CSV data")
    reader = csv.reader(io.StringIO(text, newline=""), strict=True)
    try:
        header = tuple(next(reader))
    except StopIteration as exc:
        raise NationalGasSupplyError("EMPTY_RESPONSE", "download contained no CSV header") from exc
    except csv.Error as exc:
        raise NationalGasSupplyError("MALFORMED_CSV", "CSV header is malformed") from exc
    if header != EXPECTED_HEADER:
        raise NationalGasSupplyError("HEADER_DRIFT", "CSV header does not match the contract")

    # Latest Applicable At wins per item and gas day (latestFlag=Y sends one row).
    latest: dict[tuple[str, date], _Reading] = {}
    try:
        for fields in reader:
            if not fields:
                continue
            if len(fields) != len(EXPECTED_HEADER):
                raise NationalGasSupplyError(
                    "MALFORMED_CSV", "row does not have the contracted column count"
                )
            reading = _parse_row(fields, date_from=date_from, date_to=date_to)
            if reading is None or not first_gas_day <= reading.gas_day <= last_gas_day:
                continue
            key = (reading.item.item_id, reading.gas_day)
            held = latest.get(key)
            if held is None or (reading.applicable_at, reading.generated_at) > (
                held.applicable_at,
                held.generated_at,
            ):
                latest[key] = reading
    except csv.Error as exc:
        raise NationalGasSupplyError("MALFORMED_CSV", "CSV row is malformed") from exc

    by_day: dict[tuple[str, date], list[_Reading]] = {}
    for reading in latest.values():
        by_day.setdefault((reading.item.table, reading.gas_day), []).append(reading)

    storage_rows, lng_rows = [], []
    for (table, gas_day), readings in sorted(by_day.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        row = _row(table, gas_day, readings, received)
        (storage_rows if table == "storage" else lng_rows).append(row)
    return storage_rows, lng_rows


def fetch_national_gas_supply(
    first_gas_day: date,
    last_gas_day: date,
    *,
    client: httpx.Client | None = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    sleep: Callable[[float], None] = time.sleep,
    received_at_utc: datetime | None = None,
) -> SupplyDownload:
    """Download every supply item over the gas days in one request and parse it."""

    target_url = build_supply_url(first_gas_day, last_gas_day)
    body = fetch_official_csv(
        target_url,
        client=client,
        timeout_seconds=timeout_seconds,
        max_attempts=max_attempts,
        sleep=sleep,
    )
    receipt = _require_aware_utc(received_at_utc or datetime.now(UTC), "received_at_utc")
    storage_rows, lng_rows = parse_national_gas_supply_csv(
        body, first_gas_day=first_gas_day, last_gas_day=last_gas_day, received_at_utc=receipt
    )
    return SupplyDownload(storage_rows, lng_rows, target_url, receipt)


def _parse_row(fields: list[str], *, date_from: date, date_to: date) -> _Reading | None:
    applicable_raw = fields[0].strip()
    label = fields[2]
    value_text = fields[3]
    item = ITEM_BY_LABEL.get(label)
    if item is None:
        raise NationalGasSupplyError(
            "UNKNOWN_SERIES", "data item label is not an approved storage/LNG supply item"
        )
    try:
        applicable_for = datetime.strptime(fields[1].strip(), "%d/%m/%Y").date()
    except ValueError as exc:
        raise NationalGasSupplyError("MALFORMED_GAS_DAY", "Applicable For is not a date") from exc
    if not date_from <= applicable_for <= date_to:
        raise NationalGasSupplyError(
            "ROW_OUTSIDE_WINDOW", "row is outside the explicit publication window"
        )
    applicable_at = _parse_naive(applicable_raw, "Applicable At")
    generated_at = _parse_naive(fields[4].strip(), "Generated Time")
    quality = _parse_quality(fields[5])
    _validate_value(value_text)

    if item.basis == STOCK:
        gas_day = applicable_for - timedelta(days=1)
    else:
        gas_day = applicable_for
        # A nomination applicable on the gas day itself is within-day, not end-of-day.
        if item.basis == NOMINATION and applicable_at.date() <= gas_day:
            return None
    twh = float(Decimal(value_text) * KWH_TO_TWH)
    return _Reading(item, gas_day, twh, applicable_raw, applicable_at, generated_at, quality)


def _row(
    table: str, gas_day: date, readings: list[_Reading], received: datetime
) -> dict[str, Any]:
    fields = STORAGE_FIELDS if table == "storage" else LNG_FIELDS
    values: dict[str, float | None] = dict.fromkeys(fields)
    basis: dict[str, str] = {}
    publication_ids: dict[str, str] = {}
    applicable_at: dict[str, str] = {}
    quality: dict[str, str] = {}
    # Allocation (and stock) first: a nomination fills only what no allocation did.
    for reading in sorted(readings, key=lambda r: r.item.basis == NOMINATION):
        name = reading.item.field
        if name in basis:
            continue
        values[name] = reading.twh
        basis[name] = reading.item.basis
        publication_ids[name] = reading.item.item_id
        applicable_at[name] = reading.applicable_at_raw
        if reading.quality:
            quality[name] = reading.quality
    period_start, period_end = gas_day_period_utc(gas_day)
    tag = "storage" if table == "storage" else "lng"
    entity_id = STORAGE_FACILITY_ID if table == "storage" else LNG_TERMINAL_ID
    row: dict[str, Any] = {
        "observation_id": f"national-gas-{tag}-{COUNTRY}-{gas_day.isoformat()}",
        "source_dataset": SOURCE_DATASET,
    }
    if table == "storage":
        row |= {
            "facility_id": entity_id,
            "facility_name": STORAGE_FACILITY_NAME,
            "country": COUNTRY,
            "inventory_twh": values["inventory_twh"],
            # Not published by National Gas; never inferred.
            "working_capacity_twh": None,
            "fill_pct": None,
            "injection_twh_d": values["injection_twh_d"],
            "withdrawal_twh_d": values["withdrawal_twh_d"],
        }
    else:
        row |= {
            "terminal_id": entity_id,
            "terminal_name": LNG_TERMINAL_NAME,
            "country": COUNTRY,
            "inventory_twh": values["inventory_twh"],
            "send_out_twh_d": values["send_out_twh_d"],
            "dtmi_twh": None,
        }
    row |= {
        "period_start_utc": period_start,
        "period_end_utc": period_end,
        "observed_at_utc": received,
        "source_system": SOURCE_SYSTEM,
        "source_reference": SOURCE_REFERENCE,
        "source_record_id": f"{entity_id}-{gas_day.isoformat()}",
        "freshness": "live",
        "research_only": True,
        "metadata_json": {
            "gas_day": gas_day.isoformat(),
            "calendar_version": EU_CAM_UTC_CALENDAR,
            "availability_basis": "response_receipt",
            "source_unit": "kWh",
            "basis": basis,
            "publication_ids": publication_ids,
            "applicable_at": applicable_at,
            "quality_indicators": quality,
            "provisional": NOMINATION in basis.values(),
            "stock_label_note": STOCK_LABEL_NOTE,
        },
    }
    return row
