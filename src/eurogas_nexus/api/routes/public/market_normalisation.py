"""/api/market reads for comparable prices: forward FX, normalisation and the instrument catalogue.

- ``GET /api/market/fx-forward``: a pair and a delivery period (a desk product code or a value
  date) → the rate with its method, inputs, dates and tolerance (design basis D.5).
- ``POST /api/market/normalise``: prices or a series → the requested unit and currency, each
  with its normalisation record (factors, heating value, FX rate, method and date) and tolerance.
- ``GET /api/market/instruments``: the caller's entitled daily series as hub → product kind →
  tenor (D.2), with native unit, source class and last as-of per instrument.

All three are reads (READ permission, like every ``/api/market/`` read): nothing is stored. FX
facts and prices are filtered by the caller's data entitlements.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from eurogas_nexus.application.market_normalisation import (
    NormalisationError,
    load_holdings,
    normalise_quantity,
    normalise_series,
    normalise_value,
    points_from_closes,
)
from eurogas_nexus.domain.market.fx_forward import (
    Delivery,
    FxForwardError,
    conversion_rate,
    delivery_from_period,
)
from eurogas_nexus.domain.market.products import ProductCodeError, resolve_product

router = APIRouter(tags=["market"])

MAX_VALUES = 500
MAX_SERIES_POINTS = 2_000


def _env(data: object, *, source: str, warnings: list[str] | None = None) -> dict:
    return {
        "data": data,
        "meta": {
            "research_only": True,
            "human_review_required": True,
            "source_references": [source],
            "warnings": warnings or [],
        },
    }


def _unprocessable(code: str, message: str) -> HTTPException:
    return HTTPException(status_code=422, detail={"code": code, "message": message})


def _db_unavailable(exc: Exception) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={"code": "runtime_db_unavailable", "error_class": exc.__class__.__name__},
    )


def _holdings(request: Request):
    from sqlalchemy.exc import SQLAlchemyError

    try:
        return load_holdings(request)
    except SQLAlchemyError as exc:
        raise _db_unavailable(exc) from exc


def _delivery(product: str | None, value_date: date | None, as_of: date) -> Delivery | None:
    """The delivery a request names: a product code against ``as_of``, or a bare value date."""

    if product and value_date:
        raise _unprocessable("delivery_ambiguous", "give either product or value_date, not both")
    if value_date is not None:
        return Delivery(value_date, value_date, "value_date", value_date.isoformat())
    if product:
        try:
            return delivery_from_period(resolve_product(product, as_of))
        except ProductCodeError as exc:
            raise _unprocessable("unknown_product_code", str(exc)) from exc
    return None


@router.get("/api/market/fx-forward")
def fx_forward(
    request: Request,
    base: str = Query(..., min_length=3, max_length=3),
    quote: str = Query(..., min_length=3, max_length=3),
    product: str | None = Query(default=None, max_length=16),
    value_date: date | None = None,
    as_of: date | None = None,
) -> dict:
    """Units of ``quote`` per one ``base`` for a delivery period, with method and inputs.

    ``product`` is a desk code (``Jan-27``, ``M+1``, ``Q1-27``, ``DA``) resolved against
    ``as_of`` (default today); ``value_date`` names the forward date directly. Without either,
    or for a prompt product, the spot reference rate is returned. A derived forward is labelled
    "derived" and carries its tolerance; a licensed forward overrides it.
    远期汇率（抛补利率平价推导或授权远期），附方法、输入、日期与容差。

    Raises:
        HTTPException: 422 ``fx_not_convertible`` (rate or fixing not held, unsupported
            currency), ``beyond_horizon`` (more than 24 months without licensed forwards),
            ``unknown_product_code``.
    """

    anchor = as_of or datetime.now(UTC).date()
    delivery = _delivery(product, value_date, anchor)
    holdings = _holdings(request)
    try:
        rate = conversion_rate(holdings, base, quote, as_of=anchor, delivery=delivery)
    except FxForwardError as exc:
        code = "beyond_horizon" if exc.code == "beyond_horizon" else "fx_not_convertible"
        raise _unprocessable(code, str(exc)) from exc
    payload = rate.as_dict()
    payload["as_of"] = anchor.isoformat()
    warnings = ["Derived from simulated demo rates."] if rate.simulated else []
    return _env(payload, source="fx-forward", warnings=warnings)


class NormaliseValueInput(BaseModel):
    value: float = Field(allow_inf_nan=False)
    unit: str = Field(min_length=3, max_length=16)
    product: str | None = Field(default=None, max_length=16)
    value_date: date | None = None
    as_of: date | None = None
    simulated: bool = False
    label: str | None = Field(default=None, max_length=64)


class SeriesPointInput(BaseModel):
    day: date
    value: float = Field(allow_inf_nan=False)
    product: str | None = Field(default=None, max_length=16)


class NormaliseSeriesInput(BaseModel):
    unit: str = Field(min_length=3, max_length=16)
    simulated: bool = False
    label: str | None = Field(default=None, max_length=64)
    points: list[SeriesPointInput] = Field(min_length=1, max_length=MAX_SERIES_POINTS)


class QuantityValueInput(BaseModel):
    value: float = Field(allow_inf_nan=False)
    unit: str = Field(min_length=2, max_length=16)
    simulated: bool = False
    label: str | None = Field(default=None, max_length=64)


class NormaliseInput(BaseModel):
    #: The price unit values and the series are put into (``EUR/MWh``).
    to_unit: str | None = Field(default=None, min_length=3, max_length=16)
    values: list[NormaliseValueInput] = Field(default_factory=list, max_length=MAX_VALUES)
    #: Quantities (``MWh/d``, ``th/d``) and the unit they are put into: physical factors only.
    quantities: list[QuantityValueInput] = Field(default_factory=list, max_length=MAX_VALUES)
    to_quantity_unit: str | None = Field(default=None, min_length=2, max_length=16)
    series: NormaliseSeriesInput | None = None
    gcv_kwh_per_m3: float | None = Field(default=None, allow_inf_nan=False)


@router.post("/api/market/normalise")
def normalise(body: NormaliseInput, request: Request) -> dict:
    """Prices or one series in ``to_unit``, and quantities in ``to_quantity_unit``, each with its
    normalisation record and tolerance. A quantity (``MWh/d`` → ``th/d``) converts with the units
    authority's fixed factors only (a heating value between energy and volume), never FX.

    A value's delivery period (``product`` or ``value_date``) decides the FX: spot for none or a
    prompt product, the forward for a future period. A value that cannot be converted carries
    ``refused`` with the reason instead of a number; nothing is guessed. ``simulated`` inputs
    stay simulated. Series points use the FX of their own day.
    价格或序列换算为目标单位，逐项附换算记录与容差；无法换算的项明确拒绝。

    Raises:
        HTTPException: 422 ``normalise_invalid`` (nothing to convert, unknown unit,
            implausible heating value, unknown product code).
    """

    if not body.values and body.series is None and not body.quantities:
        raise _unprocessable(
            "normalise_invalid", "give values, a series or quantities to normalise"
        )
    if (body.values or body.series is not None) and not body.to_unit:
        raise _unprocessable("normalise_invalid", "give to_unit for prices")
    if body.quantities and not body.to_quantity_unit:
        raise _unprocessable("normalise_invalid", "give to_quantity_unit for quantities")
    today = datetime.now(UTC).date()
    holdings = _holdings(request) if (body.values or body.series is not None) else None
    results: list[dict[str, Any]] = []
    try:
        for item in body.values:
            anchor = item.as_of or today
            delivery = _delivery(item.product, item.value_date, anchor)
            try:
                converted = normalise_value(
                    item.value,
                    item.unit,
                    body.to_unit,
                    holdings=holdings,
                    as_of=anchor,
                    delivery=delivery,
                    simulated=item.simulated,
                    gcv_kwh_per_m3=body.gcv_kwh_per_m3,
                )
            except NormalisationError as exc:
                if exc.code in ("unsupported_price_unit", "implausible_heating_value"):
                    raise
                converted = {
                    "value": None,
                    "native": {"value": item.value, "unit": item.unit},
                    "simulated": item.simulated,
                    "refused": {"code": exc.code, "message": str(exc)},
                }
            if item.label:
                converted["label"] = item.label
            results.append(converted)
        series = None
        if body.series is not None:
            points = []
            for point in body.series.points:
                points.append(
                    (point.day, point.value, _delivery(point.product, None, point.day))
                )
            series = normalise_series(
                points_from_closes(points),
                body.series.unit,
                body.to_unit,
                holdings=holdings,
                simulated=body.series.simulated,
                gcv_kwh_per_m3=body.gcv_kwh_per_m3,
            )
            if body.series.label:
                series["label"] = body.series.label
        quantities: list[dict[str, Any]] = []
        for item in body.quantities:
            converted = normalise_quantity(
                item.value,
                item.unit,
                body.to_quantity_unit or "",
                simulated=item.simulated,
                gcv_kwh_per_m3=body.gcv_kwh_per_m3,
            )
            if item.label:
                converted["label"] = item.label
            quantities.append(converted)
    except NormalisationError as exc:
        raise _unprocessable("normalise_invalid", str(exc)) from exc
    warnings = []
    if any(item.get("refused") for item in results) or (series and series["refused"]):
        warnings.append("Some prices could not be converted; each says why.")
    if any(item.get("simulated") for item in results) or (series and series["simulated"]):
        warnings.append("Simulated inputs stay simulated after conversion.")
    if any(item["simulated"] for item in quantities):
        warnings.append("Simulated inputs stay simulated after conversion.")
    return _env(
        {"values": results, "series": series, "quantities": quantities},
        source="market-normalisation",
        warnings=sorted(set(warnings), key=warnings.index),
    )


@router.get("/api/market/instruments")
def list_instruments(request: Request) -> dict:
    """The caller's entitled daily price series as hub → product kind → tenor.

    Each instrument has a stable id, native unit and currency, source class (sourced,
    indicative, simulated), observations held and last as-of. The flat
    ``/api/research/spread-series`` list stays until its last client is gone.
    合约目录：枢纽→产品类型→期限，仅含调用者有权访问的序列。

    Raises:
        HTTPException: 503 ``runtime_db_unavailable``.
    """

    from sqlalchemy.exc import SQLAlchemyError

    from eurogas_nexus.application.instrument_catalogue import build_catalogue
    from eurogas_nexus.application.projections.daily_closes import (
        ObservationWindowTooLarge,
        daily_rows,
    )

    try:
        rows = daily_rows(request)
    except ObservationWindowTooLarge as exc:
        raise _unprocessable(
            "catalogue_too_large", "too many observations to build the catalogue"
        ) from exc
    except SQLAlchemyError as exc:
        raise _db_unavailable(exc) from exc
    return _env(build_catalogue(rows), source="runtime-postgresql")
