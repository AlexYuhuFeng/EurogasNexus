"""A disrupted cargo or pipeline supply re-optimised across the book (LNG-3).

Builds the book's portfolio from what the firm holds (``domain/lng/disruption.py`` does the
optimising):

* cargoes of the book still at sea or discharging (``lng_cargoes``), each at the slot it holds
  (``regas_slots``) with the energy LNG-1's plan delivers at its ETA (boil-off and gas in kind
  taken off), its ETA confidence, and its voyage terms (``lng_voyage_terms``, else the cargo
  contract's master agreement for laytime and the firm's boil-off assumption);
* the book's slots, held or spare, with their product terms (``lng_slot_terms``, else the
  slot's window and send-out with a declining storage right equal to its energy, named so);
* pipeline supplies of the book and their curtailed days (``pipeline_supplies``);
* firm and soft delivery obligations (``lng_delivery_obligations``);
* capacity the desk could borrow or buy (``lng_capacity_offers``: quoted or indicative);
* month prices from the price book, the sailing difference between terminals
  (``lng_terminal_terms.extra_sailing_days``) and the costs and preference weights from the
  firm's approved assumptions (``lng.disruption.*``; desk standards otherwise, named so).

Reads (``GET /api/lng/cargoes/{id}/disruption-options``, ``.../{option_id}`` and
``GET /api/lng/disruption/frontier``) value the book now and record nothing. The outbox
consumer ``lng_disruption`` re-runs a book when one of its inputs changes, keeps a run row
when the recommendation, the frontier or the recommended P&L moved (the timeline), and tells
the trader, the scheduler and the desk head through the LNG-2 routes: once per content, not
again within :data:`COOLDOWN` unless the recommendation itself changed.

``choose_option`` records the option a person chose, audited. Nothing is booked, borrowed,
bought, traded or nominated (AGENTS.md rule 8).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import uuid4

from eurogas_nexus.application.lng_in_transit import CargoPlanError
from eurogas_nexus.domain.lng.disruption import (
    LNG,
    PIPELINE,
    CapacityOffer,
    DeskTerms,
    DisruptionError,
    Market,
    Obligation,
    Option,
    Portfolio,
    Result,
    SlotTerms,
    Supply,
    optimise,
    option_dict,
    result_dict,
)

CONSUMER_NAME = "lng_disruption"
#: The roles told about a new recommendation, and the alert category each is routed by.
ROLES = ("trader", "scheduler", "desk_head")
#: Not notified again within this time unless the recommended option itself changed.
COOLDOWN = timedelta(minutes=30)
#: Inputs whose change can move the options. Prices are valued at every read; a price tick
#: alone does not start a run (the opportunity consumer handles ticks).
ACCEPTED = frozenset(
    {
        "cargo.changed",
        "capacity.changed",
        "tariff.changed",
        "contract.changed",
        "assumption.changed",
        "outage.published",
    }
)
OPEN_STATUSES = ("loading", "laden", "discharging")
#: How far ahead month prices are read (the slot tails run a fortnight past a slot).
PRICE_MONTHS = 4
ADVISORY = (
    "Decision support: the options are proposed and valued; a person chooses. Nothing is "
    "booked, borrowed, bought, traded or nominated."
)

#: DeskTerms field -> (approved assumption key, desk standard).
ASSUMPTION_KEYS: dict[str, tuple[str, float]] = {
    "risk_weight": ("lng.disruption.risk_weight", 0.5),
    "disruption_eur_per_mwh": ("lng.disruption.moved_mwh_cost", 0.5),
    "disruption_eur_per_supply": ("lng.disruption.moved_supply_cost", 0.0),
    "flexibility_eur_per_mwh": ("lng.disruption.flexibility_value", 0.0),
    "trade_cost_eur_mwh": ("lng.disruption.trade_cost", 0.01),
    "short_notice_premium_eur_mwh": ("lng.disruption.short_notice_premium", 0.25),
    "cash_out_pct": ("lng.disruption.cash_out_pct", 3.0),
    "stranded_discount_eur_mwh": ("lng.disruption.stranded_discount", 3.0),
    "material_change_eur": ("lng.disruption.material_change", 50_000.0),
}
_UNITLESS = {"risk_weight", "cash_out_pct"}


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _gas_day(instant: datetime) -> date:
    from eurogas_nexus.domain.market.gas_day import gas_day_label

    return date.fromisoformat(gas_day_label(_aware(instant)))


def _month(day: date) -> str:
    return f"{day.year:04d}-{day.month:02d}"


@dataclass
class Book:
    """A book's portfolio as the optimiser reads it, and where each input came from."""

    book_id: str
    portfolio: Portfolio
    market: Market
    terms: DeskTerms
    inputs: list[dict[str, str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    cargo_rows: dict[str, Any] = field(default_factory=dict)


# ------------------------------------------------------------------------------ loading


def _terms(session, book_id: str, day: date) -> DeskTerms:
    from eurogas_nexus.db.repositories.commercial_assumptions import resolve_assumption_version

    resolved = resolve_assumption_version(session, day=day, book_id=book_id)
    values: dict[str, float] = {}
    sources: dict[str, str] = {}
    for name, (key, standard) in ASSUMPTION_KEYS.items():
        values[name] = standard
        sources[name] = f"desk standard {standard:g} (no approved {key})"
        if resolved is None:
            continue
        version_id, version = resolved
        held = version.value(key)
        if held is None or held.value is None:
            continue
        currency = getattr(held, "currency", None)
        if name not in _UNITLESS and currency not in (None, "EUR"):
            sources[name] = f"desk standard {standard:g} ({key} is held in {currency}, not EUR)"
            continue
        values[name] = float(held.value)
        sources[name] = f"approved assumption {key} ({version_id})"
    return DeskTerms(**values, sources=sources)


def _prices(session, hubs: set[str], today: date, now: datetime):
    from eurogas_nexus.application.price_resolver import open_price_book

    months = []
    first = today.replace(day=1)
    for step in range(PRICE_MONTHS):
        year = first.year + (first.month - 1 + step) // 12
        month = (first.month - 1 + step) % 12 + 1
        months.append(f"{year:04d}-{month:02d}")
    prices: dict[tuple[str, str], float] = {}
    sources: dict[tuple[str, str], str] = {}
    if not hubs:
        return prices, sources
    book = open_price_book(session, None, now=now, hubs=hubs)
    for hub in sorted(hubs):
        for month in months:
            resolved = book.month(hub, month)
            if resolved is None or "EUR" not in str(resolved.unit).upper():
                continue
            prices[(hub, month)] = float(resolved.value)
            sources[(hub, month)] = f"{resolved.kind} {resolved.source_system}" + (
                " (simulated)" if resolved.simulated else ""
            )
    return prices, sources


def _sailing(session) -> dict[str, float]:
    from eurogas_nexus.application.lng_in_transit import _normal
    from eurogas_nexus.db.models import LngTerminalTermsRecord

    out: dict[str, float] = {}
    for row in session.query(LngTerminalTermsRecord).all():
        out[_normal(row.name)] = float(row.extra_sailing_days or 0.0)
    return out


def _slot_terms(session, slot, hub: str, holder: str | None) -> tuple[SlotTerms, str]:
    from eurogas_nexus.db.models import LngSlotTermsRecord

    start = _gas_day(slot.window_start_utc)
    send_out = float(slot.send_out_gwh_d or 0.0) * 1000
    held = session.get(LngSlotTermsRecord, slot.slot_id)
    if held is not None:
        return (
            SlotTerms(
                slot.slot_id,
                slot.terminal_name,
                hub,
                start,
                int(held.slot_days),
                send_out,
                float(held.storage_mwh),
                profile=held.storage_profile,
                release_value_eur_mwh=held.release_value_eur_mwh,
                holder=holder,
                source=f"slot terms {held.source_reference}",
            ),
            f"slot terms {held.source_reference}",
        )
    energy = float(slot.energy_gwh or 0.0) * 1000
    if energy and send_out:
        days = max(1, math.ceil(energy / send_out - 1e-9))
    else:
        span = (_aware(slot.window_end_utc) - _aware(slot.window_start_utc)).total_seconds()
        days = max(1, math.ceil(span / 86400))
    storage = energy or send_out * days
    source = (
        f"slot {slot.slot_id}: {days} days from its window and send-out, storage "
        f"{storage:,.0f} MWh declining (no slot terms recorded)"
    )
    return (
        SlotTerms(
            slot.slot_id,
            slot.terminal_name,
            hub,
            start,
            days,
            send_out,
            storage,
            holder=holder,
            source=source,
        ),
        source,
    )


def _voyage(session, row, plan_inputs) -> dict[str, Any]:
    """Laytime, demurrage (EUR/day), boil-off and diversion right, and their sources."""

    from eurogas_nexus.application.lng_in_transit import _cargo_contract, _mspa_terms
    from eurogas_nexus.db.models import LngVoyageTermsRecord

    held = session.get(LngVoyageTermsRecord, row.cargo_id)
    contract = _cargo_contract(session, row.cargo_id)
    mspa = _mspa_terms(session, contract)
    out: dict[str, Any] = {"warnings": []}
    if held is not None and held.laytime_hours is not None:
        out["laytime_hours"], out["laytime_source"] = held.laytime_hours, "voyage terms"
    elif mspa and mspa.get("laytime_hours") is not None:
        out["laytime_hours"] = float(mspa["laytime_hours"])
        out["laytime_source"] = f"master agreement {mspa['master_contract_id']}"
    else:
        out["laytime_hours"], out["laytime_source"] = 36.0, "desk standard 36 h (none recorded)"
    if held is not None and held.demurrage_eur_per_day is not None:
        out["demurrage"] = float(held.demurrage_eur_per_day)
        out["demurrage_source"] = "voyage terms"
    else:
        out["demurrage"] = 0.0
        out["demurrage_source"] = "none in EUR recorded: waiting costs boil-off only"
        out["warnings"].append(
            f"{row.vessel_name}: no demurrage in EUR recorded (lng_voyage_terms); waiting is "
            "costed at boil-off only" + (" (the master agreement names one in USD)" if mspa else "")
        )
    if held is not None and held.boil_off_pct_per_day is not None:
        out["boil_off_pct"] = float(held.boil_off_pct_per_day)
    else:
        out["boil_off_pct"] = plan_inputs.boil_off_pct_per_day
    term = None
    if contract is not None and contract[1] is not None:
        term = getattr(contract[1], "delivery_term", None)
    if held is not None and held.diversion_allowed is not None:
        out["can_divert"] = bool(held.diversion_allowed)
        out["diversion_note"] = held.diversion_note or (
            "" if held.diversion_allowed else "the voyage terms allow no diversion"
        )
    elif term == "DES":
        out["can_divert"] = False
        out["diversion_note"] = "a DES cargo with no diversion right recorded"
    else:
        out["can_divert"] = True
        out["diversion_note"] = (
            "" if term else "no cargo contract held; diversion right not checked"
        )
    return out


def load_book(session, book_id: str, *, now: datetime) -> Book:
    """The book's portfolio, prices and terms at ``now``."""

    from eurogas_nexus.application.lng_in_transit import (
        _cargo_rows,
        _inputs,
        _normal,
        _state,
        _terminal,
    )
    from eurogas_nexus.db.models import (
        LngCapacityOfferRecord,
        LngCargoRecord,
        LngDeliveryObligationRecord,
        LngVoyageTermsRecord,
        PipelineSupplyRecord,
        RegasSlotRecord,
    )
    from eurogas_nexus.domain.lng.in_transit import build_plan

    moment = _aware(now) or datetime.now(UTC)
    today = moment.date()
    inputs: list[dict[str, str]] = []
    warnings: list[str] = []
    cargo_rows = {
        row.cargo_id: row
        for row in session.query(LngCargoRecord)
        .filter(LngCargoRecord.book_id == book_id, LngCargoRecord.status.in_(OPEN_STATUSES))
        .order_by(LngCargoRecord.cargo_id)
        .all()
    }
    slot_rows = (
        session.query(RegasSlotRecord)
        .filter(RegasSlotRecord.window_end_utc >= moment - timedelta(days=45))
        .order_by(RegasSlotRecord.window_start_utc, RegasSlotRecord.slot_id)
        .all()
    )
    slot_rows = [
        s
        for s in slot_rows
        if s.book_id == book_id or (s.book_id is None and s.cargo_id in cargo_rows)
    ]
    hubs: dict[str, str] = {}
    slots: list[SlotTerms] = []
    for slot in slot_rows:
        if slot.cargo_id is not None and slot.cargo_id not in cargo_rows:
            continue  # held by a cargo that is done or not this book's
        resolved = _terminal(session, slot.terminal_name)
        if resolved is None or not slot.send_out_gwh_d:
            warnings.append(f"slot {slot.slot_id}: no hub or send-out rate; left out")
            continue
        terms, source = _slot_terms(session, slot, resolved.hub, slot.cargo_id)
        if terms.start + timedelta(days=terms.days) <= today:
            continue
        hubs[slot.terminal_name] = resolved.hub
        slots.append(terms)
        inputs.append({"input": f"slot {slot.slot_id}", "source": source})

    supplies: list[Supply] = []
    for cargo_id, row in cargo_rows.items():
        mine = next((s for s in slots if s.holder == cargo_id), None)
        if mine is None or row.eta_utc is None:
            continue
        _row, slot_row, hedges = _cargo_rows(session, cargo_id)
        held = session.get(LngVoyageTermsRecord, cargo_id)
        try:
            cargo, _sources = _inputs(
                session,
                _state(row, slot_row, hedges, moment),
                now=moment,
                contract_boil_off=None if held is None else held.boil_off_pct_per_day,
            )
        except CargoPlanError as exc:
            warnings.append(f"{row.vessel_name}: {exc.message}; left out")
            continue
        plan = build_plan(cargo, now=moment)
        gik = cargo.slot.gas_in_kind_pct if cargo.slot is not None else 0.0
        energy = plan.energy_at_eta_mwh * (1 - gik / 100)
        voyage = _voyage(session, row, cargo)
        warnings.extend(voyage.pop("warnings"))
        supplies.append(
            Supply(
                cargo_id,
                row.vessel_name,
                kind=LNG,
                energy_mwh=energy,
                arrival=_gas_day(row.eta_utc),
                slot_id=mine.slot_id,
                terminal=mine.terminal,
                eta_confidence=row.eta_confidence,
                laytime_hours=voyage["laytime_hours"],
                demurrage_eur_per_day=voyage["demurrage"],
                boil_off_mwh_per_day=cargo.loaded_mwh * voyage["boil_off_pct"] / 100,
                can_divert=voyage["can_divert"],
                diversion_note=voyage["diversion_note"],
            )
        )
        inputs.append(
            {
                "input": f"cargo {cargo_id}",
                "source": f"{energy:,.0f} MWh at the ETA (LNG-1 plan); laytime "
                f"{voyage['laytime_source']}; demurrage {voyage['demurrage_source']}",
            }
        )

    for item in (
        session.query(PipelineSupplyRecord)
        .filter(PipelineSupplyRecord.book_id == book_id)
        .order_by(PipelineSupplyRecord.supply_id)
        .all()
    ):
        if item.last_gas_day < today:
            continue
        curtailed = tuple(
            (date.fromisoformat(str(day)), float(mwh)) for day, mwh in (item.curtailed or [])
        )
        supplies.append(
            Supply(
                item.supply_id,
                item.label,
                kind=PIPELINE,
                hub=item.hub.upper(),
                point=item.point,
                daily_mwh=float(item.mwh_per_day),
                start=item.first_gas_day,
                end=item.last_gas_day,
                curtailed=curtailed,
                cost_eur_mwh=float(item.cost_eur_mwh or 0.0),
            )
        )
        hubs[item.point] = item.hub.upper()
        inputs.append(
            {
                "input": f"pipeline {item.supply_id}",
                "source": f"{item.source_system} {item.source_reference}",
            }
        )

    obligations = [
        Obligation(
            o.obligation_id,
            o.counterparty,
            o.point,
            o.hub.upper(),
            o.first_gas_day,
            o.last_gas_day,
            float(o.mwh_per_day),
            firm=bool(o.firm),
            penalty_eur_mwh=float(o.penalty_eur_mwh or 0.0),
            contract_id=o.contract_id,
        )
        for o in session.query(LngDeliveryObligationRecord)
        .filter(LngDeliveryObligationRecord.book_id == book_id)
        .order_by(LngDeliveryObligationRecord.obligation_id)
        .all()
        if o.last_gas_day >= today
    ]
    offers = []
    for o in session.query(LngCapacityOfferRecord).order_by(LngCapacityOfferRecord.offer_id).all():
        if o.book_id not in (None, book_id) or o.last_gas_day < today:
            continue
        if o.valid_until_utc is not None and _aware(o.valid_until_utc) < moment:
            continue
        offers.append(
            CapacityOffer(
                o.offer_id,
                o.terminal_name,
                o.kind,
                o.first_gas_day,
                o.last_gas_day,
                float(o.price_eur_mwh),
                max_mwh_per_day=float(o.max_mwh_per_day or 0.0),
                max_mwh=float(o.max_mwh or 0.0),
                storage_price_eur_mwh_day=float(o.storage_price_eur_mwh_day or 0.0),
                basis=o.basis,
                source=o.source_reference,
            )
        )
        inputs.append({"input": f"offer {o.offer_id}", "source": f"{o.basis} {o.source_reference}"})
    offers.extend(_contracted_offers(session, book_id, today, moment, inputs, warnings))

    known = _sailing(session)
    sailing = {}
    for terminal in sorted({s.terminal for s in slots}):
        value = known.get(_normal(terminal))
        sailing[terminal] = 0.0 if value is None else value
    missing = sorted(t for t in sailing if _normal(t) not in known)
    if missing:
        inputs.append(
            {
                "input": "sailing difference",
                "source": "terminal terms; none held for "
                + ", ".join(missing)
                + " (taken as the same voyage)",
            }
        )
    prices, price_sources = _prices(session, set(hubs.values()), today, moment)
    for (hub, month), source in sorted(price_sources.items()):
        inputs.append({"input": f"price {hub} {month}", "source": source})
    terms = _terms(session, book_id, today)
    for name, source in terms.sources.items():
        inputs.append({"input": name, "source": source})
    try:
        portfolio = Portfolio(
            tuple(supplies), tuple(slots), tuple(obligations), tuple(offers), sailing
        )
    except DisruptionError as exc:
        raise CargoPlanError("portfolio_invalid", str(exc)) from exc
    return Book(
        book_id=book_id,
        portfolio=portfolio,
        market=Market(prices, moment, sources=price_sources),
        terms=terms,
        inputs=inputs,
        warnings=warnings,
        cargo_rows=cargo_rows,
    )


#: The contracted price units a booking's send-out or storage cost is read in (EUR only).
_CONTRACTED_UNITS = {"send_out": ("EUR/MWh",), "storage": ("EUR/MWh/d", "EUR/MWh/day")}


def _contracted_offers(session, book_id: str, today: date, moment: datetime,
                       inputs: list, warnings: list) -> list[CapacityOffer]:
    """TAR-2: send-out and storage the firm has booked at a terminal, as offers ranked before
    any public or quoted one, at their contracted cost. A booking without a contracted price
    in a unit read here is named and not used (never priced at zero)."""

    from eurogas_nexus.application.capacity_costs import bookings_as_of

    try:
        records = bookings_as_of(session, as_of=moment, kinds=("send_out", "storage"),
                                 book_ids=[book_id])
    except Exception:  # noqa: BLE001 - a store without the bookings table
        return []
    out = []
    for record in records:
        if record.last_gas_day < today:
            continue
        unit = (record.price_unit or "").replace(" ", "")
        if record.price is None or unit not in _CONTRACTED_UNITS[record.kind]:
            warnings.append(
                f"booking {record.booking_id}: contracted {record.kind.replace('_', '-')} cost "
                "not recorded in EUR/MWh (send-out) or EUR/MWh/d (storage); not used"
            )
            continue
        per_day = record.quantity * (24 / 1000 if record.quantity_unit == "kWh/h" else (
            1 / 1000 if record.quantity_unit == "kWh/d" else 1.0))
        out.append(
            CapacityOffer(
                f"booking:{record.booking_id}",
                record.facility_name or record.facility_id,
                record.kind,
                max(record.first_gas_day, today),
                record.last_gas_day,
                float(record.price),
                max_mwh_per_day=per_day if record.kind == "send_out" else 0.0,
                max_mwh=per_day if record.kind == "storage" else 0.0,
                basis="contracted",
                source=record.source_reference,
            )
        )
        inputs.append({"input": f"booking {record.booking_id}",
                       "source": f"contracted {record.source_reference}"})
    return out


def _with_curtailment(book: Book, curtail: dict[str, Any] | None) -> Book:
    """A what-if: a pipeline supply curtailed by ``mwh_per_day`` on ``[first, last]``."""

    if not curtail:
        return book
    supplies = []
    found = False
    for supply in book.portfolio.supplies:
        if supply.kind == PIPELINE and supply.supply_id == curtail["supply_id"]:
            found = True
            day, extra = curtail["first"], []
            while day <= curtail["last"]:
                extra.append((day, min(float(curtail["mwh_per_day"]), supply.daily_mwh)))
                day += timedelta(days=1)
            held = {d: m for d, m in supply.curtailed}
            held.update(dict(extra))
            supply = replace(supply, curtailed=tuple(sorted(held.items())))
        supplies.append(supply)
    if not found:
        raise CargoPlanError("supply_not_found", "No pipeline supply of the book has this id.", 404)
    book.portfolio = replace(book.portfolio, supplies=tuple(supplies))
    book.inputs.append(
        {
            "input": "what-if curtailment",
            "source": f"{curtail['supply_id']} short {float(curtail['mwh_per_day']):,.0f} MWh/d "
            f"{curtail['first']:%d %b}-{curtail['last']:%d %b} (asked for in this read)",
        }
    )
    return book


# -------------------------------------------------------------------------------- reads


def _cargo(session, cargo_id: str):
    from eurogas_nexus.application.lng_in_transit import _cargo_rows, _check_book

    row, slot, _hedges = _cargo_rows(session, cargo_id)
    _check_book(session, row.book_id)
    return row, slot


def _involves(option: Option, cargo_id: str) -> bool:
    return cargo_id in option.placements or any(cargo_id in pair for pair in option.swaps)


def _runs(session, book_id: str, limit: int = 12) -> list[dict[str, Any]]:
    from eurogas_nexus.db.models import LngDisruptionRunRecord

    rows = (
        session.query(LngDisruptionRunRecord)
        .filter(LngDisruptionRunRecord.book_id == book_id)
        .order_by(LngDisruptionRunRecord.computed_at_utc.desc(), LngDisruptionRunRecord.run_id)
        .limit(limit)
        .all()
    )
    return [
        {
            "run_id": r.run_id,
            "computed_at_utc": _aware(r.computed_at_utc).isoformat(),
            "trigger": r.trigger,
            "change": r.change,
            "notified": r.notified,
            "recommended_option_id": r.recommended_option_id,
            "recommended_title": r.recommended_title,
            "recommended_pnl_eur": r.recommended_pnl_eur,
            "frontier": list(r.frontier or []),
            "disrupted": list(r.disrupted or []),
        }
        for r in rows
    ]


def _decision(session, cargo_id: str) -> dict[str, Any] | None:
    from eurogas_nexus.db.models import LngDisruptionDecisionRecord

    row = (
        session.query(LngDisruptionDecisionRecord)
        .filter(LngDisruptionDecisionRecord.cargo_id == cargo_id)
        .order_by(LngDisruptionDecisionRecord.decided_at_utc.desc())
        .first()
    )
    return None if row is None else _decision_dict(row)


def _decision_dict(row) -> dict[str, Any]:
    return {
        "decision_id": row.decision_id,
        "cargo_id": row.cargo_id,
        "book_id": row.book_id,
        "run_id": row.run_id,
        "option_id": row.option_id,
        "option_key": row.option_key,
        "title": row.title,
        "recommended_option_id": row.recommended_option_id,
        "was_recommended": row.option_id == row.recommended_option_id,
        "objectives": dict(row.objectives or {}),
        "note": row.note,
        "decided_by": row.decided_by,
        "decided_at_utc": _aware(row.decided_at_utc).isoformat(),
        "booked": False,
    }


def _run(session, cargo_id: str, now: datetime | None):
    moment = _aware(now) or datetime.now(UTC)
    row, _slot = _cargo(session, cargo_id)
    book = load_book(session, row.book_id, now=moment)
    result = optimise(book.portfolio, book.market, book.terms)
    return row, book, result


def _cargo_block(row, book: Book) -> dict[str, Any]:
    from eurogas_nexus.application.lng_in_transit import eta_provenance

    supply = next((s for s in book.portfolio.supplies if s.supply_id == row.cargo_id), None)
    slot = None if supply is None else book.portfolio.slot(supply.slot_id)
    return {
        "cargo_id": row.cargo_id,
        "vessel_name": row.vessel_name,
        "book_id": row.book_id,
        "eta_utc": None if row.eta_utc is None else _aware(row.eta_utc).isoformat(),
        "eta": eta_provenance(row),
        "arrival_gas_day": None
        if supply is None or supply.arrival is None
        else supply.arrival.isoformat(),
        "energy_mwh": None if supply is None else round(supply.energy_mwh, 1),
        "slot": None
        if slot is None
        else {
            "slot_id": slot.slot_id,
            "terminal": slot.terminal,
            "hub": slot.hub,
            "first_gas_day": slot.start.isoformat(),
            "days": slot.days,
            "send_out_mwh_per_day": slot.send_out_mwh_per_day,
            "storage_mwh": slot.storage_mwh,
            "profile": slot.profile,
            "source": slot.source,
            "entitlement": slot.entitlement(),
        },
        "simulated": str(row.source_system or "").endswith("_Sim"),
    }


def disruption_options(session, cargo_id: str, *, now: datetime | None = None) -> dict[str, Any]:
    """The book's re-optimisation as it bears on one cargo: the options that move it, the
    frontier, the recommended default, the timeline and the last recorded choice."""

    row, book, result = _run(session, cargo_id, now)
    payload = result_dict(book.portfolio, result)
    hit = {s.supply_id for s in result.disrupted}
    mine = [o for o in result.options if _involves(o, cargo_id)]
    if cargo_id in hit:
        status = "disrupted"
    elif mine:
        status = "affected"  # another supply's options move this cargo
    else:
        status = "as_planned"
    payload["options"] = [option_dict(book.portfolio, o) for o in mine]
    payload.update(
        {
            "cargo": _cargo_block(row, book),
            "status": status,
            "book_options": len(result.options),
            "inputs": book.inputs,
            "warnings": book.warnings,
            "timeline": _runs(session, row.book_id),
            "decision": _decision(session, cargo_id),
            "advisory": ADVISORY,
        }
    )
    return payload


def option_detail(
    session, cargo_id: str, option_id: str, *, now: datetime | None = None
) -> dict[str, Any]:
    """One option in full: every leg, the arithmetic per scenario, and the mandates it moves."""

    row, book, result = _run(session, cargo_id, now)
    option = result.option(option_id)
    if option is None or not _involves(option, cargo_id):
        raise CargoPlanError(
            "option_not_found",
            "No option of the cargo's current re-optimisation has this id; inputs may have "
            "changed since it was listed.",
            404,
        )
    payload = option_dict(book.portfolio, option, detail=True)
    payload.update(
        {
            "cargo_id": cargo_id,
            "book_id": row.book_id,
            "recommended": result.recommended is not None
            and result.recommended.option_id == option_id,
            "recommended_option_id": None
            if result.recommended is None
            else result.recommended.option_id,
            "dominated_by_title": None
            if option.dominated_by is None
            else result.option(option.dominated_by).title,
            "mandates": _mandate_change(session, book, result, option),
            "preference": result_dict(book.portfolio, result)["preference"],
            "advisory": ADVISORY,
        }
    )
    return payload


def frontier(
    session,
    book_id: str,
    *,
    now: datetime | None = None,
    curtail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """The whole book's options and Pareto frontier, optionally with a pipeline curtailed."""

    from eurogas_nexus.application.lng_in_transit import _check_book

    moment = _aware(now) or datetime.now(UTC)
    _check_book(session, book_id)
    book = _with_curtailment(load_book(session, book_id, now=moment), curtail)
    result = optimise(book.portfolio, book.market, book.terms)
    payload = result_dict(book.portfolio, result)
    payload.update(
        {
            "book_id": book_id,
            "supplies": [
                {
                    "supply_id": s.supply_id,
                    "label": s.label,
                    "kind": s.kind,
                    "terminal": s.terminal or s.point,
                    "slot_id": s.slot_id,
                    "arrival": None if s.arrival is None else s.arrival.isoformat(),
                }
                for s in book.portfolio.supplies
            ],
            "obligations": [
                {
                    "obligation_id": o.obligation_id,
                    "counterparty": o.counterparty,
                    "point": o.point,
                    "first_gas_day": o.start.isoformat(),
                    "last_gas_day": o.end.isoformat(),
                    "mwh_per_day": o.mwh_per_day,
                    "firm": o.firm,
                }
                for o in book.portfolio.obligations
            ],
            "inputs": book.inputs,
            "warnings": book.warnings,
            "what_if": curtail is not None,
            "timeline": _runs(session, book_id),
            "advisory": ADVISORY,
        }
    )
    return payload


def _mandate_change(session, book: Book, result: Result, option: Option) -> dict[str, Any]:
    """Each mandate over the book: usage as the ladder stands, and with the option's change
    in physical (per gas day) and in hedges added. Pipeline supply is not on the ladder, so
    its change enters as the difference only."""

    from eurogas_nexus.db.models import TraderMandateRecord

    records = session.query(TraderMandateRecord).order_by(TraderMandateRecord.trader).all()
    relevant = [r for r in records if book.book_id in (r.book_ids or [])]
    if not relevant or option.base is None:
        return {"checked": len(relevant), "moves": []}
    try:
        from calendar import monthrange

        from eurogas_nexus.application.caller import firm_caller
        from eurogas_nexus.application.limits_service import (
            books_elsewhere,
            horizon,
            mandate_legs,
            mandate_of,
        )
        from eurogas_nexus.application.position_inputs import ladder_inputs
        from eurogas_nexus.domain.lng.disruption import planned_landings
        from eurogas_nexus.domain.risk.limits import MandateLeg, mandate_usage

        today = book.market.now.date()
        start, end = horizon(today)
        base = mandate_legs(ladder_inputs(firm_caller(None, session), today, start, end), today)
        before = planned_landings(book.portfolio, book.market)
        delta = []
        for supply_id, after in option.base.landings.items():
            was = before.get(supply_id)
            days = set(after.flows) | set(was.flows if was else {})
            for day in sorted(days):
                change = after.flows.get(day, 0.0) - (was.flows.get(day, 0.0) if was else 0.0)
                if abs(change) >= 1.0:
                    delta.append(
                        MandateLeg(
                            f"disruption:{supply_id}",
                            "physical",
                            after.hub,
                            book.book_id,
                            "",
                            day,
                            day,
                            change,
                            "physical",
                        )
                    )
        for leg in option.base.hedge_legs:
            year, month = (int(part) for part in leg["month"].split("-"))
            days = monthrange(year, month)[1]
            signed = -leg["mwh"] if leg["action"] == "sell" else leg["mwh"]
            delta.append(
                MandateLeg(
                    "disruption:hedge",
                    "financial",
                    leg["hub"],
                    book.book_id,
                    "",
                    date(year, month, 1),
                    date(year, month, days),
                    signed / days,
                    "future",
                )
            )
        moves = []
        for record in relevant:
            mandate = mandate_of(record)
            elsewhere = books_elsewhere(records, record)
            was = mandate_usage(mandate, base, today=today, books_elsewhere=elsewhere).as_row()
            now_row = mandate_usage(
                mandate, base + delta, today=today, books_elsewhere=elsewhere
            ).as_row()
            moves.append(
                {
                    "mandate_id": record.mandate_id,
                    "name": record.display_name or record.trader,
                    "status_before": str(was["status"]),
                    "status_after": str(now_row["status"]),
                    "utilisation_before_pct": was["utilisation_pct"],
                    "utilisation_after_pct": now_row["utilisation_pct"],
                }
            )
        return {"checked": len(relevant), "moves": moves}
    except Exception as exc:  # noqa: BLE001 - said in the read, never a silent all-clear
        return {"checked": len(relevant), "moves": [], "error": type(exc).__name__}


# -------------------------------------------------------------------------------- write


def choose_option(
    session,
    cargo_id: str,
    option_id: str,
    *,
    actor: str,
    note: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Record the option a person chose (audited). The caller commits. Nothing is booked."""

    from eurogas_nexus.application.audit_service import record_governed_audit
    from eurogas_nexus.db.models import LngDisruptionDecisionRecord, LngDisruptionRunRecord

    moment = _aware(now) or datetime.now(UTC)
    row, _book, result = _run(session, cargo_id, moment)
    option = result.option(option_id)
    if option is None or not _involves(option, cargo_id):
        raise CargoPlanError(
            "option_not_found",
            "No option of the cargo's current re-optimisation has this id; reload the options.",
            404,
        )
    if not option.feasible:
        raise CargoPlanError(
            "option_infeasible",
            "This option breaks a hard constraint: " + "; ".join(option.reasons),
            409,
        )
    last_run = (
        session.query(LngDisruptionRunRecord)
        .filter(LngDisruptionRunRecord.book_id == row.book_id)
        .order_by(LngDisruptionRunRecord.computed_at_utc.desc())
        .first()
    )
    record = LngDisruptionDecisionRecord(
        decision_id=uuid4().hex,
        book_id=row.book_id,
        cargo_id=cargo_id,
        run_id=None if last_run is None else last_run.run_id,
        option_id=option.option_id,
        option_key=option.key,
        title=option.title,
        recommended_option_id=None if result.recommended is None else result.recommended.option_id,
        objectives=dict(option.objectives),
        note=(note or "").strip()[:2000] or None,
        decided_by=actor,
        decided_at_utc=moment,
    )
    session.add(record)
    session.flush()
    record_governed_audit(
        session,
        event_type="portfolio",
        principal=actor,
        action="lng.disruption_choice",
        resource=f"lng_cargo:{cargo_id}",
        detail=f"chose {option.key}"
        + ("" if record.recommended_option_id == option.option_id else " (not the default)"),
    )
    return _decision_dict(record)


# ----------------------------------------------------------------------------- consumer


def _books(session) -> list[str]:
    from eurogas_nexus.db.models import LngCargoRecord, PipelineSupplyRecord

    cargo = {
        b
        for (b,) in session.query(LngCargoRecord.book_id)
        .filter(LngCargoRecord.book_id.isnot(None), LngCargoRecord.status.in_(OPEN_STATUSES))
        .distinct()
        .all()
    }
    pipeline = {b for (b,) in session.query(PipelineSupplyRecord.book_id).distinct().all()}
    return sorted(cargo | pipeline)


def _message(book_id: str, result: Result, change: str, terms: DeskTerms) -> tuple[str, str]:
    rec = result.recommended
    if rec is None:
        title = f"Disruption cleared: book {book_id}"
        lines = [
            "No supply of the book is disrupted any longer; the earlier recommendation "
            "is withdrawn."
        ]
        return title, "\n".join(lines)
    hit = ", ".join(s.label for s in result.disrupted)
    title = f"Disruption options changed: {hit}"
    o = rec.objectives
    lines = [
        f"Recommended: {rec.title}.",
        f"Expected P&L {o['pnl_expected']:+,.0f} EUR (worst {o['pnl_worst']:+,.0f}), "
        f"cost {o['cost']:,.0f} EUR, other supplies moved {o['disrupted_mwh']:,.0f} MWh.",
        "Frontier: " + "; ".join(item.title for item in result.frontier) + ".",
        f"What changed: {change}. Weights: downside x{terms.risk_weight:g}, "
        f"{terms.disruption_eur_per_mwh:g} EUR per MWh of other supply moved.",
        ADVISORY,
    ]
    return title, "\n".join(lines)


def reoptimise(session, book_id: str, *, trigger: str, now: datetime) -> dict[str, Any]:
    """Re-run a book; keep a run row and notify when the result materially moved."""

    from eurogas_nexus.application.alert_routing import (
        CARGO_ROLE_CATEGORIES,
        addressed_line,
        route_for,
    )
    from eurogas_nexus.application.notifications import queue_notification
    from eurogas_nexus.db.models import LngDisruptionRunRecord

    moment = _aware(now) or datetime.now(UTC)
    try:
        book = load_book(session, book_id, now=moment)
        result = optimise(book.portfolio, book.market, book.terms)
    except (CargoPlanError, DisruptionError) as exc:
        return {"book_id": book_id, "status": "skipped", "reason": str(exc)}
    runs = (
        session.query(LngDisruptionRunRecord)
        .filter(LngDisruptionRunRecord.book_id == book_id)
        .order_by(LngDisruptionRunRecord.computed_at_utc.desc())
        .limit(50)
        .all()
    )
    last = runs[0] if runs else None
    rec = result.recommended
    key = None if rec is None else rec.key
    pnl = None if rec is None else rec.objectives["pnl_expected"]
    frontier_keys = sorted(o.key for o in result.frontier)
    change = None
    if last is None:
        if not result.disrupted:
            return {"book_id": book_id, "status": "as_planned"}
        change = "recommendation"
    elif last.recommended_key != key:
        change = "recommendation"
    elif sorted(item.get("key") for item in (last.frontier or [])) != frontier_keys:
        change = "frontier"
    elif (
        pnl is not None
        and last.recommended_pnl_eur is not None
        and abs(pnl - last.recommended_pnl_eur) >= book.terms.material_change_eur
    ):
        change = "pnl"
    if change is None:
        return {"book_id": book_id, "status": "unchanged", "digest": result.digest()}
    digest = result.digest()
    told = next((r for r in runs if r.notified), None)
    decision = "notified"
    if told is not None and told.digest == digest and change != "pnl":
        decision = "duplicate"
    elif (
        told is not None
        and change != "recommendation"
        and moment - _aware(told.computed_at_utc) < COOLDOWN
    ):
        decision = "cooldown"
    queued = []
    if decision == "notified":
        title, body = _message(book_id, result, change, book.terms)
        severity = "warning" if rec is not None else "info"
        for role in ROLES:
            route = route_for(CARGO_ROLE_CATEGORIES[role])
            if queue_notification(
                session,
                category=route.notification_category,
                severity=severity,
                title=title,
                body=body + "\n\n" + addressed_line(route),
                dedupe_key=f"lng_disruption:{book_id}:{digest}:{change}:{role}",
                now=moment,
            ):
                queued.append(role)
    run = LngDisruptionRunRecord(
        run_id=uuid4().hex,
        book_id=book_id,
        computed_at_utc=moment,
        trigger=trigger[:160],
        digest=digest,
        disrupted=[s.supply_id for s in result.disrupted],
        recommended_option_id=None if rec is None else rec.option_id,
        recommended_key=key,
        recommended_title=None if rec is None else rec.title,
        recommended_pnl_eur=pnl,
        frontier=[
            {
                "option_id": o.option_id,
                "key": o.key,
                "title": o.title,
                "pnl_expected": o.objectives["pnl_expected"],
            }
            for o in result.frontier
        ],
        options=[
            {
                "option_id": o.option_id,
                "key": o.key,
                "feasible": o.feasible,
                "on_frontier": o.on_frontier,
                "objectives": dict(o.objectives),
            }
            for o in result.options
        ],
        change=change,
        notified=bool(queued),
    )
    session.add(run)
    session.flush()
    return {
        "book_id": book_id,
        "status": "recorded",
        "change": change,
        "decision": decision,
        "notified": queued,
        "run_id": run.run_id,
        "recommended": key,
    }


class DisruptionConsumer:
    """Re-optimises each book an input change touches."""

    name = CONSUMER_NAME

    def accepts(self, record) -> bool:
        return record.event_type in ACCEPTED

    def handle(self, session, records, *, now_utc: datetime) -> dict[str, Any]:
        books: dict[str, str] = {}
        everything = None
        for record in records:
            trigger = f"event:{record.event_id}"
            if record.event_type == "cargo.changed":
                book_id = (record.payload_json or {}).get("book_id")
                if book_id:
                    books[book_id] = trigger
                continue
            if everything is None:
                everything = _books(session)
            for book_id in everything:
                books[book_id] = trigger
        results = [
            reoptimise(session, book_id, trigger=trigger, now=now_utc)
            for book_id, trigger in sorted(books.items())
        ]
        return {"books": results, "notified": any(r.get("notified") for r in results)}


def register() -> DisruptionConsumer:
    """Subscribe the consumer to the outbox (idempotent)."""

    from eurogas_nexus.application import market_events

    try:
        return market_events.consumer(CONSUMER_NAME)  # type: ignore[return-value]
    except KeyError:
        return market_events.register_consumer(DisruptionConsumer())  # type: ignore[return-value]


__all__ = [
    "ACCEPTED",
    "CONSUMER_NAME",
    "DisruptionConsumer",
    "choose_option",
    "disruption_options",
    "frontier",
    "load_book",
    "option_detail",
    "reoptimise",
]
