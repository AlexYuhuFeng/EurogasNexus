"""Market fundamentals composed across commodities: gas-for-power with carbon and coal.

跨商品基本面：结合碳价与煤价的燃气发电（清洁点火/暗价差、燃料转换价、隐含用气量）。
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from eurogas_nexus.api.csv_export import report_response
from eurogas_nexus.api.dependencies.row_entitlement import current_principal
from eurogas_nexus.application.projections.market_reads import filter_entitled_rows
from eurogas_nexus.domain.ontology.markets import Commodity, find_market, markets
from eurogas_nexus.domain.power.gas_for_power import (
    API2_MWH_TH_PER_TONNE,
    SystemHour,
    clean_dark_spread,
    clean_spark_spread,
    fuel_switch_gas_price,
    implied_gas_burn_mwh_th,
    residual_load_mw,
)

router = APIRouter(tags=["market"])

#: GB generators pay the Carbon Price Support on top of the UK ETS price (GBP/t).
GB_CARBON_PRICE_SUPPORT_GBP_T = 18.0
_POWER_METRICS = (
    "day_ahead_price",
    "load_actual",
    "load_forecast_da",
    "wind_onshore_generation",
    "wind_offshore_generation",
    "solar_generation",
    "gas_generation",
)


def _env(data: Any, source: str, warnings: list[str]) -> dict:
    return {
        "data": data,
        "meta": {
            "research_only": True,
            "human_review_required": True,
            "source_references": [source],
            "warnings": list(dict.fromkeys(warnings)),
        },
    }


def _session_or_none():
    from eurogas_nexus.db.session import get_session_factory, resolve_database_url

    return get_session_factory()() if resolve_database_url() else None


def _aware(moment: datetime) -> datetime:
    return moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment.astimezone(UTC)


def _bound(session, day: date) -> datetime:
    moment = datetime.combine(day, time.min, tzinfo=UTC)
    return moment.replace(tzinfo=None) if session.get_bind().dialect.name == "sqlite" else moment


def daily_settlements(
    session, request: Request, codes: set[str], first: date, last: date
) -> dict[str, dict[date, float]]:
    """Front-contract daily price per market code, from entitled non-simulated settlements.

    For each market and trade date the contract with the earliest delivery start on or
    after the trade date is used (the front December for EUA, the front month for API2).
    """

    from sqlalchemy import or_

    from eurogas_nexus.db.models import MarketObservationRecord

    if not codes:
        return {}
    rows = (
        session.query(
            MarketObservationRecord.product,
            MarketObservationRecord.price,
            MarketObservationRecord.period_start_utc,
            MarketObservationRecord.observed_at_utc,
            MarketObservationRecord.source_system,
            MarketObservationRecord.metadata_json,
        )
        .filter(or_(*(MarketObservationRecord.product.like(f"{code} %") for code in codes)))
        .filter(MarketObservationRecord.observed_at_utc >= _bound(session, first))
        .filter(MarketObservationRecord.observed_at_utc < _bound(session, last + timedelta(days=1)))
        .limit(50_000)
        .all()
    )
    candidates = [
        {
            "code": row.product.split(" ", 1)[0],
            "price": float(row.price),
            "start": _aware(row.period_start_utc),
            "day": _aware(row.observed_at_utc).date(),
            "source_system": row.source_system,
        }
        for row in rows
        if not (row.metadata_json or {}).get("simulated") and not row.source_system.endswith("_Sim")
    ]
    chosen: dict[tuple[str, date], dict] = {}
    for row in filter_entitled_rows(current_principal(request), candidates):
        key = (row["code"], row["day"])
        trade_start = datetime.combine(row["day"], time.min, tzinfo=UTC)
        if row["start"] < trade_start:
            continue
        held = chosen.get(key)
        if held is None or row["start"] < held["start"]:
            chosen[key] = row
    out: dict[str, dict[date, float]] = defaultdict(dict)
    for (code, day), row in chosen.items():
        out[code][day] = row["price"]
    return out


def _latest_on_or_before(series: dict[date, float], day: date, max_age_days: int = 5):
    for back in range(max_age_days + 1):
        value = series.get(day - timedelta(days=back))
        if value is not None:
            return value
    return None


def _eur_per_usd(session, last: date) -> float | None:
    from eurogas_nexus.db.models import FxObservationRecord

    row = (
        session.query(FxObservationRecord.rate)
        .filter(FxObservationRecord.base_currency == "EUR")
        .filter(FxObservationRecord.quote_currency == "USD")
        .filter(FxObservationRecord.value_date <= last.isoformat())
        .order_by(FxObservationRecord.value_date.desc())
        .first()
    )
    return 1 / float(row.rate) if row and row.rate else None


def _gas_closes(request: Request, hub: str, first: date, last: date) -> dict[date, float]:
    from eurogas_nexus.api.routes.public.spread_lab import _daily_rows

    closes: dict[date, float] = {}
    for row in _daily_rows(request, first - timedelta(days=5), last):
        if row["simulated"] or row["hub"] != hub:
            continue
        if row["tenor"] == "day-ahead" or row["day"] not in closes:
            closes[row["day"]] = row["price"]
    return closes


@router.get("/api/market/gas-for-power")
def get_gas_for_power(
    request: Request,
    zone: str = Query("DE_LU", max_length=16),
    days: int = Query(14, ge=1, le=92),
    gas_efficiency: float = Query(0.50, ge=0.2, le=0.7),
    coal_efficiency: float = Query(0.38, ge=0.2, le=0.7),
    format: str = Query("json", pattern="^(json|csv|xlsx|pdf)$"),
):
    """Daily gas-for-power view for one bidding zone.

    每日燃气发电视图：电价、剩余负荷、隐含燃气消耗，及清洁点火/暗价差与燃料转换价。

    Power (ENTSO-E) is averaged per delivery day; gas is the zone's reference hub close,
    carbon the front EUA (UKA plus Carbon Price Support for GB) and coal front API2
    converted at 6,000 kcal/kg and the ECB EUR/USD rate. A spread is null when an input is
    missing; it is never filled with a simulated or assumed price.
    """

    power_market = find_market(zone)
    if power_market is None or power_market.commodity is not Commodity.POWER:
        zones = sorted(m.code for m in markets(commodity=Commodity.POWER))
        raise HTTPException(status_code=422, detail={"code": "unknown_zone", "zones": zones})
    session = _session_or_none()
    if session is None:
        return _env([], "runtime-db-not-configured", ["RUNTIME_DB_NOT_CONFIGURED"])
    last = datetime.now(UTC).date()
    first = last - timedelta(days=days - 1)
    warnings: list[str] = []
    from sqlalchemy.exc import SQLAlchemyError

    from eurogas_nexus.db.models.power import PowerObservationRecord

    try:
        with session:
            power_rows = (
                session.query(PowerObservationRecord)
                .filter(PowerObservationRecord.zone == power_market.code)
                .filter(PowerObservationRecord.metric.in_(_POWER_METRICS))
                .filter(PowerObservationRecord.period_start_utc >= _bound(session, first))
                .filter(
                    PowerObservationRecord.period_start_utc
                    < _bound(session, last + timedelta(days=1))
                )
                .all()
            )
            codes = {c for c in (power_market.carbon_market, "API2") if c}
            settlements = daily_settlements(
                session, request, codes, first - timedelta(days=7), last
            )
            eur_per_usd = _eur_per_usd(session, last)
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "runtime_db_unavailable", "error_class": exc.__class__.__name__},
        ) from exc
    power_rows = filter_entitled_rows(
        current_principal(request),
        [
            {
                "source_system": r.source_system,
                "metric": r.metric,
                "start": _aware(r.period_start_utc),
                "end": _aware(r.period_end_utc),
                "value": r.value,
            }
            for r in power_rows
        ],
    )
    gas = _gas_closes(request, power_market.gas_hub, first, last) if power_market.gas_hub else {}

    # period -> metric -> value; prefer actual load, fall back to the day-ahead forecast.
    periods: dict[datetime, dict[str, Any]] = defaultdict(dict)
    for r in power_rows:
        periods[r["start"]][r["metric"]] = r["value"]
        periods[r["start"]]["_hours"] = (r["end"] - r["start"]).total_seconds() / 3600
    by_day: dict[date, list[dict[str, Any]]] = defaultdict(list)
    for start, values in periods.items():
        by_day[start.date()].append(values)

    is_gb = power_market.code == "GB"
    carbon_code = power_market.carbon_market
    rows = []
    for day in sorted(by_day):
        values = by_day[day]
        prices = [v["day_ahead_price"] for v in values if "day_ahead_price" in v]
        burn = 0.0
        burn_basis: set[str] = set()
        residuals = []
        for v in values:
            load = v.get("load_actual", v.get("load_forecast_da"))
            if load is None:
                continue
            hour = SystemHour(
                load_mw=load,
                wind_mw=v.get("wind_onshore_generation", 0.0)
                + v.get("wind_offshore_generation", 0.0),
                solar_mw=v.get("solar_generation", 0.0),
                gas_generation_mw=v.get("gas_generation"),
            )
            residuals.append(residual_load_mw(hour))
            mwh, basis = implied_gas_burn_mwh_th(
                hour, hours=v.get("_hours", 1.0), efficiency=gas_efficiency
            )
            burn += mwh
            burn_basis.add(basis)
        power = sum(prices) / len(prices) if prices else None
        gas_price = _latest_on_or_before(gas, day)
        carbon = (
            _latest_on_or_before(settlements.get(carbon_code, {}), day) if carbon_code else None
        )
        if carbon is not None and is_gb:
            carbon += GB_CARBON_PRICE_SUPPORT_GBP_T
        coal_usd_t = _latest_on_or_before(settlements.get("API2", {}), day)
        coal = (
            coal_usd_t * eur_per_usd / API2_MWH_TH_PER_TONNE
            if coal_usd_t is not None and eur_per_usd and power_market.currency == "EUR"
            else None
        )
        css = (
            clean_spark_spread(power, gas_price, carbon, efficiency=gas_efficiency)
            if None not in (power, gas_price, carbon)
            else None
        )
        cds = (
            clean_dark_spread(power, coal, carbon, efficiency=coal_efficiency)
            if None not in (power, coal, carbon)
            else None
        )
        switch = (
            fuel_switch_gas_price(
                coal, carbon, gas_efficiency=gas_efficiency, coal_efficiency=coal_efficiency
            )
            if None not in (coal, carbon)
            else None
        )
        rows.append(
            {
                "day": day.isoformat(),
                "power_price": None if power is None else round(power, 2),
                "residual_load_mw": round(sum(residuals) / len(residuals), 0)
                if residuals
                else None,
                "implied_gas_burn_gwh": round(burn / 1000, 2) if burn_basis else None,
                "burn_basis": sorted(burn_basis),
                "gas_hub": power_market.gas_hub,
                "gas_price": None if gas_price is None else round(gas_price, 3),
                "carbon_market": carbon_code,
                "carbon_price": None if carbon is None else round(carbon, 2),
                "coal_price_per_mwh": None if coal is None else round(coal, 3),
                "clean_spark_spread": None if css is None else round(css, 2),
                "clean_dark_spread": None if cds is None else round(cds, 2),
                "fuel_switch_gas_price": None if switch is None else round(switch, 3),
                "currency": power_market.currency,
            }
        )
    if not rows:
        warnings.append(
            f"No ENTSO-E data for {power_market.code}; enable src-entsoe in Source Center."
        )
    if rows and not gas:
        warnings.append(f"No licensed {power_market.gas_hub} closes; spark spreads are empty.")
    if rows and carbon_code and carbon_code not in settlements:
        warnings.append(
            f"No {carbon_code} settlements; import them with scripts/ops/import_settlements.py."
        )
    if is_gb:
        warnings.append(
            "GB carbon includes Carbon Price Support of "
            f"{GB_CARBON_PRICE_SUPPORT_GBP_T:.0f} GBP/t; "
            "GB has no coal plant, so dark spreads are not computed."
        )
    elif rows and "API2" in settlements and eur_per_usd is None:
        warnings.append("No ECB EUR/USD rate; API2 coal cannot be converted.")
    if format != "json":
        return report_response(
            rows,
            report=f"gas-for-power-{power_market.code}",
            format=format,
            title=f"Gas for power {power_market.code}",
        )
    return _env(rows, "runtime-postgresql", warnings)


#: ENTSOG entry points that land Norwegian pipeline gas in north-west Europe (Europipe I/II,
#: Norpipe, Zeepipe, Franpipe, Vesterled, Langeled). Matched on the point name.
NORWEGIAN_ENTRY_POINTS = (
    "EMDEN",
    "DORNUM",
    "ZEEBRUGGE ZPT",
    "DUNKERQUE",
    "ST. FERGUS",
    "ST FERGUS",
    "EASINGTON",
)
#: Gross calorific value used to turn Norwegian volumes into energy (kWh per m3).
NORWEGIAN_GCV_KWH_M3 = 11.0


def _utc_date(session, column):
    """The UTC calendar date of a timestamp column (PostgreSQL would use the session zone)."""

    from sqlalchemy import func, literal_column

    if session.get_bind().dialect.name == "postgresql":
        # A literal, not a bound parameter, so GROUP BY sees the same expression as SELECT.
        return func.date(func.timezone(literal_column("'UTC'"), column))
    return func.date(column)


def _daily_sum(session, column_expr, model, filters, first: date):
    from sqlalchemy import func

    day = _utc_date(session, model.period_start_utc)
    query = session.query(day, func.sum(column_expr)).filter(
        model.period_start_utc >= _bound(session, first)
    )
    for condition in filters:
        query = query.filter(condition)
    return {
        (value if isinstance(value, date) else date.fromisoformat(str(value))): float(total or 0)
        for value, total in query.group_by(day).all()
        if value is not None
    }


@router.get("/api/market/nwe-balance")
def get_nwe_balance(
    request: Request,
    days: int = Query(14, ge=1, le=31),
    format: str = Query("json", pattern="^(json|csv|xlsx|pdf)$"),
):
    """North-west Europe daily balance: call on Norway, LNG and storage, and its forecast.

    西北欧天然气日度平衡：对挪威管道气、LNG 与储气的需求及其预测（含 REMIT 停运）。

    History is measured from ENTSOG Norwegian entry flows, GIE ALSI send-out and GIE AGSI
    net withdrawal for GB, NL, BE, DE, FR, DK and LU, in GWh per gas day. The forecast
    states its method per component on every day (see ``domain.fundamentals.balance``).
    """

    from sqlalchemy import or_
    from sqlalchemy.exc import SQLAlchemyError

    from eurogas_nexus.db.models import FlowObservationRecord, RemitUmmRecord
    from eurogas_nexus.db.models.observation import (
        LngObservationRecord,
        StorageObservationRecord,
    )
    from eurogas_nexus.domain.fundamentals.balance import (
        NWE_COUNTRIES,
        BalanceHistoryDay,
        Outage,
        forecast_balance,
    )

    session = _session_or_none()
    if session is None:
        return _env({}, "runtime-db-not-configured", ["RUNTIME_DB_NOT_CONFIGURED"])
    today = datetime.now(UTC).date()
    first = today - timedelta(days=800)
    mcm_to_gwh = NORWEGIAN_GCV_KWH_M3  # 1 mcm x kWh/m3 = GWh
    try:
        with session:
            norway = _daily_sum(
                session,
                FlowObservationRecord.flow_mcm_d,
                FlowObservationRecord,
                [
                    or_(
                        *(
                            FlowObservationRecord.point_name.ilike(f"%{name}%")
                            for name in NORWEGIAN_ENTRY_POINTS
                        )
                    ),
                    FlowObservationRecord.direction.ilike("entry"),
                ],
                first,
            )
            lng = _daily_sum(
                session,
                LngObservationRecord.send_out_twh_d,
                LngObservationRecord,
                [LngObservationRecord.country.in_(NWE_COUNTRIES)],
                first,
            )
            withdrawal = _daily_sum(
                session,
                StorageObservationRecord.withdrawal_twh_d,
                StorageObservationRecord,
                [StorageObservationRecord.country.in_(NWE_COUNTRIES)],
                first,
            )
            injection = _daily_sum(
                session,
                StorageObservationRecord.injection_twh_d,
                StorageObservationRecord,
                [StorageObservationRecord.country.in_(NWE_COUNTRIES)],
                first,
            )
            latest_storage_day = max(withdrawal, default=None)
            inventory = capacity = None
            if latest_storage_day is not None:
                from sqlalchemy import func

                inventory, capacity = (
                    session.query(
                        func.sum(StorageObservationRecord.inventory_twh),
                        func.sum(StorageObservationRecord.working_capacity_twh),
                    )
                    .filter(StorageObservationRecord.country.in_(NWE_COUNTRIES))
                    .filter(
                        _utc_date(session, StorageObservationRecord.period_start_utc)
                        == latest_storage_day
                    )
                    .one()
                )
            cutoff = datetime.now(UTC)
            remit = (
                session.query(RemitUmmRecord)
                .filter(RemitUmmRecord.balancing_zone.ilike("%NO%"))
                .filter(
                    or_(
                        RemitUmmRecord.event_stop_utc.is_(None),
                        RemitUmmRecord.event_stop_utc > _bound(session, cutoff.date()),
                    )
                )
                .all()
            )
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "runtime_db_unavailable", "error_class": exc.__class__.__name__},
        ) from exc

    history = [
        BalanceHistoryDay(
            day=day,
            norway_gwh=norway[day] * mcm_to_gwh,
            lng_gwh=lng[day] * 1000,
            storage_net_withdrawal_gwh=(withdrawal.get(day, 0.0) - injection.get(day, 0.0)) * 1000,
        )
        for day in sorted(set(norway) & set(lng) & (set(withdrawal) | set(injection)))
    ]
    latest_version: dict[str, Any] = {}
    for record in remit:
        held = latest_version.get(record.message_id)
        if held is None or record.version > held.version:
            latest_version[record.message_id] = record
    outages = []
    for record in latest_version.values():
        if record.event_status == "dismissed":
            continue
        gwh = record.unavailable_gwh_d
        if gwh is None and record.unavailable_mcm_d is not None:
            gwh = record.unavailable_mcm_d * mcm_to_gwh
        if not gwh:
            continue
        outages.append(
            Outage(
                start=_aware(record.event_start_utc).date(),
                end=_aware(record.event_stop_utc).date() if record.event_stop_utc else None,
                unavailable_gwh_d=gwh,
            )
        )
    start = (history[-1].day + timedelta(days=1)) if history else today
    forecast = forecast_balance(
        history,
        start=start,
        days=days + max(0, (today - start).days),
        norway_outages=outages,
        inventory_twh=float(inventory) if inventory else None,
        working_capacity_twh=float(capacity) if capacity else None,
    )
    warnings = list(forecast.warnings)
    if not history:
        warnings.append(
            "No overlapping ENTSOG Norwegian entry, ALSI and AGSI history for NW Europe; "
            "check that these sources are scheduled."
        )
    if format != "json":
        measured = [
            {
                "day": h.day.isoformat(),
                "kind": "measured",
                "call_gwh": round(h.call_gwh, 1),
                "norway_gwh": round(h.norway_gwh, 1),
                "lng_gwh": round(h.lng_gwh, 1),
                "storage_net_withdrawal_gwh": round(h.storage_net_withdrawal_gwh, 1),
            }
            for h in history[-28:]
        ]
        forecasted = [{**d.as_dict(), "kind": "forecast"} for d in forecast.days]
        return report_response(
            measured + forecasted, report="nwe-balance", format=format, title="NW Europe balance"
        )
    return _env(
        {
            "region": list(NWE_COUNTRIES),
            "unit": "GWh/d",
            "history": [
                {
                    "day": h.day.isoformat(),
                    "call_gwh": round(h.call_gwh, 1),
                    "norway_gwh": round(h.norway_gwh, 1),
                    "lng_gwh": round(h.lng_gwh, 1),
                    "storage_net_withdrawal_gwh": round(h.storage_net_withdrawal_gwh, 1),
                }
                for h in history[-28:]
            ],
            "forecast": [d.as_dict() for d in forecast.days],
            "norway_outages": len(outages),
            "assumptions": {
                "norwegian_gcv_kwh_m3": NORWEGIAN_GCV_KWH_M3,
                "norwegian_entry_points": list(NORWEGIAN_ENTRY_POINTS),
                "storage_inventory_day": latest_storage_day.isoformat()
                if latest_storage_day
                else None,
            },
        },
        "runtime-postgresql",
        warnings,
    )
