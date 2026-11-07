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

    end = (today.replace(day=1) + timedelta(days=32 * HORIZON_MONTHS)).replace(day=1)
    return today, end - timedelta(days=1)


@dataclass
class LimitRows:
    """Rows for a limits report, the warnings behind them and the books each row touches."""

    rows: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    #: Book ids behind each row, in row order (for scoping alerts to who may see them).
    books: list[tuple[str, ...]] = field(default_factory=list)


def credit_exposure_rows(caller: Caller, today: date) -> LimitRows:
    """Exposure to each counterparty with an approved credit line, against its limit."""

    from eurogas_nexus.application.position_inputs import ladder_inputs
    from eurogas_nexus.db.models import CreditLineRecord
    from eurogas_nexus.db.session import get_session_factory
    from eurogas_nexus.domain.risk.limits import (
        CounterpartyLeg,
        CreditLine,
        credit_exposure,
        fx_lookup,
    )

    start, end = horizon(today)
    with get_session_factory()() as session:
        lines = session.query(CreditLineRecord).order_by(CreditLineRecord.name).all()
        session.expunge_all()
    # Receivables look back before today, so read legs from the earliest look-back.
    lookback = max([line.receivable_days for line in lines] or [0])
    inputs = ladder_inputs(caller, today, start - timedelta(days=lookback), end)
    result = LimitRows(warnings=list(inputs.warnings))
    legs_by_ref = {leg.reference: leg for leg in inputs.legs}
    etrm_by_name: dict[str, list[str]] = {}
    for order in inputs.orders:
        if str(order.provider_id).upper() == "ETRM":
            etrm_by_name.setdefault(order.account_label.casefold(), []).append(
                order.order_observation_id
            )
    fx = fx_lookup(inputs.eur_rates)

    def mark(hub: str, month: str) -> float | None:
        return inputs.marks.get((hub, month))

    for record in lines:
        names = {record.name, record.counterparty_id, *(record.aliases or [])}
        references = [*(record.contract_ids or [])]
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
        result.rows.append(credit_exposure(line, legs, today=today, mark=mark, fx=fx).as_row())
        result.books.append(tuple(sorted(books)))
    if not lines:
        result.warnings.append(
            "No credit lines are recorded; risk adds them under Portfolio > Limits."
        )
    return result


def mandate_usage_rows(caller: Caller, today: date) -> LimitRows:
    """Each trader's open positions against their mandate: size, hubs, tenor and products."""

    from eurogas_nexus.application.position_inputs import ladder_inputs
    from eurogas_nexus.db.models import TraderMandateRecord
    from eurogas_nexus.db.session import get_session_factory
    from eurogas_nexus.domain.risk.limits import (
        Mandate,
        MandateLeg,
        gas_year_end,
        mandate_usage,
    )

    start, end = horizon(today)
    with get_session_factory()() as session:
        records = session.query(TraderMandateRecord).order_by(TraderMandateRecord.trader).all()
        session.expunge_all()
    inputs = ladder_inputs(caller, today, start, end)
    accounts = {
        order.order_observation_id: order.account_label
        for order in inputs.orders
        if str(order.provider_id).upper() != "ETRM"
    }
    instruments = {order.order_observation_id: instrument_of(order) for order in inputs.orders}
    legs = [
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
            instrument="physical"
            if leg.kind == "physical"
            else instruments.get(leg.reference, "future"),
        )
        for leg in inputs.legs
    ]
    result = LimitRows(warnings=list(inputs.warnings))
    for record in records:
        mandate = Mandate(
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
        elsewhere = frozenset(
            book
            for other in records
            if other.trader == record.trader and other.mandate_id != record.mandate_id
            for book in (other.book_ids or ())
        ) - set(mandate.book_ids)
        result.rows.append(
            mandate_usage(mandate, legs, today=today, books_elsewhere=elsewhere).as_row()
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
