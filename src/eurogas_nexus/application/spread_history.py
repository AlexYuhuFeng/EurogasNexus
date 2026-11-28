"""The daily spread history and its rule backtest, for the API.

The spread lab route (``api/routes/public/spread_lab.py``) and Research → Spreads run this one
function: daily closes
per (hub, tenor, source) from the runtime market observations, filtered by the caller's data
entitlements, converted to one display unit per day, and the pure
:mod:`eurogas_nexus.domain.research.spread_analysis` engine. Problems are
:class:`SpreadHistoryError` with the HTTP status and detail the route answers with.

价差历史与规则回测（API 使用）。
"""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, Field, model_validator

from eurogas_nexus.domain.research.spread_analysis import (
    SpreadAnalysisError,
    SpreadLeg,
    SpreadRule,
    analyse_spread,
)


def _env(data: object, *, warnings: list[str] | None = None) -> dict:
    return {
        "data": data,
        "meta": {
            "research_only": True,
            "human_review_required": True,
            "source_references": ["runtime-postgresql"],
            "warnings": warnings or [],
        },
    }


class SpreadHistoryError(Exception):
    """A request the spread history cannot answer, with the status and detail to return."""

    def __init__(self, status_code: int, detail: dict[str, Any]) -> None:
        super().__init__(detail.get("message") or detail.get("code"))
        self.status_code = status_code
        self.detail = detail


class SpreadLegInput(BaseModel):
    hub: str = Field(min_length=2, max_length=16)
    tenor: str = Field(min_length=2, max_length=32)
    source_system: str | None = Field(default=None, max_length=64)
    weight: float = Field(default=1.0, allow_inf_nan=False)


class SpreadRuleInput(BaseModel):
    kind: str = "zscore"
    lookback: int = 20
    entry_z: float = Field(default=2.0, allow_inf_nan=False)
    exit_z: float = Field(default=0.5, allow_inf_nan=False)
    low: float | None = Field(default=None, allow_inf_nan=False)
    high: float | None = Field(default=None, allow_inf_nan=False)
    volume_mwh_per_day: float = Field(default=1_000.0, allow_inf_nan=False)
    #: Cost per MWh per position change in the display unit; when omitted, half the held
    #: bid/offer of each leg (the newest two-sided quotes), else zero, and the result says which.
    cost_per_mwh: float | None = Field(default=None, ge=0, le=100, allow_inf_nan=False)
    #: ``next_close`` (default) or ``same_close``.
    execution: str = Field(default="next_close", max_length=16)


class RouteCostInput(BaseModel):
    from_hub: str = Field(min_length=2, max_length=16)
    to_hub: str = Field(min_length=2, max_length=16)


class SpreadAnalysisInput(BaseModel):
    legs: list[SpreadLegInput] = Field(min_length=1, max_length=4)
    date_from: date | None = None
    date_to: date | None = None
    rule: SpreadRuleInput = Field(default_factory=SpreadRuleInput)
    #: Display unit for legs in different units (``EUR/MWh``, ``p/th``, ``USD/MMBtu``); the
    #: first leg's native unit when omitted.
    unit: str | None = Field(default=None, min_length=3, max_length=16)
    #: The rule reads the spread net of this route's published tariff, per gas year.
    route_cost: RouteCostInput | None = None
    #: ``spot`` converts every day at that day's spot; ``forward`` (default) per delivery.
    fx: str | None = Field(default=None, max_length=8)

    @model_validator(mode="after")
    def _dates_in_order(self) -> SpreadAnalysisInput:
        # A reversed window read no rows and was answered "no entitled daily series", which
        # sent the user to check their data entitlements instead of their dates.
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError(
                f"date_from {self.date_from} is after date_to {self.date_to}"
            )
        return self


def daily_rows_for(
    request: Any, date_from: date | None = None, date_to: date | None = None, *,
    tenors: tuple[str, ...] | None = None,
) -> list[dict[str, Any]]:
    """Daily closes for the caller, with HTTP errors for an oversize window or a down store.

    ``tenors`` narrows the read in SQL (see ``daily_rows``); the catalogue reads them all.
    """

    from sqlalchemy.exc import SQLAlchemyError

    from eurogas_nexus.application.projections.daily_closes import (
        ObservationWindowTooLarge,
        daily_rows,
    )

    try:
        return daily_rows(request, date_from, date_to, tenors=tenors)
    except ObservationWindowTooLarge as exc:
        raise SpreadHistoryError(
            status_code=422,
            detail={
                "code": "spread_window_too_large",
                "message": "too many observations in this window; narrow the dates",
            },
        ) from exc
    except SQLAlchemyError as exc:
        raise SpreadHistoryError(
            status_code=503,
            detail={"code": "runtime_db_unavailable", "error_class": exc.__class__.__name__},
        ) from exc


def spread_history(body: SpreadAnalysisInput, request: Any) -> dict:
    """Weighted spread of 1-4 daily series, its statistics and a declared-rule backtest.

    Legs quoted in different units or currencies (NBP in p/th against TTF in EUR/MWh) are
    converted to one display unit through the normalisation service: ``unit`` when given, else
    the first leg's native unit. Each day uses the FX of that day for that day's delivery
    period (spot for prompt products, the forward of D.5 otherwise), and the response states
    the conversion per leg. A day whose FX is not held is left out and counted; a leg with no
    convertible day is refused with the reason. Legs in one unit are not converted.
    计算 1–4 条日度序列的加权价差、统计量及声明式规则回测（无前视偏差）；不同单位/币种的
    腿按当日交割期汇率换算为同一单位，并逐腿说明换算方式。

    Raises:
        SpreadHistoryError: 422 ``spread_analysis_invalid`` (unknown series, a leg that cannot be
            converted, too little overlap, bad rule).
    """

    # Read only the legs' tenors: the demo market alone holds ~35 000 closes of other tenors,
    # and reading them all made every analysis (and every daily track) take ~2 s.
    rows = daily_rows_for(
        request, body.date_from, body.date_to,
        tenors=tuple(sorted({leg.tenor.strip().lower() for leg in body.legs})),
    )
    collected: list[tuple[str, str, float, dict[date, dict[str, Any]]]] = []
    units: set[str] = set()
    simulated = False
    for leg in body.legs:
        hub, tenor = leg.hub.strip().upper(), leg.tenor.strip().lower()
        closes: dict[date, dict[str, Any]] = {}
        for row in rows:
            if row["hub"] != hub or row["tenor"] != tenor:
                continue
            if leg.source_system and row["source_system"] != leg.source_system:
                continue
            if body.date_from and row["day"] < body.date_from:
                continue
            if body.date_to and row["day"] > body.date_to:
                continue
            closes[row["day"]] = row  # rows are time-ordered: last one wins
            units.add(row["unit"])
            simulated = simulated or row["simulated"]
        if not closes:
            raise SpreadHistoryError(
                status_code=422,
                detail={
                    "code": "spread_analysis_invalid",
                    "message": f"no entitled daily series for {hub} {tenor}"
                    + (f" from {leg.source_system}" if leg.source_system else ""),
                },
            )
        source = f" ({leg.source_system})" if leg.source_system else ""
        collected.append((f"{hub} {tenor}{source}", hub, leg.weight, closes))

    normalisation: list[dict[str, Any]] = []
    warnings: list[str] = []
    if body.unit is None and len(units) == 1:
        display = next(iter(units))
        legs = [
            SpreadLeg(label, weight, {day: row["price"] for day, row in closes.items()})
            for label, _, weight, closes in collected
        ]
    else:
        display, legs, normalisation, warnings, converted_simulated = _normalised_legs(
            request, collected, body.unit
        )
        simulated = simulated or converted_simulated
    from dataclasses import replace

    legs = [
        replace(leg, deliveries=_deliveries(closes))
        for leg, (_label, _hub, _weight, closes) in zip(legs, collected, strict=True)
    ]
    rule_values = body.rule.model_dump()
    cost_basis = "stated"
    if rule_values.get("cost_per_mwh") is None:
        rule_values["cost_per_mwh"], cost_basis = _quoted_cost(request, collected, legs)
    offsets, tariff_notes = ({}, [])
    if body.route_cost is not None:
        offsets, tariff_notes = _tariff_offsets(request, body, collected, display)
    fx_note = _fx_note(normalisation)
    factor, money = _money_per_unit(display)
    try:
        analysis = analyse_spread(
            legs, SpreadRule(**rule_values), simulated_sources=simulated,
            signal_offsets=offsets or None, cost_basis=cost_basis, fx_note=fx_note,
            currency_per_unit=factor, currency=money,
        )
    except SpreadAnalysisError as exc:
        raise SpreadHistoryError(
            status_code=422,
            detail={"code": "spread_analysis_invalid", "message": str(exc)},
        ) from exc
    payload = analysis.as_dict()
    payload["unit"] = display
    payload["normalisation"] = normalisation
    payload["tariffs"] = tariff_notes
    payload["pnl_currency"] = money
    return _env(payload, warnings=[*analysis.limitations, *warnings])


def _normalised_legs(
    request: Any,
    collected: list[tuple[str, str, float, dict[date, dict[str, Any]]]],
    requested_unit: str | None,
) -> tuple[str, list[SpreadLeg], list[dict[str, Any]], list[str], bool]:
    """Every leg's closes in one display unit, with the conversion stated per leg."""

    from sqlalchemy.exc import SQLAlchemyError

    from eurogas_nexus.application.market_normalisation import (
        NormalisationError,
        SeriesPoint,
        display_unit,
        load_holdings,
        normalise_series,
        parse_price_unit,
    )
    from eurogas_nexus.domain.market.fx_forward import delivery_from_bounds
    from eurogas_nexus.domain.market.units import HUB_NATIVE_PRICE_UNIT

    first_hub, first_closes = collected[0][1], collected[0][3]
    target = requested_unit or HUB_NATIVE_PRICE_UNIT.get(first_hub) or next(
        iter(first_closes.values())
    )["unit"]
    try:
        display = display_unit(parse_price_unit(target))
    except NormalisationError as exc:
        raise SpreadHistoryError(
            status_code=422, detail={"code": "spread_analysis_invalid", "message": str(exc)}
        ) from exc
    try:
        holdings = load_holdings(request)
    except SQLAlchemyError as exc:
        raise SpreadHistoryError(
            status_code=503,
            detail={"code": "runtime_db_unavailable", "error_class": exc.__class__.__name__},
        ) from exc
    legs: list[SpreadLeg] = []
    records: list[dict[str, Any]] = []
    warnings: list[str] = []
    any_simulated = False
    for label, _hub, weight, closes in collected:
        by_unit: dict[str, list[SeriesPoint]] = {}
        leg_simulated = False
        for day, row in sorted(closes.items()):
            delivery = None
            if row.get("period_start_utc") is not None and row.get("period_end_utc") is not None:
                delivery = delivery_from_bounds(row["period_start_utc"], row["period_end_utc"])
            by_unit.setdefault(row["unit"], []).append(SeriesPoint(day, row["price"], delivery))
            leg_simulated = leg_simulated or bool(row["simulated"])
        values: dict[date, float] = {}
        refused: list[dict[str, Any]] = []
        for unit, points in by_unit.items():
            try:
                result = normalise_series(
                    points, unit, target, holdings=holdings, simulated=leg_simulated
                )
            except NormalisationError as exc:
                raise SpreadHistoryError(
                    status_code=422,
                    detail={"code": "spread_analysis_invalid", "message": f"{label}: {exc}"},
                ) from exc
            for point in result["points"]:
                if point["value"] is not None:
                    values[date.fromisoformat(point["day"])] = point["value"]
            refused.extend(result["refused"])
            any_simulated = any_simulated or result["simulated"]
            records.append(
                {
                    "leg": label,
                    "from_unit": result["native_unit"],
                    "to_unit": result["unit"],
                    "converted": result["converted"],
                    "refused": result["refused"],
                    "fx_methods": result["fx_methods"],
                    "fx_labels": result["fx_labels"],
                    "max_tolerance_pct": result["max_tolerance_pct"],
                    "latest": result["latest"],
                    "simulated": result["simulated"],
                }
            )
        if not values:
            reason = refused[0]["reason"] if refused else "no convertible day"
            raise SpreadHistoryError(
                status_code=422,
                detail={"code": "spread_analysis_invalid", "message": f"{label}: {reason}"},
            )
        skipped = sum(item["points"] for item in refused)
        if skipped:
            warnings.append(f"{label}: {skipped} day(s) left out ({refused[0]['reason']}).")
        legs.append(SpreadLeg(label, weight, values))
    return display, legs, records, warnings, any_simulated


def _deliveries(closes: dict[date, dict[str, Any]]) -> dict[date, tuple[str, int]]:
    """The contract behind each close: (first gas day, gas days delivered)."""

    out: dict[date, tuple[str, int]] = {}
    for day, row in closes.items():
        start, end = row.get("period_start_utc"), row.get("period_end_utc")
        if start is None or end is None:
            continue
        days = max(1, round((end - start).total_seconds() / 86400))
        out[day] = (start.date().isoformat(), days)
    return out


def _quoted_cost(request: Any, collected, legs) -> tuple[float, str]:
    """Half the newest held bid/offer of every leg, in the display unit (else zero)."""

    from sqlalchemy.exc import SQLAlchemyError

    from eurogas_nexus.application.caller import caller_of
    from eurogas_nexus.application.projections.market_reads import filter_entitled_rows
    from eurogas_nexus.db.models import MarketQuoteRecord
    from eurogas_nexus.db.session import get_session_factory, resolve_database_url

    if resolve_database_url() is None:
        return 0.0, "none"
    total = 0.0
    try:
        with get_session_factory()() as session:
            for leg, (_label, hub, weight, closes) in zip(legs, collected, strict=True):
                tenor = next(iter(closes.values()))["tenor"]
                rows = (
                    session.query(MarketQuoteRecord.source_system, MarketQuoteRecord.bid_price,
                                  MarketQuoteRecord.ask_price)
                    .filter(MarketQuoteRecord.hub == hub,
                            MarketQuoteRecord.product.ilike(tenor),
                            MarketQuoteRecord.bid_price.isnot(None),
                            MarketQuoteRecord.ask_price.isnot(None))
                    .order_by(MarketQuoteRecord.observed_at_utc.desc())
                    .limit(20)
                    .all()
                )
                held = filter_entitled_rows(
                    caller_of(request).principal,
                    [{"source_system": r[0], "bid": r[1], "ask": r[2]} for r in rows],
                )
                if not held:
                    return 0.0, "none"
                last_day = max(closes)
                raw = float(closes[last_day]["price"])
                shown = float(leg.closes.get(last_day, raw)) if leg.closes else raw
                factor = shown / raw if raw else 1.0
                total += abs(weight) * (held[0]["ask"] - held[0]["bid"]) / 2 * factor
    except SQLAlchemyError:
        return 0.0, "none"
    return round(total, 6), "quotes"


def _tariff_offsets(request: Any, body: SpreadAnalysisInput, collected,
                    display: str) -> tuple[dict[date, float], list[dict[str, Any]]]:
    """The route tariff per close, by the gas year the first leg's contract delivers in."""

    from eurogas_nexus.application.market_normalisation import (
        NormalisationError,
        conversion,
        load_holdings,
    )
    from eurogas_nexus.application.route_tariff_cost import load_tariff_rows, route_cost
    from eurogas_nexus.domain.market.fx_forward import delivery_from_bounds

    assert body.route_cost is not None
    tariffs = load_tariff_rows()
    fx = load_holdings(request)
    by_year: dict[str, tuple[float | None, dict[str, Any]]] = {}
    offsets: dict[date, float] = {}
    day_years: list[tuple[date, str]] = []
    for day, row in collected[0][3].items():
        start, end = row.get("period_start_utc"), row.get("period_end_utc")
        if start is None or end is None:
            continue
        delivery = delivery_from_bounds(start, end)
        first = delivery.first
        year = f"{first.year if first.month >= 10 else first.year - 1}"
        if year not in by_year:
            route = route_cost(body.route_cost.from_hub.upper(), body.route_cost.to_hub.upper(),
                               delivery, tariffs)
            value = None
            if route.total is not None and route.currency:
                try:
                    value = route.total * conversion(
                        f"{route.currency}/MWh", display, holdings=fx, as_of=day,
                        delivery=None if body.fx == "spot" else delivery,
                    ).factor
                except NormalisationError:
                    value = None
            by_year[year] = (value, {
                "gas_year": f"{year}/{(int(year) + 1) % 100:02d}",
                "value": None if value is None else round(value, 6),
                "unit": display,
                "tariff_gas_years": list(route.gas_years),
                "input_class": route.input_class,
            })
        day_years.append((day, year))
    # A gas year with no published tariff takes the nearest year that has one, stated as an
    # assumption: a window mixing gross and net closes would move the z-score by the tariff.
    known = sorted(year for year, (value, _) in by_year.items() if value is not None)
    for year, (value, note) in by_year.items():
        if value is None and known:
            nearest = min(known, key=lambda other: abs(int(other) - int(year)))
            by_year[year] = (by_year[nearest][0], {
                **note, "value": by_year[nearest][1]["value"], "input_class": "assumption",
                "assumed_from": by_year[nearest][1]["gas_year"],
            })
    for day, year in day_years:
        value = by_year[year][0]
        if value is not None:
            offsets[day] = value
    return offsets, [note for _value, note in by_year.values()]


def _fx_note(normalisation: list[dict[str, Any]]) -> str:
    import re

    # One method per label; the per-day dates of a daily reference rate are not repeated.
    labels = sorted({
        re.sub(r"\s*\d{4}-\d{2}-\d{2}$", "", label)
        for item in normalisation for label in item.get("fx_labels") or []
    })
    if not labels:
        return ""
    return "FX per close for its delivery: " + ", ".join(labels[:4])


def _money_per_unit(display: str) -> tuple[float, str]:
    """(currency per MWh for one display unit, the currency): p/th -> (0.3412, GBP)."""

    from eurogas_nexus.domain.market.units import canonical_price_unit, convert_price

    try:
        unit = canonical_price_unit(display)
    except Exception:  # noqa: BLE001 - an unknown unit keeps the display unit
        return 1.0, display.split("/")[0]
    if unit.endswith("/MWh"):
        return 1.0, unit.split("/")[0]
    currency = "GBP" if unit.startswith("GBp") else unit.split("/")[0]
    try:
        return round(convert_price(1.0, unit, f"{currency}/MWh"), 9), currency
    except Exception:  # noqa: BLE001
        return 1.0, unit.split("/")[0]
