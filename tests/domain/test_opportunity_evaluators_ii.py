"""Evaluators II (CP-10): golden cases for T (storage) and R (re-route through the pool)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from eurogas_nexus.domain.opportunities.model import LegKind, OpportunityState
from eurogas_nexus.domain.opportunities.reroute import RerouteEvaluator
from eurogas_nexus.domain.opportunities.storage import StorageSpreadEvaluator, season_pair
from eurogas_nexus.domain.opportunities.testing import (
    assert_legs,
    assert_reconciles,
    fixture_snapshot,
    run,
)
from eurogas_nexus.domain.route_cost.resource_pool import (
    PortfolioOptimizationScenario,
    PortfolioResource,
    PortfolioSaleOption,
    optimize_resource_pool,
)
from eurogas_nexus.domain.valuation.quality import InputClass
from eurogas_nexus.domain.valuation.snapshot import (
    InputKind,
    SnapshotInput,
    assumption_key,
    price_key,
)

AS_OF = datetime(2026, 11, 17, 9, 42, tzinfo=UTC)
D = Decimal
SUM27, WIN27 = season_pair(AS_OF.date())


def _in(key, kind, value, unit="", currency=None, klass=InputClass.SOURCED, family="EEX", **d):
    return SnapshotInput(
        key=key,
        kind=kind,
        input_class=klass,
        value=None if value is None else D(str(value)),
        unit=unit,
        currency=currency,
        as_of_utc=AS_OF,
        source_family=family,
        source_ref=f"ref:{key}",
        label=key,
        detail=d,
    )


def _assume(key, value, unit, currency=None):
    return _in(
        assumption_key(key),
        InputKind.ASSUMPTION,
        value,
        unit,
        currency,
        InputClass.ASSUMPTION,
        "operator-input",
        set_by="desk",
        set_at_utc="2026-11-01T00:00:00+00:00",
    )


def test_golden_summer_into_winter_storage_not_held_is_watch() -> None:
    """Design B.4: Win-27 31.50 - Sum-27 28.00 = 3.50 gross. Storage not held (firm's tariff):
    capacity 2.20, injection 0.20, withdrawal 0.15, fuel 1 % x 28.00 = 0.28, financing
    28.00 x 3.0 % x 183 / 365 = 0.421151 (the engine counts the days between the period
    starts; the design's 0.42 is half a year), network charges 0.20. Costs 3.451151,
    net 0.048849 EUR/MWh: below the 0.10 minimum -> watch.
    Volume: a TTF supply of 10,000 MWh/d over the 183 summer days = 1,830,000 MWh.
    """

    assert (SUM27.label, WIN27.label) == ("SUM-27", "WIN-27")
    inputs = [
        _in(price_key("TTF", SUM27, "ask"), InputKind.PRICE, "28.00", "EUR/MWh", "EUR"),
        _in(price_key("TTF", WIN27, "bid"), InputKind.PRICE, "31.50", "EUR/MWh", "EUR"),
        _assume("storage.capacity_fee", "2.20", "EUR/MWh", "EUR"),
        _assume("storage.injection_fee", "0.20", "EUR/MWh", "EUR"),
        _assume("storage.withdrawal_fee", "0.15", "EUR/MWh", "EUR"),
        _assume("storage.fuel", "1", "%"),
        _assume("storage.network_charges", "0.20", "EUR/MWh", "EUR"),
        _assume("financing.rate", "3.0", "%/yr"),
        _in(
            "contracts:norsk",
            InputKind.BOOK,
            10000,
            "MWh/d",
            family="operator-input",
            contract_id="norsk",
            hub="TTF",
            book_id="book-1",
        ),
    ]
    ((candidate, assessment),) = run(
        StorageSpreadEvaluator(), fixture_snapshot(inputs, as_of=AS_OF), as_of=AS_OF
    )
    assert_legs(
        candidate,
        [
            ("storage.withdraw", "31.50"),
            ("storage.inject", "-28.00"),
            ("storage.capacity_fee", "-2.20"),
            ("storage.injection_fee", "-0.20"),
            ("storage.withdrawal_fee", "-0.15"),
            ("storage.fuel", "-0.28"),
            ("storage.network", "-0.20"),
            ("storage.financing", "-0.421151"),
        ],
    )
    assert_reconciles(candidate)
    assert candidate.headline.value == D("0.048849")
    assert candidate.volume.value == D("1830000.0")
    assert assessment.state is OpportunityState.WATCH
    assert "margin_below_minimum" in assessment.reasons
    assert candidate.quality is InputClass.ASSUMPTION


def test_held_storage_sinks_the_capacity_fee_and_uses_the_round_trip_loss() -> None:
    """Held facility at TTF: working gas 500,000 MWh, injection 5,000 MWh/d, withdrawal
    10,000 MWh/d, efficiencies 0.99 x 0.99 (loss 1.99 %), fees 0.10 + 0.08 GBP/MWh at EUR/GBP
    1/0.85 (the record is in GBP). Volume = min(500,000; 5,000 x 183; 10,000 x 182) = 500,000.
    Net = 3.50 - 0.117647 - 0.094118 - 0.5572 - 0.421151 = 2.309884 EUR/MWh.
    """

    inputs = [
        _in(price_key("TTF", SUM27, "ask"), InputKind.PRICE, "28.00", "EUR/MWh", "EUR"),
        _in(price_key("TTF", WIN27, "bid"), InputKind.PRICE, "31.50", "EUR/MWh", "EUR"),
        _assume("financing.rate", "3.0", "%/yr"),
        _in(
            "storage:ugs-1",
            InputKind.BOOK,
            500000,
            "MWh",
            family="operator-input",
            facility_id="ugs-1",
            name="Demo UGS",
            hub="TTF",
            working_gas_mwh="500000",
            max_injection_mwh_per_day="5000",
            max_withdrawal_mwh_per_day="10000",
            injection_efficiency="0.99",
            withdrawal_efficiency="0.99",
            injection_fee="0.10",
            withdrawal_fee="0.08",
            fee_currency="GBP",
        ),
        _in("fx:GBPEUR:SUM-27", InputKind.FX, "1.1764705882", "EUR/GBP", "EUR", family="ECB"),
    ]
    produced = run(StorageSpreadEvaluator(), fixture_snapshot(inputs, as_of=AS_OF), as_of=AS_OF)
    ((candidate, assessment),) = [pair for pair in produced if pair[0].period == SUM27]
    assert_reconciles(candidate)
    assert candidate.headline.value == D("2.309884")
    assert candidate.volume.value == D("500000.0")
    assert not any(leg.label_key == "storage.capacity_fee" for leg in candidate.legs)
    assert assessment.state is OpportunityState.WATCH  # ratchets are "not assessed"
    assert "check_not_assessed" in assessment.reasons


def _pool_rows():
    resource = dict(
        resource_id="nbp-supply",
        resource_name="NBP supply",
        resource_type="PIPELINE_IMPORT",
        delivery_mode="VIRTUAL_HUB_SALE",
        location_point_name="NBP",
        available_quantity_mwh_per_day=10000.0,
        contract_cost_gbp_mwh=30.0,
        contract_cost_currency="GBP",
        contract_cost_unit="GBP/MWh",
        upstream_payment_lag_days=0,
        annual_financing_rate_pct=0.0,
    )
    local = dict(
        option_id="local-nbp",
        label="Sell at NBP",
        delivery_mode="VIRTUAL_HUB_SALE",
        target_point_name="NBP",
        route_topology_kind="LOCAL_MARKET_DISPOSITION",
        sale_price_gbp_mwh=31.0,
        sale_price_currency="GBP",
        sale_price_unit="GBP/MWh",
        route_cost_gbp_mwh=0.0,
        capacity_status="NOT_REQUIRED",
        screen_sale_cash_lag_days=0,
    )
    routed = dict(
        option_id="route-x",
        label="Route to market X",
        delivery_mode="VIRTUAL_HUB_SALE",
        target_point_name="X",
        route_topology_kind="NETWORK_ROUTE",
        sale_price_gbp_mwh=33.5,
        sale_price_currency="GBP",
        sale_price_unit="GBP/MWh",
        route_cost_gbp_mwh=1.2,
        capacity_limit_mwh_per_day=6000.0,
        capacity_status="KNOWN",
        screen_sale_cash_lag_days=0,
    )
    return resource, local, routed


def test_golden_reroute_equals_the_optimisers_delta() -> None:
    """Local only: 10,000 x (31.00 - 30.00) = GBP 10,000/d. With the route: 6,000 x
    (33.50 - 1.20 - 30.00) + 4,000 x 1.00 = GBP 17,800/d. Delta = GBP 7,800/d, exactly the
    optimiser's own difference (zero payment lags: no early-cash term)."""

    resource, local, routed = _pool_rows()
    rows = [
        _in(
            "resource_pool:resource:nbp-supply",
            InputKind.BOOK,
            10000,
            "MWh/d",
            family="operator-input",
            row_kind="resource",
            **resource,
        ),
        _in(
            "resource_pool:option:local-nbp",
            InputKind.BOOK,
            None,
            "",
            family="EEX",
            klass=InputClass.INDICATIVE,
            row_kind="option",
            **local,
        ),
        _in(
            "resource_pool:option:route-x",
            InputKind.BOOK,
            None,
            "",
            family="EEX",
            klass=InputClass.INDICATIVE,
            row_kind="option",
            **routed,
        ),
    ]
    rows[1] = SnapshotInput(**{**rows[1].__dict__, "value": D(0)})
    rows[2] = SnapshotInput(**{**rows[2].__dict__, "value": D(0)})
    fx = _in("fx:GBPEUR:" + "x", InputKind.FX, "1", "EUR/GBP")
    ((candidate, assessment),) = run(
        RerouteEvaluator(), fixture_snapshot([*rows, fx], as_of=AS_OF), as_of=AS_OF
    )
    full = optimize_resource_pool(
        PortfolioOptimizationScenario(
            portfolio_id="t",
            resources=[PortfolioResource(**resource)],
            sale_options=[PortfolioSaleOption(**local), PortfolioSaleOption(**routed)],
            annual_financing_rate_pct=0.0,
        )
    )
    base = optimize_resource_pool(
        PortfolioOptimizationScenario(
            portfolio_id="t",
            resources=[PortfolioResource(**resource)],
            sale_options=[PortfolioSaleOption(**local)],
            annual_financing_rate_pct=0.0,
        )
    )
    expected = D(str(round(full.total_net_pnl_gbp_per_day - base.total_net_pnl_gbp_per_day, 6)))
    assert candidate.headline.value == expected == D("7800")
    assert_reconciles(candidate)
    assert [leg.kind for leg in candidate.legs].count(LegKind.CONVERSION) >= 1
    assert candidate.value.value == D("7800.00") and candidate.value.unit == "GBP"
    assert assessment.claim_text.startswith(
        "Gas day 2026-11-18: routing 6,000 MWh/d of the pool (nbp-supply to Route to market X) "
        "earns GBP 7,800.00 per day over the pool's local sales only"
    )
