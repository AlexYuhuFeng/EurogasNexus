"""LNG-4: REMIT outages update the pipeline supply they flow through, advisory, with a manual
override.

A pipeline supply of a book (``pipeline_supplies``) names the assets its gas flows through in
``depends_on``: an entry point, an interconnector, a field or a facility, each by the asset
EIC a REMIT message carries, by the asset's name, or by a GIE facility EIC. When the outbox
delivers ``outage.published`` (market_events, Decision 28) the disruption consumer calls
:func:`link_outages` first, so the re-optimisation that follows already reads the supply as
curtailed. The rules:

* **Matching** is exact, never by similarity: the message's asset EIC equals the entry's
  ``asset_eic``; or its asset name equals the entry's ``asset_name`` with case, accents,
  punctuation and spacing ignored; or the reviewed alias table
  (``reference_data/outage_asset_aliases.json``) ties the message's asset to the entry's
  ``gie_facility_eic``. An entry with a ``direction`` matches only a message for that
  direction (a message without one matches).
* **Volume.** The share of the asset unavailable is ``unavailable / technical`` capacity as
  the message states it (one unit, so the unit cancels), else the message's unavailable
  GWh/d over the entry's ``capacity_mwh_d``. Each gas day the outage overlaps, the supply
  loses ``mwh_per_day x share_pct / 100 x fraction x overlap`` (``overlap`` the part of the
  gas day inside the event, so a 23- or 25-hour gas day is weighed by its own length). An
  open-ended message runs to the supply's last gas day. When no share can be derived the
  link is kept as ``unsized``: it is shown and curtails nothing.
* **Versions.** One link per supply and message. A newer version revises the link; an older
  or a repeated one changes nothing (the outbox may deliver a message twice). A message
  ``dismissed`` withdraws the link (``withdrawn``) and one ``inactive`` ends it (``ended``):
  either way the row stays, with no curtailment, so the record says what was linked and why.
* **Several links** on one gas day: the largest curtailment counts, not the sum, because two
  messages about the path of one supply are more often the same event published twice (an
  operator and an adjacent one) than two independent losses; a supply never loses more than
  it delivers.
* **Manual override.** Days entered by hand (``pipeline_supplies.curtailed``) win over a
  link on the same day. With ``outage_mode`` ``manual`` only those days count; the links are
  still recorded and shown.

Advisory: this is the platform's reading of a published message, for valuing options;
nothing is nominated or changed with a counterparty or a TSO.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import uuid4

from eurogas_nexus.domain.market.gas_day import gas_day_start_for_date
from eurogas_nexus.reference_data.outage_aliases import name_key, shipped_aliases

AUTO = "auto"
MANUAL = "manual"
MODES = (AUTO, MANUAL)
APPLIED, UNSIZED, WITHDRAWN, ENDED = "applied", "unsized", "withdrawn", "ended"
#: How long an open-ended message is taken to run when the supply has no end in sight.
OPEN_ENDED_CAP_DAYS = 400


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _match(dependency: Mapping[str, Any], message) -> str | None:
    """The key a dependency entry matches the message on, or ``None``."""

    direction = str(dependency.get("direction") or "").strip().casefold()
    published = str(getattr(message, "direction", "") or "").strip().casefold()
    if direction and published and direction != published:
        return None
    eic = str(dependency.get("asset_eic") or "").strip().upper()
    if eic and eic == str(message.asset_eic or "").strip().upper():
        return "asset_eic"
    name = dependency.get("asset_name")
    if name and name_key(name) and name_key(name) == name_key(message.asset_name):
        return "asset_name"
    facility = str(dependency.get("gie_facility_eic") or "").strip().upper()
    if facility:
        entry = shipped_aliases().facility_for(eic=message.asset_eic, name=message.asset_name)
        if entry and str(entry.get("gie_facility_eic") or "").upper() == facility:
            return "gie_facility_eic"
    return None


def _fraction(dependency: Mapping[str, Any], message) -> tuple[float | None, str]:
    """The share of the asset unavailable (0..1), and how it was derived."""

    technical = message.technical_capacity
    unavailable = message.unavailable_capacity
    if technical and technical > 0 and unavailable is not None:
        share = max(0.0, min(1.0, float(unavailable) / float(technical)))
        return share, (
            f"{float(unavailable):,.0f} of {float(technical):,.0f} {message.unit} technical "
            f"capacity unavailable ({share:.0%})"
        )
    capacity = dependency.get("capacity_mwh_d")
    if message.unavailable_gwh_d is not None and capacity:
        share = max(0.0, min(1.0, float(message.unavailable_gwh_d) * 1000 / float(capacity)))
        return share, (
            f"{float(message.unavailable_gwh_d):,.1f} GWh/d unavailable against the "
            f"{float(capacity):,.0f} MWh/d capacity the supply records ({share:.0%})"
        )
    return None, "the message states no technical capacity and the supply records none"


def curtailment(
    supply, dependency: Mapping[str, Any], message, fraction: float | None
) -> list[list[Any]]:
    """``[[gas day ISO, MWh not delivered], ...]`` the message takes from the supply."""

    if fraction is None or fraction <= 0:
        return []
    start = _aware(message.event_start_utc)
    stop = _aware(message.event_stop_utc)
    share = float(dependency.get("share_pct", 100.0)) / 100.0
    last = supply.last_gas_day
    first = max(supply.first_gas_day, (start - timedelta(days=1)).date())
    if stop is None:
        last = min(last, first + timedelta(days=OPEN_ENDED_CAP_DAYS))
    out: list[list[Any]] = []
    day = first
    while day <= last:
        begin = gas_day_start_for_date(day)
        end = gas_day_start_for_date(day + timedelta(days=1))
        lo, hi = max(begin, start), min(end, stop or end)
        if stop is not None and begin >= stop:
            break
        if hi > lo:
            overlap = (hi - lo) / (end - begin)
            mwh = round(float(supply.mwh_per_day) * share * fraction * overlap, 3)
            if mwh > 0:
                out.append([day.isoformat(), mwh])
        day += timedelta(days=1)
    return out


@dataclass
class LinkReport:
    """What one pass of :func:`link_outages` did."""

    created: list[str] = field(default_factory=list)
    revised: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    books: set[str] = field(default_factory=set)

    def as_dict(self) -> dict[str, Any]:
        return {
            "created": self.created,
            "revised": self.revised,
            "unchanged": len(self.unchanged),
            "books": sorted(self.books),
        }


def _latest_messages(session, message_ids: Iterable[str] | None):
    from eurogas_nexus.db.models import RemitUmmRecord

    query = session.query(RemitUmmRecord)
    if message_ids is not None:
        wanted = sorted(set(message_ids))
        if not wanted:
            return []
        query = query.filter(RemitUmmRecord.message_id.in_(wanted))
    latest: dict[str, Any] = {}
    for row in query.all():
        held = latest.get(row.message_id)
        if held is None or int(row.version) > int(held.version):
            latest[row.message_id] = row
    return [latest[key] for key in sorted(latest)]


def _status(message, fraction: float | None) -> str:
    status = str(message.event_status or "active").casefold()
    if status == "dismissed":
        return WITHDRAWN
    if status == "inactive":
        return ENDED
    return APPLIED if fraction is not None else UNSIZED


def link_outages(
    session,
    *,
    message_ids: Iterable[str] | None = None,
    event_ids: Mapping[str, str] | None = None,
    now: datetime | None = None,
) -> LinkReport:
    """Link the latest version of each REMIT message (all, or ``message_ids``) to the
    pipeline supplies that depend on its asset; revise links a newer version changes."""

    from eurogas_nexus.db.models import PipelineOutageLinkRecord, PipelineSupplyRecord

    moment = _aware(now) or datetime.now(UTC)
    report = LinkReport()
    supplies = [
        row
        for row in session.query(PipelineSupplyRecord)
        .order_by(PipelineSupplyRecord.supply_id)
        .all()
        if row.depends_on
    ]
    if not supplies:
        return report
    messages = _latest_messages(session, message_ids)
    for message in messages:
        for supply in supplies:
            for dependency in supply.depends_on or []:
                matched = _match(dependency, message)
                if matched is None:
                    continue
                fraction, how = _fraction(dependency, message)
                status = _status(message, fraction)
                days = curtailment(supply, dependency, message, fraction)
                if status in (WITHDRAWN, ENDED):
                    days = []
                share = float(dependency.get("share_pct", 100.0))
                why = (
                    f"{message.asset_name} ({message.asset_eic}) matches the supply's "
                    f"{dependency.get('kind') or 'asset'} on {matched.replace('_', ' ')}; "
                    f"{how}; the supply takes {share:g} % of its gas through it"
                )
                if status == WITHDRAWN:
                    why += "; the message was withdrawn, so it curtails nothing"
                elif status == ENDED:
                    why += "; the outage has ended, so it curtails nothing"
                elif status == UNSIZED:
                    why += "; no volume can be derived, so it is shown and curtails nothing"
                row = (
                    session.query(PipelineOutageLinkRecord)
                    .filter_by(supply_id=supply.supply_id, message_id=message.message_id)
                    .one_or_none()
                )
                event_id = (event_ids or {}).get(message.message_id)
                values = {
                    "version": int(message.version),
                    "event_status": str(message.event_status),
                    "asset_name": message.asset_name,
                    "asset_eic": message.asset_eic,
                    "matched_on": matched,
                    "dependency": dict(dependency),
                    "why": why,
                    "fraction": None if fraction is None else round(fraction, 6),
                    "curtailed": days,
                    "status": status,
                }
                if row is None:
                    session.add(
                        PipelineOutageLinkRecord(
                            link_id=uuid4().hex,
                            supply_id=supply.supply_id,
                            book_id=supply.book_id,
                            message_id=message.message_id,
                            event_id=event_id,
                            first_linked_at_utc=moment,
                            updated_at_utc=moment,
                            **values,
                        )
                    )
                    report.created.append(f"{supply.supply_id}:{message.message_id}")
                    report.books.add(supply.book_id)
                elif int(message.version) > int(row.version) or (
                    int(message.version) == int(row.version)
                    and any(getattr(row, key) != value for key, value in values.items())
                ):
                    for key, value in values.items():
                        setattr(row, key, value)
                    row.event_id = event_id or row.event_id
                    row.updated_at_utc = moment
                    report.revised.append(f"{supply.supply_id}:{message.message_id}")
                    report.books.add(supply.book_id)
                else:
                    report.unchanged.append(f"{supply.supply_id}:{message.message_id}")
                break  # one link per supply and message: the first entry that matches
    session.flush()
    return report


def links(session, supply_ids: Iterable[str]) -> dict[str, list]:
    """The links of each supply, newest first."""

    from eurogas_nexus.db.models import PipelineOutageLinkRecord

    wanted = sorted(set(supply_ids))
    out: dict[str, list] = {key: [] for key in wanted}
    if not wanted:
        return out
    for row in (
        session.query(PipelineOutageLinkRecord)
        .filter(PipelineOutageLinkRecord.supply_id.in_(wanted))
        .order_by(PipelineOutageLinkRecord.updated_at_utc.desc())
        .all()
    ):
        out[row.supply_id].append(row)
    return out


@dataclass(frozen=True)
class Effective:
    """A supply's curtailed days as the valuation reads them, and where each came from."""

    curtailed: tuple[tuple[date, float], ...]
    by_day: Mapping[str, str]
    mode: str
    sources: tuple[str, ...]


def effective(supply, held_links: Iterable[Any]) -> Effective:
    """Manual days win; in ``auto`` mode the largest linked curtailment fills the others."""

    mode = MANUAL if (supply.outage_mode or AUTO) == MANUAL else AUTO
    days: dict[date, float] = {}
    by_day: dict[str, str] = {}
    for day, mwh in supply.curtailed or []:
        when = date.fromisoformat(str(day))
        days[when] = float(mwh)
        by_day[when.isoformat()] = "entered by hand"
    sources: list[str] = []
    if mode == AUTO:
        for link in held_links:
            if link.status != APPLIED:
                continue
            used = False
            for day, mwh in link.curtailed or []:
                when = date.fromisoformat(str(day))
                if by_day.get(when.isoformat()) == "entered by hand":
                    continue
                if float(mwh) > days.get(when, 0.0):
                    days[when] = min(float(mwh), float(supply.mwh_per_day))
                    by_day[when.isoformat()] = f"REMIT {link.message_id} v{link.version}"
                    used = True
            if used:
                sources.append(f"REMIT {link.message_id} v{link.version}: {link.why}")
    return Effective(tuple(sorted(days.items())), by_day, mode, tuple(sources))


def link_dict(row) -> dict[str, Any]:
    return {
        "link_id": row.link_id,
        "supply_id": row.supply_id,
        "message_id": row.message_id,
        "version": row.version,
        "event_status": row.event_status,
        "asset_name": row.asset_name,
        "asset_eic": row.asset_eic,
        "matched_on": row.matched_on,
        "dependency": row.dependency,
        "why": row.why,
        "fraction": row.fraction,
        "curtailed": row.curtailed,
        "curtailed_mwh": round(sum(float(m) for _d, m in row.curtailed or []), 3),
        "status": row.status,
        "event_id": row.event_id,
        "first_linked_at_utc": _aware(row.first_linked_at_utc).isoformat(),
        "updated_at_utc": _aware(row.updated_at_utc).isoformat(),
    }


class OverrideError(ValueError):
    """An override the store cannot take (unknown supply, bad days)."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code, self.code, self.message = status_code, code, message


def _visible_supply(session, supply_id: str):
    """The supply, when its book is one the caller may see (else not found)."""

    from eurogas_nexus.db.models import PipelineSupplyRecord
    from eurogas_nexus.security.portfolio_scope import visible_book_ids

    supply = session.get(PipelineSupplyRecord, supply_id)
    allowed = visible_book_ids(session)
    if supply is None or (allowed is not None and supply.book_id not in allowed):
        raise OverrideError(404, "pipeline_supply_not_found", f"No pipeline supply {supply_id}.")
    return supply


def supply_links(session, supply_id: str) -> dict[str, Any]:
    """A supply's REMIT links, its mode and the curtailment the valuation reads."""

    supply = _visible_supply(session, supply_id)
    held = links(session, [supply_id])[supply_id]
    used = effective(supply, held)
    return {
        "supply_id": supply.supply_id,
        "book_id": supply.book_id,
        "label": supply.label,
        "depends_on": supply.depends_on or [],
        "outage_mode": used.mode,
        "entered_by_hand": [list(item) for item in supply.curtailed or []],
        "links": [link_dict(row) for row in held],
        "effective": [[day.isoformat(), mwh] for day, mwh in used.curtailed],
        "effective_source": dict(used.by_day),
        "advisory": "Advisory: the platform's reading of published REMIT messages, for valuing "
        "options. Nothing is nominated or changed with a counterparty or a TSO.",
    }


def set_override(
    session,
    supply_id: str,
    *,
    mode: str,
    curtailed: list[list[Any]] | None,
    actor: str,
    reason: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Set a supply's outage mode and, when given, the days entered by hand (audited
    ``lng.pipeline_outage_override``). Returns the supply's links as :func:`supply_links`."""

    from eurogas_nexus.application.audit_service import record_governed_audit

    if mode not in MODES:
        raise OverrideError(422, "outage_mode_invalid", f"outage_mode must be one of {MODES}.")
    supply = _visible_supply(session, supply_id)
    moment = _aware(now) or datetime.now(UTC)
    before = (supply.outage_mode or AUTO, list(supply.curtailed or []))
    if curtailed is not None:
        clean: dict[str, float] = {}
        for item in curtailed:
            try:
                day, mwh = date.fromisoformat(str(item[0])), float(item[1])
            except (TypeError, ValueError, IndexError) as exc:
                raise OverrideError(
                    422, "curtailment_invalid", "Each day is [gas day ISO, MWh not delivered]."
                ) from exc
            if not supply.first_gas_day <= day <= supply.last_gas_day:
                raise OverrideError(
                    422,
                    "curtailment_invalid",
                    f"{day} is outside the supply's {supply.first_gas_day} to "
                    f"{supply.last_gas_day}.",
                )
            if not 0 <= mwh <= float(supply.mwh_per_day):
                raise OverrideError(
                    422,
                    "curtailment_invalid",
                    f"{mwh:,.0f} MWh on {day} is not between 0 and the supply's "
                    f"{float(supply.mwh_per_day):,.0f} MWh/d.",
                )
            clean[day.isoformat()] = mwh
        supply.curtailed = [[day, clean[day]] for day in sorted(clean)]
    supply.outage_mode = mode
    supply.updated_at_utc = moment
    days = len(supply.curtailed or [])
    record_governed_audit(
        session,
        event_type="portfolio",
        principal=actor,
        action="lng.pipeline_outage_override",
        resource=f"pipeline_supply:{supply_id}",
        detail=(
            f"outage mode {before[0]} -> {mode}; {days} day(s) entered by hand"
            + (f" (was {len(before[1])})" if curtailed is not None else "")
            + (f"; {reason}" if reason else "")
        ),
    )
    session.flush()
    return supply_links(session, supply_id)


__all__ = [
    "AUTO",
    "MANUAL",
    "Effective",
    "LinkReport",
    "OverrideError",
    "curtailment",
    "effective",
    "link_dict",
    "link_outages",
    "links",
    "set_override",
    "supply_links",
]
