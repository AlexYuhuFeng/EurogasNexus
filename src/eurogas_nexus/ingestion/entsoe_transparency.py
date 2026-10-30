"""ENTSO-E Transparency Platform: day-ahead prices, load and generation by fuel.

Parses the platform's XML documents into flat, typed power observations:

- ``Publication_MarketDocument`` type A44: day-ahead prices per bidding zone;
- ``GL_MarketDocument`` type A65: total load (process A16 realised, A01 day-ahead
  forecast);
- ``GL_MarketDocument`` type A75: actual generation per production type (B04 fossil gas,
  B16 solar, B18 wind offshore, B19 wind onshore).

Availability: an API response's ``createdDateTime`` is when the response was generated,
not when the value was first published, so a backfill would otherwise look as if all
history became known today. Each observation's ``published_at_utc`` is therefore the
earlier of that time and the publication deadline in the Transparency Regulation (EU)
543/2013: day-ahead prices and load forecasts by 12:00 Brussels time the day before
delivery, actual load and generation one hour after the period ends. Datasets treat this
as approximate availability. Curve type A03
(variable-sized blocks) repeats a value until the next position, as the platform defines.
Fetching is separate from parsing so the parser is tested against stored documents.
"""

from __future__ import annotations

import os
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

ENTSOE_API_URL = "https://web-api.tp.entsoe.eu/api"
ENTSOE_TOKEN_ENV = "ENTSOE_SECURITY_TOKEN"


def resolve_entsoe_token(environ: dict[str, str] | None = None) -> str | None:
    """The Transparency Platform token from ``ENTSOE_SECURITY_TOKEN``, or ``None``."""

    env = os.environ if environ is None else environ
    token = str(env.get("ENTSOE_SECURITY_TOKEN") or "").strip()
    return token or None

#: Bidding-zone EIC codes for the zones gas desks watch most.
BIDDING_ZONES: dict[str, str] = {
    "GB": "10YGB----------A",
    "NL": "10YNL----------L",
    "DE_LU": "10Y1001A1001A82H",
    "BE": "10YBE----------2",
    "FR": "10YFR-RTE------C",
    "AT": "10YAT-APG------L",
    "IT_NORD": "10Y1001A1001A73I",
    "ES": "10YES-REE------0",
}
ZONE_BY_EIC = {eic: zone for zone, eic in BIDDING_ZONES.items()}

PRODUCTION_TYPE_METRICS = {
    "B04": "gas_generation",
    "B16": "solar_generation",
    "B18": "wind_offshore_generation",
    "B19": "wind_onshore_generation",
}

_RESOLUTION = re.compile(r"^PT(\d+)M$")
_BRUSSELS = ZoneInfo("Europe/Brussels")


def regulatory_publication_deadline(
    metric: str, period_start: datetime, period_end: datetime
) -> datetime:
    """Latest time the Transparency Regulation allows this value to be published."""

    if metric in {"day_ahead_price", "load_forecast_da"}:
        delivery_day = period_start.astimezone(_BRUSSELS).date()
        noon_before = datetime.combine(delivery_day - timedelta(days=1), time(12), tzinfo=_BRUSSELS)
        return noon_before.astimezone(UTC)
    return period_end + timedelta(hours=1)


class EntsoeParseError(ValueError):
    """A document the parser cannot read as one of the supported types."""


@dataclass(frozen=True)
class PowerObservation:
    zone: str
    metric: str
    period_start_utc: datetime
    period_end_utc: datetime
    value: float
    unit: str
    published_at_utc: datetime
    source_reference: str
    process_type: str | None = None

    @property
    def observation_id(self) -> str:
        return (
            f"entsoe:{self.zone}:{self.metric}:{self.process_type or '-'}:"
            f"{self.period_start_utc:%Y%m%dT%H%M}"
        )


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _child(element: ET.Element, name: str) -> ET.Element | None:
    for child in element:
        if _local(child.tag) == name:
            return child
    return None


def _text(element: ET.Element, *path: str) -> str | None:
    node: ET.Element | None = element
    for name in path:
        node = _child(node, name) if node is not None else None
    return node.text.strip() if node is not None and node.text else None


def _timestamp(value: str) -> datetime:
    value = value.strip().replace("Z", "+00:00")
    if re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}\+00:00$", value):
        value = value.replace("+00:00", ":00+00:00")
    return datetime.fromisoformat(value).astimezone(UTC)


def _points(period: ET.Element, curve_type: str | None) -> list[tuple[datetime, datetime, float]]:
    start = _timestamp(_text(period, "timeInterval", "start") or "")
    end = _timestamp(_text(period, "timeInterval", "end") or "")
    match = _RESOLUTION.match(_text(period, "resolution") or "")
    if not match:
        raise EntsoeParseError(f"unsupported resolution {_text(period, 'resolution')!r}")
    step = timedelta(minutes=int(match.group(1)))
    slots = int((end - start) / step)
    values: dict[int, float] = {}
    for point in period:
        if _local(point.tag) != "Point":
            continue
        position = int(_text(point, "position") or 0)
        raw = _text(point, "price.amount") or _text(point, "quantity")
        if raw is None or not 1 <= position <= slots:
            continue
        values[position] = float(raw)
    rows = []
    last: float | None = None
    for position in range(1, slots + 1):
        if position in values:
            last = values[position]
        elif curve_type != "A03":
            continue  # A01: a missing position is missing, not repeated
        if last is None:
            continue
        slot_start = start + step * (position - 1)
        rows.append((slot_start, slot_start + step, last))
    return rows


def parse_document(xml_bytes: bytes, *, source_reference: str = "entsoe") -> list[PowerObservation]:
    """Parse one ENTSO-E document into power observations (empty for an acknowledgement).

    Raises:
        EntsoeParseError: For an unsupported document type or malformed periods.
    """

    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise EntsoeParseError(f"not XML: {exc}") from exc
    kind = _local(root.tag)
    if kind == "Acknowledgement_MarketDocument":
        return []  # "No matching data found" and similar: nothing to store
    doc_type = _text(root, "type")
    if doc_type not in {"A44", "A65", "A75"}:
        raise EntsoeParseError(f"unsupported document type {doc_type!r} ({kind})")
    created = _timestamp(_text(root, "createdDateTime") or "")
    process_type = _text(root, "process.processType")
    observations: list[PowerObservation] = []
    for series in root:
        if _local(series.tag) != "TimeSeries":
            continue
        curve_type = _text(series, "curveType")
        if doc_type == "A44":
            zone_eic = _text(series, "in_Domain.mRID")
            metric = "day_ahead_price"
            unit = f"{_text(series, 'currency_Unit.name') or 'EUR'}/MWh"
        elif doc_type == "A65":
            zone_eic = _text(series, "outBiddingZone_Domain.mRID")
            metric = "load_forecast_da" if process_type == "A01" else "load_actual"
            unit = "MW"
        elif doc_type == "A75":
            if _text(series, "outBiddingZone_Domain.mRID"):
                continue  # consumption by storage units, not generation
            zone_eic = _text(series, "inBiddingZone_Domain.mRID")
            metric = PRODUCTION_TYPE_METRICS.get(_text(series, "MktPSRType", "psrType") or "")
            if metric is None:
                continue
            unit = "MW"
        else:
            raise EntsoeParseError(f"unsupported document type {doc_type!r} ({kind})")
        zone = ZONE_BY_EIC.get(zone_eic or "", zone_eic or "unknown")
        for period in series:
            if _local(period.tag) != "Period":
                continue
            for start, end, value in _points(period, curve_type):
                observations.append(
                    PowerObservation(
                        zone=zone,
                        metric=metric,
                        period_start_utc=start,
                        period_end_utc=end,
                        value=value,
                        unit=unit,
                        published_at_utc=min(
                            created, regulatory_publication_deadline(metric, start, end)
                        ),
                        source_reference=source_reference,
                        process_type=process_type,
                    )
                )
    return observations


def request_url(token: str, document_type: str, zone: str, start: datetime, end: datetime) -> str:
    """The Transparency Platform query for one document type, zone and UTC window."""

    eic = BIDDING_ZONES[zone]
    params = {
        "securityToken": token,
        "documentType": document_type,
        "periodStart": start.astimezone(UTC).strftime("%Y%m%d%H%M"),
        "periodEnd": end.astimezone(UTC).strftime("%Y%m%d%H%M"),
    }
    if document_type == "A44":
        params.update({"in_Domain": eic, "out_Domain": eic})
    elif document_type == "A65":
        params.update({"processType": "A16", "outBiddingZone_Domain": eic})
    elif document_type == "A75":
        params.update({"processType": "A16", "in_Domain": eic})
    else:
        raise EntsoeParseError(f"unsupported document type {document_type!r}")
    return f"{ENTSOE_API_URL}?{urllib.parse.urlencode(params)}"


def fetch_document(url: str, *, timeout: float = 30.0) -> bytes:
    """Fetch one document. The URL carries the token, so it is never logged."""

    request = urllib.request.Request(url, headers={"Accept": "application/xml"})
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        return response.read()
