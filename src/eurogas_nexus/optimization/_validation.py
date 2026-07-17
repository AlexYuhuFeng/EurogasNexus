"""Shared input validation for deterministic optimization models."""

from __future__ import annotations

import math
from collections.abc import Iterable

from .models import CapacityProduct, NetworkEdge, SaleOption, SupplyResource


def require_finite(value: float, label: str) -> None:
    if not math.isfinite(value):
        raise ValueError(f"{label} must be finite")


def require_unique(values: Iterable[str], label: str) -> None:
    seen: set[str] = set()
    for value in values:
        if value in seen:
            raise ValueError(f"duplicate {label}: {value}")
        seen.add(value)


def validate_network_edges(edges: list[NetworkEdge]) -> None:
    require_unique((edge.edge_id for edge in edges), "edge_id")
    for edge in edges:
        if not edge.edge_id.strip():
            raise ValueError("edge_id must not be empty")
        if not edge.source.strip() or not edge.target.strip():
            raise ValueError(f"edge nodes must not be empty: {edge.edge_id}")
        require_finite(edge.tariff_gbp_mwh, f"tariff for {edge.edge_id}")
        require_finite(edge.available_capacity_mwh, f"capacity for {edge.edge_id}")
        if edge.tariff_gbp_mwh < 0:
            raise ValueError(f"tariff must be non-negative: {edge.edge_id}")
        if edge.available_capacity_mwh < 0:
            raise ValueError(f"capacity must be non-negative: {edge.edge_id}")


def validate_supply_resources(resources: list[SupplyResource]) -> None:
    require_unique((resource.resource_id for resource in resources), "resource_id")
    for resource in resources:
        if not resource.resource_id.strip():
            raise ValueError("resource_id must not be empty")
        require_finite(resource.available_mwh, f"available quantity for {resource.resource_id}")
        require_finite(resource.unit_cost_gbp_mwh, f"unit cost for {resource.resource_id}")
        require_finite(resource.minimum_take_mwh, f"minimum take for {resource.resource_id}")
        if resource.maximum_take_mwh is not None:
            require_finite(
                resource.maximum_take_mwh,
                f"maximum take for {resource.resource_id}",
            )
        if resource.available_mwh < 0 or resource.minimum_take_mwh < 0:
            raise ValueError("Resource quantities must be non-negative")
        if resource.maximum_take_mwh is not None and resource.maximum_take_mwh < 0:
            raise ValueError("Resource quantities must be non-negative")
        if resource.minimum_take_mwh > resource.effective_maximum_mwh:
            raise ValueError(f"minimum take exceeds maximum for {resource.resource_id}")
        if resource.source_node is not None and not resource.source_node.strip():
            raise ValueError(f"source_node must not be empty for {resource.resource_id}")
        if any(not tso.strip() for tso in resource.required_tso_access):
            raise ValueError(f"required TSO access must not be empty for {resource.resource_id}")


def validate_sale_options(sale_options: list[SaleOption]) -> None:
    require_unique((option.option_id for option in sale_options), "option_id")
    for option in sale_options:
        if not option.option_id.strip():
            raise ValueError("option_id must not be empty")
        if not option.destination_node.strip():
            raise ValueError(f"destination_node must not be empty for {option.option_id}")
        require_finite(option.sale_price_gbp_mwh, f"sale price for {option.option_id}")
        require_finite(option.capacity_mwh, f"capacity for {option.option_id}")
        require_finite(option.variable_cost_gbp_mwh, f"variable cost for {option.option_id}")
        if option.capacity_mwh < 0:
            raise ValueError("Sale-option capacity must be non-negative")
        if any(not tso.strip() for tso in option.required_tso_access):
            raise ValueError(f"required TSO access must not be empty for {option.option_id}")


def validate_capacity_products(products: list[CapacityProduct]) -> None:
    require_unique((product.product_id for product in products), "product_id")
    for product in products:
        if not product.product_id.strip():
            raise ValueError("product_id must not be empty")
        require_finite(product.capacity_mwh, f"capacity for {product.product_id}")
        require_finite(product.fixed_cost_gbp, f"fixed cost for {product.product_id}")
        require_finite(
            product.variable_cost_gbp_mwh,
            f"variable cost for {product.product_id}",
        )
        if (
            product.capacity_mwh < 0
            or product.fixed_cost_gbp < 0
            or product.variable_cost_gbp_mwh < 0
        ):
            raise ValueError("Capacity-product quantities and costs must be non-negative")
        if product.firmness not in {"firm", "interruptible"}:
            raise ValueError(f"invalid firmness for {product.product_id}")
