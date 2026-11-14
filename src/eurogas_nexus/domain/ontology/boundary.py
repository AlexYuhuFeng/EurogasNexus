"""Boundary validation: unit, hub, product and period checked against the ontology (ONT-03).

Every operator file importer (settlements, ETRM trades, licensed quotes and curves, REMIT
file imports) and the contract save call :func:`check_boundary` before a row enters the
store. A row that fails carries a stable reason code (:class:`BoundaryReason`) and is
reported with it; nothing is silently dropped and nothing is guessed.

The checks are the ontology's own: markets and hubs from ``ontology.markets`` and
``ontology.identity``, units from ``ontology.quantity`` (through ``market.units``), products
from ``market.products``, periods as half-open ``[start, end)`` intervals. The function only
judges what the caller passes; each importer keeps the inputs it accepted before (a
settlement's free product label is still accepted, ``product_strict=False``).
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum

from eurogas_nexus.domain.ontology.markets import Commodity, Market, find_market


class BoundaryReason(StrEnum):
    """Why a row was refused at the boundary. Values are stable; reports and tests key on them."""

    MARKET_UNKNOWN = "market_unknown"
    HUB_NOT_GAS = "hub_not_a_gas_hub"
    HUB_UNRESOLVED = "hub_unresolved"
    UNIT_UNKNOWN = "unit_unknown"
    UNIT_NOT_ALLOWED = "unit_not_allowed"
    UNIT_CURRENCY_MISMATCH = "unit_currency_mismatch"
    PRODUCT_MISSING = "product_missing"
    PRODUCT_UNRECOGNISED = "product_unrecognised"
    PERIOD_MISSING = "period_missing"
    PERIOD_REVERSED = "period_reversed"


@dataclass(frozen=True)
class BoundaryIssue:
    code: BoundaryReason
    field: str
    value: str
    message: str

    def text(self) -> str:
        """The message with its reason code, as importers print it."""

        return f"{self.message} [{self.code.value}]"

    def as_dict(self) -> dict[str, str]:
        return {
            "code": self.code.value,
            "field": self.field,
            "value": self.value,
            "message": self.message,
        }


@dataclass(frozen=True)
class BoundaryCheck:
    """The outcome: the resolved market or hub, and every issue found."""

    market: Market | None = None
    hub: str | None = None
    issues: tuple[BoundaryIssue, ...] = field(default_factory=tuple)

    @property
    def ok(self) -> bool:
        return not self.issues

    @property
    def first(self) -> BoundaryIssue | None:
        return self.issues[0] if self.issues else None


def check_boundary(
    *,
    market: str | None = None,
    gas_hub_required: bool = False,
    hub_text: str | None = None,
    price_unit: str | None = None,
    quantity_unit: str | None = None,
    allowed_quantity_units: Collection[str] | None = None,
    product: str | None = None,
    product_required: bool = False,
    product_strict: bool = False,
    trade_date: date | None = None,
    period_start: date | datetime | None = None,
    period_end: date | datetime | None = None,
    period_required: bool = False,
    allow_empty_period: bool = True,
    price_verb: str = "quotes",
    hub_points: Mapping[str, str] | None = None,
) -> BoundaryCheck:
    """Check one row's unit, hub, product and period against the ontology.

    Args:
        market: A market code or alias (``TTF``, ``EUA``, ``DE_LU``); must be in the
            reference model, and a gas hub with a delivery calendar when
            ``gas_hub_required``.
        hub_text: A delivery point or free hub text, resolved by ``resolve_hub`` (no
            default hub).
        price_unit: ``<currency>/<unit>``; its currency must be the market's.
        quantity_unit: An energy or rate unit; limited to ``allowed_quantity_units`` when
            given, else any unit the quantity ontology knows.
        product: A product label; with ``product_strict`` it must resolve on
            ``trade_date`` (``market.products.resolve_product``).
        period_start, period_end: The delivery or event period; the end may not come
            before the start (equal is allowed unless ``allow_empty_period`` is False).
    """

    issues: list[BoundaryIssue] = []
    resolved_market: Market | None = None
    hub: str | None = None

    if market is not None:
        resolved_market = find_market(market)
        if resolved_market is None:
            issues.append(
                BoundaryIssue(
                    BoundaryReason.MARKET_UNKNOWN,
                    "market",
                    str(market),
                    f"{market!r} is not in the reference model",
                )
            )
        elif gas_hub_required and (
            resolved_market.commodity is not Commodity.NATURAL_GAS or not resolved_market.calendar
        ):
            issues.append(
                BoundaryIssue(
                    BoundaryReason.HUB_NOT_GAS,
                    "hub",
                    str(market),
                    f"{market!r} is not a gas hub",
                )
            )
        else:
            hub = resolved_market.code

    if hub_text is not None:
        from eurogas_nexus.domain.ontology.identity import resolve_hub

        resolution = resolve_hub(hub_text, points=hub_points)
        if resolution.resolved:
            hub = resolution.hub
        else:
            issues.append(
                BoundaryIssue(
                    BoundaryReason.HUB_UNRESOLVED,
                    "hub",
                    str(hub_text),
                    f"{hub_text!r} names no hub; map the point before it is valued",
                )
            )

    if price_unit is not None:
        issues.extend(_price_unit_issues(price_unit, resolved_market, price_verb))

    if quantity_unit is not None:
        issues.extend(_quantity_unit_issues(quantity_unit, allowed_quantity_units))

    if product is not None or product_required:
        label = (product or "").strip()
        if not label:
            if product_required:
                issues.append(
                    BoundaryIssue(
                        BoundaryReason.PRODUCT_MISSING, "product", "", "product is required"
                    )
                )
        elif product_strict:
            from eurogas_nexus.domain.market.products import ProductCodeError, resolve_product

            try:
                resolve_product(label, trade_date or date.today())
            except ProductCodeError as exc:
                issues.append(
                    BoundaryIssue(
                        BoundaryReason.PRODUCT_UNRECOGNISED, "product", label, str(exc)
                    )
                )

    if period_start is None or period_end is None:
        if period_required:
            issues.append(
                BoundaryIssue(
                    BoundaryReason.PERIOD_MISSING,
                    "period",
                    f"{period_start}..{period_end}",
                    "the period needs a start and an end",
                )
            )
    elif period_end < period_start or (not allow_empty_period and period_end == period_start):
        issues.append(
            BoundaryIssue(
                BoundaryReason.PERIOD_REVERSED,
                "period",
                f"{period_start}..{period_end}",
                "the period ends before it starts",
            )
        )

    return BoundaryCheck(market=resolved_market, hub=hub, issues=tuple(issues))


def _price_unit_issues(
    text: str, market: Market | None, verb: str = "quotes"
) -> list[BoundaryIssue]:
    from eurogas_nexus.domain.ontology.quantity import UnitError
    from eurogas_nexus.domain.ontology.quantity import price_unit as parse_price_unit

    try:
        parsed = parse_price_unit(text)
    except UnitError as exc:
        return [BoundaryIssue(BoundaryReason.UNIT_UNKNOWN, "unit", str(text), str(exc))]
    if market is not None and parsed.currency != market.currency:
        return [
            BoundaryIssue(
                BoundaryReason.UNIT_CURRENCY_MISMATCH,
                "unit",
                str(text),
                f"{market.code} {verb} in {market.currency}, not {text}",
            )
        ]
    return []


def _quantity_unit_issues(
    text: str, allowed: Collection[str] | None
) -> list[BoundaryIssue]:
    if allowed is not None:
        if text in allowed:
            return []
        return [
            BoundaryIssue(
                BoundaryReason.UNIT_NOT_ALLOWED,
                "quantity_unit",
                str(text),
                f"quantity_unit {text!r} not supported",
            )
        ]
    from eurogas_nexus.domain.ontology.quantity import UnitError, unit

    try:
        unit(text.split("/")[0])
    except UnitError as exc:
        return [BoundaryIssue(BoundaryReason.UNIT_UNKNOWN, "quantity_unit", str(text), str(exc))]
    return []


def refuse_if_invalid(check: BoundaryCheck, error: type[Exception], prefix: str = "") -> None:
    """Raise ``error`` naming the first issue and its reason code; the importer's refusal.

    The exception carries ``reason_code`` and every issue as ``boundary_issues`` so a
    caller (an operator script, an API route) can report them all.
    """

    issue = check.first
    if issue is None:
        return
    exc = error(f"{prefix}{issue.text()}")
    exc.reason_code = issue.code.value  # type: ignore[attr-defined]
    exc.boundary_issues = [item.as_dict() for item in check.issues]  # type: ignore[attr-defined]
    raise exc


def check_contract(
    *,
    delivery_point_name: str | None,
    gas_year: str | None,
    price_currency: str | None,
    hub_points: Mapping[str, str] | None = None,
) -> BoundaryCheck:
    """The contract save's boundary check: hub, period (gas year) and price unit.

    The save keeps every contract it accepted before; the issues are returned with the
    write and the contract is left out of positions until they are fixed (an unresolved
    delivery point is never valued at a default hub).
    """

    import re

    check = check_boundary(
        hub_text=delivery_point_name or "",
        price_unit=f"{(price_currency or 'GBP').upper()}/MWh",
        hub_points=hub_points,
    )
    issues = list(check.issues)
    if not re.search(r"(\d{4})|GY-?(\d{2})", (gas_year or "").upper()):
        issues.append(
            BoundaryIssue(
                BoundaryReason.PERIOD_MISSING,
                "gas_year",
                str(gas_year or ""),
                f"gas year {gas_year!r} is not understood (2026/27, GY-26, 2026 or 2025+)",
            )
        )
    return BoundaryCheck(market=check.market, hub=check.hub, issues=tuple(issues))
