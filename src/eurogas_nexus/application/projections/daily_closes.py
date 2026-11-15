"""Daily closes: entitled gas-price observations reduced to one close per series per day.

Spread lab, fundamentals and the position marks read the same closes. Entitlement is
applied for the caller (an API request or an explicit worker caller).
"""

from __future__ import annotations

from datetime import date
from typing import Any

from eurogas_nexus.application.caller import caller_of
from eurogas_nexus.application.projections.market_reads import filter_entitled_rows
from eurogas_nexus.domain.ontology.identity import resolve_hub


class ObservationWindowTooLarge(ValueError):
    """The requested window holds more observations than one read may load."""


def _price_unit(currency: str, unit: str) -> str:
    """``EUR/MWh`` whether the stored unit already names the currency or not."""

    return unit if "/" in unit else f"{currency}/{unit}"


def per_mwh(price: float, unit: str) -> tuple[float, str] | None:
    """``price`` in its own currency per MWh, through the unit authority.

    ``84.50 GBp/th`` is ``28.83 GBP/MWh``; ``31.40 EUR/MWh`` is unchanged. A unit the
    authority does not know returns ``None`` unless it is already per MWh (a legacy row
    stored as ``MWh`` with its currency in the currency column), which is used as stored.
    """

    from eurogas_nexus.domain.market.units import (
        PRICE_UNITS,
        UnitConversionError,
        canonical_price_unit,
        convert_price,
    )

    try:
        canonical = canonical_price_unit(unit)
    except UnitConversionError:
        return (price, unit) if "MWH" in unit.upper() else None
    currency = PRICE_UNITS[canonical][0]
    target = f"{currency}/MWh"
    if canonical == target:
        return price, target
    return convert_price(price, canonical, target), target


def in_native_unit(hub: str, price: float, unit: str) -> tuple[float, str]:
    """``price`` in the hub's native quotation (NBP in pence per therm), for display.

    Prices are stored per MWh by the imports (a p/th settlement is stored in GBP/MWh with
    its native value in the metadata), and the desk reads NBP in p/th. The conversion is
    the unit authority's; a hub without a native unit, a unit the authority does not know,
    or a native unit in another currency (that would need FX) keeps the stored unit.
    """

    from eurogas_nexus.domain.market.units import (
        HUB_NATIVE_PRICE_UNIT,
        PRICE_UNITS,
        UnitConversionError,
        canonical_price_unit,
        convert_price,
    )

    native = HUB_NATIVE_PRICE_UNIT.get(hub)
    try:
        stored = canonical_price_unit(unit)
        if not native or canonical_price_unit(native) == stored:
            return price, unit
        native = canonical_price_unit(native)
        if PRICE_UNITS[native][0] != PRICE_UNITS[stored][0]:
            return price, unit
        return convert_price(price, stored, native), native
    except UnitConversionError:
        return price, unit


#: A spread reads daily closes; this bounds the rows one request may load (about ten years
#: of daily closes for 40 series, or less history when intraday ticks are stored too).
MAX_OBSERVATION_ROWS = 150_000


def daily_rows(
    who: Any, date_from: date | None = None, date_to: date | None = None
) -> list[dict[str, Any]]:
    """Entitled gas-price observations reduced to one close per series per trade date.

    Gas prices per unit of energy in the requested window are read, in their stored
    (native) unit: NBP in pence per therm, continental hubs in EUR/MWh. Each row also
    carries ``price_mwh`` and ``unit_mwh``, the same price in its currency per MWh through
    the unit authority (``domain.market.units``); anything that multiplies a price by MWh
    (marks, P&L, exposure) uses those, never ``price``.

    ``who`` is an API request or a :class:`~eurogas_nexus.application.caller.Caller`.

    Raises:
        ObservationWindowTooLarge: above :data:`MAX_OBSERVATION_ROWS` rows.
        SQLAlchemyError: when the runtime store is unavailable.
    """

    from datetime import UTC, datetime, time, timedelta

    from sqlalchemy import func, or_

    from eurogas_nexus.db.models import MarketObservationRecord
    from eurogas_nexus.db.session import get_session_factory, resolve_database_url

    if resolve_database_url() is None:
        return []
    with get_session_factory()() as session:
        query = session.query(
            MarketObservationRecord.product,
            MarketObservationRecord.price,
            MarketObservationRecord.unit,
            MarketObservationRecord.currency,
            MarketObservationRecord.observed_at_utc,
            MarketObservationRecord.source_system,
            MarketObservationRecord.metadata_json,
            MarketObservationRecord.period_start_utc,
        ).filter(
            or_(
                func.upper(MarketObservationRecord.unit).like("%MWH%"),
                func.upper(MarketObservationRecord.unit).like("%/TH"),
                func.upper(MarketObservationRecord.unit).like("%THERM%"),
            )
        )
        # SQLite stores these timestamps without an offset; compare like with like.
        naive = session.get_bind().dialect.name == "sqlite"

        def bound(day: date) -> datetime:
            moment = datetime.combine(day, time.min, tzinfo=UTC)
            return moment.replace(tzinfo=None) if naive else moment

        if date_from:
            query = query.filter(MarketObservationRecord.observed_at_utc >= bound(date_from))
        if date_to:
            query = query.filter(
                MarketObservationRecord.observed_at_utc < bound(date_to + timedelta(days=1))
            )
        records = (
            query.order_by(MarketObservationRecord.observed_at_utc)
            .limit(MAX_OBSERVATION_ROWS + 1)
            .all()
        )
        if len(records) > MAX_OBSERVATION_ROWS:
            raise ObservationWindowTooLarge(MAX_OBSERVATION_ROWS)
        rows = []
        for record in records:
            metadata = record.metadata_json or {}
            stated = metadata.get("hub") or record.product
            resolution = resolve_hub(stated)
            # An unresolved product keeps its stated text as its series name (the spread
            # lab lists it) and is marked unresolved, so nothing values a hub with it. No
            # first word is taken as a hub (ONT-02).
            hub = resolution.hub or str(stated).strip().upper()
            tenor = str(metadata.get("tenor") or record.product).lower()
            unit = _price_unit(record.currency, record.unit)
            converted = per_mwh(float(record.price), unit)
            if converted is None:
                continue  # not a price per unit of energy this read can use
            rows.append(
                {
                    "hub": hub,
                    "hub_resolved": resolution.resolved,
                    "tenor": tenor,
                    "source_system": record.source_system,
                    "currency": record.currency,
                    "unit": unit,
                    "day": record.observed_at_utc.date(),
                    "observed_at_utc": record.observed_at_utc,
                    "period_start_utc": record.period_start_utc,
                    "price": float(record.price),
                    "price_mwh": converted[0],
                    "unit_mwh": converted[1],
                    "simulated": bool(metadata.get("simulated"))
                    or record.source_system.endswith("_Sim"),
                }
            )

    return filter_entitled_rows(caller_of(who).principal, rows, source_key="source_system")
