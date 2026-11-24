"""My gas day (Today, first row for trader and operations): what to clear, by when, at what cost.

Per hub, for today's and tomorrow's gas day, from the firm's own records only (AGENTS.md rule 19):

- **IN**: contract and upstream deliveries by delivery point (nominated quantity where the
  delivery record holds one, else the contract quantity, said so), LNG send-out from the
  regas slots the firm holds, storage withdrawal and imports on held capacity from the
  schedule, purchases booked (ETRM and exchange, spread over their delivery days);
- **OUT**: sales booked, customer offtake, storage injection and exports from the schedule;
- **net to clear** in the hub's own unit (NBP in therms per day, continental hubs in MWh per
  day with the MW figure beside it), long positive;
- **done today**: the within-day and day-ahead trades booked during today's gas day;
- **time left**: the nomination deadline and last renomination of each gas day, from a window
  the firm declares for the market area, else the network-code default labelled as an
  assumption (``domain/market/hub_cutoffs``, the calendar the prompt signals use too);
- **cost of doing nothing**: the net left open at the cash-out premium (short) or discount
  (long) from the approved assumption set in force for the book, labelled as an assumption;
  no published imbalance price is read (``docs/legal/DATA_SOURCE_TERMS.md``, "Imbalance
  prices": the terms of the National Gas and THE publications could not be verified).

**Scope** comes from books and mandates, never from the persona (AGENTS.md rule 7): a caller
named by a mandate sees the books that mandate lists (within the books portfolio isolation
lets him see) less what is delegated to others, plus what is delegated to him; a caller with
no mandate sees every book he may see, each delegated part attributed. Nothing here
nominates, trades or settles (rule 8).

我的燃气日：按枢纽列出今日/明日流入、流出、待平衡净头寸、截止时间与不平衡成本（假设已标注）。
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from eurogas_nexus.domain.portfolio.gas_day_balance import (
    IN,
    OUT,
    Delegation,
    GasDayLine,
    HubBalance,
    LineAdjustment,
    balance_for,
)

#: Kinds in the order a desk reads them, IN first.
IN_KINDS = ("supply", "upstream", "lng_send_out", "storage_withdrawal", "import", "purchase")
OUT_KINDS = ("sale", "customer_offtake", "storage_injection", "export")
#: Resource types of a contract that are producer gas landed at a beach terminal.
UPSTREAM_TYPES = frozenset({"UPSTREAM", "UPSTREAM_TENDER", "EQUITY_GAS", "BEACH"})


# ------------------------------------------------------------------ scope


@dataclass(frozen=True)
class Scope:
    """Whose gas day this is: one trader's mandated books, or every book the caller sees."""

    trader: str | None
    owned_books: frozenset[str] | None
    mandates: tuple[dict[str, Any], ...]
    visible: frozenset[str] | None  # None: every book

    def payload(self) -> dict[str, Any]:
        if self.trader is None:
            return {"kind": "all_books", "mandates": [], "books": None}
        return {
            "kind": "mandate",
            "mandates": list(self.mandates),
            "books": sorted(self.owned_books or ()),
        }


def caller_keys(caller) -> set[str]:
    principal = caller.principal
    return {
        str(value).strip().lower()
        for value in (getattr(principal, "principal_id", None), getattr(principal, "name", None))
        if value
    }


def mandates_of(session, caller, today: date) -> list:
    """The mandates in force that name this caller (by sign-in id or name)."""

    from eurogas_nexus.db.models import TraderMandateRecord

    keys = caller_keys(caller)
    return [
        row
        for row in session.query(TraderMandateRecord).order_by(TraderMandateRecord.mandate_id)
        if str(row.trader).strip().lower() in keys
        and (row.valid_until is None or row.valid_until >= today)
    ]


def scope_of(session, caller, today: date) -> Scope:
    from eurogas_nexus.security.portfolio_scope import visible_book_ids

    allowed = visible_book_ids(session)
    visible = None if allowed is None else frozenset(allowed)
    mandates = mandates_of(session, caller, today)
    if not mandates:
        return Scope(None, None, (), visible)
    books: set[str] = set()
    for row in mandates:
        if row.book_ids:
            books.update(row.book_ids)
        elif visible is not None:
            books.update(visible)
    if visible is not None:
        books &= visible
    return Scope(
        trader=str(mandates[0].trader),
        owned_books=frozenset(books),
        mandates=tuple(
            {"id": row.mandate_id, "name": row.display_name, "hubs": list(row.hubs or [])}
            for row in mandates
        ),
        visible=visible,
    )


# ------------------------------------------------------------------ units


def gas_day_hours(day: date) -> float:
    from eurogas_nexus.domain.market.gas_day import gas_day_start_for_date

    start = gas_day_start_for_date(day)
    end = gas_day_start_for_date(day + timedelta(days=1))
    return (end - start).total_seconds() / 3600.0


def native_quantity(hub: str, mwh: float, day: date) -> dict[str, Any]:
    """A day's quantity in the hub's desk unit: NBP th/d; continental MWh/d with its MW."""

    from eurogas_nexus.domain.market.units import convert_energy

    if hub.upper() == "NBP":
        return {"value": round(convert_energy(mwh, "MWh", "therm")), "unit": "th/d",
                "mwh": round(mwh, 1)}
    return {"value": round(mwh, 1), "unit": "MWh/d", "mwh": round(mwh, 1),
            "mw": round(mwh / gas_day_hours(day), 1)}


# ------------------------------------------------------------------ lines


def _aware(moment) -> datetime | None:
    if moment is None:
        return None
    if not isinstance(moment, datetime):
        moment = datetime.fromisoformat(str(moment))
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def _point(contract) -> str | None:
    """The sub-terminal or point the contract delivers at, without the hub's own name."""

    text = str(getattr(contract, "delivery_point_name", "") or "").strip()
    words = text.split()
    if len(words) > 1 and words[0].upper() in {"NBP", "TTF", "THE", "PEG", "ZTP", "CEGH", "PVB",
                                               "PSV", "ZEE", "ETF"}:
        return " ".join(words[1:])
    return text or None


def active_outages(session, caller, now: datetime, days: list[date]) -> list[dict[str, Any]]:
    """REMIT outages running on any of the days, from the service the outage list, the ticker
    and the map read (``application/remit_outages``), as the caller may see them."""

    from eurogas_nexus.application.remit_outages import load_outage_rows
    from eurogas_nexus.domain.dataops.entitlement import filter_rows_for_principal

    horizon = max((days[-1] - days[0]).days + 2, 2)
    rows = load_outage_rows(session, now=now, horizon_days=horizon)
    principal = getattr(caller, "principal", None)
    return filter_rows_for_principal(principal, rows) if principal is not None else rows


def outage_adjustments(contract_name: str, hub: str, day: date,
                       outages: Iterable[dict[str, Any]]) -> list[LineAdjustment]:
    """The outages at a contract's source on one gas day, each with the share of the asset out
    and the share of the gas day it covers.

    The link is the one the event-exposure opportunity uses (``domain/opportunities/
    event_exposure.source_name``): the contract's source name in the outage's asset name, in
    the contract hub's balancing zone, so Today and Opportunities read one outage alike.
    """

    from eurogas_nexus.domain.market.gas_day import gas_day_start_for_date
    from eurogas_nexus.domain.opportunities.event_exposure import source_name

    source = source_name(contract_name or "")
    if source is None:
        return []
    day_start = gas_day_start_for_date(day)
    day_end = gas_day_start_for_date(day + timedelta(days=1))
    found = []
    for row in outages:
        if hub.upper() not in str(row.get("balancing_zone") or "").upper():
            continue
        if source.casefold() not in str(row.get("facility_name") or "").casefold():
            continue
        technical, unavailable = row.get("technical_capacity"), row.get("unavailable_capacity")
        if not technical or unavailable is None:
            continue
        start = _aware(row.get("start_utc")) or day_start
        end = _aware(row.get("end_utc")) or day_end
        overlap = (min(end, day_end) - max(start, day_start)).total_seconds()
        if overlap <= 0:
            continue
        found.append(LineAdjustment(
            kind="outage",
            source=str(row.get("source_system") or "REMIT"),
            ref=str(row.get("event_id")),
            label=str(row.get("facility_name") or ""),
            mwh=0.0,
            share=min(max(float(unavailable) / float(technical), 0.0), 1.0),
            day_share=overlap / (day_end - day_start).total_seconds(),
            version=row.get("version"),
            source_reference=row.get("source_reference"),
            simulated=str(row.get("source_reference") or "").lower().startswith("demo"),
        ))
    return found


def contract_lines(
    inputs, days: Iterable[date], nominations: dict,
    outages: Iterable[dict[str, Any]] = (),
) -> list[tuple[date, GasDayLine]]:
    """Physical legs (contracts) delivering on each day: nominated where held, else DCQ.

    A supply line whose source has an outage on the day is capped at what the asset can still
    deliver: the daily contract quantity less the share out over the share of the day it runs
    (the largest outage where several messages name the source). The outage is on the line,
    with its source and id, also when the nomination is already under the cap.
    """

    outages = list(outages)
    contracts = {row.contract_id: row for row in inputs.contracts}
    out = []
    for leg in inputs.legs:
        if leg.kind != "physical":
            continue
        contract = contracts.get(leg.reference)
        for day in days:
            if not leg.first_gas_day <= day <= leg.last_gas_day:
                continue
            held = nominations.get((leg.reference, day))
            mwh, basis = (held, "nominated") if held is not None else (leg.mwh_per_day,
                                                                         "contract_quantity")
            resource = str(getattr(contract, "resource_type", "") or "").upper()
            kind = "upstream" if resource in UPSTREAM_TYPES else "supply"
            if mwh < 0:
                kind = "sale"
            adjustments: tuple[LineAdjustment, ...] = ()
            if mwh > 0 and leg.mwh_per_day > 0 and outages:
                found = outage_adjustments(
                    str(getattr(contract, "contract_name", None) or leg.reference), leg.hub,
                    day, outages)
                if found:
                    cut = max(item.share * item.day_share for item in found)
                    cap = leg.mwh_per_day * (1.0 - cut)
                    taken = max(float(mwh) - cap, 0.0)
                    worst = max(found, key=lambda item: item.share * item.day_share)
                    adjustments = tuple(
                        LineAdjustment(**{**item.__dict__,
                                          "mwh": round(taken, 3) if item is worst else 0.0})
                        for item in found)
                    mwh = min(float(mwh), cap)
            out.append((day, GasDayLine(
                ref=f"contract:{leg.reference}",
                hub=leg.hub,
                book_id=leg.book_id or "",
                direction=IN if mwh >= 0 else OUT,
                kind=kind,
                label=str(getattr(contract, "contract_name", None) or leg.reference),
                mwh=abs(float(mwh)),
                basis=basis,
                point=_point(contract) if contract is not None else None,
                simulated=any(item.simulated for item in adjustments),
                adjustments=adjustments,
            )))
    return out


def trade_lines(inputs, days: list[date], today: date) -> list[tuple[date, GasDayLine]]:
    """Booked trades delivering on each day; today's WD/DA trades summed per book and side."""

    from eurogas_nexus.domain.market.gas_day import gas_day_label, gas_day_start_for_date

    orders = {order.order_observation_id: order for order in inputs.orders}
    prompt_starts = {gas_day_start_for_date(day) for day in days}
    out: list[tuple[date, GasDayLine]] = []
    prompt: dict[tuple, dict] = {}
    for leg in inputs.legs:
        if leg.kind != "financial":
            continue
        order = orders.get(leg.reference)
        simulated = bool(order is not None and str(order.source_system).endswith("_Sim"))
        start = _aware(getattr(order, "delivery_start_utc", None))
        end = _aware(getattr(order, "delivery_end_utc", None))
        booked = _aware(getattr(order, "observed_at_utc", None))
        is_prompt = bool(
            start in prompt_starts and end is not None and (end - start) <= timedelta(hours=25)
            and booked is not None and gas_day_label(booked) == today.isoformat()
        )
        direction = IN if leg.mwh_per_day > 0 else OUT
        provider = str(getattr(order, "provider_id", "") or "").upper()
        venue = "bilateral" if provider == "ETRM" else "exchange"
        for day in days:
            if not leg.first_gas_day <= day <= leg.last_gas_day:
                continue
            if is_prompt:
                key = (day, leg.hub, leg.book_id or "", direction, venue)
                entry = prompt.setdefault(key, {"mwh": 0.0, "count": 0, "simulated": False})
                entry["mwh"] += abs(leg.mwh_per_day)
                entry["count"] += 1
                entry["simulated"] = entry["simulated"] or simulated
                continue
            label = (str(order.account_label) if provider == "ETRM" and order is not None
                     else str(getattr(order, "venue", None) or "Exchange"))
            out.append((day, GasDayLine(
                ref=f"trade:{leg.reference}",
                hub=leg.hub,
                book_id=leg.book_id or "",
                direction=direction,
                kind="purchase" if direction == IN else "sale",
                label=label,
                mwh=abs(leg.mwh_per_day),
                basis="booked",
                point=str(getattr(order, "contract_code", "") or "") or None,
                simulated=simulated,
                venue=venue,
            )))
    for (day, hub, book, direction, venue), entry in sorted(prompt.items()):
        # Bilateral prompt deals (ETRM) are kept apart from screen trades, so a balance by
        # venue reads the same lines; the screen line keeps its reference.
        suffix = ":bilateral" if venue == "bilateral" else ""
        out.append((day, GasDayLine(
            ref=f"prompt:{book}:{hub}:{direction}:{day.isoformat()}{suffix}",
            hub=hub,
            book_id=book,
            direction=direction,
            kind="purchase" if direction == IN else "sale",
            label=f"{entry['count']}",
            mwh=entry["mwh"],
            basis="booked_today",
            simulated=entry["simulated"],
            prompt_trade=True,
            venue=venue,
        )))
    return out


def _terminal_hubs(session) -> dict[str, str]:
    from eurogas_nexus.db.models import LngTerminalTermsRecord

    return {str(row.name).lower(): str(row.hub).upper()
            for row in session.query(LngTerminalTermsRecord).all()}


def _cargo_send_out(session, slot, now: datetime) -> dict[str, float] | None:
    """MWh by gas day from the cargo plan (``application/lng_in_transit``) of the firm cargo
    the slot holds, sent out from berth; None when the slot holds no cargo or no plan can be
    built for it (the slot's own rate is then the line, labelled as an assumption)."""

    if not slot.cargo_id:
        return None
    from eurogas_nexus.application.lng_in_transit import CargoPlanError, send_out_plan

    try:
        plan, slot_id = send_out_plan(session, slot.cargo_id, now=now)
    except CargoPlanError:
        return None
    if slot_id != slot.slot_id:
        return {}  # the cargo is planned at another slot: none of it leaves this one
    out: dict[str, float] = {}
    for label, mwh in plan.send_out:
        out[label] = out.get(label, 0.0) + mwh
    return out


def lng_lines(session, days: list[date], visible,
              now: datetime | None = None) -> list[tuple[date, GasDayLine]]:
    """Send-out from the regas slots the firm holds.

    A slot with a firm cargo takes the cargo plan's send-out by gas day (from berth, so a
    cargo that misses the window sends out nothing on its days), basis ``cargo_plan``. A slot
    without a cargo spreads its send-out rate over the gas days its window covers, basis
    ``slot``: an assumption, labelled so.
    """

    from eurogas_nexus.db.models.lng_positions import RegasSlotRecord
    from eurogas_nexus.domain.market.gas_day import gas_day_start_for_date
    from eurogas_nexus.domain.ontology.identity import resolve_hub

    now = now or datetime.now(UTC)
    first = gas_day_start_for_date(days[0])
    last = gas_day_start_for_date(days[-1] + timedelta(days=1))
    terminals = _terminal_hubs(session)
    out = []
    rows = session.query(RegasSlotRecord).filter(RegasSlotRecord.book_id.is_not(None)).all()
    for slot in rows:
        if visible is not None and slot.book_id not in visible:
            continue
        start, end = _aware(slot.window_start_utc), _aware(slot.window_end_utc)
        if start is None or end is None or not slot.send_out_gwh_d:
            continue
        in_window = not (end <= first or start >= last)
        planned = _cargo_send_out(session, slot, now) if slot.cargo_id else None
        if planned is None and not in_window:
            continue
        if planned is not None and not in_window and not any(
                day.isoformat() in planned for day in days):
            continue
        hub = terminals.get(str(slot.terminal_name).lower()) or resolve_hub(slot.terminal_name).hub
        if hub is None:
            continue
        for day in days:
            day_start = gas_day_start_for_date(day)
            day_end = gas_day_start_for_date(day + timedelta(days=1))
            overlap = (min(end, day_end) - max(start, day_start)).total_seconds()
            if planned is not None:
                if overlap <= 0 and day.isoformat() not in planned:
                    continue
                out.append((day, GasDayLine(
                    ref=f"lng:{slot.slot_id}",
                    hub=hub,
                    book_id=slot.book_id or "",
                    direction=IN,
                    kind="lng_send_out",
                    label=str(slot.terminal_name),
                    mwh=planned.get(day.isoformat(), 0.0),
                    basis="cargo_plan",
                    simulated=str(slot.source_system).endswith("_Sim"),
                    source_ref=f"cargo:{slot.cargo_id}",
                )))
                continue
            if overlap <= 0:
                continue
            share = overlap / (day_end - day_start).total_seconds()
            out.append((day, GasDayLine(
                ref=f"lng:{slot.slot_id}",
                hub=hub,
                book_id=slot.book_id or "",
                direction=IN,
                kind="lng_send_out",
                label=str(slot.terminal_name),
                mwh=float(slot.send_out_gwh_d) * 1000.0 * share,
                basis="slot",
                simulated=str(slot.source_system).endswith("_Sim"),
            )))
    return out


def schedule_lines(session, days: list[date], visible) -> list[tuple[date, GasDayLine]]:
    from eurogas_nexus.db.models import GasDayScheduleLineRecord

    rows = (
        session.query(GasDayScheduleLineRecord)
        .filter(GasDayScheduleLineRecord.gas_day.in_(days))
        .order_by(GasDayScheduleLineRecord.line_id)
        .all()
    )
    out = []
    for row in rows:
        if visible is not None and row.book_id not in visible:
            continue
        out.append((row.gas_day, GasDayLine(
            ref=f"schedule:{row.line_id}",
            hub=row.hub.upper(),
            book_id=row.book_id or "",
            direction=IN if row.direction == IN else OUT,
            kind=row.kind,
            label=row.label,
            mwh=abs(float(row.quantity_mwh)),
            basis="scheduled",
            point=row.point,
            simulated=bool(row.simulated),
        )))
    return out


def nominations_for(session, contract_ids: list[str], days: list[date]) -> dict:
    from eurogas_nexus.db.models import ContractDeliveryRecord

    if not contract_ids:
        return {}
    rows = (
        session.query(ContractDeliveryRecord)
        .filter(ContractDeliveryRecord.contract_id.in_(contract_ids))
        .filter(ContractDeliveryRecord.gas_day.in_(days))
        .all()
    )
    return {(row.contract_id, row.gas_day): float(row.nominated_mwh)
            for row in rows if row.nominated_mwh is not None}


def delegations_for(session, day: date, now: datetime, visible) -> list[Delegation]:
    from eurogas_nexus.db.models import GasDayDelegationRecord, TraderMandateRecord

    names = {row.mandate_id: row.display_name for row in session.query(TraderMandateRecord)}
    out = []
    for row in (
        session.query(GasDayDelegationRecord)
        .filter(GasDayDelegationRecord.revoked_at_utc.is_(None))
        .filter(GasDayDelegationRecord.gas_day_from <= day)
        .filter(GasDayDelegationRecord.gas_day_to >= day)
        .order_by(GasDayDelegationRecord.assigned_at_utc, GasDayDelegationRecord.delegation_id)
    ):
        until = _aware(row.until_utc)
        if until is not None and day == row.gas_day_to and until <= now:
            continue
        if visible is not None and row.book_id not in visible:
            continue
        out.append(Delegation(
            trader=row.trader, book_id=row.book_id, hub=row.hub.upper(), ref=row.line_ref,
            mwh=row.mwh_per_day, trader_name=names.get(row.mandate_id) or row.trader,
            delegation_id=row.delegation_id,
        ))
    return out


# ------------------------------------------------------------------ cut-offs and cost


def cutoffs_for(session, hub: str, day: date, now: datetime) -> list[dict[str, Any]]:
    """The day's cut-offs at the hub: declared windows for its country, else the defaults."""

    from eurogas_nexus.domain.market.hub_cutoffs import default_cutoffs, gas_day_end
    from eurogas_nexus.domain.market.nomination_windows import resolve_window_occurrence
    from eurogas_nexus.domain.ontology.markets import find_market

    market = find_market(hub)
    country = (market.country if market else "") or ""
    held: list[dict[str, Any]] = []
    if country:
        try:
            from eurogas_nexus.db.repositories.storage_nomination import (
                active_nomination_windows,
            )

            for row in active_nomination_windows(session, at_utc=now):
                if str(row.country).upper() != country.upper():
                    continue
                occurrence = resolve_window_occurrence(
                    gas_day=day, opens_at=row.opens_at, closes_at=row.closes_at)
                held.append({"key": "window", "name": row.name,
                             "at_utc": occurrence.closes_at_utc.isoformat(),
                             "basis": "held", "source": row.source_reference})
        except Exception:  # noqa: BLE001 - a malformed window must not lose the row
            held = []
    if held:
        held.append({"key": "gas_day_end", "name": None,
                     "at_utc": gas_day_end(day).isoformat(), "basis": "calendar",
                     "source": "Gas-day calendar"})
        items = held
    else:
        items = [{"key": cut.key, "name": None, "at_utc": cut.at_utc.isoformat(),
                  "basis": cut.basis, "source": cut.source} for cut in default_cutoffs(day)]
    for item in items:
        item["passed"] = datetime.fromisoformat(item["at_utc"]) <= now
    return sorted(items, key=lambda item: item["at_utc"])


def cash_out_assumption(session, books: list[str], hub: str, day: date) -> dict[str, Any] | None:
    """The approved cash-out premium and discount in the hub's currency for the hub's books."""

    from eurogas_nexus.db.repositories.commercial_assumptions import resolve_assumption_version
    from eurogas_nexus.domain.ontology.markets import quote_currency

    currency = quote_currency(hub)
    reasons = []
    found: dict[str, Any] = {}
    for book in [*books, None]:
        try:
            resolved = resolve_assumption_version(session, day=day, book_id=book)
        except Exception:  # noqa: BLE001 - no assumption store: not estimated
            return None
        if resolved is None:
            continue
        _version_id, version = resolved
        short = version.value("balancing.short_premium")
        long_ = version.value("balancing.long_discount")
        band = version.value("balancing.flat_band_pct")
        if band is not None and "flat_band_pct" not in found:
            found["flat_band_pct"] = float(band.value)
            found["band_set"] = f"{version.name} v{version.version}"
        if short is None and long_ is None:
            continue
        if any(item is not None and (item.currency or currency) != currency
               for item in (short, long_)):
            reasons.append(f"{version.name} v{version.version} is not in {currency}")
            continue
        return {
            **found,
            "set": version.name,
            "version": version.version,
            "currency": currency,
            "short_premium": None if short is None else float(short.value),
            "long_discount": None if long_ is None else float(long_.value),
        }
    return {**found, "reasons": reasons} if (reasons or found) else None


#: Within this share of the day's larger side a hub reads "balanced" unless the assumption set
#: says otherwise (``balancing.flat_band_pct``): the usual nomination tolerance of 2 %.
DEFAULT_FLAT_BAND_PCT = 2.0


def balance_band(assumption: dict[str, Any] | None, in_mwh: float, out_mwh: float) -> dict:
    """The band around zero inside which a net is rounding, not a position, and its basis."""

    pct = (assumption or {}).get("flat_band_pct")
    basis = "assumption" if pct is not None else "default"
    pct = DEFAULT_FLAT_BAND_PCT if pct is None else pct
    return {
        "pct": pct,
        "mwh": round(max(in_mwh, out_mwh) * pct / 100.0, 1),
        "basis": basis,
        "set": (assumption or {}).get("band_set"),
    }


def state_within(net_mwh: float, band: dict) -> str:
    if abs(net_mwh) <= max(band["mwh"], 0.5):
        return "balanced"
    return "long" if net_mwh > 0 else "short"


def cost_of_nothing(net_mwh: float, assumption: dict[str, Any] | None, hub: str,
                    state: str | None = None) -> dict:
    """The net left open at the assumed cash-out premium (short) or discount (long)."""

    from eurogas_nexus.domain.ontology.markets import quote_currency

    if state == "balanced" or abs(net_mwh) <= 0.5:
        return {"value": 0.0, "currency": quote_currency(hub), "basis": "balanced"}
    if not assumption or "reasons" in assumption or "set" not in assumption:
        return {"value": None, "currency": quote_currency(hub), "basis": "missing",
                "reason": "; ".join((assumption or {}).get("reasons") or [])
                or "no cash-out premium in the assumption set in force"}
    rate = assumption["long_discount"] if net_mwh > 0 else assumption["short_premium"]
    if rate is None:
        return {"value": None, "currency": assumption["currency"], "basis": "missing",
                "reason": "no cash-out premium in the assumption set in force"}
    return {
        "value": round(abs(net_mwh) * rate, 2),
        "currency": assumption["currency"],
        "rate": rate,
        "rate_unit": f"{assumption['currency']}/MWh",
        "basis": "assumption",
        "side": "long_discount" if net_mwh > 0 else "short_premium",
        "assumption_set": assumption["set"],
        "assumption_version": assumption["version"],
    }


# ------------------------------------------------------------------ the row


def _target(line: GasDayLine) -> dict[str, Any]:
    if line.prompt_trade:
        return {"mode": "desk", "task": "prices", "params": {"hub": line.hub, "view": "prompt"}}
    if line.ref.startswith("contract:"):
        return {"mode": "book", "task": "delivery",
                "params": {"contract": line.ref.split(":", 1)[1]}}
    if line.ref.startswith(("lng:",)) or line.kind.startswith("storage"):
        return {"mode": "book", "task": "planning", "params": {}}
    if line.ref.startswith("trade:"):
        return {"mode": "book", "task": "position", "params": {}}
    return {"mode": "book", "task": "delivery", "params": {}}


def _adjustment_payload(item: LineAdjustment, hub: str, day: date) -> dict[str, Any]:
    return {
        "kind": item.kind,
        "source": item.source,
        "id": item.ref,
        "version": item.version,
        "source_reference": item.source_reference,
        "asset": item.label,
        "share_out_pct": round(item.share * 100.0, 2),
        "day_share_pct": round(item.day_share * 100.0, 2),
        "quantity": native_quantity(hub, item.mwh, day),
        "simulated": item.simulated,
        "target": {"mode": "desk", "task": "events", "params": {"event": item.ref}},
    }


def _line_payload(line: GasDayLine, day: date) -> dict[str, Any]:
    return {
        "ref": line.ref,
        "direction": line.direction,
        "kind": line.kind,
        "label": line.label,
        "point": line.point,
        "basis": line.basis,
        "book_id": line.book_id,
        "quantity": native_quantity(line.hub, line.mwh, day),
        "simulated": line.simulated,
        "prompt_trade": line.prompt_trade,
        "target": _target(line),
        "source_ref": line.source_ref,
        "adjustments": [_adjustment_payload(item, line.hub, day) for item in line.adjustments],
    }


def _order(line: GasDayLine) -> tuple:
    kinds = IN_KINDS if line.direction == IN else OUT_KINDS
    return (kinds.index(line.kind) if line.kind in kinds else 99, line.prompt_trade, -line.mwh)


def hub_payload(session, balance: HubBalance, day: date, now: datetime,
                book_names: dict[str, str]) -> dict[str, Any]:
    hub = balance.hub
    lines = sorted(balance.lines, key=_order)
    done = [line for line in lines if line.prompt_trade]
    books = sorted({line.book_id for line in lines if line.book_id},
                   key=lambda book: -sum(line.mwh for line in lines if line.book_id == book))
    assumption = cash_out_assumption(session, books, hub, day)
    band = balance_band(assumption, balance.in_mwh, balance.out_mwh)
    state = state_within(balance.net_mwh, band)
    delegated = [
        {
            "ref": line.ref,
            "label": line.label,
            "direction": line.direction,
            "quantity": native_quantity(hub, mwh, day),
            "trader": item.trader,
            "trader_name": item.trader_name,
            "delegation_id": item.delegation_id,
            "book": book_names.get(item.book_id, item.book_id),
        }
        for line, mwh, item in balance.delegated
    ]
    return {
        "hub": hub,
        "state": state,
        "band": band,
        "in": native_quantity(hub, balance.in_mwh, day),
        "out": native_quantity(hub, balance.out_mwh, day),
        "net": native_quantity(hub, balance.net_mwh, day),
        "lines": [_line_payload(line, day) for line in lines],
        "done_today": {
            "trades": sum(int(line.label) for line in done if line.label.isdigit()),
            "bought": native_quantity(hub, sum(x.mwh for x in done if x.direction == IN), day),
            "sold": native_quantity(hub, sum(x.mwh for x in done if x.direction == OUT), day),
            "target": {"mode": "desk", "task": "prices", "params": {"hub": hub,
                                                                     "view": "prompt"}},
        },
        "delegated": delegated,
        "cutoffs": cutoffs_for(session, hub, day, now),
        "cost_of_nothing": cost_of_nothing(balance.net_mwh, assumption, hub, state),
        "books": [book_names.get(book, book) for book in books],
        "simulated": any(line.simulated for line in lines),
    }


@dataclass
class GasDayView:
    """One caller's lines and balances for today and tomorrow (shared by the row and the
    checklist, so both read the same scope)."""

    scope: Scope
    days: list[date]
    balances: dict[date, dict[str, HubBalance]]
    book_names: dict[str, str]
    contracts: dict[str, Any]


def gas_day_view(session, caller, *, now: datetime, inputs=None,
                 days: list[date] | None = None) -> GasDayView:
    """The caller's lines and balances per hub for ``days`` (today's and tomorrow's gas day
    unless given: the daily balance reads further days from the same lines)."""

    from eurogas_nexus.domain.market.gas_day import gas_day_label

    today = date.fromisoformat(gas_day_label(now))
    days = list(days) if days else [today, today + timedelta(days=1)]
    if inputs is None:
        from eurogas_nexus.application.position_inputs import ladder_inputs

        inputs = ladder_inputs(caller, today, today, days[-1])
    scope = scope_of(session, caller, today)
    contract_ids = [leg.reference for leg in inputs.legs if leg.kind == "physical"]
    dated = [
        *contract_lines(inputs, days, nominations_for(session, contract_ids, days),
                        active_outages(session, caller, now, days)),
        *trade_lines(inputs, days, today),
        *lng_lines(session, days, scope.visible, now),
        *schedule_lines(session, days, scope.visible),
    ]
    balances = {}
    for day in days:
        lines = [line for when, line in dated if when == day]
        delegations = delegations_for(session, day, now, scope.visible)
        balances[day] = balance_for(lines, delegations, trader=scope.trader,
                                    owned_books=scope.owned_books)
    return GasDayView(
        scope=scope,
        days=days,
        balances=balances,
        book_names={book_id: book.name for book_id, book in (inputs.books or {}).items()},
        contracts={row.contract_id: row for row in inputs.contracts},
    )


def hub_daily_balance(
    session,
    view: GasDayView,
    hub: str,
    *,
    short_premium: float | None = None,
    long_discount: float | None = None,
    flat_band_mwh: float = 0.0,
) -> list[dict[str, Any]]:
    """One hub's balance for each day of the view, from the same lines as "My gas day".

    The daily balance (``GET /api/portfolio/daily-balance``) reads this, so Today and Book >
    Delivery give one figure per hub and day (QA-T-07): ``supply`` is the physical lines net
    (contracts nominated where held, else their quantity, capped by an outage at the source;
    LNG send-out; storage and imports less offtake, injection and exports), trades by venue,
    the residual is the net, its state within the gas day's band, and its cost at the approved
    cash-out premium or discount for the hub's books. A premium or discount given here is
    entered by hand and labelled so (``basis`` ``entered``); a band given in MWh replaces the
    percentage band.
    """

    from eurogas_nexus.domain.ontology.markets import quote_currency

    hub = hub.upper()
    manual = short_premium is not None or long_discount is not None
    rows = []
    for day in view.days:
        balance = view.balances[day].get(hub) or HubBalance(hub)
        lines = sorted(balance.lines, key=_order)
        physical_in = sum(x.mwh for x in lines if x.venue is None and x.direction == IN)
        physical_out = sum(x.mwh for x in lines if x.venue is None and x.direction == OUT)
        traded = {
            f"{venue}_{side}": sum(
                x.mwh for x in lines
                if x.venue == venue and x.direction == (IN if side == "bought" else OUT))
            for venue in ("exchange", "bilateral") for side in ("bought", "sold")
        }
        books = sorted({x.book_id for x in lines if x.book_id})
        approved = cash_out_assumption(session, books, hub, day)
        band = balance_band(approved, balance.in_mwh, balance.out_mwh)
        if flat_band_mwh:
            band = {"pct": None, "mwh": round(flat_band_mwh, 1), "basis": "entered", "set": None}
        state = state_within(balance.net_mwh, band)
        assumption = approved
        if manual:
            assumption = {"set": "entered by hand", "version": None,
                          "currency": quote_currency(hub), "short_premium": short_premium,
                          "long_discount": long_discount}
        cost = cost_of_nothing(balance.net_mwh, assumption, hub, state)
        if manual and cost.get("basis") == "assumption":
            cost["basis"] = "entered"
        rows.append({
            "gas_day": day.isoformat(),
            "supply": round(physical_in - physical_out, 1) + 0.0,
            **{key: round(value, 1) for key, value in traded.items()},
            "residual_mwh": round(balance.net_mwh, 1) + 0.0,
            "state": state,
            "cash_out_cost": cost.get("value"),
            "physical_in_mwh": round(physical_in, 1),
            "physical_out_mwh": round(physical_out, 1),
            "net": native_quantity(hub, balance.net_mwh, day),
            "band": band,
            "cash_out": cost,
            "lines": [_line_payload(line, day) for line in lines],
            "simulated": any(line.simulated for line in lines),
        })
    return rows


def my_gas_day(session, caller, *, now: datetime, inputs=None,
               view: GasDayView | None = None) -> dict[str, Any]:
    """The "My gas day" row for this caller: today's and tomorrow's gas day per hub."""

    view = view or gas_day_view(session, caller, now=now, inputs=inputs)
    out_days = []
    for offset, day in enumerate(view.days):
        balances = view.balances[day]
        hubs = [hub_payload(session, balances[hub], day, now, view.book_names)
                for hub in sorted(balances, key=lambda h: -abs(balances[h].net_mwh))]
        out_days.append({
            "gas_day": day.isoformat(),
            "which": "today" if offset == 0 else "tomorrow",
            "hours": gas_day_hours(day),
            "hubs": hubs,
        })
    populated = any(item["hubs"] for item in out_days)
    simulated = any(hub["simulated"] for item in out_days for hub in item["hubs"])
    return {
        "key": "gas_day",
        "title": "My gas day",
        "scope": view.scope.payload(),
        "days": out_days,
        "simulated": simulated,
        "populated": populated,
        "empty": None if populated else {
            "code": "no_gas_day_lines",
            "reason": "Nothing to clear today or tomorrow in the books you hold",
            "action": "Deliveries appear once contracts, trades or the schedule are imported",
        },
        "execution": "none: decision support only; nominations and trades are made elsewhere",
    }
