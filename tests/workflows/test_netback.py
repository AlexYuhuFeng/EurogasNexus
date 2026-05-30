"""Indicative netback computation tests."""

from eurogas_nexus.workflows.netback import NetbackInput, compute_netback


def test_netback_subtracts_route_cost() -> None:
    result = compute_netback(NetbackInput(
        route_name="TTF-NBP", from_market="TTF", to_market="NBP",
        market_price_eur_mwh=42.50, route_cost_eur_mwh=1.80,
    ))
    assert result.netback_eur_mwh == 40.70
    assert result.research_only is True
    assert not result.is_partial


def test_netback_applies_fx() -> None:
    result = compute_netback(NetbackInput(
        route_name="TTF-NBP", from_market="TTF", to_market="NBP",
        market_price_eur_mwh=42.50, route_cost_eur_mwh=1.80,
        fx_rate=0.851, fx_pair="EURGBP",
    ))
    assert result.netback_eur_mwh == 40.70
    assert result.netback_local_mwh == round(40.70 * 0.851, 4)


def test_netback_warns_on_non_positive() -> None:
    result = compute_netback(NetbackInput(
        route_name="Test", from_market="A", to_market="B",
        market_price_eur_mwh=1.0, route_cost_eur_mwh=5.0,
    ))
    assert result.netback_eur_mwh < 0
    assert len(result.warnings) >= 1


def test_netback_requires_market_price() -> None:
    result = compute_netback(NetbackInput(
        route_name="Test", from_market="A", to_market="B",
        market_price_eur_mwh=0.0, route_cost_eur_mwh=1.0,
    ))
    assert len(result.missing_inputs) >= 1


def test_netback_lineage_present() -> None:
    result = compute_netback(NetbackInput(
        route_name="T1", from_market="A", to_market="B",
        market_price_eur_mwh=10.0, route_cost_eur_mwh=2.0,
    ))
    assert "netback-computation" in result.lineage
