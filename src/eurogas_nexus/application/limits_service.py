"""Credit exposure and mandate usage as a service, for a person or for the firm.

The risk pages and the monitoring worker read the same figures. Both call this module with an
explicit :class:`~eurogas_nexus.application.caller.Caller`: the API passes the request's
caller (portfolio isolation and data scopes applied), the worker passes the firm caller and
sees every book. Nothing here depends on an HTTP request.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from eurogas_nexus.application.caller import Caller
from eurogas_nexus.domain.ontology.markets import quote_currency

HORIZON_MONTHS = 36


def horizon(today: date) -> tuple[date, date]:
    """Today to the last day of the month 36 months on: the ladder's credit horizon."""

    from eurogas_nexus.domain.portfolio.position_ladder import ladder_horizon

    return ladder_horizon(today, HORIZON_MONTHS)


@dataclass
class LimitRows:
    """Rows for a limits report, the warnings behind them and the books each row touches."""

    rows: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    #: Book ids behind each row, in row order (for scoping alerts to who may see them).
    books: list[tuple[str, ...]] = field(default_factory=list)
    #: Newest daily close behind the marks (ISO date), for the figures' method notes.
    marks_as_of: str | None = None


def latest_close_day(closes: dict) -> str | None:
    """The newest close date across the hubs' daily close series, as an ISO date."""

    days = [max(series) for series in closes.values() if series]
    return max(days).isoformat() if days else None


@dataclass
class CounterpartyBook:
    """One credit line with the legs that face its counterparty and the marks that value them."""

    line: Any
    legs: list
    books: tuple[str, ...]


@dataclass
class CreditInputs:
    """Every credit line's legs, with the marks, FX and warnings of the position ladder."""

    lines: list[CounterpartyBook]
    mark: Any
    fx: Any
    warnings: list[str]
    marks_as_of: str | None
    simulated_marks: bool
    #: Hub -> {close day: price}: the daily closes the marks fall back to, for per-row as-of.
    closes: dict = field(default_factory=dict)
    #: ``valuation(currency, as_of)``: forward FX and discounting (``LadderInputs.valuation``).
    valuation: Any = None


def credit_inputs(caller: Caller, today: date) -> CreditInputs:
    """The legs facing each counterparty with an approved credit line (one place builds them)."""

    from eurogas_nexus.application.position_inputs import ladder_inputs
    from eurogas_nexus.core.config import demo_marks_allowed
    from eurogas_nexus.db.models import CreditLineRecord
    from eurogas_nexus.db.session import get_session_factory
    from eurogas_nexus.domain.risk.limits import CounterpartyLeg, CreditLine, fx_lookup

    start, end = horizon(today)
    with get_session_factory()() as session:
        lines = session.query(CreditLineRecord).order_by(CreditLineRecord.name).all()
        session.expunge_all()
    # Receivables look back before today, so read legs from the earliest look-back.
    lookback = max([line.receivable_days for line in lines] or [0])
    inputs = ladder_inputs(caller, today, start - timedelta(days=lookback), end)
    legs_by_ref = {leg.reference: leg for leg in inputs.legs}
    etrm_by_name: dict[str, list[str]] = {}
    for order in inputs.orders:
        if str(order.provider_id).upper() == "ETRM":
            etrm_by_name.setdefault(order.account_label.casefold(), []).append(
                order.order_observation_id
            )

    def mark(hub: str, month: str) -> float | None:
        return inputs.marks.get((hub, month))

    # Contract kinds: a typed contract names the credit line it faces (a cargo, its master's).
    from eurogas_nexus.domain.contracts import kinds

    records_by_id = {item.contract_id: item for item in inputs.contracts}
    typed_by_counterparty: dict[str, list[str]] = {}
    for item in inputs.contracts:
        master = records_by_id.get(item.master_contract_id or "")
        counterparty = kinds.counterparty_id_of(
            kinds.terms_of(item.contract_kind, item.kind_terms),
            kinds.terms_of(master.contract_kind, master.kind_terms) if master else None,
        )
        if counterparty:
            typed_by_counterparty.setdefault(counterparty, []).append(item.contract_id)

    out = []
    for record in lines:
        names = {record.name, record.counterparty_id, *(record.aliases or [])}
        references = [
            *(record.contract_ids or []),
            *typed_by_counterparty.get(record.counterparty_id, []),
        ]
        for name in names:
            references += etrm_by_name.get(str(name).casefold(), [])
        legs, books = [], set()
        for reference in dict.fromkeys(references):
            leg = legs_by_ref.get(reference)
            if leg is None:
                continue
            books.add(leg.book_id or "")
            legs.append(
                CounterpartyLeg(
                    reference=reference,
                    kind="supply_contract" if leg.kind == "physical" else "otc_trade",
                    hub=leg.hub,
                    currency=quote_currency(leg.hub),
                    first_gas_day=leg.first_gas_day,
                    last_gas_day=leg.last_gas_day,
                    mwh_per_day=leg.mwh_per_day,
                    price=leg.price,
                    open_ended=leg.open_ended,
                )
            )
        line = CreditLine(
            counterparty_id=record.counterparty_id,
            name=record.name,
            limit_amount=float(record.limit_amount),
            currency=record.currency,
            collateral_amount=float(record.collateral_amount or 0.0),
            receivable_days=int(record.receivable_days or 0),
            valid_until=record.valid_until,
            legal_entity=record.legal_entity,
            rating=record.rating,
        )
        out.append(CounterpartyBook(line, legs, tuple(sorted(books))))
    warnings = list(inputs.warnings)
    if not lines:
        warnings.append("No credit lines are recorded; risk adds them under Portfolio > Limits.")
    return CreditInputs(
        lines=out,
        mark=mark,
        fx=fx_lookup(inputs.eur_rates),
        warnings=warnings,
        marks_as_of=latest_close_day(inputs.closes),
        simulated_marks=demo_marks_allowed(),
        closes=inputs.closes,
        valuation=inputs.valuation,
    )


def marks_freshness(day: date | None, today: date) -> dict[str, Any]:
    """``marks_as_of``, ``state`` and ``freshness_state`` of a figure priced off ``day``'s close.

    One rule (``domain.monitoring.freshness.close_state``): the previous weekday's close is
    ``current``, one business day older ``late``, more ``stale``, none ``never``;
    ``freshness_state`` is the same verdict in the quotes' vocabulary (FRESH, LATE, STALE,
    MISSING) through the freshness contract's one mapping.
    """

    from eurogas_nexus.application.freshness_contract import projection_state
    from eurogas_nexus.domain.monitoring.freshness import close_state

    state = close_state(day, today)
    return {
        "marks_as_of": day.isoformat() if day else None,
        "state": state,
        "freshness_state": projection_state(state),
    }


#: A mandate is measured in MWh from the firm's own books: no price feeds it, so its figures
#: are as current as the read (Today's mandate headroom says "current" on the same basis).
MANDATE_FRESHNESS = {"marks_as_of": None, "state": "current", "freshness_state": "FRESH"}


def credit_exposure_rows(caller: Caller, today: date) -> LimitRows:
    """Exposure to each counterparty with an approved credit line, against its limit.

    Each row carries ``marks_as_of`` (the oldest newest close among the hubs its legs are
    marked at; the newest close of any hub when it has no leg) and its ``state`` and
    ``freshness_state`` by :func:`marks_freshness` (QA-R-07).
    """

    from eurogas_nexus.domain.monitoring.freshness import marks_as_of
    from eurogas_nexus.domain.risk.limits import credit_exposure

    built = credit_inputs(caller, today)
    result = LimitRows(warnings=built.warnings, marks_as_of=built.marks_as_of)
    newest = date.fromisoformat(built.marks_as_of) if built.marks_as_of else None
    for item in built.lines:
        row = credit_exposure(
            item.line, item.legs, today=today, mark=built.mark, fx=built.fx,
            valuation=built.valuation(item.line.currency, today) if built.valuation else None,
        ).as_row()
        hubs = {leg.hub for leg in item.legs}
        day = marks_as_of(hubs, built.closes) if hubs else newest
        row.update(marks_freshness(day, today))
        result.rows.append(row)
        result.books.append(item.books)
    return result


def mandate_legs(inputs, today: date) -> list:
    """The ladder's legs as mandate legs: each with its book, account and instrument."""

    from eurogas_nexus.domain.risk.limits import MandateLeg, gas_year_end

    accounts = {
        order.order_observation_id: order.account_label
        for order in inputs.orders
        if str(order.provider_id).upper() != "ETRM"
    }
    instruments = {order.order_observation_id: instrument_of(order) for order in inputs.orders}
    return [
        MandateLeg(
            reference=leg.reference,
            kind=leg.kind,
            hub=leg.hub,
            book_id=leg.book_id,
            account=accounts.get(leg.reference, ""),
            first_gas_day=leg.first_gas_day,
            # An evergreen contract is committed only to the end of the current gas year, so
            # its tenor is not "to the horizon" (the same rule credit applies).
            last_gas_day=min(leg.last_gas_day, gas_year_end(today))
            if leg.open_ended
            else leg.last_gas_day,
            mwh_per_day=leg.mwh_per_day,
            index_hub=leg.index_hub,
            instrument="physical"
            if leg.kind == "physical"
            else instruments.get(leg.reference, "future"),
            label=getattr(leg, "label", ""),
        )
        for leg in inputs.legs
    ]


def mandate_of(record):
    """The domain mandate of a stored ``TraderMandateRecord``."""

    from eurogas_nexus.domain.risk.limits import Mandate

    return Mandate(
        mandate_id=record.mandate_id,
        trader=record.trader,
        display_name=record.display_name,
        book_ids=tuple(record.book_ids or ()),
        hubs=tuple(record.hubs or ()),
        max_net_mwh_per_month=record.max_net_mwh_per_month,
        max_tenor_months=record.max_tenor_months,
        physical_allowed=bool(record.physical_allowed),
        financial_allowed=bool(record.financial_allowed),
        valid_until=record.valid_until,
        min_hedge_ratio_pct=record.min_hedge_ratio_pct,
        max_hedge_ratio_pct=record.max_hedge_ratio_pct,
        instruments=tuple(record.instruments or ()),
    )


def books_elsewhere(records, record) -> frozenset[str]:
    """The books the trader's *other* mandates cover (``mandate_usage``'s own-account rule)."""

    return frozenset(
        book
        for other in records
        if other.trader == record.trader and other.mandate_id != record.mandate_id
        for book in (other.book_ids or ())
    ) - set(record.book_ids or ())


def mandate_usage_rows(caller: Caller, today: date) -> LimitRows:
    """Each trader's open positions against their mandate: size, hubs, tenor and products."""

    from eurogas_nexus.application.position_inputs import ladder_inputs
    from eurogas_nexus.db.models import TraderMandateRecord
    from eurogas_nexus.db.session import get_session_factory
    from eurogas_nexus.domain.risk.limits import mandate_usage

    start, end = horizon(today)
    with get_session_factory()() as session:
        records = session.query(TraderMandateRecord).order_by(TraderMandateRecord.trader).all()
        session.expunge_all()
    inputs = ladder_inputs(caller, today, start, end)
    legs = mandate_legs(inputs, today)
    result = LimitRows(warnings=list(inputs.warnings))
    for record in records:
        mandate = mandate_of(record)
        elsewhere = books_elsewhere(records, record)
        result.rows.append(
            {
                **mandate_usage(mandate, legs, today=today, books_elsewhere=elsewhere).as_row(),
                **MANDATE_FRESHNESS,
            }
        )
        # A mandate on the trader's own account (no books) is head-office only when isolated.
        result.books.append(tuple(sorted(mandate.book_ids)) or ("",))
    if not records:
        result.warnings.append(
            "No trader mandates are recorded; risk adds them under Portfolio > Limits."
        )
    return result


def instrument_of(order) -> str:
    """What kind of financial trade a filled order is, for the mandate's instrument list."""

    text = f"{order.product} {order.order_type} {order.contract_code}".casefold()
    if "option" in text or " call" in text or " put" in text:
        return "option"
    if "swap" in text:
        return "swap"
    if str(order.provider_id).upper() == "ETRM":
        return "forward"  # bilateral OTC from the ETRM
    return "future"  # exchange screen trade
