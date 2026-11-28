"""Public prices fetched under written consent: where they are stored and how they are read.

The watch (``publication_watch``) reads each consented price publication and hands its
:class:`~eurogas_nexus.domain.publications.public_prices.PricePoint` rows here:

- **History** goes to the observation store (``market_observations``), one row per series and
  day, under the publisher's consented source family (``THE``, ``NATIONAL_GAS_PRICES``,
  ``MIBGAS``, ``EEX_PUBLIC``) and the product name the board's chart reads ("THE within-day",
  "PVB day-ahead", "PVB month-ahead", "PVB Q1-27", "PVB Cal-27"). A preliminary value the
  publisher later finalises replaces the held one (the row says so). Prices are stored per MWh
  in the hub's currency, as every import does (NBP in GBP/MWh, its p/th figure beside it).
- **The board** reads one quote per series (``market_quotes``, ``quote_id`` ``pub:<series>``):
  the newest published figure as its *last*, no bid or offer, with what it is, the day it is
  for and the consent it was fetched under in ``metadata_json``. A published daily figure is a
  real price with a date, never a live quote.
- **My gas day** reads the published cash-out: the premium a short position pays (the
  system buy or negative imbalance price over the day's reference price) and the discount a
  long one takes, for the newest gas day published (:func:`published_cash_out`).

经书面同意获取的公开价格：历史写入观测表，最新值写成看板报价（仅“最新”，无买卖价），
并为“我的气日”提供已公布的不平衡价格。
"""

from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from eurogas_nexus.domain.publications.public_prices import (
    CALENDAR_YEAR,
    DAY_AHEAD,
    IMBALANCE,
    IMBALANCE_LONG,
    IMBALANCE_SHORT,
    MONTH,
    QUARTER,
    WITHIN_DAY,
    PricePoint,
)

#: The publisher's venue name on each stored row.
VENUES = {"THE": "THE", "NATIONAL_GAS_PRICES": "National Gas", "MIBGAS": "MIBGAS",
          "EEX_PUBLIC": "EEX"}
#: What the board calls each kind of published price (short, then on demand).
KIND_WORDS = {"reference_index": "reference index", "daily_price": "daily price",
              "imbalance_price": "imbalance price"}
PUBLIC_QUOTE_PREFIX = "pub:"


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def product_name(point: PricePoint) -> str:
    """The observation store's product for a series (the board chart's ``historyProduct``)."""

    if point.tenor in (MONTH, QUARTER, CALENDAR_YEAR):
        if point.tenor == MONTH:
            return f"{point.hub} month-ahead"
        return f"{point.hub} {point.contract_label}"
    return f"{point.hub} {point.tenor}"


def per_mwh(point: PricePoint) -> tuple[float, str, str, float, str]:
    """``(value, currency, unit, native value, native unit)`` as the product stores prices."""

    if point.unit == "GBp/kWh":
        # 1 p/kWh = 10 GBP/MWh; the desk reads NBP in p/th, through the units authority.
        from eurogas_nexus.domain.market.units import convert_price

        gbp_mwh = point.value * 10.0
        return (round(gbp_mwh, 6), "GBP", "GBP/MWh",
                round(convert_price(gbp_mwh, "GBP/MWh", "GBp/th"), 4), "p/th")
    if point.unit == "EUR/MWh":
        return point.value, "EUR", "EUR/MWh", point.value, "EUR/MWh"
    raise ValueError(f"unit {point.unit!r} is not one the product stores")


def delivery_window(point: PricePoint) -> tuple[datetime, datetime]:
    """The delivery's UTC window: from the first gas day's start to the day after the last."""

    from eurogas_nexus.domain.market.gas_day import (
        EU_CAM_UTC_CALENDAR,
        UK_LEGACY_CALENDAR,
        gas_day_start_for_date,
    )

    calendar = UK_LEGACY_CALENDAR if point.hub == "NBP" else EU_CAM_UTC_CALENDAR
    try:
        return (gas_day_start_for_date(point.delivery_start, calendar),
                gas_day_start_for_date(point.delivery_end + timedelta(days=1), calendar))
    except (ValueError, KeyError):
        return (datetime.combine(point.delivery_start, time(5), tzinfo=UTC),
                datetime.combine(point.delivery_end + timedelta(days=1), time(5), tzinfo=UTC))


def observed_instant(point: PricePoint) -> datetime:
    """The instant a daily figure is filed under: its day, late afternoon UTC.

    The daily-close reads take the day from this instant, so a price for gas day D (or traded
    on day D) is D's close; the time is not a publication time and is not shown as one.
    """

    return datetime.combine(point.day, time(17, 0), tzinfo=UTC)


def _observation_id(family: str, point: PricePoint) -> str:
    key = f"{family}|{point.series}|{point.day.isoformat()}|{point.delivery_start.isoformat()}"
    return "pub-" + hashlib.sha256(key.encode()).hexdigest()[:40]


def store_points(session, points: list[PricePoint], *, family: str, publication_id: str,
                 publisher: str, consent_publisher: str | None, document_url: str,
                 now: datetime) -> dict[str, int]:
    """Keep each point once (by series and day); a changed value replaces the held one."""

    from eurogas_nexus.db.models import MarketObservationRecord

    now = _aware(now)
    wanted = {_observation_id(family, p): p for p in points}
    held = {}
    ids = list(wanted)
    for start in range(0, len(ids), 500):
        for row in session.query(MarketObservationRecord).filter(
                MarketObservationRecord.observation_id.in_(ids[start:start + 500])):
            held[row.observation_id] = row
    added = revised = 0
    for observation_id, point in wanted.items():
        value, currency, unit, native, native_unit = per_mwh(point)
        start_utc, end_utc = delivery_window(point)
        metadata = {
            "hub": point.hub,
            # The front month is stored as the daily closes call it ("month-ahead").
            "tenor": "month-ahead" if point.tenor == MONTH else point.tenor,
            "simulated": False,
            "settlement": False,
            "public_price": True,
            "price_kind": point.kind,
            "price_name": point.name,
            "price_day": point.day.isoformat(),
            "status": point.status,
            "contract": point.contract_label or None,
            "native_value": native,
            "native_unit": native_unit,
            "published_unit": point.unit,
            "published_value": point.value,
            "publication_id": publication_id,
            "publisher": publisher,
            "consent_publisher": consent_publisher,
            "fetched_at_utc": now.isoformat(),
            **({"extra": point.extra} if point.extra else {}),
        }
        row = held.get(observation_id)
        if row is None:
            session.add(MarketObservationRecord(
                observation_id=observation_id,
                market_venue=VENUES.get(family, family)[:32],
                product=product_name(point)[:32],
                price=value, unit=unit, currency=currency,
                period_start_utc=start_utc, period_end_utc=end_utc,
                observed_at_utc=observed_instant(point),
                source_system=family,
                source_reference=f"{publication_id}:{point.series}"[:128],
                source_record_id=point.day.isoformat(),
                freshness="daily", quality_score=1.0, research_only=False,
                metadata_json=metadata,
            ))
            added += 1
        elif abs(float(row.price) - value) > 1e-9 or (row.metadata_json or {}).get(
                "status") != point.status:
            previous = row.metadata_json or {}
            row.price = value
            row.metadata_json = metadata | {"revised_from": previous.get("published_value"),
                                            "revised_at_utc": now.isoformat()}
            revised += 1
    session.flush()
    quotes = _store_latest_quotes(session, points, family=family, publication_id=publication_id,
                                  publisher=publisher, consent_publisher=consent_publisher,
                                  document_url=document_url, now=now)
    return {"observations_added": added, "observations_revised": revised, "quotes": quotes}


#: Series that price a board row (imbalance prices price none; My gas day reads them).
def _board_series(point: PricePoint) -> bool:
    return point.kind != IMBALANCE and point.tenor in (WITHIN_DAY, DAY_AHEAD, MONTH, QUARTER,
                                                       CALENDAR_YEAR)


def _store_latest_quotes(session, points: list[PricePoint], *, family: str, publication_id: str,
                         publisher: str, consent_publisher: str | None, document_url: str,
                         now: datetime) -> int:
    from eurogas_nexus.db.models import MarketQuoteRecord

    latest: dict[str, PricePoint] = {}
    for point in points:
        if not _board_series(point):
            continue
        held = latest.get(point.series)
        if held is None or point.day > held.day:
            latest[point.series] = point
    count = 0
    for series, point in latest.items():
        quote_id = f"{PUBLIC_QUOTE_PREFIX}{series}"
        row = session.get(MarketQuoteRecord, quote_id)
        observed = observed_instant(point)
        if row is not None and _aware(row.observed_at_utc) > observed:
            continue  # a later figure is already held (a history read arrived after it)
        value, currency, unit, native, native_unit = per_mwh(point)
        start_utc, end_utc = delivery_window(point)
        product = point.contract_label or point.tenor
        previous = _previous_publication(session, family, point, start_utc)
        metadata = {
            "public_price": True,
            "price_kind": point.kind,
            "price_kind_words": KIND_WORDS.get(point.kind, point.kind),
            "price_name": point.name,
            "price_day": point.day.isoformat(),
            "delivery_start": point.delivery_start.isoformat(),
            "delivery_end": point.delivery_end.isoformat(),
            "status": point.status,
            "native_last": native,
            "native_unit_last": native_unit,
            "publication_id": publication_id,
            "publisher": publisher,
            "consent_publisher": consent_publisher,
            "document_url": document_url,
            "fetched_at_utc": now.isoformat(),
            "live": False,
            "previous_day": previous[1] if previous else None,
        }
        if row is None:
            row = MarketQuoteRecord(quote_id=quote_id)
            session.add(row)
        row.source_system = family
        row.source_record_id = point.day.isoformat()
        row.venue = VENUES.get(family, family)[:64]
        row.instrument_id = series[:128]
        row.hub = point.hub
        row.product = product.lower()[:64]
        row.delivery_start_utc = start_utc
        row.delivery_end_utc = end_utc
        row.bid_price = None
        row.ask_price = None
        row.last_price = value
        row.currency = currency
        row.unit = unit
        row.observed_at_utc = observed
        row.received_at_utc = now
        row.source_reference = f"{publication_id}:{series}"[:256]
        row.freshness = "daily"
        row.quality_score = 1.0
        row.simulated = False
        row.metadata_json = metadata
        # The publication before this one, same series and same delivery: the change on the
        # day is this figure against it (``close_day`` is its day), never against a quote.
        row.prior_settlement_price = previous[0] if previous else None
        count += 1
    session.flush()
    return count


def _previous_publication(session, family: str, point: PricePoint, start_utc: datetime
                          ) -> tuple[float, str] | None:
    """The newest stored figure of the same series and delivery before ``point``'s day."""

    from eurogas_nexus.db.models import MarketObservationRecord

    before = observed_instant(point)
    naive = session.get_bind().dialect.name == "sqlite"
    query = (session.query(MarketObservationRecord)
             .filter(MarketObservationRecord.source_system == family)
             .filter(MarketObservationRecord.product == product_name(point)[:32])
             .filter(MarketObservationRecord.observed_at_utc
                     < (before.replace(tzinfo=None) if naive else before))
             .order_by(MarketObservationRecord.observed_at_utc.desc()))
    for row in query.limit(10):
        meta = row.metadata_json or {}
        if point.tenor in (MONTH, QUARTER, CALENDAR_YEAR) and _aware(row.period_start_utc) != \
                start_utc:
            continue
        if meta.get("price_day"):
            return float(row.price), str(meta["price_day"])
    return None


def published_cash_out(session, hub: str, day: date) -> dict[str, Any] | None:
    """The newest published cash-out on or before ``day`` for ``hub``, per MWh.

    NBP: National Gas's SMP buy and sell against SAP; THE: the negative and positive imbalance
    prices against the VTP daily average. Returns the premium a short position pays and the
    discount a long one takes, with the gas day and the source, or ``None`` when none is held.
    """

    from eurogas_nexus.db.models import MarketObservationRecord

    hub = hub.upper()
    family = {"NBP": "NATIONAL_GAS_PRICES", "THE": "THE"}.get(hub)
    if family is None:
        return None
    since = datetime.combine(day - timedelta(days=10), time(0), tzinfo=UTC)
    until = datetime.combine(day + timedelta(days=1), time(0), tzinfo=UTC)
    if session.get_bind().dialect.name == "sqlite":
        since, until = since.replace(tzinfo=None), until.replace(tzinfo=None)
    rows = (session.query(MarketObservationRecord)
            .filter(MarketObservationRecord.source_system == family)
            .filter(MarketObservationRecord.observed_at_utc >= since)
            .filter(MarketObservationRecord.observed_at_utc < until).all())
    by_day: dict[str, dict[str, Any]] = {}
    for row in rows:
        meta = row.metadata_json or {}
        tenor = meta.get("tenor")
        if tenor not in (WITHIN_DAY, IMBALANCE_SHORT, IMBALANCE_LONG):
            continue
        by_day.setdefault(str(meta.get("price_day")), {})[tenor] = row
    for price_day in sorted(by_day, reverse=True):
        legs = by_day[price_day]
        if not all(t in legs for t in (WITHIN_DAY, IMBALANCE_SHORT, IMBALANCE_LONG)):
            continue
        reference = float(legs[WITHIN_DAY].price)
        short = float(legs[IMBALANCE_SHORT].price)
        long_ = float(legs[IMBALANCE_LONG].price)
        meta = legs[WITHIN_DAY].metadata_json or {}
        return {
            "hub": hub,
            "gas_day": price_day,
            "currency": legs[WITHIN_DAY].currency,
            "reference": round(reference, 4),
            "short_price": round(short, 4),
            "long_price": round(long_, 4),
            "short_premium": round(max(short - reference, 0.0), 4),
            "long_discount": round(max(reference - long_, 0.0), 4),
            "source_system": family,
            "publisher": meta.get("publisher"),
            "statuses": sorted({(legs[t].metadata_json or {}).get("status", "final")
                                for t in legs}),
            "names": [(legs[t].metadata_json or {}).get("price_name") for t in
                      (IMBALANCE_SHORT, WITHIN_DAY, IMBALANCE_LONG)],
        }
    return None


def public_price_quotes(session) -> list[dict[str, Any]]:
    """The board's public-price quotes (one per series), whatever else the quote store holds."""

    from eurogas_nexus.db.models import MarketQuoteRecord
    from eurogas_nexus.db.repositories.market_intelligence import _quote_dict

    rows = (session.query(MarketQuoteRecord)
            .filter(MarketQuoteRecord.quote_id.like(f"{PUBLIC_QUOTE_PREFIX}%")).all())
    return [_quote_dict(row) for row in rows]


__all__ = [
    "KIND_WORDS",
    "PUBLIC_QUOTE_PREFIX",
    "delivery_window",
    "observed_instant",
    "per_mwh",
    "product_name",
    "public_price_quotes",
    "published_cash_out",
    "store_points",
]
