"""Spreadsheet formula-injection neutralisation for every export (security review M4).

A text cell that begins with ``=``, ``+``, ``-``, ``@``, a tab or a carriage return is run as a
formula by Excel and LibreOffice when a CSV is opened. Values from outside sources reach
exports (counterparty names, news titles, REMIT text, imported files), so such a cell is
prefixed with a single quote, as the OWASP CSV-injection guidance recommends. Numbers are
written as numbers and keep their sign: only text is changed.
"""

from __future__ import annotations

from typing import Any

FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def neutralise(value: Any) -> Any:
    """``value`` unchanged unless it is text a spreadsheet would run as a formula."""

    if isinstance(value, str) and value.startswith(FORMULA_PREFIXES):
        if value[0] in "+-":
            # A plain signed number written as text ("-12.5") is data, not a formula.
            try:
                float(value)
                return value
            except ValueError:
                pass
        return "'" + value
    return value
