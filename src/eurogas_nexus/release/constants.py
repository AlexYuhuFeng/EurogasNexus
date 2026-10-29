"""Build-time compatibility and engine constants exposed by the API.

``BACKTEST_ENGINE_VERSION`` remains the deterministic legacy engine/1 helper
identity; the public application historical run executes
``TARGET_BACKTEST_ENGINE_VERSION`` (engine/2). Release metadata advertises both
rather than relabelling stored engine/1 results.
"""

from __future__ import annotations

from eurogas_nexus.domain.backtest.contracts import (
    BACKTEST_ENGINE_VERSION,
    TARGET_BACKTEST_ENGINE_VERSION,
)
from eurogas_nexus.domain.strategy_lab.registry import (
    RUN_SCHEMA_VERSION,
    STRATEGY_SCHEMA_VERSION,
)
from eurogas_nexus.version import APPLICATION_VERSION

API_CONTRACT_VERSION = "api-contract/v1"
DB_SCHEMA_REVISION = "0044_entsog_native_rates"
MINIMUM_SUPPORTED_CLIENT_VERSION = APPLICATION_VERSION
MINIMUM_SUPPORTED_SERVER_VERSION = APPLICATION_VERSION
SOLVER_VERSION = "min-cost-flow/v1"

#: The legacy engine/1 helper identity, under the name release metadata uses.
LEGACY_BACKTEST_ENGINE_VERSION = BACKTEST_ENGINE_VERSION

__all__ = [
    "API_CONTRACT_VERSION",
    "BACKTEST_ENGINE_VERSION",
    "DB_SCHEMA_REVISION",
    "LEGACY_BACKTEST_ENGINE_VERSION",
    "MINIMUM_SUPPORTED_CLIENT_VERSION",
    "MINIMUM_SUPPORTED_SERVER_VERSION",
    "RUN_SCHEMA_VERSION",
    "SOLVER_VERSION",
    "STRATEGY_SCHEMA_VERSION",
    "TARGET_BACKTEST_ENGINE_VERSION",
]
