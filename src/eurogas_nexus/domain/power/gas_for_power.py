"""Gas-for-power: how electricity demand, renewables and prices turn into gas burn.

Gas plants run when they are needed to meet the load that wind, solar and must-run
plant leave behind (the residual load), and when burning gas is cheaper than the
alternative (the clean spark spread against the clean dark spread). Both are computed
here from explicit inputs; nothing is estimated silently.

Units: power in MW (average over the period), prices in currency per MWh of electricity
(``/MWh_e``) or of gas (``/MWh_th``, gross calorific value as hubs quote), carbon in
currency per tonne CO2. Efficiencies are net electrical efficiencies on the same
calorific basis as the gas price.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Emission factor of natural gas, tonnes CO2 per MWh of gas burned (GCV basis).
GAS_EMISSION_T_PER_MWH_TH = 0.184
#: Emission factor of hard coal, tonnes CO2 per MWh of coal burned (NCV basis).
COAL_EMISSION_T_PER_MWH_TH = 0.341


class GasForPowerError(ValueError):
    """An input outside its physical range."""


def _efficiency(value: float, name: str) -> float:
    if not 0.2 <= value <= 0.7:
        raise GasForPowerError(f"{name} must be a net efficiency between 0.20 and 0.70")
    return value


def clean_spark_spread(
    power_price: float,
    gas_price: float,
    carbon_price: float,
    *,
    efficiency: float = 0.50,
    emission_factor: float = GAS_EMISSION_T_PER_MWH_TH,
) -> float:
    """Margin of a gas plant per MWh of electricity after fuel and carbon.

    CSS = power − gas / η − carbon × EF / η. Prices must share one currency.
    """

    eta = _efficiency(efficiency, "efficiency")
    return power_price - gas_price / eta - carbon_price * emission_factor / eta


def clean_dark_spread(
    power_price: float,
    coal_price_per_mwh_th: float,
    carbon_price: float,
    *,
    efficiency: float = 0.38,
    emission_factor: float = COAL_EMISSION_T_PER_MWH_TH,
) -> float:
    """Margin of a coal plant per MWh of electricity after fuel and carbon."""

    eta = _efficiency(efficiency, "efficiency")
    return power_price - coal_price_per_mwh_th / eta - carbon_price * emission_factor / eta


def fuel_switch_gas_price(
    coal_price_per_mwh_th: float,
    carbon_price: float,
    *,
    gas_efficiency: float = 0.50,
    coal_efficiency: float = 0.38,
) -> float:
    """Gas price at which a gas plant and a coal plant have the same marginal cost.

    Below this price gas is dispatched ahead of coal. Setting the two marginal costs per
    MWh_e equal and solving for the gas price gives
    ``gas = η_gas × (coal/η_coal + CO2×EF_coal/η_coal) − CO2×EF_gas``.
    """

    eta_g = _efficiency(gas_efficiency, "gas_efficiency")
    eta_c = _efficiency(coal_efficiency, "coal_efficiency")
    coal_cost_per_mwh_e = (
        coal_price_per_mwh_th + carbon_price * COAL_EMISSION_T_PER_MWH_TH
    ) / eta_c
    return eta_g * coal_cost_per_mwh_e - carbon_price * GAS_EMISSION_T_PER_MWH_TH


@dataclass(frozen=True)
class SystemHour:
    """One period of a power system, average MW over the period."""

    load_mw: float
    wind_mw: float = 0.0
    solar_mw: float = 0.0
    #: Nuclear, run-of-river hydro, biomass and other plant that runs regardless of price.
    must_run_mw: float = 0.0
    #: Net imports (positive) or exports (negative).
    net_imports_mw: float = 0.0
    #: Observed gas-fired generation, when the source publishes it (ENTSO-E B04, Elexon CCGT+OCGT).
    gas_generation_mw: float | None = None


def residual_load_mw(hour: SystemHour) -> float:
    """Load left for dispatchable thermal plant after renewables, must-run and imports."""

    return hour.load_mw - hour.wind_mw - hour.solar_mw - hour.must_run_mw - hour.net_imports_mw


def implied_gas_burn_mwh_th(
    hour: SystemHour,
    *,
    hours: float = 1.0,
    gas_share_of_residual: float = 1.0,
    efficiency: float = 0.50,
) -> tuple[float, str]:
    """Gas burned to generate the gas share of the period, in MWh of gas.

    Uses observed gas generation when available; otherwise the residual load times the
    share of it gas is assumed to cover (1.0 where coal has left the system, as in GB).
    Returns the burn and its basis (``observed_generation`` or ``residual_load``).
    """

    eta = _efficiency(efficiency, "efficiency")
    if not 0 <= gas_share_of_residual <= 1:
        raise GasForPowerError("gas_share_of_residual must be between 0 and 1")
    if hours <= 0:
        raise GasForPowerError("hours must be positive")
    if hour.gas_generation_mw is not None:
        return max(0.0, hour.gas_generation_mw) * hours / eta, "observed_generation"
    gas_mw = max(0.0, residual_load_mw(hour)) * gas_share_of_residual
    return gas_mw * hours / eta, "residual_load"


def mwh_th_to_mcm(mwh_th: float, *, gcv_kwh_per_m3: float = 11.0) -> float:
    """Convert MWh of gas to million cubic metres at a stated gross calorific value."""

    if gcv_kwh_per_m3 <= 0:
        raise GasForPowerError("gcv_kwh_per_m3 must be positive")
    return mwh_th * 1000 / gcv_kwh_per_m3 / 1_000_000
