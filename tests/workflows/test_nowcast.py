"""Weather-adjusted nowcast tests."""

from eurogas_nexus.workflows.nowcast import NowcastInput, compute_nowcast


def test_nowcast_adjusts_for_hdd() -> None:
    result = compute_nowcast(NowcastInput(
        market="TTF", base_demand_boe_d=4200000.0, hdd=1.0, cdd=0.0,
    ))
    assert result.hdd_adjustment_boe_d == 150000.0
    assert result.weather_adjustment_boe_d == 150000.0
    assert result.adjusted_demand_boe_d == 4350000.0


def test_nowcast_adjusts_for_cdd() -> None:
    result = compute_nowcast(NowcastInput(
        market="TTF", base_demand_boe_d=4200000.0, hdd=0.0, cdd=2.0,
    ))
    assert result.cdd_adjustment_boe_d == 100000.0


def test_nowcast_no_weather_no_adjustment() -> None:
    result = compute_nowcast(NowcastInput(
        market="TTF", base_demand_boe_d=4200000.0, hdd=0.0, cdd=0.0,
    ))
    assert result.adjusted_demand_boe_d == 4200000.0


def test_nowcast_research_metadata() -> None:
    result = compute_nowcast(NowcastInput(
        market="TTF", base_demand_boe_d=1000000.0,
    ))
    assert result.research_only is True
    assert "nowcast-computation" in result.lineage
