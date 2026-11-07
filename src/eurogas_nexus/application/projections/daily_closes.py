"""Daily closes: entitled gas-price observations reduced to one close per series per day.

Spread lab, fundamentals and the position marks read the same closes. Entitlement is
applied for the caller (an API request or an explicit worker caller).
"""

from __future__ import annotations

from datetime import date
from typing import Any

from eurogas_nexus.application.caller import caller_of
from eurogas_nexus.application.projections.market_reads import filter_entitled_rows


class ObservationWindowTooLarge(ValueError):
    """The requested window holds more observations than one read may load."""


def _price_unit(currency: str, unit: str) -> str:
    """``EUR/MWh`` whether the stored unit already names the currency or not."""

    return unit if "/" in unit else f"{currency}/{unit}"


#: A spread reads daily closes; this bounds the rows one request may load (about ten years
#: of daily closes for 40 series, or less history when intraday ticks are stored too).
MAX_OBSERVATION_ROWS = 150_000


def daily_rows(
    who: Any, date_from: date | None = None, date_to: date | None = None
) -> list[dict[str, Any]]:
    """Entitled gas-price observations reduced to one close per series per trade date.

    Only per-MWh prices in the requested window are read, and only the columns used.

    ``who`` is an API request or a :class:`~eurogas_nexus.application.caller.Caller`.

    Raises:
        ObservationWindowTooLarge: above :data:`MAX_OBSERVATION_ROWS` rows.
        SQLAlchemyError: when the runtime store is unavailable.
    """

    from datetime import UTC, datetime, time, timedelta

    from sqlalchemy import func

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
        ).filter(func.upper(MarketObservationRecord.unit).like("%MWH%"))
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
            hub = str(metadata.get("hub") or record.product.split(" ")[0]).upper()
            tenor = str(metadata.get("tenor") or record.product).lower()
            rows.append(
                {
                    "hub": hub,
                    "tenor": tenor,
                    "source_system": record.source_system,
                    "currency": record.currency,
                    "unit": _price_unit(record.currency, record.unit),
                    "day": record.observed_at_utc.date(),
                    "price": float(record.price),
                    "simulated": bool(metadata.get("simulated"))
                    or record.source_system.endswith("_Sim"),
                }
            )

    return filter_entitled_rows(caller_of(who).principal, rows, source_key="source_system")
