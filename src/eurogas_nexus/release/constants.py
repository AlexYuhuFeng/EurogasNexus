"""Build-time compatibility and engine constants exposed by the API."""

from __future__ import annotations

from eurogas_nexus.domain.backtest.contracts import BACKTEST_ENGINE_VERSION
from eurogas_nexus.domain.strategy_lab.registry import (
    RUN_SCHEMA_VERSION,
    STRATEGY_SCHEMA_VERSION,
)
from eurogas_nexus.version import APPLICATION_VERSION

API_CONTRACT_VERSION = "api-contract/v1"
DB_SCHEMA_REVISION = "0030_reliability_indexes"
MINIMUM_SUPPORTED_CLIENT_VERSION = APPLICATION_VERSION
MINIMUM_SUPPORTED_SERVER_VERSION = APPLICATION_VERSION
SOLVER_VERSION = "min-cost-flow/v1"

__all__ = [
    "API_CONTRACT_VERSION",
    "BACKTEST_ENGINE_VERSION",
    "DB_SCHEMA_REVISION",
    "MINIMUM_SUPPORTED_CLIENT_VERSION",
    "MINIMUM_SUPPORTED_SERVER_VERSION",
    "RUN_SCHEMA_VERSION",
    "SOLVER_VERSION",
    "STRATEGY_SCHEMA_VERSION",
]
