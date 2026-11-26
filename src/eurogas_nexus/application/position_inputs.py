"""Physical and financial position legs and the monthly marks that value them.

Application layer: no HTTP here. The API adapters in ``api/positions.py`` turn a store
failure into a 503; a worker (monitoring) calls these functions with a firm caller.

One place builds what the position ladder, credit exposure, mandate usage and LNG cargo
bids all read: the caller's contracts (portfolio isolation applied, retired contracts left
out) and filled trades as legs, and the forward-curve marks with the latest-close fallback.
Keeping it here, not inside one router, means the risk reads cannot drift from the ladder.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from eurogas_nexus.application.bounded_reads import read_bounded
from eurogas_nexus.application.caller import caller_of
from eurogas_nexus.core.config import demo_marks_allowed
from eurogas_nexus.domain.ontology.identity import resolve_hub
from eurogas_nexus.domain.ontology.markets import european_gas_hubs, quote_currency

HUB_CODES = european_gas_hubs()
HUB_CURRENCY = {code: quote_currency(code) for code in HUB_CODES}
CURVE_QUOTE_LOOKBACK_DAYS = 10



#: The warning a ladder read carries when simulated prices value it (said once, as its source).
SIMULATED_MARKS_WARNING = "Marks are simulated prices, not market prices."


def is_simulated_marks_warning(text: str) -> bool:
    """Whether a warning is the simulated-marks one (an older "DEMO: ..." wording counts too)."""

    return text == SIMULATED_MARKS_WARNING or text.startswith("DEMO")

#: Endings of the notes that say how a contract is shown on the ladder (a floating price, an
#: FOB cargo off the hubs): normal method, not a problem with the book.
#: How an index-priced contract is shown: its volume, with its flat-price exposure on the index.
INDEXED_NOTE_ENDING = "; volume on the ladder, its price exposure on that index"

METHOD_NOTE_ENDINGS = (
    "; volume only on the ladder",
    INDEXED_NOTE_ENDING,
    ": an FOB cargo is not on a European hub until it is sold or discharged",
)


def index_exposure(basis: dict, hub: str, eur_rates: dict[str, float]):
    """``(index hub, differential in the hub's currency)`` of an index-priced contract.

    The index hub is the European gas hub the index names (``TTF month-ahead`` -> TTF);
    ``(None, None)`` for a formula or an index that is not a European hub price (Henry Hub,
    Brent, JKM), whose flat-price exposure stays at the delivery hub. The differential is
    ``None`` when it cannot be put in the hub's currency (the leg is then not valued).
    """

    if basis.get("basis") != "index" or not basis.get("index"):
        return None, None
    index_hub = resolve_hub(str(basis["index"])).hub
    if index_hub is None or index_hub not in HUB_CURRENCY:
        return None, None
    differential, _warning = contract_price_in_hub_currency(
        float(basis.get("differential_mwh") or 0.0),
        basis.get("currency") or HUB_CURRENCY.get(hub, "EUR"),
        HUB_CURRENCY.get(hub),
        eur_rates,
    )
    return index_hub, differential


def is_method_note(text: str) -> bool:
    """Whether a ladder warning only says how a contract is shown (not that something failed)."""

    return text.endswith(METHOD_NOTE_ENDINGS)


#: Curve snapshot (quant review 2026-11-26): how much older than the hub's curve as-of a quote
#: may be, per tenor, in calendar days (a Friday close still prices Monday's months).
CURVE_STALENESS_DAYS = {"month": 3, "quarter": 3, "season": 5, "year": 7}
#: Price types that are not a price on their own: one side of the market.
ONE_SIDED_PRICE_TYPES = frozenset({"bid", "ask", "offer"})


def _curve_tenor(days: int) -> str | None:
    """The staleness class of a delivery window: month (or balance of month), quarter, ..."""

    if days <= 2:
        return None  # day-ahead and weekend: never on the forward curve
    if days <= 31:
        return "month"
    if days <= 92:
        return "quarter"
    if days <= 184:
        return "season"
    return "year"


def curve_snapshot(rows: list[dict]) -> tuple[list, list[str]]:
    """One consistent snapshot of quotes per hub for the forward curve, and what it left out.

    ``rows`` are entitled quotes in the hub's currency per MWh (``hub``, ``label``, ``first``,
    ``end``, ``price``, ``source_system``, ``observed_at``, ``settlement``, ``price_type``),
    time-ordered. The rule, per hub:

    - **as-of**: the newest trade date among the hub's usable quotes;
    - **price type**: a settlement or a mid/last/close price; a bid or an ask alone is not a
      price and is left out;
    - **products**: day-ahead and weekend windows are not curve products and are left out;
    - **source precedence**, per delivery window: settlements before other quotes; then the
      hub's primary source (the one quoting the most windows on the as-of day), then the
      others by name; then the newest;
    - **staleness**: a quote older than its tenor's limit (``CURVE_STALENESS_DAYS``) against
      the as-of is left out, so a nine-day-old quarter never meets today's month.
    """

    from collections import Counter
    from datetime import timedelta

    from eurogas_nexus.domain.market.forward_curve import CurveQuote

    usable: dict[str, list[dict]] = {}
    for row in rows:
        if str(row.get("price_type") or "").lower() in ONE_SIDED_PRICE_TYPES:
            continue
        first, end = row["first"], row["end"]
        if first.day == 1 and 28 <= (end - first).days <= 31:
            end = (first.replace(day=28) + timedelta(days=4)).replace(day=1)
        tenor = _curve_tenor((end - first).days)
        if tenor is None:
            continue
        usable.setdefault(row["hub"], []).append(
            {**row, "end": end, "tenor": tenor, "day": row["observed_at"].date()}
        )
    quotes, left_out = [], []
    for hub, hub_rows in sorted(usable.items()):
        as_of = max(row["day"] for row in hub_rows)
        on_day = Counter(
            row["source_system"] for row in hub_rows if row["day"] == as_of
        )
        primary = max(sorted(on_day), key=lambda source: on_day[source])
        stale: set[tuple] = set()
        chosen: dict[tuple, dict] = {}
        for row in hub_rows:
            if (as_of - row["day"]).days > CURVE_STALENESS_DAYS[row["tenor"]]:
                stale.add((row["first"], row["end"]))
                continue
            rank = (
                bool(row.get("settlement")),
                row["source_system"] == primary,
                _desc(row["source_system"]),
                row["observed_at"],
            )
            key = (row["first"], row["end"])
            if key not in chosen or rank > chosen[key]["_rank"]:
                chosen[key] = {**row, "_rank": rank}
        stale -= set(chosen)  # a window with a quote in date is priced, not left out
        if stale:
            left_out.append(
                f"{hub}: {len(stale)} product(s) quoted only longer ago than their tenor allows "
                f"against the curve's as-of {as_of.isoformat()}; left out of the curve"
            )
        quotes.extend(
            CurveQuote(
                hub, first, end, row["price"], label=row["label"],
                reference=row["source_system"], as_of=row["day"],
            )
            for (first, end), row in sorted(chosen.items())
        )
    return quotes, left_out


def curve_quotes(who: Any, date_from, date_to, *, left_out: list | None = None) -> list:
    """Entitled, non-simulated quotes for the curve, as one snapshot per hub (``curve_snapshot``).

    Only quotes in the hub's own currency are used (NBP in GBP, continental hubs in EUR),
    in that currency per MWh: a quote stored in pence per therm is converted through the
    unit authority (``domain.market.units``), never assumed.
    A window that starts on the 1st and lasts 28 to 31 days is read as that whole month,
    so a month-ahead quote with a gas-day-aligned end prices its month. ``left_out``, when
    given, receives the snapshot's sentences about the quotes it left out.
    """

    from datetime import UTC, datetime, time, timedelta

    from sqlalchemy import func, or_

    from eurogas_nexus.application.projections.daily_closes import _price_unit, per_mwh
    from eurogas_nexus.application.projections.market_reads import filter_entitled_rows
    from eurogas_nexus.db.models import MarketObservationRecord
    from eurogas_nexus.db.session import get_session_factory

    with get_session_factory()() as session:
        naive = session.get_bind().dialect.name == "sqlite"

        def bound(day):
            moment = datetime.combine(day, time.min, tzinfo=UTC)
            return moment.replace(tzinfo=None) if naive else moment

        records = read_bounded(
            session.query(
                MarketObservationRecord.product,
                MarketObservationRecord.price,
                MarketObservationRecord.unit,
                MarketObservationRecord.currency,
                MarketObservationRecord.period_start_utc,
                MarketObservationRecord.period_end_utc,
                MarketObservationRecord.observed_at_utc,
                MarketObservationRecord.source_system,
                MarketObservationRecord.metadata_json,
            )
            .filter(
                or_(
                    func.upper(MarketObservationRecord.unit).like("%MWH%"),
                    func.upper(MarketObservationRecord.unit).like("%/TH"),
                    func.upper(MarketObservationRecord.unit).like("%THERM%"),
                )
            )
            .filter(MarketObservationRecord.observed_at_utc >= bound(date_from))
            .filter(MarketObservationRecord.observed_at_utc < bound(date_to + timedelta(days=1)))
            .order_by(MarketObservationRecord.observed_at_utc),
            20_000,
            what="market observation",
        )
    rows = []
    for record in records:
        metadata = record.metadata_json or {}
        if (metadata.get("simulated") or record.source_system.endswith("_Sim")) and not (
            demo_marks_allowed()
        ):
            continue
        # A quote prices a hub only if its stated hub or its product resolves to one.
        hub = resolve_hub(metadata.get("hub") or record.product).hub
        if hub is None or (record.currency or "").upper() != HUB_CURRENCY.get(hub, "EUR"):
            continue
        # The curve is money per MWh: a quote in p/th is converted by the unit authority.
        converted = per_mwh(float(record.price), _price_unit(record.currency, record.unit))
        if converted is None or converted[1].split("/")[0].upper() != HUB_CURRENCY.get(hub):
            continue
        observed = record.observed_at_utc
        rows.append(
            {
                "hub": hub,
                "label": str(metadata.get("tenor") or record.product),
                "first": record.period_start_utc.date(),
                "end": record.period_end_utc.date(),
                "price": converted[0],
                "source_system": record.source_system,
                "observed_at": observed if observed.tzinfo else observed.replace(tzinfo=UTC),
                "settlement": bool(metadata.get("settlement"))
                or str(metadata.get("price_type") or "").lower() == "settlement",
                "price_type": metadata.get("price_type") or metadata.get("side"),
            }
        )
    entitled = filter_entitled_rows(caller_of(who).principal, rows, source_key="source_system")
    quotes, dropped = curve_snapshot(entitled)
    if left_out is not None:
        left_out.extend(dropped)
    return quotes


def hub_from_text(
    text: str, default: str | None = None, *, session=None
) -> str | None:
    """The hub a delivery point or product names, by the ontology's rules; else ``default``.

    There is no default hub: an unresolved name is reported and mapped, not valued at NBP.
    With ``session`` the deployment's ``delivery_point`` mappings in
    ``source_entity_mappings`` are consulted first (ONT-02, the one identity resolver).
    """

    if session is not None:
        from eurogas_nexus.application.identity_resolution import load_resolver

        return load_resolver(session).hub(text).hub or default
    return resolve_hub(text).hub or default


def gas_year_window(label: str, horizon_end) -> tuple | None:
    """``2026/27``, ``GY-26``, ``2026`` or ``2025+`` (open-ended) as first/last gas day."""

    import re
    from datetime import date, timedelta

    match = re.search(r"(\d{4})|GY-?(\d{2})", (label or "").upper())
    if not match:
        return None
    year = int(match.group(1)) if match.group(1) else 2000 + int(match.group(2))
    first = date(year, 10, 1)
    last = horizon_end if label.strip().endswith("+") else date(year + 1, 10, 1) - timedelta(days=1)
    return first, last


def books_by_id(session) -> dict:
    """Books the caller may see (all of them unless portfolio isolation restricts)."""

    from eurogas_nexus.db.models import TradingBookRecord
    from eurogas_nexus.domain.portfolio.books import Book
    from eurogas_nexus.security.portfolio_scope import restrict

    return {
        row.book_id: Book(
            book_id=row.book_id,
            name=row.name,
            legal_entity=row.legal_entity,
            region=row.region,
            business=row.business,
            base_currency=row.base_currency,
            commodities=tuple(row.commodities or ()),
            active=row.active,
        )
        for row in restrict(session.query(TradingBookRecord), TradingBookRecord, session).all()
    }


def book_of_order(session) -> dict[str, str]:
    from eurogas_nexus.db.models import ScreenOrderObservationRecord

    return {
        order_id: book_id
        for order_id, book_id in session.query(
            ScreenOrderObservationRecord.order_observation_id,
            ScreenOrderObservationRecord.book_id,
        )
        .filter(ScreenOrderObservationRecord.book_id.is_not(None))
        .all()
    }


def ecb_rates(session) -> dict[str, float]:
    """Latest ECB reference rate per currency, units of currency per EUR (EUR itself is 1)."""

    from eurogas_nexus.db.models import FxObservationRecord

    # Demo FX counts only when the operator runs a demo with demo marks, and a real ECB
    # fixing for the same currency always wins over it.
    sources = ("ECB", "DEMO_Sim") if demo_marks_allowed() else ("ECB",)
    rates: dict[str, tuple[int, str, float]] = {}
    for quote, value_date, rate, source in (
        session.query(
            FxObservationRecord.quote_currency,
            FxObservationRecord.value_date,
            FxObservationRecord.rate,
            FxObservationRecord.source_system,
        )
        .filter(FxObservationRecord.base_currency == "EUR")
        .filter(FxObservationRecord.source_system.in_(sources))
        .all()
    ):
        rank = 1 if source == "ECB" else 0
        held = rates.get(quote)
        if rate and (held is None or (rank, value_date) > (held[0], held[1])):
            rates[quote] = (rank, value_date, float(rate))
    return {"EUR": 1.0, **{quote: rate for quote, (_r, _d, rate) in rates.items()}}


def contract_price_in_hub_currency(
    price: float,
    currency: str,
    hub_currency: str | None,
    eur_rates: dict[str, float],
) -> tuple[float | None, str | None]:
    """A contract price in its hub's quote currency, for marking against that hub.

    A price in the hub's own currency is used as recorded. Another currency is
    translated at the latest ECB reference rates (units per EUR), which is how the
    mark-to-market of a fixed foreign-currency price is reported; without a rate the
    leg keeps its volume but is not valued, and the reason is returned.

    Returns:
        ``(price or None, warning or None)``.
    """

    currency = (currency or "GBP").upper()
    if hub_currency is None:
        return None, f"no quote currency for its hub; the {currency} price is not marked"
    if currency == hub_currency:
        return price, None
    from_rate, to_rate = eur_rates.get(currency), eur_rates.get(hub_currency)
    if not from_rate or not to_rate:
        return None, (
            f"no ECB rate to translate its {currency} price into {hub_currency};"
            " volume shown, not valued"
        )
    return price * to_rate / from_rate, (
        f"{currency} price translated into {hub_currency} at the latest ECB reference rate"
    )


def fx_by_hub_for(hubs, reporting_currency: str, eur_rates: dict[str, float]):
    """Multiplier from each hub's quote currency into the reporting currency (shared FX table)."""

    from datetime import date

    from eurogas_nexus.domain.ontology.currency import FxTable

    table = FxTable.from_pivot_map(eur_rates, as_of=date.today(), source="ECB")
    fx: dict[str, float] = {}
    missing: set[str] = set()
    for hub in hubs:
        currency = quote_currency(hub)
        if table.has(currency, reporting_currency):
            fx[hub] = table.rate(currency, reporting_currency)
        else:
            missing.add(currency)
    return fx, missing


def rollup(legs, books, level, *, horizon_start, horizon_end, marks, fx_by_hub) -> list[dict]:
    """Totals per group at ``level`` (firm, legal entity, region, business or book)."""

    from eurogas_nexus.domain.portfolio.books import group_key
    from eurogas_nexus.domain.portfolio.position_ladder import build_ladder, mark_to_market

    groups: dict[str, list] = {}
    for leg in legs:
        groups.setdefault(group_key(leg.book_id, books, level), []).append(leg)
    rollup = []
    for key, members in sorted(groups.items()):
        rows = build_ladder(members, horizon_start=horizon_start, horizon_end=horizon_end)
        physical = sum(row.physical_mwh for row in rows)
        financial = sum(row.financial_mwh for row in rows)
        # Flat-price exposure of the physical legs: index-priced contracts carry none.
        physical_price = sum(row.physical_price_mwh for row in rows)
        value, _missing = mark_to_market(
            members,
            marks,
            horizon_start=horizon_start,
            horizon_end=horizon_end,
            fx_by_hub=fx_by_hub,
        )
        rollup.append(
            {
                "group": key,
                "level": level,
                "physical_mwh": round(physical, 1),
                "financial_mwh": round(financial, 1),
                "net_mwh": round(physical + financial, 1),
                "price_exposure_mwh": round(physical_price + financial, 1),
                "hedge_ratio": None
                if abs(physical_price) < 1e-9
                else round(-financial / physical_price, 4),
                "mark_to_market": None if value is None else round(value, 2),
                "legs": len(members),
            }
        )
    return rollup


#: Cargo statuses whose send-out can still be ahead: a delivered cargo's terminal may still be
#: sending out, a ballast voyage carries no cargo of the firm.
CARGO_PHYSICAL_STATUSES = ("loading", "laden", "discharging", "delivered")
_CARGO_UNDELIVERED = {"loading", "laden", "discharging"}


def _cargo_of(terms) -> str | None:
    """The vessel-feed cargo a cargo contract (Confirmation Notice) names, if any."""

    return getattr(terms, "lng_cargo_id", None)


def cargo_legs(
    session, *, on_ladder: dict[str, str], booked_refs: set[str], now=None
) -> tuple[list, list[str], set[str]]:
    """The firm's cargoes on the ladder: send-out by gas day and the hedges recorded on them.

    A cargo's physical exposure is its plan's send-out by gas day at the terminal's hub
    (``application/lng_in_transit.send_out_plan``, decision log 2026-11-24): one physical leg
    per gas day, ``source`` ``cargo_plan``. The hedges the desk recorded against the cargo
    (``lng_cargo_hedges``, not retired) are financial legs over their delivery month,
    ``source`` ``cargo_hedge``. Both carry ``reference`` ``cargo:<id>`` and the cargo's book.

    Nothing is counted twice: a cargo that a contract leg already on the ladder names
    (``on_ladder``: cargo id -> contract id, a DES Confirmation Notice) adds no send-out, and a
    hedge whose reference is a trade already on the ladder (``booked_refs``) is not added
    again. Returns the legs, warnings, and the ids of cargoes whose
    send-out is on the ladder.
    """

    from calendar import monthrange
    from datetime import UTC, date, datetime

    from eurogas_nexus.application.lng_in_transit import CargoPlanError, send_out_plan
    from eurogas_nexus.db.models import LngCargoHedgeRecord, LngCargoRecord
    from eurogas_nexus.domain.portfolio.position_ladder import PositionLeg
    from eurogas_nexus.security.portfolio_scope import restrict

    moment = now or datetime.now(UTC)
    rows = (
        restrict(session.query(LngCargoRecord), LngCargoRecord, session)
        .filter(LngCargoRecord.book_id.isnot(None))
        .order_by(LngCargoRecord.cargo_id)
        .all()
    )
    if not rows:
        return [], [], set()
    by_id = {row.cargo_id: row for row in rows}
    legs: list = []
    warnings: list[str] = []
    planned: set[str] = set()
    for row in rows:
        if row.status not in CARGO_PHYSICAL_STATUSES:
            continue
        if row.cargo_id in on_ladder:
            warnings.append(
                f"cargo {row.cargo_id}: on the ladder as contract {on_ladder[row.cargo_id]}; "
                "its plan's send-out is not added again"
            )
            continue
        try:
            plan, _slot_id = send_out_plan(session, row.cargo_id, now=moment)
        except CargoPlanError as exc:
            if row.status in _CARGO_UNDELIVERED:
                warnings.append(
                    f"cargo {row.cargo_id}: no send-out on the ladder ({exc.message})"
                )
            continue
        hub = next((cover.hub for cover in plan.months if cover.physical_mwh > 0), None)
        if hub is None or not plan.send_out:
            if row.status in _CARGO_UNDELIVERED:
                warnings.append(
                    f"cargo {row.cargo_id}: no send-out on the ladder (slot {plan.slot_status})"
                )
            continue
        planned.add(row.cargo_id)
        for label, mwh in plan.send_out:
            day = date.fromisoformat(label)
            legs.append(
                PositionLeg(
                    kind="physical",
                    hub=hub,
                    first_gas_day=day,
                    last_gas_day=day,
                    mwh_per_day=mwh,
                    reference=f"cargo:{row.cargo_id}",
                    book_id=row.book_id or "",
                    source="cargo_plan",
                )
            )
    hedges = (
        session.query(LngCargoHedgeRecord)
        .filter(
            LngCargoHedgeRecord.cargo_id.in_(sorted(by_id)),
            LngCargoHedgeRecord.retired_at_utc.is_(None),
        )
        .order_by(LngCargoHedgeRecord.cargo_id, LngCargoHedgeRecord.delivery_month)
        .all()
    )
    hedged: set[str] = set()
    for hedge in hedges:
        if hedge.reference and hedge.reference in booked_refs:
            warnings.append(
                f"cargo {hedge.cargo_id}: hedge {hedge.reference} is a trade already on the "
                "ladder; not added again"
            )
            continue
        year, month = (int(part) for part in hedge.delivery_month.split("-"))
        days = monthrange(year, month)[1]
        legs.append(
            PositionLeg(
                kind="financial",
                hub=hedge.hub.upper(),
                first_gas_day=date(year, month, 1),
                last_gas_day=date(year, month, days),
                mwh_per_day=float(hedge.mwh) / days,
                reference=f"cargo:{hedge.cargo_id}",
                book_id=by_id[hedge.cargo_id].book_id or "",
                source="cargo_hedge",
            )
        )
        hedged.add(hedge.cargo_id)
    if planned or hedged:
        warnings.append(
            f"{len(planned | hedged)} cargo(es) on the ladder from their plans and recorded "
            "hedges; volume only, not valued"
        )
    return legs, warnings, planned


@dataclass
class LadderInputs:
    """Legs and marks as the position ladder builds them, shared with the risk reads."""

    legs: list
    warnings: list[str]
    books: dict
    contracts: list
    orders: list
    marks: dict
    mark_method: dict
    closes: dict
    curve: object
    eur_rates: dict[str, float]
    flat_months: int
    simulated_skipped: int
    #: Per (hub, month) the resolved price behind the mark (``price_resolver.price_payload``).
    resolved: dict = field(default_factory=dict)
    #: Per hub, per close day: the contract the close prices (first gas day, gas days), so a
    #: move is taken within one contract (``domain.market.returns``).
    close_contracts: dict = field(default_factory=dict)
    #: Per hub: which product and source ``closes`` is (``HubCloseSeries.describe``).
    close_series: dict = field(default_factory=dict)
    #: Per hub: (day, price per MWh) of the latest day-ahead close (the spot price).
    day_ahead: dict = field(default_factory=dict)


#: The product a hub's risk series is read from, in order of preference: the month-ahead
#: series prices the forward months the ladder holds; day-ahead only where no month-ahead
#: series is held, as one whole series, never day by day.
RISK_SERIES_TENORS = ("month-ahead", "day-ahead")


@dataclass
class HubCloseSeries:
    """One hub's daily closes for risk: one product (tenor) from one source."""

    tenor: str
    source_system: str
    closes: dict = field(default_factory=dict)
    contracts: dict = field(default_factory=dict)
    as_of: Any = None
    simulated: bool = False

    def describe(self) -> dict[str, Any]:
        return {
            "tenor": self.tenor,
            "source_system": self.source_system,
            "closes": len(self.closes),
            "first": min(self.closes).isoformat() if self.closes else None,
            "last": max(self.closes).isoformat() if self.closes else None,
        }


def hub_close_series(rows) -> dict[str, HubCloseSeries]:
    """Per hub, the daily close series VaR, freshness and the day P&L read: one product.

    ``rows`` are ``daily_rows`` closes (time-ordered; the caller has already applied the
    simulated-price policy). The product is the month-ahead series when the hub has one, else
    its day-ahead series (``RISK_SERIES_TENORS``); the source is the one holding the most
    closes of that product (a licensed source before a simulated one, then the newest close,
    then the name), so two sources never overwrite each other day by day. A day that series
    does not hold is missing: the VaR gap rule handles it. Each close carries the contract it
    prices (first gas day, gas days delivered) for the roll rule.
    """

    from collections import defaultdict

    grouped: dict[tuple[str, str, str], HubCloseSeries] = {}
    for row in rows:
        tenor = row.get("tenor")
        if tenor not in RISK_SERIES_TENORS:
            continue
        key = (row["hub"], tenor, row["source_system"])
        series = grouped.get(key)
        if series is None:
            series = grouped[key] = HubCloseSeries(tenor=tenor, source_system=key[2])
        day = row["day"]
        series.closes[day] = row["price_mwh"]  # time-ordered: the day's last close wins
        start, end = row.get("period_start_utc"), row.get("period_end_utc")
        if start is not None and end is not None:
            series.contracts[day] = (
                start.date().isoformat(),
                max(1, round((end - start).total_seconds() / 86_400)),
            )
        else:
            series.contracts.pop(day, None)
        series.simulated = series.simulated or bool(row.get("simulated"))
        if series.as_of is None or row["observed_at_utc"] >= series.as_of:
            series.as_of = row["observed_at_utc"]
    by_hub: dict[str, list[HubCloseSeries]] = defaultdict(list)
    for (hub, _tenor, _source), series in grouped.items():
        by_hub[hub].append(series)
    chosen: dict[str, HubCloseSeries] = {}
    for hub, candidates in by_hub.items():
        tenor = next(
            t for t in RISK_SERIES_TENORS if any(c.tenor == t for c in candidates)
        )
        chosen[hub] = max(
            (c for c in candidates if c.tenor == tenor),
            key=lambda c: (not c.simulated, len(c.closes), max(c.closes), _desc(c.source_system)),
        )
    return chosen


def _desc(text: str) -> tuple[int, ...]:
    """A key that orders names A before B under ``max``."""

    return tuple(-ord(char) for char in text)


def ladder_inputs(
    who: Any, today, horizon_start, horizon_end, *, now=None, price_book=None
) -> LadderInputs:
    """Physical and financial legs in the caller's books, and the monthly marks for them.

    ``who`` is the API request or an explicit :class:`Caller` (a worker running firm-wide).
    Each month's mark is the one price every screen reads for that hub and month
    (``price_resolver``, P-08): the forward curve's month, a flat fill or a curve-derived
    month enter as ``derived`` candidates beside the held ticks, closes and firm marks.
    ``price_book`` (or the book a composed read shares) is used when given; ``now`` is the
    instant (default: now, or the end of ``today`` for a past day).
    """

    from datetime import UTC, date, datetime, timedelta

    from eurogas_nexus.application.projections.daily_closes import daily_rows
    from eurogas_nexus.application.projections.portfolio_reads import screen_orders
    from eurogas_nexus.domain.market.forward_curve import build_forward_curve
    from eurogas_nexus.domain.market.gas_day import gas_day_label
    from eurogas_nexus.domain.portfolio.position_ladder import PositionLeg

    caller = caller_of(who)
    legs: list[PositionLeg] = []
    warnings: list[str] = []
    from eurogas_nexus.db.models.route_cost import UpstreamResourceContractRecord
    from eurogas_nexus.db.session import get_session_factory

    with get_session_factory()() as session:
        from eurogas_nexus.security.portfolio_scope import restrict

        contracts = (
            restrict(
                session.query(UpstreamResourceContractRecord),
                UpstreamResourceContractRecord,
                session,
            )
            .filter(UpstreamResourceContractRecord.retired_at_utc.is_(None))
            .all()
        )
        books = books_by_id(session)
        order_books = book_of_order(session)
        # ONT-02: the deployment's delivery-point mappings, loaded once for every contract.
        from eurogas_nexus.application.identity_resolution import load_resolver

        identity = load_resolver(session)
        eur_rates = ecb_rates(session)
        orders = screen_orders(session, principal_id=caller.principal_id)
    from eurogas_nexus.domain.contracts import kinds

    cargo_contracts: dict[str, str] = {}  # cargo id -> the contract leg that already holds it
    fob_cargoes: list[tuple[str, str | None]] = []  # FOB contract id, the cargo it names

    for contract in contracts:
        # Contract kinds (CONTRACT_TYPES.md): a master is no position; an FOB cargo is
        # exposure to its formula, not to a European hub, until it is sold or discharged.
        terms = kinds.terms_of(contract.contract_kind, contract.kind_terms)
        if not kinds.feeds_book(contract.contract_kind, terms):
            if contract.contract_kind == kinds.LNG_CARGO:
                fob_cargoes.append((contract.contract_id, _cargo_of(terms)))
            continue
        window = kinds.position_window(contract.contract_kind, terms) or gas_year_window(
            contract.gas_year, horizon_end
        )
        if window is None:
            warnings.append(
                f"contract {contract.contract_id}: gas year {contract.gas_year!r} not understood"
            )
            continue
        hub = identity.hub(
            kinds.position_hub_text(contract.contract_kind, terms, contract.delivery_point_name)
        ).hub
        if hub is None:
            warnings.append(
                f"contract {contract.contract_id}: delivery point "
                f"{contract.delivery_point_name!r} does not name a hub; the contract is left "
                "out of positions and valuation until the point is mapped"
            )
            continue
        price, price_warning = contract_price_in_hub_currency(
            float(contract.contract_price_gbp_mwh),
            contract.contract_price_currency or "GBP",
            HUB_CURRENCY.get(hub),
            eur_rates,
        )
        if price_warning:
            warnings.append(f"contract {contract.contract_id}: {price_warning}")
        basis = kinds.price_basis(contract.contract_kind, terms)
        index_hub, differential = None, None
        if basis["basis"] in {"index", "formula"}:
            # A floating price has no fixed figure to mark against. An index on a European
            # hub carries the leg's flat-price exposure (quant review 2026-11-26): the volume
            # is on the ladder, its price exposure on the index, valued on its premium.
            price = None
            index_hub, differential = index_exposure(basis, hub, eur_rates)
            named = basis.get("index") or basis.get("label")
            shown = INDEXED_NOTE_ENDING if index_hub else "; volume only on the ladder"
            warnings.append(f"contract {contract.contract_id}: price floats with {named}{shown}")
        legs.append(
            PositionLeg(
                kind="physical",
                hub=hub,
                first_gas_day=window[0],
                last_gas_day=window[1],
                mwh_per_day=float(contract.delivery_quantity_mwh_per_day),
                price=price,
                reference=contract.contract_id,
                book_id=contract.book_id or "",
                open_ended=(contract.gas_year or "").strip().endswith("+"),
                source="contract",
                label=contract.contract_name or contract.contract_id,
                index_hub=index_hub,
                index_differential=differential,
            )
        )
        if _cargo_of(terms):
            cargo_contracts[_cargo_of(terms)] = contract.contract_id
    for order in orders:
        filled = float(order.filled_quantity_mwh or 0.0)
        if filled <= 0:
            continue
        start_at, end_at = (
            value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
            for value in (order.delivery_start_utc, order.delivery_end_utc)
        )
        # Delivery windows run gas day start to gas day start (05:00/06:00 UTC), so the number
        # of gas days is the whole days between them, not the calendar date of the end.
        # The first gas day is the one the start instant falls in, by the gas-day calendar:
        # a start before the morning boundary belongs to the previous gas day.
        first = date.fromisoformat(gas_day_label(start_at))
        days = max(1, round((end_at - start_at).total_seconds() / 86_400))
        last = first + timedelta(days=days - 1)
        sign = 1.0 if str(order.side).lower() in {"buy", "bid", "b"} else -1.0
        hub = order.hub.upper()
        currency_matches = (order.currency or "").upper() == HUB_CURRENCY.get(hub, "EUR")
        legs.append(
            PositionLeg(
                kind="financial",
                hub=hub,
                first_gas_day=first,
                last_gas_day=last,
                mwh_per_day=sign * filled / days,
                price=float(order.price) if currency_matches else None,
                reference=order.order_observation_id,
                book_id=order_books.get(order.order_observation_id, ""),
                source="trade",
                label=" ".join(
                    part for part in (str(order.venue or ""), str(order.side or "").lower(), hub)
                    if part
                ),
            )
        )
    with get_session_factory()() as session:
        cargo, cargo_warnings, planned = cargo_legs(
            session,
            on_ladder=cargo_contracts,
            booked_refs={order.order_observation_id for order in orders},
        )
    # An FOB cargo whose vessel has a plan is on the ladder by that plan's send-out.
    warnings += [
        f"contract {contract_id}: an FOB cargo is not on a European hub until it is sold or "
        "discharged"
        for contract_id, cargo_id in fob_cargoes
        if cargo_id not in planned
    ]
    legs += cargo
    warnings += cargo_warnings
    simulated_skipped = 0
    demo_marks_used = demo_marks_allowed()
    usable_rows = []
    for row in daily_rows(
        caller, today - timedelta(days=400), today, tenors=("month-ahead", "day-ahead")
    ):
        if not row.get("hub_resolved", True):
            continue  # a series whose product names no hub cannot mark a hub
        if row["simulated"]:
            # A simulated price must not become a mark or a risk figure (AGENTS.md rule 17),
            # unless the operator runs a demo with EUROGAS_NEXUS_DEMO_MARKS, and then it says so.
            if not demo_marks_allowed():
                simulated_skipped += 1
                continue
            demo_marks_used = True
        usable_rows.append(row)
    # One product from one source per hub (quant review 2026-11-26): a day the month-ahead
    # series does not hold is a gap, never filled with a day-ahead close or another source's.
    series_by_hub = hub_close_series(usable_rows)
    closes = {hub: series.closes for hub, series in series_by_hub.items()}
    close_contracts = {hub: series.contracts for hub, series in series_by_hub.items()}
    closes_as_of = {hub: series.as_of for hub, series in series_by_hub.items()}
    # The latest day-ahead close per hub: the spot price where a screen shows one, as the
    # day-ahead product it is (never a month-ahead close called spot).
    day_ahead: dict[str, tuple] = {}
    for row in usable_rows:
        if row.get("tenor") == "day-ahead":
            held = day_ahead.get(row["hub"])
            if held is None or row["observed_at_utc"] >= held[2]:
                day_ahead[row["hub"]] = (row["day"], row["price_mwh"], row["observed_at_utc"])
    for hub, series in sorted(series_by_hub.items()):
        if series.tenor != "month-ahead":
            warnings.append(
                f"{hub}: no month-ahead history held; its day-ahead series stands in for the "
                "forward months in VaR and the day P&L"
            )
    # One snapshot of quotes per hub (``curve_snapshot``); a month no quote prices is not
    # available, never filled flat with the latest close (which can be a day-ahead price).
    left_out: list[str] = []
    curve = build_forward_curve(
        curve_quotes(
            caller, today - timedelta(days=CURVE_QUOTE_LOOKBACK_DAYS), today, left_out=left_out
        ),
        first_month=horizon_start,
        last_month=horizon_end,
    )
    curve.warnings.extend(left_out)
    marks = curve.marks()
    mark_method = {
        (point.hub, point.month): point.method for point in curve.points if point.price is not None
    }
    # A curve month enters the resolver as of its snapshot's trade date, not the close's.
    curve_as_of = {
        hub: datetime.combine(day, datetime.min.time(), tzinfo=UTC)
        for hub, day in curve.as_of.items()
    }
    resolved, demo_resolved = _resolve_marks(
        caller,
        marks,
        mark_method,
        {**closes_as_of, **curve_as_of},
        horizon_start=horizon_start,
        horizon_end=horizon_end,
        today=today,
        now=now,
        price_book=price_book,
    )
    flat_months = sum(1 for method in mark_method.values() if method == "flat")
    demo_marks_used = demo_marks_used or demo_resolved
    if demo_marks_used:
        warnings.append(
            # Shown to traders: plain words, not the switch's name (UX_REFERENCE rule 3). The
            # desk, explain, alerts and reports find it with ``is_simulated_marks_warning``.
            SIMULATED_MARKS_WARNING
        )
    return LadderInputs(
        legs=legs,
        warnings=warnings,
        books=books,
        contracts=contracts,
        orders=orders,
        marks=marks,
        mark_method=mark_method,
        closes=closes,
        close_contracts=close_contracts,
        day_ahead={hub: (day, price) for hub, (day, price, _at) in day_ahead.items()},
        close_series={hub: series.describe() for hub, series in series_by_hub.items()},
        curve=curve,
        eur_rates=eur_rates,
        flat_months=flat_months,
        simulated_skipped=simulated_skipped,
        resolved=resolved,
    )


#: Ladder ``mark_method`` for a month the resolver priced from a held price.
_METHOD_OF_KIND = {"live_tick": "quoted", "settlement": "quoted", "firm_mark": "firm_mark"}


def _resolve_marks(
    caller,
    marks: dict,
    mark_method: dict,
    closes_as_of: dict,
    *,
    horizon_start,
    horizon_end,
    today,
    now,
    price_book,
) -> tuple[dict, bool]:
    """Replace each month's mark by the one price for it (P-08); returns the payloads.

    The curve month, flat fill or curve-derived month already in ``marks`` enters as a
    ``derived`` candidate (as of the hub's newest close) beside the held ticks, closes and
    firm marks, so a month's own price wins when it is in date and the old mark stands where
    nothing else is held. ``marks`` and ``mark_method`` are updated in place.
    """

    from datetime import UTC, datetime, time, timedelta

    from eurogas_nexus.application.price_resolver import (
        current_price_book,
        open_price_book,
        price_payload,
    )
    from eurogas_nexus.domain.market.price_resolution import DERIVED, PriceCandidate

    allow_simulated = demo_marks_allowed()
    book = price_book or current_price_book(caller.principal)
    if book is None:
        moment = now
        if moment is None:
            moment = datetime.now(UTC)
            if today < moment.date():
                moment = datetime.combine(today, time.max, tzinfo=UTC)
        try:
            book = open_price_book(None, caller, now=moment, allow_simulated=allow_simulated)
        except Exception:  # noqa: BLE001 - the curve marks stand without the resolver
            return {}, False
    hubs = {hub for hub, _ in marks} | {c.hub for c in book.candidates}
    months = []
    month = horizon_start.replace(day=1)
    while month <= horizon_end:
        months.append(month)
        month = (month + timedelta(days=32)).replace(day=1)
    resolved: dict = {}
    demo_used = False
    for hub in sorted(hubs):
        if hub not in HUB_CURRENCY:
            continue
        currency = HUB_CURRENCY[hub]
        as_of = closes_as_of.get(hub)
        for first in months:
            key = (hub, f"{first.year:04d}-{first.month:02d}")
            end = (first + timedelta(days=32)).replace(day=1)
            extra = []
            if key in marks and mark_method.get(key) != "quoted":
                extra.append(
                    PriceCandidate(
                        hub=hub,
                        period_start=first,
                        period_end=end,
                        kind=DERIVED,
                        value=float(marks[key]),
                        unit=f"{currency}/MWh",
                        source_system=f"curve:{mark_method.get(key)}",
                        as_of_utc=as_of if as_of is None or as_of.tzinfo else as_of.replace(
                            tzinfo=UTC),
                        reference=f"{hub}:{key[1]}:{mark_method.get(key)}",
                    )
                )
            answer = book.resolve(
                hub, first, end, extra=extra, allow_simulated=allow_simulated
            )
            if answer is None or answer.unit != f"{currency}/MWh":
                continue
            if answer.kind != DERIVED:
                marks[key] = answer.value
                mark_method[key] = _METHOD_OF_KIND.get(answer.kind, "quoted")
            demo_used = demo_used or answer.simulated
            resolved[key] = price_payload(answer)
    return resolved, demo_used
