"""End-of-day gas option settlements from a licensed exchange or vendor export.

The desk does not trade options; option settlements are read for what they say about the
market (implied volatility, skew, where open interest sits). Exchange option settlements
are licensed market data (ICE Report Center end-of-day reports for ICE Endex, EEX Group
DataSource "End of Day Prices", CME DataMine); no free endpoint exists, and the public EEX
download this product already reads (the TTF NGP index file) carries no options. A market-data
team exports the settlements it is entitled to as CSV and imports them here; rows are stored
under that licence's source family, so entitlement filtering applies as for every other
licensed price. See ``docs/data/GAS_OPTION_SETTLEMENTS.md``.

Columns (case-insensitive; spaces, ``/`` and ``-`` read as underscores; extra columns
ignored)::

    trade_date, hub, contract, strike, option_type, settlement
    [, expiry, underlying, implied_vol, open_interest, volume, unit, currency, style]

- ``contract``: the underlying future's delivery period (``Jan-27``, ``Q1-27``, ``Sum-27``,
  ``Cal-27``); ``date``/``product``/``delivery_period`` are accepted as column names.
- ``option_type``: ``C``/``Call`` or ``P``/``Put`` (column ``call_put``/``cp``/``type``).
- ``settlement``, ``strike`` and ``underlying`` are in the hub's native unit (TTF and THE
  EUR/MWh, NBP GBp/th) unless a ``unit`` column says otherwise.
- ``expiry`` (``YYYY-MM-DD``) is required except for ICE Endex TTF monthly options, whose
  published expiry rule is applied when the column is absent (weekends only; the exchange's
  own column is preferred).
- ``underlying`` is the futures settlement of the same trade date. Without it the import
  takes the stored futures settlement it is given, else the futures price implied by
  put-call parity (median over strikes listed as both call and put).
- ``implied_vol`` is the exchange-published volatility **in percent**; it is kept beside
  the Black-76 volatility this import solves, and preferred when present.
- ``style``: ``futures_style`` (premium margined, not discounted) or ``premium`` (paid up
  front, discounted). Defaults exist only where the exchange documents the style: every EEX
  gas option and the ICE Endex TTF options are futures-style.

A malformed file is refused as a whole with the line and the reason; a row whose settlement
has no implied volatility (below intrinsic, no time value, no underlying) is stored with the
reason, never with an invented volatility.

本模块导入客户自有授权的天然气期权日终结算价（交易所或供应商导出的 CSV），按授权来源族
存储并受授权过滤；逐行求 Black-76 隐含波动率。不属于模拟数据。
"""

from __future__ import annotations

import csv
import hashlib
import io
import math
import re
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time
from typing import Any

from eurogas_nexus.domain.market.gas_day import EU_CAM_UTC_CALENDAR
from eurogas_nexus.domain.market.options import (
    CALL,
    FUTURES_STYLE,
    PREMIUM_STYLE,
    PUT,
    OptionMathError,
    discount_factor,
    forward_delta,
    ice_endex_ttf_monthly_expiry,
    implied_underlying_from_parity,
    implied_vol,
    option_source_tier,
    year_fraction,
)
from eurogas_nexus.domain.market.products import ProductCodeError, resolve_product
from eurogas_nexus.domain.market.units import (
    HUB_NATIVE_PRICE_UNIT,
    UnitConversionError,
    canonical_price_unit,
)
from eurogas_nexus.domain.ontology.boundary import check_boundary

#: Licensed families an option export may be stored under, with the venue label: the
#: exchanges' own settlements first, then vendors that redistribute them.
OPTION_SETTLEMENT_SOURCES = {
    "ICE_ENDEX": "ICE Endex",
    "EEX": "EEX",
    "CME": "CME",
    "Argus": "Argus",
    "Platts": "Platts",
}
#: The demo simulator's family (``ingestion/simulated_option_settlements.py``); never
#: accepted from a file.
SIMULATED_OPTION_SOURCES = {"ICE_ENDEX_Sim": "ICE Endex"}

MAX_ROWS = 100_000
#: Above this difference (volatility points) between the exchange's volatility and the one
#: solved from its settlement the row carries a warning: different underlying or tenor.
IV_MISMATCH_WARNING_VOL_PTS = 2.0

_COLUMN_ALIASES = {
    "date": "trade_date",
    "tradedate": "trade_date",
    "product": "contract",
    "delivery_period": "contract",
    "underlying_contract": "contract",
    "contract_month": "contract",
    "strike_price": "strike",
    "call_put": "option_type",
    "put_call": "option_type",
    "cp": "option_type",
    "type": "option_type",
    "settlement_price": "settlement",
    "premium": "settlement",
    "expiry_date": "expiry",
    "last_trading_date": "expiry",
    "underlying_settlement": "underlying",
    "futures_settlement": "underlying",
    "underlying_price": "underlying",
    "volatility": "implied_vol",
    "iv": "implied_vol",
    "implied_volatility": "implied_vol",
    "oi": "open_interest",
    "premium_style": "style",
}
_REQUIRED = ("trade_date", "hub", "contract", "strike", "option_type", "settlement")
_TYPES = {"C": CALL, "CALL": CALL, "P": PUT, "PUT": PUT}
_STYLES = {
    "FUTURES_STYLE": FUTURES_STYLE,
    "FUTURES-STYLE": FUTURES_STYLE,
    "FUTURE-STYLE": FUTURES_STYLE,
    "FUTURE_STYLED": FUTURES_STYLE,
    "FUTURES": FUTURES_STYLE,
    "MARGINED": FUTURES_STYLE,
    "PREMIUM": PREMIUM_STYLE,
    "EQUITY": PREMIUM_STYLE,
    "EQUITY-STYLE": PREMIUM_STYLE,
    "UPFRONT": PREMIUM_STYLE,
}
_OPTION_PRODUCT_KINDS = {"month", "quarter", "season", "gas_year", "calendar_year", "cal"}


def default_premium_style(source_system: str, hub: str) -> str | None:
    """The documented premium style of a source's gas options, if documented."""

    family = source_system.removesuffix("_Sim")
    if family == "EEX":
        return FUTURES_STYLE  # EEX settlement procedures: all gas options future-styled
    if family == "ICE_ENDEX" and hub == "TTF":
        return FUTURES_STYLE  # ICE Endex TTF options: futures-style margin
    return None


class OptionSettlementImportError(ValueError):
    """Malformed export; the whole file is refused."""


@dataclass(frozen=True)
class OptionSettlementImport:
    rows: list[dict[str, Any]]
    hubs: list[str]
    contracts: list[str]
    first_day: date
    last_day: date
    solved: int
    unsolved: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


#: ``(currency, trade_date) -> (rate ACT/365F percent, reference)`` or ``None``.
RateLookup = Callable[[str, date], tuple[float, str] | None]


def _fail(line: int, message: str) -> OptionSettlementImportError:
    return OptionSettlementImportError(f"line {line}: {message}")


def _date(text: str | None, line: int, name: str) -> date:
    value = (text or "").strip()[:10]
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise _fail(line, f"{name} {text!r} is not YYYY-MM-DD") from exc


def _number(text: str | None, line: int, name: str) -> float | None:
    value = (text or "").strip().replace(",", "")
    if not value:
        return None
    try:
        number = float(value)
    except ValueError as exc:
        raise _fail(line, f"{name} {text!r} is not a number") from exc
    if not math.isfinite(number) or abs(number) > 1e9:
        raise _fail(line, f"{name} is out of range")
    return number


def parse_option_settlements(
    text: str,
    *,
    source_system: str,
    source_reference: str,
    received_at_utc: datetime | None = None,
    underlying_prices: Mapping[tuple[str, str, date], float] | None = None,
    discount_rate: RateLookup | None = None,
    holidays: Iterable[date] = (),
) -> OptionSettlementImport:
    """Rows for ``option_settlements`` from one licensed export.

    Args:
        text: The CSV export.
        source_system: Licence family the file was obtained under (see
            :data:`OPTION_SETTLEMENT_SOURCES`).
        source_reference: Where the file came from (kept on every row).
        received_at_utc: Receipt instant; now when omitted.
        underlying_prices: Stored futures settlements ``(hub, contract, trade_date) ->
            price`` in the hub's native unit, used when the file has no underlying column
            and the options are quoted in that unit.
        discount_rate: Rate lookup for premium-paid options.
        holidays: Exchange holidays known to the caller (expiry rule only).

    Raises:
        OptionSettlementImportError: Unknown source, missing columns or any bad row.
    """

    if source_system not in OPTION_SETTLEMENT_SOURCES:
        raise OptionSettlementImportError(
            f"source {source_system!r} is not one of {sorted(OPTION_SETTLEMENT_SOURCES)}"
        )
    return _parse(
        text,
        source_system=source_system,
        venue=OPTION_SETTLEMENT_SOURCES[source_system],
        simulated=False,
        source_reference=source_reference,
        received_at_utc=received_at_utc or datetime.now(UTC),
        underlying_prices=underlying_prices or {},
        discount_rate=discount_rate,
        holidays=tuple(holidays),
    )


def _parse(
    text: str,
    *,
    source_system: str,
    venue: str,
    simulated: bool,
    source_reference: str,
    received_at_utc: datetime,
    underlying_prices: Mapping[tuple[str, str, date], float],
    discount_rate: RateLookup | None,
    holidays: tuple[date, ...],
) -> OptionSettlementImport:
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    headers: dict[str, str] = {}
    for name in reader.fieldnames or []:
        key = re.sub(r"[^a-z0-9]+", "_", (name or "").strip().lower()).strip("_")
        headers.setdefault(_COLUMN_ALIASES.get(key, key), name)
    for required in _REQUIRED:
        if required not in headers:
            raise OptionSettlementImportError(f"export is missing a {required!r} column")

    def cell(record: dict[str, str], name: str) -> str | None:
        key = headers.get(name)
        return record.get(key) if key else None

    parsed: list[dict[str, Any]] = []
    seen: dict[tuple, int] = {}
    for line, record in enumerate(reader, start=2):
        if line - 1 > MAX_ROWS:
            raise OptionSettlementImportError(f"export exceeds {MAX_ROWS} rows")
        if not any((value or "").strip() for value in record.values() if isinstance(value, str)):
            continue  # a blank line
        trade_day = _date(cell(record, "trade_date"), line, "trade_date")
        hub = (cell(record, "hub") or "").strip().upper()
        checked = check_boundary(market=hub, gas_hub_required=True)
        if not checked.ok or hub not in HUB_NATIVE_PRICE_UNIT:
            raise _fail(line, f"hub {hub!r} is not a gas hub in the reference model")
        raw_contract = (cell(record, "contract") or "").strip()
        try:
            period = resolve_product(raw_contract, trade_day)
        except ProductCodeError as exc:
            raise _fail(line, f"contract {raw_contract!r}: {exc}") from exc
        if period.kind not in _OPTION_PRODUCT_KINDS:
            raise _fail(
                line,
                f"contract {raw_contract!r} is a {period.kind.replace('_', ' ')} product; "
                "gas options are listed on month, quarter, season and calendar futures",
            )
        option_type = _TYPES.get((cell(record, "option_type") or "").strip().upper())
        if option_type is None:
            raise _fail(line, "option_type must be C, Call, P or Put")
        strike = _number(cell(record, "strike"), line, "strike")
        if strike is None or strike <= 0:
            raise _fail(line, "strike must be a positive number")
        settlement = _number(cell(record, "settlement"), line, "settlement")
        if settlement is None:
            raise _fail(line, "settlement is required")
        if settlement < 0:
            raise _fail(line, "settlement cannot be negative")
        unit_text = (cell(record, "unit") or "").strip()
        currency = (cell(record, "currency") or "").strip().upper()
        if unit_text and "/" not in unit_text:
            if not currency:
                raise _fail(line, f"unit {unit_text!r} needs a currency column")
            unit_text = f"{currency}/{unit_text}"
        try:
            unit = canonical_price_unit(unit_text or HUB_NATIVE_PRICE_UNIT[hub])
        except UnitConversionError as exc:
            raise _fail(line, str(exc)) from exc
        unit_check = check_boundary(market=hub, price_unit=unit)
        if not unit_check.ok:
            raise _fail(line, f"unit {unit} is not a price unit of {hub}")
        style_text = (cell(record, "style") or "").strip().upper().replace(" ", "_")
        if style_text:
            style = _STYLES.get(style_text)
            if style is None:
                raise _fail(line, "style must be futures_style or premium")
        else:
            style = default_premium_style(source_system, hub)
            if style is None:
                raise _fail(
                    line,
                    f"{source_system} {hub} options have no documented premium style; add a "
                    "style column (futures_style or premium)",
                )
        expiry_text = (cell(record, "expiry") or "").strip()
        if expiry_text:
            expiry = _date(expiry_text, line, "expiry")
            expiry_basis = "file"
        elif (
            source_system.removesuffix("_Sim") == "ICE_ENDEX"
            and hub == "TTF"
            and (period.kind == "month")
        ):
            expiry = ice_endex_ttf_monthly_expiry(period.first_gas_day, holidays=holidays)
            expiry_basis = "ice_endex_ttf_monthly_rule"
        else:
            raise _fail(line, "expiry is required for this source and contract")
        if expiry < trade_day:
            raise _fail(line, f"expiry {expiry.isoformat()} is before the trade date")
        if expiry > period.last_gas_day:
            raise _fail(line, f"expiry {expiry.isoformat()} is after the contract delivers")
        underlying = _number(cell(record, "underlying"), line, "underlying")
        if underlying is not None and underlying <= 0:
            raise _fail(line, "underlying must be positive")
        exchange_iv = _number(cell(record, "implied_vol"), line, "implied_vol")
        if exchange_iv is not None and not 0 < exchange_iv <= 1000:
            raise _fail(line, "implied_vol is in percent and must be above 0 and at most 1000")
        open_interest = _number(cell(record, "open_interest"), line, "open_interest")
        volume = _number(cell(record, "volume"), line, "volume")
        for name, value in (("open_interest", open_interest), ("volume", volume)):
            if value is not None and value < 0:
                raise _fail(line, f"{name} cannot be negative")
        key = (hub, period.label, trade_day, strike, option_type)
        if key in seen:
            raise _fail(
                line,
                f"duplicate {hub} {period.label} {option_type} {strike:g} on "
                f"{trade_day.isoformat()} (first on line {seen[key]})",
            )
        seen[key] = line
        parsed.append(
            {
                "line": line,
                "hub": hub,
                "period": period,
                "trade_date": trade_day,
                "expiry": expiry,
                "expiry_basis": expiry_basis,
                "style": style,
                "option_type": option_type,
                "strike": strike,
                "settlement": settlement,
                "unit": unit,
                "underlying": underlying,
                "exchange_iv": exchange_iv,
                "open_interest": open_interest,
                "volume": volume,
            }
        )
    if not parsed:
        raise OptionSettlementImportError("the export has no option rows")

    groups: dict[tuple[str, str, date], list[dict[str, Any]]] = defaultdict(list)
    for item in parsed:
        groups[(item["hub"], item["period"].label, item["trade_date"])].append(item)

    rows: list[dict[str, Any]] = []
    unsolved: dict[str, int] = defaultdict(int)
    warnings: list[str] = []
    solved = 0
    for (hub, label, trade_day), items in sorted(
        groups.items(), key=lambda kv: (kv[0][0], kv[0][2], kv[0][1])
    ):
        expiries = {item["expiry"] for item in items}
        if len(expiries) > 1:
            raise _fail(items[0]["line"], f"{hub} {label} on {trade_day} has more than one expiry")
        styles = {item["style"] for item in items}
        if len(styles) > 1:
            raise _fail(items[0]["line"], f"{hub} {label} on {trade_day} mixes premium styles")
        units = {item["unit"] for item in items}
        if len(units) > 1:
            raise _fail(items[0]["line"], f"{hub} {label} on {trade_day} mixes price units")
        expiry, style, unit = expiries.pop(), styles.pop(), units.pop()
        tenor = year_fraction(trade_day, expiry)
        rate_info: tuple[float, str] | None = None
        df: float | None = 1.0
        if style == PREMIUM_STYLE:
            rate_info = discount_rate(unit.split("/")[0], trade_day) if discount_rate else None
            df = (
                None if rate_info is None else discount_factor(style, rate_info[0], max(tenor, 0.0))
            )
        file_underlyings = {item["underlying"] for item in items if item["underlying"] is not None}
        if len(file_underlyings) > 1:
            raise _fail(
                items[0]["line"], f"{hub} {label} on {trade_day} has conflicting underlying prices"
            )
        forward: float | None
        if file_underlyings:
            forward, basis = file_underlyings.pop(), "file"
        elif (hub, label, trade_day) in underlying_prices and unit == HUB_NATIVE_PRICE_UNIT[hub]:
            forward, basis = float(underlying_prices[(hub, label, trade_day)]), "futures_settlement"
        else:
            forward, basis = None, None
            if df is not None:
                calls = {i["strike"]: i["settlement"] for i in items if i["option_type"] == CALL}
                puts = {i["strike"]: i["settlement"] for i in items if i["option_type"] == PUT}
                pairs = [(k, calls[k], puts[k]) for k in calls.keys() & puts.keys()]
                forward = implied_underlying_from_parity(pairs, df)
                basis = "put_call_parity" if forward is not None else None
        for item in sorted(items, key=lambda i: (i["strike"], i["option_type"])):
            reason: str | None = None
            solved_vol: float | None = None
            if tenor <= 0:
                reason = "expired"
            elif forward is None:
                reason = "no_discount_rate" if df is None else "no_underlying"
            elif df is None:
                reason = "no_discount_rate"
            else:
                try:
                    result = implied_vol(
                        item["option_type"], item["settlement"], forward, item["strike"], tenor, df
                    )
                except OptionMathError:  # pragma: no cover - inputs validated above
                    result = None
                solved_vol = result.vol if result else None
                reason = result.reason if result else "bad_input"
            exchange_vol = None if item["exchange_iv"] is None else item["exchange_iv"] / 100.0
            chosen = exchange_vol if exchange_vol is not None else solved_vol
            iv_basis = (
                "exchange" if exchange_vol is not None else ("black76" if solved_vol else None)
            )
            mismatch = None
            if exchange_vol is not None and solved_vol is not None:
                mismatch = round((solved_vol - exchange_vol) * 100.0, 4)
                if abs(mismatch) > IV_MISMATCH_WARNING_VOL_PTS:
                    warnings.append(
                        f"line {item['line']}: solved volatility differs from the exchange's by "
                        f"{mismatch:+.2f} vol points"
                    )
            if chosen is None:
                unsolved[reason or "unknown"] += 1
            else:
                solved += 1
                reason = None
            delta = (
                round(forward_delta(item["option_type"], forward, item["strike"], chosen, tenor), 6)
                if chosen is not None and forward is not None and tenor > 0
                else None
            )
            rows.append(
                _row(
                    item,
                    source_system=source_system,
                    venue=venue,
                    simulated=simulated,
                    source_reference=source_reference,
                    received_at_utc=received_at_utc,
                    expiry=expiry,
                    style=style,
                    unit=unit,
                    tenor=tenor,
                    df=df,
                    rate_info=rate_info,
                    forward=forward,
                    basis=basis,
                    chosen=chosen,
                    iv_basis=iv_basis,
                    reason=reason,
                    solved_vol=solved_vol,
                    exchange_vol=exchange_vol,
                    mismatch=mismatch,
                    delta=delta,
                )
            )
    days = [row["trade_date"] for row in rows]
    return OptionSettlementImport(
        rows=rows,
        hubs=sorted({row["hub"] for row in rows}),
        contracts=sorted({row["contract"] for row in rows}),
        first_day=min(days),
        last_day=max(days),
        solved=solved,
        unsolved=dict(sorted(unsolved.items())),
        warnings=warnings[:50],
    )


def _row(
    item: dict[str, Any],
    *,
    source_system: str,
    venue: str,
    simulated: bool,
    source_reference: str,
    received_at_utc: datetime,
    expiry: date,
    style: str,
    unit: str,
    tenor: float,
    df: float | None,
    rate_info: tuple[float, str] | None,
    forward: float | None,
    basis: str | None,
    chosen: float | None,
    iv_basis: str | None,
    reason: str | None,
    solved_vol: float | None,
    exchange_vol: float | None,
    mismatch: float | None,
    delta: float | None,
) -> dict[str, Any]:
    period = item["period"]
    identity = (
        f"{source_system}|{item['hub']}|{period.label}|{item['trade_date'].isoformat()}|"
        f"{item['strike']:.6f}|{item['option_type']}"
    )
    digest = hashlib.sha256(identity.encode()).hexdigest()[:40]
    return {
        "settlement_id": f"opt-{digest}",
        "source_system": source_system,
        "venue": venue,
        "hub": item["hub"],
        "contract": period.label,
        "product_kind": period.kind,
        "delivery_start_utc": period.delivery_start_utc,
        "delivery_end_utc": period.delivery_end_utc,
        "trade_date": item["trade_date"],
        "expiry_date": expiry,
        "premium_style": style,
        "option_type": item["option_type"],
        "strike": item["strike"],
        "settlement_price": item["settlement"],
        "unit": unit,
        "currency": unit.split("/")[0],
        "underlying_price": None if forward is None else round(forward, 6),
        "underlying_basis": basis,
        "implied_vol": None if chosen is None else round(chosen, 8),
        "iv_basis": iv_basis,
        "iv_reason": reason,
        "forward_delta": delta,
        "open_interest": item["open_interest"],
        "volume": item["volume"],
        "simulated": simulated,
        "freshness": "simulated_daily" if simulated else "end_of_day",
        # Settlements are end-of-day values: observed at 18:00 UTC on the trade date, the
        # convention of the futures settlement import.
        "observed_at_utc": datetime.combine(item["trade_date"], time(18), tzinfo=UTC),
        "ingested_at_utc": received_at_utc,
        "source_reference": source_reference[:128],
        "source_record_id": identity[:128],
        "metadata_json": {
            "source_family": source_system.removesuffix("_Sim"),
            "source_tier": option_source_tier(source_system),
            "simulated": simulated,
            "official_entitlement_required": True,
            "expiry_basis": item["expiry_basis"],
            "tenor_years": round(tenor, 8),
            "discount_factor": None if df is None else round(df, 10),
            "discount_rate": (
                None
                if rate_info is None
                else {"rate_act365_pct": rate_info[0], "reference": rate_info[1]}
            ),
            "solved_iv": None if solved_vol is None else round(solved_vol, 8),
            "exchange_iv": exchange_vol,
            "iv_mismatch_vol_pts": mismatch,
            "pricing_model": "black76",
            "calendar_version": EU_CAM_UTC_CALENDAR,
        },
    }
