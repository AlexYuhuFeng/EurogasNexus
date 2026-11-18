"""Claim sentences: one template per claim key, rendered only from structured fields.

A claim is a statement with its arithmetic, never advice and never an instruction: no "you
should", no imperative to trade, order, nominate or settle (AGENTS rules 8 and 17). The
templates are the only text an evaluator can produce; a test renders every template and
checks the wording rule. A new evaluator adds its templates here.
"""

from __future__ import annotations

import re
import string
from collections.abc import Mapping
from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal

#: claim key -> template. Fields are ``{name}`` placeholders; every one must be supplied.
CLAIM_TEMPLATES: dict[str, str] = {
    "hedge_gap.below_band": (
        "{contract} · {period}: cover {cover_pct} % against an approved band of {band}; "
        "{gap_mwh} MWh below the band edge. Band approved by {approved_by}{approval_ref}."
    ),
    "hedge_gap.above_band": (
        "{contract} · {period}: cover {cover_pct} % against an approved band of {band}; "
        "{gap_mwh} MWh above the band edge. Band approved by {approved_by}{approval_ref}."
    ),
    "locational.spread": (
        "{buy_hub} → {sell_hub} · {period} · {volume}: {margin} after {costs}; {value}."
    ),
    "capacity.spread": (
        "Held capacity {buy_hub} → {sell_hub} · {period} · {volume}: {margin} with the "
        "{costs}; {value}."
    ),
    "sell_down.residual": (
        "{hub} gas day {gas_day}: {side} residual of {volume} MWh left open; cash-out "
        "{relation} day-ahead by the desk's {penalty} costs {value}."
    ),
    "event.exposure": (
        "Outage at {asset}: {contract} supply -{mwh_d} MWh/d for {days} d ({volume} MWh); "
        "cover at {cover} against the contract's {contract_price}: {value}."
    ),
    "blocked.tariff_not_held": "Cannot evaluate: tariff not held at {subject}.",
    "blocked.price_missing": "Cannot evaluate: no price or firm's mark held for {subject}.",
    "blocked.input_missing": "Cannot evaluate: {subject} not held.",
    "blocked.input_stale": "Cannot evaluate: {subject} is stale ({detail}).",
    "blocked.check_failed": "Cannot evaluate: {subject} check failed ({detail}).",
    "blocked.path_unproven": "Cannot evaluate: no proven path for {subject}.",
    "blocked.evaluator": "Cannot evaluate: {subject}.",
    # Used by the evaluator test harness (a synthetic spread with an exit and entry leg).
    "harness.spread": (
        "{sell_hub} over {buy_hub}, {period}, {volume}: {margin} after transport; {value}."
    ),
}

#: Words a rendered claim must never contain (advice or an action to trade).
FORBIDDEN_WORDS: tuple[str, ...] = (
    "you should",
    "we recommend",
    "recommend",
    "advise",
    "must buy",
    "must sell",
    "buy now",
    "sell now",
    "place an order",
    "execute",
    "submit",
    "nominate",
    "settle",
)

_FIELD = re.compile(r"\{(\w+)\}")


class ClaimError(ValueError):
    """An unknown claim key or a missing field (an evaluator defect)."""


def template_fields(key: str) -> set[str]:
    """The fields a template needs."""

    return {name for _t, name, _f, _c in string.Formatter().parse(CLAIM_TEMPLATES[key]) if name}


def render_claim(key: str, fields: Mapping[str, str]) -> str:
    """Render a claim from its fields.

    Raises:
        ClaimError: unknown key, a missing field or a field that is not plain text.
    """

    template = CLAIM_TEMPLATES.get(key)
    if template is None:
        raise ClaimError(f"unknown claim key {key!r}")
    needed = template_fields(key)
    missing = sorted(needed - set(fields))
    if missing:
        raise ClaimError(f"claim {key!r} misses fields {missing}")
    for name in needed:
        if not isinstance(fields[name], str) or "{" in fields[name]:
            raise ClaimError(f"claim field {name!r} must be plain text")
    return template.format(**{name: fields[name] for name in needed})


def wording_violations(text: str) -> list[str]:
    """Forbidden words found in a rendered sentence."""

    lowered = text.casefold()
    return [word for word in FORBIDDEN_WORDS if re.search(rf"\b{re.escape(word)}\b", lowered)]


# --------------------------------------------------------------------------- formatting


def grouped(value: Decimal, places: int = 0) -> str:
    """``54000`` -> ``54,000``; rounding half to even at ``places``."""

    quantum = Decimal(1).scaleb(-places)
    rounded = value.quantize(quantum, rounding=ROUND_HALF_EVEN)
    if rounded == 0:
        rounded = abs(rounded)  # never "-0"
    return f"{rounded:,.{places}f}"


def signed(value: Decimal, places: int) -> str:
    """``+0.23`` / ``-0.01``."""

    text = grouped(abs(value), places)
    return f"-{text}" if value < 0 else f"+{text}"


def period_label(label: str) -> str:
    """Desk label of a period: ``2027-01`` -> ``Jan-27``; others unchanged."""

    match = re.fullmatch(r"(\d{4})-(\d{2})", label)
    if match:
        month = date(int(match.group(1)), int(match.group(2)), 1)
        return month.strftime("%b-%y")
    return label
