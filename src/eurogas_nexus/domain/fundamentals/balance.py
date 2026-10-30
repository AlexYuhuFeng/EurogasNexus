"""North-west Europe gas balance: what the region calls on, what supplies it, and storage.

Desks forecast a regional balance from components they can each explain, not from one
black box. Here the region (GB, NL, BE, DE, FR, DK, LU) calls on three flexible sources:
Norwegian pipeline gas, LNG send-out and storage. Domestic production and other imports
change slowly and sit inside the call. On any day::

    call = norway + lng + storage_net_withdrawal

Historically all three supply terms are observed (ENTSOG entry flows, GIE ALSI, GIE AGSI),
so the call is measured. Forward, each component has its own method, recorded on every
day it produces:

- call: weather regression ``a + b·HDD`` (+ weekend effect) when heating-degree-day
  forecasts are supplied; otherwise the seasonal normal (same days of the year in earlier
  years) shifted by how far the last 14 days ran above or below their own normal; if
  there is too little history, the 28-day average.
- norway: the 7-day average flow minus the unavailable capacity of Norwegian outages
  (REMIT UMMs) on each day.
- lng: the 14-day average send-out (a cargo schedule from a licensed source replaces it).
- storage: the residual, then rolled into an inventory trajectory against working
  capacity, flagged when it implies withdrawals the region has not delivered recently.

All quantities are energy, GWh per gas day, so no calorific value is assumed except where
a volume source is converted, and that conversion is stated by the caller.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, timedelta
from statistics import mean

NWE_COUNTRIES = ("GB", "NL", "BE", "DE", "FR", "DK", "LU")


@dataclass(frozen=True)
class BalanceHistoryDay:
    day: date
    norway_gwh: float
    lng_gwh: float
    storage_net_withdrawal_gwh: float  # withdrawal positive, injection negative

    @property
    def call_gwh(self) -> float:
        return self.norway_gwh + self.lng_gwh + self.storage_net_withdrawal_gwh


@dataclass(frozen=True)
class Outage:
    start: date
    end: date | None  # exclusive; None while open-ended
    unavailable_gwh_d: float

    def on(self, day: date) -> bool:
        return self.start <= day and (self.end is None or day < self.end)


@dataclass(frozen=True)
class WeatherModel:
    intercept: float
    slope_per_hdd: float
    weekend_effect: float
    r2: float
    observations: int

    def call(self, hdd: float, day: date) -> float:
        return (
            self.intercept
            + self.slope_per_hdd * hdd
            + (self.weekend_effect if day.weekday() >= 5 else 0.0)
        )


@dataclass(frozen=True)
class BalanceDay:
    day: date
    call_gwh: float
    norway_gwh: float
    lng_gwh: float
    storage_net_withdrawal_gwh: float
    inventory_twh: float | None
    fill_pct: float | None
    methods: dict[str, str]
    hdd: float | None = None
    norway_outage_gwh: float = 0.0
    flags: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "day": self.day.isoformat(),
            "call_gwh": round(self.call_gwh, 1),
            "norway_gwh": round(self.norway_gwh, 1),
            "norway_outage_gwh": round(self.norway_outage_gwh, 1),
            "lng_gwh": round(self.lng_gwh, 1),
            "storage_net_withdrawal_gwh": round(self.storage_net_withdrawal_gwh, 1),
            "inventory_twh": None if self.inventory_twh is None else round(self.inventory_twh, 2),
            "fill_pct": None if self.fill_pct is None else round(self.fill_pct, 1),
            "hdd": self.hdd,
            "methods": dict(self.methods),
            "flags": list(self.flags),
        }


@dataclass
class BalanceForecast:
    history: list[BalanceHistoryDay]
    days: list[BalanceDay]
    model: WeatherModel | None = None
    warnings: list[str] = field(default_factory=list)


def fit_weather_model(
    history: Iterable[BalanceHistoryDay], hdd: Mapping[date, float]
) -> WeatherModel | None:
    """Least squares of the call on HDD and a weekend flag; ``None`` below 30 matched days."""

    rows = [
        (d.call_gwh, hdd[d.day], 1.0 if d.day.weekday() >= 5 else 0.0)
        for d in history
        if d.day in hdd
    ]
    if len(rows) < 30:
        return None
    # Normal equations for y = a + b·x + c·w (3x3, solved by elimination).
    n = len(rows)
    sx = sum(r[1] for r in rows)
    sw = sum(r[2] for r in rows)
    sy = sum(r[0] for r in rows)
    sxx = sum(r[1] ** 2 for r in rows)
    sww = sum(r[2] ** 2 for r in rows)
    sxw = sum(r[1] * r[2] for r in rows)
    sxy = sum(r[1] * r[0] for r in rows)
    swy = sum(r[2] * r[0] for r in rows)
    matrix = [[n, sx, sw, sy], [sx, sxx, sxw, sxy], [sw, sxw, sww, swy]]
    for col in range(3):
        pivot = max(range(col, 3), key=lambda r: abs(matrix[r][col]))
        if abs(matrix[pivot][col]) < 1e-12:
            return None
        matrix[col], matrix[pivot] = matrix[pivot], matrix[col]
        for r in range(3):
            if r != col:
                factor = matrix[r][col] / matrix[col][col]
                matrix[r] = [a - factor * b for a, b in zip(matrix[r], matrix[col], strict=True)]
    a, b, c = (matrix[i][3] / matrix[i][i] for i in range(3))
    mean_y = sy / n
    ss_tot = sum((r[0] - mean_y) ** 2 for r in rows)
    ss_res = sum((r[0] - (a + b * r[1] + c * r[2])) ** 2 for r in rows)
    r2 = 1 - ss_res / ss_tot if ss_tot else 0.0
    return WeatherModel(a, b, c, r2, n)


def _day_of_year_distance(a: date, b: date) -> int:
    gap = abs(a.timetuple().tm_yday - b.timetuple().tm_yday)
    return min(gap, 365 - gap)


def _seasonal_normal(history: list[BalanceHistoryDay], day: date, window: int = 3) -> float | None:
    """Mean call on the same days of the year (±``window``) in earlier years."""

    values = [
        h.call_gwh
        for h in history
        if h.day <= day - timedelta(days=300) and _day_of_year_distance(h.day, day) <= window
    ]
    return mean(values) if len(values) >= 5 else None


def forecast_balance(
    history: Iterable[BalanceHistoryDay],
    *,
    start: date,
    days: int,
    norway_outages: Iterable[Outage] = (),
    hdd: Mapping[date, float] | None = None,
    inventory_twh: float | None = None,
    working_capacity_twh: float | None = None,
) -> BalanceForecast:
    """Daily balance from ``start`` for ``days`` days."""

    past = sorted((h for h in history if h.day < start), key=lambda h: h.day)
    result = BalanceForecast(history=past, days=[])
    if len(past) < 7:
        result.warnings.append("Fewer than 7 days of Norwegian, LNG and storage history.")
        return result
    hdd = hdd or {}
    model = fit_weather_model(past, hdd) if hdd else None
    result.model = model
    last7 = past[-7:]
    last14 = past[-14:]
    last28 = past[-28:]
    norway_base = mean(h.norway_gwh for h in last7)
    lng_base = mean(h.lng_gwh for h in last14)
    # How far recent days ran from their own seasonal normal, carried into the forecast.
    anomalies = [
        h.call_gwh - normal for h in last14 if (normal := _seasonal_normal(past, h.day)) is not None
    ]
    anomaly = mean(anomalies) if len(anomalies) >= 7 else None
    max_recent_withdrawal = max(h.storage_net_withdrawal_gwh for h in last28)
    outages = list(norway_outages)
    inventory = inventory_twh
    for offset in range(days):
        day = start + timedelta(days=offset)
        if model is not None and day in hdd:
            call, call_method = model.call(hdd[day], day), "weather_regression"
        elif anomaly is not None and (normal := _seasonal_normal(past, day)) is not None:
            call, call_method = normal + anomaly, "seasonal_normal_plus_recent_anomaly"
        else:
            call, call_method = mean(h.call_gwh for h in last28), "28_day_average"
        outage = sum(o.unavailable_gwh_d for o in outages if o.on(day))
        norway = max(0.0, norway_base - outage)
        storage = call - norway - lng_base
        flags = []
        if storage > max_recent_withdrawal * 1.25 and storage > 0:
            flags.append("withdrawal_above_recent_maximum")
        fill = None
        if inventory is not None:
            inventory = inventory - storage / 1000
            if working_capacity_twh:
                fill = 100 * inventory / working_capacity_twh
                if inventory < 0 or (fill is not None and fill > 100):
                    flags.append("inventory_outside_capacity")
        result.days.append(
            BalanceDay(
                day=day,
                call_gwh=call,
                norway_gwh=norway,
                lng_gwh=lng_base,
                storage_net_withdrawal_gwh=storage,
                inventory_twh=inventory,
                fill_pct=fill,
                hdd=hdd.get(day),
                norway_outage_gwh=outage,
                methods={
                    "call": call_method,
                    "norway": "7_day_average_less_remit_outages",
                    "lng": "14_day_average",
                    "storage": "residual",
                },
                flags=tuple(flags),
            )
        )
    if model is None:
        result.warnings.append(
            "No heating-degree-day forecast supplied: the call is the seasonal normal plus "
            "the recent anomaly, not a weather forecast."
        )
    elif model.r2 < 0.6:
        result.warnings.append(f"Weather model fit is weak (R² {model.r2:.2f}).")
    return result
