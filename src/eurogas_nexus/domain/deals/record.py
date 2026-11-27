"""The canonical deal record every format adapter produces, in exact decimals.

One record per deal version as the desk knows it: where it was traded and with whom, what
(hub, delivery period, physical or financial), which way, how much and at what price, and
where the record came from (file and line, or entered by hand). Money and volume are
:class:`~decimal.Decimal`; no binary float is stored or summed.

The *deal key* (``venue:venue trade id[:leg]``) makes the same trade the same deal across
repeated exports of a day; the *digest* over the economic fields tells a duplicate (same
digest) from a correction (new digest, a new version).

统一交易记录（精确小数）：交易键识别重复导出；摘要区分重复与更正。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any

SIDES = ("buy", "sell")
INSTRUMENTS = ("future", "forward", "spot", "swap", "option")
STATUSES = ("live", "cancelled")
ORIGINS = ("file", "manual")

#: The canonical fields, in the order a person reads a deal; the format files map to these.
FIELDS: tuple[str, ...] = (
    "venue",
    "venue_trade_id",
    "leg_id",
    "trade_date",
    "trade_time",
    "trader",
    "counterparty",
    "cleared",
    "hub",
    "product",
    "delivery_start",
    "delivery_end",
    "side",
    "volume",
    "volume_unit",
    "price",
    "price_unit",
    "physical",
    "instrument",
    "fees",
    "fee_currency",
    "status",
    "book",
)

#: Fields that change what the deal is; a change in any of them is a new version.
ECONOMIC_FIELDS: tuple[str, ...] = (
    "trade_time_utc",
    "trader",
    "counterparty",
    "cleared",
    "hub",
    "product",
    "delivery_start",
    "delivery_end",
    "side",
    "volume",
    "volume_unit",
    "total_mwh",
    "price",
    "price_currency",
    "price_unit",
    "physical",
    "instrument",
    "fees",
    "fee_currency",
    "status",
    "book_id",
)


@dataclass(frozen=True)
class CanonicalDeal:
    """One deal as captured: the fields every report, sheet and check reads."""

    venue: str
    venue_trade_id: str
    leg_id: str
    trade_date: date
    trade_time_utc: datetime | None
    trader: str
    counterparty: str
    cleared: bool
    hub: str
    product: str
    delivery_start: date
    delivery_end: date
    side: str
    volume: Decimal
    volume_unit: str
    total_mwh: Decimal
    price: Decimal
    price_currency: str
    price_unit: str
    physical: bool
    instrument: str
    fees: Decimal | None
    fee_currency: str | None
    status: str
    book_id: str | None
    origin: str
    source_file: str | None = None
    source_line: int | None = None
    #: Fields the person typed (manual entry), so a result can say which inputs were by hand.
    entered_by_hand: tuple[str, ...] = field(default_factory=tuple)

    @property
    def deal_key(self) -> str:
        return deal_key(self.venue, self.venue_trade_id, self.leg_id)

    @property
    def signed_mwh(self) -> Decimal:
        return self.total_mwh if self.side == "buy" else -self.total_mwh

    def economic(self) -> dict[str, Any]:
        values = asdict(self)
        return {name: _plain(values[name]) for name in ECONOMIC_FIELDS}

    def digest(self) -> str:
        text = json.dumps(self.economic(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(text.encode("utf-8")).hexdigest()


def deal_key(venue: str, venue_trade_id: str, leg_id: str = "") -> str:
    """``EEX:123456`` or ``ICE:9876:2``: one trade across repeated exports."""

    parts = [venue.strip().upper(), venue_trade_id.strip()]
    if leg_id and leg_id.strip():
        parts.append(leg_id.strip())
    return ":".join(parts)[:200]


def _plain(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value.normalize(), "f") if value == value else str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


@dataclass(frozen=True)
class RowProblem:
    """A row the format could not read, and why (shown on the blotter, never dropped)."""

    line: int
    code: str
    message: str
    field: str | None = None
    value: str | None = None
    raw: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "line": self.line,
            "code": self.code,
            "message": self.message,
            "field": self.field,
            "value": self.value,
            "raw": self.raw,
        }


@dataclass
class ParsedFile:
    """What one file gave: the deals it holds, in file order, and every unread row."""

    format_name: str
    deals: list[CanonicalDeal] = field(default_factory=list)
    problems: list[RowProblem] = field(default_factory=list)
    rows: int = 0


def money(value: Decimal | None, places: int = 2) -> str:
    """A decimal as text with fixed places, for files and messages (never a float)."""

    if value is None:
        return ""
    quantum = Decimal(1).scaleb(-places)
    return format(value.quantize(quantum), "f")
