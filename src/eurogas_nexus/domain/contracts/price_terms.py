"""Contract price terms as a formula, not one number (docs/product/CONTRACT_TYPES.md, slice 2).

A desk prices gas as:

- **fixed**: a price in the contract's unit (``31.50 EUR/MWh``, ``84.00 GBp/th``);
- **index ± premium**: a hub index read from a publication and averaged by a rule
  (``TTF month-ahead, average of the month before delivery, + 0.25 EUR/MWh``;
  ``NBP day-ahead of the delivery day − 0.40 p/th``);
- **formula**: a weighted basket plus a constant (``1.15 × Henry Hub + 2.50 USD/MMBtu``;
  ``0.12 × Brent + 0.50``), with a cap and floor where the contract has them.

:func:`evaluate` prices one delivery period from the indices a ``lookup`` holds. An index the
lookup does not hold is named as missing, never guessed; a value in another currency is
refused (the FX rule of the contract is not modelled yet); a value in another energy unit of
the same currency is converted through the units authority. Each input carries its class
(settlement, firm mark, simulated, ...) and the result takes the weakest.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from eurogas_nexus.domain.ontology.quantity import UnitError, convert_price

PriceUnit = Literal["EUR/MWh", "GBP/MWh", "GBp/th", "USD/MMBtu", "USD/bbl"]
_UNIT_CURRENCY = {
    "EUR/MWh": "EUR",
    "GBP/MWh": "GBP",
    "GBp/th": "GBP",
    "USD/MMBtu": "USD",
    "USD/bbl": "USD",
}

#: Input classes, weakest last (the result takes the weakest of its inputs).
CLASS_ORDER = ("contract", "settlement", "firm_mark", "indicative", "assumption", "simulated")

#: Drivers an index may name: European hubs and the global benchmarks LNG is priced off.
INDEX_NAMES = {
    "TTF": "TTF",
    "NBP": "NBP",
    "THE": "THE",
    "PEG": "PEG",
    "ZTP": "ZTP",
    "PSV": "PSV",
    "PVB": "PVB",
    "CEGH": "CEGH",
    "HH": "Henry Hub",
    "BRENT": "Brent",
    "JKM": "JKM",
}

Product = Literal["day_ahead", "weekend", "bom", "month_ahead", "pricing_month"]
Averaging = Literal[
    "delivery_day",  # the day-ahead price of each delivery day, averaged over the period
    "month_before_delivery",  # month-ahead closes over the month before delivery
    "delivery_month",  # all closes in the delivery month
    "last_n_trading_days",  # the last N closes before the delivery month
    "pricing_month",  # the settlement of a named pricing month (LNG: HH/Brent)
]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class PriceIndex(_Model):
    """One index: a driver, a product, where it is read and how it is averaged."""

    index: str = Field(min_length=2, max_length=8)
    product: Product = "month_ahead"
    averaging: Averaging = "month_before_delivery"
    n_days: int | None = Field(default=None, ge=1, le=60)
    #: The publication the index is read from (ICIS Heren, Argus, EEX settlement, NYMEX).
    publication: str | None = Field(default=None, max_length=96)

    @model_validator(mode="after")
    def _known(self) -> PriceIndex:
        if self.index.upper() not in INDEX_NAMES:
            raise ValueError(f"index {self.index!r} is not one the product reads")
        if (self.averaging == "last_n_trading_days") != (self.n_days is not None):
            raise ValueError("'last N trading days' states N, and only that rule does")
        return self

    def words(self) -> str:
        name = INDEX_NAMES[self.index.upper()]
        product = {
            "day_ahead": "day-ahead",
            "weekend": "weekend",
            "bom": "balance-of-month",
            "month_ahead": "month-ahead",
            "pricing_month": "settlement",
        }[self.product]
        rule = {
            "delivery_day": "of each delivery day",
            "month_before_delivery": "averaged over the month before delivery",
            "delivery_month": "averaged over the delivery month",
            "last_n_trading_days": f"averaged over the last {self.n_days} trading days",
            "pricing_month": "of the pricing month",
        }[self.averaging]
        source = f" ({self.publication})" if self.publication else ""
        return f"{name} {product}{source} {rule}"


class PriceComponent(_Model):
    """One weighted index in a formula (a slope on HH, a share of a basket)."""

    index: PriceIndex
    weight: float = Field(gt=-10, le=10)


class PriceTerms(_Model):
    """A contract's price as signed (``price-terms/v1``)."""

    schema_: Literal["price-terms/v1"] = Field("price-terms/v1", alias="schema")
    basis: Literal["fixed", "index", "formula"]
    unit: PriceUnit
    fixed_price: float | None = Field(default=None, ge=-1_000, le=10_000)
    index: PriceIndex | None = None
    #: Premium (+) or discount (−) over the index, in ``unit``.
    premium: float = Field(default=0.0, ge=-1_000, le=1_000)
    components: list[PriceComponent] = Field(default_factory=list, max_length=6)
    constant: float = Field(default=0.0, ge=-1_000, le=1_000)
    cap: float | None = None
    floor: float | None = None
    #: The pricing month a formula reads (LNG cargo), ``YYYY-MM``; None: the delivery month.
    pricing_month: str | None = Field(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    rounding_dp: int | None = Field(default=None, ge=0, le=6)

    @model_validator(mode="after")
    def _consistent(self) -> PriceTerms:
        if self.basis == "fixed" and self.fixed_price is None:
            raise ValueError("a fixed price states the price")
        if self.basis == "index" and self.index is None:
            raise ValueError("an index price names its index")
        if self.basis == "formula" and not self.components:
            raise ValueError("a formula names at least one weighted index")
        if self.cap is not None and self.floor is not None and self.floor > self.cap:
            raise ValueError("the floor is above the cap")
        return self

    @property
    def currency(self) -> str:
        return _UNIT_CURRENCY[self.unit]

    def words(self) -> str:
        """The price in words, as the contract would state it."""

        unit = self.unit.replace("GBp/th", "p/th")
        if self.basis == "fixed":
            text = f"fixed {self.fixed_price:g} {unit}"
        elif self.basis == "index":
            sign = "+" if self.premium >= 0 else "−"
            text = f"{self.index.words()} {sign} {abs(self.premium):g} {unit}"
        else:
            parts = [f"{c.weight:g} × {c.index.words()}" for c in self.components]
            sign = "+" if self.constant >= 0 else "−"
            text = f"{' + '.join(parts)} {sign} {abs(self.constant):g} {unit}"
        if self.floor is not None and self.cap is not None:
            text += f", within {self.floor:g}–{self.cap:g} {unit}"
        elif self.cap is not None:
            text += f", capped at {self.cap:g} {unit}"
        elif self.floor is not None:
            text += f", floored at {self.floor:g} {unit}"
        return text


@dataclass(frozen=True)
class IndexPoint:
    """One index value a lookup holds for a period, with where it came from."""

    value: float
    unit: str
    input_class: str
    source_ref: str
    as_of: str | None = None
    observations: int = 1


#: ``lookup(index, first_day, last_day) -> IndexPoint | None``: the averaged index over the
#: window the averaging rule names, or None when the store does not hold it.
Lookup = Callable[[PriceIndex, date, date], IndexPoint | None]


@dataclass
class PriceResult:
    value: float | None
    unit: str
    input_class: str
    words: str
    inputs: list[dict] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "value": self.value,
            "unit": self.unit,
            "currency": _UNIT_CURRENCY.get(self.unit),
            "input_class": self.input_class,
            "words": self.words,
            "inputs": self.inputs,
            "missing": self.missing,
            "notes": self.notes,
        }


def _month_bounds(month: str) -> tuple[date, date]:
    first = date(int(month[:4]), int(month[5:7]), 1)
    last = (first + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    return first, last


def averaging_window(index: PriceIndex, first: date, last: date, pricing_month: str | None):
    """The days an index is read over for a delivery period ``first``..``last``."""

    if index.averaging == "pricing_month":
        return _month_bounds(pricing_month or f"{first:%Y-%m}")
    if index.averaging == "month_before_delivery":
        start = first.replace(day=1)
        before = start - timedelta(days=1)
        return before.replace(day=1), before
    if index.averaging == "last_n_trading_days":
        start = first.replace(day=1) - timedelta(days=1)
        # N trading days back: about 1.4 calendar days each (weekends); the lookup counts closes.
        return start - timedelta(days=int(index.n_days * 1.4) + 2), start
    if index.averaging == "delivery_month":
        return _month_bounds(f"{first:%Y-%m}")
    return first, last


def weakest(classes: list[str]) -> str:
    if not classes:
        return "contract"
    return max(classes, key=lambda item: CLASS_ORDER.index(item) if item in CLASS_ORDER else 99)


def _in_unit(point: IndexPoint, unit: str) -> tuple[float | None, str | None]:
    """The index value in the contract's unit, or the reason it cannot be.

    Units of one currency convert through the units authority (p/th to GBP/MWh is exact); a
    value in another currency is refused, because the contract's FX rule is not modelled yet.
    """

    if point.unit == unit:
        return point.value, None
    try:
        return convert_price(point.value, point.unit, unit), None
    except (UnitError, ValueError, KeyError) as exc:
        reason = f"in {point.unit}, not {unit} ({exc})"
        return None, f"{reason}; the contract's FX rule is not modelled yet"


def evaluate(terms: PriceTerms, first: date, last: date, lookup: Lookup) -> PriceResult:
    """The contract price for the delivery period ``first``..``last`` (see the module doc)."""

    words = terms.words()
    unit = terms.unit
    if terms.basis == "fixed":
        return PriceResult(terms.fixed_price, unit, "contract", words)
    weighted = (
        [(terms.index, 1.0)]
        if terms.basis == "index"
        else [(component.index, component.weight) for component in terms.components]
    )
    base = terms.premium if terms.basis == "index" else terms.constant
    inputs: list[dict] = []
    missing: list[str] = []
    total = base
    classes: list[str] = []
    for index, weight in weighted:
        window = averaging_window(index, first, last, terms.pricing_month)
        point = lookup(index, *window)
        label = index.words()
        if point is None:
            missing.append(f"{label}: index not held for {window[0]:%d %b %Y}–{window[1]:%d %b %Y}")
            continue
        value, problem = _in_unit(point, unit)
        if value is None:
            missing.append(f"{label}: {problem}")
            continue
        classes.append(point.input_class)
        total += weight * value
        inputs.append(
            {
                "index": label,
                "weight": weight,
                "value": round(value, 6),
                "unit": unit,
                "read_value": point.value,
                "read_unit": point.unit,
                "input_class": point.input_class,
                "source_ref": point.source_ref,
                "as_of": point.as_of,
                "window": [window[0].isoformat(), window[1].isoformat()],
                "observations": point.observations,
            }
        )
    if missing:
        return PriceResult(None, unit, "missing", words, inputs, missing)
    notes = []
    if terms.cap is not None and total > terms.cap:
        notes.append(f"capped: {total:.4f} > {terms.cap:g}")
        total = terms.cap
    if terms.floor is not None and total < terms.floor:
        notes.append(f"floored: {total:.4f} < {terms.floor:g}")
        total = terms.floor
    if terms.rounding_dp is not None:
        total = round(total, terms.rounding_dp)
    return PriceResult(round(total, 6), unit, weakest(classes), words, inputs, [], notes)


def index_from_label(label: str) -> PriceIndex | None:
    """An index from the desk's label (``NBP day-ahead``, ``TTF month-ahead``)."""

    text = (label or "").strip()
    head, _, rest = text.partition(" ")
    code = head.upper()
    if code not in INDEX_NAMES:
        return None
    rest = rest.lower()
    if "day" in rest:
        return PriceIndex(index=code, product="day_ahead", averaging="delivery_day")
    if "season" in rest or "year" in rest or "month" in rest or not rest:
        return PriceIndex(index=code, product="month_ahead", averaging="month_before_delivery")
    return None
