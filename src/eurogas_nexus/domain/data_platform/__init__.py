"""Unified Data Platform domain layer (Architecture V2 Wave 4).

This package owns the business-facing data vocabulary of the Unified Data
Platform: the declared Data Product catalogue and the Analysis Snapshot
descriptor contract. It is pure Python - no web framework, no ORM, no network -
so both the API delivery layer and the repositories can consume it without a
circular dependency.

Authority: ``docs/engineering/Architecture-V2/07_DATA_PLATFORM.md`` sections 2,
3 and 6.
"""

from eurogas_nexus.domain.data_platform.products import (
    DATA_PRODUCTS,
    DataProduct,
    DataProductAvailability,
    DataProductConfidence,
    ProductEntitlement,
    ServedSurface,
    SurfaceKind,
    TimeBasis,
    data_products,
    evaluate_product_entitlement,
    product_by_id,
)
from eurogas_nexus.domain.data_platform.snapshots import (
    ACTIVE_CONTEXT_KEYS,
    ANALYSIS_SNAPSHOT_SCHEMA_VERSION,
    CONTEXT_FIELDS,
    DESCRIPTOR_FIELDS,
    UNSUPPORTED_ACTIVE_CONTEXT_KEYS,
    AvailabilityState,
    DescriptorFieldState,
    SnapshotDescriptor,
    descriptor_content_hash,
)

__all__ = [
    "ACTIVE_CONTEXT_KEYS",
    "ANALYSIS_SNAPSHOT_SCHEMA_VERSION",
    "CONTEXT_FIELDS",
    "DATA_PRODUCTS",
    "DESCRIPTOR_FIELDS",
    "UNSUPPORTED_ACTIVE_CONTEXT_KEYS",
    "AvailabilityState",
    "DataProduct",
    "DataProductAvailability",
    "DataProductConfidence",
    "DescriptorFieldState",
    "ProductEntitlement",
    "ServedSurface",
    "SnapshotDescriptor",
    "SurfaceKind",
    "TimeBasis",
    "data_products",
    "descriptor_content_hash",
    "evaluate_product_entitlement",
    "product_by_id",
]
