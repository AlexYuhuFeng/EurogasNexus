"""Trades from the firm's ETRM (Endur, Allegro, Openlink, RightAngle...) into books.

The ETRM is the book of record. A nightly or intraday extract loads its gas trades here
so positions, roll-ups, marks and risk read the same trades the back office settles.
Rows are keyed by (system, trade id): a re-sent trade replaces its earlier version and a
cancelled trade is removed, so the import is safe to repeat.

Columns (case-insensitive; extra columns ignored)::

    trade_id, trade_time, book_id, hub, side, delivery_start, delivery_end,
    quantity, quantity_unit, price, price_unit[, status, counterparty]

``delivery_start`` and ``delivery_end`` are the first and last gas day (inclusive).
``quantity_unit`` is ``MWh`` (total), ``MWh/d``, ``MW`` or ``th/d``; ``price_unit`` is the
trade's quote (``EUR/MWh``, ``GBp/th``...) and must be in the hub's currency.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from eurogas_nexus.domain.market.gas_day import gas_day_start_for_date
from eurogas_nexus.domain.ontology.boundary import check_boundary, refuse_if_invalid
from eurogas_nexus.domain.ontology.quantity import UnitError, convert, convert_price

#: Quantity units an ETRM extract may state; anything else is refused with a reason code.
QUANTITY_UNITS = ("MWh", "MWh/d", "MWh/day", "MW", "th/d", "therm/d")

MAX_ROWS = 200_000
_CANCELLED = {"CANCELLED", "CANCELED", "DELETED", "VOID"}


def _refused(message: str, check) -> EtrmImportError:
    exc = EtrmImportError(message)
    exc.reason_code = check.first.code.value  # type: ignore[attr-defined]
    exc.boundary_issues = [item.as_dict() for item in check.issues]  # type: ignore[attr-defined]
    return exc


class EtrmImportError(ValueError):
    """Malformed extract; the whole file is refused."""


@dataclass(frozen=True)
class EtrmImport:
    upserts: list[dict[str, Any]]
    cancelled_ids: list[str]


def _date(text: str, line: int, name: str) -> date:
    try:
        return date.fromisoformat((text or "").strip()[:10])
    except ValueError as exc:
        raise EtrmImportError(f"line {line}: {name} {text!r} is not YYYY-MM-DD") from exc


def _number(text: str | None, line: int, name: str) -> float:
    try:
        return float((text or "").replace(",", "").strip())
    except ValueError as exc:
        raise EtrmImportError(f"line {line}: {name} {text!r} is not a number") from exc


def parse_etrm_trades(text: str, *, system: str, source_reference: str) -> EtrmImport:
    """Trades for ``screen_order_observations`` (source ETRM) and the ids to remove."""

    system_key = "".join(ch for ch in system.upper() if ch.isalnum())[:16] or "ETRM"
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    headers = {(name or "").strip().lower(): name for name in reader.fieldnames or []}
    required = (
        "trade_id",
        "book_id",
        "hub",
        "side",
        "delivery_start",
        "delivery_end",
        "quantity",
        "quantity_unit",
        "price",
        "price_unit",
    )
    for name in required:
        if name not in headers:
            raise EtrmImportError(f"extract is missing a {name!r} column")

    def cell(record: dict[str, str], name: str) -> str:
        key = headers.get(name)
        return (record.get(key) or "").strip() if key else ""

    upserts: list[dict[str, Any]] = []
    cancelled: list[str] = []
    for line, record in enumerate(reader, start=2):
        if line - 1 > MAX_ROWS:
            raise EtrmImportError(f"extract exceeds {MAX_ROWS} rows")
        trade_id = cell(record, "trade_id")
        if not trade_id:
            raise EtrmImportError(f"line {line}: trade_id is required")
        row_id = f"etrm-{system_key.lower()}-{trade_id}"[:64]
        if cell(record, "status").upper() in _CANCELLED:
            cancelled.append(row_id)
            continue
        hub_checked = check_boundary(market=cell(record, "hub"), gas_hub_required=True)
        if hub_checked.first is not None and hub_checked.first.code.value == "market_unknown":
            # Said as before ("... is not a gas hub"), with the reason code.
            raise _refused(
                f"line {line}: {cell(record, 'hub')!r} is not a gas hub [market_unknown]",
                hub_checked,
            )
        refuse_if_invalid(hub_checked, EtrmImportError, f"line {line}: ")
        market = hub_checked.market
        if market is None:  # pragma: no cover - refused above
            raise EtrmImportError(f"line {line}: hub did not resolve")
        side = cell(record, "side").upper()
        if side not in {"BUY", "SELL", "B", "S"}:
            raise EtrmImportError(f"line {line}: side must be BUY or SELL")
        first = _date(cell(record, "delivery_start"), line, "delivery_start")
        last = _date(cell(record, "delivery_end"), line, "delivery_end")
        period = check_boundary(
            period_start=first,
            period_end=last,
            quantity_unit=cell(record, "quantity_unit"),
            allowed_quantity_units=QUANTITY_UNITS,
            market=market.code,
            price_unit=cell(record, "price_unit"),
            price_verb="trades",
        )
        if period.first is not None and period.first.code.value == "period_reversed":
            raise _refused(
                f"line {line}: delivery_end is before delivery_start [period_reversed]", period
            )
        refuse_if_invalid(period, EtrmImportError, f"line {line}: ")
        start = gas_day_start_for_date(first, market.calendar)
        end = gas_day_start_for_date(last + timedelta(days=1), market.calendar)
        days = (last - first).days + 1
        hours = (end - start).total_seconds() / 3600
        quantity = _number(cell(record, "quantity"), line, "quantity")
        unit = cell(record, "quantity_unit")
        try:
            if unit == "MWh":
                total = quantity
            elif unit in {"MWh/d", "MWh/day"}:
                total = quantity * days
            elif unit == "MW":
                total = quantity * hours
            elif unit in {"th/d", "therm/d"}:
                total = convert(quantity, "th", "MWh") * days
            else:  # pragma: no cover - refused at the boundary above
                raise EtrmImportError(f"line {line}: quantity_unit {unit!r} not supported")
            quote = cell(record, "price_unit")
            per_mwh_unit = f"{market.currency}/MWh"
            price = convert_price(
                _number(cell(record, "price"), line, "price"), quote, per_mwh_unit
            )
        except UnitError as exc:
            raise EtrmImportError(f"line {line}: {exc}") from exc
        if total <= 0:
            raise EtrmImportError(f"line {line}: quantity must be positive (use side for sign)")
        traded = cell(record, "trade_time")
        try:
            observed = datetime.fromisoformat(traded.replace("Z", "+00:00")) if traded else start
        except ValueError as exc:
            raise EtrmImportError(f"line {line}: trade_time {traded!r} is not ISO 8601") from exc
        if observed.tzinfo is None:
            observed = observed.replace(tzinfo=UTC)
        upserts.append(
            {
                "order_observation_id": row_id,
                "provider_id": "ETRM",
                "venue": system[:32] or "ETRM",
                "account_label": cell(record, "counterparty")[:64] or "ETRM",
                "external_order_id": trade_id[:128],
                "side": "BUY" if side in {"BUY", "B"} else "SELL",
                "order_type": "TRADE",
                "hub": market.code,
                "product": "ETRM",
                "contract_code": trade_id[:64],
                "delivery_start_utc": start,
                "delivery_end_utc": end,
                "price": round(price, 6),
                "currency": market.currency,
                "unit": per_mwh_unit,
                "quantity_mwh": round(total, 3),
                "filled_quantity_mwh": round(total, 3),
                "remaining_quantity_mwh": 0.0,
                "status": "FILLED",
                "observed_at_utc": observed.astimezone(UTC),
                "source_system": "ETRM",
                "source_reference": source_reference[:128],
                "linked_strategy_id": None,
                "linked_resource_id": None,
                "research_only": True,
                "human_review_required": True,
                "book_id": cell(record, "book_id")[:64] or None,
            }
        )
    if not upserts and not cancelled:
        raise EtrmImportError("the extract has no trades")
    return EtrmImport(upserts=upserts, cancelled_ids=cancelled)
