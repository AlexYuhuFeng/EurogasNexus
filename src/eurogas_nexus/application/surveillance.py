"""Market-abuse surveillance input: the firm's activity set against REMIT disclosure timing.

Decision support for the compliance function, not a verdict. Under REMIT Art. 3-4 and
MAR, a firm must disclose inside information about its own assets promptly (ACER's guidance
is within an hour) and must not trade on it before disclosure. This module lines up
everything the firm did in the product (decision cases opened, decisions recorded, trades
imported from the ETRM) against the publication times of gas UMMs and raises alerts:

``late_own_disclosure`` (high)
    An outage at one of the firm's own assets was first published more than
    :data:`DISCLOSURE_LIMIT` after it started.
``activity_before_own_disclosure`` (high)
    The firm acted on an affected hub between the start of its own outage (or
    :data:`OWN_LOOKBACK` before publication, whichever is earlier) and the first publication.
``activity_before_market_disclosure`` (medium)
    The firm acted on an affected hub in the :data:`MARKET_WINDOW` before another
    participant's outage was published, a pattern surveillance reviews for leaks.

The firm's own participants come from ``EUROGAS_NEXUS_REMIT_OWN_PARTICIPANTS`` (names or
ACER codes as they appear in the UMMs, comma-separated). The output feeds the firm's
surveillance system (Nasdaq SMARTS, Behavox, Eventus, an in-house tool) as CSV or JSON.
"""

from __future__ import annotations

import os
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta

from eurogas_nexus.domain.ontology.markets import european_gas_hubs, find_market

OWN_PARTICIPANTS_ENV = "EUROGAS_NEXUS_REMIT_OWN_PARTICIPANTS"
DISCLOSURE_LIMIT = timedelta(hours=1)
OWN_LOOKBACK = timedelta(hours=24)
MARKET_WINDOW = timedelta(hours=2)
#: Norwegian supply lands in the north-west European hubs.
_NORWAY_HUBS = ("NBP", "TTF", "THE", "ZTP", "PEG")


@dataclass(frozen=True)
class SurveillanceAlert:
    """One row for the firm's surveillance queue."""

    alert_id: str
    rule: str
    severity: str
    message_id: str
    asset_name: str
    balancing_zone: str
    market_participant: str
    event_start_utc: str
    first_published_utc: str
    activity_type: str
    activity_id: str
    actor: str
    hub: str
    activity_at_utc: str
    minutes_before_publication: int | None


def own_participants(environ: dict[str, str] | None = None) -> set[str]:
    env = os.environ if environ is None else environ
    return {
        item.strip().casefold()
        for item in str(env.get(OWN_PARTICIPANTS_ENV, "")).split(",")
        if item.strip()
    }


def hubs_for_zone(zone: str) -> set[str]:
    """Gas hubs a balancing zone's outage moves; empty when the zone is not recognised."""

    value = (zone or "").strip().upper()
    if not value:
        return set()
    if value in {"NO", "NORWAY"} or "NORW" in value:
        return set(_NORWAY_HUBS)
    tokens = set(re.split(r"[^A-Z0-9]+", value)) - {""}
    hubs = set()
    for code in european_gas_hubs():
        country = (getattr(find_market(code), "country", "") or "").upper()
        if code in tokens or (country and country in tokens):
            hubs.add(code)
    if value in {"UK", "GB-NTS"}:
        hubs.add("NBP")
    return hubs


def _aware(moment: datetime | None) -> datetime | None:
    if moment is None:
        return None
    return moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment.astimezone(UTC)


def surveillance_alerts(
    session,
    *,
    since: datetime,
    until: datetime,
    own: set[str] | None = None,
) -> list[SurveillanceAlert]:
    """Alerts for UMMs first published in ``[since, until)``, oldest first."""

    from eurogas_nexus.db.models import (
        DecisionCaseDecisionRecord,
        DecisionCaseRecord,
        RemitUmmRecord,
        ScreenOrderObservationRecord,
    )

    own = own_participants() if own is None else {item.casefold() for item in own}
    first: dict[str, RemitUmmRecord] = {}
    for record in session.query(RemitUmmRecord).all():
        held = first.get(record.message_id)
        if held is None or _aware(record.published_at_utc) < _aware(held.published_at_utc):
            first[record.message_id] = record

    cases = {case.case_id: case for case in session.query(DecisionCaseRecord).all()}
    activities: list[tuple[str, str, str, str, datetime]] = []
    for case in cases.values():
        activities.append(
            (
                "decision_case_opened",
                case.case_id,
                case.created_by,
                case.hub_id.upper(),
                _aware(case.created_at_utc),
            )
        )
    for decision in session.query(DecisionCaseDecisionRecord).all():
        case = cases.get(decision.case_id)
        activities.append(
            (
                "decision_recorded",
                decision.record_id,
                decision.actor,
                (case.hub_id if case else "").upper(),
                _aware(decision.recorded_at_utc),
            )
        )
    for trade in session.query(ScreenOrderObservationRecord).all():
        activities.append(
            (
                "trade",
                trade.order_observation_id,
                trade.account_label,
                trade.hub.upper(),
                _aware(trade.observed_at_utc),
            )
        )

    alerts: list[SurveillanceAlert] = []

    def alert(rule, severity, umm, published, activity=None):
        kind, activity_id, actor, hub, at = activity or ("", "", "", "", None)
        minutes = int((published - at).total_seconds() // 60) if at else None
        alerts.append(
            SurveillanceAlert(
                alert_id=f"{rule}:{umm.message_id}:{activity_id}"[:200],
                rule=rule,
                severity=severity,
                message_id=umm.message_id,
                asset_name=umm.asset_name,
                balancing_zone=umm.balancing_zone,
                market_participant=umm.market_participant,
                event_start_utc=_aware(umm.event_start_utc).isoformat(),
                first_published_utc=published.isoformat(),
                activity_type=kind,
                activity_id=activity_id,
                actor=actor,
                hub=hub,
                activity_at_utc=at.isoformat() if at else "",
                minutes_before_publication=minutes,
            )
        )

    since, until = _aware(since), _aware(until)
    for umm in sorted(first.values(), key=lambda item: _aware(item.published_at_utc)):
        published = _aware(umm.published_at_utc)
        if not (since <= published < until):
            continue
        start = _aware(umm.event_start_utc)
        is_own = bool(own) and (umm.market_participant or "").casefold() in own
        hubs = hubs_for_zone(umm.balancing_zone)
        if is_own:
            if published - start > DISCLOSURE_LIMIT:
                alert("late_own_disclosure", "high", umm, published)
            window_start = min(start, published - OWN_LOOKBACK)
            rule, severity = "activity_before_own_disclosure", "high"
        else:
            window_start = published - MARKET_WINDOW
            rule, severity = "activity_before_market_disclosure", "medium"
        for activity in activities:
            at = activity[4]
            if at is not None and activity[3] in hubs and window_start <= at < published:
                alert(rule, severity, umm, published, activity)
    return alerts


def alerts_as_rows(alerts: list[SurveillanceAlert]) -> list[dict]:
    return [asdict(item) for item in alerts]
