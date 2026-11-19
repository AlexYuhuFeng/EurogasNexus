"""Forward balance: supply and demand dated forward, storage as the balancing item.

The desk cannot forecast price, but it can forecast volumes; the forward curve is the
market's price forecast and is shown beside this only for reference. This module turns
the north-west Europe balance (``domain.fundamentals.balance``) into a forward view a
desk reads in one line ("tighter than normal by X GWh/d, mainly because ...") and can
check: every line says where it comes from and what kind of number it is, every figure
carries its error, and the same method is run over the past year against what happened.

Quantities are GWh per gas day. "Demand" here is the region's call on Norwegian pipeline
gas, LNG and storage (``call``): consumption net of domestic production and other pipeline
imports, which change slowly and sit inside the call. Supply minus demand is therefore
minus the storage draw: a negative gap is gas the region must take from storage.

Methods (each output line records its own):

- **Daily, D+1 to D+14.** Demand: the same days' measured call in earlier years
  (``seasonal normal``) plus how far the last 14 days ran from their own normal
  (``domain.fundamentals.balance.forecast_balance``); this assumes normal weather from
  here on. Norway: the 7-day average landing minus announced unavailable capacity (REMIT)
  on each date. LNG: the 14-day average send-out. Storage: the residual.
- **Monthly, M+1 to M+3.** Demand: ``a + b·HDD`` fitted on the months the product holds
  (monthly mean call against the region's Eurostat heating degree days per day), at the
  month's 30-year normal HDD. Norway and LNG as above, outages averaged over the month.
- **Range.** Daily: ± the method's own mean absolute error at that horizon over the past
  year (backtest). Monthly: ± one standard deviation of the month's HDD over 30 years,
  times ``b``, combined with the fit's residual. Outage uncertainty is not in the range.
- **What-if.** A temperature shift of x °C moves each day's HDD by −x (never below
  zero) and demand by ``b`` per HDD; an added outage removes its GWh/d from its supply line
  on its dates. Storage absorbs both.

This is a volume balance, not a price forecast.
"""

from __future__ import annotations

import calendar
import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from statistics import mean, pstdev

from eurogas_nexus.domain.fundamentals.balance import (
    BalanceHistoryDay,
    forecast_balance,
)

DAILY_HORIZON = 14
MONTHS_AHEAD = 3
BACKTEST_HORIZONS = (1, 7, 14)
#: Origins of the daily backtest are this many days apart over the past year.
BACKTEST_STEP_DAYS = 7
#: A month counts in the demand fit when the history holds at least this many of its days.
MIN_DAYS_IN_MONTH = 25
#: Below this many fitted months the monthly demand says it rests on too little history.
MIN_FIT_MONTHS = 6
#: Within this many GWh/d of normal the balance is called "about normal".
NORMAL_BAND_GWH = 25.0
NOT_A_PRICE_FORECAST = (
    "A volume balance: supply and demand dated forward, storage taking the difference. "
    "It is not a price forecast; the forward curve is shown beside it for reference only."
)

#: Input classes, weakest last; a figure's class is that of its weakest input.
INPUT_CLASSES = ("observed", "scheduled", "forecast", "assumption", "manual")


def weakest(classes: Iterable[str]) -> str:
    ranked = [INPUT_CLASSES.index(c) for c in classes if c in INPUT_CLASSES]
    return INPUT_CLASSES[max(ranked)] if ranked else "assumption"


# ----------------------------------------------------------------------------- weather


@dataclass(frozen=True)
class HddReference:
    """Monthly regional HDD (per day of the month) from the shipped Eurostat reference."""

    per_day: Mapping[str, float]  # "YYYY-MM" -> region HDD per day
    first_month: str
    last_month: str

    @classmethod
    def from_table(cls, table: Mapping) -> HddReference:
        months = list(table["months"])
        weights = table["weights"]
        per_day: dict[str, float] = {}
        for index, month in enumerate(months):
            year, mon = int(month[:4]), int(month[5:7])
            total = sum(
                weights[code] * table["monthly_hdd"][code][index] for code in weights
            ) / sum(weights.values())
            per_day[month] = total / calendar.monthrange(year, mon)[1]
        return cls(per_day=per_day, first_month=months[0], last_month=months[-1])

    def normal(self, month_of_year: int, years: int = 30) -> tuple[float, float, int]:
        """Mean and standard deviation of HDD per day for a calendar month (last N years)."""

        values = [v for k, v in sorted(self.per_day.items()) if int(k[5:7]) == month_of_year]
        values = values[-years:]
        return mean(values), (pstdev(values) if len(values) > 1 else 0.0), len(values)

    def normal_on(self, day: date) -> float:
        """Normal HDD per day, interpolated between mid-month normals."""

        mid = date(day.year, day.month, 15)
        other = (mid.replace(day=1) - timedelta(days=1) if day < mid
                 else (mid.replace(day=28) + timedelta(days=10)))
        other_mid = date(other.year, other.month, 15)
        here, there = self.normal(day.month)[0], self.normal(other_mid.month)[0]
        span = abs((other_mid - mid).days)
        weight = abs((day - mid).days) / span if span else 0.0
        return here * (1 - weight) + there * weight


def hdd_change(normal_hdd: float, shift_c: float) -> float:
    """HDD change per day when the temperature runs ``shift_c`` °C away from normal."""

    if shift_c >= 0:
        return -min(shift_c, normal_hdd)
    return -shift_c


@dataclass(frozen=True)
class DemandFit:
    intercept: float
    slope_per_hdd: float
    r2: float
    months: int
    residual_std: float
    first_month: str | None
    last_month: str | None

    def demand(self, hdd_per_day: float) -> float:
        return self.intercept + self.slope_per_hdd * hdd_per_day

    def as_dict(self) -> dict[str, object]:
        return {
            "formula": "demand = a + b x HDD per day (monthly means)",
            "a_gwh_d": round(self.intercept, 1),
            "b_gwh_d_per_hdd": round(self.slope_per_hdd, 2),
            "r2": round(self.r2, 3),
            "months": self.months,
            "residual_std_gwh_d": round(self.residual_std, 1),
            "fitted_from": self.first_month,
            "fitted_to": self.last_month,
        }


def monthly_means(history: Sequence[BalanceHistoryDay]) -> dict[str, float]:
    """Mean call per month over the months the history holds nearly whole."""

    buckets: dict[str, list[float]] = {}
    for h in history:
        buckets.setdefault(f"{h.day:%Y-%m}", []).append(h.call_gwh)
    return {m: mean(v) for m, v in buckets.items() if len(v) >= MIN_DAYS_IN_MONTH}


def fit_demand(
    history: Sequence[BalanceHistoryDay], hdd: HddReference, *, before: str | None = None
) -> DemandFit | None:
    """Least squares of monthly mean call on the month's HDD per day."""

    pairs = [
        (hdd.per_day[month], value)
        for month, value in sorted(monthly_means(history).items())
        if month in hdd.per_day and (before is None or month < before)
    ]
    if len(pairs) < 3:
        return None
    xs, ys = [p[0] for p in pairs], [p[1] for p in pairs]
    mx, my = mean(xs), mean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return None
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True)) / sxx
    intercept = my - slope * mx
    residuals = [y - (intercept + slope * x) for x, y in zip(xs, ys, strict=True)]
    sst = sum((y - my) ** 2 for y in ys)
    months = sorted(m for m in monthly_means(history) if m in hdd.per_day
                    and (before is None or m < before))
    return DemandFit(
        intercept=intercept,
        slope_per_hdd=slope,
        r2=1 - sum(r * r for r in residuals) / sst if sst else 0.0,
        months=len(pairs),
        residual_std=math.sqrt(sum(r * r for r in residuals) / max(1, len(pairs) - 2)),
        first_month=months[0] if months else None,
        last_month=months[-1] if months else None,
    )


# ----------------------------------------------------------------------------- inputs


@dataclass(frozen=True)
class SupplyOutage:
    """Unavailable capacity on a supply line between two dates (end exclusive)."""

    line: str  # "norway" | "lng"
    start: date
    end: date | None
    gwh_d: float
    source: str = "REMIT"

    def on(self, day: date) -> bool:
        return self.start <= day and (self.end is None or day < self.end)


@dataclass(frozen=True)
class StorageBand:
    """The storage fill's range on each day of the gas year (``storage_history``)."""

    low: Sequence[float | None]
    high: Sequence[float | None]
    mean: Sequence[float | None]
    label: str | None

    def on(self, index: int) -> tuple[float | None, float | None, float | None]:
        if not 0 <= index < len(self.mean):
            return None, None, None
        return self.low[index], self.high[index], self.mean[index]


@dataclass(frozen=True)
class Overrides:
    """Inputs a user set by hand; the result names each one it used."""

    temperature_shift_c: float = 0.0
    norway_gwh_d: float | None = None
    lng_gwh_d: float | None = None
    added_outage: SupplyOutage | None = None

    def names(self) -> list[str]:
        named = []
        if self.temperature_shift_c:
            named.append("temperature_shift_c")
        if self.norway_gwh_d is not None:
            named.append("norway_gwh_d")
        if self.lng_gwh_d is not None:
            named.append("lng_gwh_d")
        if self.added_outage is not None:
            named.append("added_outage")
        return named


@dataclass
class ForwardBalance:
    as_of: date | None
    daily: list[dict] = field(default_factory=list)
    monthly: list[dict] = field(default_factory=list)
    headline: dict | None = None
    demand_fit: DemandFit | None = None
    backtest: dict = field(default_factory=dict)
    target: dict | None = None
    overridden: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ----------------------------------------------------------------------------- normals


def _day_of_year(day: date) -> int:
    """Day of a 365-day year (29 February counts as the 28th)."""

    same = date(2001, day.month, min(day.day, 28) if day.month == 2 else day.day)
    return same.timetuple().tm_yday


def component_normal(
    history: Sequence[BalanceHistoryDay], day: date, pick
) -> tuple[float | None, int]:
    """Mean of a component on the same days (±3) of earlier years, and how many years."""

    target = _day_of_year(day)
    values: dict[int, list[float]] = {}
    for h in history:
        if (day - h.day).days < 300:
            continue  # this year's own days are not its normal
        distance = abs(_day_of_year(h.day) - target)
        if min(distance, 365 - distance) <= 3:
            values.setdefault(h.day.year, []).append(pick(h))
    if not values:
        return None, 0
    return mean(mean(v) for v in values.values()), len(values)


# ----------------------------------------------------------------------------- backtest


def backtest_daily(history: Sequence[BalanceHistoryDay], *, days: int = 365) -> dict:
    """The daily method run at weekly origins over the past year, against what happened."""

    by_day = {h.day: h for h in history}
    if not history:
        return {"horizons": [], "origins": 0}
    last = history[-1].day
    origins = [
        last - timedelta(days=d)
        for d in range(days, DAILY_HORIZON - 1, -BACKTEST_STEP_DAYS)
    ]
    errors: dict[int, list[tuple[float, float]]] = {h: [] for h in BACKTEST_HORIZONS}
    used = 0
    for origin in origins:
        past = [h for h in history if h.day < origin]
        if len(past) < 400:
            continue
        forecast = forecast_balance(past, start=origin, days=DAILY_HORIZON)
        if not forecast.days:
            continue
        used += 1
        for horizon in BACKTEST_HORIZONS:
            predicted = forecast.days[horizon - 1]
            actual = by_day.get(predicted.day)
            if actual is not None:
                errors[horizon].append((predicted.call_gwh, actual.call_gwh))
    rows = []
    for horizon, pairs in errors.items():
        if not pairs:
            rows.append({"horizon_days": horizon, "n": 0, "mae_gwh_d": None,
                         "mape_pct": None, "bias_gwh_d": None})
            continue
        diffs = [p - a for p, a in pairs]
        rows.append({
            "horizon_days": horizon,
            "n": len(pairs),
            "mae_gwh_d": round(mean(abs(d) for d in diffs), 1),
            "mape_pct": round(100 * mean(abs(p - a) / a for p, a in pairs if a), 1),
            "bias_gwh_d": round(mean(diffs), 1),
        })
    return {
        "method": "daily method at weekly origins, history before each origin only; "
                  "announced outages as then known are not replayed",
        "origins": used,
        "from": origins[0].isoformat() if origins else None,
        "to": last.isoformat(),
        "horizons": rows,
    }


def backtest_monthly(history: Sequence[BalanceHistoryDay], hdd: HddReference) -> dict:
    """Each held month predicted from the months before it at normal HDD, against outturn."""

    actual = monthly_means(history)
    rows = []
    for month, value in sorted(actual.items()):
        fit = fit_demand(history, hdd, before=month)
        if fit is None or fit.months < MIN_FIT_MONTHS:
            continue
        normal = hdd.normal(int(month[5:7]))[0]
        predicted = fit.demand(normal)
        rows.append({"month": month, "predicted_gwh_d": round(predicted, 1),
                     "actual_gwh_d": round(value, 1),
                     "error_gwh_d": round(predicted - value, 1)})
    errors = [abs(r["error_gwh_d"]) for r in rows]
    return {
        "method": "monthly demand at normal HDD, fitted on earlier months only",
        "months": rows,
        "n": len(rows),
        "mae_gwh_d": round(mean(errors), 1) if errors else None,
    }


def _daily_error(backtest: dict, horizon: int) -> float | None:
    """Mean absolute error at a horizon, interpolated between the measured horizons."""

    points = [(r["horizon_days"], r["mae_gwh_d"]) for r in backtest.get("horizons", [])
              if r.get("mae_gwh_d") is not None]
    if not points:
        return None
    points.sort()
    if horizon <= points[0][0]:
        return points[0][1]
    for (h0, e0), (h1, e1) in zip(points, points[1:], strict=False):
        if h0 <= horizon <= h1:
            return e0 + (e1 - e0) * (horizon - h0) / (h1 - h0)
    return points[-1][1]


# ----------------------------------------------------------------------------- forward


def build_forward_balance(
    history: Sequence[BalanceHistoryDay],
    base_days: Sequence[Mapping],
    *,
    hdd: HddReference,
    outages: Sequence[SupplyOutage] = (),
    band: StorageBand | None = None,
    season_index=None,
    target: tuple[float, tuple[int, int]] | None = None,
    overrides: Overrides | None = None,
    backtest: dict | None = None,
) -> ForwardBalance:
    """The forward balance from the measured history and the 14-day base forecast.

    ``base_days`` are the 14 days ``forecast_balance`` produced (``BalanceDay.as_dict``):
    they carry the demand, Norway after announced outages, LNG and the inventory path.
    """

    overrides = overrides or Overrides()
    history = sorted(history, key=lambda h: h.day)
    result = ForwardBalance(as_of=history[-1].day if history else None)
    result.overridden = overrides.names()
    if not history or not base_days:
        result.warnings.append("No measured balance history: no forward balance.")
        return result
    fit = fit_demand(history, hdd)
    result.demand_fit = fit
    if fit is None or fit.months < MIN_FIT_MONTHS:
        result.warnings.append(
            f"The monthly demand fit rests on {fit.months if fit else 0} months of held history "
            f"(fewer than {MIN_FIT_MONTHS}); monthly demand and the temperature what-if are "
            "indicative."
        )
    slope = fit.slope_per_hdd if fit else 0.0
    result.backtest = {"daily": backtest if backtest is not None else backtest_daily(history),
                       "monthly": backtest_monthly(history, hdd)}
    last7 = history[-7:]
    last14 = history[-14:]
    norway_base = (overrides.norway_gwh_d if overrides.norway_gwh_d is not None
                   else mean(h.norway_gwh for h in last7))
    lng_base = (overrides.lng_gwh_d if overrides.lng_gwh_d is not None
                else mean(h.lng_gwh for h in last14))
    added = [overrides.added_outage] if overrides.added_outage else []

    def outage_on(line: str, day: date, *, extra: bool = True) -> float:
        pool = [*outages, *added] if extra else list(outages)
        return sum(o.gwh_d for o in pool if o.line == line and o.on(day))

    capacity = None
    outside_draw = 0.0
    inventory = None
    for index, base in enumerate(base_days):
        day = date.fromisoformat(str(base["day"]))
        horizon = index + 1
        normal_hdd = hdd.normal_on(day)
        delta_hdd = hdd_change(normal_hdd, overrides.temperature_shift_c)
        demand = float(base["call_gwh"]) + slope * delta_hdd
        added_norway = sum(o.gwh_d for o in added if o.line == "norway" and o.on(day))
        if overrides.norway_gwh_d is not None:
            norway = max(0.0, norway_base - outage_on("norway", day))
            norway_outage = outage_on("norway", day)
        else:
            # The base day already has the announced outages taken off.
            norway = max(0.0, float(base["norway_gwh"]) - added_norway)
            norway_outage = float(base.get("norway_outage_gwh") or 0.0) + added_norway
        lng = max(0.0, lng_base - outage_on("lng", day))
        storage = demand - norway - lng
        if base.get("inventory_twh") is not None and inventory is None:
            draw0 = base.get("inventory_draw_gwh")
            outside_draw = float(base["storage_net_withdrawal_gwh"]) - float(draw0 or 0.0)
            start_inventory = float(base["inventory_twh"]) + float(draw0 or 0.0) / 1000
            fill0 = base.get("fill_pct")
            capacity = (float(base["inventory_twh"]) * 100 / float(fill0)) if fill0 else None
            inventory = start_inventory
        fill = None
        if inventory is not None:
            inventory -= (storage - outside_draw) / 1000
            fill = 100 * inventory / capacity if capacity else None
        normal = {
            name: component_normal(history, day, pick)[0]
            for name, pick in (
                ("demand", lambda h: h.call_gwh),
                ("norway", lambda h: h.norway_gwh),
                ("lng", lambda h: h.lng_gwh),
                ("storage", lambda h: h.storage_net_withdrawal_gwh),
            )
        }
        error = _daily_error(result.backtest["daily"], horizon)
        if error is None and fit is not None:
            error = fit.residual_std
        low, high, avg = band.on(season_index(day)) if band and season_index else (None,) * 3
        flags = list(base.get("flags") or [])
        if inventory is not None and capacity and not 0 <= inventory <= capacity:
            flags.append("inventory_outside_capacity")
        result.daily.append({
            "day": day.isoformat(),
            "horizon_days": horizon,
            "demand_gwh_d": round(demand, 1),
            "demand_error_gwh_d": None if error is None else round(error, 1),
            "demand_normal_gwh_d": _r(normal["demand"]),
            "hdd_normal": round(normal_hdd, 2),
            "hdd_change": round(delta_hdd, 2),
            "norway_gwh_d": round(norway, 1),
            "norway_normal_gwh_d": _r(normal["norway"]),
            "norway_outage_gwh_d": round(norway_outage, 1),
            "lng_gwh_d": round(lng, 1),
            "lng_normal_gwh_d": _r(normal["lng"]),
            "lng_outage_gwh_d": round(outage_on("lng", day), 1),
            "storage_gwh_d": round(storage, 1),
            "storage_normal_gwh_d": _r(normal["storage"]),
            "gap_gwh_d": round(norway + lng - demand, 1),
            "inventory_twh": None if inventory is None else round(inventory, 2),
            "fill_pct": None if fill is None else round(fill, 1),
            "band_low_pct": low,
            "band_high_pct": high,
            "band_mean_pct": avg,
            "methods": {
                "demand": str((base.get("methods") or {}).get("call") or "seasonal_normal"),
                "norway": "7_day_average_less_announced_outages",
                "lng": "14_day_average",
                "storage": "residual",
            },
            "flags": flags,
        })
    result.headline = _headline(result.daily)
    # Months after the current one: normal-weather demand from the fit.
    last_day = date.fromisoformat(result.daily[-1]["day"])
    month_start = (history[-1].day.replace(day=1) + timedelta(days=32)).replace(day=1)
    for _ in range(MONTHS_AHEAD):
        days_in = calendar.monthrange(month_start.year, month_start.month)[1]
        month_end = month_start.replace(day=days_in)
        hdd_mean, hdd_std, years = hdd.normal(month_start.month)
        delta = hdd_change(hdd_mean, overrides.temperature_shift_c)
        if fit is not None:
            demand = fit.demand(hdd_mean + delta)
            spread = math.hypot(fit.slope_per_hdd * hdd_std, fit.residual_std)
        else:
            demand, spread = mean(h.call_gwh for h in history[-28:]), None
        dates = [month_start + timedelta(days=k) for k in range(days_in)]
        norway_out = mean(outage_on("norway", d) for d in dates)
        lng_out = mean(outage_on("lng", d) for d in dates)
        norway = max(0.0, norway_base - norway_out)
        lng = max(0.0, lng_base - lng_out)
        storage = demand - norway - lng
        fill = None
        if inventory is not None:
            # From the last daily day to the month's end at the month's rate.
            remaining = (month_end - max(last_day, month_start - timedelta(days=1))).days
            if remaining > 0:
                inventory -= (storage - outside_draw) * remaining / 1000
                last_day = month_end
            fill = 100 * inventory / capacity if capacity else None
        low, high, avg = band.on(season_index(month_end)) if band and season_index else (None,) * 3
        result.monthly.append({
            "month": f"{month_start:%Y-%m}",
            "days": days_in,
            "demand_gwh_d": round(demand, 1),
            "demand_error_gwh_d": None if spread is None else round(spread, 1),
            "hdd_normal": round(hdd_mean, 2),
            "hdd_normal_std": round(hdd_std, 2),
            "hdd_years": years,
            "hdd_change": round(delta, 2),
            "norway_gwh_d": round(norway, 1),
            "norway_outage_gwh_d": round(norway_out, 1),
            "lng_gwh_d": round(lng, 1),
            "storage_gwh_d": round(storage, 1),
            "gap_gwh_d": round(norway + lng - demand, 1),
            "inventory_twh_end": None if inventory is None else round(inventory, 2),
            "fill_pct_end": None if fill is None else round(fill, 1),
            "band_low_pct": low,
            "band_high_pct": high,
            "band_mean_pct": avg,
            "methods": {
                "demand": "monthly_fit_at_normal_hdd" if fit else "28_day_average",
                "norway": "7_day_average_less_announced_outages",
                "lng": "14_day_average",
                "storage": "residual",
            },
        })
        month_start = month_end + timedelta(days=1)
    if target is not None and capacity:
        pct, (month, day_of_month) = target
        result.target = _target(result, pct, month, day_of_month)
    return result


def _r(value: float | None) -> float | None:
    return None if value is None else round(value, 1)


def _headline(daily: Sequence[Mapping]) -> dict | None:
    """Tighter or looser than normal over the daily window, and the main reason."""

    rows = [r for r in daily if None not in (
        r["demand_normal_gwh_d"], r["norway_normal_gwh_d"], r["lng_normal_gwh_d"],
        r["storage_normal_gwh_d"])]
    if not rows:
        return None
    contributions = {
        "demand": mean(r["demand_gwh_d"] - r["demand_normal_gwh_d"] for r in rows),
        "norway": -mean(r["norway_gwh_d"] - r["norway_normal_gwh_d"] for r in rows),
        "lng": -mean(r["lng_gwh_d"] - r["lng_normal_gwh_d"] for r in rows),
    }
    # Tightness: how much more the region must draw from storage than on normal days.
    tightness = mean(
        (r["demand_gwh_d"] - r["norway_gwh_d"] - r["lng_gwh_d"])
        - (r["demand_normal_gwh_d"] - r["norway_normal_gwh_d"] - r["lng_normal_gwh_d"])
        for r in rows
    )
    direction = ("about_normal" if abs(tightness) < NORMAL_BAND_GWH
                 else "tighter" if tightness > 0 else "looser")
    main = max(contributions, key=lambda k: abs(contributions[k]))
    outage = mean(r["norway_outage_gwh_d"] for r in rows)
    return {
        "direction": direction,
        "gwh_d": round(abs(tightness), 1),
        "signed_gwh_d": round(tightness, 1),
        "window": {"from": rows[0]["day"], "to": rows[-1]["day"], "days": len(rows)},
        "main_driver": main,
        "contributions_gwh_d": {k: round(v, 1) for k, v in contributions.items()},
        "norway_outage_gwh_d": round(outage, 1),
        "normal_basis": "same days in earlier years held (±3 days)",
    }


def _target(result: ForwardBalance, pct: float, month: int, day_of_month: int) -> dict:
    """Implied fill at the storage target's next deadline, if the horizon reaches it."""

    if result.as_of is None:
        return {}
    year = result.as_of.year
    deadline = date(year, month, day_of_month)
    if deadline <= result.as_of:
        deadline = date(year + 1, month, day_of_month)
    implied = None
    for row in result.daily:
        if row["day"] == deadline.isoformat():
            implied = row["fill_pct"]
    if implied is None:
        for row in result.monthly:
            if row["month"] == f"{deadline:%Y-%m}" or (
                row["month"] == f"{(deadline - timedelta(days=1)):%Y-%m}"
                and deadline.day == 1
            ):
                implied = row["fill_pct_end"]
    return {
        "pct": pct,
        "deadline": deadline.isoformat(),
        "implied_fill_pct": implied,
        "within_horizon": implied is not None,
        "gap_pts": None if implied is None else round(implied - pct, 1),
    }
