"""Gas-for-power arithmetic: spreads, fuel switching, residual load and implied burn."""

import pytest

from eurogas_nexus.domain.power.gas_for_power import (
    GAS_EMISSION_T_PER_MWH_TH,
    GasForPowerError,
    SystemHour,
    clean_dark_spread,
    clean_spark_spread,
    fuel_switch_gas_price,
    implied_gas_burn_mwh_th,
    mwh_th_to_mcm,
    residual_load_mw,
)


def test_clean_spark_spread():
    # 100 power, 35 gas, 70 carbon at 50%: 100 - 70 - 70*0.184/0.5 = 4.24
    assert clean_spark_spread(100, 35, 70) == pytest.approx(100 - 70 - 70 * 0.184 / 0.5)


def test_fuel_switch_price_equalises_marginal_costs():
    switch = fuel_switch_gas_price(12.0, 70.0)
    gas_cost = (switch + 70 * GAS_EMISSION_T_PER_MWH_TH) / 0.50
    # At the switch price both plants earn the same spread at any power price.
    assert clean_spark_spread(90, switch, 70) == pytest.approx(clean_dark_spread(90, 12.0, 70))
    assert gas_cost == pytest.approx((12.0 + 70 * 0.341) / 0.38)


def test_residual_load_and_implied_burn():
    hour = SystemHour(
        load_mw=35_000, wind_mw=12_000, solar_mw=3_000, must_run_mw=5_000, net_imports_mw=4_000
    )
    assert residual_load_mw(hour) == 11_000
    burn, basis = implied_gas_burn_mwh_th(hour, efficiency=0.5)
    assert (burn, basis) == (22_000, "residual_load")
    observed = SystemHour(load_mw=35_000, gas_generation_mw=9_000)
    assert implied_gas_burn_mwh_th(observed, hours=0.5) == (9_000, "observed_generation")
    windy = SystemHour(load_mw=20_000, wind_mw=25_000)
    assert implied_gas_burn_mwh_th(windy)[0] == 0


def test_units_and_bad_inputs():
    # 1 TWh at 11 kWh/m3 is about 90.9 mcm.
    assert mwh_th_to_mcm(1_000_000) == pytest.approx(90.909, rel=1e-4)
    with pytest.raises(GasForPowerError):
        clean_spark_spread(100, 35, 70, efficiency=0.9)
    with pytest.raises(GasForPowerError):
        implied_gas_burn_mwh_th(SystemHour(load_mw=1), gas_share_of_residual=1.5)
