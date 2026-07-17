"""Input-integrity tests shared by the stable optimization models."""

from __future__ import annotations

import math

import pytest

from eurogas_nexus.optimization import (
    CapacityProduct,
    NetworkEdge,
    SaleOption,
    SupplyResource,
    find_min_cost_route,
    optimize_capacity_bookings,
    optimize_contract_dispatch,
    optimize_resource_pool,
)


def test_route_rejects_duplicate_edges_and_non_finite_capacity() -> None:
    duplicate_edges = [
        NetworkEdge("same", "A", "B", 1.0, 10.0),
        NetworkEdge("same", "B", "C", 1.0, 10.0),
    ]
    with pytest.raises(ValueError, match="duplicate edge_id"):
        find_min_cost_route(duplicate_edges, "A", "C", 1.0)

    with pytest.raises(ValueError, match="must be finite"):
        find_min_cost_route([], "A", "B", math.inf)


def test_resource_pool_rejects_duplicate_resource_and_option_ids() -> None:
    duplicate_resources = [
        SupplyResource("same", 10.0, 1.0),
        SupplyResource("same", 20.0, 2.0),
    ]
    with pytest.raises(ValueError, match="duplicate resource_id"):
        optimize_resource_pool(
            duplicate_resources,
            [SaleOption("sale", "NBP", 3.0, 30.0)],
        )

    duplicate_options = [
        SaleOption("same", "NBP", 3.0, 10.0),
        SaleOption("same", "TTF", 4.0, 10.0),
    ]
    with pytest.raises(ValueError, match="duplicate option_id"):
        optimize_resource_pool([SupplyResource("supply", 20.0, 1.0)], duplicate_options)


def test_capacity_optimizer_rejects_duplicate_products_and_invalid_numbers() -> None:
    products = [
        CapacityProduct("same", 10.0, 1.0),
        CapacityProduct("same", 20.0, 2.0),
    ]
    with pytest.raises(ValueError, match="duplicate product_id"):
        optimize_capacity_bookings(products, 5.0)

    with pytest.raises(ValueError, match="must be finite"):
        optimize_capacity_bookings([], math.nan)


def test_contract_dispatch_rejects_duplicate_resources_and_non_finite_price() -> None:
    resources = [
        SupplyResource("same", 10.0, 1.0),
        SupplyResource("same", 20.0, 2.0),
    ]
    with pytest.raises(ValueError, match="duplicate resource_id"):
        optimize_contract_dispatch(resources, 3.0, 10.0)

    with pytest.raises(ValueError, match="market_price_gbp_mwh must be finite"):
        optimize_contract_dispatch([SupplyResource("supply", 10.0, 1.0)], math.nan, 10.0)
