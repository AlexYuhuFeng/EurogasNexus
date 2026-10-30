"""Overnight benchmark interest rates and contract financing rates.

Gas supply and LNG contracts that price the time value of money (early-payment
credit, late-payment interest, prepayment discount) usually reference an overnight
risk-free rate plus a contractual spread, observed on or before a stated date:

| Benchmark | Currency | Administrator | Day count | Published |
|---|---|---|---|---|
| SONIA | GBP | Bank of England | ACT/365F | 09:00 London, T+1 |
| €STR (ESTR) | EUR | European Central Bank | ACT/360 | 08:00 CET, T+1 |
| SOFR | USD | Federal Reserve Bank of New York | ACT/360 | 08:00 New York, T+1 |

All three are published free of charge by their administrators and may be used
commercially with attribution (see ``docs/operations/INTEREST_RATES.md``).

This module is pure: it parses the administrators' public formats, picks the
fixing for a date, adds the spread and converts between day-count bases. It never
fills a missing fixing: beyond ``max_staleness_days`` it refuses.

本模块管理隔夜基准利率（SONIA/€STR/SOFR）：解析官方公开数据、按日期取定盘、
加合同点差并按计息基准换算；缺失或过期的定盘一律拒绝，不做假设。
"""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime

MAX_RATE_PCT = 50.0
MIN_RATE_PCT = -5.0


class InterestRateError(ValueError):
    """Unknown benchmark, malformed source payload or unusable fixing."""


@dataclass(frozen=True)
class Benchmark:
    """One overnight benchmark rate.

    Attributes:
        benchmark_id: Stable id (``SONIA``, ``ESTR``, ``SOFR``).
        currency: ISO currency of the rate.
        administrator: Publishing administrator (entitlement source family).
        day_count_days: Year basis of the day count (365 for ACT/365F, 360 for ACT/360).
        label: Desk label.
        attribution: Attribution text required by the administrator's terms.
    """

    benchmark_id: str
    currency: str
    administrator: str
    day_count_days: int
    label: str
    attribution: str

    @property
    def day_count(self) -> str:
        """Day-count label (``ACT/365F`` or ``ACT/360``)."""

        return "ACT/365F" if self.day_count_days == 365 else "ACT/360"


BENCHMARKS: dict[str, Benchmark] = {
    "SONIA": Benchmark(
        "SONIA", "GBP", "BOE", 365, "SONIA (Sterling Overnight Index Average)",
        "Source: Bank of England. SONIA is administered by the Bank of England.",
    ),
    "ESTR": Benchmark(
        "ESTR", "EUR", "ECB", 360, "€STR (Euro Short-Term Rate)",
        "Source: European Central Bank (ECB Data Portal).",
    ),
    "SOFR": Benchmark(
        "SOFR", "USD", "NYFED", 360, "SOFR (Secured Overnight Financing Rate)",
        "Source: Federal Reserve Bank of New York.",
    ),
}

#: Benchmark a contract in this currency would normally reference.
DEFAULT_BENCHMARK_FOR_CURRENCY = {"GBP": "SONIA", "EUR": "ESTR", "USD": "SOFR"}


def benchmark(benchmark_id: str) -> Benchmark:
    """Look up a benchmark by id (``€STR``/``EUR STR`` accepted for ``ESTR``).

    Raises:
        InterestRateError: Unknown benchmark.
    """

    key = (benchmark_id or "").strip().upper().replace("€", "E").replace(" ", "")
    key = {"EURSTR": "ESTR", "€STR": "ESTR"}.get(key, key)
    try:
        return BENCHMARKS[key]
    except KeyError as exc:
        raise InterestRateError(f"unknown benchmark: {benchmark_id!r}") from exc


@dataclass(frozen=True)
class RateFixing:
    """One published daily fixing.

    Attributes:
        benchmark_id: Benchmark id.
        value_date: The business day the rate applies to.
        rate_pct: Annualised rate in percent on the benchmark's day count.
        source_system: Administrator id (``BOE``/``ECB``/``NYFED``).
        source_reference: Dataset / series reference.
    """

    benchmark_id: str
    value_date: date
    rate_pct: float
    source_system: str
    source_reference: str

    def as_record(self) -> dict[str, object]:
        """Keyword arguments for ``InterestRateObservationRecord``."""

        return {
            "observation_id": f"{self.benchmark_id.lower()}-{self.value_date.isoformat()}",
            "benchmark_id": self.benchmark_id,
            "currency": BENCHMARKS[self.benchmark_id].currency,
            "value_date": self.value_date,
            "rate_pct": self.rate_pct,
            "day_count": BENCHMARKS[self.benchmark_id].day_count,
            "source_system": self.source_system,
            "source_reference": self.source_reference,
        }


def _fixing(bench: Benchmark, value_date: date, raw: object, reference: str) -> RateFixing:
    try:
        rate = float(str(raw).strip())
    except ValueError as exc:
        raise InterestRateError(f"{bench.benchmark_id} {value_date}: rate is not a number") from exc
    if not MIN_RATE_PCT <= rate <= MAX_RATE_PCT:
        raise InterestRateError(f"{bench.benchmark_id} {value_date}: rate {rate} out of range")
    return RateFixing(bench.benchmark_id, value_date, rate, bench.administrator, reference)


def parse_boe_sonia_csv(text: str) -> list[RateFixing]:
    """Parse a Bank of England IADB CSV export of series ``IUDSOIA`` (SONIA).

    Expected header ``DATE,IUDSOIA`` with dates like ``30 Oct 2026``.

    Raises:
        InterestRateError: Missing columns, bad dates or rates.
    """

    bench = BENCHMARKS["SONIA"]
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    fields = {name.strip().upper(): name for name in reader.fieldnames or []}
    if "DATE" not in fields or "IUDSOIA" not in fields:
        raise InterestRateError("BoE export must have DATE and IUDSOIA columns")
    fixings = []
    for row in reader:
        raw_date = (row[fields["DATE"]] or "").strip()
        raw_rate = (row[fields["IUDSOIA"]] or "").strip()
        if not raw_date or not raw_rate:
            continue
        try:
            value_date = datetime.strptime(raw_date, "%d %b %Y").date()
        except ValueError as exc:
            raise InterestRateError(f"BoE date not in 'DD Mon YYYY' form: {raw_date!r}") from exc
        fixings.append(_fixing(bench, value_date, raw_rate, "boe-iadb:IUDSOIA"))
    return _require_rows(fixings, "SONIA")


def parse_ecb_estr_csv(text: str) -> list[RateFixing]:
    """Parse an ECB Data Portal CSV (``EST/B.EU000A2X2A25.WT``, ``format=csvdata``).

    Uses the ``TIME_PERIOD`` and ``OBS_VALUE`` columns.

    Raises:
        InterestRateError: Missing columns, bad dates or rates.
    """

    bench = BENCHMARKS["ESTR"]
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    fields = set(reader.fieldnames or [])
    if not {"TIME_PERIOD", "OBS_VALUE"} <= fields:
        raise InterestRateError("ECB export must have TIME_PERIOD and OBS_VALUE columns")
    fixings = []
    for row in reader:
        if not (row["OBS_VALUE"] or "").strip():
            continue
        try:
            value_date = date.fromisoformat(row["TIME_PERIOD"].strip())
        except ValueError as exc:
            raise InterestRateError(f"ECB TIME_PERIOD is not ISO: {row['TIME_PERIOD']!r}") from exc
        fixings.append(
            _fixing(bench, value_date, row["OBS_VALUE"], "ecb-data-portal:EST.B.EU000A2X2A25.WT")
        )
    return _require_rows(fixings, "ESTR")


def parse_nyfed_sofr_json(text: str) -> list[RateFixing]:
    """Parse the NY Fed Markets API JSON (``/api/rates/secured/sofr/...json``).

    Raises:
        InterestRateError: Malformed JSON, bad dates or rates.
    """

    bench = BENCHMARKS["SOFR"]
    try:
        payload = json.loads(text)
        rows = payload["refRates"]
    except (ValueError, KeyError, TypeError) as exc:
        raise InterestRateError("NY Fed payload must be JSON with a refRates list") from exc
    fixings = []
    for row in rows:
        if not isinstance(row, Mapping) or str(row.get("type", "SOFR")).upper() != "SOFR":
            continue
        try:
            value_date = date.fromisoformat(str(row["effectiveDate"]))
        except (KeyError, ValueError) as exc:
            raise InterestRateError("NY Fed effectiveDate missing or not ISO") from exc
        fixings.append(_fixing(bench, value_date, row.get("percentRate"), "nyfed-markets:sofr"))
    return _require_rows(fixings, "SOFR")


def _require_rows(fixings: list[RateFixing], name: str) -> list[RateFixing]:
    if not fixings:
        raise InterestRateError(f"{name} payload contained no fixings")
    dates = [fixing.value_date for fixing in fixings]
    if len(set(dates)) != len(dates):
        raise InterestRateError(f"{name} payload has duplicate value dates")
    return sorted(fixings, key=lambda fixing: fixing.value_date)


@dataclass(frozen=True)
class FinancingRate:
    """An all-in contract financing rate resolved from a benchmark fixing.

    ``all_in_pct`` is on the benchmark's own day count; ``all_in_act365_pct`` is the
    same money rate restated on ACT/365F for engines that accrue ``days / 365``.
    """

    benchmark_id: str
    currency: str
    day_count: str
    fixing_date: date
    as_of: date
    benchmark_rate_pct: float
    spread_bps: float
    all_in_pct: float
    all_in_act365_pct: float
    staleness_days: int
    source_system: str
    source_reference: str
    attribution: str

    def as_dict(self) -> dict[str, object]:
        """JSON-ready representation."""

        return {
            name: (value.isoformat() if isinstance(value, date) else value)
            for name, value in self.__dict__.items()
        }


def resolve_financing_rate(
    fixings: Iterable[Mapping[str, object] | RateFixing],
    benchmark_id: str,
    *,
    as_of: date,
    spread_bps: float = 0.0,
    max_staleness_days: int = 7,
) -> FinancingRate:
    """Benchmark fixing on or before ``as_of`` plus ``spread_bps``.

    Market practice for a contract rate "SONIA + x bp observed on date D" is the
    latest published fixing whose value date is on or before D. Weekends and
    holidays therefore carry the previous business day; a gap longer than
    ``max_staleness_days`` calendar days is refused instead of silently using an
    old rate.

    Raises:
        InterestRateError: Unknown benchmark, no fixing, stale fixing or bad spread.
    """

    bench = benchmark(benchmark_id)
    if not -1000 <= spread_bps <= 5000:
        raise InterestRateError("spread_bps must be between -1000 and 5000")
    best: RateFixing | None = None
    for item in fixings:
        fixing = item if isinstance(item, RateFixing) else _from_mapping(item)
        if fixing.benchmark_id != bench.benchmark_id or fixing.value_date > as_of:
            continue
        if best is None or fixing.value_date > best.value_date:
            best = fixing
    if best is None:
        raise InterestRateError(f"no {bench.benchmark_id} fixing on or before {as_of.isoformat()}")
    staleness = (as_of - best.value_date).days
    if staleness > max_staleness_days:
        raise InterestRateError(
            f"latest {bench.benchmark_id} fixing {best.value_date.isoformat()} is {staleness} "
            f"days before {as_of.isoformat()}; ingest newer fixings"
        )
    all_in = best.rate_pct + spread_bps / 100.0
    return FinancingRate(
        benchmark_id=bench.benchmark_id,
        currency=bench.currency,
        day_count=bench.day_count,
        fixing_date=best.value_date,
        as_of=as_of,
        benchmark_rate_pct=best.rate_pct,
        spread_bps=spread_bps,
        all_in_pct=round(all_in, 6),
        all_in_act365_pct=round(all_in * 365 / bench.day_count_days, 6),
        staleness_days=staleness,
        source_system=best.source_system,
        source_reference=best.source_reference,
        attribution=bench.attribution,
    )


def _from_mapping(row: Mapping[str, object]) -> RateFixing:
    value_date = row["value_date"]
    if isinstance(value_date, str):
        value_date = date.fromisoformat(value_date[:10])
    if isinstance(value_date, datetime):
        value_date = value_date.date()
    return RateFixing(
        benchmark_id=str(row["benchmark_id"]),
        value_date=value_date,  # type: ignore[arg-type]
        rate_pct=float(row["rate_pct"]),  # type: ignore[arg-type]
        source_system=str(row.get("source_system") or ""),
        source_reference=str(row.get("source_reference") or ""),
    )


def simple_interest(amount: float, rate_pct: float, days: int, day_count_days: int) -> float:
    """Simple interest on ``amount`` for ``days`` at ``rate_pct`` (ACT/``day_count_days``).

    This is the convention gas contracts use for early/late payment adjustments over a
    short lag; compounding in arrears is not applied over lags of a few weeks.
    """

    if day_count_days not in (360, 365):
        raise InterestRateError("day_count_days must be 360 or 365")
    return amount * rate_pct / 100.0 * days / day_count_days
