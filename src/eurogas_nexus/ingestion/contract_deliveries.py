"""Daily nominations and allocations for bilateral supply contracts.

The source is the TSO's or upstream system's allocation report (Gassco, the entry TSO's
shipper portal) or the ETRM's scheduling module, exported as CSV. Columns
(case-insensitive; extras ignored)::

    contract_id, gas_day, nominated_mwh, allocated_mwh[, tso, point]

``gas_day`` is the gas day's date (YYYY-MM-DD). Quantities are MWh for the gas day; an
empty cell means the figure is not known yet (an allocation arrives after the day) and is
stored as missing, not zero. Rows are keyed by (contract, gas day): a later file with the
final allocation replaces the provisional one, so loads are safe to repeat.
"""

from __future__ import annotations

import csv
import io
from datetime import date, datetime
from typing import Any

MAX_ROWS = 400_000


class DeliveryImportError(ValueError):
    """Malformed file; nothing is loaded."""


def _quantity(raw: str, line: int, name: str) -> float | None:
    text = (raw or "").strip().replace(",", "")
    if not text:
        return None
    try:
        value = float(text)
    except ValueError as exc:
        raise DeliveryImportError(f"line {line}: {name} {raw!r} is not a number") from exc
    if value != value or value < 0:
        raise DeliveryImportError(f"line {line}: {name} must be zero or more")
    return value


def parse_contract_deliveries(
    text: str, *, source_system: str, source_reference: str, now_utc: datetime
) -> list[dict[str, Any]]:
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    if not reader.fieldnames:
        raise DeliveryImportError("the file has no header")
    fields = {name.strip().casefold(): name for name in reader.fieldnames}
    for required in ("contract_id", "gas_day", "nominated_mwh", "allocated_mwh"):
        if required not in fields:
            raise DeliveryImportError(f"missing column {required!r}")
    rows: dict[tuple[str, date], dict[str, Any]] = {}
    for line, record in enumerate(reader, start=2):
        if line - 1 > MAX_ROWS:
            raise DeliveryImportError(f"more than {MAX_ROWS} rows")

        def cell(name: str, record: dict = record) -> str:
            key = fields.get(name)
            return (record.get(key) or "").strip() if key else ""

        contract_id = cell("contract_id")
        if not contract_id:
            raise DeliveryImportError(f"line {line}: contract_id is empty")
        try:
            gas_day = date.fromisoformat(cell("gas_day")[:10])
        except ValueError as exc:
            raise DeliveryImportError(f"line {line}: gas_day is not YYYY-MM-DD") from exc
        rows[(contract_id, gas_day)] = {
            "contract_id": contract_id[:128],
            "gas_day": gas_day,
            "nominated_mwh": _quantity(cell("nominated_mwh"), line, "nominated_mwh"),
            "allocated_mwh": _quantity(cell("allocated_mwh"), line, "allocated_mwh"),
            "tso": cell("tso")[:64] or None,
            "point": cell("point")[:160] or None,
            "source_system": source_system[:32],
            "source_reference": source_reference[:160],
            "updated_at_utc": now_utc,
        }
    if not rows:
        raise DeliveryImportError("the file has no rows")
    return list(rows.values())
