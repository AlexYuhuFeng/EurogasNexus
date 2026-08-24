"""Composition contract tests for DB-backed portfolio network optimization."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from eurogas_nexus.domain.route_cost.european_public_tariffs import (
    published_european_corridor_tariffs,
)
from eurogas_nexus.domain.route_cost.portfolio_network import (
    CompanyTsoAccessFact,
    ContractFact,
    FxObservationFact,
    MarketObservationFact,
    NetworkNodeFact,
    RouteCandidateFact,
    RouteLegFact,
    compose_portfolio_network,
    optimize_composed_portfolio_network,
)

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
GAS_DAY = date(2026, 1, 1)
TARIFFS = published_european_corridor_tariffs()


def _contracts(*exit_points: str) -> list[ContractFact]:
    return [
        ContractFact(
            contract_id="contract-ttf",
            contract_name="TTF supply",
            resource_type="PIPELINE_IMPORT",
            delivery_point_name="TTF",
            gas_year="2025+",
            delivery_quantity_mwh_per_day=100.0,
            contract_price_gbp_mwh=25.0,
            tolerance_risk_allowance_gbp_mwh=0.1,
            allowed_exit_points=tuple(exit_points),
            eligible_sale_modes=("TARGET_MARKET_SALE", "LOCAL_MARKET_SALE"),
        )
    ]


def _nodes() -> list[NetworkNodeFact]:
    return [
        NetworkNodeFact("node-ttf", "TTF", "hub", "NL"),
        NetworkNodeFact("node-nbp", "NBP", "hub", "GB"),
    ]


def _local_route() -> RouteCandidateFact:
    return RouteCandidateFact(
        route_id="local-ttf",
        route_name="Sell locally at TTF",
        start_point_name="TTF",
        target_point_name="TTF",
        business_model="VIRTUAL_HUB_SALE",
        route_legs=(),
        required_tso_access=(),
        source_systems=("public_route_template",),
    )


def _bbl_route(capacity_mwh: float = 2000.0) -> RouteCandidateFact:
    return RouteCandidateFact(
        route_id="bbl-route",
        route_name="TTF to NBP",
        start_point_name="TTF",
        target_point_name="NBP",
        business_model="CROSS_BORDER_TRANSFER",
        route_legs=(
            RouteLegFact(
                leg_id="bbl-forward",
                country="NL",
                tso="BBL Company",
                market_area="BBL",
                point_name="BBL Forward Flow NL to GB",
                direction="EXIT",
                capacity_product="ANNUAL",
                firmness="FIRM",
                gas_year="2025+",
                available_capacity_mwh_per_day=capacity_mwh,
            ),
        ),
        required_tso_access=("BBL Company",),
        source_systems=("public_route_template", "BBL"),
    )


def _market(target: str, *, hours_old: float = 1.0) -> MarketObservationFact:
    observed = NOW - timedelta(hours=hours_old)
    return MarketObservationFact(
        observation_id=f"market-{target.lower()}",
        market_venue="EEX",
        product=f"{target} Day-Ahead",
        price=32.0,
        unit="EUR/MWh",
        currency="EUR",
        period_start_utc=GAS_DAY - timedelta(days=1),
        period_end_utc=GAS_DAY + timedelta(days=1),
        observed_at_utc=observed,
        source_system="EEX_Sim",
        source_reference="simulated:test",
        freshness="simulated_live",
        quality_score=0.9,
        simulated=True,
        metadata_json={"hub": target, "tenor": "day-ahead"},
    )


def _fx() -> list[FxObservationFact]:
    return [
        FxObservationFact(
            observation_id="fx-eur-gbp",
            pair="EURGBP",
            base_currency="EUR",
            quote_currency="GBP",
            rate=0.85,
            value_date="2026-01-01",
            observed_at_utc=NOW,
            source_system="ECB",
            source_reference="ecb:eurofxref",
        )
    ]


def _access(status: str = "ACTIVE") -> list[CompanyTsoAccessFact]:
    return [
        CompanyTsoAccessFact(
            tso="BBL Company",
            status=status,
            valid_from_utc=datetime(2025, 1, 1, tzinfo=UTC),
            valid_to_utc=None,
            source_reference="preview-access",
        )
    ]


def _compose(
    *,
    contracts: list[ContractFact] | None = None,
    routes: list[RouteCandidateFact] | None = None,
    market: list[MarketObservationFact] | None = None,
    fx: list[FxObservationFact] | None = None,
    access: list[CompanyTsoAccessFact] | None = None,
    max_age_hours: float = 72.0,
):
    return compose_portfolio_network(
        contracts=contracts if contracts is not None else _contracts("NBP", "TTF"),
        routes=routes if routes is not None else [_local_route(), _bbl_route()],
        nodes=_nodes(),
        tariffs=TARIFFS,
        access_rows=access if access is not None else _access(),
        market_rows=(
            market
            if market is not None
            else [_market("TTF"), _market("NBP")]
        ),
        fx_rows=fx if fx is not None else _fx(),
        gas_day=GAS_DAY,
        now_utc=NOW,
        max_market_price_age_hours=max_age_hours,
    )


def test_complete_composition_builds_contracts_routes_tariffs_and_access() -> None:
    composition = _compose()

    assert composition.is_complete is True
    assert [resource.resource_id for resource in composition.resources] == ["contract-ttf"]
    assert {option.option_id for option in composition.sale_options} == {
        "route:local-ttf",
        "route:bbl-route",
    }
    assert [edge.edge_id for edge in composition.edges] == ["route:bbl-route"]
    assert composition.edges[0].tariff_gbp_mwh == pytest.approx(0.85)
    assert composition.edge_lineage[0]["source_node_id"] == "node-ttf"
    assert composition.edge_lineage[0]["target_node_id"] == "node-nbp"
    assert composition.sale_option_lineage[0]["sale_price_currency"] == "GBP"


def test_local_sale_does_not_require_tariff_capacity_or_tso() -> None:
    composition = _compose(routes=[_local_route()], access=[])

    assert composition.is_complete is True
    assert composition.edges == ()
    assert composition.sale_options[0].destination_node == "node-ttf"
    assert composition.sale_options[0].capacity_mwh == 100.0


def test_missing_supply_node_blocks_composition() -> None:
    composition = _compose(
        contracts=[
            ContractFact(
                contract_id="contract-unknown",
                contract_name="Unknown",
                resource_type="PIPELINE_IMPORT",
                delivery_point_name="UNKNOWN_POINT",
                gas_year="2025+",
                delivery_quantity_mwh_per_day=100.0,
                contract_price_gbp_mwh=25.0,
            )
        ]
    )

    assert composition.is_complete is False
    assert "SUPPLY_NODE_MISSING:contract-unknown" in composition.blockers


def test_missing_market_price_blocks_route() -> None:
    composition = _compose(market=[_market("TTF")])

    assert composition.is_complete is False
    assert "MARKET_PRICE_MISSING:NBP" in composition.blockers


def test_stale_market_price_blocks_route() -> None:
    composition = _compose(
        market=[_market("TTF"), _market("NBP", hours_old=80.0)],
        max_age_hours=72.0,
    )

    assert composition.is_complete is False
    assert any(
        blocker.startswith("MARKET_PRICE_STALE:NBP:") for blocker in composition.blockers
    )


def test_missing_fx_blocks_non_gbp_market_price() -> None:
    composition = _compose(fx=[])

    assert composition.is_complete is False
    assert any(
        blocker.startswith("MARKET_PRICE_CONVERSION_BLOCKED:")
        for blocker in composition.blockers
    )


def test_missing_tariff_blocks_cross_border_route() -> None:
    route = _bbl_route()
    route = RouteCandidateFact(
        route_id=route.route_id,
        route_name=route.route_name,
        start_point_name=route.start_point_name,
        target_point_name=route.target_point_name,
        business_model=route.business_model,
        route_legs=(
            RouteLegFact(
                leg_id="missing-tariff-leg",
                country="NL",
                tso="Unknown TSO",
                market_area="UNKNOWN",
                point_name="Unknown Tariff Point",
                direction="EXIT",
                capacity_product="ANNUAL",
                firmness="FIRM",
                gas_year="2025+",
                available_capacity_mwh_per_day=100.0,
            ),
        ),
        required_tso_access=("Unknown TSO",),
        source_systems=("test",),
    )
    composition = _compose(
        routes=[route],
        access=[
            *_access(),
            CompanyTsoAccessFact(
                tso="Unknown TSO",
                status="ACTIVE",
                valid_from_utc=datetime(2025, 1, 1, tzinfo=UTC),
                source_reference="test-access",
            ),
        ],
    )

    assert composition.is_complete is False
    assert any(
        blocker.startswith("ROUTE_COST_MISSING:missing-tariff-leg:")
        or blocker == "ROUTE_COST_MISSING:bbl-route"
        for blocker in composition.blockers
    )


def test_missing_company_tso_access_blocks_required_route() -> None:
    composition = _compose(routes=[_local_route(), _bbl_route()], access=[])

    assert composition.is_complete is False
    assert any(
        blocker.startswith("TSO_ACCESS_MISSING:bbl-route")
        for blocker in composition.blockers
    )


def test_denied_company_tso_access_blocks_required_route() -> None:
    composition = _compose(routes=[_local_route(), _bbl_route()], access=_access("DENIED"))

    assert composition.is_complete is False
    assert any(
        blocker.startswith("TSO_ACCESS_DENIED:bbl-route")
        for blocker in composition.blockers
    )


def test_missing_route_capacity_blocks_cross_border_route() -> None:
    composition = _compose(routes=[_local_route(), _bbl_route(capacity_mwh=None)])

    assert composition.is_complete is False
    assert "ROUTE_CAPACITY_UNKNOWN:bbl-route" in composition.blockers


def test_route_target_outside_contract_allowlist_is_excluded() -> None:
    composition = _compose(
        contracts=_contracts("TTF"),
        routes=[_local_route(), _bbl_route()],
    )

    assert composition.is_complete is True
    assert "ROUTE_TARGET_NOT_ALLOWED_BY_CONTRACT:bbl-route" in composition.warnings
    assert all(option.destination_node == "node-ttf" for option in composition.sale_options)


def test_tariff_outside_gas_day_is_not_selected() -> None:
    old_gas_day = date(2025, 1, 1)
    old_now = datetime(2025, 1, 1, 12, 0, tzinfo=UTC)
    market = [
        MarketObservationFact(
            observation_id=f"market-{target.lower()}-2025",
            market_venue="EEX",
            product=f"{target} Day-Ahead",
            price=32.0,
            unit="EUR/MWh",
            currency="EUR",
            period_start_utc=old_gas_day - timedelta(days=1),
            period_end_utc=old_gas_day + timedelta(days=1),
            observed_at_utc=old_now,
            source_system="EEX_Sim",
            source_reference="simulated:test",
            freshness="simulated_live",
            quality_score=0.9,
            simulated=True,
            metadata_json={"hub": target, "tenor": "day-ahead"},
        )
        for target in ("TTF", "NBP")
    ]
    fx = [
        FxObservationFact(
            observation_id="fx-eur-gbp-2025",
            pair="EURGBP",
            base_currency="EUR",
            quote_currency="GBP",
            rate=0.85,
            value_date="2025-01-01",
            observed_at_utc=old_now,
            source_system="ECB",
            source_reference="ecb:eurofxref",
        )
    ]

    composition = compose_portfolio_network(
        contracts=_contracts("NBP", "TTF"),
        routes=[_local_route(), _bbl_route()],
        nodes=_nodes(),
        tariffs=TARIFFS,
        access_rows=_access(),
        market_rows=market,
        fx_rows=fx,
        gas_day=old_gas_day,
        now_utc=old_now,
    )

    assert composition.is_complete is False
    assert any(
        blocker.startswith("ROUTE_COST_MISSING") for blocker in composition.blockers
    )


def test_unsupported_product_or_firmness_fails_explicitly() -> None:
    common = dict(
        contracts=_contracts("NBP", "TTF"),
        routes=[_local_route()],
        nodes=_nodes(),
        tariffs=TARIFFS,
        access_rows=_access(),
        market_rows=[_market("TTF")],
        fx_rows=_fx(),
        gas_day=GAS_DAY,
        now_utc=NOW,
    )
    with pytest.raises(ValueError, match="unsupported capacity_product"):
        compose_portfolio_network(**common, capacity_product="UNKNOWN")
    with pytest.raises(ValueError, match="unsupported firmness"):
        compose_portfolio_network(**common, firmness="UNKNOWN")


def test_blocked_composition_never_reaches_solver() -> None:
    composition = _compose(routes=[_local_route(), _bbl_route()], access=[])

    with pytest.raises(ValueError, match="composition is blocked"):
        optimize_composed_portfolio_network(composition)
