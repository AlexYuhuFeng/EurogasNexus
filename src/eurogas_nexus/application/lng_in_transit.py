"""The firm's cargoes in transit, each as one linked plan (``domain/lng/in_transit.py``).

Reads the cargo (``lng_cargoes``: ETA, loading time, energy), its regas slot
(``regas_slots``), the hedges the desk recorded against it (``lng_cargo_hedges``), the
firm's approved boil-off assumption, and the terminal's hub and gas in kind (the firm's terms
or the tariff register), then builds the plan: berth, boil-off, delivered energy, send-out by
gas day, hub months, hedge cover and suggestions.

Every change to a cargo, its slot or its hedges is a ``cargo.changed`` market event
(``market_event_capture.cargo_event``) whose payload holds what the plan is built from. The
plan before the last change is rebuilt from the previous revision, so "what did the new ETA
do to my book" is a comparison of two plans, not a guess.

Nothing is offered, nominated or traded: the plan is for the desk to decide.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import uuid4

from eurogas_nexus.domain.lng.in_transit import (
    CargoInTransit,
    CargoPlan,
    HedgeLeg,
    InTransitError,
    SlotWindow,
    build_plan,
    compare,
)

#: The firm's assumption key for boil-off, %/day (the cargo economics reads the same key).
BOIL_OFF_KEY = "lng.boil_off"
#: Used, and labelled, when the firm has approved no boil-off figure: a modern membrane
#: carrier's design rate is about 0.085-0.10 %/day; the desk standard is the cargo
#: economics' 0.10.
STANDARD_BOIL_OFF = 0.10
MONTH_PATTERN = r"^\d{4}-(0[1-9]|1[0-2])$"


class CargoPlanError(ValueError):
    def __init__(self, code: str, message: str, status_code: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


@dataclass(frozen=True)
class _Resolved:
    hub: str
    gas_in_kind_pct: float
    source: str


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _instant(text: str | None) -> datetime | None:
    if text is None:
        return None
    return _aware(datetime.fromisoformat(text))


def _number(text: Any) -> float | None:
    if text is None:
        return None
    try:
        return float(Decimal(str(text)))
    except InvalidOperation:
        return None


def _normal(name: str) -> str:
    words = [w for w in name.lower().replace("-", " ").split() if w not in {"lng", "terminal"}]
    return " ".join(words)


def _terminal(session, name: str | None) -> _Resolved | None:
    """The hub and gas in kind of the terminal a slot names, by name or id."""

    if not name:
        return None
    from eurogas_nexus.application.lng_cargo_economics import known_terminals

    wanted = _normal(name)
    for terminal in known_terminals(session):
        if wanted in {_normal(terminal.name), _normal(terminal.terminal_id)}:
            return _Resolved(
                terminal.hub,
                float(terminal.gas_in_kind_pct or 0.0),
                f"terminal {terminal.terminal_id}"
                + ("" if terminal.gas_in_kind_pct is not None else " (no gas-in-kind figure)"),
            )
    from eurogas_nexus.application.identity_resolution import load_resolver

    hub = load_resolver(session).hub(name).hub
    if hub is None:
        return None
    return _Resolved(hub, 0.0, f"hub mapped from {name!r}; no terminal terms or tariff held")


def _boil_off(
    session, book_id: str | None, day: date, contract_rate: float | None = None
) -> tuple[float, str]:
    if contract_rate is not None:
        return contract_rate, "cargo contract terms"
    from eurogas_nexus.db.repositories.commercial_assumptions import resolve_assumption_version

    resolved = resolve_assumption_version(session, day=day, book_id=book_id)
    if resolved is not None:
        version_id, version = resolved
        value = version.value(BOIL_OFF_KEY)
        if value is not None and value.value is not None:
            return float(value.value), f"approved assumption {BOIL_OFF_KEY} ({version_id})"
    return STANDARD_BOIL_OFF, f"desk standard {STANDARD_BOIL_OFF} %/day (no approved figure)"


def _cargo_rows(session, cargo_id: str):
    from eurogas_nexus.db.models import LngCargoHedgeRecord, LngCargoRecord, RegasSlotRecord

    row = session.get(LngCargoRecord, cargo_id)
    if row is None or row.book_id is None:
        # A market cargo from a vessel feed is context, not the firm's position.
        raise CargoPlanError("cargo_not_found", "No cargo of the firm has this id.", 404)
    slot = (
        session.query(RegasSlotRecord)
        .filter(RegasSlotRecord.cargo_id == cargo_id)
        .order_by(RegasSlotRecord.window_start_utc)
        .first()
    )
    hedges = (
        session.query(LngCargoHedgeRecord)
        .filter(
            LngCargoHedgeRecord.cargo_id == cargo_id,
            LngCargoHedgeRecord.retired_at_utc.is_(None),
        )
        .order_by(LngCargoHedgeRecord.delivery_month, LngCargoHedgeRecord.link_id)
        .all()
    )
    return row, slot, hedges


def _cargo_contract(session, cargo_id: str):
    """The firm's cargo contract (a Confirmation Notice) that names this vessel-feed cargo."""

    from eurogas_nexus.db.models.route_cost import UpstreamResourceContractRecord
    from eurogas_nexus.domain.contracts import kinds

    rows = (
        session.query(UpstreamResourceContractRecord)
        .filter(
            UpstreamResourceContractRecord.contract_kind == kinds.LNG_CARGO,
            UpstreamResourceContractRecord.retired_at_utc.is_(None),
        )
        .all()
    )
    for row in rows:
        if (row.kind_terms or {}).get("lng_cargo_id") != cargo_id:
            continue
        try:
            return row.contract_id, kinds.terms_of(row.contract_kind, row.kind_terms)
        except ValueError:
            return row.contract_id, None
    return None


def _contract_check(contract, eta: datetime | None) -> dict[str, Any] | None:
    if contract is None:
        return None
    contract_id, terms = contract
    if terms is None:
        return {"contract_id": contract_id, "window": None, "eta_inside_window": None}
    start, end = terms.delivery_days()
    inside = None if eta is None else start <= eta.date() <= end
    return {
        "contract_id": contract_id,
        "delivery_term": terms.delivery_term,
        "window": [start.isoformat(), end.isoformat()],
        "eta_inside_window": inside,
        "warning": (
            None
            if inside in (True, None)
            else f"The vessel ETA {eta:%d %b} is outside the contract's delivery window "
            f"{start:%d %b}-{end:%d %b}: one of them is out of date."
        ),
    }


def _check_book(session, book_id: str) -> None:
    from eurogas_nexus.security.portfolio_scope import visible_book_ids

    allowed = visible_book_ids(session)
    if allowed is not None and book_id not in allowed:
        raise CargoPlanError("cargo_not_found", "No cargo of the firm has this id.", 404)


def _state(row, slot, hedges, now: datetime) -> dict[str, Any]:
    """The cargo's state in the same shape as its ``cargo.changed`` payload."""

    from eurogas_nexus.application.market_event_capture import cargo_event

    return cargo_event(row, slot=slot, hedges=hedges, now_utc=now).payload


def _inputs(
    session,
    state: dict[str, Any],
    *,
    now: datetime,
    berth_delay_hours: float = 0.0,
    laytime_hours: float = 36.0,
    demurrage_per_day: float | None = None,
    contract_boil_off: float | None = None,
) -> tuple[CargoInTransit, list[dict[str, str]]]:
    """The domain inputs for a cargo state, and where each came from."""

    sources: list[dict[str, str]] = []
    energy = _number(state.get("energy_gwh"))
    loaded_at = _instant(state.get("departed_at_utc"))
    eta = _instant(state.get("eta_utc"))
    for value, field in ((energy, "energy_gwh"), (loaded_at, "departed_at_utc"), (eta, "eta_utc")):
        if value is None:
            raise CargoPlanError(
                "cargo_incomplete",
                f"The cargo record has no {field}; the vessel feed or ETRM import must carry it.",
            )
    sources.append({"input": "loaded energy", "source": "cargo record energy_gwh"})
    sources.append({"input": "loaded at", "source": "cargo record departed_at_utc"})
    sources.append({"input": "ETA", "source": "cargo record eta_utc"})

    slot = None
    held = state.get("slot")
    if held is not None:
        terminal = _terminal(session, held.get("terminal"))
        if terminal is None:
            raise CargoPlanError(
                "terminal_hub_unknown",
                f"The slot's terminal {held.get('terminal')!r} maps to no hub; record the "
                "terminal's terms or a delivery-point mapping.",
            )
        send_out_gwh = _number(held.get("send_out_gwh_d"))
        if not send_out_gwh:
            raise CargoPlanError(
                "slot_send_out_missing", "The regas slot has no send-out rate (GWh/d)."
            )
        slot = SlotWindow(
            slot_id=held["slot_id"],
            terminal=held.get("terminal") or held["slot_id"],
            hub=terminal.hub,
            window_start_utc=_instant(held["window_start_utc"]),
            window_end_utc=_instant(held["window_end_utc"]),
            send_out_mwh_per_day=send_out_gwh * 1000,
            gas_in_kind_pct=terminal.gas_in_kind_pct,
        )
        sources.append({"input": "slot window and send-out", "source": f"slot {slot.slot_id}"})
        sources.append({"input": "hub and gas in kind", "source": terminal.source})

    boil_off, boil_source = _boil_off(
        session, state.get("book_id"), now.date(), contract_boil_off
    )
    sources.append({"input": "boil-off", "source": boil_source})
    hedges = tuple(
        HedgeLeg(hub=hub, month=month, mwh=float(Decimal(str(mwh))))
        for hub, month, mwh in state.get("hedges") or ()
    )
    sources.append(
        {"input": "hedges", "source": f"{len(hedges)} leg(s) the desk recorded on the cargo"}
    )
    try:
        cargo = CargoInTransit(
            cargo_id=state["cargo_id"],
            loaded_mwh=energy * 1000,
            loaded_at_utc=loaded_at,
            eta_utc=eta,
            boil_off_pct_per_day=boil_off,
            slot=slot,
            hedges=hedges,
            berth_delay_hours=berth_delay_hours,
            laytime_hours=laytime_hours,
            demurrage_per_day=demurrage_per_day,
        )
    except InTransitError as exc:
        raise CargoPlanError("cargo_inputs_invalid", str(exc)) from exc
    return cargo, sources


def _revisions(session, cargo_id: str):
    """The last two revisions of the cargo's ``cargo.changed`` event, newest first."""

    from eurogas_nexus.db.models import MarketEventRecord

    return (
        session.query(MarketEventRecord)
        .filter(
            MarketEventRecord.subject_key == f"cargo:{cargo_id}",
            MarketEventRecord.event_type == "cargo.changed",
        )
        .order_by(MarketEventRecord.revision.desc())
        .limit(2)
        .all()
    )


def _previous_state(session, cargo_id: str) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """The last two revisions of the cargo's event: (before, after) payloads."""

    rows = _revisions(session, cargo_id)
    if len(rows) < 2:
        return None
    return rows[1].payload_json, rows[0].payload_json


#: Payload fields of ``cargo.changed`` and the name a reader sees for a change to each.
_CHANGE_KINDS = (
    ("eta_utc", "eta"),
    ("departed_at_utc", "departure"),
    ("energy_gwh", "energy"),
    ("slot", "slot"),
    ("hedges", "hedges"),
    ("status", "status"),
    ("destination_terminal", "destination"),
)


def _change_meta(session, row, hedges) -> dict[str, Any] | None:
    """When the cargo's plan inputs last changed, what changed and who changed it.

    ``by`` is the person who recorded the hedge set for a hedge change, else the import that
    carried the new values (``import ETRM``): the event itself records no person. ``kinds`` is
    ``["recorded"]`` for the first recorded state. ``eta_before_utc`` is the ETA the change
    replaced, when the ETA changed.
    """

    rows = _revisions(session, row.cargo_id)
    if not rows:
        return None
    latest = rows[0].payload_json or {}
    before = rows[1].payload_json if len(rows) > 1 else None
    if before is None:
        kinds = ["recorded"]
    else:
        kinds = [name for field, name in _CHANGE_KINDS if before.get(field) != latest.get(field)]
    by = f"import {row.source_system}"
    if "hedges" in kinds and hedges:
        newest = max(hedges, key=lambda leg: _aware(leg.created_at_utc))
        by = newest.created_by
    return {
        "at_utc": _aware(rows[0].ingested_at_utc).isoformat(),
        "kinds": kinds,
        "by": by,
        "eta_before_utc": (before or {}).get("eta_utc") if "eta" in kinds else None,
    }


def _hedge_legs(hedges) -> list[dict[str, Any]]:
    """The hedge legs held against the cargo, with who recorded them and when."""

    return [
        {
            "hub": leg.hub,
            "month": leg.delivery_month,
            "mwh": float(leg.mwh),
            "reference": leg.reference,
            "created_by": leg.created_by,
            "created_at_utc": _aware(leg.created_at_utc).isoformat(),
        }
        for leg in hedges
    ]


def _slot_options(session, row, now: datetime) -> list[dict[str, Any]]:
    """Slots a what-if may move the cargo to: the book's own (or unbooked) slots whose window
    has not closed. ``free`` is false when another cargo already holds the slot."""

    from eurogas_nexus.db.models import RegasSlotRecord

    slots = (
        session.query(RegasSlotRecord)
        .filter(RegasSlotRecord.window_end_utc >= now)
        .order_by(RegasSlotRecord.window_start_utc)
        .limit(200)
        .all()
    )
    out = []
    for slot in slots:
        if slot.book_id is not None and slot.book_id != row.book_id:
            continue
        end = _aware(slot.window_end_utc)
        if end is None or end < now:
            continue
        out.append(
            {
                "slot_id": slot.slot_id,
                "terminal": slot.terminal_name,
                "window_start_utc": _aware(slot.window_start_utc).isoformat(),
                "window_end_utc": end.isoformat(),
                "send_out_gwh_d": _number(slot.send_out_gwh_d),
                "held_by": slot.cargo_id,
                "free": slot.cargo_id in (None, row.cargo_id),
            }
        )
        if len(out) >= 24:
            break
    return out


def _mspa_terms(session, contract) -> dict[str, Any] | None:
    """Laytime and demurrage from the master agreement the cargo contract is made under."""

    if contract is None:
        return None
    from eurogas_nexus.db.models.route_cost import UpstreamResourceContractRecord
    from eurogas_nexus.domain.contracts import kinds

    cargo_row = session.get(UpstreamResourceContractRecord, contract[0])
    master_id = getattr(cargo_row, "master_contract_id", None)
    if not master_id:
        return None
    master = session.get(UpstreamResourceContractRecord, master_id)
    if master is None or master.contract_kind != kinds.LNG_MSPA:
        return None
    terms = kinds.terms_of(master.contract_kind, master.kind_terms)
    if terms is None:
        return None
    return {
        "master_contract_id": master_id,
        "laytime_hours": terms.laytime_hours,
        "demurrage_usd_per_day": terms.demurrage_usd_per_day,
    }


def _summary(row, plan: CargoPlan, slot: SlotWindow | None = None) -> dict[str, Any]:
    return {
        "cargo_id": row.cargo_id,
        "vessel_name": row.vessel_name,
        "vessel_imo": row.vessel_imo,
        "status": row.status,
        "book_id": row.book_id,
        "load_port": row.load_port,
        "destination_terminal": row.destination_terminal,
        "departed_at_utc": _aware(row.departed_at_utc).isoformat() if row.departed_at_utc else None,
        "eta_utc": _aware(row.eta_utc).isoformat() if row.eta_utc else None,
        "source_system": row.source_system,
        # When the import last wrote the cargo row (the ETA's age, not the plan's).
        "imported_at_utc": _aware(row.updated_at_utc).isoformat() if row.updated_at_utc else None,
        "simulated": row.source_system.endswith("_Sim"),
        "slot_status": plan.slot_status,
        "hub": None if slot is None else slot.hub,
        "slot": None
        if slot is None
        else {
            "slot_id": slot.slot_id,
            "terminal": slot.terminal,
            "window_start_utc": slot.window_start_utc.isoformat(),
            "window_end_utc": slot.window_end_utc.isoformat(),
            "send_out_mwh_per_day": round(slot.send_out_mwh_per_day, 1),
        },
        # The cargo record's loaded energy: the energy waterfall starts here and must reconcile.
        "loaded_mwh": None if row.energy_gwh is None else round(float(row.energy_gwh) * 1000, 1),
        "delivered_mwh": round(plan.delivered_mwh, 1),
        "suggestions": len([item for item in plan.suggestions if item.kind != "deadline"]),
    }


def cargo_plan(
    session,
    cargo_id: str,
    *,
    now: datetime | None = None,
    berth_delay_hours: float = 0.0,
    laytime_hours: float = 36.0,
    demurrage_per_day: float | None = None,
) -> dict[str, Any]:
    """The cargo's plan now, its inputs with their sources, and what the last recorded
    change (a new ETA, slot or hedge set) did compared with the plan before it."""

    moment = _aware(now) or datetime.now(UTC)
    row, slot, hedges = _cargo_rows(session, cargo_id)
    _check_book(session, row.book_id)
    contract = _cargo_contract(session, cargo_id)
    options = {
        "berth_delay_hours": berth_delay_hours,
        "laytime_hours": laytime_hours,
        "demurrage_per_day": demurrage_per_day,
        "contract_boil_off": None if contract is None or contract[1] is None
        else contract[1].boil_off_pct_per_day,
    }
    cargo, sources = _inputs(session, _state(row, slot, hedges, moment), now=moment, **options)
    plan = build_plan(cargo, now=moment)
    last_change = None
    pair = _previous_state(session, cargo_id)
    if pair is not None:
        try:
            before, _ = _inputs(session, pair[0], now=moment, **options)
            after, _ = _inputs(session, pair[1], now=moment, **options)
        except CargoPlanError:
            last_change = None  # an earlier revision lacked an input; nothing to compare
        else:
            last_change = compare(
                build_plan(before, now=moment), build_plan(after, now=moment)
            ).as_dict()
            last_change.pop("after", None)  # the plan now is returned in full already
    summary = _summary(row, plan, cargo.slot)
    summary["changed"] = _change_meta(session, row, hedges)
    checked = _contract_check(contract, _aware(row.eta_utc))
    if checked is not None:
        checked["mspa"] = _mspa_terms(session, contract)
    return {
        "cargo": summary,
        "inputs": sources,
        "plan": plan.as_dict(),
        "contract": checked,
        "last_change": last_change,
        "hedges": _hedge_legs(hedges),
        "slot_options": _slot_options(session, row, moment),
        "as_of_utc": moment.isoformat(),
        "advisory": "Suggestions for the desk; nothing is traded or nominated.",
    }


def send_out_plan(session, cargo_id: str, *, now: datetime | None = None
                  ) -> tuple[CargoPlan, str | None]:
    """The cargo's plan as :func:`cargo_plan` builds it, and the id of the slot it uses.

    For a reader that needs the send-out by gas day (My gas day), so the gas-day line and the
    cargo plan are one figure. Raises :class:`CargoPlanError` when the plan cannot be built.
    """

    moment = _aware(now) or datetime.now(UTC)
    row, slot, hedges = _cargo_rows(session, cargo_id)
    contract = _cargo_contract(session, cargo_id)
    cargo, _sources = _inputs(
        session, _state(row, slot, hedges, moment), now=moment,
        contract_boil_off=None if contract is None or contract[1] is None
        else contract[1].boil_off_pct_per_day,
    )
    return build_plan(cargo, now=moment), (None if cargo.slot is None else cargo.slot.slot_id)


def what_if(session, cargo_id: str, changes: dict[str, Any], *, now: datetime | None = None):
    """The plan now against the plan under a changed ETA, slot or berth delay."""

    moment = _aware(now) or datetime.now(UTC)
    row, slot, hedges = _cargo_rows(session, cargo_id)
    _check_book(session, row.book_id)
    state = _state(row, slot, hedges, moment)
    contract = _cargo_contract(session, cargo_id)
    options = {
        "laytime_hours": float(changes.get("laytime_hours") or 36.0),
        "demurrage_per_day": changes.get("demurrage_per_day"),
        "contract_boil_off": None if contract is None or contract[1] is None
        else contract[1].boil_off_pct_per_day,
    }
    current, _ = _inputs(session, state, now=moment, **options)
    scenario = dict(state)
    if changes.get("eta_utc") is not None:
        scenario["eta_utc"] = _aware(changes["eta_utc"]).isoformat()
    if changes.get("slot_id") is not None:
        from eurogas_nexus.db.models import RegasSlotRecord

        other = session.get(RegasSlotRecord, changes["slot_id"])
        if other is None or (other.book_id is not None and other.book_id != row.book_id):
            raise CargoPlanError("slot_not_found", "No slot of this book has that id.", 404)
        scenario["slot"] = _state(row, other, hedges, moment)["slot"]
    after, sources = _inputs(
        session,
        scenario,
        now=moment,
        berth_delay_hours=float(changes.get("berth_delay_hours") or 0.0),
        **options,
    )
    change = compare(build_plan(current, now=moment), build_plan(after, now=moment))
    return {
        "cargo_id": cargo_id,
        "change": change.as_dict(),
        "inputs": sources,
        "as_of_utc": moment.isoformat(),
        "advisory": "A what-if: nothing is stored, traded or nominated.",
    }


def cargo_plans(session, *, now: datetime | None = None) -> list[dict[str, Any]]:
    """One line per cargo of the firm that is not yet delivered: the board view."""

    from eurogas_nexus.db.models import LngCargoRecord
    from eurogas_nexus.security.portfolio_scope import visible_book_ids

    moment = _aware(now) or datetime.now(UTC)
    allowed = visible_book_ids(session)
    rows = (
        session.query(LngCargoRecord)
        .filter(
            LngCargoRecord.book_id.isnot(None),
            LngCargoRecord.status.in_(("loading", "laden", "discharging")),
        )
        .order_by(LngCargoRecord.eta_utc)
        .all()
    )
    board = []
    for row in rows:
        if allowed is not None and row.book_id not in allowed:
            continue
        try:
            built = cargo_plan(session, row.cargo_id, now=moment)
        except CargoPlanError as exc:
            board.append(
                {"cargo_id": row.cargo_id, "vessel_name": row.vessel_name, "error": exc.code}
            )
            continue
        line = built["cargo"]
        line["headline"] = (
            built["last_change"]["headline"] if built["last_change"] is not None else None
        )
        line["contract_warning"] = (built["contract"] or {}).get("warning")
        line["next"] = next(
            (item["text"] for item in built["plan"]["suggestions"] if item["kind"] != "deadline"),
            None,
        )
        line["next_action"] = _next_action(built["plan"]["suggestions"])
        line["next_expiry"] = next(
            (item for item in built["plan"]["suggestions"] if item["kind"] == "deadline"), None
        )
        line["months"] = built["plan"]["months"]
        board.append(line)
    return board


def _next_action(suggestions: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The suggestion due first (one without a due time comes after those with one)."""

    actions = [item for item in suggestions if item["kind"] != "deadline"]
    if not actions:
        return None
    return min(
        enumerate(actions),
        key=lambda pair: (pair[1]["due_utc"] is None, pair[1]["due_utc"] or "", pair[0]),
    )[1]


def record_hedges(
    session, cargo_id: str, legs: list[dict[str, Any]], *, actor: str, now: datetime | None = None
) -> dict[str, Any]:
    """Replace the hedges the desk records against a cargo; the old set is retired, not
    deleted, and the change is a ``cargo.changed`` event (commit is the caller's)."""

    import re

    from eurogas_nexus.application.market_event_capture import capture_desk
    from eurogas_nexus.db.models import LngCargoHedgeRecord
    from eurogas_nexus.domain.ontology.markets import find_market

    moment = _aware(now) or datetime.now(UTC)
    row, _slot, current = _cargo_rows(session, cargo_id)
    _check_book(session, row.book_id)
    for leg in legs:
        if not re.match(MONTH_PATTERN, str(leg.get("month", ""))):
            raise CargoPlanError("month_invalid", f"{leg.get('month')!r} is not YYYY-MM.")
        if find_market(str(leg.get("hub", ""))) is None:
            raise CargoPlanError("hub_unknown", f"{leg.get('hub')!r} is not a known hub.")
    for held in current:
        held.retired_at_utc = moment
        held.retired_by = actor
    for leg in legs:
        session.add(
            LngCargoHedgeRecord(
                link_id=uuid4().hex,
                cargo_id=cargo_id,
                hub=str(leg["hub"]).upper(),
                delivery_month=leg["month"],
                mwh=Decimal(str(leg["mwh"])),
                reference=leg.get("reference"),
                created_at_utc=moment,
                created_by=actor,
            )
        )
    session.flush()
    from eurogas_nexus.db.repositories.audit import record_audit_event

    record_audit_event(
        session,
        event_type="portfolio",
        principal=actor,
        action="lng.cargo_hedges",
        resource=f"lng_cargo:{cargo_id}",
        detail=f"{len(legs)} leg(s) replace {len(current)}",
    )
    captured = capture_desk(session, cargo_ids=[cargo_id], now_utc=moment)
    return {"cargo_id": cargo_id, "legs": len(legs), "events": captured}
