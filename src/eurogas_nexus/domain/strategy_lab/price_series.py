"""Price-series evidence names and exact source-decimal access for research.

The name helpers are shared by market discovery and historical evaluation. The
source-price adapter applies the same bounded exact-decimal authority as the
normalized market view before strategy research does arithmetic.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from eurogas_nexus.domain.market_intelligence.source_price import (
    SourcePrice,
    resolve_source_price,
)


def source_price_for_series(row: Mapping[str, Any]) -> SourcePrice:
    """Resolve a stored/normalized market row's exact source price for research.

    Strategy research consumes the backend-normalized rows (or the stored rows
    they are built from). This adapter applies the same bounded
    :func:`resolve_source_price` authority as the normalized view, so research
    can obtain the exact EEX NGP decimal and its provenance before doing any
    financial arithmetic.

    Args:
        row: Mapping with ``source_system``, ``source_reference``, ``price``,
            ``unit``, ``currency`` and ``metadata_json`` fields. A normalized
            repository row carries all of them.

    Returns:
        The validated :class:`SourcePrice`; non-EEX or legacy rows report their
        float-only provenance instead of being called exact.
    """

    metadata = row.get("metadata_json")
    if not isinstance(metadata, Mapping):
        metadata = {}
    return resolve_source_price(
        source_system=_text_or_none(row.get("source_system")),
        source_reference=_text_or_none(row.get("source_reference")),
        numeric_price=row.get("price"),
        metadata=metadata,
        unit=_text_or_none(row.get("unit")),
        currency=_text_or_none(row.get("currency")),
    )


def exact_source_price_decimal(row: Mapping[str, Any]) -> Decimal | None:
    """Return a row's validated exact source ``Decimal``, or None.

    A None result is not a license to treat the row's float as exact: callers
    must inspect :func:`source_price_for_series` for the explicit status and
    issue when they need to decide how to handle the row.

    Args:
        row: Mapping accepted by :func:`source_price_for_series`.

    Returns:
        The exact Decimal only for a fully validated EEX NGP row.
    """

    source_price = source_price_for_series(row)
    return source_price.exact_decimal if source_price.is_exact else None


def _text_or_none(value: object) -> str | None:
    """Trimmed text or None (the source authority rejects non-strings itself)."""

    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def canonical_price_name(source_system: str, tenor: str) -> str:
    normalized_source = source_system.upper().replace("_SIM", "")
    normalized_tenor = tenor.replace("-", "_").replace(" ", "_").upper()
    if "ICE_OCM" in normalized_source:
        return "ICE_OCM"
    if "ICIS" in normalized_source or "HEREN" in normalized_source:
        return "ICIS_HEREN_DAY_AHEAD"
    if "SAP" in normalized_source:
        return "SAP"
    if "EEX" in normalized_source:
        return (
            "EEX_DAY_AHEAD"
            if "DAY_AHEAD" in normalized_tenor or "DAYAHEAD" in normalized_tenor
            else f"EEX_{normalized_tenor}"
        )
    return f"{normalized_source}_{normalized_tenor}"


def evidence_tenor_from_product(product: str) -> str:
    lowered = product.lower()
    if "within-day" in lowered or "withinday" in lowered:
        return "within-day"
    if "day-ahead" in lowered or "day ahead" in lowered:
        return "day-ahead"
    if "weekend" in lowered:
        return "weekend"
    if "month" in lowered:
        return "month-ahead"
    return lowered
