"""Daily settlement prices for any market in the reference model, from a licensed export.

Gas desks need more than gas: EUA and UKA carbon and API2 coal set the fuel-switching
level, power prices set gas burn, Henry Hub and JKM set LNG arbitrage. Settlement prices
for these are licensed (ICE Endex, EEX, CME, NGX, Argus). A market-data team exports the
settlements it is entitled to (EEX DataSource, ICE Report Center, NGX, a vendor terminal)
as CSV and imports them here; rows are stored under that licence's source family, so
entitlement filtering applies as for a direct connector.

Columns (case-insensitive; extra columns ignored)::

    date, market, product, settlement[, currency, unit, volume]

``market`` is a code from ``domain.ontology.markets`` (EUA, UKA, API2, TTF, NBP, DE_LU,
HH, AECO...). ``product`` is the exchange label: ``Dec-26``, ``Cal-27``, ``Q1-27``,
``M+1``, ``DA``, ``Spot``. Without a unit the market's native quote applies. Gas prices in
p/th are stored per MWh in GBP, like screen imports; other units are stored as quoted.
"""

from __future__ import annotations

import csv
import hashlib
import io
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from eurogas_nexus.domain.market.products import ProductCodeError, resolve_product
from eurogas_nexus.domain.market.units import (
    UnitConversionError,
    canonical_price_unit,
    convert_price,
)
from eurogas_nexus.domain.ontology.markets import Commodity, find_market

#: Licensed families an import may be stored under, with the venue label.
SETTLEMENT_SOURCES = {
    "EEX": "EEX",
    "ICE_ENDEX": "ICE Endex",
    "CME": "CME",
    "NGX": "NGX",
    "Argus": "Argus",
    "Platts": "Platts",
}
MAX_ROWS = 50_000
_SPOT = {"SPOT", "DA", "DAY AHEAD", "DAY-AHEAD"}


class SettlementImportError(ValueError):
    """Malformed export; the whole file is refused."""


@dataclass(frozen=True)
class SettlementImport:
    rows: list[dict[str, Any]]
    markets: list[str]
    first_day: date
    last_day: date


def _date(text: str, line: int) -> date:
    try:
        return date.fromisoformat(text.strip()[:10])
    except ValueError as exc:
        raise SettlementImportError(f"line {line}: date {text!r} is not YYYY-MM-DD") from exc


def _number(text: str | None, line: int, name: str) -> float | None:
    value = (text or "").strip().replace(",", "")
    if not value:
        return None
    try:
        return float(value)
    except ValueError as exc:
        raise SettlementImportError(f"line {line}: {name} {text!r} is not a number") from exc


def _period(product: str, trade_day: date) -> tuple[datetime, datetime, str]:
    """Delivery window and board tenor for a product label on a trade date."""

    label = product.strip()
    if label.upper() in _SPOT:
        start = datetime.combine(trade_day + timedelta(days=1), time.min, tzinfo=UTC)
        return start, start + timedelta(days=1), "day-ahead"
    try:
        period = resolve_product(label, trade_day)
    except ProductCodeError:
        start = datetime.combine(trade_day, time.min, tzinfo=UTC)
        return start, start + timedelta(days=1), label.lower()[:24]
    next_month = (trade_day.replace(day=28) + timedelta(days=4)).replace(day=1)
    first = period.delivery_start_utc
    tenor = (
        "month-ahead"
        if period.kind == "month"
        and (first.year, first.month) == (next_month.year, next_month.month)
        else "day-ahead"
        if period.kind == "day_ahead"
        else period.label.lower()
    )
    return period.delivery_start_utc, period.delivery_end_utc, tenor


def parse_settlements(
    text: str,
    *,
    source_system: str,
    source_reference: str,
    received_at_utc: datetime | None = None,
) -> SettlementImport:
    """Rows for ``market_observations`` from one export; refuses the file on any bad line."""

    if source_system not in SETTLEMENT_SOURCES:
        raise SettlementImportError(
            f"source {source_system!r} is not one of {sorted(SETTLEMENT_SOURCES)}"
        )
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    headers = {(name or "").strip().lower(): name for name in reader.fieldnames or []}
    for required in ("date", "market", "product", "settlement"):
        if required not in headers:
            raise SettlementImportError(f"export is missing a {required!r} column")

    def cell(record: dict[str, str], name: str) -> str | None:
        key = headers.get(name)
        return record.get(key) if key else None

    received = received_at_utc or datetime.now(UTC)
    rows: list[dict[str, Any]] = []
    for line, record in enumerate(reader, start=2):
        if line - 1 > MAX_ROWS:
            raise SettlementImportError(f"export exceeds {MAX_ROWS} rows")
        trade_day = _date(cell(record, "date") or "", line)
        code = (cell(record, "market") or "").strip()
        market = find_market(code)
        if market is None:
            raise SettlementImportError(
                f"line {line}: market {code!r} is not in the reference model"
            )
        price = _number(cell(record, "settlement"), line, "settlement")
        if price is None:
            raise SettlementImportError(f"line {line}: settlement is required")
        unit_text = (cell(record, "unit") or "").strip()
        currency = (cell(record, "currency") or "").strip().upper()
        if unit_text and "/" not in unit_text:
            unit_text = f"{currency or market.currency}/{unit_text}"
        unit = unit_text or market.price_unit
        if unit.split("/")[0].upper() != market.currency:
            raise SettlementImportError(
                f"line {line}: {market.code} quotes in {market.currency}, not {unit}"
            )
        native = {"price": price, "unit": unit}
        if market.commodity in (Commodity.NATURAL_GAS, Commodity.LNG):
            try:
                unit = canonical_price_unit(unit)
                if unit == "GBp/th":
                    price, unit = round(convert_price(price, "GBp/th", "GBP/MWh"), 6), "GBP/MWh"
            except UnitConversionError as exc:
                raise SettlementImportError(f"line {line}: {exc}") from exc
        product = (cell(record, "product") or "").strip()
        if not product:
            raise SettlementImportError(f"line {line}: product is required")
        start, end, tenor = _period(product, trade_day)
        # Settlements are end-of-day values: stamp them at 18:00 UTC on the trade date.
        observed = datetime.combine(trade_day, time(18), tzinfo=UTC)
        identity = f"{source_system}|{market.code}|{product.upper()}|{trade_day.isoformat()}"
        digest = hashlib.sha256(identity.encode()).hexdigest()[:32]
        rows.append(
            {
                "observation_id": f"stl-{digest}",
                "market_venue": SETTLEMENT_SOURCES[source_system][:32],
                "product": f"{market.code} {product}"[:32],
                "price": price,
                "unit": unit[:16],
                "currency": unit.split("/")[0][:8],
                "period_start_utc": start,
                "period_end_utc": end,
                "observed_at_utc": observed,
                "source_system": source_system,
                "source_reference": source_reference[:128],
                "source_record_id": identity[:128],
                "freshness": "end_of_day",
                "quality_score": 1.0,
                "research_only": True,
                "metadata_json": {
                    "hub": market.code,
                    "tenor": tenor,
                    "commodity": market.commodity.value,
                    "settlement": True,
                    "native": native,
                    "volume": _number(cell(record, "volume"), line, "volume"),
                    "received_at_utc": received.isoformat(),
                },
            }
        )
    if not rows:
        raise SettlementImportError("the export has no rows")
    days = [row["observed_at_utc"].date() for row in rows]
    return SettlementImport(
        rows=rows,
        markets=sorted({row["metadata_json"]["hub"] for row in rows}),
        first_day=min(days),
        last_day=max(days),
    )
