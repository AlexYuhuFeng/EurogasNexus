"""LNG cargo bid sheet: the most the firm can pay for a DES cargo at each regas terminal.

Bidding for a spot or tender cargo, the desk asks where the cargo is worth most once landed
and what that makes the bid. For each terminal the firm has terms for::

    energy unloaded      E                     (the cargo, MWh)
    after boil-off       E x (1 - bor x d)     d = extra sailing days versus the reference
    sent out             x (1 - fuel retention)
    revenue              sent out x hub price for the arrival month
    costs                E x (regas + other) + sent out x entry tariff
                         + port costs + charter per day x d
    breakeven            (revenue - costs) / E          per MWh of cargo bought
    max bid              breakeven - target margin

Prices are in the terminal's hub currency per MWh and also in USD/MMBtu, the way cargoes
are quoted, and as a share of the hub price (cargoes are often priced as a percentage of
TTF). The range runs the same sum on the hub marks of the month before and after arrival,
because a cargo's arrival slips. Terminals are ranked on the bid in one currency; the
result names the hub mark and its month for each, so the bid can be checked against the
screen. Decision support for pricing a bid, not an offer.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass

MWH_PER_MMBTU = 0.29307107


@dataclass(frozen=True)
class TerminalTerms:
    terminal_id: str
    name: str
    country: str | None
    hub: str
    currency: str
    regas_tariff_per_mwh: float
    entry_tariff_per_mwh: float = 0.0
    fuel_retention_pct: float = 0.0
    port_costs_per_cargo: float = 0.0
    other_per_mwh: float = 0.0
    extra_sailing_days: float = 0.0
    source_note: str = ""


@dataclass(frozen=True)
class CargoBidRequest:
    cargo_mwh: float
    arrival_month: str  # "2026-12"
    target_margin_per_mwh: float = 0.0  # in the ranking currency
    boil_off_pct_per_day: float = 0.1
    charter_per_day: float = 0.0  # in the ranking currency
    ranking_currency: str = "EUR"


def _neighbours(month: str) -> tuple[str, str]:
    year, number = int(month[:4]), int(month[5:7])
    before = f"{year - (number == 1):04d}-{12 if number == 1 else number - 1:02d}"
    after = f"{year + (number == 12):04d}-{1 if number == 12 else number + 1:02d}"
    return before, after


def _bid(terms: TerminalTerms, request: CargoBidRequest, price: float, to_hub: float):
    energy = request.cargo_mwh
    days = max(0.0, terms.extra_sailing_days)
    after_boil_off = energy * max(0.0, 1 - request.boil_off_pct_per_day / 100 * days)
    sent_out = after_boil_off * (1 - terms.fuel_retention_pct / 100)
    revenue = sent_out * price
    costs = (
        energy * (terms.regas_tariff_per_mwh + terms.other_per_mwh)
        + sent_out * terms.entry_tariff_per_mwh
        + terms.port_costs_per_cargo
        + request.charter_per_day * to_hub * days
    )
    breakeven = (revenue - costs) / energy
    return breakeven, breakeven - request.target_margin_per_mwh * to_hub, sent_out, costs


def cargo_bid_sheet(
    terminals: Iterable[TerminalTerms],
    request: CargoBidRequest,
    *,
    mark: Callable[[str, str], float | None],
    spot: Callable[[str], float | None],
    fx: Callable[[str, str], float | None],
) -> tuple[list[dict[str, object]], list[str]]:
    """One row per terminal, best bid first, and the warnings for terminals left out."""

    if request.cargo_mwh <= 0:
        raise ValueError("cargo_mwh must be positive")
    rows, warnings = [], []
    before, after = _neighbours(request.arrival_month)
    for terms in terminals:
        price = mark(terms.hub, request.arrival_month)
        to_hub = fx(request.ranking_currency, terms.currency)
        to_rank = fx(terms.currency, request.ranking_currency)
        to_usd = fx(terms.currency, "USD")
        if price is None:
            warnings.append(f"{terms.name}: no {terms.hub} mark for {request.arrival_month}")
            continue
        if to_hub is None or to_rank is None:
            warnings.append(
                f"{terms.name}: no ECB rate between {terms.currency} and {request.ranking_currency}"
            )
            continue
        breakeven, bid, sent_out, costs = _bid(terms, request, price, to_hub)
        bids = [bid]
        for month in (before, after):
            other = mark(terms.hub, month)
            if other is not None:
                bids.append(_bid(terms, request, other, to_hub)[1])
        rows.append(
            {
                "terminal": terms.name,
                "terminal_id": terms.terminal_id,
                "country": terms.country,
                "hub": terms.hub,
                "currency": terms.currency,
                "hub_mark": round(price, 3),
                "mark_month": request.arrival_month,
                "spot": None if spot(terms.hub) is None else round(spot(terms.hub), 3),
                "sent_out_mwh": round(sent_out, 0),
                "costs_per_mwh": round(costs / request.cargo_mwh, 3),
                "breakeven_per_mwh": round(breakeven, 3),
                "max_bid_per_mwh": round(bid, 3),
                "bid_low_per_mwh": round(min(bids), 3),
                "bid_high_per_mwh": round(max(bids), 3),
                "max_bid_usd_mmbtu": None
                if to_usd is None
                else round(bid * to_usd * MWH_PER_MMBTU, 3),
                "bid_vs_hub_per_mwh": round(bid - price, 3),
                "bid_pct_of_hub": None if price == 0 else round(100 * bid / price, 1),
                f"max_bid_{request.ranking_currency.lower()}_per_mwh": round(bid * to_rank, 3),
                "cargo_value": round(bid * request.cargo_mwh, 0),
                "terms_source": terms.source_note,
            }
        )
    key = f"max_bid_{request.ranking_currency.lower()}_per_mwh"
    rows.sort(key=lambda row: row[key], reverse=True)
    for rank, row in enumerate(rows, start=1):
        row["rank"] = rank
    return rows, warnings


def region_ranges(rows: list[dict[str, object]], currency: str) -> list[dict[str, object]]:
    """Bid range per country, in the ranking currency (the 'where to send it' view)."""

    key = f"max_bid_{currency.lower()}_per_mwh"
    ranges: dict[str, list[float]] = {}
    for row in rows:
        ranges.setdefault(str(row.get("country") or "?"), []).append(float(row[key]))
    return [
        {"country": country, "terminals": len(values), "low": min(values), "high": max(values)}
        for country, values in sorted(ranges.items(), key=lambda item: -max(item[1]))
    ]
