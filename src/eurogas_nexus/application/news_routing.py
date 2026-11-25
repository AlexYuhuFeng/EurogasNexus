"""A news item that touches the firm's book reaches the role whose work it changes (NEWS-1).

:class:`NewsRoutingConsumer` is a consumer of the market event outbox
(``application/market_events.py``). For each ``news.published`` event it reads the item, finds
the exposures it touches (``news_relevance.matches``: a contract's hub, an open cargo's vessel
or terminal, a hub the firm nominates at) and raises one monitoring alert per role
(fingerprint ``news:<item>:<role>``, category from ``alert_routing.NEWS_ROLE_CATEGORIES``,
routed by ``alert_routing``), with the books it touches in its evidence so each reader sees it
only for books they may see (``alert_scope``).

A notification is queued only for an item that is recent (published within
:data:`RECENT`) and of a kind a desk must hear about at once (:data:`NOTIFY_TYPES`, or a
capacity change); any other match is an in-app alert only. Dedupe and cooldown:

* the same content for the same role is never notified twice (``digest``);
* a role is not notified again about the same item within :data:`COOLDOWN` unless something
  new is in it;
* a role is not notified about a second item on the same held outage (``linked_event_key``)
  within :data:`COOLDOWN`: two publishers reporting one outage is one message.

Open news alerts older than :data:`ALERT_DAYS` are resolved as aged. Nothing is traded,
nominated or sent beyond the notification; a person decides.

新闻路由：触及账簿的新闻按角色生成告警（交易员/LNG/调度），去重与冷却后通知。
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any

from eurogas_nexus.application.alert_routing import (
    NEWS_ROLE_CATEGORIES,
    addressed_line,
    route_for,
)

CONSUMER_NAME = "news_roles"
COOLDOWN = timedelta(minutes=30)
RECENT = timedelta(days=2)
ALERT_DAYS = 3
#: Event types a role is notified about at once; others raise an in-app alert only.
NOTIFY_TYPES = frozenset({"outage", "sanction", "strike", "geopolitical"})
_TITLES_ZH = {"trader": "新闻触及合同枢纽", "lng": "新闻触及在途船货",
              "scheduler": "新闻触及提名枢纽"}


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def fingerprint(item_id: str, role: str) -> str:
    return f"news:{item_id}:{role}"


class NewsRoutingConsumer:
    """Tells each role about the news items that touch its part of the book."""

    name = CONSUMER_NAME

    def accepts(self, record) -> bool:
        return record.event_type == "news.published"

    def handle(self, session, records, *, now_utc: datetime) -> dict[str, Any]:
        latest: dict[str, Any] = {}
        for record in records:
            item_id = (record.payload_json or {}).get("item_id")
            if item_id and (item_id not in latest or record.revision > latest[item_id].revision):
                latest[item_id] = record
        results = [react(session, item_id, now=now_utc) for item_id in sorted(latest)]
        aged = expire_aged(session, now=now_utc)
        return {
            "items": results,
            "aged": aged,
            "notified": any(r.get("queued") for r in results),
        }


def register() -> NewsRoutingConsumer:
    """Subscribe the consumer to the outbox (idempotent)."""

    from eurogas_nexus.application import market_events

    try:
        return market_events.consumer(CONSUMER_NAME)  # type: ignore[return-value]
    except KeyError:
        return market_events.register_consumer(NewsRoutingConsumer())  # type: ignore[return-value]


def _digest(value: Any) -> str:
    text = json.dumps(value, sort_keys=True, default=str)
    return hashlib.sha256(text.encode()).hexdigest()[:24]


def _same_event_notified(session, role: str, event_key: str | None, item_id: str,
                         now: datetime) -> bool:
    from eurogas_nexus.db.models import MonitoringAlertRecord

    if not event_key:
        return False
    for alert in (
        session.query(MonitoringAlertRecord)
        .filter(MonitoringAlertRecord.category == NEWS_ROLE_CATEGORIES[role])
        .filter(MonitoringAlertRecord.resolved_at_utc.is_(None))
        .limit(500)
    ):
        evidence = alert.evidence_snapshot or {}
        notified = evidence.get("notified") or {}
        if (evidence.get("item_id") != item_id and evidence.get("linked_event_key") == event_key
                and notified.get("at_utc")
                and now - datetime.fromisoformat(notified["at_utc"]) < COOLDOWN):
            return True
    return False


def react(session, item_id: str, *, now: datetime) -> dict[str, Any]:
    """Raise, refresh or leave the per-role alerts of one item; what was decided per role."""

    from eurogas_nexus.application.news_reads import item_dict
    from eurogas_nexus.application.news_relevance import firm_exposures, matches
    from eurogas_nexus.db.models import MonitoringAlertRecord, NewsItemRecord

    row = session.get(NewsItemRecord, item_id)
    if row is None:
        return {"item_id": item_id, "roles": {}, "queued": False}
    item = item_dict(row)
    found = matches(item, firm_exposures(session, now=now))
    by_role: dict[str, list[dict[str, Any]]] = {}
    for match in found:
        by_role.setdefault(match["role"], []).append(match)
    decisions: dict[str, str] = {}
    queued_any = False
    for role, role_matches in sorted(by_role.items()):
        alert = (
            session.query(MonitoringAlertRecord)
            .filter(MonitoringAlertRecord.fingerprint == fingerprint(item_id, role))
            .one_or_none()
        )
        decision, queued = _raise(session, row, item, role, role_matches, alert, now)
        decisions[role] = decision
        queued_any = queued_any or queued
    return {"item_id": item_id, "roles": decisions, "queued": queued_any}


def _raise(session, row, item, role: str, found: list[dict[str, Any]], alert, now: datetime
           ) -> tuple[str, bool]:
    from eurogas_nexus.application.notifications import queue_notification
    from eurogas_nexus.db.repositories.monitoring import upsert_monitoring_alert
    from eurogas_nexus.domain.monitoring import MonitoringCandidate

    category = NEWS_ROLE_CATEGORIES[role]
    route = route_for(category)
    kinds = set(item["event_types"])
    urgent = bool(kinds & NOTIFY_TYPES) or item["capacity_change"]
    severity = "warning" if urgent else "info"
    published = _aware(row.published_at_utc) or _aware(row.first_seen_at_utc) or now
    recent = now - published <= RECENT
    held = dict(alert.evidence_snapshot or {}) if alert is not None else {}
    notified = held.get("notified")
    refs = sorted(f"{m['kind']}:{m['ref']}" for m in found)
    digest = _digest({"content": row.content_sha256, "refs": refs, "severity": severity})
    reasons = [f"{m['reason']}: book {m['book_id'] or 'unassigned'}, {m['figure']}"
               for m in found[:5]]
    title = f"{row.publisher}: {row.title}"[:240]
    evidence = {
        "item_id": row.item_id,
        "source_id": row.source_id,
        "url": row.url,
        "role": role,
        "for": sorted({f for m in found for f in m["for"]}),
        "book_ids": sorted({m["book_id"] for m in found if m["book_id"]}),
        "matches": found,
        "event_types": list(item["event_types"]),
        "linked_event_key": row.linked_event_key,
        "notified": notified,
        "advisory": "For a person to decide; nothing is traded, nominated or booked.",
    }
    if not urgent or not recent:
        decision = "in_app_only"
    elif notified and notified.get("digest") == digest:
        decision = "duplicate"
    elif notified and now - datetime.fromisoformat(notified["at_utc"]) < COOLDOWN and set(
        refs
    ) <= set(notified.get("refs") or []):
        decision = "cooldown"
    elif _same_event_notified(session, role, row.linked_event_key, row.item_id, now):
        decision = "same_event"
    else:
        decision = "notified"
    queued = False
    if decision == "notified":
        body = "\n".join([
            title,
            *reasons,
            f"Source: {row.publisher}" + (f", {row.url}" if row.url else ""),
            "",
            addressed_line(route),
        ])
        queued = queue_notification(
            session,
            category=route.notification_category,
            severity=severity,
            title=title,
            body=body,
            dedupe_key=f"news:{row.item_id}:{role}:{digest}",
            now=now,
        )
        evidence["notified"] = {"digest": digest, "at_utc": now.isoformat(), "refs": refs,
                                "severity": severity, "category": route.notification_category}
    else:
        evidence["held_back"] = {"reason": decision, "at_utc": now.isoformat()}
    upsert_monitoring_alert(
        session,
        MonitoringCandidate(
            fingerprint=fingerprint(row.item_id, role),
            category=category,
            alert_type="news_item",
            severity=severity,
            title_en=title,
            title_zh_cn=f"{_TITLES_ZH[role]}：{row.title}"[:240],
            message_en=" ".join(reasons)[:2000],
            message_zh_cn=f"{_TITLES_ZH[role]}（{len(found)} 项）。来源：{row.publisher}。"[:2000],
            entity_type="news_item",
            entity_id=row.item_id,
            event_time_utc=published,
            evidence_snapshot=evidence,
            source_refs=[f"news:{row.item_id}", *([row.url] if row.url else [])],
            warnings=[],
            simulated=False,
            human_review_required=True,
        ),
        now_utc=now,
    )
    return decision, queued


def expire_aged(session, *, now: datetime) -> int:
    """Resolve open news alerts not updated for :data:`ALERT_DAYS` days."""

    from eurogas_nexus.db.models import MonitoringAlertRecord

    cutoff = now - timedelta(days=ALERT_DAYS)
    naive = session.get_bind().dialect.name == "sqlite"
    rows = (
        session.query(MonitoringAlertRecord)
        .filter(MonitoringAlertRecord.category.in_(sorted(NEWS_ROLE_CATEGORIES.values())))
        .filter(MonitoringAlertRecord.resolved_at_utc.is_(None))
        .filter(MonitoringAlertRecord.updated_at_utc
                < (cutoff.replace(tzinfo=None) if naive else cutoff))
        .all()
    )
    for alert in rows:
        alert.status = "resolved"
        alert.resolved_at_utc = now
        alert.updated_at_utc = now
    session.flush()
    return len(rows)


__all__ = [
    "ALERT_DAYS",
    "CONSUMER_NAME",
    "COOLDOWN",
    "NOTIFY_TYPES",
    "RECENT",
    "NewsRoutingConsumer",
    "expire_aged",
    "fingerprint",
    "react",
    "register",
]
