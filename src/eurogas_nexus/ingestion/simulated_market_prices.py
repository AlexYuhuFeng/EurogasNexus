"""Simulated exchange and assessment market price sources.

The simulator writes source-shaped rows into the same runtime tables used by
licensed connectors. It is not a fallback business dataset; every row is marked
as simulated and keeps the vendor entitlement boundary visible.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from datetime import UTC, date, datetime, time, timedelta
from time import sleep
from typing import Any

from sqlalchemy.orm import Session

from eurogas_nexus.db.models import IngestionRunRecord, MarketObservationRecord

SIMULATOR_VERSION = "sim-market-v1"
SIMULATED_MARKET_PRICE_SOURCE_SYSTEMS = (
    "EEX_Sim",
    "ICE_OCM_Sim",
    "Trayport_Sim",
    "ICIS_Sim",
)
DEFAULT_SIMULATED_MARKET_PRICE_INTERVALS_SECONDS = {
    "ICE_OCM_Sim": 10,
    "Trayport_Sim": 10,
    "EEX_Sim": 10,
    "ICIS_Sim": 86_400,
}

HUB_PRICE_BASE_EUR_MWH = {
    "TTF": 31.4,
    "NBP": 33.2,
    "THE": 31.9,
    "PEG": 31.1,
    "ZTP": 31.6,
    "PSV": 32.4,
}

HUB_REGIONS = {
    "TTF": "Netherlands",
    "NBP": "Great Britain",
    "THE": "Germany",
    "PEG": "France",
    "ZTP": "Belgium",
    "PSV": "Italy",
}

TENOR_PRICE_OFFSETS = {
    "within-day": -0.25,
    "day-ahead": 0.0,
    "weekend": -0.1,
    "month-ahead": 0.45,
}


def generate_simulated_market_observations(
    *,
    observed_at_utc: datetime | None = None,
    source_systems: Iterable[str] | None = None,
) -> list[dict[str, Any]]:
    """Generate exchange, broker-screen, and assessment-shaped simulated rows."""

    observed_at = _as_utc(observed_at_utc or datetime.now(UTC))
    requested_sources = _normalise_source_systems(source_systems)
    rows: list[dict[str, Any]] = []
    for hub in HUB_PRICE_BASE_EUR_MWH:
        if "EEX_Sim" in requested_sources:
            rows.extend(
                [
                    _eex_row(hub, "day-ahead", observed_at),
                    _eex_row(hub, "weekend", observed_at),
                    _eex_row(hub, "month-ahead", observed_at),
                ]
            )
        if "ICIS_Sim" in requested_sources:
            rows.append(_icis_daily_row(hub, observed_at))
        if "Trayport_Sim" in requested_sources:
            rows.extend(
                [
                    _trayport_row(hub, "within-day", observed_at),
                    _trayport_row(hub, "day-ahead", observed_at),
                ]
            )
    if "ICE_OCM_Sim" in requested_sources:
        rows.extend(
            [
                _ice_ocm_row("NBP", "within-day", observed_at),
                _ice_ocm_row("NBP", "day-ahead", observed_at),
            ]
        )
    return sorted(rows, key=lambda row: row["observation_id"])


def generate_simulated_market_quotes(
    *,
    observed_at_utc: datetime | None = None,
    source_systems: Iterable[str] | None = None,
) -> list[dict[str, Any]]:
    """Generate provider-shaped L1 bid/ask ticks for the normalized quote table."""

    observed_at = _as_utc(observed_at_utc or datetime.now(UTC))
    requested_sources = _normalise_source_systems(source_systems)
    rows: list[dict[str, Any]] = []
    for hub in HUB_PRICE_BASE_EUR_MWH:
        if "EEX_Sim" in requested_sources:
            for tenor in ("day-ahead", "weekend", "month-ahead"):
                rows.append(_simulated_quote_row("EEX_Sim", "EEX", hub, tenor, observed_at))
        if "Trayport_Sim" in requested_sources:
            for tenor in ("within-day", "day-ahead"):
                rows.append(
                    _simulated_quote_row(
                        "Trayport_Sim", "Trayport", hub, tenor, observed_at
                    )
                )
    if "ICE_OCM_Sim" in requested_sources:
        for tenor in ("within-day", "day-ahead"):
            rows.append(
                _simulated_quote_row(
                    "ICE_OCM_Sim", "ICE OCM", "NBP", tenor, observed_at
                )
            )
    return sorted(rows, key=lambda row: row["quote_id"])


def upsert_simulated_market_observations(
    session: Session,
    *,
    observed_at_utc: datetime | None = None,
    source_systems: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Upsert simulated prices and source-run metadata into the runtime DB."""

    observed_at = _as_utc(observed_at_utc or datetime.now(UTC))
    rows = generate_simulated_market_observations(
        observed_at_utc=observed_at,
        source_systems=source_systems,
    )
    for row in rows:
        session.merge(MarketObservationRecord(**row))

    from eurogas_nexus.db.repositories.market_intelligence import (
        scan_and_persist_intraday_opportunities,
        upsert_market_quotes,
    )

    quote_rows = generate_simulated_market_quotes(
        observed_at_utc=observed_at,
        source_systems=source_systems,
    )
    upsert_market_quotes(session, quote_rows)

    counts = Counter(row["source_system"] for row in rows)
    bucket = _tick_bucket(observed_at)
    for source_system, row_count in sorted(counts.items()):
        session.merge(
            IngestionRunRecord(
                run_id=f"sim-{source_system.lower().replace('_', '-')}-{bucket}",
                source_name=source_system,
                status="succeeded",
                started_at_utc=observed_at,
                finished_at_utc=observed_at,
                notes=(
                    f"records={row_count}; source={source_system}; "
                    "simulated_market_prices; normalized=market_observations"
                ),
            )
        )
    session.flush()
    scan_summary = scan_and_persist_intraday_opportunities(
        session,
        detected_at_utc=observed_at,
    )
    return {
        "rows_upserted": len(rows),
        "quotes_upserted": len(quote_rows),
        "source_counts": dict(sorted(counts.items())),
        "opportunity_scan": scan_summary,
        "observed_at_utc": observed_at.isoformat(),
    }


def due_simulated_market_price_sources(
    last_emitted_at_utc: Mapping[str, datetime],
    *,
    observed_at_utc: datetime | None = None,
    intervals_seconds: Mapping[str, int | float] | None = None,
) -> tuple[str, ...]:
    """Return simulated source systems whose configured update cadence is due."""

    observed_at = _as_utc(observed_at_utc or datetime.now(UTC))
    intervals = _normalise_intervals_seconds(intervals_seconds)
    due_sources: list[str] = []
    for source_system in SIMULATED_MARKET_PRICE_SOURCE_SYSTEMS:
        last_emitted = last_emitted_at_utc.get(source_system)
        if last_emitted is None:
            due_sources.append(source_system)
            continue
        elapsed_seconds = (observed_at - _as_utc(last_emitted)).total_seconds()
        if elapsed_seconds >= intervals[source_system]:
            due_sources.append(source_system)
    return tuple(due_sources)


def run_simulated_market_price_loop(
    session_factory: Callable[[], Session],
    *,
    intervals_seconds: Mapping[str, int | float] | None = None,
    max_iterations: int | None = None,
    now_fn: Callable[[], datetime] | None = None,
    sleep_fn: Callable[[float], None] = sleep,
    emit: Callable[[str], None] = print,
) -> list[dict[str, Any]]:
    """Continuously inject simulated source ticks until stopped or iteration-capped."""

    intervals = _normalise_intervals_seconds(intervals_seconds)
    clock = now_fn or (lambda: datetime.now(UTC))
    summaries: list[dict[str, Any]] = []
    last_emitted_at: dict[str, datetime] = {}

    while max_iterations is None or len(summaries) < max_iterations:
        observed_at = _as_utc(clock())
        due_sources = due_simulated_market_price_sources(
            last_emitted_at,
            observed_at_utc=observed_at,
            intervals_seconds=intervals,
        )
        if due_sources:
            with session_factory() as session:
                summary = upsert_simulated_market_observations(
                    session,
                    observed_at_utc=observed_at,
                    source_systems=due_sources,
                )
                session.commit()
            for source_system in due_sources:
                last_emitted_at[source_system] = observed_at
            summaries.append(summary)
            emit(_format_loop_summary(summary))

            if max_iterations is not None and len(summaries) >= max_iterations:
                break

        sleep_seconds = _seconds_until_next_tick(
            last_emitted_at,
            observed_at_utc=observed_at,
            intervals_seconds=intervals,
        )
        if sleep_seconds > 0:
            sleep_fn(sleep_seconds)

    return summaries


def _eex_row(hub: str, tenor: str, observed_at: datetime) -> dict[str, Any]:
    period_start, period_end = _period_for_tenor(tenor, observed_at)
    price = _simulated_price(hub, tenor, observed_at, source_bias=0.08)
    return _market_row(
        source_system="EEX_Sim",
        market_venue="EEX",
        hub=hub,
        product=f"{hub} {tenor}",
        tenor=tenor,
        price=price,
        period_start=period_start,
        period_end=period_end,
        observed_at=observed_at,
        freshness="simulated_live",
        quality_score=0.62,
        price_timing="exchange_reference",
        assessment_format="EEX-style simulated spot/curve mark",
    )


def _ice_ocm_row(hub: str, tenor: str, observed_at: datetime) -> dict[str, Any]:
    period_start, period_end = _period_for_tenor(tenor, observed_at)
    price = _simulated_price(hub, tenor, observed_at, source_bias=0.18)
    return _market_row(
        source_system="ICE_OCM_Sim",
        market_venue="ICE OCM",
        hub=hub,
        product=f"{hub} {tenor}",
        tenor=tenor,
        price=price,
        period_start=period_start,
        period_end=period_end,
        observed_at=observed_at,
        freshness="simulated_live",
        quality_score=0.58,
        price_timing="instant" if tenor == "within-day" else "exchange_reference",
        assessment_format="ICE OCM-style simulated screen mark",
    )


def _trayport_row(hub: str, tenor: str, observed_at: datetime) -> dict[str, Any]:
    period_start, period_end = _period_for_tenor(tenor, observed_at)
    price = _simulated_price(hub, tenor, observed_at, source_bias=0.12)
    return _market_row(
        source_system="Trayport_Sim",
        market_venue="Trayport",
        hub=hub,
        product=f"{hub} {tenor}",
        tenor=tenor,
        price=price,
        period_start=period_start,
        period_end=period_end,
        observed_at=observed_at,
        freshness="simulated_live",
        quality_score=0.57,
        price_timing="broker_screen",
        assessment_format="Trayport-style simulated broker screen mark",
    )


def _icis_daily_row(hub: str, observed_at: datetime) -> dict[str, Any]:
    period_start, period_end = _period_for_tenor("day-ahead", observed_at)
    price = _simulated_price(hub, "day-ahead", observed_at, source_bias=-0.06)
    return _market_row(
        source_system="ICIS_Sim",
        market_venue="ICIS Heren",
        hub=hub,
        product=f"{hub} day-ahead assessment",
        tenor="day-ahead",
        price=price,
        period_start=period_start,
        period_end=period_end,
        observed_at=observed_at,
        freshness="simulated_daily",
        quality_score=0.6,
        price_timing="daily_assessment",
        assessment_format="ICIS Heren daily assessment",
    )


def _market_row(
    *,
    source_system: str,
    market_venue: str,
    hub: str,
    product: str,
    tenor: str,
    price: float,
    period_start: datetime,
    period_end: datetime,
    observed_at: datetime,
    freshness: str,
    quality_score: float,
    price_timing: str,
    assessment_format: str,
) -> dict[str, Any]:
    source_slug = source_system.replace("_", "-").upper()
    hub_slug = hub.lower()
    tenor_slug = tenor.replace("-", "")
    bucket = (
        _tick_bucket(observed_at)
        if source_system != "ICIS_Sim"
        else period_start.date().isoformat()
    )
    observation_id = (
        f"sim-{source_slug.lower()}-{hub_slug}-{tenor_slug}-{bucket}"
    ).replace("--", "-")
    return {
        "observation_id": observation_id[:64],
        "market_venue": market_venue,
        "product": product,
        "price": round(price, 3),
        "unit": "EUR/MWh",
        "currency": "EUR",
        "period_start_utc": period_start,
        "period_end_utc": period_end,
        "observed_at_utc": observed_at,
        "source_system": source_system,
        "source_reference": f"sim:{source_system}:{hub}:{tenor}:{bucket}",
        "source_record_id": f"{source_slug}-{hub}-{tenor.upper()}-{bucket}",
        "freshness": freshness,
        "quality_score": quality_score,
        "research_only": False,
        "metadata_json": {
            "hub": hub,
            "market_area": hub,
            "region": HUB_REGIONS[hub],
            "tenor": tenor,
            "price_timing": price_timing,
            "assessment_format": assessment_format,
            "source_family": source_system.removesuffix("_Sim"),
            "simulated": True,
            "simulator_version": SIMULATOR_VERSION,
            "tick_bucket": bucket,
            "update_interval_seconds": (
                DEFAULT_SIMULATED_MARKET_PRICE_INTERVALS_SECONDS[source_system]
            ),
            "official_entitlement_required": True,
            "data_contract_shape": "market_observations",
        },
    }


def _simulated_quote_row(
    source_system: str,
    venue: str,
    hub: str,
    tenor: str,
    observed_at: datetime,
) -> dict[str, Any]:
    source_bias = {
        "EEX_Sim": 0.08,
        "ICE_OCM_Sim": 0.18,
        "Trayport_Sim": 0.12,
    }[source_system]
    mid = _simulated_price(hub, tenor, observed_at, source_bias=source_bias)
    half_spread = {
        "EEX_Sim": 0.025,
        "ICE_OCM_Sim": 0.04,
        "Trayport_Sim": 0.035,
    }[source_system]
    period_start, period_end = _period_for_tenor(tenor, observed_at)
    quantity_wave = 400 * (
        1 + math.sin((observed_at.second / 60) * math.tau + len(hub))
    )
    bid_quantity = round(700 + quantity_wave + len(hub) * 45, 2)
    ask_quantity = round(760 + quantity_wave + len(tenor) * 28, 2)
    bucket = _tick_bucket(observed_at)
    source_slug = source_system.lower().replace("_", "-")
    instrument_id = f"{venue.upper().replace(' ', '-')}-{hub}-{tenor}"[:128]
    quote_id = f"sim-quote-{source_slug}-{hub.lower()}-{tenor}-{bucket}"[:128]
    source_reference = f"sim:{source_system}:{hub}:{tenor}:{bucket}"
    return {
        "quote_id": quote_id,
        "source_system": source_system,
        "source_record_id": f"{instrument_id}-{bucket}"[:128],
        "venue": venue,
        "instrument_id": instrument_id,
        "hub": hub,
        "product": tenor,
        "delivery_start_utc": period_start,
        "delivery_end_utc": period_end,
        "bid_price": round(mid - half_spread, 4),
        "ask_price": round(mid + half_spread, 4),
        "last_price": round(mid, 4),
        "bid_quantity_mwh": bid_quantity,
        "ask_quantity_mwh": ask_quantity,
        "currency": "EUR",
        "unit": "MWh",
        "observed_at_utc": observed_at,
        "received_at_utc": observed_at,
        "source_reference": source_reference,
        "freshness": "simulated_live",
        "quality_score": {
            "EEX_Sim": 0.62,
            "ICE_OCM_Sim": 0.58,
            "Trayport_Sim": 0.57,
        }[source_system],
        "simulated": True,
        "metadata_json": {
            "source_family": source_system.removesuffix("_Sim"),
            "simulator_version": SIMULATOR_VERSION,
            "tick_bucket": bucket,
            "update_interval_seconds": (
                DEFAULT_SIMULATED_MARKET_PRICE_INTERVALS_SECONDS[source_system]
            ),
            "official_entitlement_required": True,
            "data_contract_shape": "market_quotes",
            "price_level": "L1",
        },
    }


def _simulated_price(
    hub: str,
    tenor: str,
    observed_at: datetime,
    *,
    source_bias: float,
) -> float:
    base = HUB_PRICE_BASE_EUR_MWH[hub] + TENOR_PRICE_OFFSETS[tenor] + source_bias
    minutes = observed_at.hour * 60 + observed_at.minute
    hub_phase = (sum(ord(character) for character in hub) % 17) / 17 * math.tau
    intraday_wave = math.sin((minutes / 1440) * math.tau + hub_phase) * 0.34
    weekly_wave = math.sin((observed_at.toordinal() % 7) / 7 * math.tau) * 0.22
    month_curve = 0.18 if tenor == "month-ahead" else 0.0
    return max(base + intraday_wave + weekly_wave + month_curve, 0.01)


def _period_for_tenor(tenor: str, observed_at: datetime) -> tuple[datetime, datetime]:
    gas_day = _gas_day(observed_at)
    if tenor == "within-day":
        return observed_at, gas_day + timedelta(days=1)
    if tenor == "day-ahead":
        start = gas_day + timedelta(days=1)
        return start, start + timedelta(days=1)
    if tenor == "weekend":
        days_until_saturday = (5 - gas_day.weekday()) % 7
        start = gas_day + timedelta(days=days_until_saturday)
        return start, start + timedelta(days=2)
    if tenor == "month-ahead":
        first_next_month = _first_day_next_month(observed_at.date())
        start = datetime.combine(first_next_month, time(hour=5), UTC)
        first_following_month = _first_day_next_month(first_next_month)
        return start, datetime.combine(first_following_month, time(hour=5), UTC)
    raise ValueError(f"Unsupported simulated tenor: {tenor}")


def _gas_day(value: datetime) -> datetime:
    gas_day = datetime.combine(value.date(), time(hour=5), UTC)
    if value < gas_day:
        return gas_day - timedelta(days=1)
    return gas_day


def _first_day_next_month(value: date) -> date:
    if value.month == 12:
        return date(value.year + 1, 1, 1)
    return date(value.year, value.month + 1, 1)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _normalise_source_systems(source_systems: Iterable[str] | None) -> tuple[str, ...]:
    if source_systems is None:
        return SIMULATED_MARKET_PRICE_SOURCE_SYSTEMS
    requested = tuple(source_systems)
    unknown = sorted(set(requested) - set(SIMULATED_MARKET_PRICE_SOURCE_SYSTEMS))
    if unknown:
        raise ValueError(f"Unsupported simulated source system(s): {', '.join(unknown)}")
    return tuple(
        source_system
        for source_system in SIMULATED_MARKET_PRICE_SOURCE_SYSTEMS
        if source_system in requested
    )


def _normalise_intervals_seconds(
    intervals_seconds: Mapping[str, int | float] | None,
) -> dict[str, float]:
    intervals = {
        source_system: float(DEFAULT_SIMULATED_MARKET_PRICE_INTERVALS_SECONDS[source_system])
        for source_system in SIMULATED_MARKET_PRICE_SOURCE_SYSTEMS
    }
    if intervals_seconds is not None:
        unknown = sorted(set(intervals_seconds) - set(SIMULATED_MARKET_PRICE_SOURCE_SYSTEMS))
        if unknown:
            raise ValueError(f"Unsupported simulated interval source(s): {', '.join(unknown)}")
        for source_system, interval_seconds in intervals_seconds.items():
            interval = float(interval_seconds)
            if interval <= 0:
                raise ValueError(f"Interval for {source_system} must be positive.")
            intervals[source_system] = interval
    return intervals


def _seconds_until_next_tick(
    last_emitted_at_utc: Mapping[str, datetime],
    *,
    observed_at_utc: datetime,
    intervals_seconds: Mapping[str, int | float],
) -> float:
    observed_at = _as_utc(observed_at_utc)
    next_due_seconds: list[float] = []
    for source_system in SIMULATED_MARKET_PRICE_SOURCE_SYSTEMS:
        last_emitted = last_emitted_at_utc.get(source_system)
        if last_emitted is None:
            return 0.0
        elapsed_seconds = (observed_at - _as_utc(last_emitted)).total_seconds()
        next_due_seconds.append(float(intervals_seconds[source_system]) - elapsed_seconds)
    return max(min(next_due_seconds), 0.0)


def _format_loop_summary(summary: dict[str, Any]) -> str:
    sources = ", ".join(
        f"{source}={count}" for source, count in summary["source_counts"].items()
    )
    return (
        "Simulated market price tick: "
        f"{summary['rows_upserted']} rows at {summary['observed_at_utc']} ({sources})"
    )


def _tick_bucket(value: datetime) -> str:
    return value.strftime("%Y%m%dT%H%M%S")
