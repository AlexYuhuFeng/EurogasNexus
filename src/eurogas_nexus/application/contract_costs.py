"""Costs for the opportunity evaluators: the firm's contracts first, public tariffs second,
assumptions last, else missing (docs/product/CONTRACT_TYPES.md §6; thin first versions).

One read per cost kind, each answering::

    {value, unit, currency, basis, source_ref, as_of, input_class, note}

``basis`` is ``contract_sunk`` (capacity the firm holds: its charge is paid whatever flows, so
the cost of using it is nil), ``contracted`` / ``contracted+public`` (TAR-2: capacity the firm
has booked, at its contracted cost, with any part no booking covers at the public tariff;
``breakdown`` then lists the layers and the sources in precedence order),
``contract_variable`` (a price or charge the firm's contract states per unit),
``public_tariff`` (the published register), ``assumption`` (the approved assumption set) or
``missing`` (with the reason in ``note``). ``value`` is per MWh in ``currency`` (a supply
price is in the contract's own unit). Nothing is estimated: a cost the
sources do not hold is missing.

Names agreed with the opportunity worker: :func:`transport_leg_cost`, :func:`regas_cost`,
:func:`storage_cost`, :func:`supply_price`.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from typing import Any


@dataclass(frozen=True)
class CostAnswer:
    value: float | None
    unit: str | None
    currency: str | None
    basis: str
    source_ref: str | None
    as_of: str | None
    input_class: str
    note: str | None = None
    breakdown: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        out = asdict(self)
        if out["breakdown"] is None:
            out.pop("breakdown")
        return out


def _missing(note: str) -> dict[str, Any]:
    return CostAnswer(None, None, None, "missing", None, None, "missing", note).as_dict()


def _active_contracts(session):
    from eurogas_nexus.db.models import UpstreamResourceContractRecord
    from eurogas_nexus.security.portfolio_scope import restrict

    return (
        restrict(
            session.query(UpstreamResourceContractRecord), UpstreamResourceContractRecord, session
        )
        .filter(UpstreamResourceContractRecord.retired_at_utc.is_(None))
        .all()
    )


def _assumption(session, day: date, keys: tuple[str, ...]):
    from eurogas_nexus.db.repositories.commercial_assumptions import resolve_assumption_version

    resolved = resolve_assumption_version(session, day=day)
    if resolved is None:
        return None, None, "no approved assumption set"
    version_id, version = resolved
    values = [version.value(key) for key in keys]
    if any(value is None for value in values):
        return None, None, f"the approved set does not hold {', '.join(keys)}"
    return version_id, values, None


def transport_leg_cost(
    session, caller, *, from_point: str, to_point: str, gas_day: date
) -> dict[str, Any]:
    """The cost per MWh of moving gas ``from_point`` -> ``to_point`` on ``gas_day``.

    Capacity the firm holds on the leg (a contract delivering at ``from_point`` with exit
    capacity and ``to_point`` among its allowed exits) is sunk; else the published tariffs
    along the cheapest proven route (firm yearly capacity at full load); else missing (the
    assumption set holds no transport tariff).
    """

    from eurogas_nexus.application.identity_resolution import load_resolver
    from eurogas_nexus.application.route_tariff_cost import load_tariff_rows, route_cost
    from eurogas_nexus.domain.market.fx_forward import Delivery

    resolver = load_resolver(session)
    from_hub = resolver.hub(from_point).hub or from_point.upper()
    to_hub = resolver.hub(to_point).hub or to_point.upper()
    for record in _active_contracts(session):
        exits = {str(point).upper() for point in record.allowed_exit_points or []}
        delivers = resolver.hub(record.delivery_point_name).hub or record.delivery_point_name
        if (
            record.owned_exit_capacity_mwh_per_day
            and str(delivers).upper() == from_hub.upper()
            and (to_hub.upper() in exits or to_point.upper() in exits)
        ):
            currency = record.contract_price_currency or "GBP"
            return CostAnswer(
                0.0,
                f"{currency}/MWh",
                currency,
                "contract_sunk",
                f"upstream_resource_contract:{record.contract_id}",
                record.updated_at_utc.date().isoformat() if record.updated_at_utc else None,
                "contract",
                f"capacity held under {record.contract_name}: its charge is paid whatever flows",
            ).as_dict()
    from eurogas_nexus.application.capacity_costs import load_leg_bookings
    from eurogas_nexus.application.source_precedence import configured_orders

    delivery = Delivery(gas_day, gas_day, "day_ahead", gas_day.isoformat())
    # TAR-2: capacity the firm has booked on a leg prices first, at its contracted cost.
    route = route_cost(from_hub, to_hub, delivery, load_tariff_rows(),
                       bookings=load_leg_bookings(session), orders=configured_orders(session))
    if route.complete and route.total is not None:
        tariffs = [leg.as_dict().get("tariff_id") for leg in route.legs]
        booked = [leg for leg in route.legs if leg.cost_basis != "public"]
        basis = "public_tariff"
        if booked:
            basis = (
                "contracted"
                if all(leg.cost_basis == "contracted" for leg in route.legs)
                else "contracted+public"
            )
        return CostAnswer(
            round(route.total, 6),
            f"{route.currency}/MWh",
            route.currency,
            basis,
            ", ".join(str(item) for item in tariffs if item) or "tso_tariffs",
            gas_day.isoformat(),
            route.input_class,
            f"firm yearly capacity at full load via {' → '.join(route.hubs) or from_hub}"
            + ("; booked capacity at its contracted cost first" if booked else ""),
            breakdown={
                "legs": [
                    {"point_key": leg.point_key, "direction": leg.direction,
                     **(leg.breakdown or {"cost_basis": leg.cost_basis})}
                    for leg in route.legs
                ]
            }
            if booked
            else None,
        ).as_dict()
    reason = "; ".join(route.issues) or ", ".join(route.missing_legs()) or "no proven route"
    return _missing(f"no held capacity and no complete published tariff ({reason})")


def regas_cost(session, caller, *, terminal: str, month: str, cargo_mwh: float) -> dict[str, Any]:
    """The regas cost per MWh of one cargo of ``cargo_mwh`` at ``terminal`` in ``month``.

    The firm's own terminal terms (entered from its contracts) first, then the reviewed or
    candidate published tariff (a candidate is indicative); else missing.
    """

    from eurogas_nexus.application.lng_terminal_tariff_register import price_terminal

    if cargo_mwh <= 0:
        return _missing("a cargo size is needed to state a regas cost per MWh")
    slot = _held_slot_cost(session, terminal, month=month, cargo_mwh=cargo_mwh)
    if slot is not None:
        return slot
    charge = price_terminal(session, terminal, arrival_month=month, cargo_mwh=cargo_mwh)
    if charge.charge is None:
        return _missing(charge.reason or f"no terms or tariff held for {terminal}")
    basis = "contract_variable" if charge.basis == "firm_terms" else "public_tariff"
    return CostAnswer(
        round(charge.charge / cargo_mwh, 6),
        f"{charge.currency}/MWh",
        charge.currency,
        basis,
        ", ".join(charge.tariff_ids) or f"lng_terminal_terms:{terminal}",
        f"{month}-01",
        "indicative"
        if charge.indicative
        else ("contract" if basis.startswith("contract") else "published"),
        "; ".join(charge.excludes) or None,
    ).as_dict()


def _held_slot_cost(session, terminal: str, *, month: str, cargo_mwh: float):
    """TAR-2: a slot the firm holds at ``terminal`` in ``month`` prices first, at its
    contracted cost (``None`` when none is held)."""

    import calendar

    from eurogas_nexus.application.capacity_costs import bookings_as_of, terminal_cost

    first = date(int(month[:4]), int(month[5:7]), 1)
    end = first.replace(day=calendar.monthrange(first.year, first.month)[1])
    held = [
        record
        for record in bookings_as_of(session, kinds=("lng_slot",), facility_id=terminal)
        if record.first_gas_day <= end and record.last_gas_day >= first
    ]
    if not held:
        return None
    arrival = max(first, min(record.first_gas_day for record in held))
    cost = terminal_cost(session, terminal, arrival=arrival, cargo_mwh=cargo_mwh)
    if cost["total_cost"] is None or not cost["currency"]:
        return _missing("; ".join(cost["issues"]) or f"the slot held at {terminal} has no "
                        "contracted cost recorded")
    contracted = cost["covered"]["public"] <= 1e-9
    return CostAnswer(
        round(cost["total_cost"] / cargo_mwh, 6),
        f"{cost['currency']}/MWh",
        cost["currency"],
        "contracted" if contracted else "contracted+public",
        ", ".join(item["reference"] for item in cost["layers"]),
        arrival.isoformat(),
        "contract" if contracted else "published",
        "slot held at its contracted cost",
        breakdown=cost,
    ).as_dict()


def storage_cost(session, caller, *, facility: str, period: str) -> dict[str, Any]:
    """The cost per MWh of cycling gas through ``facility`` over ``period`` (``YYYY-MM``).

    Storage contracts are not a typed kind yet and no public storage tariff is held, so this
    reads the approved assumption set (capacity, injection and withdrawal fees); else missing.
    """

    day = date(int(period[:4]), int(period[5:7]), 1)
    version_id, values, reason = _assumption(
        session, day, ("storage.capacity_fee", "storage.injection_fee", "storage.withdrawal_fee")
    )
    if values is None:
        return _missing(f"no storage contract or tariff for {facility}; {reason}")
    currency = values[0].currency or "EUR"
    total = float(sum(value.value for value in values))
    return CostAnswer(
        round(total, 6),
        f"{currency}/MWh",
        currency,
        "assumption",
        f"{version_id}: storage fees",
        datetime.now(UTC).date().isoformat(),
        "assumption",
        f"assumed fees for {facility}: capacity + injection + withdrawal",
    ).as_dict()


def supply_price(session, caller, *, contract_id: str, period: str) -> dict[str, Any]:
    """The price of a supply contract for a delivery month, from its own formula."""

    from eurogas_nexus.application.contract_pricing import contract_price

    record = next(
        (item for item in _active_contracts(session) if item.contract_id == contract_id), None
    )
    if record is None:
        return _missing(f"contract {contract_id} is not active in the caller's books")
    priced = contract_price(session, caller, record, period)
    result = priced.get("result")
    if not result:
        return _missing(priced.get("note") or "the contract's price terms are not recorded")
    if result["value"] is None:
        return _missing("; ".join(result["missing"]) or "an index is not held")
    sources = [item["source_ref"] for item in result["inputs"]]
    return CostAnswer(
        result["value"],
        result["unit"],
        result["currency"],
        "contract_variable",
        "; ".join([f"upstream_resource_contract:{contract_id}", *sources]),
        max((item["as_of"] or "" for item in result["inputs"]), default=None) or None,
        result["input_class"],
        result["words"],
    ).as_dict()
