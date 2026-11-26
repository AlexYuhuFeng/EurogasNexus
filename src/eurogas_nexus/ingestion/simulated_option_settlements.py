"""Simulated TTF option settlements for the demo (source ``ICE_ENDEX_Sim``).

The demo has no licensed option file, so the option views would otherwise be empty. This
module writes ICE Endex-shaped end-of-day TTF option settlements for the next monthly
contracts through the same row builder the licensed import uses, so the views and the
dataset builder read them exactly as they would read a real file. Every row is marked
``simulated`` (column and metadata), carries the ``ICE_ENDEX_Sim`` source system, ranks
below any exchange or vendor settlement in source precedence and is entitled through the
ICE Endex family, like the other simulated price sources.

The numbers are synthetic: a futures level around the simulated TTF curve, an ATM
volatility with a winter premium and a declining term structure, and a smile with an
upside (call) skew, priced with Black-76 and rounded to the 0.005 EUR/MWh settlement
tick. They are not market data and must never be read as a market price.

本模块为演示环境生成模拟 TTF 期权结算价（ICE_ENDEX_Sim），所有行均标记为模拟数据。
"""

from __future__ import annotations

import csv
import io
import math
from datetime import UTC, date, datetime, timedelta
from typing import Any

from eurogas_nexus.domain.market.options import black76_price, ice_endex_ttf_monthly_expiry
from eurogas_nexus.domain.market.products import resolve_product
from eurogas_nexus.ingestion.option_settlements import (
    SIMULATED_OPTION_SOURCES,
    OptionSettlementImport,
    _parse,
)
from eurogas_nexus.ingestion.provenance_versions import SIMULATOR_VERSION

SIMULATED_OPTION_SOURCE = "ICE_ENDEX_Sim"
SIMULATED_HUB = "TTF"
TICK = 0.005
STRIKE_STEP = 0.5
STRIKES_EACH_SIDE = 12
CONTRACTS = 4
_BASE_PRICE = 31.4


def _business_days(first: date, last: date) -> list[date]:
    days, day = [], first
    while day <= last:
        if day.weekday() < 5:
            days.append(day)
        day += timedelta(days=1)
    return days


def _months_ahead(trade_day: date, count: int) -> list[str]:
    labels: list[str] = []
    offset = 1
    while len(labels) < count:
        period = resolve_product(f"M+{offset}", trade_day)
        if ice_endex_ttf_monthly_expiry(period.first_gas_day) > trade_day:
            labels.append(period.label)
        offset += 1
    return labels


def _futures(trade_day: date, delivery: date) -> float:
    winter = 1.6 if delivery.month in (11, 12, 1, 2, 3) else -0.8
    drift = 2.2 * math.sin(trade_day.toordinal() / 37.0) + 0.9 * math.sin(
        trade_day.toordinal() / 9.0
    )
    return round(_BASE_PRICE + winter + drift, 3)


def _vol(trade_day: date, delivery: date, rank: int, moneyness: float) -> float:
    regime = 0.06 * math.sin(trade_day.toordinal() / 23.0) + 0.02 * math.sin(
        trade_day.toordinal() / 5.0
    )
    winter = 0.05 if delivery.month in (12, 1, 2) else 0.0
    atm = 0.44 + regime + winter - 0.025 * rank
    skew = 0.12 + 0.04 * math.sin(trade_day.toordinal() / 31.0)
    return max(atm + skew * moneyness + 0.45 * moneyness * moneyness, 0.08)


def simulated_option_csv(first: date, last: date) -> str:
    """The simulated settlements between two trade dates as an ICE Endex-shaped CSV."""

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "trade_date",
            "hub",
            "contract",
            "expiry",
            "strike",
            "option_type",
            "settlement",
            "underlying",
            "open_interest",
            "volume",
        ]
    )
    for trade_day in _business_days(first, last):
        for rank, label in enumerate(_months_ahead(trade_day, CONTRACTS)):
            period = resolve_product(label, trade_day)
            expiry = ice_endex_ttf_monthly_expiry(period.first_gas_day)
            tenor = (expiry - trade_day).days / 365.0
            forward = _futures(trade_day, period.first_gas_day)
            centre = round(forward / STRIKE_STEP) * STRIKE_STEP
            for step in range(-STRIKES_EACH_SIDE, STRIKES_EACH_SIDE + 1):
                strike = round(centre + step * STRIKE_STEP, 3)
                if strike <= 0:
                    continue
                vol = _vol(trade_day, period.first_gas_day, rank, math.log(strike / forward))
                for option_type in ("C", "P"):
                    price = black76_price(option_type, forward, strike, vol, tenor)
                    settled = round(round(price / TICK) * TICK, 3)
                    distance = abs(step) + (0 if (option_type == "C") == (step >= 0) else 4)
                    interest = max(0, int(900 * math.exp(-distance / 4.0) / (1 + rank)))
                    if option_type == "P":
                        interest = int(interest * 0.8)
                    writer.writerow(
                        [
                            trade_day.isoformat(),
                            SIMULATED_HUB,
                            label,
                            expiry.isoformat(),
                            f"{strike:.3f}",
                            option_type,
                            f"{settled:.3f}",
                            f"{forward:.3f}",
                            interest,
                            interest // 6,
                        ]
                    )
    return buffer.getvalue()


def generate_simulated_option_settlements(
    first: date, last: date, *, received_at_utc: datetime | None = None
) -> OptionSettlementImport:
    """Simulated rows for ``option_settlements`` (``simulated`` true on every row)."""

    received = received_at_utc or datetime.now(UTC)
    result = _parse(
        simulated_option_csv(first, last),
        source_system=SIMULATED_OPTION_SOURCE,
        venue=SIMULATED_OPTION_SOURCES[SIMULATED_OPTION_SOURCE],
        simulated=True,
        source_reference=f"sim:{SIMULATED_OPTION_SOURCE}:{first.isoformat()}..{last.isoformat()}",
        received_at_utc=received,
        underlying_prices={},
        discount_rate=None,
        holidays=(),
    )
    for row in result.rows:
        metadata: dict[str, Any] = row["metadata_json"]
        metadata["simulator_version"] = SIMULATOR_VERSION
        metadata["data_contract_shape"] = "option_settlements"
    return result
