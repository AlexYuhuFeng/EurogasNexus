"""US Energy Information Administration (EIA) open data: Henry Hub daily spot.

EIA data is a US government work in the public domain; the API needs a free key
(``EIA_API_KEY``). Henry Hub is the reference for US LNG export economics (HH-linked
FOB pricing plus liquefaction) against TTF, NBP and JKM.

Series ``RNGWHHD``: Henry Hub natural gas spot price, USD/MMBtu, daily, published with
about a one-business-day lag.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from urllib.parse import urlencode

EIA_API = "https://api.eia.gov/v2/natural-gas/pri/fut/data/"
HENRY_HUB_SPOT_SERIES = "RNGWHHD"
MAX_PAYLOAD_BYTES = 8 * 1024 * 1024


class EiaParseError(ValueError):
    """The response is not an EIA v2 data payload."""


@dataclass(frozen=True)
class EiaPrice:
    series: str
    day: date
    price: float
    unit: str

    def as_record(self, *, source_reference: str) -> dict[str, object]:
        start = datetime.combine(self.day, time.min, tzinfo=UTC)
        return {
            "observation_id": f"eia-{self.series.lower()}-{self.day.isoformat()}",
            "market_venue": "EIA",
            "product": "HH spot",
            "price": self.price,
            "unit": self.unit,
            "currency": "USD",
            "period_start_utc": start,
            "period_end_utc": start + timedelta(days=1),
            "observed_at_utc": datetime.combine(self.day, time(18), tzinfo=UTC),
            "source_system": "EIA",
            "source_reference": source_reference[:128],
            "source_record_id": f"{self.series}:{self.day.isoformat()}",
            "freshness": "end_of_day",
            "quality_score": 1.0,
            "research_only": True,
            "metadata_json": {"hub": "HH", "tenor": "spot", "commodity": "natural_gas"},
        }


def resolve_eia_key(environ: dict[str, str] | None = None) -> str | None:
    """The API key from ``EIA_API_KEY``, or ``None``."""

    env = os.environ if environ is None else environ
    key = str(env.get("EIA_API_KEY") or "").strip()
    return key or None


def request_url(api_key: str, start: date, series: str = HENRY_HUB_SPOT_SERIES) -> str:
    """The v2 query for one daily series from ``start``. The URL carries the key."""

    query = urlencode(
        [
            ("api_key", api_key),
            ("frequency", "daily"),
            ("data[0]", "value"),
            ("facets[series][]", series),
            ("start", start.isoformat()),
            ("sort[0][column]", "period"),
            ("sort[0][direction]", "asc"),
            ("length", "5000"),
        ]
    )
    return f"{EIA_API}?{query}"


def parse_prices(payload: bytes | str, series: str = HENRY_HUB_SPOT_SERIES) -> list[EiaPrice]:
    """Daily prices for ``series`` from a v2 response; empty values are skipped."""

    try:
        document = json.loads(payload)
        rows = document["response"]["data"]
    except (ValueError, KeyError, TypeError) as exc:
        raise EiaParseError("not an EIA v2 data response") from exc
    prices = []
    for row in rows:
        if row.get("series") not in (None, series) or row.get("value") in (None, ""):
            continue
        try:
            day = date.fromisoformat(str(row["period"])[:10])
            value = float(row["value"])
        except (KeyError, ValueError) as exc:
            raise EiaParseError(f"bad row {row!r}") from exc
        unit = str(row.get("units") or "$/MMBTU").upper().replace("$", "USD")
        prices.append(EiaPrice(series, day, value, "USD/MMBtu" if "MMBTU" in unit else unit))
    return prices
