"""One price per hub, delivery period and instant (P-08, QA-T-02, QA-L-22).

Before this module the Prices board, Today, the desk brief, the position ladder, the LNG cargo
economics and the opportunity scan each chose their own price for the same hub and month, so
TTF Dec-26 could read three different numbers at one instant, and a quote of any age beat a
settlement published since. Every one of those reads now asks :func:`resolve_price` with the
candidates the store holds and gets the same answer.

**Candidates** come in four kinds:

- ``live_tick``: a top-of-book quote from an exchange or broker feed (``market_quotes``); its
  mid for a two-sided quote, or one side when a side is asked for;
- ``settlement``: a settlement or daily close (``market_observations``);
- ``firm_mark``: the desk's own mark (``firm_marks``), never a market price;
- ``derived``: a figure computed from other prices (a curve month priced from a quarter, a
  month filled flat from the front month).

**Freshness.** Each candidate is judged ``current``, ``late`` or ``stale`` by its class's
maximum age: a tick by its source's declared ``FreshnessPolicy`` (the freshness contract,
``application/freshness_contract.receipt_state``: current within ``normal_max_age_minutes``,
late up to ``stale_after_minutes``, stale beyond), every other kind by the business-day close
rule (``domain.monitoring.freshness.close_state``). A candidate is *in date* when it is
``current`` or ``late``. The application layer may pass a candidate's judged ``state``; when it
does not, it is judged here from the candidate's own thresholds.

**Precedence** (first rule that yields a candidate wins):

1. Entitlement: a candidate whose source the caller may not use is never considered.
   Simulated candidates are considered only where simulated prices are allowed, and only when
   no real candidate exists at all (a real price always wins over a demo price).
2. The freshest in-date market price (``live_tick`` or ``settlement``); on an exact tie of
   as-of, the tick. So a fresh tick beats yesterday's close, and a stale tick loses to a
   settlement published since.
3. The newest in-date firm mark: the desk's figure where the market has none in date. A firm
   mark never beats an in-date market price.
4. The freshest in-date derived price.
5. Nothing in date: the freshest candidate of any kind, returned with its ``stale`` state so
   the screen says so (ties: tick, settlement, firm mark, derived).

The answer names the kind, the source, the as-of, the state and why it was chosen. Pure: no
database, clock or registry access.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta

from eurogas_nexus.domain.monitoring.freshness import close_state

LIVE_TICK = "live_tick"
SETTLEMENT = "settlement"
DERIVED = "derived"
FIRM_MARK = "firm_mark"
#: Every kind, in tie-break order (strongest first).
PRICE_KINDS = (LIVE_TICK, SETTLEMENT, FIRM_MARK, DERIVED)
#: The kinds that are market prices (rule 2).
MARKET_KINDS = frozenset({LIVE_TICK, SETTLEMENT})
#: A candidate's judged state; ``current`` and ``late`` are in date.
PRICE_STATES = ("current", "late", "stale")
IN_DATE_STATES = frozenset({"current", "late"})
#: Sides a reader may ask for: a mid (the default) or one executable side of a tick.
SIDES = ("mid", "bid", "ask")

#: Why a candidate was chosen (``ResolvedPrice.basis``).
BASIS_MARKET = "freshest_in_date_market_price"
BASIS_FIRM_MARK = "firm_mark_no_market_price_in_date"
BASIS_DERIVED = "derived_no_direct_price_in_date"
BASIS_NOTHING_IN_DATE = "freshest_held_nothing_in_date"


@dataclass(frozen=True)
class PriceCandidate:
    """One price the store holds for a hub and delivery period.

    ``value`` is the price per MWh in ``unit`` (``EUR/MWh``, ``GBP/MWh``): for a tick, its mid
    when two-sided (``None`` otherwise); ``bid`` and ``ask`` are the tick's sides. ``state``
    is the judged freshness when the caller has judged it; otherwise :func:`judge` judges a
    tick by ``current_within`` and ``stale_after`` (its source's declared policy) and any other
    kind by the business-day close rule on its as-of day.
    """

    hub: str
    period_start: date
    period_end: date
    kind: str
    value: float | None
    unit: str
    source_system: str
    as_of_utc: datetime | None
    simulated: bool = False
    reference: str = ""
    bid: float | None = None
    ask: float | None = None
    state: str | None = None
    current_within: timedelta | None = None
    stale_after: timedelta | None = None
    detail: str = ""

    def side_value(self, side: str) -> float | None:
        """The price this candidate gives for ``side``.

        A tick gives its mid, bid or ask; every other kind gives its one value for any side
        (a settlement is a level, not an executable side).
        """

        if self.kind != LIVE_TICK or side == "mid":
            return self.value
        return self.bid if side == "bid" else self.ask

    def covers(self, start: date, end: date) -> bool:
        """Whether the candidate prices the period ``[start, end)``.

        The period's first gas day must match; the end may be stated exclusive or inclusive
        (``period_end`` one day short), as the stores hold both.
        """

        return self.period_start == start and self.period_end in {end, end - timedelta(days=1)}


@dataclass(frozen=True)
class ResolvedPrice:
    """The one price for a hub, period and instant, with where it came from."""

    hub: str
    period_start: date
    period_end: date
    side: str
    value: float
    unit: str
    kind: str
    source_system: str
    as_of_utc: datetime | None
    state: str
    simulated: bool
    reference: str
    basis: str
    considered: int
    detail: str = ""

    @property
    def in_date(self) -> bool:
        """Whether the price is within its class's maximum age."""

        return self.state in IN_DATE_STATES

    def as_dict(self) -> dict[str, object]:
        """Plain data for an API response (``as_of_utc`` in ISO 8601)."""

        return {
            "hub": self.hub,
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "side": self.side,
            "value": round(self.value, 6),
            "unit": self.unit,
            "kind": self.kind,
            "source_system": self.source_system,
            "as_of_utc": None if self.as_of_utc is None else _utc(self.as_of_utc).isoformat(),
            "state": self.state,
            "simulated": self.simulated,
            "reference": self.reference,
            "basis": self.basis,
            "considered": self.considered,
        }


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def judge(candidate: PriceCandidate, now: datetime) -> str:
    """``current``, ``late`` or ``stale`` for one candidate at ``now``.

    A state the caller already judged is kept. A tick without one is judged by its declared
    thresholds (no declared threshold, or no as-of, is ``stale``: never read as fresh); every
    other kind by the business-day close rule on its as-of day.
    """

    if candidate.state in PRICE_STATES:
        return candidate.state
    if candidate.as_of_utc is None:
        return "stale"
    observed, moment = _utc(candidate.as_of_utc), _utc(now)
    if candidate.kind == LIVE_TICK:
        if candidate.stale_after is None:
            return "stale"
        age = max(moment - observed, timedelta(0))
        if candidate.current_within is not None and age <= candidate.current_within:
            return "current"
        return "late" if age <= candidate.stale_after else "stale"
    state = close_state(observed.date(), moment.date())
    return "stale" if state == "never" else state


def _as_of_key(candidate: PriceCandidate) -> datetime:
    return datetime.min.replace(tzinfo=UTC) if candidate.as_of_utc is None else _utc(
        candidate.as_of_utc
    )


def _freshest(candidates: list[PriceCandidate]) -> PriceCandidate:
    """The newest as-of; on a tie the stronger kind (tick, settlement, firm mark, derived)."""

    return max(
        candidates, key=lambda c: (_as_of_key(c), -PRICE_KINDS.index(c.kind), c.reference)
    )


def resolve_price(
    candidates: Iterable[PriceCandidate],
    *,
    hub: str,
    period_start: date,
    period_end: date,
    now: datetime,
    side: str = "mid",
    entitled: Callable[[str], bool] | None = None,
    allow_simulated: bool = True,
) -> ResolvedPrice | None:
    """The one price for ``hub`` and ``[period_start, period_end)`` at ``now`` (see module).

    Args:
        candidates: Every price held; those for other hubs or periods, observed after
            ``now``, of an unknown kind or without a value for ``side`` are ignored.
        hub: The hub code (``TTF``).
        period_start: First gas day of the delivery period.
        period_end: First gas day after it.
        now: The instant the price is for; also the clock freshness is judged on.
        side: ``mid`` (default), ``bid`` or ``ask``.
        entitled: Whether the caller may use a source system; ``None`` allows every source.
        allow_simulated: Whether demo prices may be used at all.

    Returns:
        The resolved price, or ``None`` when no usable candidate is held.

    Raises:
        ValueError: An unknown ``side``.
    """

    if side not in SIDES:
        raise ValueError(f"side must be one of {SIDES}")
    wanted = hub.upper()
    moment = _utc(now)
    usable: list[PriceCandidate] = []
    for candidate in candidates:
        if candidate.hub.upper() != wanted or candidate.kind not in PRICE_KINDS:
            continue
        if not candidate.covers(period_start, period_end):
            continue
        if candidate.as_of_utc is not None and _utc(candidate.as_of_utc) > moment:
            continue  # not yet known at this instant
        if candidate.side_value(side) is None:
            continue
        if entitled is not None and not entitled(candidate.source_system):
            continue
        if candidate.simulated and not allow_simulated:
            continue
        usable.append(candidate)
    real = [c for c in usable if not c.simulated]
    pool = real or usable
    if not pool:
        return None
    judged = [replace(c, state=judge(c, moment)) for c in pool]
    in_date = [c for c in judged if c.state in IN_DATE_STATES]
    chosen: PriceCandidate | None = None
    basis = BASIS_NOTHING_IN_DATE
    for kinds, why in (
        (MARKET_KINDS, BASIS_MARKET),
        (frozenset({FIRM_MARK}), BASIS_FIRM_MARK),
        (frozenset({DERIVED}), BASIS_DERIVED),
    ):
        group = [c for c in in_date if c.kind in kinds]
        if group:
            chosen, basis = _freshest(group), why
            break
    if chosen is None:
        chosen = _freshest(judged)
    value = chosen.side_value(side)
    assert value is not None  # filtered above
    return ResolvedPrice(
        hub=wanted,
        period_start=period_start,
        period_end=period_end,
        side=side,
        value=float(value),
        unit=chosen.unit,
        kind=chosen.kind,
        source_system=chosen.source_system,
        as_of_utc=chosen.as_of_utc,
        state=str(chosen.state),
        simulated=chosen.simulated,
        reference=chosen.reference,
        basis=basis,
        considered=len(pool),
        detail=chosen.detail,
    )


def month_window(start: date, end: date) -> tuple[date, date]:
    """``[start, end)`` with a whole month normalised to its exclusive end.

    A window that starts on the 1st and lasts 27 to 31 days is read as that whole month (a
    month-ahead product stored with an inclusive or gas-day-aligned end prices its month), so
    every reader keys the same month the same way.
    """

    if start.day == 1 and 27 <= (end - start).days <= 31:
        return start, (start.replace(day=28) + timedelta(days=4)).replace(day=1)
    return start, end


def day_of(value: datetime | date) -> date:
    """The UTC calendar day of an instant (a date is returned as it is)."""

    if isinstance(value, datetime):
        return _utc(value).date()
    return value
