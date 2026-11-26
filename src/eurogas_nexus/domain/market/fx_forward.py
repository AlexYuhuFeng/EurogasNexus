"""Forward FX for a delivery period, by covered interest parity from the rates the product holds.

A price for delivery in a future period, quoted in currency X, is worth in currency Y what that
cash flow could be hedged at today: the forward rate to the period's value date, not today's
spot. The product holds the ECB euro reference rates (``fx_fixings``) and the overnight
benchmark fixings SONIA, €STR and SOFR (``interest_rates``), so the forward is derived from them
(design basis 2, section D.5):

1. **Spot** ``S(X/Y)`` = units of Y per one X from the latest ECB reference rates held on or
   before the as-of date, crossed through EUR when neither currency is EUR, named with its date.
2. **Rates** ``r_X``, ``r_Y`` = the latest held overnight fixing of each currency's benchmark
   (``DEFAULT_BENCHMARK_FOR_CURRENCY``), each on its own day count: GBP ACT/365F, EUR and USD
   ACT/360.
3. **Value date** ``t`` = the middle of the delivery period: the 15th for a month, the middle
   gas day for a quarter, season or year. A prompt product (within-day, day-ahead, weekend,
   balance-of-month) settles at spot: no forward.
4. **Forward** ``F = S × (1 + r_Y·τ_Y) / (1 + r_X·τ_X)`` with ``τ = days / basis`` counted from
   the spot reference date to ``t``, simple interest up to one year; beyond one year
   ``F = S × (1 + r_Y)^τ_Y / (1 + r_X)^τ_X`` (annual compounding). Both forms agree at τ = 1.
5. **Horizon**: beyond 24 months the derived forward is refused; only a licensed forward may
   convert there.
6. **Tolerance**: a flat overnight fixing is not a term curve and ignores the cross-currency
   basis, so every derived rate carries 0.1 % of the rate up to 3 months, 0.3 % to 12 months
   and 1 % beyond.
7. **Licensed forwards** (outright forwards imported through the customer's entitlement, stored
   as FX rows of rate type :data:`LICENSED_FORWARD_RATE_TYPE`) take precedence: the one whose
   value date is nearest the target inside the delivery period is used, labelled "licensed",
   with no tolerance.

Every result carries its method, inputs and dates (:meth:`FxConversionRate.as_dict`); nothing
here fills a missing rate. A refusal says which rate is missing ("not convertible: no EURGBP
rate held"). A simulated input (a demo source) makes the rate simulated.

本模块按抛补利率平价由 ECB 参考汇率与隔夜基准利率推导交割期远期汇率；超过 24 个月拒绝
推导（除非有授权远期），每个结果都带方法、输入及日期，缺少数据时明确拒绝，绝不猜测。
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from eurogas_nexus.domain.market.interest_rates import (
    BENCHMARKS,
    DEFAULT_BENCHMARK_FOR_CURRENCY,
    Benchmark,
    InterestRateError,
    RateFixing,
    resolve_financing_rate,
)

#: The method strings a conversion row shows (D.5 step 4 and 6).
METHOD_DERIVED = "derived: covered interest parity"
METHOD_LICENSED = "licensed"
METHOD_SPOT = "spot: ECB reference rate"
METHOD_IDENTITY = "same currency"

#: FX rows of this rate type are outright forwards from a licensed source (value date = the
#: forward's value date). Nothing in the product fetches them; an operator import does.
LICENSED_FORWARD_RATE_TYPE = "forward_outright"

#: A derived forward is refused beyond this many months after the spot reference date.
HORIZON_MONTHS = 24
#: Up to this many days the forward uses simple interest; beyond, annual compounding.
SIMPLE_INTEREST_DAYS = 365
#: Days without a newer ECB reference rate before the spot is refused (weekends and TARGET
#: holidays leave at most four days without a fixing).
MAX_REFERENCE_STALENESS_DAYS = 5
#: Days without a newer benchmark fixing before a rate is refused (the benchmark module's rule).
MAX_FIXING_STALENESS_DAYS = 7
#: Tolerance on the rate by days to the value date (D.5 step 5).
TOLERANCE_STEPS: tuple[tuple[int, float], ...] = ((92, 0.1), (366, 0.3))
TOLERANCE_BEYOND_PCT = 1.0

#: Product kinds that settle at spot (``domain.market.products.PRODUCT_KINDS``).
PROMPT_KINDS = frozenset({"within_day", "day_ahead", "weekend", "balance_of_month", "spot"})

_SIMULATED_SUFFIX = "_sim"


class FxForwardError(ValueError):
    """A conversion rate cannot be given; ``code`` names why, the message says what is missing."""

    def __init__(self, code: str, message: str, params: dict[str, str] | None = None) -> None:
        super().__init__(message)
        self.code = code
        #: What the sentence names, for a reader that says it in its own language.
        self.params = dict(params or {})


def is_simulated_source(source_system: str | None) -> bool:
    """Whether rows of this source are simulated (the ``*_Sim`` demo families)."""

    from eurogas_nexus.domain.ontology.provenance import is_simulated

    return is_simulated(source_system)


@dataclass(frozen=True)
class Delivery:
    """The delivery period a price is for: first and last gas day, kind and desk label."""

    first: date
    last: date
    kind: str
    label: str

    @property
    def prompt(self) -> bool:
        """A prompt product converts at spot."""

        return self.kind in PROMPT_KINDS

    def value_date(self) -> date:
        """The forward's value date: the 15th of a month, else the middle gas day (D.5 step 3)."""

        if self.kind == "month":
            return self.first.replace(day=15)
        return self.first + timedelta(days=(self.last - self.first).days // 2)

    def as_dict(self) -> dict[str, str]:
        return {
            "label": self.label,
            "kind": self.kind,
            "first_gas_day": self.first.isoformat(),
            "last_gas_day": self.last.isoformat(),
        }


def delivery_from_period(period: object) -> Delivery:
    """A :class:`Delivery` from a resolved product (``domain.market.products.DeliveryPeriod``)."""

    return Delivery(
        first=period.first_gas_day,  # type: ignore[attr-defined]
        last=period.last_gas_day,  # type: ignore[attr-defined]
        kind=period.kind,  # type: ignore[attr-defined]
        label=period.label,  # type: ignore[attr-defined]
    )


def delivery_from_bounds(start: datetime | date, end_exclusive: datetime | date) -> Delivery:
    """A :class:`Delivery` from a stored observation's period bounds.

    A window of one or two days is a prompt product; a window that is one calendar month is a
    month (labelled ``Jan-27``); anything longer is a strip labelled by its first and last day.
    """

    first = start.date() if isinstance(start, datetime) else start
    end = end_exclusive.date() if isinstance(end_exclusive, datetime) else end_exclusive
    last = max(first, end - timedelta(days=1))
    span = (last - first).days + 1
    if span <= 2:
        return Delivery(first, last, "day_ahead", first.isoformat())
    if first.day == 1 and (last + timedelta(days=1)).day == 1 and span <= 31:
        return Delivery(first, last, "month", f"{first:%b}-{first:%y}")
    return Delivery(first, last, "strip", f"{first.isoformat()}..{last.isoformat()}")


@dataclass(frozen=True)
class ReferenceRate:
    """One ECB-convention rate: units of ``currency`` per one EUR on ``value_date``."""

    currency: str
    units_per_eur: float
    value_date: date
    source_system: str

    @property
    def simulated(self) -> bool:
        return is_simulated_source(self.source_system)


@dataclass(frozen=True)
class LicensedForward:
    """An outright forward from a licensed source: units of ``quote`` per one ``base``."""

    base: str
    quote: str
    value_date: date
    rate: float
    as_of: date
    source_system: str


@dataclass(frozen=True)
class FxHoldings:
    """The FX facts the product holds for a caller (entitlement already applied)."""

    reference_rates: tuple[ReferenceRate, ...] = ()
    fixings: tuple[RateFixing, ...] = ()
    licensed_forwards: tuple[LicensedForward, ...] = ()
    _by_date: dict[date, dict[str, ReferenceRate]] = field(
        default_factory=dict, compare=False, repr=False
    )

    def __post_init__(self) -> None:
        index: dict[date, dict[str, ReferenceRate]] = {}
        for rate in self.reference_rates:
            day = index.setdefault(rate.value_date, {})
            held = day.get(rate.currency)
            # A real (ECB) fixing beats a simulated one for the same day.
            if held is None or (held.simulated and not rate.simulated):
                day[rate.currency] = rate
        object.__setattr__(self, "_by_date", index)

    @classmethod
    def from_rows(
        cls,
        fx_rows: Iterable[Mapping[str, object]],
        rate_rows: Iterable[Mapping[str, object] | RateFixing] = (),
    ) -> FxHoldings:
        """From FX observation payloads and interest-rate fixing rows (as the API reads them).

        FX rows of rate type ``reference`` give ECB-convention rates (``EURxxx`` rows; an
        ``xxxEUR`` row is inverted); rows of :data:`LICENSED_FORWARD_RATE_TYPE` from a non-ECB
        source are licensed forwards. Other rate types (WMR, BFIX fixes) are not used here.
        """

        reference: list[ReferenceRate] = []
        forwards: list[LicensedForward] = []
        for row in fx_rows:
            rate = row.get("rate")
            if not isinstance(rate, (int, float)) or not rate > 0:
                continue
            pair = str(row.get("pair") or "").upper().replace("/", "")
            if len(pair) != 6:
                pair = f"{row.get('base_currency') or ''}{row.get('quote_currency') or ''}".upper()
            if len(pair) != 6:
                continue
            value_date = _as_date(row.get("value_date"))
            if value_date is None:
                continue
            rate_type = str(row.get("rate_type") or "")
            source = str(row.get("source_system") or "")
            if rate_type == LICENSED_FORWARD_RATE_TYPE and source.upper() != "ECB":
                as_of = _as_date(row.get("observed_at_utc")) or value_date
                forwards.append(
                    LicensedForward(pair[:3], pair[3:], value_date, float(rate), as_of, source)
                )
            elif rate_type == "reference":
                if pair.startswith("EUR"):
                    reference.append(ReferenceRate(pair[3:], float(rate), value_date, source))
                elif pair.endswith("EUR"):
                    reference.append(ReferenceRate(pair[:3], 1.0 / float(rate), value_date, source))
        fixings = []
        for item in rate_rows:
            if isinstance(item, RateFixing):
                fixings.append(item)
                continue
            value_date = _as_date(item.get("value_date"))
            benchmark_id = str(item.get("benchmark_id") or "")
            rate_pct = item.get("rate_pct")
            if value_date is None or benchmark_id not in BENCHMARKS:
                continue
            if not isinstance(rate_pct, (int, float)):
                continue
            fixings.append(
                RateFixing(
                    benchmark_id,
                    value_date,
                    float(rate_pct),
                    str(item.get("source_system") or ""),
                    str(item.get("source_reference") or ""),
                )
            )
        return cls(tuple(reference), tuple(fixings), tuple(forwards))

    def reference_on(self, currency: str, as_of: date) -> ReferenceRate | None:
        """The newest reference rate of ``currency`` on or before ``as_of`` within the limit."""

        currency = currency.upper()
        for back in range(MAX_REFERENCE_STALENESS_DAYS + 1):
            day = self._by_date.get(as_of - timedelta(days=back))
            if day and currency in day:
                return day[currency]
        return None

    def latest_date(self) -> date | None:
        """The newest date any reference rate is held for."""

        return max(self._by_date) if self._by_date else None


@dataclass(frozen=True)
class SpotReference:
    """``rate`` = units of ``quote`` per one ``base`` on ``value_date``, from these inputs."""

    base: str
    quote: str
    rate: float
    value_date: date
    inputs: tuple[ReferenceRate, ...]

    @property
    def simulated(self) -> bool:
        return any(item.simulated for item in self.inputs)

    def as_dict(self) -> dict[str, object]:
        return {
            "pair": f"{self.base}{self.quote}",
            "rate": self.rate,
            "value_date": self.value_date.isoformat(),
            "crossed_via": "EUR" if "EUR" not in (self.base, self.quote) else None,
            "inputs": [
                {
                    "pair": f"EUR{item.currency}",
                    "rate": item.units_per_eur,
                    "value_date": item.value_date.isoformat(),
                    "source_system": item.source_system,
                }
                for item in self.inputs
            ],
            "source": (
                "simulated reference rate" if self.simulated else "ECB euro reference rate"
            ),
            "simulated": self.simulated,
        }


@dataclass(frozen=True)
class RateUsed:
    """One benchmark fixing used in a derived forward, with its accrual."""

    benchmark: Benchmark
    rate_pct: float
    fixing_date: date
    days: int
    source_system: str

    @property
    def year_fraction(self) -> float:
        return self.days / self.benchmark.day_count_days

    @property
    def simulated(self) -> bool:
        return is_simulated_source(self.source_system)

    def growth(self, compounded: bool) -> float:
        rate = self.rate_pct / 100.0
        if compounded:
            return (1.0 + rate) ** self.year_fraction
        return 1.0 + rate * self.year_fraction

    def as_dict(self) -> dict[str, object]:
        return {
            "benchmark": self.benchmark.benchmark_id,
            "label": self.benchmark.label,
            "currency": self.benchmark.currency,
            "rate_pct": self.rate_pct,
            "fixing_date": self.fixing_date.isoformat(),
            "day_count": self.benchmark.day_count,
            "days": self.days,
            "year_fraction": self.year_fraction,
            "source_system": self.source_system,
            "attribution": self.benchmark.attribution,
        }


@dataclass(frozen=True)
class FxConversionRate:
    """Units of ``quote`` per one ``base`` for a delivery period, and how it was obtained."""

    base: str
    quote: str
    rate: float
    method: str
    value_date: date | None
    delivery: Delivery | None
    spot: SpotReference | None = None
    rates: tuple[RateUsed, ...] = ()
    compounding: str | None = None
    licensed: LicensedForward | None = None
    tolerance_pct: float = 0.0
    limitations: tuple[str, ...] = ()

    @property
    def simulated(self) -> bool:
        return bool(
            (self.spot is not None and self.spot.simulated)
            or any(item.simulated for item in self.rates)
            or (self.licensed is not None and is_simulated_source(self.licensed.source_system))
        )

    @property
    def input_class(self) -> str:
        """The data-quality class of the rate (B.2): derived, sourced, reference or simulated."""

        if self.simulated:
            return "simulated"
        if self.method == METHOD_DERIVED:
            return "derived"
        if self.method == METHOD_LICENSED:
            return "sourced"
        return "reference"

    @property
    def label(self) -> str:
        """The words shown beside the converted figure (D.5 step 4, 6)."""

        if self.method == METHOD_DERIVED:
            names = ", ".join(item.benchmark.label.split(" (")[0] for item in self.rates)
            return f"derived (interest parity from {names}, flat rate)"
        if self.method == METHOD_LICENSED and self.licensed is not None:
            return f"sourced ({self.licensed.source_system})"
        if self.method == METHOD_SPOT and self.spot is not None:
            kind = "simulated reference rate" if self.spot.simulated else "ECB reference rate"
            return f"{kind} {self.spot.value_date.isoformat()}"
        return self.method

    @property
    def tolerance_abs(self) -> float:
        return abs(self.rate) * self.tolerance_pct / 100.0

    def inverse(self) -> FxConversionRate:
        """The same rate the other way round (units of ``base`` per one ``quote``)."""

        return FxConversionRate(
            base=self.quote,
            quote=self.base,
            rate=1.0 / self.rate,
            method=self.method,
            value_date=self.value_date,
            delivery=self.delivery,
            spot=self.spot,
            rates=self.rates,
            compounding=self.compounding,
            licensed=self.licensed,
            tolerance_pct=self.tolerance_pct,
            limitations=self.limitations,
        )

    def desk_quote(self) -> dict[str, object]:
        """The rate as a desk quotes the pair (EUR, then GBP, then USD as the base currency)."""

        order = ("EUR", "GBP", "USD")

        def rank(code: str) -> int:
            return order.index(code) if code in order else len(order)

        flip = rank(self.quote) < rank(self.base)
        base, quote = (self.quote, self.base) if flip else (self.base, self.quote)
        spot = self.spot.rate if self.spot else None
        return {
            "pair": f"{base}/{quote}",
            "rate": 1.0 / self.rate if flip else self.rate,
            "spot_rate": (1.0 / spot if flip else spot) if spot else None,
        }

    def as_dict(self) -> dict[str, object]:
        return {
            "pair": f"{self.base}{self.quote}",
            "desk_quote": self.desk_quote(),
            "base": self.base,
            "quote": self.quote,
            "rate": self.rate,
            "quoted_as": f"{self.quote} per 1 {self.base}",
            "method": self.method,
            "label": self.label,
            "input_class": self.input_class,
            "simulated": self.simulated,
            "value_date": self.value_date.isoformat() if self.value_date else None,
            "delivery": self.delivery.as_dict() if self.delivery else None,
            "spot": self.spot.as_dict() if self.spot else None,
            "rates": [item.as_dict() for item in self.rates],
            "days": self.rates[0].days if self.rates else None,
            "compounding": self.compounding,
            "licensed": (
                {
                    "source_system": self.licensed.source_system,
                    "value_date": self.licensed.value_date.isoformat(),
                    "as_of": self.licensed.as_of.isoformat(),
                }
                if self.licensed
                else None
            ),
            "tolerance": {"relative_pct": self.tolerance_pct, "absolute": self.tolerance_abs},
            "horizon_months": HORIZON_MONTHS,
            "limitations": list(self.limitations),
        }


def spot_reference(holdings: FxHoldings, base: str, quote: str, as_of: date) -> SpotReference:
    """``S(base/quote)`` from the ECB reference rates held on or before ``as_of``.

    Raises:
        FxForwardError: ``no_reference_rate`` when a needed EURxxx rate is not held.
    """

    base, quote = base.upper(), quote.upper()
    inputs: list[ReferenceRate] = []
    per_eur: dict[str, float] = {"EUR": 1.0}
    for currency in (base, quote):
        if currency == "EUR":
            continue
        held = holdings.reference_on(currency, as_of)
        if held is None:
            raise FxForwardError(
                "no_reference_rate", f"not convertible: no EUR{currency} rate held"
            )
        inputs.append(held)
        per_eur[currency] = held.units_per_eur
    value_date = min((item.value_date for item in inputs), default=as_of)
    return SpotReference(base, quote, per_eur[quote] / per_eur[base], value_date, tuple(inputs))


def _add_months(day: date, months: int) -> date:
    index = day.year * 12 + day.month - 1 + months
    year, month = divmod(index, 12)
    month += 1
    for candidate in (day.day, 30, 29, 28):
        try:
            return date(year, month, candidate)
        except ValueError:
            continue
    raise AssertionError("unreachable")


def tolerance_pct_for(days: int) -> float:
    """The D.5 tolerance of a derived forward ``days`` after spot."""

    for limit, pct in TOLERANCE_STEPS:
        if days <= limit:
            return pct
    return TOLERANCE_BEYOND_PCT


def _benchmark_rate(holdings: FxHoldings, currency: str, as_of: date, days: int) -> RateUsed:
    benchmark_id = DEFAULT_BENCHMARK_FOR_CURRENCY.get(currency)
    if benchmark_id is None:
        raise FxForwardError(
            "no_benchmark",
            f"not convertible forward: no benchmark rate for {currency} "
            "(forwards are derived for EUR, GBP and USD only)",
        )
    try:
        resolved = resolve_financing_rate(
            holdings.fixings,
            benchmark_id,
            as_of=as_of,
            max_staleness_days=MAX_FIXING_STALENESS_DAYS,
        )
    except InterestRateError as exc:
        name = BENCHMARKS[benchmark_id].label.split(" (")[0]
        raise FxForwardError(
            "no_benchmark_rate",
            f"not convertible forward: no {name} fixing held ({exc})",
            {"currency": currency, "benchmark": name, "as_of": as_of.isoformat()},
        ) from exc
    return RateUsed(
        BENCHMARKS[benchmark_id],
        resolved.benchmark_rate_pct,
        resolved.fixing_date,
        days,
        resolved.source_system,
    )


def _licensed_for(
    holdings: FxHoldings, base: str, quote: str, delivery: Delivery, target: date
) -> tuple[LicensedForward, float] | None:
    """The licensed forward nearest ``target`` inside the delivery period, as base->quote."""

    best: tuple[int, LicensedForward, float] | None = None
    for item in holdings.licensed_forwards:
        if not delivery.first <= item.value_date <= delivery.last:
            continue
        if (item.base, item.quote) == (base, quote):
            rate = item.rate
        elif (item.base, item.quote) == (quote, base):
            rate = 1.0 / item.rate
        else:
            continue
        distance = abs((item.value_date - target).days)
        if best is None or (distance, -item.as_of.toordinal()) < (
            best[0],
            -best[1].as_of.toordinal(),
        ):
            best = (distance, item, rate)
    return (best[1], best[2]) if best else None


def conversion_rate(
    holdings: FxHoldings,
    base: str,
    quote: str,
    *,
    as_of: date,
    delivery: Delivery | None = None,
) -> FxConversionRate:
    """Units of ``quote`` per one ``base`` for a price delivered in ``delivery``.

    No delivery, a prompt product, or a value date on or before the spot date: the spot
    reference rate. A future period: a licensed forward when one is held for the period, else
    the covered-interest-parity forward of D.5.

    Raises:
        FxForwardError: a missing reference rate or benchmark fixing, or a derived forward
            beyond :data:`HORIZON_MONTHS`.
    """

    base, quote = base.upper(), quote.upper()
    if base == quote:
        return FxConversionRate(base, quote, 1.0, METHOD_IDENTITY, None, delivery)
    target = delivery.value_date() if delivery is not None and not delivery.prompt else None
    if delivery is not None and target is not None:
        licensed = _licensed_for(holdings, base, quote, delivery, target)
        if licensed is not None:
            item, rate = licensed
            return FxConversionRate(
                base, quote, rate, METHOD_LICENSED, item.value_date, delivery, licensed=item
            )
    spot = spot_reference(holdings, base, quote, as_of)
    if target is None or target <= spot.value_date:
        return FxConversionRate(
            base,
            quote,
            spot.rate,
            METHOD_SPOT,
            spot.value_date,
            delivery,
            spot=spot,
            limitations=(
                ("prompt delivery converts at the spot reference rate",)
                if delivery is not None
                else ()
            ),
        )
    horizon_end = _add_months(spot.value_date, HORIZON_MONTHS)
    if target > horizon_end:
        raise FxForwardError(
            "beyond_horizon",
            f"not convertible: {delivery.label if delivery else target.isoformat()} is more "
            f"than {HORIZON_MONTHS} months after the spot date {spot.value_date.isoformat()}; "
            "a derived forward is refused there without licensed forwards",
        )
    days = (target - spot.value_date).days
    for currency in (base, quote):
        if currency not in DEFAULT_BENCHMARK_FOR_CURRENCY:
            raise FxForwardError(
                "no_benchmark",
                f"not convertible forward: no benchmark rate for {currency} "
                "(forwards are derived for EUR, GBP and USD only)",
            )
    rate_base =_benchmark_rate(holdings, base, as_of, days)
    rate_quote = _benchmark_rate(holdings, quote, as_of, days)
    compounded = days > SIMPLE_INTEREST_DAYS
    forward = spot.rate * rate_quote.growth(compounded) / rate_base.growth(compounded)
    return FxConversionRate(
        base,
        quote,
        forward,
        METHOD_DERIVED,
        target,
        delivery,
        spot=spot,
        rates=(rate_base, rate_quote),
        compounding="annual" if compounded else "simple",
        tolerance_pct=tolerance_pct_for(days),
        limitations=(
            "a flat overnight fixing, not a term curve",
            "ignores the cross-currency basis",
        ),
    )


def _as_date(value: object) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and len(value) >= 10:
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None
