"""The monthly price strip of a few hubs, live or as known at an instant (DATA-1).

One flat row per hub and delivery month: the P-08 price (``application/price_resolver``) for
that month, with its kind, source, age and the version it was (revision, publication time,
when this store first held it). A month with no price held is still a row, with empty price
fields, so a spreadsheet that refreshes the strip keeps its shape (Power Query, lesson P7).

Simulated prices are left out unless asked for (AGENTS.md rule 17: no simulated price that
can be read as a market price); a row that carries one says so in ``simulated``.

DATA-1：按枢纽与交割月份输出的平面价格曲线（实时或“某一时刻已知”）。
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta
from typing import Any

#: The strip's columns, in order; stable across releases (additions go at the end).
PRICE_STRIP_COLUMNS: tuple[str, ...] = (
    "hub",
    "month",
    "period_start",
    "period_end",
    "side",
    "value",
    "unit",
    "value_mwh",
    "unit_mwh",
    "kind",
    "source_system",
    "price_as_of_utc",
    "state",
    "simulated",
    "basis",
    "reference",
    "revision",
    "revision_basis",
    "published_at_utc",
    "known_from_utc",
    "as_of_utc",
)

MAX_HUBS = 20
MAX_MONTHS = 36


class PriceStripError(ValueError):
    """A strip that cannot be read as asked; ``code`` is the API error code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def strip_hubs(values: Iterable[str]) -> list[str]:
    """The canonical hub codes asked for (repeated or comma-separated); refuses unknown ones."""

    from eurogas_nexus.domain.ontology.identity import resolve_hub

    asked = [part.strip() for value in values for part in str(value).split(",") if part.strip()]
    if not asked:
        raise PriceStripError("hub_required", "name at least one hub, e.g. hub=TTF")
    hubs: list[str] = []
    for text in asked:
        resolution = resolve_hub(text)
        if not resolution.resolved or resolution.hub is None:
            raise PriceStripError("hub_unknown", f"{text!r} is not a known gas hub")
        code = resolution.hub.upper()
        if code not in hubs:
            hubs.append(code)
    if len(hubs) > MAX_HUBS:
        raise PriceStripError("too_many_hubs", f"at most {MAX_HUBS} hubs per read")
    return hubs


def strip_months(start: str | None, months: int, *, at: datetime) -> list[date]:
    """First days of ``months`` delivery months from ``start`` (``YYYY-MM``; default: ``at``'s)."""

    if not 1 <= months <= MAX_MONTHS:
        raise PriceStripError("months_out_of_range", f"months must be 1 to {MAX_MONTHS}")
    if start:
        try:
            first = date(int(start[:4]), int(start[5:7]), 1)
            if len(start) != 7 or start[4] != "-":
                raise ValueError(start)
        except (ValueError, IndexError):
            raise PriceStripError("start_invalid", "start must be a month, YYYY-MM") from None
    else:
        first = at.astimezone(UTC).date().replace(day=1)
    out = [first]
    while len(out) < months:
        out.append((out[-1].replace(day=28) + timedelta(days=4)).replace(day=1))
    return out


def _month_end(first: date) -> date:
    return (first.replace(day=28) + timedelta(days=4)).replace(day=1)


def price_strip_rows(
    session,
    who: Any,
    *,
    hubs: list[str],
    months: list[date],
    as_of: datetime | None,
    side: str = "mid",
    include_simulated: bool = False,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """One row per hub and month (hub order as asked, months ascending)."""

    from eurogas_nexus.application.as_of_reads import firm_mark_version
    from eurogas_nexus.application.price_resolver import open_price_book, price_payload
    from eurogas_nexus.domain.market.price_resolution import FIRM_MARK

    instant = as_of or now or datetime.now(UTC)
    book = open_price_book(
        session,
        who,
        now=instant,
        hubs=hubs,
        allow_simulated=include_simulated,
        known_at=as_of,
        with_versions=True,
    )
    rows: list[dict[str, Any]] = []
    for hub in hubs:
        for first in months:
            resolved = book.resolve(hub, first, _month_end(first), side=side)
            payload = price_payload(resolved) or {}
            row: dict[str, Any] = {name: None for name in PRICE_STRIP_COLUMNS}
            row.update(
                {
                    "hub": hub,
                    "month": first.strftime("%Y-%m"),
                    "period_start": first.isoformat(),
                    "period_end": _month_end(first).isoformat(),
                    "side": side,
                    "as_of_utc": instant.isoformat(),
                }
            )
            if payload:
                for name in (
                    "value",
                    "unit",
                    "value_mwh",
                    "unit_mwh",
                    "kind",
                    "source_system",
                    "state",
                    "simulated",
                    "basis",
                    "reference",
                ):
                    row[name] = payload.get(name)
                row["price_as_of_utc"] = payload.get("as_of_utc")
                version = book.versions.get(resolved.reference)
                if version is None and resolved.kind == FIRM_MARK:
                    version = firm_mark_version(session, resolved.reference)
                if version is not None:
                    fields = version.as_fields()
                    for name in ("revision", "revision_basis", "published_at_utc"):
                        row[name] = fields[name]
                    row["known_from_utc"] = fields["known_from_utc"]
            rows.append(row)
    return rows


__all__ = [
    "MAX_HUBS",
    "MAX_MONTHS",
    "PRICE_STRIP_COLUMNS",
    "PriceStripError",
    "price_strip_rows",
    "strip_hubs",
    "strip_months",
]
