"""Currencies and FX: one registry and one conversion rule for every office and market.

Every amount carries an ISO 4217 currency. Markets sometimes quote in a sub-unit (NBP in
pence, GBp; JSE in cents, ZAc) or in a market convention that is not an ISO code (offshore
renminbi, CNH); those are *quote units* that resolve to an ISO currency and a divisor, so
money is always stored and summed in the ISO currency.

FX is always explicit: an :class:`FxTable` holds dated rates from a named source (ECB
reference rates by default, a customer's WM/Reuters or BFIX fix when licensed) and
converts by a direct rate, its inverse, or through one pivot currency. A missing rate is an
error, never a guess and never 1.0.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal


@dataclass(frozen=True)
class Currency:
    """An ISO 4217 currency."""

    code: str
    numeric: str
    name: str
    minor_units: int  # decimal places of the minor unit (JPY 0, EUR 2, KWD 3)
    symbol: str = ""


#: Currencies the desks and offices are likely to meet. Extend as offices are added.
CURRENCIES: dict[str, Currency] = {
    c.code: c
    for c in (
        Currency("EUR", "978", "Euro", 2, "€"),
        Currency("GBP", "826", "Pound sterling", 2, "£"),
        Currency("USD", "840", "US dollar", 2, "$"),
        Currency("CAD", "124", "Canadian dollar", 2, "C$"),
        Currency("CNY", "156", "Renminbi (yuan)", 2, "¥"),
        Currency("SGD", "702", "Singapore dollar", 2, "S$"),
        Currency("JPY", "392", "Yen", 0, "¥"),
        Currency("KRW", "410", "Won", 0, "₩"),
        Currency("CHF", "756", "Swiss franc", 2, "CHF"),
        Currency("NOK", "578", "Norwegian krone", 2, "kr"),
        Currency("SEK", "752", "Swedish krona", 2, "kr"),
        Currency("DKK", "208", "Danish krone", 2, "kr"),
        Currency("PLN", "985", "Zloty", 2, "zł"),
        Currency("CZK", "203", "Czech koruna", 2, "Kč"),
        Currency("HUF", "348", "Forint", 2, "Ft"),
        Currency("AUD", "036", "Australian dollar", 2, "A$"),
        Currency("INR", "356", "Indian rupee", 2, "₹"),
        Currency("HKD", "344", "Hong Kong dollar", 2, "HK$"),
        Currency("TRY", "949", "Turkish lira", 2, "₺"),
        Currency("QAR", "634", "Qatari riyal", 2, "QR"),
        Currency("AED", "784", "UAE dirham", 2, "AED"),
        Currency("ZAR", "710", "Rand", 2, "R"),
    )
}


@dataclass(frozen=True)
class QuoteUnit:
    """A market quote convention that resolves to an ISO currency and a divisor."""

    code: str
    currency: str
    divisor: int  # quote units per one unit of the currency
    note: str = ""


#: Sub-units and market conventions, keyed by their exact spelling (``GBp`` is pence,
#: ``GBP`` is pounds). Prices in these are converted on entry.
QUOTE_UNITS: dict[str, QuoteUnit] = {
    q.code: q
    for q in (
        QuoteUnit("GBp", "GBP", 100, "pence; NBP gas quotes in pence per therm"),
        QuoteUnit("GBX", "GBP", 100, "pence, exchange spelling"),
        QuoteUnit("USc", "USD", 100, "US cents"),
        QuoteUnit("EURc", "EUR", 100, "euro cents"),
        QuoteUnit("ZAc", "ZAR", 100, "South African cents"),
        QuoteUnit("CNH", "CNY", 1, "offshore renminbi; priced separately from onshore CNY"),
    )
}


class CurrencyError(ValueError):
    """Unknown currency or a conversion without a rate."""


def currency(code: str) -> Currency:
    """The ISO currency for a code (case-insensitive)."""

    try:
        return CURRENCIES[(code or "").strip().upper()]
    except KeyError as exc:
        raise CurrencyError(f"unknown currency {code!r}") from exc


def resolve_quote_unit(code: str) -> tuple[str, int]:
    """(ISO currency, divisor) for an ISO code or a quote unit such as GBp or CNH.

    ``GBp`` and ``GBP`` differ only in case, so the case-sensitive spelling decides:
    ``GBp``/``GBX`` are pence, ``GBP`` is pounds.
    """

    text = (code or "").strip()
    if text in QUOTE_UNITS:
        return QUOTE_UNITS[text].currency, QUOTE_UNITS[text].divisor
    upper = text.upper()
    if upper in CURRENCIES:
        return upper, 1
    # Unambiguous conventions in any case (CNH, ZAC); GBP stays pounds above.
    quote = next((q for code, q in QUOTE_UNITS.items() if code.upper() == upper), None)
    if quote is None:
        raise CurrencyError(f"unknown currency or quote unit {code!r}")
    return quote.currency, quote.divisor


@dataclass(frozen=True)
class Money:
    """An amount in an ISO currency, rounded only when presented."""

    amount: Decimal
    currency: str

    def rounded(self) -> Decimal:
        places = Decimal(1).scaleb(-currency(self.currency).minor_units)
        return self.amount.quantize(places, rounding=ROUND_HALF_EVEN)


@dataclass(frozen=True)
class FxRate:
    """``rate`` units of ``quote`` per one ``base`` on ``as_of`` from ``source``."""

    base: str
    quote: str
    rate: float
    as_of: date
    source: str


@dataclass
class FxTable:
    """Dated FX rates from named sources, converting directly, inversely or via a pivot."""

    rates: dict[tuple[str, str], FxRate] = field(default_factory=dict)
    pivot: str = "EUR"

    @classmethod
    def from_rates(cls, rates: Iterable[FxRate], pivot: str = "EUR") -> FxTable:
        table = cls(pivot=pivot)
        for rate in rates:
            table.add(rate)
        return table

    @classmethod
    def from_pivot_map(
        cls, per_pivot: Mapping[str, float], *, as_of: date, source: str, pivot: str = "EUR"
    ) -> FxTable:
        """From ``{currency: units per one pivot}``, the ECB reference-rate shape."""

        return cls.from_rates(
            (
                FxRate(pivot, code.upper(), float(value), as_of, source)
                for code, value in per_pivot.items()
                if value and code.upper() != pivot
            ),
            pivot=pivot,
        )

    def add(self, rate: FxRate) -> None:
        if not rate.rate > 0:
            raise CurrencyError(f"non-positive FX rate {rate}")
        key = (rate.base.upper(), rate.quote.upper())
        held = self.rates.get(key)
        if held is None or rate.as_of >= held.as_of:
            self.rates[key] = rate

    def rate(self, base: str, quote: str) -> float:
        """Units of ``quote`` per one ``base``."""

        base, quote = base.upper(), quote.upper()
        if base == quote:
            return 1.0
        direct = self._direct(base, quote)
        if direct is not None:
            return direct
        to_pivot = self._direct(base, self.pivot)
        from_pivot = self._direct(self.pivot, quote)
        if to_pivot is not None and from_pivot is not None:
            return to_pivot * from_pivot
        raise CurrencyError(f"no FX rate from {base} to {quote}")

    def has(self, base: str, quote: str) -> bool:
        try:
            self.rate(base, quote)
        except CurrencyError:
            return False
        return True

    def convert(self, amount: float, base: str, quote: str) -> float:
        return amount * self.rate(base, quote)

    def _direct(self, base: str, quote: str) -> float | None:
        if base == quote:
            return 1.0
        if (base, quote) in self.rates:
            return self.rates[(base, quote)].rate
        if (quote, base) in self.rates:
            return 1.0 / self.rates[(quote, base)].rate
        return None
