"""Store ticks from a licensed exchange/broker feed (or the demo simulator).

One call stores a batch of top-of-book quotes with the session fields the feed carries
(``domain/market/feed.py``) and the trade prints, under the source family. PostgreSQL stays
the event log the quote stream reads.

Sources: the licensed families the operator import accepts (``EEX``, ``ICE_OCM``,
``Trayport``), entitled per principal as every quote is; and ``EEX_Sim`` (the demo exchange
feed simulator) only where simulated sources are allowed (the demo profile), stored
``simulated``. Prices arrive in the hub's native quotation (NBP p/th, the others EUR/MWh) and
are stored per MWh in the quote currency with the native values in the metadata; sizes arrive
in the screen convention (MW, NBP therms/day) and are stored per gas day in MWh, as the CSV
import does.

许可行情源（或演示模拟器）的逐笔报价与成交入库。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy.orm import Session

from eurogas_nexus.domain.market.feed import (
    FeedError,
    TradePrint,
    check_jump,
    check_not_future,
    check_plausible_price,
)
from eurogas_nexus.domain.market.gas_day import gas_day_label
from eurogas_nexus.domain.market.products import ProductCodeError, board_tenor, resolve_product
from eurogas_nexus.domain.market.units import HUB_NATIVE_PRICE_UNIT, convert_energy, convert_price
from eurogas_nexus.ingestion.licensed_quote_import import (
    _PRODUCT_ALIASES,
    LICENSED_QUOTE_SOURCES,
    SUPPORTED_HUBS,
    intake_hub,
)

SIMULATED_FEED_SOURCES = {"EEX_Sim": "EEX (simulated)", "DEMO_Sim": "Exchange feed (simulated)"}
MAX_TICKS_PER_CALL = 5_000
_SESSION_PRICE_FIELDS = ("open", "high", "low", "vwap", "settlement", "prior_settlement", "last")


@dataclass
class TickBatchResult:
    quotes: int
    trades: int

    def as_dict(self) -> dict[str, Any]:
        return {"quotes": self.quotes, "trades": self.trades}


def _venue(source_system: str) -> str:
    return LICENSED_QUOTE_SOURCES.get(source_system) or SIMULATED_FEED_SOURCES[source_system]


def check_source(source_system: str, *, simulated_allowed: bool) -> bool:
    """Whether ``source_system`` may be stored here; returns whether it is simulated."""

    if source_system in LICENSED_QUOTE_SOURCES:
        return False
    if source_system in SIMULATED_FEED_SOURCES:
        if not simulated_allowed:
            raise FeedError("simulated feeds are accepted only in the demo profile")
        return True
    raise FeedError(
        f"source must be one of {sorted([*LICENSED_QUOTE_SOURCES, *SIMULATED_FEED_SOURCES])}"
    )


#: Data-scope prefix that lets a connector's service key publish a venue's prices.
PUBLISH_PREFIX = "PUBLISH:"


def publisher_refusal(principal: Any, source_system: str) -> str | None:
    """Why ``principal`` may not deliver ticks under ``source_system``, or ``None``.

    A licensed label (``EEX``, ``ICE_OCM``, ``Trayport``) tells every reader the price came
    from that venue under the firm's licence. Only the venue's connector may write it
    (security review H4): a **service** identity, authenticated by its own **identity key**,
    whose data scopes name ``PUBLISH:<family>``. Reading a family (``EEX``) or everything
    (``*``) is not a licence to publish as the venue; a person, a browser session and the
    deployment token never publish one. A person who holds a screen export imports it as a
    file, which is labelled as a file import by that person. Simulated sources are labelled
    simulated wherever they travel and need no grant.
    """

    from eurogas_nexus.security.identity import normalize_data_scope

    if source_system not in LICENSED_QUOTE_SOURCES:
        return None
    if getattr(principal, "auth_method", None) != "identity_key":
        return (
            f"{source_system} prices are delivered only by the venue's connector with its own "
            "service key; import a screen export as a file instead"
        )
    if str(getattr(principal, "principal_type", "")).upper() != "SERVICE":
        return (
            f"a person may not publish {source_system} prices; the venue's connector does, "
            "and a screen export is imported as a file labelled with who imported it"
        )
    scopes = {
        normalize_data_scope(scope).casefold()
        for scope in getattr(principal, "data_scopes", ()) or ()
    }
    if f"{PUBLISH_PREFIX}{source_system}".casefold() in scopes:
        return None
    return (
        f"this key may not deliver {source_system} prices: its data scopes must name "
        f"{PUBLISH_PREFIX}{source_system} (reading a family, or '*', publishes nothing)"
    )


def _when(value: Any, field: str) -> datetime:
    if isinstance(value, datetime):
        stamp = value
    else:
        try:
            stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError as exc:
            raise FeedError(f"{field} must be ISO 8601") from exc
    if stamp.tzinfo is None:
        raise FeedError(f"{field} needs an explicit UTC offset")
    return stamp.astimezone(UTC)


def _period(hub: str, product: str, observed: datetime):
    hub = intake_hub(hub)
    if hub not in SUPPORTED_HUBS:
        raise FeedError(f"unsupported hub {hub!r}")
    code = _PRODUCT_ALIASES.get((product or "").strip().upper(), (product or "").strip())
    # The trade date is the gas day the tick falls in (06:00 CET boundary), not the UTC date.
    trade_date = date.fromisoformat(gas_day_label(observed))
    try:
        period = resolve_product(code, trade_date)
    except ProductCodeError as exc:
        raise FeedError(f"{hub} {product}: {exc}") from exc
    return hub, code, period, board_tenor(code, period.kind, period.label)


def _price(
    hub: str, value: Any, *, kind: str = "", label: str = ""
) -> tuple[float | None, float | None, str]:
    """(per MWh in the quote currency, native, native unit); implausible prices refused."""

    if value is None or value == "":
        return None, None, ""
    native = float(value)
    if native != native or abs(native) > 1e6:
        raise FeedError("price out of range")
    unit = HUB_NATIVE_PRICE_UNIT.get(hub, "EUR/MWh")
    check_plausible_price(native, unit, product_kind=kind, label=label or hub)
    per_mwh_unit = "GBP/MWh" if unit == "GBp/th" else unit
    return round(convert_price(native, unit, per_mwh_unit), 6), native, unit


def _size(hub: str, value: Any, hours_per_day: float) -> float | None:
    """Screen size (MW, or therms/day for NBP) as MWh per gas day."""

    if value is None or value == "":
        return None
    size = float(value)
    if size < 0 or size != size or size > 1e10:
        raise FeedError("size out of range")
    if HUB_NATIVE_PRICE_UNIT.get(hub) == "GBp/th":
        return round(convert_energy(size, "therm", "MWh"), 6)
    return round(size * hours_per_day, 6)


def quote_row(source_system: str, simulated: bool, tick: dict[str, Any],
              received: datetime) -> dict[str, Any]:
    observed = _when(tick.get("exchange_time") or tick.get("timestamp"), "exchange_time")
    hub, code, period, tenor = _period(tick.get("hub"), tick.get("product"), observed)
    label = f"{hub} {code}"
    check_not_future(observed, received, label=label)
    hours = period.hours / period.gas_days

    def price(field: str):
        return _price(hub, tick.get(field), kind=period.kind, label=f"{label} {field}")

    bid, native_bid, unit = price("bid")
    ask, native_ask, _ = price("ask")
    if bid is None and ask is None:
        raise FeedError(f"{hub} {code}: bid or ask is required")
    if bid is not None and ask is not None and bid > ask:
        raise FeedError(f"{hub} {code}: crossed quote")
    session = {name: price(name)[0] for name in _SESSION_PRICE_FIELDS}
    venue = _venue(source_system)
    instrument_id = f"{venue.upper().replace(' ', '-')}-{hub}-{period.label}"[:128]
    sequence = str(tick.get("sequence") or "")
    identity = f"{source_system}|{hub}|{period.label}|{observed.isoformat()}|{sequence}"
    trade_count = tick.get("trade_count")
    return {
        "quote_id": f"tick-{source_system.lower()}-"
        f"{hashlib.sha256(identity.encode()).hexdigest()[:24]}",
        "source_system": source_system,
        "source_record_id": f"{instrument_id}@{observed.isoformat()}"[:128],
        "venue": venue,
        "instrument_id": instrument_id,
        "hub": hub,
        "product": tenor,
        "delivery_start_utc": period.delivery_start_utc,
        "delivery_end_utc": period.delivery_end_utc,
        "bid_price": bid,
        "ask_price": ask,
        "last_price": session["last"],
        "bid_quantity_mwh": _size(hub, tick.get("bid_qty"), hours),
        "ask_quantity_mwh": _size(hub, tick.get("ask_qty"), hours),
        "currency": "GBP" if unit == "GBp/th" else unit.split("/")[0],
        "unit": "MWh",
        "observed_at_utc": observed,
        "received_at_utc": received,
        "source_reference": "feed:simulated-exchange" if simulated else f"feed:{source_system}",
        "freshness": "simulated" if simulated else "streaming",
        "quality_score": 0.0 if simulated else 1.0,
        "simulated": simulated,
        "last_quantity_mwh": _size(hub, tick.get("last_qty"), hours),
        "session_open": session["open"],
        "session_high": session["high"],
        "session_low": session["low"],
        "vwap": session["vwap"],
        "volume_mwh": _size(hub, tick.get("volume"), hours),
        "trade_count": None if trade_count in (None, "") else int(trade_count),
        "settlement_price": session["settlement"],
        "prior_settlement_price": session["prior_settlement"],
        "open_interest_mwh": _size(hub, tick.get("open_interest"), hours),
        "metadata_json": {
            "source_family": source_system.removesuffix("_Sim"),
            "product_label": period.label,
            "product_kind": period.kind,
            "native_unit": unit,
            "native_bid": native_bid,
            "native_ask": native_ask,
            "price_level": "L1",
            "simulated": simulated,
            "official_entitlement_required": True,
        },
    }


def trade_row(source_system: str, simulated: bool, item: dict[str, Any],
              received: datetime) -> dict[str, Any]:
    traded = _when(item.get("exchange_time") or item.get("timestamp"), "exchange_time")
    hub, code, period, tenor = _period(item.get("hub"), item.get("product"), traded)
    check_not_future(traded, received, label=f"{hub} {code} trade")
    price, native, unit = _price(
        hub, item.get("price"), kind=period.kind, label=f"{hub} {code} trade"
    )
    hours = period.hours / period.gas_days
    size = _size(hub, item.get("qty"), hours)
    printed = TradePrint(
        trade_id=str(item.get("trade_id") or ""), hub=hub, product=tenor,
        price=price if price is not None else float("nan"), quantity_mwh=size or 0.0,
        traded_at_utc=traded, trade_type=str(item.get("trade_type") or "screen"),
        aggressor=item.get("aggressor"), venue=_venue(source_system), broker=item.get("broker"),
    )
    printed.validate()
    return {
        "trade_id": f"{source_system.lower()}-{printed.trade_id}"[:128],
        "source_system": source_system,
        "venue": printed.venue,
        "instrument_id": f"{printed.venue.upper().replace(' ', '-')}-{hub}-{period.label}"[:128],
        "hub": hub,
        "product": tenor,
        "delivery_start_utc": period.delivery_start_utc,
        "delivery_end_utc": period.delivery_end_utc,
        "price": price,
        "quantity_mwh": size,
        "currency": "GBP" if unit == "GBp/th" else unit.split("/")[0],
        "trade_type": printed.trade_type,
        "aggressor": printed.aggressor,
        "broker": printed.broker,
        "traded_at_utc": traded,
        "received_at_utc": received,
        "simulated": simulated,
        "metadata_json": {"native_price": native, "native_unit": unit,
                          "product_label": period.label, "simulated": simulated},
    }


def _mid(row: dict[str, Any]) -> float | None:
    bid, ask = row.get("bid_price"), row.get("ask_price")
    if bid is not None and ask is not None:
        return (bid + ask) / 2
    return bid if bid is not None else ask


def _check_jumps(session: Session, quote_rows: list[dict[str, Any]]) -> None:
    """Refuse a quote whose mid jumped implausibly from the last one for its instrument.

    The previous mid is the newest stored quote from the same source for the same instrument
    and delivery, then each earlier quote of the batch in exchange-time order.
    """

    if not quote_rows:
        return
    from eurogas_nexus.db.models import MarketQuoteRecord

    previous: dict[tuple[str, str], float | None] = {}
    for row in sorted(quote_rows, key=lambda item: item["observed_at_utc"]):
        key = (row["source_system"], row["instrument_id"])
        if key not in previous:
            stored = (
                session.query(MarketQuoteRecord.bid_price, MarketQuoteRecord.ask_price)
                .filter(
                    MarketQuoteRecord.source_system == row["source_system"],
                    MarketQuoteRecord.instrument_id == row["instrument_id"],
                    MarketQuoteRecord.delivery_start_utc == row["delivery_start_utc"],
                    MarketQuoteRecord.observed_at_utc <= row["observed_at_utc"],
                )
                .order_by(MarketQuoteRecord.observed_at_utc.desc())
                .first()
            )
            previous[key] = (
                _mid({"bid_price": stored[0], "ask_price": stored[1]}) if stored else None
            )
        mid = _mid(row)
        if mid is None:
            continue
        label = f"{row['hub']} {row['metadata_json']['product_label']}"
        check_jump(mid, previous[key], label=label)
        previous[key] = mid


def ingest_ticks(
    session: Session,
    *,
    source_system: str,
    quotes: list[dict[str, Any]],
    trades: list[dict[str, Any]] | None = None,
    simulated_allowed: bool = False,
    received_at: datetime | None = None,
) -> TickBatchResult:
    """Store one batch of quotes and trade prints.

    Raises:
        FeedError: an unknown source, a bad tick or print; nothing of the batch is stored.
    """

    from sqlalchemy import insert

    from eurogas_nexus.db.models import MarketQuoteRecord, MarketTradeRecord

    trades = trades or []
    if len(quotes) + len(trades) > MAX_TICKS_PER_CALL:
        raise FeedError(f"at most {MAX_TICKS_PER_CALL} ticks per call")
    simulated = check_source(source_system, simulated_allowed=simulated_allowed)
    received = received_at or datetime.now(UTC)
    quote_rows = [quote_row(source_system, simulated, tick, received) for tick in quotes]
    trade_rows = [trade_row(source_system, simulated, item, received) for item in trades]
    _check_jumps(session, quote_rows)
    if trade_rows:
        ids = [row["trade_id"] for row in trade_rows]
        held = {value for (value,) in session.query(MarketTradeRecord.trade_id)
                .filter(MarketTradeRecord.trade_id.in_(ids))}
        fresh = [row for row in trade_rows if row["trade_id"] not in held]
        if fresh:
            session.execute(insert(MarketTradeRecord), fresh)
    if quote_rows:
        ids = [row["quote_id"] for row in quote_rows]
        held = {value for (value,) in session.query(MarketQuoteRecord.quote_id)
                .filter(MarketQuoteRecord.quote_id.in_(ids))}
        fresh_quotes = [row for row in quote_rows if row["quote_id"] not in held]
        if fresh_quotes:
            session.execute(insert(MarketQuoteRecord), fresh_quotes)
    session.flush()
    return TickBatchResult(len(quote_rows), len(trade_rows))
