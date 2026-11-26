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
METHOD_NOTE_ENDINGS = (
    "; volume only on the ladder",
    ": an FOB cargo is not on a European hub until it is sold or discharged",
)


def is_method_note(text: str) -> bool:
    """Whether a ladder warning only says how a contract is shown (not that something failed)."""

    return text.endswith(METHOD_NOTE_ENDINGS)


def curve_quotes(who: Any, date_from, date_to) -> list:
    """Latest entitled, non-simulated quote per hub and delivery window, for the curve.

    Only quotes in the hub's own currency are used (NBP in GBP, continental hubs in EUR),
    in that currency per MWh: a quote stored in pence per therm is converted through the
    unit authority (``domain.market.units``), never assumed.
    A window that starts on the 1st and lasts 28 to 31 days is read as that whole month,
    so a month-ahead quote with a gas-day-aligned end prices its month.
    """

    from datetime import UTC, datetime, time, timedelta

    from sqlalchemy import func, or_

    from eurogas_nexus.application.projections.daily_closes import _price_unit, per_mwh
    from eurogas_nexus.application.projections.market_reads import filter_entitled_rows
    from eurogas_nexus.db.models import MarketObservationRecord
    from eurogas_nexus.db.session import get_session_factory
    from eurogas_nexus.domain.market.forward_curve import CurveQuote

    with get_session_factory()() as session:
        naive = session.get_bind().dialect.name == "sqlite"

        def bound(day):
            moment = datetime.combine(day, time.min, tzinfo=UTC)
            return moment.replace(tzinfo=None) if naive else moment

        records = (
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
            .order_by(MarketObservationRecord.observed_at_utc)
            .limit(20_000)
            .all()
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
        rows.append(
            {
                "hub": hub,
                "label": str(metadata.get("tenor") or record.product),
                "first": record.period_start_utc.date(),
                "end": record.period_end_utc.date(),
                "price": converted[0],
                "source_system": record.source_system,
            }
        )
    latest: dict[tuple, dict] = {}
    for row in filter_entitled_rows(caller_of(who).principal, rows, source_key="source_system"):
        first, end = row["first"], row["end"]
        if first.day == 1 and 28 <= (end - first).days <= 31:
            end = (first.replace(day=28) + timedelta(days=4)).replace(day=1)
        latest[(row["hub"], first, end)] = row  # ordered by time: the last one wins
    return [
        CurveQuote(
            hub, first, end, row["price"], label=row["label"], reference=row["source_system"]
        )
        for (hub, first, end), row in latest.items()
    ]


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
                "hedge_ratio": None if abs(physical) < 1e-9 else round(-financial / physical, 4),
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

    from datetime import date, datetime, timedelta

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
        if basis["basis"] in {"index", "formula"}:
            # A floating price has no fixed figure to mark against: the volume is on the
            # ladder, its price follows the index (or formula) it names.
            price = None
            warnings.append(
                f"contract {contract.contract_id}: price floats with "
                f"{basis.get('index') or basis.get('label')}; volume only on the ladder"
            )
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
    closes: dict[str, dict] = {}
    closes_as_of: dict[str, datetime] = {}
    simulated_skipped = 0
    demo_marks_used = demo_marks_allowed()
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
        tenor = row["tenor"]
        if tenor not in {"month-ahead", "day-ahead"}:
            continue
        # Prefer month-ahead closes; day-ahead fills hubs without a month-ahead series.
        series = closes.setdefault(row["hub"], {})
        if tenor == "month-ahead" or row["day"] not in series:
            # Marks are money per MWh (positions are MWh): NBP's p/th through the authority.
            series[row["day"]] = row["price_mwh"]
            observed = closes_as_of.get(row["hub"])
            if observed is None or row["observed_at_utc"] >= observed:
                closes_as_of[row["hub"]] = row["observed_at_utc"]
    curve = build_forward_curve(
        curve_quotes(caller, today - timedelta(days=CURVE_QUOTE_LOOKBACK_DAYS), today),
        first_month=horizon_start,
    )
    marks = curve.marks()
    mark_method = {(point.hub, point.month): point.method for point in curve.points}
    flat_months = 0
    for hub, series in closes.items():
        if series:
            latest = series[max(series)]
            month = horizon_start
            while month <= horizon_end:
                key = (hub, f"{month.year:04d}-{month.month:02d}")
                if key not in marks:
                    marks[key] = latest
                    mark_method[key] = "flat"
                    flat_months += 1
                month = (month.replace(day=1) + timedelta(days=32)).replace(day=1)
    resolved, demo_resolved = _resolve_marks(
        caller,
        marks,
        mark_method,
        closes_as_of,
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
