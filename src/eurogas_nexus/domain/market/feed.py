"""The licensed exchange/broker feed contract: what one tick may carry beyond bid and offer.

EEX, ICE Endex and Trayport deliver more than a price. These are the fields a desk uses to
decide, and the product stores what the customer's own licensed feed delivers (nothing is
fetched, inferred or redistributed; a field the feed does not carry stays empty):

========================  ==================================================================
field                     why a trader or risk manager uses it
========================  ==================================================================
bid / ask, sizes          the price you can deal at and how much of it (top of book); a
                          quote with no size is not a market
depth (optional)          what the next levels cost when the size is larger than the top
last trade price, size    where business was actually done, not where it was offered
session open/high/low     the day's range: breakouts, how far the market already moved
VWAP                      the volume-weighted average traded price of the session: the
                          benchmark a fill is judged against
volume, number of trades  liquidity: a level on no volume is not a level
settlement, prior settl.  the exchange's official end-of-day price and the change against it
open interest             exchange futures: positions outstanding (not for spot WD/DA)
trade type                screen, block, OTC cleared, auction: a block print is not the
                          screen market and is kept out of screen VWAP
venue, broker             where it traded (Trayport carries the broker)
exchange time, received   the instant the venue stamped and the instant we stored it; their
                          difference is the feed's delay
========================  ==================================================================

Quantities follow the screen convention (MW for MWh-priced hubs, therms/day for NBP) and are
stored per gas day in MWh, as the quote import already does. Prices are stored per MWh in the
quote currency; the native quotation stays in ``metadata_json``.

许可行情源合约：一笔行情除买卖价外还可携带的字段（成交价量、开高低、VWAP、成交量与笔数、
结算价、未平仓量、成交类型、场所与经纪商、交易所时间与接收时间）。只存储客户自有授权源实际
提供的字段，不推断、不转发。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

#: Trade types a feed may flag. Only ``screen`` prints enter the screen VWAP a signal uses.
TRADE_TYPES = ("screen", "block", "otc_cleared", "auction")
AGGRESSOR_SIDES = ("buy", "sell")

#: The optional session fields a quote row may carry (``market_quotes`` columns).
SESSION_FIELDS = (
    "last_quantity_mwh",
    "session_open",
    "session_high",
    "session_low",
    "vwap",
    "volume_mwh",
    "trade_count",
    "settlement_price",
    "prior_settlement_price",
    "open_interest_mwh",
)

#: What each licensed family's feed carries, by the field names above (plus the trade print).
#: A connector stores only these; the rest stay empty for that source.
FEED_FIELDS_BY_FAMILY: dict[str, tuple[str, ...]] = {
    "EEX": (
        "bid", "ask", "bid_quantity", "ask_quantity", "last", *SESSION_FIELDS, "trades",
        "trade_type", "exchange_time",
    ),
    "ICE_OCM": (
        "bid", "ask", "bid_quantity", "ask_quantity", "last", *SESSION_FIELDS, "trades",
        "trade_type", "exchange_time",
    ),
    # Broker screens: no exchange settlement or open interest; the broker is on the print.
    "Trayport": (
        "bid", "ask", "bid_quantity", "ask_quantity", "last", "last_quantity_mwh",
        "session_open", "session_high", "session_low", "vwap", "volume_mwh", "trade_count",
        "trades", "trade_type", "broker", "exchange_time",
    ),
}


class FeedError(ValueError):
    """A tick or a trade print that cannot be stored as given."""


# --------------------------------------------------------------------- plausibility (A7)
#
# A feed is trusted only as far as its prices are plausible. A price a hundred times the
# market (a fat finger, pence keyed as pounds), a forward month below zero or a quote stamped
# in the future is refused with the reason, and nothing of the batch is stored, so it can
# never reach a strategy, a mark or the prompt panel (persona review P-03).
#
# Bands are in the hub's native quotation and wide on purpose: they hold every price the
# NWE hubs printed in the 2021-2022 crisis (TTF within-day near 340 EUR/MWh, NBP day-ahead
# near 800 p/th) with room to spare. Prompt products (within-day, day-ahead, weekend) may go
# below zero, as German and Dutch within-day did briefly; a curve product may not.

#: (prompt floor, curve floor, ceiling) per native price unit.
PLAUSIBLE_NATIVE_PRICE: dict[str, tuple[float, float, float]] = {
    "EUR/MWh": (-50.0, 0.0, 500.0),
    "GBp/th": (-150.0, 0.0, 1_500.0),
}
#: Product kinds that may print below zero.
PROMPT_KINDS = frozenset({"within_day", "day_ahead", "weekend"})
#: A quote may be stamped this far after the moment it is received (venue clock skew).
MAX_CLOCK_SKEW_SECONDS = 120
#: A mid this many times the previous one for the same instrument, or this many times
#: smaller, is not a market move between two ticks; it is a keying or unit error.
MAX_TICK_JUMP_FACTOR = 3.0
#: Below this absolute price the jump test means nothing (a move from 0.2 to 0.7).
JUMP_TEST_MIN_PRICE = 2.0


def check_plausible_price(native: float, unit: str, *, product_kind: str, label: str) -> None:
    """Refuse a native price outside the band for its unit and product kind."""

    band = PLAUSIBLE_NATIVE_PRICE.get(unit)
    if band is None:
        return
    prompt_floor, curve_floor, ceiling = band
    floor = prompt_floor if product_kind in PROMPT_KINDS else curve_floor
    if native > ceiling:
        raise FeedError(
            f"{label}: {native:g} {unit} is above the plausible ceiling of {ceiling:g}; "
            "check the price and its unit"
        )
    if native < floor:
        raise FeedError(
            f"{label}: {native:g} {unit} is below the plausible floor of {floor:g} for this "
            "product; check the price and its sign"
        )


def check_not_future(observed: datetime, received: datetime, *, label: str) -> None:
    """Refuse a tick stamped later than it arrived (beyond clock skew)."""

    if (observed - received).total_seconds() > MAX_CLOCK_SKEW_SECONDS:
        raise FeedError(
            f"{label}: exchange time {observed.isoformat()} is after it was received "
            f"({received.isoformat()}); check the venue clock or the time zone"
        )


def check_jump(new_mid: float, previous_mid: float | None, *, label: str) -> None:
    """Refuse a mid that jumped by more than ``MAX_TICK_JUMP_FACTOR`` from the previous one."""

    if previous_mid is None:
        return
    if abs(new_mid) < JUMP_TEST_MIN_PRICE or abs(previous_mid) < JUMP_TEST_MIN_PRICE:
        return
    ratio = new_mid / previous_mid
    if ratio > MAX_TICK_JUMP_FACTOR or ratio < 1 / MAX_TICK_JUMP_FACTOR:
        raise FeedError(
            f"{label}: mid {new_mid:g} is {ratio:.1f}x the previous {previous_mid:g}; "
            "a keying or unit error, not a market move"
        )


@dataclass(frozen=True)
class TradePrint:
    """One executed trade as the venue printed it."""

    trade_id: str
    hub: str
    product: str
    price: float
    quantity_mwh: float
    traded_at_utc: datetime
    trade_type: str = "screen"
    aggressor: str | None = None
    venue: str = ""
    broker: str | None = None

    def validate(self) -> None:
        if not self.trade_id:
            raise FeedError("a trade print needs its venue trade id")
        if self.trade_type not in TRADE_TYPES:
            raise FeedError(f"trade type must be one of {TRADE_TYPES}")
        if self.aggressor is not None and self.aggressor not in AGGRESSOR_SIDES:
            raise FeedError("aggressor must be buy or sell")
        if not self.quantity_mwh > 0:
            raise FeedError("a trade print needs a positive size")
        if self.price != self.price or abs(self.price) > 1e6:
            raise FeedError("trade price out of range")
        if self.traded_at_utc.tzinfo is None:
            raise FeedError("trade time needs an explicit UTC offset")


def session_stats(prints: list[TradePrint]) -> dict[str, float | int | None]:
    """Open, high, low, last, VWAP, volume and count of the screen prints given (in order).

    Block, OTC-cleared and auction prints are counted in ``all_volume_mwh`` only: they are
    not the screen market a signal or a fill is judged against.
    """

    screen = [item for item in prints if item.trade_type == "screen"]
    volume = sum(item.quantity_mwh for item in screen)
    return {
        "session_open": screen[0].price if screen else None,
        "session_high": max(item.price for item in screen) if screen else None,
        "session_low": min(item.price for item in screen) if screen else None,
        "last": screen[-1].price if screen else None,
        "vwap": round(sum(item.price * item.quantity_mwh for item in screen) / volume, 6)
        if volume > 0
        else None,
        "volume_mwh": round(volume, 6),
        "trade_count": len(screen),
        "all_volume_mwh": round(sum(item.quantity_mwh for item in prints), 6),
    }
