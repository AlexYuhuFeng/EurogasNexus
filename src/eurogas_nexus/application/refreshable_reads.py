"""Market reads a spreadsheet can refresh: flat rows, fixed columns (DATA-1, lesson P7).

Excel's Power Query (and any BI tool or loader) refreshes ``GET /api/market/prices``,
``/api/market/observations`` and ``/api/market/fx`` with ``format=csv``: one header line in
the fixed order below, one row per figure, nested values written as JSON text, UTF-8 with a
byte-order mark. The header is the same whether or not there are rows and whether or not
``as_of`` was given (the version columns are then empty), so a query built once keeps
working. ``format=json`` (the default) answers exactly as before.

The CSV is a file, so it goes through ``api/csv_export``: entitlement and licensed-use
metering are the reads' own (``market_reads.row_allowed``), and the export decision of
GOV-1 is applied to the licensed families the rows came from (403 ``export_denied`` when a
family's export terms are not registered; ``X-Eurogas-Export-Decision: restricted`` and its
restrictions when they forbid redistribution). The how-to is ``docs/sdk/POWER_QUERY.md``.

DATA-1：可在 Excel Power Query 中刷新的平面读取（固定列序，CSV 或 JSON）。
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

#: ``format`` values the refreshable reads accept.
REFRESH_FORMAT_PATTERN = "^(json|csv)$"

FORMAT_DESCRIPTION = (
    "json (default, the enveloped read) or csv (flat rows, fixed header, for Excel Power "
    "Query and loaders; the GOV-1 export decision applies)"
)

#: The version of a figure as read with ``as_of`` (``KnownVersion.as_fields`` and the instant).
VERSION_COLUMNS: tuple[str, ...] = (
    "revision",
    "revision_basis",
    "published_at_utc",
    "known_from_utc",
    "revision_event_id",
    "as_of_utc",
)

#: ``/api/market/observations?format=csv`` columns, in order (additions go at the end).
OBSERVATION_COLUMNS: tuple[str, ...] = (
    "observation_id",
    "market_venue",
    "product",
    "price",
    "unit",
    "currency",
    "period_start_utc",
    "period_end_utc",
    "observed_at_utc",
    "source_system",
    "source_reference",
    "source_record_id",
    "freshness",
    "quality_score",
    "entitlement_scope",
    "research_only",
    *VERSION_COLUMNS,
    "metadata_json",
)

#: ``/api/market/fx?format=csv`` columns, in order (additions go at the end).
FX_COLUMNS: tuple[str, ...] = (
    "observation_id",
    "pair",
    "base_currency",
    "quote_currency",
    "rate",
    "rate_type",
    "value_date",
    "observed_at_utc",
    "source_system",
    "source_reference",
    "freshness",
    "entitlement_scope",
    "research_only",
    *VERSION_COLUMNS,
)


def flat_rows(
    rows: Iterable[Mapping[str, Any]], columns: Sequence[str]
) -> list[dict[str, Any]]:
    """Each row cut to ``columns``, in order; a column a row lacks is empty."""

    return [{name: row.get(name) for name in columns} for row in rows]


__all__ = [
    "FORMAT_DESCRIPTION",
    "FX_COLUMNS",
    "OBSERVATION_COLUMNS",
    "REFRESH_FORMAT_PATTERN",
    "VERSION_COLUMNS",
    "flat_rows",
]
