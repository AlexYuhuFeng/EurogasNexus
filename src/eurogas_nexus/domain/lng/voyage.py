"""One LNG voyage: sailing days, boil-off and freight in money (CP-12, design C.1-C.2).

``days = distance_nm / (speed_kn x 24)`` per leg, rounded to a tenth of a day (the way a
voyage estimate states it: "12.0 days laden at 17 kn"); ballast is the same distance back by
default (round voyage) or none (one-way, for a positioning or a delivered-ex-ship offer close
to the terminal). Port days are one at loading and one at discharge unless set.

Freight, in the cargo's purchase currency (USD for an FOB lift)::

    hire          = hire_per_day x (days laden + days ballast + port days)
    ballast fuel  = fuel_ballast MMBtu/day x days ballast x the cargo's FOB price
                    (laden, boil-off drives the ship: already lost from the cargo, no money)
    canal, ports  = as entered (zero only where the route has no canal)
    insurance     = insurance % x cargo value

Boil-off is energy, not money: ``Q_lost = Q_load x bor %/day x days laden``. Pure, Decimal,
no rounding of money until the caller displays it.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

_TENTH = Decimal("0.1")
_HUNDRED = Decimal(100)


class VoyageError(ValueError):
    """An input outside what a voyage can be (non-positive speed, negative distance)."""


@dataclass(frozen=True)
class Voyage:
    """Distances and speeds of one cargo's voyage."""

    distance_nm: Decimal
    speed_laden_kn: Decimal = Decimal(17)
    speed_ballast_kn: Decimal = Decimal(17)
    port_days: Decimal = Decimal(2)
    ballast: str = "round"  # round | one_way
    routing: str = "direct"

    def __post_init__(self) -> None:
        if self.distance_nm < 0:
            raise VoyageError("distance_nm must not be negative")
        if self.speed_laden_kn <= 0 or self.speed_ballast_kn <= 0:
            raise VoyageError("speed must be positive")
        if self.port_days < 0:
            raise VoyageError("port_days must not be negative")
        if self.ballast not in {"round", "one_way"}:
            raise VoyageError("ballast is round or one_way")


def sailing_days(distance_nm: Decimal, speed_kn: Decimal) -> Decimal:
    """Days at sea for one leg, to a tenth of a day."""

    return (distance_nm / (speed_kn * 24)).quantize(_TENTH, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class VoyageDays:
    laden: Decimal
    ballast: Decimal
    port: Decimal

    @property
    def total(self) -> Decimal:
        return self.laden + self.ballast + self.port


def voyage_days(voyage: Voyage) -> VoyageDays:
    laden = sailing_days(voyage.distance_nm, voyage.speed_laden_kn)
    ballast = (
        sailing_days(voyage.distance_nm, voyage.speed_ballast_kn)
        if voyage.ballast == "round"
        else Decimal(0)
    )
    return VoyageDays(laden=laden, ballast=ballast, port=voyage.port_days)


def boil_off_mmbtu(q_load_mmbtu: Decimal, bor_pct_per_day: Decimal, days_laden: Decimal) -> Decimal:
    """Energy boiled off on the laden leg."""

    return q_load_mmbtu * bor_pct_per_day / _HUNDRED * days_laden


@dataclass(frozen=True)
class FreightCosts:
    """The voyage's money legs, in the purchase currency, unrounded."""

    hire: Decimal
    ballast_fuel: Decimal
    canal: Decimal
    port_load: Decimal
    port_discharge: Decimal
    insurance: Decimal

    @property
    def total(self) -> Decimal:
        return (
            self.hire
            + self.ballast_fuel
            + self.canal
            + self.port_load
            + self.port_discharge
            + self.insurance
        )


def freight_costs(
    days: VoyageDays,
    *,
    hire_per_day: Decimal,
    ballast_fuel_mmbtu_per_day: Decimal,
    fuel_price_per_mmbtu: Decimal,
    canal: Decimal,
    port_load: Decimal,
    port_discharge: Decimal,
    insurance_pct: Decimal,
    cargo_value: Decimal,
) -> FreightCosts:
    return FreightCosts(
        hire=hire_per_day * days.total,
        ballast_fuel=ballast_fuel_mmbtu_per_day * days.ballast * fuel_price_per_mmbtu,
        canal=canal,
        port_load=port_load,
        port_discharge=port_discharge,
        insurance=insurance_pct / _HUNDRED * cargo_value,
    )
