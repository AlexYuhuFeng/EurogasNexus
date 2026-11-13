"""Great Britain power from the Elexon Insights Solution (BMRS), the GB market's own data.

ENTSO-E no longer carries Great Britain (the first live run on 2026-11-12 returned nothing
for the GB zone), so the gas-for-power view had no GB side. Elexon publishes the GB
system's half-hourly data openly, without a key:

- ``FUELHH``: generation by fuel. CCGT and OCGT together are gas-fired generation; ``WIND``
  is transmission-metered wind, onshore and offshore together.
- demand outturn: ``INDO``, initial national demand outturn.
- ``MID``: the market index price (APX), a volume-weighted within-day reference. It is not
  the day-ahead auction price and is stored under its own metric so nothing mistakes it.

Rows are :class:`PowerObservation` for zone ``GB`` with source ``elexon``, stored beside the
ENTSO-E zones. Solar is not in ``FUELHH`` (it is embedded generation); it is left absent,
never zero. Parsing is pure; :func:`fetch_json` is the only network call.

Licence: BMRS data is published under the BMRS Data Licence, which permits reuse including
commercial use with the attribution "Contains BMRS data © Elexon Limited copyright and
database right". See ``docs/legal/``.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from typing import Any

from eurogas_nexus.ingestion.entsoe_transparency import PowerObservation

ELEXON_API_URL = "https://data.elexon.co.uk/bmrs/api/v1"
ZONE = "GB"
SOURCE = "elexon"
ATTRIBUTION = "Contains BMRS data © Elexon Limited copyright and database right"
SETTLEMENT_PERIOD = timedelta(minutes=30)
#: FUELHH fuel types that are gas-fired generation.
GAS_FUELS = frozenset({"CCGT", "OCGT"})
MARKET_INDEX_PROVIDER = "APXMIDP"


class ElexonParseError(ValueError):
    """A response that is not the documented shape."""


def _instant(value: object) -> datetime:
    try:
        moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ElexonParseError(f"not a timestamp: {value!r}") from exc
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def _rows(payload: Any) -> list[dict[str, Any]]:
    data = payload.get("data") if isinstance(payload, dict) else payload
    if not isinstance(data, list):
        raise ElexonParseError("expected a list of rows")
    return [row for row in data if isinstance(row, dict)]


def _observation(metric: str, start: datetime, value: float, unit: str, published: datetime,
                 reference: str) -> PowerObservation:
    return PowerObservation(
        zone=ZONE,
        metric=metric,
        period_start_utc=start,
        period_end_utc=start + SETTLEMENT_PERIOD,
        value=float(value),
        unit=unit,
        published_at_utc=published,
        source_reference=reference,
        source=SOURCE,
    )


def parse_generation(payload: Any, *, reference: str = "elexon:FUELHH") -> list[PowerObservation]:
    """``FUELHH`` rows as gas and wind generation per settlement period (MW)."""

    gas: dict[datetime, float] = defaultdict(float)
    published: dict[datetime, datetime] = {}
    observations = []
    for row in _rows(payload):
        fuel, value = str(row.get("fuelType") or ""), row.get("generation")
        if value is None or "startTime" not in row:
            continue
        start = _instant(row["startTime"])
        stamp = _instant(row.get("publishTime") or row["startTime"])
        if fuel in GAS_FUELS:
            gas[start] += float(value)
            published[start] = max(published.get(start, stamp), stamp)
        elif fuel == "WIND":
            observations.append(
                _observation("wind_generation", start, value, "MW", stamp, reference)
            )
    observations += [
        _observation("gas_generation", start, total, "MW", published[start], reference)
        for start, total in gas.items()
    ]
    return sorted(observations, key=lambda item: (item.metric, item.period_start_utc))


def parse_demand(payload: Any, *, reference: str = "elexon:INDO") -> list[PowerObservation]:
    """Initial national demand outturn per settlement period (MW)."""

    return [
        _observation(
            "load_actual",
            _instant(row["startTime"]),
            row["initialDemandOutturn"],
            "MW",
            _instant(row.get("publishTime") or row["startTime"]),
            reference,
        )
        for row in _rows(payload)
        if row.get("initialDemandOutturn") is not None and "startTime" in row
    ]


def parse_market_index(payload: Any, *, reference: str = "elexon:MID") -> list[PowerObservation]:
    """The APX market index price per settlement period (GBP/MWh), where it traded."""

    observations = []
    for row in _rows(payload):
        if row.get("dataProvider") != MARKET_INDEX_PROVIDER or row.get("price") is None:
            continue
        if not float(row.get("volume") or 0.0):
            continue  # no trades in the period: the published price of 0 is not a price
        start = _instant(row["startTime"])
        # The index for a period is known once the period has traded.
        observations.append(
            _observation("market_index_price", start, row["price"], "GBP/MWh",
                         start + SETTLEMENT_PERIOD, reference)
        )
    return observations


def request_urls(first: date, last: date) -> dict[str, str]:
    """The three reads for settlement dates ``first`` to ``last`` inclusive."""

    def url(path: str, **params: str) -> str:
        return f"{ELEXON_API_URL}{path}?{urllib.parse.urlencode({**params, 'format': 'json'})}"

    day_from, day_to = first.isoformat(), last.isoformat()
    return {
        "generation": url("/datasets/FUELHH", settlementDateFrom=day_from,
                          settlementDateTo=day_to),
        "demand": url("/demand/outturn", settlementDateFrom=day_from, settlementDateTo=day_to),
        "market_index": url(
            "/balancing/pricing/market-index",
            **{
                "from": f"{day_from}T00:00Z",
                "to": f"{(last + timedelta(days=1)).isoformat()}T00:00Z",
                "dataProviders": MARKET_INDEX_PROVIDER,
            },
        ),
    }


PARSERS = {
    "generation": parse_generation,
    "demand": parse_demand,
    "market_index": parse_market_index,
}


def fetch_json(url: str, *, timeout: float = 45.0) -> Any:
    """Fetch one public Elexon response (no credential is sent)."""

    request = urllib.request.Request(  # noqa: S310 - fixed https host above
        url, headers={"Accept": "application/json", "User-Agent": "EurogasNexus elexon"}
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        return json.loads(response.read())
