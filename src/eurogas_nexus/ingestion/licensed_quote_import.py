"""Import L1 quotes exported from the customer's own licensed trading screen.

Live European gas prices are licensed per subscriber (Trayport, ICE Endex, EEX);
there is no free feed the product can ship. A desk that already holds a Trayport
or exchange entitlement can export its own screen (a CSV export, or an Excel/RTD
sheet saved as CSV on a timer) and import it here. Rows are stored under the
licensed source family, so entitlement filtering applies exactly as for a direct
connector, and nothing is marked simulated.

Expected columns (case-insensitive; extra columns ignored)::

    timestamp, hub, product, bid, ask[, last, bid_qty, ask_qty, currency, unit]

``product`` accepts Trayport-style names: ``WD``/``Within Day``, ``DA``/``Day Ahead``,
``WE``/``Weekend``, ``BOM``, ``Nov-26``, ``Q1-27``, ``Sum-27``/``Win-27``,
``GY-27``, ``Cal-27`` and relative ``M+1``/``Q+1``. Prices may be EUR/MWh,
GBP/MWh or GBp/th (NBP); pence per therm is stored per MWh in GBP and the native
value is kept in ``metadata_json``.

本模块导入客户自有授权交易屏（Trayport/ICE/EEX）导出的一档报价；不属于模拟数据，
按授权来源族过滤。
"""

from __future__ import annotations

import csv
import hashlib
import io
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from eurogas_nexus.domain.market.gas_day import EU_CAM_UTC_CALENDAR
from eurogas_nexus.domain.market.products import ProductCodeError, resolve_product
from eurogas_nexus.domain.market.units import (
    HUB_NATIVE_PRICE_UNIT,
    UnitConversionError,
    canonical_price_unit,
    convert_energy,
    convert_price,
)

#: Licensed families an operator may import and the venue label stored with them.
LICENSED_QUOTE_SOURCES = {
    "Trayport": "Trayport",
    "ICE_OCM": "ICE Endex",
    "EEX": "EEX",
}
SUPPORTED_HUBS = {"TTF", "NBP", "THE", "PEG", "ZTP", "PSV", "CEGH", "VTP", "PVB", "ETF"}
MAX_IMPORT_ROWS = 20_000
_PRODUCT_ALIASES = {
    "WITHIN DAY": "WD",
    "WITHIN-DAY": "WD",
    "DAY AHEAD": "DA",
    "DAY-AHEAD": "DA",
    "WEEKEND": "WE",
    "BAL MONTH": "BOM",
    "BALANCE OF MONTH": "BOM",
}
#: Board tenors the market terminal groups by; other products keep their desk label.
_BOARD_TENOR = {"within_day": "within-day", "day_ahead": "day-ahead", "weekend": "weekend"}


class QuoteImportError(ValueError):
    """Malformed export; the whole file is refused."""


@dataclass(frozen=True)
class QuoteImportResult:
    rows: list[dict[str, Any]]
    hubs: list[str]
    products: list[str]


def _number(value: str | None, line: int, name: str, *, required: bool) -> float | None:
    text = (value or "").strip().replace(",", "")
    if not text:
        if required:
            raise QuoteImportError(f"line {line}: {name} is required")
        return None
    try:
        number = float(text)
    except ValueError as exc:
        raise QuoteImportError(f"line {line}: {name} is not a number") from exc
    if number != number or abs(number) > 1e6:
        raise QuoteImportError(f"line {line}: {name} is out of range")
    return number


def _quantity_mwh(value: float | None, native_unit: str) -> float | None:
    if value is None:
        return None
    if native_unit == "GBp/th":
        return round(convert_energy(value, "therm", "MWh"), 6)
    return value


def _timestamp(value: str, line: int) -> datetime:
    text = (value or "").strip().replace("Z", "+00:00")
    try:
        stamp = datetime.fromisoformat(text)
    except ValueError as exc:
        raise QuoteImportError(f"line {line}: timestamp must be ISO 8601") from exc
    if stamp.tzinfo is None:
        raise QuoteImportError(f"line {line}: timestamp needs an explicit UTC offset")
    return stamp.astimezone(UTC)


def parse_quote_export(
    text: str,
    *,
    source_system: str,
    source_reference: str,
    received_at_utc: datetime,
    default_units: dict[str, str] | None = None,
) -> QuoteImportResult:
    """Parse one export into ``market_quotes`` rows.

    Raises:
        QuoteImportError: Unknown source, missing columns or any bad row.
    """

    if source_system not in LICENSED_QUOTE_SOURCES:
        raise QuoteImportError(f"source must be one of {sorted(LICENSED_QUOTE_SOURCES)}")
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    headers = {
        name.strip().lower().replace(" ", "_"): name for name in reader.fieldnames or []
    }
    for required in ("timestamp", "hub", "product", "bid", "ask"):
        if required not in headers:
            raise QuoteImportError(f"export is missing a {required!r} column")

    def cell(record: dict[str, str], name: str) -> str | None:
        key = headers.get(name)
        return record.get(key) if key else None

    rows: list[dict[str, Any]] = []
    for line, record in enumerate(reader, start=2):
        if line - 1 > MAX_IMPORT_ROWS:
            raise QuoteImportError(f"export exceeds {MAX_IMPORT_ROWS} rows")
        observed = _timestamp(cell(record, "timestamp") or "", line)
        hub = (cell(record, "hub") or "").strip().upper()
        if hub not in SUPPORTED_HUBS:
            raise QuoteImportError(f"line {line}: unsupported hub {hub!r}")
        raw_product = (cell(record, "product") or "").strip()
        code = _PRODUCT_ALIASES.get(raw_product.upper(), raw_product)
        try:
            period = resolve_product(code, observed.date())
        except ProductCodeError as exc:
            raise QuoteImportError(f"line {line}: {exc}") from exc
        bid = _number(cell(record, "bid"), line, "bid", required=False)
        ask = _number(cell(record, "ask"), line, "ask", required=False)
        last = _number(cell(record, "last"), line, "last", required=False)
        if bid is None and ask is None and last is None:
            raise QuoteImportError(f"line {line}: bid, ask or last is required")
        if bid is not None and ask is not None and bid > ask:
            raise QuoteImportError(f"line {line}: bid above ask (crossed quote)")
        native_unit_text = (cell(record, "unit") or "").strip()
        currency_text = (cell(record, "currency") or "").strip().upper()
        if not native_unit_text:
            # No per-row unit: the hub's declared quoting convention (NBP p/th, continental
            # hubs EUR/MWh), overridable per import. Never inferred from the price level.
            native_unit_text = (default_units or {}).get(hub) or HUB_NATIVE_PRICE_UNIT.get(hub, "")
            if not native_unit_text:
                raise QuoteImportError(f"line {line}: no unit column and no convention for {hub}")
        elif "/" not in native_unit_text:
            if not currency_text:
                raise QuoteImportError(f"line {line}: unit {native_unit_text!r} needs a currency")
            native_unit_text = f"{currency_text}/{native_unit_text}"
        try:
            native_unit = canonical_price_unit(native_unit_text)
            per_mwh_unit = "GBP/MWh" if native_unit == "GBp/th" else native_unit
            if not per_mwh_unit.endswith("/MWh"):
                raise UnitConversionError(f"unsupported quote unit {native_unit}")
            bid_mwh, ask_mwh, last_mwh = (
                None if value is None else round(convert_price(value, native_unit, per_mwh_unit), 6)
                for value in (bid, ask, last)
            )
        except UnitConversionError as exc:
            raise QuoteImportError(f"line {line}: {exc}") from exc
        board_tenor = _BOARD_TENOR.get(period.kind)
        if board_tenor is None:
            board_tenor = "month-ahead" if code.upper() in {"M+1", "MA"} else period.label.lower()
        venue = LICENSED_QUOTE_SOURCES[source_system]
        instrument_id = f"{venue.upper().replace(' ', '-')}-{hub}-{period.label}"[:128]
        identity = f"{source_system}|{hub}|{period.label}|{observed.isoformat()}"
        digest = hashlib.sha256(identity.encode()).hexdigest()[:24]
        rows.append(
            {
                "quote_id": f"import-{source_system.lower()}-{digest}",
                "source_system": source_system,
                "source_record_id": f"{instrument_id}@{observed.isoformat()}"[:128],
                "venue": venue,
                "instrument_id": instrument_id,
                "hub": hub,
                "product": board_tenor,
                "delivery_start_utc": period.delivery_start_utc,
                "delivery_end_utc": period.delivery_end_utc,
                "bid_price": bid_mwh,
                "ask_price": ask_mwh,
                "last_price": last_mwh,
                # p/th screens quote volume in therms/day; store MWh like every other row.
                "bid_quantity_mwh": _quantity_mwh(
                    _number(cell(record, "bid_qty"), line, "bid_qty", required=False), native_unit
                ),
                "ask_quantity_mwh": _quantity_mwh(
                    _number(cell(record, "ask_qty"), line, "ask_qty", required=False), native_unit
                ),
                "currency": per_mwh_unit.split("/")[0],
                "unit": "MWh",
                "observed_at_utc": observed,
                "received_at_utc": received_at_utc,
                "source_reference": source_reference[:256],
                "freshness": "imported",
                "quality_score": 1.0,
                "simulated": False,
                "metadata_json": {
                    "source_family": source_system,
                    "import": "operator_licensed_screen_export",
                    "product_label": period.label,
                    "product_kind": period.kind,
                    "native_unit": native_unit,
                    "native_bid": bid,
                    "native_ask": ask,
                    "native_last": last,
                    "price_level": "L1",
                    "calendar_version": EU_CAM_UTC_CALENDAR,
                    "official_entitlement_required": True,
                },
            }
        )
    if not rows:
        raise QuoteImportError("export contains no quote rows")
    return QuoteImportResult(
        rows=rows,
        hubs=sorted({row["hub"] for row in rows}),
        products=sorted({row["metadata_json"]["product_label"] for row in rows}),
    )
