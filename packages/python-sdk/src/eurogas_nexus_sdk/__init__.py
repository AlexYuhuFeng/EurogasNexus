"""Eurogas Nexus Python SDK: typed API clients for /api.

Import typed clients from submodules, for example:

    from eurogas_nexus_sdk.reference_network import fetch_nodes, NodeDTO
    from eurogas_nexus_sdk.research import compute_route_cost, RouteCostResult
"""

from eurogas_nexus_sdk._transport import ResponseMeta, SdkProtocolError, SdkResult
from eurogas_nexus_sdk.health_client import HealthPayload, fetch_health  # noqa: F401

__all__ = [
    "HealthPayload",
    "ResponseMeta",
    "SdkProtocolError",
    "SdkResult",
    "fetch_health",
]
