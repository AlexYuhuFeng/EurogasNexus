"""Streaming package exports (optional boundary)."""

from eurogas_nexus.streaming.contracts import (
    MARKET_CHANGE_KIND,
    MARKET_CHANGE_SCHEMA_VERSION,
    MarketChangeV1,
    StreamingEnvelope,
    market_change_fields,
)

__all__ = [
    "MARKET_CHANGE_KIND",
    "MARKET_CHANGE_SCHEMA_VERSION",
    "MarketChangeV1",
    "StreamingEnvelope",
    "market_change_fields",
]
