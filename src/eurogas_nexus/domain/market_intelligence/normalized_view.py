"""Backend-owned normalization for the shared market view.

The Web client historically re-implemented FX conversion, hub/tenor extraction,
and gas-price detection in TypeScript (`marketPriceNormalization.ts`). This
module is the backend contract for those semantics so clients consume
normalized rows instead of re-deriving them.

Semantics are pinned to the legacy frontend behavior so the migration is
value-identical:

- latest FX rate per currency pair is chosen by ``observed_at_utc``;
- cross-currency conversion walks the rate graph breadth-first with a maximum
  depth of three edges and returns the first path to the target currency;
- hub extraction prefers ``metadata_json.hub``, then the first whitespace token
  of ``product``, then ``market_venue``;
- tenor extraction prefers ``metadata_json.tenor``, then the full ``product``;
- a gas-price observation has a unit containing ``MWH`` and a three-letter
  currency code.
"""

from __future__ import annotations

import re
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

TARGET_CURRENCY = "GBP"
MAX_CONVERSION_DEPTH = 3


@dataclass(frozen=True)
class FxRateInput:
    """Minimal FX rate record for normalization."""

    pair: str = ""
    base_currency: str | None = None
    quote_currency: str | None = None
    rate: float = 0.0
    observed_at_utc: str | None = None


@dataclass(frozen=True)
class MarketObservationInput:
    """Minimal market observation record for normalization."""

    market_venue: str
    product: str
    price: float
    currency: str
    unit: str | None = None
    observed_at_utc: str | None = None
    period_start_utc: str | None = None
    metadata_json: dict[str, Any] = field(default_factory=dict)


def normalized_currency(value: str | None) -> str:
    return (value or "").strip().upper()


def _timestamp_ms(value: str | None) -> float:
    if not value:
        return 0.0
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def _rate_currencies(rate: FxRateInput) -> tuple[str, str] | None:
    pair = re.sub(r"[^A-Za-z]", "", rate.pair).upper()
    base = normalized_currency(rate.base_currency) or pair[:3]
    quote = normalized_currency(rate.quote_currency) or pair[3:6]
    if len(base) == 3 and len(quote) == 3:
        return base, quote
    return None


def latest_fx_edges(rates: list[FxRateInput]) -> dict[str, list[tuple[str, float]]]:
    """Build an undirected latest-rate graph: currency -> [(target, multiplier)]."""

    latest: dict[tuple[str, str], FxRateInput] = {}
    for rate in rates:
        currencies = _rate_currencies(rate)
        if currencies is None:
            continue
        value = rate.rate
        if not _is_positive_finite(value):
            continue
        key = currencies
        current = latest.get(key)
        if current is None or _timestamp_ms(rate.observed_at_utc) > _timestamp_ms(
            current.observed_at_utc
        ):
            latest[key] = rate

    graph: dict[str, list[tuple[str, float]]] = {}
    for rate in latest.values():
        currencies = _rate_currencies(rate)
        if currencies is None:
            continue
        base, quote = currencies
        graph.setdefault(base, []).append((quote, rate.rate))
        graph.setdefault(quote, []).append((base, 1.0 / rate.rate))
    return graph


def convert_currency(
    value: float,
    source_currency: str,
    target_currency: str,
    rates: list[FxRateInput],
) -> float | None:
    """Convert a value across the latest FX graph (BFS, max 3 edges)."""

    if not _is_finite_number(value):
        return None
    source = normalized_currency(source_currency)
    target = normalized_currency(target_currency)
    if not source or not target:
        return None
    if source == target:
        return value

    graph = latest_fx_edges(rates)
    queue: deque[tuple[str, float, int]] = deque([(source, value, 0)])
    visited = {source}
    while queue:
        current, converted, depth = queue.popleft()
        if depth >= MAX_CONVERSION_DEPTH:
            continue
        for currency, multiplier in graph.get(current, []):
            next_value = converted * multiplier
            if currency == target:
                return next_value
            if currency in visited:
                continue
            visited.add(currency)
            queue.append((currency, next_value, depth + 1))
    return None


def observation_hub(observation: MarketObservationInput) -> str:
    metadata_hub = (observation.metadata_json or {}).get("hub")
    if isinstance(metadata_hub, str) and metadata_hub.strip():
        return metadata_hub.strip()
    product_hub = observation.product.strip().split()[0] if observation.product.strip() else ""
    return product_hub or observation.market_venue


def observation_tenor(observation: MarketObservationInput) -> str:
    metadata_tenor = (observation.metadata_json or {}).get("tenor")
    if isinstance(metadata_tenor, str) and metadata_tenor.strip():
        return metadata_tenor.strip().lower()
    return observation.product.strip().lower()


def is_gas_price_observation(observation: MarketObservationInput) -> bool:
    unit = (observation.unit or "").upper()
    return "MWH" in unit and len(normalized_currency(observation.currency)) == 3


def normalize_observation(
    observation: MarketObservationInput,
    rates: list[FxRateInput],
) -> dict[str, Any]:
    """Return the observation row with backend-owned normalization fields."""

    gas_price = is_gas_price_observation(observation)
    price_gbp_mwh = (
        convert_currency(observation.price, observation.currency, TARGET_CURRENCY, rates)
        if gas_price
        else None
    )
    return {
        "market_venue": observation.market_venue,
        "product": observation.product,
        "price": observation.price,
        "unit": observation.unit,
        "currency": observation.currency,
        "observed_at_utc": observation.observed_at_utc,
        "period_start_utc": observation.period_start_utc,
        "hub": observation_hub(observation),
        "tenor": observation_tenor(observation),
        "is_gas_price": gas_price,
        "price_gbp_mwh": price_gbp_mwh,
    }


def build_normalized_market_view(
    observations: list[MarketObservationInput],
    fx_rates: list[FxRateInput],
) -> dict[str, Any]:
    """Build the normalized market view with per-row conversion status."""

    rows: list[dict[str, Any]] = []
    warnings: list[str] = []
    for observation in observations:
        row = normalize_observation(observation, fx_rates)
        if row["is_gas_price"] and row["price_gbp_mwh"] is None:
            warnings.append(
                f"FX conversion unavailable for observation "
                f"{observation.market_venue}/{observation.product} "
                f"({observation.currency}->{TARGET_CURRENCY})."
            )
        rows.append(row)
    return {"rows": rows, "warnings": warnings}


def _is_positive_finite(value: float) -> bool:
    return _is_finite_number(value) and value > 0


def _is_finite_number(value: float) -> bool:
    return (
        isinstance(value, int | float)
        and value == value
        and abs(value) != float("inf")
    )
