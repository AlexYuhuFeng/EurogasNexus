"""FX benchmark fixings used to price gas and LNG.

Pipeline gas desks commonly convert with the ECB euro reference rate. LNG SPAs and
cargo confirmations usually name a specific market fix instead, most often the
WM/Reuters (WMR, now LSEG) 4pm London closing spot rate or the Bloomberg BFIX, and
frequently the arithmetic average of the daily fixes over a pricing period. Using
the wrong fix leaves a visible mismatch against the counterparty invoice, so the fix
is an explicit, named choice.

WMR and BFIX are licensed data: rows enter only through an operator import of the
subscriber's own export (see ``scripts/ops/import_fx_fixings.py``) and are served
only to principals holding the ``WMR``/``BFIX`` data-scope grant. Nothing here
fetches, scrapes or invents a rate.

本模块定义 FX 基准定盘（ECB 参考价、WM/Reuters 伦敦 4pm 收盘、Bloomberg BFIX）。
LNG 合同通常指定 WMR/BFIX 并按定价期日均；WMR/BFIX 为授权数据，仅能经运营方
导入且仅对拥有对应数据范围授权的用户可见。
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo


class FxFixingError(ValueError):
    """Unknown fixing, malformed import row or unusable rate set."""


@dataclass(frozen=True)
class FxFixing:
    """One named FX benchmark fix.

    Attributes:
        fixing_id: Stable ``rate_type`` stored on imported rows.
        source_system: Entitlement family of the rows (``ECB``, ``WMR``, ``BFIX``).
        label: Desk label shown next to a converted price.
        local_time: Wall-clock time of the fix.
        timezone_name: IANA zone of ``local_time``.
        licensed: True when rows require a commercial data-scope grant.
    """

    fixing_id: str
    source_system: str
    label: str
    local_time: time
    timezone_name: str
    licensed: bool

    def fixing_instant_utc(self, value_date: date) -> datetime:
        """UTC instant of this fix on ``value_date`` (DST-aware)."""

        local = datetime.combine(value_date, self.local_time, tzinfo=ZoneInfo(self.timezone_name))
        return local.astimezone(UTC)


FX_FIXINGS: dict[str, FxFixing] = {
    fixing.fixing_id: fixing
    for fixing in (
        FxFixing("reference", "ECB", "ECB euro reference rate", time(14, 10),
                 "Europe/Berlin", licensed=False),
        FxFixing("WMR_1600_LDN", "WMR", "WM/Reuters 4pm London closing spot", time(16, 0),
                 "Europe/London", licensed=True),
        FxFixing("WMR_1100_LDN", "WMR", "WM/Reuters 11am London intraday spot", time(11, 0),
                 "Europe/London", licensed=True),
        FxFixing("BFIX_1600_LDN", "BFIX", "Bloomberg BFIX 4pm London", time(16, 0),
                 "Europe/London", licensed=True),
        FxFixing("BFIX_1400_CET", "BFIX", "Bloomberg BFIX 2pm CET", time(14, 0),
                 "Europe/Berlin", licensed=True),
    )
}

#: Default fix per source when the caller names only the source.
DEFAULT_FIXING_FOR_SOURCE = {
    "ECB": "reference",
    "WMR": "WMR_1600_LDN",
    "BFIX": "BFIX_1600_LDN",
}


def resolve_fixing(source: str | None, fixing_id: str | None = None) -> FxFixing:
    """Resolve a fix from an explicit id or a source's default.

    Raises:
        FxFixingError: Unknown source or fixing, or a fixing of another source.
    """

    source_key = (source or "ECB").strip().upper()
    if fixing_id:
        fixing = FX_FIXINGS.get(fixing_id.strip())
        if fixing is None:
            raise FxFixingError(f"unknown FX fixing: {fixing_id!r}")
        if source and fixing.source_system != source_key:
            raise FxFixingError(f"{fixing_id} is not a {source_key} fixing")
        return fixing
    default = DEFAULT_FIXING_FOR_SOURCE.get(source_key)
    if default is None:
        raise FxFixingError(f"unknown FX source: {source!r}")
    return FX_FIXINGS[default]


def eur_rates_from_pairs(pairs: Mapping[str, float]) -> dict[str, float]:
    """Derive units-per-EUR rates from direct and USD-quoted pairs.

    WMR and BFIX publish majors against USD (``EURUSD``, ``GBPUSD``); the
    conversion engine wants units per 1 EUR. Direct ``EURxxx`` pairs win; otherwise
    ``xxx`` is crossed through USD (``EURUSD / xxxUSD`` or ``EURUSD * USDxxx``).

    Args:
        pairs: Six-letter pair -> rate (base priced in quote).

    Returns:
        Currency -> units per 1 EUR, for every currency derivable.
    """

    clean = {key.upper().replace("/", ""): float(val) for key, val in pairs.items() if val > 0}
    rates: dict[str, float] = {}
    for pair, rate in clean.items():
        if pair.startswith("EUR") and len(pair) == 6:
            rates[pair[3:]] = rate
        elif pair.endswith("EUR") and len(pair) == 6:
            rates.setdefault(pair[:3], 1.0 / rate)
    eur_usd = rates.get("USD")
    if eur_usd:
        for pair, rate in clean.items():
            if len(pair) != 6:
                continue
            if pair.endswith("USD") and pair[:3] not in rates and pair[:3] != "EUR":
                rates[pair[:3]] = eur_usd / rate
            elif pair.startswith("USD") and pair[3:] not in rates and pair[3:] != "EUR":
                rates[pair[3:]] = eur_usd * rate
    return rates


@dataclass(frozen=True)
class FxFixingRow:
    """One imported fix, shaped for ``fx_observations``."""

    observation_id: str
    pair: str
    base_currency: str
    quote_currency: str
    rate: float
    rate_type: str
    value_date: str
    observed_at_utc: datetime
    source_system: str
    source_reference: str

    def as_record(self) -> dict[str, object]:
        """Keyword arguments for ``FxObservationRecord``."""

        return {
            "observation_id": self.observation_id,
            "pair": self.pair,
            "base_currency": self.base_currency,
            "quote_currency": self.quote_currency,
            "rate": self.rate,
            "rate_type": self.rate_type,
            "value_date": self.value_date,
            "observed_at_utc": self.observed_at_utc,
            "source_system": self.source_system,
            "source_reference": self.source_reference,
            "source_record_id": f"{self.rate_type}:{self.pair}:{self.value_date}",
            "freshness": "imported",
            "research_only": True,
            "metadata_json": {"import": "operator_fx_fixing_export"},
        }


def parse_fixing_export(
    text: str,
    fixing: FxFixing,
    *,
    source_reference: str,
) -> list[FxFixingRow]:
    """Parse a subscriber's fixing export (CSV with ``date,pair,rate`` columns).

    Header names are case-insensitive; ``value_date``/``ric``/``ticker``/``mid`` are
    accepted aliases. Pairs are six letters (``EURUSD``, ``GBP/USD``); a RIC such as
    ``EURUSDFIXM=WM`` or a ticker such as ``EURUSD F160 Curncy`` is reduced to its
    leading pair.

    Raises:
        FxFixingError: Missing columns, bad dates/rates or duplicate pair/date rows.
    """

    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    headers = {name.strip().lower(): name for name in reader.fieldnames or []}

    def column(*names: str) -> str:
        for name in names:
            if name in headers:
                return headers[name]
        raise FxFixingError(f"export is missing a {names[0]!r} column")

    date_col = column("date", "value_date")
    pair_col = column("pair", "ric", "ticker")
    rate_col = column("rate", "mid", "fix")
    rows: list[FxFixingRow] = []
    seen: set[tuple[str, str]] = set()
    for line, record in enumerate(reader, start=2):
        try:
            value_date = date.fromisoformat((record[date_col] or "").strip())
        except ValueError as exc:
            raise FxFixingError(f"line {line}: date must be ISO YYYY-MM-DD") from exc
        raw_pair = (record[pair_col] or "").strip().upper().replace("/", "")
        pair = raw_pair[:6]
        if len(pair) != 6 or not pair.isalpha():
            raise FxFixingError(f"line {line}: cannot read a currency pair from {raw_pair!r}")
        try:
            rate = float((record[rate_col] or "").strip())
        except ValueError as exc:
            raise FxFixingError(f"line {line}: rate is not a number") from exc
        if not rate > 0 or rate != rate:
            raise FxFixingError(f"line {line}: rate must be positive")
        key = (pair, value_date.isoformat())
        if key in seen:
            raise FxFixingError(f"line {line}: duplicate {pair} on {value_date.isoformat()}")
        seen.add(key)
        rows.append(
            FxFixingRow(
                observation_id=f"{fixing.source_system.lower()}-{fixing.fixing_id}-{pair}-"
                f"{value_date.isoformat()}"[:64],
                pair=pair,
                base_currency=pair[:3],
                quote_currency=pair[3:],
                rate=rate,
                rate_type=fixing.fixing_id,
                value_date=value_date.isoformat(),
                observed_at_utc=fixing.fixing_instant_utc(value_date),
                source_system=fixing.source_system,
                source_reference=source_reference,
            )
        )
    if not rows:
        raise FxFixingError("export contains no fixing rows")
    return rows


def select_fixing_rates(
    rows: Iterable[Mapping[str, object]],
    fixing: FxFixing,
    *,
    on: date | None = None,
    average_from: date | None = None,
    average_to: date | None = None,
) -> dict[str, object]:
    """Pick EUR-based rates for one fix: latest, a given date, or a period average.

    Averaging follows LNG practice: per pair, the arithmetic mean of the daily
    fixes published inside ``[average_from, average_to]``; EUR-based rates are then
    derived from the averaged pairs.

    Returns:
        ``{"eur_rates": {...}, "value_dates": [...], "fixings_used": n}``; empty
        ``eur_rates`` when nothing matches.

    Raises:
        FxFixingError: An incomplete or inverted averaging window.
    """

    if (average_from is None) != (average_to is None):
        raise FxFixingError("average_from and average_to must be given together")
    if average_from and average_to and average_from > average_to:
        raise FxFixingError("average_from must not be after average_to")
    by_date: dict[str, dict[str, float]] = {}
    for row in rows:
        if row.get("source_system") != fixing.source_system:
            continue
        if fixing.source_system != "ECB" and row.get("rate_type") != fixing.fixing_id:
            continue
        value_date = str(row.get("value_date") or "")[:10]
        rate = row.get("rate")
        if not value_date or not isinstance(rate, (int, float)) or not rate > 0:
            continue
        pair = str(row.get("pair") or "").upper().replace("/", "")
        if len(pair) != 6:
            pair = f"{row.get('base_currency') or ''}{row.get('quote_currency') or ''}".upper()
        by_date.setdefault(value_date, {}).setdefault(pair, float(rate))
    if average_from and average_to:
        window = [
            day for day in sorted(by_date)
            if average_from.isoformat() <= day <= average_to.isoformat()
        ]
        sums: dict[str, list[float]] = {}
        for day in window:
            for pair, rate in by_date[day].items():
                sums.setdefault(pair, []).append(rate)
        pairs = {pair: sum(values) / len(values) for pair, values in sums.items()}
        return {
            "eur_rates": eur_rates_from_pairs(pairs),
            "value_dates": window,
            "fixings_used": len(window),
        }
    if on is not None:
        chosen = on.isoformat() if on.isoformat() in by_date else None
    else:
        chosen = max(by_date) if by_date else None
    if chosen is None:
        return {"eur_rates": {}, "value_dates": [], "fixings_used": 0}
    return {
        "eur_rates": eur_rates_from_pairs(by_date[chosen]),
        "value_dates": [chosen],
        "fixings_used": 1,
    }
