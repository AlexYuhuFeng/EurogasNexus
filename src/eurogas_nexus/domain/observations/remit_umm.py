"""REMIT urgent market messages (UMMs) for gas: parse an inside-information export.

Under REMIT Article 4, operators publish unavailability of gas production, storage, LNG and
transmission facilities on inside-information platforms (EEX Transparency, GIE IIP,
Gassco UMM, Nord Pool and others) in the fields ACER's Manual of Procedures defines. The
operator exports messages from the platform they use as JSON or CSV and imports them; this
module reads either and keeps ACER's field meanings.

A message is identified by ``message_id`` and revised by ``version``: a later version
replaces an earlier one, and ``Dismissed`` withdraws the event. Capacity stays in the unit
the message states (mcm/d, MSm3/d, GWh/d, kWh/h...). The daily figures
(``unavailable_mcm_d``, ``unavailable_gwh_d``) come from one function, ``daily_figure``,
through the unit authority (``domain/ontology/quantity.py``), never across energy and
volume (no calorific value is assumed):

- a rate per day converts directly;
- a rate per hour is multiplied by the hours of the gas day (23, 24 or 25 at the clock
  changes, ``domain/market/gas_day.py``): the gas day containing the event start when
  stored, the current gas day for a live event when read;
- an energy or volume with no rate (GWh, TWh) is not a daily rate. For storage and LNG
  it is working gas volume (live: Gas Storage Denmark technical 8,590 GWh, its working
  volume), so no daily figure is derived; for other assets with a known duration a daily
  average over the event is derived and labelled ``event_average``;
- a figure whose technical (or unavailable) capacity would exceed
  ``MAX_FACILITY_GWH_D`` per day for one facility is refused as a unit error (live:
  EPE-H 469.2 "GWh/h", 11 TWh/d).

Anything not converted keeps its unit, says why (``daily_basis``) and is counted by
``outage_unit_summary``.
"""

from __future__ import annotations

import csv
import io
import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

from eurogas_nexus.domain.market.gas_day import gas_day_interval_utc
from eurogas_nexus.domain.ontology.quantity import Dimension, UnitError, convert
from eurogas_nexus.domain.ontology.quantity import unit as quantity_unit

ASSET_TYPES = ("production", "storage", "lng", "transmission", "consumption", "other")
EVENT_STATUSES = ("active", "inactive", "dismissed")
#: Statuses whose latest version ends the event (``current_messages``).
ENDED_STATUSES = frozenset({"inactive", "dismissed"})


class UmmParseError(ValueError):
    """The export cannot be read as REMIT gas UMMs."""


@dataclass(frozen=True)
class UmmMessage:
    message_id: str
    version: int
    published_at_utc: datetime
    event_status: str  # active, inactive, dismissed
    unavailability_type: str  # planned, unplanned, ""
    event_start_utc: datetime
    event_stop_utc: datetime | None
    asset_name: str
    asset_eic: str
    asset_type: str
    balancing_zone: str
    direction: str
    unit: str
    technical_capacity: float | None
    available_capacity: float | None
    unavailable_capacity: float | None
    unavailable_mcm_d: float | None
    unavailable_gwh_d: float | None
    reason: str
    market_participant: str
    remarks: str
    source_reference: str

    @property
    def record_id(self) -> str:
        return f"{self.message_id}:{self.version}"[:96]

    def as_record(self) -> dict[str, object]:
        record = asdict(self)
        record["record_id"] = self.record_id
        return record


# ACER field names as the platforms spell them, mapped to ours (compared without case,
# spaces, underscores or hyphens).
_ALIASES: dict[str, tuple[str, ...]] = {
    "message_id": ("messageid", "ummid", "id", "mrid"),
    "version": ("version", "messageversion", "revisionnumber"),
    "published_at": ("publicationdatetime", "publicationdate", "published", "publishedat"),
    "event_status": ("eventstatus", "status"),
    "unavailability_type": ("unavailabilitytype", "typeofunavailability", "type"),
    "event_start": ("eventstart", "start", "eventstartdatetime", "startdate"),
    "event_stop": ("eventstop", "stop", "end", "eventstopdatetime", "enddate", "eventend"),
    "asset_name": ("affectedassetname", "assetname", "affectedasset", "facility", "unitname"),
    "asset_eic": ("affectedasseteic", "affectedassetidentifier", "asseteic", "eic", "eiccode"),
    "asset_type": ("affectedassettype", "assettype", "facilitytype"),
    "balancing_zone": ("balancingzone", "balancingzones", "biddingzone", "zone", "marketarea"),
    "direction": ("direction", "flowdirection"),
    "unit": ("unitmeasure", "unitofmeasure", "unit", "uom"),
    "technical_capacity": ("technicalcapacity", "installedcapacity"),
    "available_capacity": ("availablecapacity",),
    "unavailable_capacity": ("unavailablecapacity", "unavailablevolume"),
    "reason": ("unavailabilityreason", "reason", "reasonforunavailability"),
    "market_participant": ("marketparticipant", "marketparticipantname", "publisher", "operator"),
    "remarks": ("remarks", "comment", "comments", "description"),
}

# Platform spellings of volume units, as the unit authority's codes.  MSm3 (standard
# cubic metres) is read as mcm, as before: no reference-condition correction is applied.
_VOLUME_ALIASES = {"mm3": "mcm", "msm3": "mcm", "mscm": "mcm", "mcm": "mcm", "sm3": "m3",
                   "m3": "m3", "bcm": "bcm"}
_PER_DAY = {"d", "day", "gd", "gasday"}
_PER_HOUR = {"h", "hr", "hour"}
# One facility above this per day is a unit error, not an outage (the largest single
# gas facilities in Europe, Troll and the biggest storage sites, are about 1.3 TWh/d).
MAX_FACILITY_GWH_D = 2_000.0
MAX_FACILITY_MCM_D = 200.0
_WORKING_VOLUME_ASSETS = {"storage", "lng"}


@dataclass(frozen=True)
class DailyFigure:
    """The daily figure of a message's unavailable capacity, or why there is none.

    ``basis``: ``per_day``, ``per_hour_x_<n>h`` (hourly rate times the gas day's
    hours), ``event_average`` (an energy over a known event, averaged per 24 hours),
    or ``unconverted:<reason>``.
    """

    gwh_d: float | None
    mcm_d: float | None
    basis: str
    gwh_h: float | None = None
    total_gwh: float | None = None

    @property
    def converted(self) -> bool:
        return self.gwh_d is not None or self.mcm_d is not None


def _split_unit(text: str) -> tuple[str, Dimension, str | None] | None:
    """``(authority code, dimension, per)`` with per ``d``, ``h`` or None (no rate)."""

    compact = re.sub(r"\s", "", text or "").casefold()
    if not compact:
        return None
    numerator, _, per = compact.partition("/")
    code = _VOLUME_ALIASES.get(numerator, numerator)
    try:
        found = quantity_unit(code)
    except UnitError:
        return None
    if found.dimension not in (Dimension.ENERGY, Dimension.VOLUME):
        return None
    if not per:
        return found.code, found.dimension, None
    if per in _PER_DAY:
        return found.code, found.dimension, "d"
    if per in _PER_HOUR:
        return found.code, found.dimension, "h"
    return None


def gas_day_hours(at: datetime) -> float:
    """Hours of the gas day containing ``at`` (23, 24 or 25)."""

    start, end = gas_day_interval_utc(at)
    return (end - start).total_seconds() / 3600


def daily_figure(
    unit_text: str,
    unavailable: float | None,
    *,
    technical: float | None = None,
    asset_type: str = "",
    start: datetime | None = None,
    stop: datetime | None = None,
    at: datetime | None = None,
) -> DailyFigure:
    """The one conversion of a message's unavailable capacity to a daily figure.

    ``at`` picks the gas day whose length applies to an hourly rate (default: the
    event start).
    """

    if unavailable is None:
        return DailyFigure(None, None, "unconverted:no_unavailable_capacity")
    parsed = _split_unit(unit_text)
    if parsed is None:
        return DailyFigure(None, None, f"unconverted:unknown_unit:{unit_text or '-'}")
    code, dimension, per = parsed
    target = "GWh" if dimension is Dimension.ENERGY else "mcm"
    bound = MAX_FACILITY_GWH_D if dimension is Dimension.ENERGY else MAX_FACILITY_MCM_D

    if per is None:
        total = convert(unavailable, code, target)
        if asset_type in _WORKING_VOLUME_ASSETS:
            return DailyFigure(
                None, None, "unconverted:working_volume_not_rate",
                total_gwh=total if dimension is Dimension.ENERGY else None,
            )
        if start is None or stop is None or stop <= start:
            return DailyFigure(
                None, None, "unconverted:total_without_duration",
                total_gwh=total if dimension is Dimension.ENERGY else None,
            )
        hours = (stop - start).total_seconds() / 3600
        per_day = total * 24 / hours
        basis = "event_average"
        gwh_h = None
    else:
        reference = at or start
        hours = 24.0 if per == "d" else (gas_day_hours(reference) if reference else None)
        if hours is None:
            return DailyFigure(None, None, "unconverted:hourly_rate_without_gas_day")
        per_day = convert(unavailable, code, target) * (1 if per == "d" else hours)
        basis = "per_day" if per == "d" else f"per_hour_x_{hours:g}h"
        gwh_h = (
            convert(unavailable, code, "GWh")
            if per == "h" and dimension is Dimension.ENERGY
            else None
        )
        total = None
        technical_day = (
            convert(technical, code, target) * (1 if per == "d" else hours)
            if technical is not None
            else None
        )
        if max(per_day, technical_day or 0.0) > bound:
            return DailyFigure(None, None, f"unconverted:implausible_for_unit:{unit_text}")
    if per_day > bound:
        return DailyFigure(None, None, f"unconverted:implausible_for_unit:{unit_text}")
    if dimension is Dimension.ENERGY:
        return DailyFigure(per_day, None, basis, gwh_h=gwh_h, total_gwh=total)
    return DailyFigure(None, per_day, basis)


def outage_unit_summary(rows: Iterable[Mapping[str, object]]) -> dict[str, object]:
    """How many outage rows carry a daily figure, and what stayed in its own unit."""

    rows = list(rows)
    unconverted = [
        row for row in rows if str(row.get("daily_basis", "")).startswith("unconverted")
    ]
    reasons: dict[str, int] = {}
    units: dict[str, int] = {}
    for row in unconverted:
        reason = str(row["daily_basis"]).split(":")[1]
        reasons[reason] = reasons.get(reason, 0) + 1
        unit_text = str(row.get("unit") or "-")
        units[unit_text] = units.get(unit_text, 0) + 1
    return {
        "outage_count": len(rows),
        "with_daily_figure": len(rows) - len(unconverted),
        "unconverted_count": len(unconverted),
        "unconverted_units": dict(sorted(units.items())),
        "unconverted_reasons": dict(sorted(reasons.items())),
    }


def _key(name: str) -> str:
    return re.sub(r"[\s_\-./]", "", name).casefold()


def _field(raw: Mapping[str, object], name: str) -> object | None:
    normalised = {_key(str(k)): v for k, v in raw.items()}
    for alias in _ALIASES[name]:
        value = normalised.get(alias)
        if value not in (None, ""):
            return value
    return None


def _flatten(raw: Mapping[str, object]) -> dict[str, object]:
    """Nested platform JSON (``affectedAsset: {name, eic}``) as flat ACER-style keys."""

    flat: dict[str, object] = {}
    for key, value in raw.items():
        if isinstance(value, Mapping):
            for inner, inner_value in value.items():
                flat[f"{key}{str(inner)[:1].upper()}{str(inner)[1:]}"] = inner_value
            if "name" in value:
                flat.setdefault(key, value["name"])
        elif isinstance(value, list) and value and all(isinstance(v, str) for v in value):
            flat[key] = ",".join(value)
        else:
            flat[key] = value
    return flat


def _time(value: object, field: str, message_id: str) -> datetime:
    text = str(value).strip().replace("Z", "+00:00")
    try:
        moment = datetime.fromisoformat(text)
    except ValueError as exc:
        raise UmmParseError(f"{message_id}: {field} {value!r} is not an ISO 8601 time") from exc
    if moment.tzinfo is None:
        # ACER requires UTC; a naive time in an export is read as UTC, not local time.
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)


def _number(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", "").strip())
    except ValueError:
        return None


def _status(value: object) -> str:
    # "inactive" contains "active": the longer words are tested first (until 2026-11-16
    # every "Inactive" message was read as active).
    text = str(value or "active").strip().casefold()
    return next(
        (status for status in ("dismissed", "inactive", "active") if status in text), "active"
    )


def _unavailability(value: object) -> str:
    text = str(value or "").casefold()
    if "unplanned" in text or "forced" in text:
        return "unplanned"
    return "planned" if "planned" in text else ""


def _asset_type(value: object) -> str:
    text = str(value or "").casefold()
    if "lng" in text:
        return "lng"
    return next((kind for kind in ASSET_TYPES if kind in text), "other")


def parse_umm_export(
    text: str, *, source_reference: str, quarantine: list[dict] | None = None
) -> list[UmmMessage]:
    """Messages from a JSON (list, or object with ``messages``/``data``) or CSV export.

    With ``quarantine`` (the scheduled IIP collector), a message refused at the boundary
    (ONT-03: an event that ends before it starts) is left out and appended there with its
    reason code, so one bad provider record does not refuse the page; the operator's file
    import passes none and the whole file is refused, as before.

    Raises:
        UmmParseError: when a message lacks an identifier or an event start, or a time is
            not ISO 8601. Nothing is imported from a file with an unreadable message.
    """

    stripped = text.lstrip("﻿").strip()
    if not stripped:
        raise UmmParseError("the export is empty")
    if stripped[0] in "[{":
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise UmmParseError(f"not valid JSON: {exc.msg}") from exc
        if isinstance(payload, Mapping):
            payload = payload.get("messages") or payload.get("data") or payload.get("umms") or []
        raw_rows: Iterable[Mapping[str, object]] = [
            _flatten(row) for row in payload if isinstance(row, Mapping)
        ]
    else:
        raw_rows = list(csv.DictReader(io.StringIO(stripped)))
    messages = []
    for row in raw_rows:
        try:
            messages.append(_message(row, source_reference))
        except UmmParseError as exc:
            if quarantine is None or not getattr(exc, "reason_code", None):
                raise
            quarantine.append(
                {
                    "message_id": str(_field(row, "message_id") or ""),
                    "reason": exc.reason_code,  # type: ignore[attr-defined]
                    "detail": str(exc),
                }
            )
    if not messages and not quarantine:
        raise UmmParseError("no messages found in the export")
    return messages


def _message(raw: Mapping[str, object], source_reference: str) -> UmmMessage:
    message_id = str(_field(raw, "message_id") or "").strip()
    if not message_id:
        raise UmmParseError("a message has no identifier")
    start = _field(raw, "event_start")
    if start is None:
        raise UmmParseError(f"{message_id}: no event start")
    published = _field(raw, "published_at")
    stop = _field(raw, "event_stop")
    unit = str(_field(raw, "unit") or "").strip()
    technical = _number(_field(raw, "technical_capacity"))
    available = _number(_field(raw, "available_capacity"))
    unavailable = _number(_field(raw, "unavailable_capacity"))
    if unavailable is None and technical is not None and available is not None:
        unavailable = technical - available
    event_start = _time(start, "event start", message_id)
    event_stop = _time(stop, "event stop", message_id) if stop is not None else None
    # ONT-03: the event period against the ontology; an outage that ends before it starts
    # is refused with its reason code, not stored. The unit is kept as published: a unit
    # with no daily figure is reported by ``daily_figure`` (``unconverted:<reason>``).
    from eurogas_nexus.domain.ontology.boundary import check_boundary, refuse_if_invalid

    refuse_if_invalid(
        check_boundary(period_start=event_start, period_end=event_stop),
        UmmParseError,
        f"{message_id}: ",
    )
    asset_type = _asset_type(_field(raw, "asset_type"))
    figure = daily_figure(
        unit,
        unavailable,
        technical=technical,
        asset_type=asset_type,
        start=event_start,
        stop=event_stop,
    )
    return UmmMessage(
        message_id=message_id[:64],
        version=int(_number(_field(raw, "version")) or 1),
        published_at_utc=_time(published, "publication time", message_id)
        if published is not None
        else _time(start, "event start", message_id),
        event_status=_status(_field(raw, "event_status")),
        unavailability_type=_unavailability(_field(raw, "unavailability_type")),
        event_start_utc=event_start,
        event_stop_utc=event_stop,
        asset_name=str(_field(raw, "asset_name") or "")[:160],
        asset_eic=str(_field(raw, "asset_eic") or "")[:32],
        asset_type=asset_type,
        balancing_zone=str(_field(raw, "balancing_zone") or "")[:64],
        direction=str(_field(raw, "direction") or "")[:16].casefold(),
        unit=unit[:16],
        technical_capacity=technical,
        available_capacity=available,
        unavailable_capacity=unavailable,
        unavailable_mcm_d=figure.mcm_d,
        unavailable_gwh_d=figure.gwh_d,
        reason=str(_field(raw, "reason") or "")[:240],
        market_participant=str(_field(raw, "market_participant") or "")[:160],
        remarks=str(_field(raw, "remarks") or "")[:1000],
        source_reference=source_reference[:160],
    )


def current_messages(messages: Iterable[UmmMessage]) -> list[UmmMessage]:
    """The latest version of each message that is still an event.

    ACER's event status: ``Dismissed`` withdraws a message published in error and
    ``Inactive`` says the event is over (live: NaTran's PS000SA message, version 5
    ``Inactive`` with 0 unavailable, published a year before its stated stop). Neither is a
    live or upcoming outage, whatever its stop time says.
    """

    latest: dict[str, UmmMessage] = {}
    for message in messages:
        held = latest.get(message.message_id)
        if held is None or (message.version, message.published_at_utc) > (
            held.version,
            held.published_at_utc,
        ):
            latest[message.message_id] = message
    return [m for m in latest.values() if m.event_status not in ENDED_STATUSES]


def outage_view(
    messages: Iterable[UmmMessage],
    *,
    now: datetime,
    horizon_days: int = 90,
    ended_since: datetime | None = None,
) -> list[dict[str, object]]:
    """Events running now or starting within ``horizon_days``, soonest first.

    Rows keep the ``OutageEvent`` fields the SDK reads and add the REMIT detail. With
    ``ended_since``, events that ended after it and by ``now`` are kept too, with status
    ``ended``, after the others: a report's period start, or the Network page's "Ended
    recently" window. The live views never pass it.
    """

    from datetime import timedelta

    from eurogas_nexus.domain.observations.remit_platforms import platform_attribution

    horizon = now + timedelta(days=horizon_days)
    rows = []
    for m in current_messages(messages):
        ended = m.event_stop_utc is not None and m.event_stop_utc <= now
        if ended and (ended_since is None or m.event_stop_utc <= ended_since):
            continue
        if m.event_start_utc > horizon:
            continue
        status = "ended" if ended else "active" if m.event_start_utc <= now else "scheduled"
        # Re-derived from the stored unit and capacity, so rows stored before a
        # conversion existed read the same as new ones.
        figure = daily_figure(
            m.unit,
            m.unavailable_capacity,
            technical=m.technical_capacity,
            asset_type=m.asset_type,
            start=m.event_start_utc,
            stop=m.event_stop_utc,
            at=m.event_start_utc if ended else max(now, m.event_start_utc),
        )
        if figure.gwh_d is None and m.unavailable_gwh_d is not None:
            # A figure the message was stored with (an import that stated GWh/d beside a
            # volume) is kept; the conversion never invents one across energy and volume.
            figure = DailyFigure(
                m.unavailable_gwh_d, figure.mcm_d or m.unavailable_mcm_d, "stored",
                gwh_h=figure.gwh_h, total_gwh=figure.total_gwh,
            )
        platform, attribution = platform_attribution(m.source_reference)
        rows.append(
            {
                "event_id": m.message_id,
                "version": m.version,
                "facility_id": m.asset_eic,
                "facility_name": m.asset_name,
                "asset_type": m.asset_type,
                "event_type": m.unavailability_type or "unspecified",
                "status": status,
                "start_utc": m.event_start_utc.isoformat(),
                "end_utc": m.event_stop_utc.isoformat() if m.event_stop_utc else None,
                "published_at_utc": m.published_at_utc.isoformat(),
                "balancing_zone": m.balancing_zone,
                "direction": m.direction,
                "unit": m.unit,
                "technical_capacity": m.technical_capacity,
                "available_capacity": m.available_capacity,
                "unavailable_capacity": m.unavailable_capacity,
                # None, not 0, when the message gives no volume figure: an outage published
                # in GWh/d with no conversion is not an outage of zero (``unavailable_gwh_d``
                # and ``daily_basis`` carry what is known).
                "capacity_impact_mcm_d": figure.mcm_d,
                "unavailable_gwh_d": figure.gwh_d,
                "unavailable_mcm_d": figure.mcm_d,
                "unavailable_gwh_h": figure.gwh_h,
                "unavailable_total_gwh": figure.total_gwh,
                "daily_basis": figure.basis,
                "description": m.reason or m.remarks,
                "market_participant": m.market_participant,
                "source_system": "REMIT",
                "source_reference": m.source_reference,
                # The inside-information platform and the credit its terms ask for.
                "platform": platform,
                "attribution": attribution,
                "research_only": True,
            }
        )
    order = {"active": 0, "scheduled": 1, "ended": 2}
    rows.sort(key=lambda row: (order[str(row["status"])], str(row["start_utc"])))
    return rows


def _event_asset_keys(row: Mapping[str, object]) -> list[str]:
    keys = []
    eic = str(row.get("facility_id") or "").strip().casefold()
    if eic:
        keys.append(f"eic:{eic}")
    name = re.sub(r"[^0-9a-z]", "", str(row.get("facility_name") or "").casefold())
    if name:
        keys.append(f"name:{name}")
    return keys


def _event_shape(row: Mapping[str, object]) -> tuple[str, str, str]:
    """Period (to the minute) and size of an outage row, as compared for one event."""

    def minute(value: object) -> str:
        return str(value or "")[:16]

    gwh = row.get("unavailable_gwh_d")
    size = (
        f"gwh_d:{float(gwh):.1f}"
        if isinstance(gwh, int | float)
        else f"raw:{row.get('unavailable_capacity')}:{row.get('unit') or ''}"
    )
    return minute(row.get("start_utc")), minute(row.get("end_utc")), size


def outage_events(rows: Iterable[Mapping[str, object]]) -> list[dict[str, object]]:
    """One row per outage event: messages that describe the same reduction collapse.

    The rule (docs/operations/REMIT_OUTAGES.md, "One row per event"): two rows (each already
    the latest version of its message, ``current_messages``) are one event when they name the
    same asset - the same asset EIC, or the same asset name compared without case, spaces or
    punctuation - for the same period (start and stop to the minute, an open stop matching
    only an open stop) and the same size (the daily figure in GWh/d to 0.1, or the published
    capacity and unit where no daily figure exists). Direction is not compared: the two
    operators at an interconnection point publish its exit and its entry side. Matching is
    transitive. The event row is the most recently published member (then the highest
    version, then the largest message id); it adds ``messages`` (every member's message id,
    sorted), ``operators`` (every member's market participant, sorted, de-duplicated) and
    ``message_count``. Rows keep the input order of their event's first member.
    """

    rows = [dict(row) for row in rows]
    parent = list(range(len(rows)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    seen: dict[tuple[str, str, str, str], int] = {}
    for index, row in enumerate(rows):
        shape = _event_shape(row)
        for asset in _event_asset_keys(row):
            key = (asset, *shape)
            if key in seen:
                parent[find(index)] = find(seen[key])
            else:
                seen[key] = index
    groups: dict[int, list[int]] = {}
    for index in range(len(rows)):
        groups.setdefault(find(index), []).append(index)
    events = []
    for members in sorted(groups.values(), key=lambda indices: indices[0]):
        lead = max(
            (rows[index] for index in members),
            key=lambda row: (
                str(row.get("published_at_utc") or ""),
                int(row.get("version") or 0),
                str(row.get("event_id") or ""),
            ),
        )
        event = dict(lead)
        event["messages"] = sorted(str(rows[index].get("event_id")) for index in members)
        event["operators"] = sorted(
            {
                str(rows[index].get("market_participant") or "").strip()
                for index in members
                if str(rows[index].get("market_participant") or "").strip()
            }
        )
        event["message_count"] = len(members)
        events.append(event)
    return events
