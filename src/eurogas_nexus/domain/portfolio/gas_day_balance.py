"""What one trader has to clear at each hub on one gas day: IN, OUT and the net, split by owner.

Every gas day the firm's inputs at a hub (contract and upstream deliveries, LNG send-out,
storage withdrawal, imports on held capacity, purchases) must equal its outputs (sales,
customer offtake, storage injection, exports). What is left at the end of the gas day is
cashed out by the TSO. This module is the arithmetic only: the lines come from the firm's
own records (``application/gas_day``) and nothing here nominates or trades.

**Who clears a line.** A line belongs to its book. A *delegation* hands part (``mwh``) or all
of one line, or a book's whole position at a hub (``ref`` None), to one trader for the day.
A trader's view holds the undelegated part of the lines in the books his mandate covers, plus
whatever is delegated to him; a view without a trader (operations, the desk head, risk) holds
every line it may see, with each delegated part attributed. Delegated parts never count
twice: what one trader receives is what the book's owner no longer holds.

**Sign.** Net = IN − OUT; positive is long (gas to sell or inject before the day ends),
negative is short (gas to buy).

燃气日平衡：按枢纽汇总流入/流出与净头寸，委派部分按交易员拆分，不重复计算。
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field, replace

IN = "in"
OUT = "out"
#: A net within this many MWh is balanced (rounding of nominations, not a position).
FLAT_MWH = 0.5


@dataclass(frozen=True)
class LineAdjustment:
    """Something that changed a line's quantity, with its source and id (an outage)."""

    kind: str  # "outage"
    source: str  # "REMIT"
    ref: str  # the message id
    label: str  # the asset
    #: MWh taken off the line for the gas day (0 when the line was already below the cap).
    mwh: float
    #: Share of the asset out (unavailable / technical) and of the gas day it covers.
    share: float
    day_share: float
    version: int | None = None
    source_reference: str | None = None
    simulated: bool = False


@dataclass(frozen=True)
class GasDayLine:
    """One physical or traded quantity at a hub on one gas day, in MWh for the day."""

    ref: str
    hub: str
    book_id: str
    direction: str  # IN | OUT
    kind: str
    label: str
    mwh: float
    #: How the quantity is known: nominated, contract_quantity, booked, scheduled, slot (the
    #: slot's rate over its window, an assumption) or cargo_plan (the cargo's send-out plan).
    basis: str
    point: str | None = None
    simulated: bool = False
    #: A WD or DA trade booked during today's gas day (what has been done today).
    prompt_trade: bool = False
    #: A trade's venue: "exchange" or "bilateral" (an ETRM deal); None for physical lines.
    venue: str | None = None
    #: The record the quantity was read from beyond ``ref`` (the cargo of a cargo-plan line).
    source_ref: str | None = None
    #: What changed the quantity (an outage at the line's source), each with source and id.
    adjustments: tuple[LineAdjustment, ...] = ()


@dataclass(frozen=True)
class Delegation:
    """Part (``mwh``) or all of one line, or of a book's position at a hub, to one trader."""

    trader: str
    book_id: str
    hub: str
    ref: str | None = None
    mwh: float | None = None
    trader_name: str | None = None
    delegation_id: str | None = None


@dataclass
class HubBalance:
    """One hub on one gas day for one view."""

    hub: str
    lines: list[GasDayLine] = field(default_factory=list)
    #: Parts of lines that are someone else's in this view (a trader's view) or attributed to a
    #: named trader (a desk view): (line, mwh, delegation).
    delegated: list[tuple[GasDayLine, float, Delegation]] = field(default_factory=list)

    @property
    def in_mwh(self) -> float:
        return sum(line.mwh for line in self.lines if line.direction == IN)

    @property
    def out_mwh(self) -> float:
        return sum(line.mwh for line in self.lines if line.direction == OUT)

    @property
    def net_mwh(self) -> float:
        return self.in_mwh - self.out_mwh

    @property
    def state(self) -> str:
        net = self.net_mwh
        if abs(net) <= FLAT_MWH:
            return "balanced"
        return "long" if net > 0 else "short"


def _matches(delegation: Delegation, line: GasDayLine) -> bool:
    return (
        delegation.book_id == line.book_id
        and delegation.hub.upper() == line.hub.upper()
        and (delegation.ref is None or delegation.ref == line.ref)
    )


def split_line(
    line: GasDayLine, delegations: Sequence[Delegation]
) -> tuple[float, list[tuple[float, Delegation]]]:
    """The owner's part of a line and each delegated part, in MWh; parts never exceed it.

    A line-level delegation takes its ``mwh`` (or the whole line); a book-and-hub delegation
    takes what is left. Delegations are applied in the order given, each capped at what is
    still undelegated, so the parts always add up to the line.
    """

    left = line.mwh
    parts: list[tuple[float, Delegation]] = []
    ordered = sorted(
        (item for item in delegations if _matches(item, line)), key=lambda item: item.ref is None
    )
    for delegation in ordered:
        if left <= 0:
            break
        part = left if delegation.mwh is None else min(max(delegation.mwh, 0.0), left)
        if part <= 0:
            continue
        parts.append((part, delegation))
        left -= part
    return left, parts


def balance_for(
    lines: Iterable[GasDayLine],
    delegations: Sequence[Delegation],
    *,
    trader: str | None = None,
    owned_books: frozenset[str] | None = None,
) -> dict[str, HubBalance]:
    """Per hub, the lines one view clears.

    ``trader`` with ``owned_books``: that trader's view (the undelegated part of his books'
    lines, plus what is delegated to him from any line given). Without ``trader``: every line,
    each delegated part kept in the totals and listed with whom it is delegated to.
    """

    out: dict[str, HubBalance] = {}
    key = (trader or "").lower()
    for line in lines:
        own, parts = split_line(line, delegations)
        hub = line.hub.upper()
        if not trader:
            entry = out.setdefault(hub, HubBalance(hub))
            entry.lines.append(line)
            entry.delegated.extend((line, mwh, item) for mwh, item in parts)
            continue
        mine = sum(mwh for mwh, item in parts if item.trader.lower() == key)
        others = [(line, mwh, item) for mwh, item in parts if item.trader.lower() != key]
        held = mine + (own if owned_books is not None and line.book_id in owned_books else 0.0)
        # A line of nothing in his own books stays in view (a cargo that misses its slot).
        empty = line.mwh == 0 and line.book_id in (owned_books or ())
        if held <= 0 and not empty and not (others and line.book_id in (owned_books or ())):
            continue
        entry = out.setdefault(hub, HubBalance(hub))
        if held > 0 or empty:
            entry.lines.append(line if abs(held - line.mwh) < 1e-9 else replace(line, mwh=held))
        if line.book_id in (owned_books or ()):
            entry.delegated.extend(others)
    return out
