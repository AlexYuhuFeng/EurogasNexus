"""Which source a price, rate or tariff comes from: one ordered hierarchy for every calculation.

A calculation asks for a **quantity kind** (an FX rate, an interest rate, a capacity cost, a
tariff, a commodity price) in a **context** (the calculation asking: ``lng_demurrage``,
``route_cost`` ...) **as of** an instant. :func:`resolve` walks the kind's tiers in order and
takes the first that holds a usable value; every tier tried is reported, used or skipped, with
why (not held, stale, does not cover the period, not configured), so a breakdown can list the
sources applied in precedence order with the one used marked.

Default orders (``DEFAULT_ORDERS``), owner's rule 2026-11-25: what the firm itself has
agreed comes first, then a published reference, then the default public source.

* ``fx_rate`` and ``interest_rate``: ``contracted_bank`` (the firm's clearing or account bank's
  own rate, where the firm holds the money and converts it), ``published_reference`` (a
  licensed fixing the firm holds: WM/Reuters, BFIX; for interest rates the administrator's
  benchmark fixing), ``ecb_reference`` (the ECB euro reference rate; €STR for EUR rates);
* ``capacity_cost``: ``contracted`` (the firm's booking at its contracted cost), then
  ``public_final``, then ``public_indicative`` (TAR-2's layering is built on this order);
* ``tariff``: ``public_final``, then ``public_indicative``;
* ``commodity_price``: ``firm_mark`` (the firm's approved marks), ``licensed_exchange``
  (settlement or screen price under the firm's licence), ``public_reference``.

A firm may reorder or drop tiers per kind, and per calculation context, through the
organisation setting ``source_precedence`` (``{"fx_rate": [...], "fx_rate@lng_demurrage":
[...]}``), written by an administrator through the governed, audited settings write;
:func:`order_for` reads it, a context's own order first. A tier not in a kind's vocabulary is
refused when the setting is written (:func:`validate_orders`), so a stored order is always one
the resolver can walk.

Pure and deterministic: each tier's lookup is a callable the application layer supplies.

TAR-2：统一的数据来源优先级：按计算类型与场景的有序层级依次尝试，返回所用数值与来源，
并列出每一层被采用或跳过的原因；企业可经受审计的组织设置调整顺序。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

FX_RATE = "fx_rate"
INTEREST_RATE = "interest_rate"
CAPACITY_COST = "capacity_cost"
TARIFF = "tariff"
COMMODITY_PRICE = "commodity_price"

#: Every tier a kind may use, in its default order.
DEFAULT_ORDERS: dict[str, tuple[str, ...]] = {
    FX_RATE: ("contracted_bank", "published_reference", "ecb_reference"),
    INTEREST_RATE: ("contracted_bank", "published_reference", "ecb_reference"),
    CAPACITY_COST: ("contracted", "public_final", "public_indicative"),
    TARIFF: ("public_final", "public_indicative"),
    COMMODITY_PRICE: ("firm_mark", "licensed_exchange", "public_reference"),
}

TIER_TEXT: dict[str, str] = {
    "contracted_bank": "the firm's contracted bank rate (clearing or account bank)",
    "published_reference": "a published reference rate the firm holds (licensed fixing)",
    "ecb_reference": "the ECB reference rate (default)",
    "contracted": "the firm's contracted or booked cost",
    "public_final": "the public tariff, final",
    "public_indicative": "the public tariff, indicative",
    "firm_mark": "the firm's approved mark",
    "licensed_exchange": "an exchange or screen price under the firm's licence",
    "public_reference": "a public reference price",
}

SETTING = "source_precedence"

#: Why a tier was not used.
NOT_HELD = "not_held"
STALE = "stale"
NOT_COVERING = "not_covering"
NOT_CONFIGURED = "not_configured"
NOT_ENTITLED = "not_entitled"
SKIP_REASONS = (NOT_HELD, STALE, NOT_COVERING, NOT_CONFIGURED, NOT_ENTITLED)


class PrecedenceError(ValueError):
    """An order that names an unknown kind or tier."""


@dataclass(frozen=True)
class Found:
    """What one tier holds: the value and where it came from."""

    value: float
    source: str
    reference: str = ""
    as_of: str | None = None
    unit: str | None = None
    detail: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Skipped:
    """Why one tier holds nothing usable (``SKIP_REASONS``) and, in words, what is missing."""

    reason: str
    note: str = ""


Lookup = Callable[[], "Found | Skipped"]


@dataclass(frozen=True)
class TierOutcome:
    tier: str
    used: bool
    reason: str
    note: str = ""
    found: Found | None = None

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "tier": self.tier,
            "label": TIER_TEXT.get(self.tier, self.tier),
            "used": self.used,
            "reason": self.reason,
            "note": self.note or None,
        }
        if self.found is not None:
            out |= {
                "value": self.found.value,
                "source": self.found.source,
                "reference": self.found.reference or None,
                "as_of": self.found.as_of,
                "unit": self.found.unit,
                **dict(self.found.detail),
            }
        return out


@dataclass(frozen=True)
class Resolution:
    """The value a calculation uses, its provenance, and every tier tried in order."""

    kind: str
    context: str
    as_of: datetime | None
    order: tuple[str, ...]
    order_source: str
    tiers: tuple[TierOutcome, ...]

    @property
    def used(self) -> TierOutcome | None:
        return next((item for item in self.tiers if item.used), None)

    @property
    def value(self) -> float | None:
        used = self.used
        return None if used is None or used.found is None else used.found.value

    def as_dict(self) -> dict[str, Any]:
        used = self.used
        return {
            "kind": self.kind,
            "context": self.context,
            "as_of": self.as_of.isoformat() if self.as_of else None,
            "value": self.value,
            "used_tier": None if used is None else used.tier,
            "source": None if used is None or used.found is None else used.found.source,
            "order": list(self.order),
            "order_source": self.order_source,
            "sources": [item.as_dict() for item in self.tiers],
        }


def validate_orders(values: Any) -> dict[str, list[str]]:
    """The ``source_precedence`` setting: ``kind`` or ``kind@context`` -> an ordered list of
    that kind's tiers, each at most once (a tier left out is not used)."""

    if not isinstance(values, Mapping) or not values:
        raise PrecedenceError(f"{SETTING} must map a kind to an ordered list of tiers")
    out: dict[str, list[str]] = {}
    for key, order in values.items():
        kind, _, context = str(key).partition("@")
        if kind not in DEFAULT_ORDERS:
            raise PrecedenceError(f"{kind!r} is not a quantity kind ({', '.join(DEFAULT_ORDERS)})")
        if context and (len(context) > 48 or not context.replace("_", "").isalnum()):
            raise PrecedenceError(f"{key!r}: a context is letters, digits and underscores")
        if not isinstance(order, (list, tuple)) or not order:
            raise PrecedenceError(f"{key}: the order must be a non-empty list of tiers")
        tiers = [str(item) for item in order]
        unknown = [item for item in tiers if item not in DEFAULT_ORDERS[kind]]
        if unknown:
            raise PrecedenceError(
                f"{key}: {unknown[0]!r} is not a tier of {kind} "
                f"({', '.join(DEFAULT_ORDERS[kind])})"
            )
        if len(set(tiers)) != len(tiers):
            raise PrecedenceError(f"{key}: a tier is listed twice")
        out[str(key)] = tiers
    return out


def order_for(
    kind: str, context: str = "", configured: Mapping[str, Any] | None = None
) -> tuple[tuple[str, ...], str]:
    """The order for ``kind`` in ``context`` and where it came from (``setting:<key>`` or
    ``default``). A stored order that does not validate is ignored (the default holds)."""

    if kind not in DEFAULT_ORDERS:
        raise PrecedenceError(f"{kind!r} is not a quantity kind")
    if isinstance(configured, Mapping):
        for key in ((f"{kind}@{context}",) if context else ()) + (kind,):
            if key in configured:
                try:
                    return tuple(validate_orders({key: configured[key]})[key]), f"setting:{key}"
                except PrecedenceError:
                    continue
    return DEFAULT_ORDERS[kind], "default"


def resolve(
    kind: str,
    lookups: Mapping[str, Lookup],
    *,
    context: str = "",
    as_of: datetime | None = None,
    configured: Mapping[str, Any] | None = None,
    order: Sequence[str] | None = None,
) -> Resolution:
    """Walk ``kind``'s tiers in order; the first that holds a value is used.

    ``order`` (a calculation's own, validated) overrides the configured one. A tier with no
    lookup is skipped as ``not_configured``; the tiers after the used one are listed as
    ``not_tried`` so the reader sees the whole hierarchy.
    """

    if order is not None:
        chosen = tuple(validate_orders({kind: list(order)})[kind])
        origin = "calculation"
    else:
        chosen, origin = order_for(kind, context, configured)
    outcomes: list[TierOutcome] = []
    done = False
    for tier in chosen:
        if done:
            outcomes.append(TierOutcome(tier, False, "not_tried"))
            continue
        lookup = lookups.get(tier)
        if lookup is None:
            outcomes.append(TierOutcome(tier, False, NOT_CONFIGURED, "no source of this tier"))
            continue
        result = lookup()
        if isinstance(result, Found):
            outcomes.append(TierOutcome(tier, True, "used", found=result))
            done = True
        else:
            outcomes.append(TierOutcome(tier, False, result.reason, result.note))
    return Resolution(kind, context, as_of, chosen, origin, tuple(outcomes))


__all__ = [
    "CAPACITY_COST",
    "COMMODITY_PRICE",
    "DEFAULT_ORDERS",
    "FX_RATE",
    "INTEREST_RATE",
    "NOT_CONFIGURED",
    "NOT_COVERING",
    "NOT_ENTITLED",
    "NOT_HELD",
    "SETTING",
    "SKIP_REASONS",
    "STALE",
    "TARIFF",
    "TIER_TEXT",
    "Found",
    "PrecedenceError",
    "Resolution",
    "Skipped",
    "TierOutcome",
    "order_for",
    "resolve",
    "validate_orders",
]
