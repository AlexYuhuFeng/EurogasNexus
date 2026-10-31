"""Physical and financial position legs and the monthly marks that value them.

One place builds what the position ladder, credit exposure, mandate usage and LNG cargo
bids all read: the caller's contracts (portfolio isolation applied, retired contracts left
out) and filled trades as legs, and the forward-curve marks with the latest-close fallback.
Keeping it here, not inside one router, means the risk reads cannot drift from the ladder.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Request

from eurogas_nexus.api.routes.public.portfolio_common import (
    db_unavailable,
    identity_id,
    load_screen_orders,
    sqlalchemy_error_type,
)
from eurogas_nexus.domain.ontology.markets import european_gas_hubs, quote_currency

HUB_CODES = european_gas_hubs()
HUB_CURRENCY = {code: quote_currency(code) for code in HUB_CODES}
CURVE_QUOTE_LOOKBACK_DAYS = 10


def curve_quotes(request: Request, date_from, date_to) -> list:
    """Latest entitled, non-simulated quote per hub and delivery window, for the curve.

    Only quotes in the hub's own currency are used (NBP in GBP, continental hubs in EUR).
    A window that starts on the 1st and lasts 28 to 31 days is read as that whole month,
    so a month-ahead quote with a gas-day-aligned end prices its month.
    """

    from datetime import UTC, datetime, time, timedelta

    from sqlalchemy import func

    from eurogas_nexus.api.dependencies.row_entitlement import current_principal
    from eurogas_nexus.application.projections.market_reads import filter_entitled_rows
    from eurogas_nexus.db.models import MarketObservationRecord
    from eurogas_nexus.db.session import get_session_factory
    from eurogas_nexus.domain.market.forward_curve import CurveQuote

    sqlalchemy_error = sqlalchemy_error_type()
    try:
        with get_session_factory()() as session:
            naive = session.get_bind().dialect.name == "sqlite"

            def bound(day):
                moment = datetime.combine(day, time.min, tzinfo=UTC)
                return moment.replace(tzinfo=None) if naive else moment

            records = (
                session.query(
                    MarketObservationRecord.product,
                    MarketObservationRecord.price,
                    MarketObservationRecord.currency,
                    MarketObservationRecord.period_start_utc,
                    MarketObservationRecord.period_end_utc,
                    MarketObservationRecord.observed_at_utc,
                    MarketObservationRecord.source_system,
                    MarketObservationRecord.metadata_json,
                )
                .filter(func.upper(MarketObservationRecord.unit).like("%MWH%"))
                .filter(MarketObservationRecord.observed_at_utc >= bound(date_from))
                .filter(
                    MarketObservationRecord.observed_at_utc < bound(date_to + timedelta(days=1))
                )
                .order_by(MarketObservationRecord.observed_at_utc)
                .limit(20_000)
                .all()
            )
    except sqlalchemy_error as exc:
        raise db_unavailable(exc) from exc
    rows = []
    for record in records:
        metadata = record.metadata_json or {}
        if metadata.get("simulated") or record.source_system.endswith("_Sim"):
            continue
        hub = str(metadata.get("hub") or record.product.split(" ")[0]).upper()
        if (record.currency or "").upper() != HUB_CURRENCY.get(hub, "EUR"):
            continue
        rows.append(
            {
                "hub": hub,
                "label": str(metadata.get("tenor") or record.product),
                "first": record.period_start_utc.date(),
                "end": record.period_end_utc.date(),
                "price": float(record.price),
                "source_system": record.source_system,
            }
        )
    latest: dict[tuple, dict] = {}
    for row in filter_entitled_rows(current_principal(request), rows, source_key="source_system"):
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


def hub_from_text(text: str, default: str = "NBP") -> str:
    upper = (text or "").upper()
    return next((hub for hub in HUB_CODES if hub in upper), default)


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

    rates: dict[str, tuple[str, float]] = {}
    for quote, value_date, rate in (
        session.query(
            FxObservationRecord.quote_currency,
            FxObservationRecord.value_date,
            FxObservationRecord.rate,
        )
        .filter(FxObservationRecord.base_currency == "EUR")
        .filter(FxObservationRecord.source_system == "ECB")
        .all()
    ):
        held = rates.get(quote)
        if rate and (held is None or value_date > held[0]):
            rates[quote] = (value_date, float(rate))
    return {"EUR": 1.0, **{quote: rate for quote, (_d, rate) in rates.items()}}


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


def ladder_inputs(request: Request, today, horizon_start, horizon_end) -> LadderInputs:
    """Physical and financial legs in the caller's books, and the monthly marks for them."""

    from datetime import datetime, timedelta

    from eurogas_nexus.api.routes.public.spread_lab import _daily_rows
    from eurogas_nexus.domain.market.forward_curve import build_forward_curve
    from eurogas_nexus.domain.portfolio.position_ladder import PositionLeg

    legs: list[PositionLeg] = []
    warnings: list[str] = []
    sqlalchemy_error = sqlalchemy_error_type()
    try:
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
            eur_rates = ecb_rates(session)
    except sqlalchemy_error as exc:
        raise db_unavailable(exc) from exc
    for contract in contracts:
        window = gas_year_window(contract.gas_year, horizon_end)
        if window is None:
            warnings.append(
                f"contract {contract.contract_id}: gas year {contract.gas_year!r} not understood"
            )
            continue
        hub = hub_from_text(contract.delivery_point_name)
        legs.append(
            PositionLeg(
                kind="physical",
                hub=hub,
                first_gas_day=window[0],
                last_gas_day=window[1],
                mwh_per_day=float(contract.delivery_quantity_mwh_per_day),
                # Contract prices are stored in GBP/MWh; they value only against a GBP mark.
                price=float(contract.contract_price_gbp_mwh)
                if HUB_CURRENCY.get(hub) == "GBP"
                else None,
                reference=contract.contract_id,
                book_id=contract.book_id or "",
            )
        )
    orders, _source, order_warnings = load_screen_orders(identity_id(request))
    warnings += order_warnings
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
        first = start_at.date()
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
            )
        )
    closes: dict[str, dict] = {}
    simulated_skipped = 0
    for row in _daily_rows(request, today - timedelta(days=400), today):
        if row["simulated"]:
            # A simulated price must not become a mark or a risk figure (AGENTS.md rule 17).
            simulated_skipped += 1
            continue
        tenor = row["tenor"]
        if tenor not in {"month-ahead", "day-ahead"}:
            continue
        # Prefer month-ahead closes; day-ahead fills hubs without a month-ahead series.
        series = closes.setdefault(row["hub"], {})
        if tenor == "month-ahead" or row["day"] not in series:
            series[row["day"]] = row["price"]
    curve = build_forward_curve(
        curve_quotes(request, today - timedelta(days=CURVE_QUOTE_LOOKBACK_DAYS), today),
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
    )
