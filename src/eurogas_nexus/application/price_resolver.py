"""The one price every screen reads for a hub, delivery period and instant (P-08, QA-T-02).

:class:`PriceBook` loads, for one caller and one instant, every candidate price the store holds
and answers ``resolve(hub, period)`` through the domain rule
(``domain/market/price_resolution.py``). The Prices board (``/api/market/quotes``), Today
(key figures, My market, the book row), the desk brief, the position ladder's marks and the
valuation snapshot behind the opportunity scan and the LNG cargo economics all ask a price book,
so the same hub and month reads the same price on every screen at one instant.

Candidates:

- **live ticks**: the newest two-sided quote, the newest bid and the newest ask per hub,
  delivery window and source (``market_quotes``) observed in the look-back window; judged by
  the source's declared ``FreshnessPolicy`` through the freshness contract
  (``freshness_contract.source_system_state``), falling back to the source registry's
  expectation for a source no manifest declares (and stale when none is declared);
- **settlements and closes**: every energy-price observation in the look-back window
  (``market_observations``), judged by the business-day close rule;
- **firm marks**: the marks in force at the instant (``firm_marks``), class ``firm_mark``;
- **derived**: figures a reader computed from other prices and adds itself (the ladder's curve
  months and flat fills).

Entitlement is the market reads' rule (``market_reads.row_allowed``): a source family the caller
does not hold is never a candidate. Simulated prices are used only where the reader allows them
and only when no real price is held.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from functools import lru_cache
from typing import Any

from eurogas_nexus.domain.market.price_resolution import (
    FIRM_MARK,
    LIVE_TICK,
    SETTLEMENT,
    PriceCandidate,
    ResolvedPrice,
    day_of,
    month_window,
    resolve_price,
)

#: How far back candidates are read: a weekend and a holiday or two (the quote close look-back).
PRICE_LOOKBACK_DAYS = 10
#: The family recorded for the firm's own marks (public baseline: entitlement never hides them).
FIRM_MARK_SOURCE = "operator-input"
#: Bound on the observations one price book loads.
MAX_OBSERVATIONS = 100_000


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def tick_state(source_system: str, observed: datetime | None, now: datetime) -> str:
    """``current``, ``late`` or ``stale`` for a tick, by its source's declared cadence.

    The freshness contract's receipt rule for a source a connector manifest declares; else the
    source registry's expectation (within it current, beyond stale); with neither, stale (a
    tick nobody declared a cadence for is never read as fresh).
    """

    from eurogas_nexus.application.freshness_contract import receipt_state
    from eurogas_nexus.domain.monitoring.freshness import FreshnessStatus, evaluate_freshness

    if observed is None:
        return "stale"
    definition, minutes = _tick_policy(source_system)
    if definition is not None:
        state = receipt_state(definition, observed, now)
        if state in {"current", "late", "stale"}:
            return state
    if not minutes:
        return "stale"
    status = evaluate_freshness(minutes, observed, now_utc=now)
    return "current" if status is FreshnessStatus.LIVE else "stale"


@lru_cache(maxsize=256)
def _tick_policy(source_system: str):
    """(the source's registered definition or ``None``, the registry expectation in minutes).

    The definition is resolved as ``freshness_contract.source_system_state`` resolves it (the
    connector manifest whose system is the row's source system); both are static declarations,
    read once per source.
    """

    from eurogas_nexus.application.freshness_contract import definition_by_id
    from eurogas_nexus.application.projections.freshness import expectation_for_source
    from eurogas_nexus.domain.connectors.registry import connector_manifests

    wanted = str(source_system or "").casefold()
    manifest = next(
        (item for item in connector_manifests() if item.system.casefold() == wanted), None
    )
    definition = definition_by_id(manifest.source_id) if manifest is not None else None
    return definition, expectation_for_source(source_system)


# ------------------------------------------------------------------------------ loading


def window_start(now: datetime, lookback_days: int) -> datetime:
    """The first instant read: the start of the UTC day ``lookback_days`` before ``now``.

    Day-aligned like the daily-close reads (``daily_rows(today - n, today)``), so a close one
    screen reads by day is a candidate here too.
    """

    first = (_aware(now) - timedelta(days=lookback_days)).date()
    return datetime.combine(first, datetime.min.time(), tzinfo=UTC)


def _start_filter(column, starts: Iterable[date] | None, bound):
    """SQL: ``column`` falls on one of the UTC days ``starts`` (``None``: no filter)."""

    from sqlalchemy import and_, or_

    if starts is None:
        return None
    ranges = [
        and_(
            column >= bound(datetime.combine(day, datetime.min.time(), tzinfo=UTC)),
            column < bound(datetime.combine(day + timedelta(days=1), datetime.min.time(), UTC)),
        )
        for day in sorted(set(starts))
    ]
    return or_(*ranges) if ranges else None


def _per_mwh_factor(currency: str, unit: str) -> tuple[float, str] | None:
    from eurogas_nexus.application.projections.daily_closes import _price_unit, per_mwh

    converted = per_mwh(1.0, _price_unit(currency or "", unit or ""))
    return converted


def quote_candidates(
    session,
    *,
    now: datetime,
    hubs: Iterable[str] | None = None,
    lookback_days: int,
    period_starts: Iterable[date] | None = None,
    known_at: datetime | None = None,
    versions: dict[str, Any] | None = None,
) -> list[PriceCandidate]:
    """The newest two-sided quote, bid and ask per hub, window and source (live ticks).

    ``period_starts`` narrows the read to deliveries starting on those UTC days. With
    ``known_at`` (DATA-1) only ticks received by then are read. ``versions``, when given,
    receives each candidate tick's version (revision 1, known from its receipt).
    """

    from sqlalchemy import and_, case, func, or_

    from eurogas_nexus.db.models import MarketQuoteRecord

    naive = session.get_bind().dialect.name == "sqlite"

    def bound(moment: datetime) -> datetime:
        return moment.replace(tzinfo=None) if naive else moment

    q = MarketQuoteRecord
    window = [
        q.observed_at_utc <= bound(now),
        q.observed_at_utc >= bound(window_start(now, lookback_days)),
    ]
    if known_at is not None:
        window.append(q.received_at_utc <= bound(_aware(known_at)))
    if period_starts is not None:
        starts = list(period_starts)
        if not starts:
            return []
        window.append(_start_filter(q.delivery_start_utc, starts, bound))
    wanted = sorted({h.upper() for h in hubs}) if hubs is not None else None
    if wanted is not None:
        if not wanted:
            return []
        window.append(q.hub.in_(wanted))
    sides = {
        "mid": and_(q.bid_price.isnot(None), q.ask_price.isnot(None)),
        "bid": q.bid_price.isnot(None),
        "ask": q.ask_price.isnot(None),
    }
    # One pass over the window: per hub, delivery and source the newest time of a two-sided
    # quote, of a bid and of an ask. A feed that ticks every few seconds holds tens of
    # thousands of rows here, so the rows themselves are then fetched by those times (the
    # observed-time index) rather than by one condition per key.
    latest = (
        session.query(
            q.hub,
            q.delivery_start_utc,
            q.delivery_end_utc,
            q.source_system,
            *[
                func.max(case((condition, q.observed_at_utc), else_=None)).label(label)
                for label, condition in sides.items()
            ],
        )
        .filter(*window, or_(q.bid_price.isnot(None), q.ask_price.isnot(None)))
        .group_by(q.hub, q.delivery_start_utc, q.delivery_end_utc, q.source_system)
        .all()
    )
    wanted_rows: dict[tuple, list[str]] = {}
    for item in latest:
        for label in sides:
            observed = getattr(item, label)
            if observed is not None:
                identity = (
                    item.hub, item.delivery_start_utc, item.delivery_end_utc,
                    item.source_system, observed,
                )
                wanted_rows.setdefault(identity, []).append(label)
    stamps = sorted({identity[4] for identity in wanted_rows})
    newest: dict[tuple, Any] = {}
    for offset in range(0, len(stamps), 500):
        chunk = stamps[offset : offset + 500]
        for row in session.query(q).filter(*window, q.observed_at_utc.in_(chunk)).all():
            identity = (
                row.hub, row.delivery_start_utc, row.delivery_end_utc, row.source_system,
                row.observed_at_utc,
            )
            for label in wanted_rows.get(identity, ()):
                if (label != "ask" and row.bid_price is None) or (
                    label != "bid" and row.ask_price is None
                ):
                    continue
                key = (
                    label, row.hub, row.delivery_start_utc, row.delivery_end_utc,
                    row.source_system,
                )
                held = newest.get(key)
                if held is None or row.quote_id > held.quote_id:
                    newest[key] = row
    out: list[PriceCandidate] = []
    seen: set[str] = set()
    for row in newest.values():
        if row.quote_id in seen:
            continue
        seen.add(row.quote_id)
        if versions is not None:
            from eurogas_nexus.application.as_of_reads import tick_version

            versions[str(row.quote_id)] = tick_version(row)
        factor = _per_mwh_factor(row.currency, row.unit)
        if factor is None:
            continue
        scale, unit = factor
        bid = None if row.bid_price is None else float(row.bid_price) * scale
        ask = None if row.ask_price is None else float(row.ask_price) * scale
        observed = _aware(row.observed_at_utc)
        start, end = month_window(
            day_of(_aware(row.delivery_start_utc)), day_of(_aware(row.delivery_end_utc))
        )
        simulated = bool(row.simulated) or str(row.source_system).endswith("_Sim")
        out.append(
            PriceCandidate(
                hub=str(row.hub).upper(),
                period_start=start,
                period_end=end,
                kind=LIVE_TICK,
                value=None if bid is None or ask is None else (bid + ask) / 2,
                unit=unit,
                source_system=row.source_system,
                as_of_utc=observed,
                simulated=simulated,
                reference=row.quote_id,
                bid=bid,
                ask=ask,
                state=tick_state(row.source_system, observed, now),
                detail=row.venue,
            )
        )
    return out


def observation_candidates(
    session,
    *,
    now: datetime,
    hubs: Iterable[str] | None = None,
    lookback_days: int,
    period_starts: Iterable[date] | None = None,
    known_at: datetime | None = None,
    versions: dict[str, Any] | None = None,
) -> list[PriceCandidate]:
    """Every energy-price observation in the window (settlements and daily closes).

    ``period_starts`` narrows the read to periods starting on those UTC days.

    DATA-1: with ``known_at`` each figure is read as known then (``application/as_of_reads``):
    the value of the revision current at that instant, and a figure first known later is no
    candidate. ``versions``, when given, receives each candidate's version; without
    ``known_at`` that is the newest revision, or ``capture_pending`` when the stored row
    already differs from it (a correction stored, change capture not yet run).
    """

    from sqlalchemy import func, or_

    from eurogas_nexus.db.models import MarketObservationRecord
    from eurogas_nexus.domain.ontology.identity import resolve_hub

    naive = session.get_bind().dialect.name == "sqlite"

    def bound(moment: datetime) -> datetime:
        return moment.replace(tzinfo=None) if naive else moment

    o = MarketObservationRecord
    extra = []
    if period_starts is not None:
        starts = list(period_starts)
        if not starts:
            return []
        extra.append(_start_filter(o.period_start_utc, starts, bound))
    records = (
        session.query(
            o.observation_id,
            o.product,
            o.price,
            o.unit,
            o.currency,
            o.observed_at_utc,
            o.source_system,
            o.metadata_json,
            o.period_start_utc,
            o.period_end_utc,
            o.market_venue,
        )
        .filter(
            or_(
                func.upper(o.unit).like("%MWH%"),
                func.upper(o.unit).like("%/TH"),
                func.upper(o.unit).like("%THERM%"),
            )
        )
        .filter(o.observed_at_utc <= bound(now))
        .filter(o.observed_at_utc >= bound(window_start(now, lookback_days)))
        .filter(*extra)
        .order_by(o.observed_at_utc.desc())
        .limit(MAX_OBSERVATIONS)
        .all()
    )
    wanted = {h.upper() for h in hubs} if hubs is not None else None
    known = None
    if known_at is not None or versions is not None:
        from eurogas_nexus.application.as_of_reads import settlement_versions

        known = settlement_versions(session, records, as_of=_aware(known_at))
    resolved: dict[str, Any] = {}
    out: list[PriceCandidate] = []
    for record in records:
        if known is not None:
            record, version = _as_known(record, known.get(str(record.observation_id)), known_at)
            if record is None:
                continue  # first known after known_at
            if versions is not None:
                versions[str(record.observation_id)] = version
        metadata = record.metadata_json or {}
        stated = metadata.get("hub") or record.product
        resolution = resolved.get(stated)
        if resolution is None:
            resolution = resolved[stated] = resolve_hub(stated)
        if not resolution.resolved or resolution.hub is None:
            continue  # an unresolved product prices no hub (ONT-02)
        hub = resolution.hub.upper()
        if wanted is not None and hub not in wanted:
            continue
        factor = _per_mwh_factor(record.currency, record.unit)
        if factor is None:
            continue
        start, end = month_window(
            day_of(_aware(record.period_start_utc)), day_of(_aware(record.period_end_utc))
        )
        if end <= start:
            continue
        out.append(
            PriceCandidate(
                hub=hub,
                period_start=start,
                period_end=end,
                kind=SETTLEMENT,
                value=float(record.price) * factor[0],
                unit=factor[1],
                source_system=record.source_system,
                as_of_utc=_aware(record.observed_at_utc),
                simulated=bool(metadata.get("simulated"))
                or str(record.source_system).endswith("_Sim"),
                reference=record.observation_id,
                detail="settlement" if metadata.get("settlement") else "close",
            )
        )
    return out


def _as_known(record, version, known_at: datetime | None):
    """``(record, version)`` with the record's figure as ``version`` states it.

    As of an instant the figure is the version's; at the newest, the stored row stands and a
    version whose figure differs from it is reported as ``capture_pending``.
    """

    from types import SimpleNamespace

    from eurogas_nexus.application.as_of_reads import BASIS_EVENT, BASIS_PENDING, KnownVersion

    if version is None:
        return (None, None) if known_at is not None else (record, None)
    if version.basis != BASIS_EVENT:
        return record, version
    stated = version.values
    if known_at is not None:
        fields = {name: getattr(record, name) for name in record._fields}
        for name in ("price", "unit", "currency"):
            if stated.get(name) is not None:
                fields[name] = stated[name]
        return SimpleNamespace(**fields), version
    same = (
        stated.get("price") is not None
        and abs(float(stated["price"]) - float(record.price)) <= 1e-9
        and (stated.get("unit") or record.unit) == record.unit
        and (stated.get("currency") or record.currency) == record.currency
    )
    if same:
        return record, version
    return record, KnownVersion(
        revision=None, published_at_utc=None, known_from_utc=None, basis=BASIS_PENDING
    )


def firm_mark_candidates(
    session, *, now: datetime, hubs: Iterable[str] | None = None
) -> list[PriceCandidate]:
    """The firm's marks in force at ``now`` (class ``firm_mark``, never a market price)."""

    from eurogas_nexus.db.repositories.commercial_assumptions import current_firm_marks

    wanted = {h.upper() for h in hubs} if hubs is not None else None
    out: list[PriceCandidate] = []
    for mark in current_firm_marks(session, as_of_utc=now):
        if wanted is not None and mark.hub.upper() not in wanted:
            continue
        factor = _per_mwh_factor(mark.currency, mark.unit)
        if factor is None:
            continue
        start, end = month_window(mark.period.start, mark.period.end)
        out.append(
            PriceCandidate(
                hub=mark.hub.upper(),
                period_start=start,
                period_end=end,
                kind=FIRM_MARK,
                value=float(mark.value) * factor[0],
                unit=factor[1],
                source_system=FIRM_MARK_SOURCE,
                as_of_utc=_aware(mark.entered_at_utc),
                reference=mark.mark_id,
                detail=mark.entered_by,
            )
        )
    return out


# ------------------------------------------------------------------------------ the book


@dataclass
class PriceBook:
    """Every candidate one caller may use at one instant, and the answers drawn from them."""

    now: datetime
    candidates: list[PriceCandidate]
    principal: Any = None
    allow_simulated: bool = True
    #: DATA-1: the version of each tick and settlement candidate by reference (only when the
    #: book was opened ``known_at`` an instant or ``with_versions``).
    versions: dict[str, Any] = field(default_factory=dict, repr=False)
    #: DATA-1: the instant the book was read as known at (``None``: the live book).
    known_at: datetime | None = None
    _cache: dict[tuple, ResolvedPrice | None] = field(default_factory=dict, repr=False)
    _by_hub: dict[str, list[PriceCandidate]] | None = field(default=None, repr=False)

    def _entitled(self, source_system: str) -> bool:
        if self.principal is None:
            return True
        from eurogas_nexus.application.projections.market_reads import row_allowed

        return row_allowed(self.principal, source_system)

    def for_hub(self, hub: str) -> list[PriceCandidate]:
        """The candidates held for one hub."""

        if self._by_hub is None:
            index: dict[str, list[PriceCandidate]] = {}
            for candidate in self.candidates:
                index.setdefault(candidate.hub.upper(), []).append(candidate)
            self._by_hub = index
        return self._by_hub.get(hub.upper(), [])

    def resolve(
        self,
        hub: str,
        start: date,
        end: date,
        *,
        side: str = "mid",
        extra: Sequence[PriceCandidate] = (),
        allow_simulated: bool | None = None,
    ) -> ResolvedPrice | None:
        """The one price for ``hub`` and ``[start, end)`` (a month's end normalised).

        ``extra`` adds a reader's own derived candidates (that answer is not cached);
        ``allow_simulated`` overrides the book's default for one reader (the ladder's marks
        use demo prices only with demo marks on).
        """

        start, end = month_window(start, end)
        simulated = self.allow_simulated if allow_simulated is None else allow_simulated
        key = (hub.upper(), start, end, side, simulated)
        if not extra and key in self._cache:
            return self._cache[key]
        answer = resolve_price(
            [*self.for_hub(hub), *extra],
            hub=hub,
            period_start=start,
            period_end=end,
            now=self.now,
            side=side,
            entitled=self._entitled,
            allow_simulated=simulated,
        )
        if not extra:
            self._cache[key] = answer
        return answer

    def month(self, hub: str, month: str, **kwargs) -> ResolvedPrice | None:
        """The price for a delivery month ``YYYY-MM``."""

        first = date(int(month[:4]), int(month[5:7]), 1)
        end = (first.replace(day=28) + timedelta(days=4)).replace(day=1)
        return self.resolve(hub, first, end, **kwargs)


def open_price_book(
    session=None,
    who: Any = None,
    *,
    now: datetime | None = None,
    hubs: Iterable[str] | None = None,
    allow_simulated: bool = True,
    lookback_days: int = PRICE_LOOKBACK_DAYS,
    period_starts: Iterable[date] | None = None,
    known_at: datetime | None = None,
    with_versions: bool = False,
) -> PriceBook:
    """Load a price book for ``who`` (an API request, a ``Caller`` or ``None``: every source).

    ``session`` is the caller's open session; without one a session is opened for the load.
    With no runtime store configured the book is empty. ``hubs`` and ``period_starts`` narrow
    the load for a reader that needs a few prices (the valuation snapshot). A longer
    ``lookback_days`` never changes an answer a shorter one gives: anything older is staler.

    DATA-1: ``known_at`` reads the book as known at that instant (it is also the book's
    ``now``): ticks received by then, each settlement at its revision current then, the firm
    marks in force then. ``with_versions`` records each candidate's version in
    ``book.versions`` without changing any answer. Neither is used by any existing screen.
    """

    from eurogas_nexus.application.caller import caller_of

    known = _aware(known_at)
    moment = known or _aware(now) or datetime.now(UTC)
    principal = None if who is None else caller_of(who).principal
    hub_list = None if hubs is None else sorted({h.upper() for h in hubs if h})
    starts = None if period_starts is None else sorted(set(period_starts))
    versions: dict[str, Any] | None = {} if (known is not None or with_versions) else None

    def load(active) -> list[PriceCandidate]:
        window = {"now": moment, "hubs": hub_list, "lookback_days": lookback_days}
        dated = {"known_at": known, "versions": versions}
        return [
            *quote_candidates(active, period_starts=starts, **window, **dated),
            *observation_candidates(active, period_starts=starts, **window, **dated),
            *firm_mark_candidates(active, now=moment, hubs=hub_list),
        ]

    if session is not None:
        candidates = load(session)
    else:
        from eurogas_nexus.db.session import get_session_factory, resolve_database_url

        if resolve_database_url() is None:
            candidates = []
        else:
            with get_session_factory()() as active:
                candidates = load(active)
    return PriceBook(
        now=moment,
        candidates=candidates,
        principal=principal,
        allow_simulated=allow_simulated,
        versions=versions or {},
        known_at=known,
    )


def price_payload(resolved: ResolvedPrice | None) -> dict[str, Any] | None:
    """The resolved price as an API block: per MWh, in the hub's quotation, and provenance.

    ``value``/``unit`` are the hub's own quotation (NBP in p/th), ``value_mwh``/``unit_mwh``
    the same price per MWh; ``kind`` is ``live_tick``, ``settlement``, ``derived`` or
    ``firm_mark``; ``state`` the contract word (``current``, ``late``, ``stale``) and
    ``freshness_state`` the projection word (``FRESH``, ``LATE``, ``STALE``).
    """

    if resolved is None:
        return None
    from eurogas_nexus.application.freshness_contract import projection_state
    from eurogas_nexus.application.projections.daily_closes import in_native_unit

    shown, unit = in_native_unit(resolved.hub, resolved.value, resolved.unit)
    return {
        "hub": resolved.hub,
        "period_start": resolved.period_start.isoformat(),
        "period_end": resolved.period_end.isoformat(),
        "side": resolved.side,
        "value": round(shown, 4),
        "unit": unit,
        "value_mwh": round(resolved.value, 6),
        "unit_mwh": resolved.unit,
        "kind": resolved.kind,
        "source_system": resolved.source_system,
        "as_of_utc": None if resolved.as_of_utc is None else resolved.as_of_utc.isoformat(),
        "state": resolved.state,
        "freshness_state": projection_state(resolved.state),
        "simulated": resolved.simulated,
        "basis": resolved.basis,
        "reference": resolved.reference,
    }


def attach_resolved(rows: Iterable[dict[str, Any]], book: PriceBook) -> list[dict[str, Any]]:
    """Add ``resolved_price`` to each quote row: the one price for its hub and delivery window.

    The row keeps its own bid, ask and age; ``resolved_price`` is what every other screen reads
    for the same hub and window at the book's instant (``None`` when nothing is held).
    """

    out: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        start = _instant(row.get("delivery_start_utc"))
        end = _instant(row.get("delivery_end_utc"))
        hub = str(row.get("hub") or "")
        resolved = None
        if hub and start is not None and end is not None and end > start:
            resolved = book.resolve(hub, start.date(), end.date())
        item["resolved_price"] = price_payload(resolved)
        out.append(item)
    return out


def _instant(value: Any) -> datetime | None:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return _aware(value) if isinstance(value, datetime) else None


def resolve_close_series(
    book: PriceBook | None,
    hub: str,
    closes: Mapping[date, Mapping[str, Any]],
    *,
    max_gap_days: int,
) -> dict[str, Any] | None:
    """The one price for the delivery window of a close series' newest close.

    For a screen that picks a hub's front month from its daily closes (Today, the desk brief):
    the window is the newest close's delivery period, the price is the book's answer for it
    (a fresher tick, a later close or the close itself), and the change is against the newest
    earlier close **of the same window** at most ``max_gap_days`` before the price's day (a
    close for another month is another contract, not a day change). ``None`` when the newest
    close states no window or nothing resolves; the caller then keeps its close.
    """

    from eurogas_nexus.application.projections.daily_closes import in_native_unit

    if book is None or not closes:
        return None
    days = sorted(closes)
    last = closes[days[-1]]
    start, end = _instant(last.get("period_start_utc")), _instant(last.get("period_end_utc"))
    if start is None or end is None or end <= start:
        return None
    window = month_window(start.date(), end.date())
    resolved = book.resolve(hub, *window)
    if resolved is None:
        return None
    shown, unit = in_native_unit(hub, resolved.value, resolved.unit)
    priced_day = day_of(resolved.as_of_utc) if resolved.as_of_utc is not None else days[-1]
    change = change_vs = None
    for day in reversed(days):
        if day >= priced_day:
            continue
        row = closes[day]
        first, final = _instant(row.get("period_start_utc")), _instant(row.get("period_end_utc"))
        if first is None or final is None or month_window(first.date(), final.date()) != window:
            continue
        if (priced_day - day).days <= max_gap_days:
            previous, _ = in_native_unit(hub, float(row["price_mwh"]), str(row["unit_mwh"]))
            change, change_vs = round(shown - previous, 4), day
        break
    return {
        "resolved": resolved,
        "value": shown,
        "unit": unit,
        "change": change,
        "change_vs": change_vs,
        "payload": price_payload(resolved),
    }


#: A price book a composed read shares with the reads inside it (Today and its ladder).
_SHARED_BOOK: ContextVar[PriceBook | None] = ContextVar("shared_price_book", default=None)


@contextmanager
def shared_price_book(book: PriceBook | None) -> Iterator[None]:
    """Inside this block, :func:`current_price_book` answers ``book`` for its own caller."""

    token = _SHARED_BOOK.set(book)
    try:
        yield
    finally:
        _SHARED_BOOK.reset(token)


def current_price_book(principal: Any) -> PriceBook | None:
    """The shared book when it was loaded for the same principal and scopes, else ``None``."""

    book = _SHARED_BOOK.get()
    if book is None:
        return None

    def identity(item: Any) -> tuple:
        return (
            getattr(item, "principal_id", None),
            tuple(getattr(item, "data_scopes", ()) or ()),
            getattr(item, "auth_method", None),
        )

    if book.principal is None or principal is None:
        return book if book.principal is principal else None
    return book if identity(book.principal) == identity(principal) else None
