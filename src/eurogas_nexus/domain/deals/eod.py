"""The end-of-day check: captured deals against what was entered in the ETRM.

Every difference is listed, none is hidden: a deal captured but not in the ETRM, an ETRM
trade with no captured deal, and for each pair a different side, hub, delivery period,
volume, price or counterparty. Pairs are found first by the exchange's trade id where the
ETRM export carries it (the layout file names that column), then by terms (hub, side and
delivery period, the closest volume and price). A pair found by terms says so. Volumes are
compared in MWh over the period and prices per MWh in the hub's currency, in exact decimals,
within the stated tolerances.

日终核对：捕获交易与 ETRM 录入逐项比对，所有差异全部列出
（缺失、方向、枢纽、交割期、数量、价格、对手方）。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

#: Within these the two sides agree (rounding of a converted unit, not a real difference).
VOLUME_TOLERANCE_MWH = Decimal("0.01")
PRICE_TOLERANCE_PER_MWH = Decimal("0.0005")

KINDS = (
    "missing_in_etrm",
    "missing_in_capture",
    "side",
    "hub",
    "period",
    "volume",
    "price",
    "counterparty",
    "cancelled_in_capture",
)


@dataclass(frozen=True)
class CapturedSide:
    deal_key: str
    venue: str
    venue_trade_id: str
    status: str
    trader: str
    counterparty: str
    cleared: bool
    hub: str
    product: str
    side: str
    first_day: date
    last_day: date
    total_mwh: Decimal
    price_per_mwh: Decimal
    currency: str
    book_id: str | None
    source: str


@dataclass(frozen=True)
class EtrmSide:
    trade_id: str
    reference: str
    hub: str
    side: str
    first_day: date
    last_day: date
    total_mwh: Decimal
    price_per_mwh: Decimal
    counterparty: str
    book_id: str | None
    line: int


@dataclass
class CheckResult:
    matched: int = 0
    matched_by_terms: int = 0
    differences: list[dict[str, Any]] = field(default_factory=list)
    unreadable: list[dict[str, Any]] = field(default_factory=list)
    #: Every pair found, deal key to ETRM trade id (with or without a difference).
    pairs: dict[str, str] = field(default_factory=dict)

    def counts(self) -> dict[str, int]:
        out = dict.fromkeys(KINDS, 0)
        for item in self.differences:
            out[item["kind"]] += 1
        return out

    def as_dict(self) -> dict[str, Any]:
        return {
            "matched": self.matched,
            "matched_by_terms": self.matched_by_terms,
            "pairs": self.pairs,
            "differences": self.differences,
            "counts": self.counts(),
            "unreadable_etrm_rows": self.unreadable,
            "tolerances": {
                "volume_mwh": str(VOLUME_TOLERANCE_MWH),
                "price_per_mwh": str(PRICE_TOLERANCE_PER_MWH),
            },
        }


def _txt(value: Decimal) -> str:
    """A decimal as plain text without trailing zeros."""

    text = format(value.normalize(), "f")
    return "0" if text == "-0" else text


def difference_id(kind: str, deal_key: str | None, etrm_id: str | None) -> str:
    text = f"{kind}|{deal_key or ''}|{etrm_id or ''}"
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def _captured_view(deal: CapturedSide) -> dict[str, Any]:
    return {
        "deal_key": deal.deal_key, "venue": deal.venue, "trade_id": deal.venue_trade_id,
        "trader": deal.trader, "counterparty": deal.counterparty or None,
        "cleared": deal.cleared, "hub": deal.hub, "product": deal.product, "side": deal.side,
        "delivery_start": deal.first_day.isoformat(), "delivery_end": deal.last_day.isoformat(),
        "total_mwh": _txt(deal.total_mwh), "price_per_mwh": _txt(deal.price_per_mwh),
        "currency": deal.currency, "book_id": deal.book_id, "source": deal.source,
        "status": deal.status,
    }  # fmt: skip


def _etrm_view(row: EtrmSide) -> dict[str, Any]:
    return {
        "trade_id": row.trade_id, "reference": row.reference or None, "hub": row.hub,
        "side": row.side, "delivery_start": row.first_day.isoformat(),
        "delivery_end": row.last_day.isoformat(), "total_mwh": _txt(row.total_mwh),
        "price_per_mwh": _txt(row.price_per_mwh), "counterparty": row.counterparty or None,
        "book_id": row.book_id, "line": row.line,
    }  # fmt: skip


def _counterparty_differs(deal: CapturedSide, row: EtrmSide) -> bool:
    theirs = row.counterparty.strip().casefold()
    ours = (deal.counterparty or ("" if not deal.cleared else deal.venue)).strip().casefold()
    if not theirs or not ours:
        return bool(theirs) != bool(ours) and not deal.cleared
    return not (theirs == ours or theirs in ours or ours in theirs)


def _compare(deal: CapturedSide, row: EtrmSide, by_terms: bool) -> list[dict[str, Any]]:
    out = []

    def add(kind: str, detail: dict[str, Any]) -> None:
        out.append({
            "id": difference_id(kind, deal.deal_key, row.trade_id),
            "kind": kind,
            "deal_key": deal.deal_key,
            "etrm_trade_id": row.trade_id,
            "hub": deal.hub,
            "product": deal.product,
            "matched_by": "terms" if by_terms else "reference",
            "captured": _captured_view(deal),
            "etrm": _etrm_view(row),
            "detail": detail,
        })

    if deal.status == "cancelled":
        add("cancelled_in_capture", {})
    if deal.side != row.side:
        add("side", {"captured": deal.side, "etrm": row.side})
    if deal.hub != row.hub:
        add("hub", {"captured": deal.hub, "etrm": row.hub})
    if (deal.first_day, deal.last_day) != (row.first_day, row.last_day):
        add("period", {
            "captured": f"{deal.first_day.isoformat()}..{deal.last_day.isoformat()}",
            "etrm": f"{row.first_day.isoformat()}..{row.last_day.isoformat()}",
        })
    if abs(deal.total_mwh - row.total_mwh) > VOLUME_TOLERANCE_MWH:
        add("volume", {"captured_mwh": _txt(deal.total_mwh), "etrm_mwh": _txt(row.total_mwh),
                       "difference_mwh": _txt(row.total_mwh - deal.total_mwh)})
    if abs(deal.price_per_mwh - row.price_per_mwh) > PRICE_TOLERANCE_PER_MWH:
        add("price", {"captured": _txt(deal.price_per_mwh), "etrm": _txt(row.price_per_mwh),
                      "currency": deal.currency,
                      "difference": _txt(row.price_per_mwh - deal.price_per_mwh)})
    if _counterparty_differs(deal, row):
        add("counterparty", {"captured": deal.counterparty or deal.venue,
                             "etrm": row.counterparty})
    return out


def _distance(deal: CapturedSide, row: EtrmSide) -> tuple[Decimal, Decimal]:
    return abs(deal.total_mwh - row.total_mwh), abs(deal.price_per_mwh - row.price_per_mwh)


@dataclass
class Pairing:
    """Which captured deal is which ETRM trade: the one same-deal rule (``pair_deals``)."""

    #: deal key -> the ETRM trade paired with it.
    pairs: dict[str, EtrmSide] = field(default_factory=dict)
    #: deal key -> how the pair was found: ``close`` (recorded at a day's close),
    #: ``reference`` (the exchange's trade id) or ``terms``.
    matched_by: dict[str, str] = field(default_factory=dict)


def pair_deals(
    captured: list[CapturedSide],
    etrm: list[EtrmSide],
    recorded: dict[str, str] | None = None,
) -> Pairing:
    """Pair captured deals with ETRM trades, each at most once: the same-deal rule.

    In order, a captured deal and an ETRM trade are the same deal when:

    1. a day's close recorded them as a pair (``recorded``: deal key -> ETRM trade id);
    2. the ETRM trade's exchange reference is the deal's venue trade id or deal key;
    3. else, for an ETRM trade that carries no reference, the same hub, side and delivery
       period (first and last gas day); among several, the closest volume, then price.

    Live deals are paired by terms first; a cancelled captured deal is then paired by terms
    only with an ETRM trade no live deal took (the ETRM still holds a deal the desk cancelled:
    "cancelled, still in the ETRM"). The end-of-day check and the position both use this
    function, so what the check calls one deal the position counts once.
    """

    out = Pairing()
    used: set[int] = set()
    by_trade = {row.trade_id: row for row in etrm}
    pending: list[CapturedSide] = []
    for deal in captured:
        held = by_trade.get((recorded or {}).get(deal.deal_key, ""))
        if held is not None and id(held) not in used:
            used.add(id(held))
            out.pairs[deal.deal_key] = held
            out.matched_by[deal.deal_key] = "close"
        else:
            pending.append(deal)
    by_reference: dict[str, list[EtrmSide]] = {}
    for row in etrm:
        if row.reference:
            by_reference.setdefault(row.reference.strip().casefold(), []).append(row)
    unmatched: list[CapturedSide] = []
    for deal in pending:
        keys = {deal.venue_trade_id.strip().casefold(), deal.deal_key.strip().casefold()}
        candidates = [
            row for key in sorted(keys) for row in by_reference.get(key, [])
            if id(row) not in used
        ]
        if candidates:
            used.add(id(candidates[0]))
            out.pairs[deal.deal_key] = candidates[0]
            out.matched_by[deal.deal_key] = "reference"
        else:
            unmatched.append(deal)
    ordered = [d for d in unmatched if d.status != "cancelled"]
    ordered += [d for d in unmatched if d.status == "cancelled"]
    for deal in ordered:
        candidates = [
            row for row in etrm
            if id(row) not in used and not row.reference
            and (row.hub, row.side, row.first_day, row.last_day)
            == (deal.hub, deal.side, deal.first_day, deal.last_day)
        ]
        if not candidates:
            continue
        row = min(candidates, key=lambda item: (*_distance(deal, item), item.trade_id))
        used.add(id(row))
        out.pairs[deal.deal_key] = row
        out.matched_by[deal.deal_key] = "terms"
    return out


def check(captured: list[CapturedSide], etrm: list[EtrmSide]) -> CheckResult:
    """Pair captured deals with ETRM trades (``pair_deals``) and list every difference."""

    result = CheckResult()
    pairing = pair_deals(captured, etrm)
    used = {id(row) for row in pairing.pairs.values()}
    for deal in captured:
        row = pairing.pairs.get(deal.deal_key)
        if row is None:
            if deal.status == "cancelled":
                continue  # a cancelled deal with nothing in the ETRM is as it should be
            result.differences.append({
                "id": difference_id("missing_in_etrm", deal.deal_key, None),
                "kind": "missing_in_etrm", "deal_key": deal.deal_key, "etrm_trade_id": None,
                "hub": deal.hub, "product": deal.product, "matched_by": None,
                "captured": _captured_view(deal), "etrm": None, "detail": {},
            })
            continue
        by_terms = pairing.matched_by[deal.deal_key] == "terms"
        result.matched += 1
        result.matched_by_terms += 1 if by_terms else 0
        result.pairs[deal.deal_key] = row.trade_id
        result.differences += _compare(deal, row, by_terms=by_terms)
    for row in etrm:
        if id(row) in used:
            continue
        result.differences.append({
            "id": difference_id("missing_in_capture", None, row.trade_id),
            "kind": "missing_in_capture", "deal_key": None, "etrm_trade_id": row.trade_id,
            "hub": row.hub, "product": None, "matched_by": None, "captured": None,
            "etrm": _etrm_view(row), "detail": {},
        })
    result.differences.sort(key=lambda item: (KINDS.index(item["kind"]), item["hub"] or "",
                                              item["deal_key"] or item["etrm_trade_id"] or ""))
    return result
