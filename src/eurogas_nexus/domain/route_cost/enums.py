"""Route-cost enum contracts (re-exported from the domain ontology).

The canonical definitions live in ``eurogas_nexus.domain.ontology.vocabulary``.
This module is a thin compatibility shim so existing importers keep working.
"""

from __future__ import annotations

from eurogas_nexus.domain.ontology.vocabulary import (
    BusinessModel,
    CapacityProduct,
    CostComponentType,
    DeliveryMode,
    Firmness,
    PointType,
    SourceResourceType,
    TariffDirection,
    TariffStatus,
)

__all__ = [
    "TariffStatus",
    "TariffDirection",
    "CapacityProduct",
    "Firmness",
    "PointType",
    "BusinessModel",
    "DeliveryMode",
    "SourceResourceType",
    "CostComponentType",
]
