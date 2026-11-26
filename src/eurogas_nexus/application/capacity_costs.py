"""Capacity costs with contracted before public (TAR-2, ADR Decision 38).

Loads the firm's bookings (``capacity_bookings``, imported through ``etrm.capacity_bookings.v1``)
as held at an instant and prices a requirement through the precedence split
(``domain/tariffs/precedence.py``, built on the source-precedence resolver):

* :func:`pipeline_cost`: entry or exit capacity at a point: the booked part at its contracted
  cost, the rest at the public tariff for the product it would be bought as (``DAILY``: the
  day-ahead auction's reserve price; ``WITHIN_DAY``; ``ANNUAL``...), plus any premium stated,
  each gas day from its own tariff year's version (FINAL where held as of the instant, else
  INDICATIVE), else not held;
* :func:`terminal_cost`: one cargo's slot at an LNG terminal: a slot the firm holds (booked at
  auction or in an allocation) at its contracted cost, the firm's own terminal terms next,
  then the terminal's public first-come-first-served rate, else not held;
* :func:`load_leg_bookings`: the bookings route pricing (``route_tariff_cost.price_leg``)
  splits its legs with.

Every figure states its layer, booking or tariff version, status, tariff year, publication
and record times. Reads only: nothing is booked, nominated or released.

TAR-2：按已签约容量优先、公开费率其次计价（管道入口/出口、LNG 槽位），逐层列出版本与状态。
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from eurogas_nexus.domain.tariffs import precedence

#: A capacity unit's quantity per gas day in MWh/d.
_TO_MWH_PER_DAY = {"MWh/d": 1.0, "kWh/h": 0.024, "kWh/d": 0.001, "MWh": 1.0}

CAPACITY_CONTEXT = "capacity_cost"
TERMINAL_CONTEXT = "lng_slot"


def _aware(moment: datetime | None) -> datetime | None:
    if moment is None:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return _aware(value).isoformat()
    return value.isoformat() if isinstance(value, date) else str(value)


def bookings_as_of(
    session,
    *,
    as_of: datetime | None = None,
    kinds: Iterable[str] | None = None,
    facility_id: str | None = None,
    book_ids: Iterable[str] | None = None,
    scoped: bool = True,
) -> list[Any]:
    """The bookings the firm held at ``as_of`` (now when ``None``): recorded by then and not
    released by then. ``scoped`` limits them to the books the caller may see (a firm-level
    booking, with no book, only where firm-level figures may be shown)."""

    from sqlalchemy import or_

    from eurogas_nexus.db.models import CapacityBookingRecord as B

    moment = _aware(as_of) or datetime.now(UTC)
    query = session.query(B).filter(B.recorded_at_utc <= moment).filter(
        or_(B.released_at_utc.is_(None), B.released_at_utc > moment)
    )
    if kinds is not None:
        query = query.filter(B.kind.in_(sorted(set(kinds))))
    if facility_id:
        query = query.filter(B.facility_id == facility_id)
    if book_ids is not None:
        wanted = sorted(set(book_ids))
        query = query.filter(or_(B.book_id.is_(None), B.book_id.in_(wanted)))
    if scoped:
        from eurogas_nexus.security.portfolio_scope import firm_level_visible, visible_book_ids

        allowed = visible_book_ids(session)
        if allowed is not None:
            clause = B.book_id.in_(sorted(allowed))
            if firm_level_visible():
                clause = or_(clause, B.book_id.is_(None))
            query = query.filter(clause)
    return query.order_by(B.first_gas_day, B.booking_id).all()


def held_from_record(record: Any, *, load_factor: float = 1.0) -> precedence.Held:
    """A booking as the split holds it: quantity per gas day in MWh/d (or slots), contracted
    cost per MWh/d of capacity a gas day (or per slot); ``None`` when no price is recorded or
    its unit is not understood."""

    from eurogas_nexus.domain.route_cost.tariff_units import per_mwh

    slots = record.quantity_unit == "slot"
    quantity = float(record.quantity) * (1.0 if slots else _TO_MWH_PER_DAY.get(
        record.quantity_unit, 1.0
    ))
    unit_cost = None
    currency = record.currency
    price_text = ""
    if record.price is not None and record.price_unit:
        price_text = f"{record.price:g} {record.price_unit}"
        if slots:
            unit_cost = float(record.price)
        else:
            read = per_mwh(
                float(record.price),
                record.price_unit,
                on=record.first_gas_day,
                load_factor=load_factor,
                anniversary=record.first_gas_day,
                currency=record.currency,
            )
            if read is not None:
                unit_cost, currency = read.value * load_factor, read.currency
    return precedence.Held(
        booking_id=record.booking_id,
        first=record.first_gas_day,
        last=record.last_gas_day,
        quantity=quantity,
        unit_cost=unit_cost,
        currency=currency,
        basis=precedence.POOL if slots else precedence.PER_DAY,
        acquired_via=record.acquired_via,
        price_text=price_text,
        source=f"capacity_bookings ({record.source_system})",
    )


def booking_row(record: Any) -> dict[str, Any]:
    """One booking for ``GET /api/capacity/bookings``."""

    return {
        "booking_id": record.booking_id,
        "source_system": record.source_system,
        "external_id": record.external_id,
        "book_id": record.book_id,
        "kind": record.kind,
        "facility_kind": record.facility_kind,
        "facility_id": record.facility_id,
        "facility_name": record.facility_name,
        "operator": record.operator,
        "direction": record.direction,
        "product": record.product,
        "firmness": record.firmness,
        "acquired_via": record.acquired_via,
        "first_gas_day": record.first_gas_day.isoformat(),
        "last_gas_day": record.last_gas_day.isoformat(),
        "quantity": record.quantity,
        "quantity_unit": record.quantity_unit,
        "quantity_basis": record.quantity_basis,
        "price": record.price,
        "price_unit": record.price_unit,
        "currency": record.currency,
        "price_recorded": record.price is not None,
        "counterparty": record.counterparty,
        "source_reference": record.source_reference,
        "recorded_at_utc": _iso(record.recorded_at_utc),
        "updated_at_utc": _iso(record.updated_at_utc),
        "released_at_utc": _iso(record.released_at_utc),
    }


def load_leg_bookings(session, *, as_of: datetime | None = None,
                      book_ids: Iterable[str] | None = None) -> list[Any]:
    """Pipeline bookings as route legs take them (``route_tariff_cost.LegBooking``): the
    contracted cost per MWh/d of capacity a gas day (the leg applies its load factor)."""

    from eurogas_nexus.application.route_tariff_cost import LegBooking

    return [
        LegBooking(
            point_key=record.facility_id,
            direction=str(record.direction or record.kind).upper(),
            operator=record.operator,
            held=held_from_record(record),
        )
        for record in bookings_as_of(
            session, as_of=as_of, kinds=("entry", "exit"), book_ids=book_ids
        )
    ]


# --------------------------------------------------------------------------- pipeline


def pipeline_cost(
    session,
    *,
    point_key: str,
    direction: str,
    first: date,
    last: date,
    mwh_per_day: float,
    product: str = "DAILY",
    firmness: str = "FIRM",
    operator: str | None = None,
    premium: float = 0.0,
    as_of: datetime | None = None,
    book_ids: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Capacity of ``mwh_per_day`` at a point from ``first`` to ``last``: the firm's bookings
    first, the rest at ``product``'s public tariff (with ``premium`` per MWh/d a day where an
    auction cleared above the reserve price), each gas day from its tariff year's version
    held at ``as_of``."""

    from eurogas_nexus.application.route_tariff_cost import _LegSpec, _price_public_leg
    from eurogas_nexus.application.source_precedence import configured_orders
    from eurogas_nexus.application.tariff_book import tariff_versions_as_rows

    moment = _aware(as_of) or datetime.now(UTC)
    rows = tariff_versions_as_rows(session, product=product, firmness=firmness, as_of=moment)
    held = [
        held_from_record(record)
        for record in bookings_as_of(
            session, as_of=moment, kinds=("entry", "exit"), facility_id=point_key,
            book_ids=book_ids,
        )
        if str(record.direction or record.kind).upper() == direction.upper()
        and record.firmness == firmness.upper()
    ]
    # Without an operator, the leg matches any TSO publishing at the point and direction.
    tsos = sorted(
        {
            str(row.get("tso") or "")
            for row in rows
            if row.get("point_id") == point_key
            and str(row.get("direction") or "").upper() == direction.upper()
        }
        - {""}
    )
    spec = _LegSpec(point_key, point_key, operator or "/".join(tsos), direction.upper(), "point")
    how = precedence.HOW_BOUGHT.get(product.upper(), product)
    cache: dict[date, Any] = {}

    def rate(day: date) -> precedence.PublicRate | None:
        leg = cache.get(day)
        if leg is None:
            leg = cache[day] = _price_public_leg(
                spec, rows, day, product=product, firmness=firmness, load_factor=1.0
            )
        if leg.value is None or leg.currency is None:
            return None
        return precedence.PublicRate(
            unit_cost=leg.value,
            currency=leg.currency,
            status=leg.status or "INDICATIVE",
            tariff_year=leg.tariff_year or leg.gas_year,
            version_id=leg.version_id,
            published_at=leg.published_at,
            recorded_at=leg.recorded_at,
            status_basis=leg.status_basis,
            how_bought=how,
            premium=premium,
            price_text=leg.published or "",
            source=leg.source or "",
            reference=leg.tariff_id or "",
        )

    breakdown = precedence.split(
        precedence.Requirement(first, last, float(mwh_per_day)),
        held,
        rate,
        not_held_reason=f"no booking covers it and no {how} is held",
        configured=configured_orders(session),
        context=CAPACITY_CONTEXT,
    )
    return {
        "point_key": point_key,
        "direction": direction.upper(),
        "operator": operator,
        "product": product.upper(),
        "firmness": firmness.upper(),
        "how_bought": how,
        "premium": premium,
        "as_of": moment.isoformat(),
        **breakdown.as_dict(),
    }


# --------------------------------------------------------------------------- terminals


@dataclass(frozen=True)
class _TerminalPublic:
    rate: precedence.PublicRate | None
    reason: str | None
    excludes: tuple[str, ...]


def _terminal_public(session, terminal_id: str, *, arrival: date, cargo_mwh: float,
                     product: str, as_of: datetime | None) -> _TerminalPublic:
    """The terminal's public rate for one cargo: the register now, or the tariff book's
    versions held at ``as_of``."""

    from eurogas_nexus.application.lng_terminal_tariff_register import (
        operator_for_terminal,
        operator_permitted,
        public_tariffs,
    )
    from eurogas_nexus.domain.route_cost.terminal_tariff_register import (
        CANDIDATE,
        REVIEWED,
        PublicTariff,
        resolve_terminal_charge,
    )

    versions: dict[str, Any] = {}
    if as_of is None:
        public = public_tariffs(session)
    else:
        from sqlalchemy import or_

        from eurogas_nexus.application.tariff_book import ChangeKind, effective_status
        from eurogas_nexus.db.models import TariffVersionRecord as V

        public = []
        query = (
            session.query(V)
            .filter(V.facility_kind == "terminal")
            .filter(V.facility_id == terminal_id)
            .filter(V.recorded_at_utc <= as_of)
            .filter(or_(V.superseded_at_utc.is_(None), V.superseded_at_utc > as_of))
            .filter(V.change_kind != ChangeKind.WITHDRAWN.value)
        )
        for record in query.all():
            parts = record.tariff_key.split(":")
            status, _basis = effective_status(record, as_of)
            public.append(
                PublicTariff(
                    tariff_id=record.version_id,
                    terminal_id=record.facility_id,
                    product=record.product.split("/", 1)[-1],
                    charge_basis=parts[-2] if len(parts) > 4 else "per_cargo",
                    amount=record.value,
                    currency=record.currency,
                    review_status=REVIEWED if status == "FINAL" else CANDIDATE,
                    valid_from=record.period_from,
                    valid_to=record.period_to,
                    by_cargo_class=record.by_class,
                    source_url=record.source_url,
                )
            )
            versions[record.version_id] = record
    operator = operator_for_terminal(terminal_id)
    charge = resolve_terminal_charge(
        terminal_id,
        arrival_month=arrival.strftime("%Y-%m"),
        cargo_mwh=cargo_mwh,
        firm_terms=None,
        public=public,
        product=product,
        operator_needs_terms=bool(operator) and not operator_permitted(session, operator),
    )
    if charge.charge is None or charge.currency is None:
        return _TerminalPublic(None, charge.reason, charge.excludes)
    record = next((versions[i] for i in charge.tariff_ids if i in versions), None)
    if record is None and charge.tariff_ids:
        record = _current_terminal_version(session, charge.tariff_ids)
    year = published = recorded = basis = version_id = None
    if record is not None:
        from eurogas_nexus.application.tariff_book import effective_status, year_of_record

        year = year_of_record(record).label
        published, recorded = _iso(record.published_at_utc), _iso(record.recorded_at_utc)
        basis = effective_status(record, as_of)[1]
        version_id = record.version_id
    return _TerminalPublic(
        precedence.PublicRate(
            unit_cost=float(charge.charge),
            currency=charge.currency,
            status="INDICATIVE" if charge.indicative else "FINAL",
            tariff_year=year,
            version_id=version_id,
            published_at=published,
            recorded_at=recorded,
            status_basis=basis or charge.basis,
            how_bought=precedence.HOW_BOUGHT.get(product, product),
            price_text=f"{charge.charge:,.0f} {charge.currency} a cargo",
            source=f"terminal tariff ({charge.basis})",
            reference=",".join(charge.tariff_ids),
        ),
        None,
        charge.excludes,
    )


def _current_terminal_version(session, tariff_ids: Iterable[str]):
    """The current tariff-book version of a register figure (matched by its source row)."""

    from eurogas_nexus.application.tariff_book import lng_identity
    from eurogas_nexus.db.models import LngTerminalTariffRecord, TariffVersionRecord
    from eurogas_nexus.domain.tariffs.publishers import lng_publisher_for

    for tariff_id in tariff_ids:
        row = session.get(LngTerminalTariffRecord, tariff_id)
        if row is None:
            continue
        publisher_id = lng_publisher_for(str(row.terminal_id))
        if publisher_id is None:
            continue
        found = (
            session.query(TariffVersionRecord)
            .filter(TariffVersionRecord.tariff_key == lng_identity(row, publisher_id))
            .filter(TariffVersionRecord.superseded_at_utc.is_(None))
            .first()
        )
        if found is not None:
            return found
    return None


def _firm_terms_held(session, terminal_id: str, *, arrival: date, cargo_mwh: float):
    """The firm's own terminal terms (entered from its contracts) as a contracted slot."""

    from eurogas_nexus.db.models import LngTerminalTermsRecord
    from eurogas_nexus.domain.portfolio.lng_bid import TerminalTerms
    from eurogas_nexus.domain.route_cost.terminal_tariff_register import resolve_terminal_charge

    firm = session.get(LngTerminalTermsRecord, terminal_id)
    if firm is None or firm.source_url is not None:
        return None
    terms = TerminalTerms(
        terminal_id=firm.terminal_id,
        name=firm.name,
        country=firm.country,
        hub=firm.hub,
        currency="EUR" if firm.hub != "NBP" else "GBP",
        regas_tariff_per_mwh=firm.regas_tariff_per_mwh,
        fixed_per_cargo=firm.fixed_per_cargo,
        by_cargo_class=firm.by_cargo_class,
        capacity_basis=firm.capacity_basis,
        variable_regas_per_mwh=firm.variable_regas_per_mwh,
    )
    charge = resolve_terminal_charge(
        terminal_id, arrival_month=arrival.strftime("%Y-%m"), cargo_mwh=cargo_mwh,
        firm_terms=terms, public=[],
    )
    return precedence.Held(
        booking_id=f"terms:{terminal_id}",
        first=arrival,
        last=arrival,
        quantity=1.0,
        unit_cost=charge.charge,
        currency=charge.currency,
        basis=precedence.POOL,
        acquired_via="long_term",
        price_text="" if charge.charge is None else f"{charge.charge:,.0f} {charge.currency}",
        source="lng_terminal_terms (the firm's own terms)",
    )


def terminal_cost(
    session,
    terminal_id: str,
    *,
    arrival: date,
    cargo_mwh: float,
    product: str = "spot",
    as_of: datetime | None = None,
    book_ids: Iterable[str] | None = None,
) -> dict[str, Any]:
    """One cargo's slot at ``terminal_id`` arriving on ``arrival``: a slot the firm holds
    then (its contracted cost per slot), its own terminal terms, the public rate (``spot``:
    first-come-first-served) held at ``as_of``, else not held."""

    moment = _aware(as_of)
    held = [
        held_from_record(record)
        for record in bookings_as_of(
            session, as_of=moment, kinds=("lng_slot",), facility_id=terminal_id,
            book_ids=book_ids,
        )
    ]
    terms = _firm_terms_held(session, terminal_id, arrival=arrival, cargo_mwh=cargo_mwh)
    if terms is not None:
        held.append(terms)
    public = _terminal_public(session, terminal_id, arrival=arrival, cargo_mwh=cargo_mwh,
                              product=product, as_of=moment)
    from eurogas_nexus.application.source_precedence import configured_orders

    breakdown = precedence.split(
        precedence.Requirement(arrival, arrival, 1.0, unit="slot"),
        held,
        public.rate,
        not_held_reason=public.reason or "no slot held and no public rate held",
        configured=configured_orders(session),
        context=TERMINAL_CONTEXT,
    )
    out = breakdown.as_dict()
    return {
        "terminal_id": terminal_id,
        "arrival": arrival.isoformat(),
        "cargo_mwh": cargo_mwh,
        "product": product,
        "as_of": _iso(moment),
        "excludes": list(public.excludes),
        **out,
    }


def summary(breakdown: Mapping[str, Any]) -> str:
    """One line for a desk: the parts and the total, or what is not priced."""

    parts = []
    for item in breakdown.get("layers", ()):
        label = item["layer"]
        if item["layer"] == precedence.PUBLIC:
            label = f"public {item.get('status', '').lower()} {item.get('tariff_year') or ''}"
        parts.append(f"{item['quantity']:,.1f} {item['unit']} {label.strip()}")
    total = breakdown.get("total_cost")
    tail = "not priced" if total is None else f"{total:,.2f} {breakdown.get('currency')}"
    return "; ".join(parts) + f" = {tail}"


__all__ = [
    "CAPACITY_CONTEXT",
    "TERMINAL_CONTEXT",
    "booking_row",
    "bookings_as_of",
    "held_from_record",
    "load_leg_bookings",
    "pipeline_cost",
    "summary",
    "terminal_cost",
]
