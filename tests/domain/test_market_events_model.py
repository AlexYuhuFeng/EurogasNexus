"""Canonical market events (M4): identity, content, revisions, timeline, priority, staleness."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from eurogas_nexus.application.opportunities.schedule import INPUT_CLASSES as SCHEDULE_CLASSES
from eurogas_nexus.domain.market_events import (
    INPUT_CLASSES,
    EventTimeline,
    HeldRevision,
    MarketEvent,
    MarketEventError,
    PublishKind,
    SubjectLatest,
    canonical_json,
    decide_publication,
    default_priority,
    evaluate_staleness,
)
from eurogas_nexus.domain.monitoring.freshness import FreshnessStatus

NOW = datetime(2026, 11, 24, 9, 0, tzinfo=UTC)


def _price(value="31.25", **kw) -> MarketEvent:
    base = {
        "source_id": "src-eex",
        "event_type": "price.updated",
        "subject_key": "hub:TTF:2027-01",
        "ingested_at_utc": NOW,
        "market_time_utc": datetime(2026, 11, 23, tzinfo=UTC),
        "published_at_utc": NOW - timedelta(minutes=30),
        "payload": {"settlement": Decimal(value), "unit": "EUR/MWh"},
    }
    base.update(kw)
    return MarketEvent(**base)


def test_the_domain_input_classes_are_the_evaluation_input_classes() -> None:
    assert INPUT_CLASSES == SCHEDULE_CLASSES


def test_defaults_come_from_the_event_type_and_subject() -> None:
    event = _price()
    assert event.input_class == "prices"
    assert event.priority == 2
    assert event.dependency_keys == ("hub:TTF:2027-01",)
    assert default_priority("outage.published") == 0
    assert default_priority("weather.updated") == 4
    # A subject that is not an input key gives no dependency key by default.
    assert MarketEvent("src-x", "source.ingested", "ingestion:src-x", NOW).dependency_keys == ()


def test_identity_ignores_publication_and_ingestion_times_and_payload() -> None:
    first = _price()
    later = _price(ingested_at_utc=NOW + timedelta(hours=1), published_at_utc=NOW)
    corrected = _price(value="31.40")
    assert first.event_key == later.event_key == corrected.event_key
    assert first.content_hash == later.content_hash
    assert first.content_hash != corrected.content_hash
    # Decimal scale does not change content; another market day is another event.
    assert _price(value="31.250").content_hash == first.content_hash
    other_day = _price(market_time_utc=datetime(2026, 11, 24, tzinfo=UTC))
    assert other_day.event_key != first.event_key
    assert first.event_id(1) == f"mev-{first.event_key[:24]}-r1"


def test_an_explicit_identity_survives_a_moved_start_time() -> None:
    def umm(start):
        return MarketEvent(
            "src-remit-umm",
            "outage.published",
            "outage:UMM-77",
            NOW,
            market_time_utc=start,
            identity="UMM-77",
            payload={"unavailable_mcm_d": 12},
        )

    moved = umm(datetime(2026, 11, 26, tzinfo=UTC))
    assert umm(datetime(2026, 11, 25, tzinfo=UTC)).event_key == moved.event_key
    assert moved.priority == 0 and moved.input_class == "outages"


def test_the_publication_decision() -> None:
    first, correction = _price(), _price(value="31.40")
    assert decide_publication(first, []).kind is PublishKind.NEW
    held = [HeldRevision(1, first.content_hash, first.published_at_utc)]
    assert decide_publication(first, held).kind is PublishKind.DUPLICATE
    revision = decide_publication(correction, held)
    assert (revision.kind, revision.revision, revision.supersedes_revision) == (
        PublishKind.REVISION, 2, 1,
    )
    assert revision.writes
    both = [*held, HeldRevision(2, correction.content_hash, correction.published_at_utc)]
    # The source replays the first figure after its correction: the correction stands.
    replayed = decide_publication(first, both)
    assert replayed.kind is PublishKind.OUT_OF_ORDER and not replayed.writes
    # A new figure published before the latest revision is history arriving late.
    late = _price(value="30.00", published_at_utc=NOW - timedelta(hours=2))
    assert decide_publication(late, both).kind is PublishKind.OUT_OF_ORDER
    # The source goes back to the first figure in a later publication: that is news.
    back = _price(published_at_utc=correction.published_at_utc + timedelta(minutes=5))
    assert back.content_hash == first.content_hash
    restored = decide_publication(back, both)
    assert (restored.kind, restored.revision, restored.supersedes_revision) == (
        PublishKind.REVISION, 3, 2,
    )


@pytest.mark.parametrize(
    ("change", "rule"),
    [
        ({"event_type": "price.moved"}, "unknown event type"),
        ({"subject_key": ""}, "subject_key"),
        ({"input_class": "weather"}, "unknown input class"),
        ({"priority": 9}, "priority"),
        ({"published_at_utc": NOW + timedelta(hours=1)}, "published after"),
        ({"payload": {"x": float("nan")}}, "non-finite"),
        ({"payload": {"x": object()}}, "JSON-safe"),
    ],
)
def test_events_that_cannot_be_published(change, rule) -> None:
    with pytest.raises(MarketEventError, match=rule):
        _price(**change)


def test_canonical_json_is_order_and_type_stable() -> None:
    assert canonical_json({"b": Decimal("1.50"), "a": [NOW]}) == canonical_json(
        {"a": (NOW,), "b": Decimal("1.5")}
    )


def test_the_timeline_names_impossible_orderings_and_latencies() -> None:
    line = EventTimeline(
        market_time_utc=NOW - timedelta(days=1),
        published_at_utc=NOW - timedelta(seconds=90),
        ingested_at_utc=NOW,
        processed_at_utc=NOW + timedelta(seconds=4),
        notified_at_utc=NOW + timedelta(seconds=10),
    )
    assert line.issues() == []
    assert line.latencies_seconds() == {
        "publication_to_ingestion": 90.0,
        "ingestion_to_processing": 4.0,
        "processing_to_notification": 6.0,
    }
    broken = EventTimeline(None, None, NOW, NOW - timedelta(seconds=1), NOW - timedelta(seconds=2))
    assert broken.issues() == ["processed_before_ingested", "notified_before_processed"]


def test_staleness_uses_the_one_freshness_rule() -> None:
    findings = evaluate_staleness(
        [
            SubjectLatest("hub:TTF:2027-01", "src-eex", "prices", NOW - timedelta(hours=2)),
            SubjectLatest("outage:UMM-77", "src-remit-umm", "outages", NOW - timedelta(hours=7)),
            SubjectLatest("assumption:lng.speed", "desk", "assumptions", NOW),
        ],
        now_utc=NOW,
    )
    assert [(f.subject_key, f.status) for f in findings] == [
        ("outage:UMM-77", FreshnessStatus.STALE),
        ("assumption:lng.speed", FreshnessStatus.UNKNOWN),  # no expectation: never live
        ("hub:TTF:2027-01", FreshnessStatus.LIVE),
    ]
    assert findings[0].to_json()["expectation_minutes"] == 360
