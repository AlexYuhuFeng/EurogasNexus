"""A cargo in transit as one linked object: voyage, slot, send-out, hub months and hedges.

A desk that has bought a US cargo for Europe manages one chain, not separate screens:

    ETA -> berth time (slot window) -> boil-off -> delivered energy -> send-out by gas day
        -> hub exposure by delivery month -> hedge cover per month -> what to do

When the ship's schedule changes, the whole chain is recomputed and the two plans are
compared. The comparison says which delivery month gained or lost gas, how much of the
short hedge now sits in the wrong month (a roll), whether a month's futures contract has
already stopped trading (so the gap has to be covered at short notice in the spot market),
and whether the slot is still reachable.

Conventions (see docs/engineering/Commercial-Intelligence-V3/12_LNG_CARGO_IN_TRANSIT.md):

* Energy is MWh. Physical length is positive, a short hedge is negative.
* Exposure is allocated by the terminal's send-out profile, not by the arrival date: one
  cargo's gas leaves the terminal over about ten days and can straddle two months.
* Send-out starts when the ship berths and runs at the slot's send-out rate until the
  delivered energy is gone. Delivered energy is the loaded energy less boil-off for every
  day from loading to berth (waiting at anchor boils off too) and less the terminal's
  gas-in-kind share.
* Arriving before the slot window means waiting at anchor until it opens; arriving after
  it closes means the slot is missed and no send-out can be assumed.
* The month's futures contract stops trading two business days before the month starts
  (the ICE Endex TTF rule, which uses UK business days; weekends are skipped and any
  holidays the caller passes are skipped too). After that, a residual in that month can
  only be closed in balance-of-month or day-ahead products.

Everything here is a suggestion for a person to act on. Nothing is executed or nominated.
Pure: no I/O, no clock; the caller passes ``now``.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

from eurogas_nexus.domain.market.gas_day import (
    DEFAULT_GAS_DAY_CALENDAR,
    gas_day_interval_utc,
    gas_day_label,
)

#: Residual below which a month counts as balanced (MWh). A cargo is about 1 TWh, so this is
#: noise from rounding of send-out hours, not a position.
BALANCED_MWH = 1.0
#: Default hours a terminal takes to start sending out once the ship is alongside. Zero keeps
#: the plan simple; a terminal with a known lag can pass its own.
_HOURS_PER_DAY = 24.0


class InTransitError(ValueError):
    """An input a cargo plan cannot be built from."""


@dataclass(frozen=True)
class SlotWindow:
    """The regas slot the cargo is aimed at: its arrival window and send-out rate."""

    slot_id: str
    terminal: str
    hub: str
    window_start_utc: datetime
    window_end_utc: datetime
    send_out_mwh_per_day: float
    #: Share of the delivered energy the terminal keeps as fuel, in percent (e.g. 1.3).
    gas_in_kind_pct: float = 0.0

    def __post_init__(self) -> None:
        _aware(self.window_start_utc, "window_start_utc")
        _aware(self.window_end_utc, "window_end_utc")
        if self.window_end_utc <= self.window_start_utc:
            raise InTransitError("the slot window must end after it starts")
        if self.send_out_mwh_per_day <= 0:
            raise InTransitError("send_out_mwh_per_day must be positive")
        if not 0 <= self.gas_in_kind_pct < 100:
            raise InTransitError("gas_in_kind_pct must be within 0-100")


@dataclass(frozen=True)
class HedgeLeg:
    """A hedge the desk holds against the cargo: hub, delivery month and signed MWh."""

    hub: str
    month: str  # YYYY-MM
    mwh: float  # a short is negative
    reference: str = ""

    def __post_init__(self) -> None:
        _month_start(self.month)


@dataclass(frozen=True)
class CargoInTransit:
    """What the desk knows about the cargo now."""

    cargo_id: str
    loaded_mwh: float
    loaded_at_utc: datetime
    eta_utc: datetime
    #: Boil-off in percent of the cargo per day, from loading to berth.
    boil_off_pct_per_day: float
    slot: SlotWindow | None
    hedges: tuple[HedgeLeg, ...] = ()
    #: Hours the ship waits for a berth after arriving inside the window (terminal congestion).
    berth_delay_hours: float = 0.0
    #: Laytime allowed before demurrage runs, in hours, and the demurrage rate per day.
    laytime_hours: float = 36.0
    demurrage_per_day: float | None = None
    demurrage_currency: str = "USD"

    def __post_init__(self) -> None:
        _aware(self.loaded_at_utc, "loaded_at_utc")
        _aware(self.eta_utc, "eta_utc")
        if self.loaded_mwh <= 0:
            raise InTransitError("loaded_mwh must be positive")
        if self.eta_utc < self.loaded_at_utc:
            raise InTransitError("the ETA cannot be before loading")
        if not 0 <= self.boil_off_pct_per_day < 1:
            raise InTransitError("boil_off_pct_per_day must be within 0-1 %/day")
        if self.berth_delay_hours < 0 or self.laytime_hours < 0:
            raise InTransitError("berth delay and laytime must not be negative")


@dataclass(frozen=True)
class MonthCover:
    """Exposure, hedge and what is left in one hub month."""

    hub: str
    month: str
    physical_mwh: float
    hedge_mwh: float
    last_trading_day: date
    trading: bool  # the month's futures contract still trades

    @property
    def net_mwh(self) -> float:
        return self.physical_mwh + self.hedge_mwh

    @property
    def cover_ratio(self) -> float | None:
        if abs(self.physical_mwh) < BALANCED_MWH:
            return None
        return -self.hedge_mwh / self.physical_mwh

    def as_dict(self) -> dict[str, object]:
        ratio = self.cover_ratio
        return {
            "hub": self.hub,
            "month": self.month,
            "physical_mwh": round(self.physical_mwh, 1),
            "hedge_mwh": round(self.hedge_mwh, 1),
            "net_mwh": round(self.net_mwh, 1),
            "cover_ratio": None if ratio is None else round(ratio, 4),
            "last_trading_day": self.last_trading_day.isoformat(),
            "trading": self.trading,
        }


@dataclass(frozen=True)
class Suggestion:
    """One thing the desk could do. Advisory: never executed or nominated by the product."""

    kind: str  # roll | sell | buy_back | short_notice | find_slot | demurrage | deadline
    text: str
    hub: str | None = None
    from_month: str | None = None
    to_month: str | None = None
    mwh: float | None = None
    due_utc: datetime | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "text": self.text,
            "hub": self.hub,
            "from_month": self.from_month,
            "to_month": self.to_month,
            "mwh": None if self.mwh is None else round(self.mwh, 1),
            "due_utc": None if self.due_utc is None else self.due_utc.isoformat(),
        }


@dataclass(frozen=True)
class CargoPlan:
    """The cargo's chain as it stands: berth, energy, send-out, months and suggestions."""

    cargo_id: str
    slot_status: str  # no_slot | on_time | waiting | missed
    berth_utc: datetime | None
    wait_hours: float
    days_to_berth: float
    boil_off_mwh: float
    #: Kept by the terminal as fuel: 0 when there is no berth (nothing is unloaded).
    gas_in_kind_mwh: float
    #: Sent out from berth (the send-out by gas day adds up to it): 0 when there is no berth.
    delivered_mwh: float
    send_out: tuple[tuple[str, float], ...]  # (gas day label, MWh)
    send_out_end_utc: datetime | None
    months: tuple[MonthCover, ...]
    demurrage_hours: float
    demurrage_cost: float | None
    suggestions: tuple[Suggestion, ...] = field(default=())
    #: Energy aboard when the ship arrives: loaded less boil-off up to the ETA. With no berth
    #: it is the cargo as it stands (loaded = boil-off + energy at ETA); with a berth, waiting
    #: and berth delay boil off more (loaded = boil-off + gas in kind + delivered).
    energy_at_eta_mwh: float = 0.0

    def month(self, hub: str, month: str) -> MonthCover | None:
        for cover in self.months:
            if cover.hub == hub and cover.month == month:
                return cover
        return None

    def as_dict(self) -> dict[str, object]:
        return {
            "cargo_id": self.cargo_id,
            "slot_status": self.slot_status,
            "berth_utc": None if self.berth_utc is None else self.berth_utc.isoformat(),
            "wait_hours": round(self.wait_hours, 1),
            "days_to_berth": round(self.days_to_berth, 2),
            "boil_off_mwh": round(self.boil_off_mwh, 1),
            "gas_in_kind_mwh": round(self.gas_in_kind_mwh, 1),
            "delivered_mwh": round(self.delivered_mwh, 1),
            "energy_at_eta_mwh": round(self.energy_at_eta_mwh, 1),
            "send_out": [{"gas_day": day, "mwh": round(mwh, 1)} for day, mwh in self.send_out],
            "send_out_end_utc": (
                None if self.send_out_end_utc is None else self.send_out_end_utc.isoformat()
            ),
            "months": [cover.as_dict() for cover in self.months],
            "demurrage_hours": round(self.demurrage_hours, 1),
            "demurrage_cost": (
                None if self.demurrage_cost is None else round(self.demurrage_cost, 2)
            ),
            "suggestions": [item.as_dict() for item in self.suggestions],
        }


# --- calendar -------------------------------------------------------------------------


def _aware(value: datetime, name: str) -> None:
    if value.tzinfo is None:
        raise InTransitError(f"{name} must carry a time zone")


def _month_start(month: str) -> date:
    try:
        year, number = month.split("-")
        return date(int(year), int(number), 1)
    except (ValueError, TypeError) as exc:
        raise InTransitError(f"month {month!r} is not YYYY-MM") from exc


def _month_label(day: date) -> str:
    return f"{day.year:04d}-{day.month:02d}"


def last_trading_day(month: str, holidays: Iterable[date] = ()) -> date:
    """The last day the month's futures contract trades: two business days before it starts."""

    blocked = frozenset(holidays)
    day = _month_start(month)
    counted = 0
    while counted < 2:
        day -= timedelta(days=1)
        if day.weekday() < 5 and day not in blocked:
            counted += 1
    return day


def _still_trading(month: str, now: datetime, holidays: Iterable[date]) -> bool:
    return now.astimezone(UTC).date() <= last_trading_day(month, holidays)


# --- the chain ------------------------------------------------------------------------


def _send_out(
    start: datetime, delivered_mwh: float, rate_mwh_per_day: float, calendar: str
) -> tuple[list[tuple[str, float]], datetime]:
    """Split the delivered energy across gas days at a flat hourly rate from ``start``."""

    rate_per_hour = rate_mwh_per_day / _HOURS_PER_DAY
    left = delivered_mwh
    cursor = start
    days: list[tuple[str, float]] = []
    while left > 1e-9:
        _day_start, day_end = gas_day_interval_utc(cursor, calendar)
        hours = (day_end - cursor).total_seconds() / 3600
        amount = min(left, rate_per_hour * hours)
        days.append((gas_day_label(cursor, calendar), amount))
        left -= amount
        if left <= 1e-9:
            cursor = cursor + timedelta(hours=amount / rate_per_hour)
            break
        cursor = day_end
    return days, cursor


def build_plan(
    cargo: CargoInTransit,
    *,
    now: datetime,
    holidays: Iterable[date] = (),
    calendar: str = DEFAULT_GAS_DAY_CALENDAR,
) -> CargoPlan:
    """Recompute the whole chain for the cargo as it stands at ``now``."""

    _aware(now, "now")
    slot = cargo.slot
    holidays = tuple(holidays)
    if slot is None:
        status, berth, wait = "no_slot", None, 0.0
    elif cargo.eta_utc > slot.window_end_utc:
        status, berth, wait = "missed", None, 0.0
    elif cargo.eta_utc < slot.window_start_utc:
        berth = slot.window_start_utc + timedelta(hours=cargo.berth_delay_hours)
        status = "waiting"
        wait = (berth - cargo.eta_utc).total_seconds() / 3600
    else:
        berth = cargo.eta_utc + timedelta(hours=cargo.berth_delay_hours)
        status = "on_time"
        wait = cargo.berth_delay_hours

    # Boil-off runs until the ship is alongside; with no berth, until the ETA.
    until = berth if berth is not None else cargo.eta_utc
    days_to_berth = (until - cargo.loaded_at_utc).total_seconds() / 86400
    boil_off = cargo.loaded_mwh * cargo.boil_off_pct_per_day / 100 * days_to_berth
    at_berth = max(cargo.loaded_mwh - boil_off, 0.0)
    to_eta = (cargo.eta_utc - cargo.loaded_at_utc).total_seconds() / 86400
    at_eta = max(cargo.loaded_mwh * (1 - cargo.boil_off_pct_per_day / 100 * to_eta), 0.0)
    # Gas in kind is taken from what is unloaded: with no berth nothing is, and nothing is
    # delivered either (the energy stays aboard: ``energy_at_eta_mwh``).
    berthed = berth is not None and slot is not None
    in_kind = at_berth * (slot.gas_in_kind_pct / 100) if berthed else 0.0
    delivered = at_berth - in_kind if berthed else 0.0

    send_out: list[tuple[str, float]] = []
    send_out_end = None
    if berth is not None and slot is not None:
        send_out, send_out_end = _send_out(
            berth, delivered, slot.send_out_mwh_per_day, calendar
        )

    # Physical exposure by (hub, month) from the send-out profile.
    physical: dict[tuple[str, str], float] = {}
    if slot is not None:
        for label, mwh in send_out:
            key = (slot.hub, label[:7])
            physical[key] = physical.get(key, 0.0) + mwh
    hedged: dict[tuple[str, str], float] = {}
    for leg in cargo.hedges:
        key = (leg.hub, leg.month)
        hedged[key] = hedged.get(key, 0.0) + leg.mwh
    months = tuple(
        MonthCover(
            hub=hub,
            month=month,
            physical_mwh=physical.get((hub, month), 0.0),
            hedge_mwh=hedged.get((hub, month), 0.0),
            last_trading_day=last_trading_day(month, holidays),
            trading=_still_trading(month, now, holidays),
        )
        for hub, month in sorted(set(physical) | set(hedged), key=lambda key: (key[1], key[0]))
    )

    demurrage_hours = 0.0
    demurrage_cost = None
    if status == "on_time":
        demurrage_hours = max(0.0, cargo.berth_delay_hours - cargo.laytime_hours)
        if cargo.demurrage_per_day is not None:
            demurrage_cost = demurrage_hours / _HOURS_PER_DAY * cargo.demurrage_per_day

    plan = CargoPlan(
        cargo_id=cargo.cargo_id,
        slot_status=status,
        berth_utc=berth,
        wait_hours=wait,
        days_to_berth=days_to_berth,
        boil_off_mwh=boil_off,
        gas_in_kind_mwh=in_kind,
        delivered_mwh=delivered,
        energy_at_eta_mwh=at_eta,
        send_out=tuple(send_out),
        send_out_end_utc=send_out_end,
        months=months,
        demurrage_hours=demurrage_hours,
        demurrage_cost=demurrage_cost,
    )
    return _with_suggestions(plan, cargo, now=now, holidays=holidays)


def _fmt_mwh(mwh: float) -> str:
    return f"{abs(mwh):,.0f} MWh"


def _with_suggestions(
    plan: CargoPlan, cargo: CargoInTransit, *, now: datetime, holidays: Sequence[date]
) -> CargoPlan:
    items: list[Suggestion] = []
    slot = cargo.slot
    if plan.slot_status == "missed" and slot is not None:
        hedged = sum(leg.mwh for leg in cargo.hedges)
        items.append(
            Suggestion(
                kind="find_slot",
                text=(
                    f"ETA {cargo.eta_utc:%d %b %H:%M} UTC is after the {slot.terminal} slot "
                    f"window closes ({slot.window_end_utc:%d %b %H:%M} UTC). Find a new slot "
                    "or re-run the destination choice; "
                    + (
                        f"{_fmt_mwh(hedged)} of hedges no longer has gas behind it."
                        if abs(hedged) >= BALANCED_MWH
                        else "no hedge is attached."
                    )
                ),
                hub=slot.hub,
                due_utc=slot.window_end_utc,
            )
        )
    elif plan.slot_status == "no_slot":
        items.append(
            Suggestion(
                kind="find_slot",
                text="No regas slot is attached, so the gas has no hub month yet.",
            )
        )

    # Pair months with too much hedge against months with too little, within one hub, in
    # date order: that is a roll (a time-spread trade), not two separate trades.
    by_hub: dict[str, list[MonthCover]] = {}
    for cover in plan.months:
        by_hub.setdefault(cover.hub, []).append(cover)
    for hub, covers in by_hub.items():
        residual = {cover.month: cover.net_mwh for cover in covers}
        trading = {cover.month: cover.trading for cover in covers}
        over = [m for m in sorted(residual) if residual[m] < -BALANCED_MWH and trading[m]]
        under = [m for m in sorted(residual) if residual[m] > BALANCED_MWH and trading[m]]
        for source in over:
            for target in under:
                if residual[source] >= -BALANCED_MWH:
                    break
                if residual[target] <= BALANCED_MWH:
                    continue
                amount = min(-residual[source], residual[target])
                items.append(
                    Suggestion(
                        kind="roll",
                        text=(
                            f"Roll {_fmt_mwh(amount)} of {hub} short from {source} to "
                            f"{target}: the gas now leaves the terminal in {target}."
                        ),
                        hub=hub,
                        from_month=source,
                        to_month=target,
                        mwh=amount,
                        due_utc=_close_of(source, holidays),
                    )
                )
                residual[source] += amount
                residual[target] -= amount
        for month in sorted(residual):
            left = residual[month]
            if abs(left) < BALANCED_MWH:
                continue
            if not trading[month]:
                items.append(
                    Suggestion(
                        kind="short_notice",
                        text=(
                            f"The {hub} {month} contract has stopped trading. "
                            + (
                                f"Buy {_fmt_mwh(left)} in day-ahead or balance-of-month to "
                                "meet the short futures delivery."
                                if left < 0
                                else f"Sell {_fmt_mwh(left)} in day-ahead or balance-of-month "
                                "as the gas is sent out."
                            )
                        ),
                        hub=hub,
                        from_month=month,
                        mwh=left,
                    )
                )
            elif left > 0:
                items.append(
                    Suggestion(
                        kind="sell",
                        text=f"{_fmt_mwh(left)} of {hub} {month} is not hedged.",
                        hub=hub,
                        from_month=month,
                        mwh=left,
                        due_utc=_close_of(month, holidays),
                    )
                )
            else:
                items.append(
                    Suggestion(
                        kind="buy_back",
                        text=(
                            f"{hub} {month} is over-hedged by {_fmt_mwh(left)}: "
                            "no gas leaves the terminal against it."
                        ),
                        hub=hub,
                        from_month=month,
                        mwh=left,
                        due_utc=_close_of(month, holidays),
                    )
                )

    if plan.demurrage_hours > 0:
        cost = (
            ""
            if plan.demurrage_cost is None
            else f", about {plan.demurrage_cost:,.0f} {cargo.demurrage_currency}"
        )
        items.append(
            Suggestion(
                kind="demurrage",
                text=(
                    f"The berth delay runs {plan.demurrage_hours:.0f} h past laytime{cost}."
                ),
            )
        )

    # The next futures expiry that still matters for this cargo.
    upcoming = [
        cover
        for cover in plan.months
        if cover.trading and abs(cover.physical_mwh) + abs(cover.hedge_mwh) >= BALANCED_MWH
    ]
    if upcoming:
        first = min(upcoming, key=lambda cover: cover.last_trading_day)
        items.append(
            Suggestion(
                kind="deadline",
                text=(
                    f"{first.hub} {first.month} stops trading at the close on "
                    f"{first.last_trading_day:%a %d %b}."
                ),
                hub=first.hub,
                from_month=first.month,
                due_utc=_close_of(first.month, holidays),
            )
        )

    return CargoPlan(**{**plan.__dict__, "suggestions": tuple(items)})


def _close_of(month: str, holidays: Sequence[date]) -> datetime:
    """End of the last trading day, as a UTC midnight boundary (a deadline, not a fixing)."""

    day = last_trading_day(month, holidays)
    return datetime(day.year, day.month, day.day, tzinfo=UTC) + timedelta(days=1)


# --- what changed ---------------------------------------------------------------------


@dataclass(frozen=True)
class MonthShift:
    hub: str
    month: str
    physical_before: float
    physical_after: float

    @property
    def change_mwh(self) -> float:
        return self.physical_after - self.physical_before

    def as_dict(self) -> dict[str, object]:
        return {
            "hub": self.hub,
            "month": self.month,
            "physical_before_mwh": round(self.physical_before, 1),
            "physical_after_mwh": round(self.physical_after, 1),
            "change_mwh": round(self.change_mwh, 1),
        }


@dataclass(frozen=True)
class PlanChange:
    """What a schedule change did to the cargo's chain."""

    before: CargoPlan
    after: CargoPlan
    months: tuple[MonthShift, ...]

    @property
    def boil_off_change_mwh(self) -> float:
        return self.after.boil_off_mwh - self.before.boil_off_mwh

    @property
    def delivered_change_mwh(self) -> float:
        return self.after.delivered_mwh - self.before.delivered_mwh

    def headline(self) -> str:
        if self.before.slot_status != "missed" and self.after.slot_status == "missed":
            return "The new ETA misses the slot window."
        moved = sum(shift.change_mwh for shift in self.months if shift.change_mwh > 0)
        if moved >= BALANCED_MWH:
            target = max(self.months, key=lambda shift: shift.change_mwh)
            return f"{_fmt_mwh(moved)} of send-out moves into {target.hub} {target.month}."
        if abs(self.delivered_change_mwh) >= BALANCED_MWH:
            return f"Delivered energy changes by {self.delivered_change_mwh:+,.0f} MWh."
        return "The change leaves the hub months as they were."

    def as_dict(self) -> dict[str, object]:
        return {
            "headline": self.headline(),
            "slot_status_before": self.before.slot_status,
            "slot_status_after": self.after.slot_status,
            "boil_off_change_mwh": round(self.boil_off_change_mwh, 1),
            "delivered_change_mwh": round(self.delivered_change_mwh, 1),
            "months": [shift.as_dict() for shift in self.months],
            "before": self.before.as_dict(),
            "after": self.after.as_dict(),
        }


def compare(before: CargoPlan, after: CargoPlan) -> PlanChange:
    keys = sorted(
        {(cover.hub, cover.month) for cover in before.months}
        | {(cover.hub, cover.month) for cover in after.months},
        key=lambda key: (key[1], key[0]),
    )
    shifts = []
    for hub, month in keys:
        was = before.month(hub, month)
        now = after.month(hub, month)
        shifts.append(
            MonthShift(
                hub=hub,
                month=month,
                physical_before=0.0 if was is None else was.physical_mwh,
                physical_after=0.0 if now is None else now.physical_mwh,
            )
        )
    return PlanChange(before=before, after=after, months=tuple(shifts))
