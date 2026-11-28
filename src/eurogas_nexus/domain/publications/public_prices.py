"""Read the public price publications fetched under written consent (owner, 2026-11-28).

Pure parsers, one per publisher layout, each returning :class:`PricePoint` rows: what the price
is, the day it is for, the delivery it prices, its value in the publisher's own unit and
whether the publisher calls it final. Nothing here fetches, stores or converts beyond the
publisher's own statement; a layout the parser does not recognise raises
:class:`PricesUncertain` (the held record stays and a person is asked), never a guess.

=================  =====================================================  ===================
Publisher          What is read                                           Board row
=================  =====================================================  ===================
Trading Hub        DataExport API ``PricesEnergyImbalance``: the VTP      THE WD (daily
Europe             daily average price and the positive and negative      average, a
                   imbalance prices per gas day, EUR/MWh                  reference index)
National Gas       Gas Operational Data API ``/publications/gasday``:     NBP WD (SAP, a
                   SAP (PUBOB603), SMP buy (PUBOB604), SMP sell           reference index)
                   (PUBOB605), Actual Day, p/kWh
MIBGAS             Yearly ``MIBGAS_Data_<year>.csv``: the MIBGAS daily    PVB DA, M1 (month
                   price per product and trading day (D+1, month-ahead,   ahead), Q1 (Q+1),
                   Q+1, Y+1), EUR/MWh                                     Cal (Y+1)
EEX                ``TTF_NGP_60_Days.csv`` (gas market transparency):     TTF WD (neutral
                   the TTF neutral gas price per delivery day, EUR/MWh    gas price index)
=================  =====================================================  ===================

None of these is a live bid or offer: each is a published daily figure with a date, and the
board says so. Imbalance (cash-out) prices price no board contract; they go to My gas day.

Import-safe: no database, web or network import.

经书面同意获取的公开价格：逐个发布方的纯解析器；版式不符时不猜测，保留原记录并请人确认。
"""

from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from xml.etree import ElementTree

#: What a price is, in the board's words.
REFERENCE_INDEX = "reference_index"
DAILY_PRICE = "daily_price"
IMBALANCE = "imbalance_price"
PRICE_KINDS = (REFERENCE_INDEX, DAILY_PRICE, IMBALANCE)

#: Tenors the product stores (the observation store's ``metadata_json.tenor``).
WITHIN_DAY = "within-day"
DAY_AHEAD = "day-ahead"
MONTH = "month"
QUARTER = "quarter"
CALENDAR_YEAR = "calendar-year"
IMBALANCE_SHORT = "imbalance-short"
IMBALANCE_LONG = "imbalance-long"

_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


class PricesUncertain(ValueError):
    """The document is not in the layout the parser was written for: nothing is guessed."""


@dataclass(frozen=True)
class PricePoint:
    """One published price: the day it is for, what it prices and its value as published."""

    #: Stable series id within its publication (``the:vtp-daily-average``).
    series: str
    hub: str
    tenor: str
    kind: str
    #: The day the publisher dates the figure by: the gas day (THE, National Gas, EEX) or the
    #: trading day (MIBGAS).
    day: date
    delivery_start: date
    #: The last gas day delivered (inclusive).
    delivery_end: date
    value: float
    #: The publisher's own unit (``EUR/MWh``, ``GBp/kWh``).
    unit: str
    #: ``final`` or ``preliminary`` as the publisher states or implies it.
    status: str = "final"
    #: What the publisher calls it, for the title on demand.
    name: str = ""
    extra: dict = field(default_factory=dict)

    @property
    def contract_label(self) -> str:
        """The execution screen's name for the delivery (``Dec-26``, ``Q1-27``, ``Cal-27``)."""

        yy = f"{self.delivery_start.year % 100:02d}"
        if self.tenor == MONTH:
            return f"{_MONTHS[self.delivery_start.month - 1]}-{yy}"
        if self.tenor == QUARTER:
            return f"Q{(self.delivery_start.month - 1) // 3 + 1}-{yy}"
        if self.tenor == CALENDAR_YEAR:
            return f"Cal-{yy}"
        return ""

    def to_json(self) -> dict:
        return {
            "series": self.series, "hub": self.hub, "tenor": self.tenor, "kind": self.kind,
            "day": self.day.isoformat(), "delivery_start": self.delivery_start.isoformat(),
            "delivery_end": self.delivery_end.isoformat(), "value": self.value,
            "unit": self.unit, "status": self.status, "name": self.name,
            "contract": self.contract_label, **({"extra": self.extra} if self.extra else {}),
        }


@dataclass(frozen=True)
class PriceRecord:
    """What one check read: the points and a short summary kept on the watched record."""

    points: tuple[PricePoint, ...]

    def to_json(self) -> dict:
        latest: dict[str, dict] = {}
        for point in self.points:
            held = latest.get(point.series)
            if held is None or point.day.isoformat() > held["day"]:
                latest[point.series] = point.to_json()
        days = sorted(p.day for p in self.points)
        return {
            "points": len(self.points),
            "first_day": days[0].isoformat() if days else None,
            "last_day": days[-1].isoformat() if days else None,
            "latest": dict(sorted(latest.items())),
        }


def _number(text: str | None, *, what: str) -> float | None:
    if text is None:
        return None
    value = text.strip()
    if not value:
        return None
    if not re.fullmatch(r"[+-]?(?:\d+(?:\.\d+)?|\.\d+)", value):
        raise PricesUncertain(f"{what}: {value!r} is not a plain decimal")
    return float(value)


# --------------------------------------------------------------------- Trading Hub Europe

_THE_ROOT = "PricesEnergyImbalance"
_THE_FIELDS = {
    "Gasday", "PositiveEnergyImbalancePrice", "NegativeEnergyImbalancePrice",
    "VTPDailyAveragePrice", "VTPDailyAveragePriceSmallAdjPlus",
    "VTPDailyAveragePriceSmallAdjMinus", "MarginalPriceSystemBuy", "MarginalPriceSystemSell",
    "Unit",
}
_XSI_NIL = "{http://www.w3.org/2001/XMLSchema-instance}nil"


def parse_the_imbalance(data: bytes, *, today: date) -> PriceRecord:
    """THE's ``PricesEnergyImbalance`` export (DataExport API manual, section 12.31).

    The previous and the current gas day are preliminary (manual section 4.4); older days are
    closed. The positive imbalance price is what a long balancing group is paid, the negative
    one what a short group pays.
    """

    text = data.decode("utf-8-sig", "replace").lstrip()
    if "<!DOCTYPE" in text[:500].upper():
        raise PricesUncertain("THE export declares a document type")
    try:
        root = ElementTree.fromstring(text)
    except ElementTree.ParseError as exc:
        raise PricesUncertain(f"THE export is not XML: {exc}") from exc
    if root.tag != _THE_ROOT:
        raise PricesUncertain(f"THE export root is {root.tag!r}, not {_THE_ROOT}")
    points: list[PricePoint] = []
    for entry in root:
        if entry.tag != _THE_ROOT:
            raise PricesUncertain(f"unexpected element {entry.tag!r} in THE export")
        values = {child.tag: (None if child.get(_XSI_NIL) == "true" else (child.text or ""))
                  for child in entry}
        unknown = set(values) - _THE_FIELDS
        if unknown or "Gasday" not in values:
            raise PricesUncertain(f"THE export fields changed: {sorted(unknown) or 'no Gasday'}")
        if (values.get("Unit") or "").strip() != "EUR/MWh":
            raise PricesUncertain(f"THE export unit is {values.get('Unit')!r}, not EUR/MWh")
        try:
            day = date.fromisoformat((values["Gasday"] or "").strip())
        except ValueError as exc:
            raise PricesUncertain(f"THE gas day {values['Gasday']!r}") from exc
        status = "preliminary" if day >= today - timedelta(days=1) else "final"
        for series, tag, tenor, kind, name in (
            ("the:vtp-daily-average", "VTPDailyAveragePrice", WITHIN_DAY, REFERENCE_INDEX,
             "THE VTP daily average price"),
            ("the:imbalance-negative", "NegativeEnergyImbalancePrice", IMBALANCE_SHORT,
             IMBALANCE, "THE negative imbalance price (short balancing groups pay)"),
            ("the:imbalance-positive", "PositiveEnergyImbalancePrice", IMBALANCE_LONG,
             IMBALANCE, "THE positive imbalance price (long balancing groups are paid)"),
        ):
            value = _number(values.get(tag), what=tag)
            if value is None:
                continue
            points.append(PricePoint(series=series, hub="THE", tenor=tenor, kind=kind, day=day,
                                     delivery_start=day, delivery_end=day, value=value,
                                     unit="EUR/MWh", status=status, name=name))
    if not points:
        raise PricesUncertain("THE export carries no price")
    return PriceRecord(tuple(points))


# ---------------------------------------------------------------------------- National Gas

NATIONAL_GAS_ITEMS = {
    "PUBOB603": ("ng:sap", WITHIN_DAY, REFERENCE_INDEX, "SAP, Actual Day"),
    "PUBOB604": ("ng:smp-buy", IMBALANCE_SHORT, IMBALANCE, "SMP Buy, Actual Day"),
    "PUBOB605": ("ng:smp-sell", IMBALANCE_LONG, IMBALANCE, "SMP Sell, Actual Day"),
}


def parse_national_gas(data: bytes) -> PriceRecord:
    """The ``/publications/gasday`` answer for the three Actual Day price items (p/kWh).

    ``qualityIndicator`` is kept as published; a value National Gas substituted is kept and
    marked. A gas day is final once published (the items are "Actual Day", 12:00 D+1).
    """

    try:
        body = json.loads(data.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PricesUncertain(f"National Gas answer is not JSON: {exc}") from exc
    if not isinstance(body, list):
        raise PricesUncertain("National Gas answer is not a list of publications")
    points: list[PricePoint] = []
    for item in body:
        if not isinstance(item, dict):
            raise PricesUncertain("National Gas publication is not an object")
        known = NATIONAL_GAS_ITEMS.get(str(item.get("publicationId")))
        if known is None:
            continue
        series, tenor, kind, name = known
        if str(item.get("publicationName") or "").strip() != name:
            raise PricesUncertain(f"{item.get('publicationId')} is now named "
                                  f"{item.get('publicationName')!r}, not {name!r}")
        for row in item.get("publications") or []:
            try:
                day = date.fromisoformat(str(row["applicableFor"])[:10])
            except (KeyError, ValueError) as exc:
                raise PricesUncertain("National Gas row without a gas day") from exc
            value = _number(str(row.get("value") or ""), what=name)
            if value is None:
                continue
            points.append(PricePoint(
                series=series, hub="NBP", tenor=tenor, kind=kind, day=day, delivery_start=day,
                delivery_end=day, value=value, unit="GBp/kWh", status="final",
                name=f"National Gas {name}",
                extra={"quality": str(row.get("qualityIndicator") or ""),
                       "substituted": str(row.get("substituted") or "") == "Y",
                       "published_at": str(row.get("applicableAt") or "")},
            ))
    return PriceRecord(tuple(points))


# --------------------------------------------------------------------------------- MIBGAS

MIBGAS_HEADER = ("Trading day", "Product", "Place of delivery", "Area", "First Day Delivery",
                 "Last Day Delivery", "MIBGAS Daily Price [EUR/MWh]")
#: The products the board prices, by MIBGAS code: (series, tenor).
MIBGAS_PRODUCTS = {
    "GDAES_D+1": ("mibgas:pvb-da", DAY_AHEAD),
    "GMAES": ("mibgas:pvb-ma", MONTH),
    "GQES_Q+1": ("mibgas:pvb-q1", QUARTER),
    "GYES_Y+1": ("mibgas:pvb-y1", CALENDAR_YEAR),
}


def _dmy(value: str) -> date:
    match = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})", value.strip())
    if not match:
        raise PricesUncertain(f"MIBGAS date {value!r} is not DD/MM/YYYY")
    day, month, year = (int(g) for g in match.groups())
    return date(year, month, day)


def parse_mibgas(data: bytes) -> PriceRecord:
    """A yearly ``MIBGAS_Data_<year>.csv``: an issue line, then the daily price table.

    Only the PVB products the board prices are read; a row with no price (the session has not
    closed) is skipped. The MIBGAS daily price is MIBGAS's published price for the product on
    that trading day, not a bid or offer.
    """

    text = data.decode("utf-8-sig", "replace")
    if text.lstrip().startswith("<"):
        raise PricesUncertain("MIBGAS answered with a page, not the CSV")
    lines = [line for line in text.splitlines() if line.strip()]
    header_at = next((i for i, line in enumerate(lines[:5]) if line.startswith("Trading day;")),
                     None)
    if header_at is None:
        raise PricesUncertain("MIBGAS CSV has no 'Trading day' header")
    reader = csv.reader(io.StringIO("\n".join(lines[header_at:])), delimiter=";")
    header = tuple(cell.strip() for cell in next(reader) if cell.strip())
    if header != MIBGAS_HEADER:
        raise PricesUncertain(f"MIBGAS CSV header changed: {header}")
    points: list[PricePoint] = []
    for row in reader:
        cells = [cell.strip() for cell in row]
        if len(cells) < 7 or not cells[0]:
            continue
        known = MIBGAS_PRODUCTS.get(cells[1])
        if known is None or cells[2] != "PVB" or cells[3] != "ES":
            continue
        value = _number(cells[6], what=f"MIBGAS {cells[1]}")
        if value is None:
            continue
        series, tenor = known
        start, end = _dmy(cells[4]), _dmy(cells[5])
        points.append(PricePoint(
            series=series, hub="PVB", tenor=tenor, kind=DAILY_PRICE, day=_dmy(cells[0]),
            delivery_start=start, delivery_end=end, value=value, unit="EUR/MWh",
            status="final", name=f"MIBGAS daily price {cells[1]}",
        ))
    return PriceRecord(tuple(points))


# ------------------------------------------------------------------------------------ EEX

EEX_NGP_HEADER = ("Index name", "Delivery date", "Index Value (€/MWh)", "Index Volume (MWh)",
                  "Number of trades")


def parse_eex_ngp(data: bytes, *, hub: str = "TTF") -> PriceRecord:
    """EEX's ``<HUB>_NGP_60_Days.csv``: the neutral gas price per delivery day.

    The neutral gas price is EEX's volume-weighted index of the day's exchange trades for
    delivery on that gas day: a reference index, final once the delivery day is over.
    """

    text = data.decode("utf-8-sig", "replace")
    if text.lstrip().startswith("<"):
        raise PricesUncertain("EEX answered with a page, not the CSV")
    reader = csv.reader(io.StringIO(text), delimiter=";")
    try:
        header = tuple(cell.strip() for cell in next(reader) if cell.strip())
    except StopIteration as exc:
        raise PricesUncertain("EEX NGP file is empty") from exc
    if header != EEX_NGP_HEADER:
        raise PricesUncertain(f"EEX NGP header changed: {header}")
    points: list[PricePoint] = []
    for row in reader:
        cells = [cell.strip() for cell in row]
        if len(cells) < 5 or not cells[0]:
            continue
        if not cells[0].upper().startswith(f"{hub} NEUTRAL GAS PRICE"):
            raise PricesUncertain(f"EEX NGP row names {cells[0]!r}, not {hub}")
        try:
            day = date.fromisoformat(cells[1])
        except ValueError as exc:
            raise PricesUncertain(f"EEX NGP delivery date {cells[1]!r}") from exc
        value = _number(cells[2], what="EEX NGP index value")
        if value is None:
            continue
        volume = _number(cells[3], what="EEX NGP volume")
        trades = _number(cells[4], what="EEX NGP trades")
        points.append(PricePoint(
            series=f"eex:{hub.lower()}-ngp", hub=hub, tenor=WITHIN_DAY, kind=REFERENCE_INDEX,
            day=day, delivery_start=day, delivery_end=day, value=value, unit="EUR/MWh",
            status="final", name=f"EEX {hub} neutral gas price",
            extra={"volume_mwh": volume, "trades": None if trades is None else int(trades)},
        ))
    if not points:
        raise PricesUncertain("EEX NGP file carries no index value")
    return PriceRecord(tuple(points))


__all__ = [
    "CALENDAR_YEAR",
    "DAILY_PRICE",
    "DAY_AHEAD",
    "IMBALANCE",
    "IMBALANCE_LONG",
    "IMBALANCE_SHORT",
    "MIBGAS_PRODUCTS",
    "MONTH",
    "NATIONAL_GAS_ITEMS",
    "PRICE_KINDS",
    "QUARTER",
    "REFERENCE_INDEX",
    "WITHIN_DAY",
    "PricePoint",
    "PriceRecord",
    "PricesUncertain",
    "parse_eex_ngp",
    "parse_mibgas",
    "parse_national_gas",
    "parse_the_imbalance",
]
