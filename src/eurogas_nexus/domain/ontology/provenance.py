"""Is this row simulated? One answer for the whole product (backend audit O1, rule 17).

The question was answered in about 140 places by hand, under five rules that disagreed:
``source_system.endswith("_Sim")`` (most), that or ``metadata["simulated"]``
(``valuation_snapshot``, ``resource_pool``, ``optimization``), a case-insensitive suffix
(``reports.sections``), or the suffix or a ``demo`` prefix (``fx_forward``). A row the
demo seed marks ``simulated`` in its metadata under a plain source name (``DEMO``) was
therefore a market row to most readers. This module is the rule: simulated when the
metadata says so, when the source family is a ``*_Sim`` family (any case) or when it is
the demo desk's own ``DEMO`` source. ``tests/contract/test_simulated_rule.py`` keeps new
hand-written checks from appearing.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

SIMULATED_SUFFIX = "_sim"
#: The demo desk's own source name for rows it invents (deliveries, REMIT messages).
DEMO_SOURCE = "demo"


def is_simulated(source_system: str | None, metadata: Mapping[str, Any] | None = None) -> bool:
    """Whether a row is simulator- or demo-produced rather than read from a source."""

    if isinstance(metadata, Mapping) and metadata.get("simulated") is True:
        return True
    value = str(source_system or "").strip().casefold()
    return value.endswith(SIMULATED_SUFFIX) or value == DEMO_SOURCE or value.startswith(
        DEMO_SOURCE + "_"
    )


def is_simulated_row(row: Any) -> bool:
    """:func:`is_simulated` for an ORM row or a mapping with ``source_system``/``metadata``."""

    if isinstance(row, Mapping):
        source = row.get("source_system")
        metadata = row.get("metadata_json") or row.get("metadata")
    else:
        source = getattr(row, "source_system", None)
        metadata = getattr(row, "metadata_json", None)
    return is_simulated(source, metadata if isinstance(metadata, Mapping) else None)
