"""What a market event is: identity, content, revisions, timestamps and priority (M4).

A market event says that one *subject* (a hub delivery period, an outage message, a contract,
a tariff, a source's ingestion) changed, which input keys of the valuation snapshot that
change touches, and five distinct times:

==========================  ================================================================
``market_time_utc``         When the market fact applies (a settlement day, an outage start).
``published_at_utc``        When the source published it (``None``: the source does not say).
``ingested_at_utc``         When this platform recorded it.
``processed_at_utc``        When a consumer finished with it (per consumer, set by the outbox).
``notified_at_utc``         When a person was told of its consequence (set by the consumer
                            that notifies; ``None`` when nobody needed telling).
==========================  ================================================================

Identity
--------
``event_key`` is a hash of the event's *identity*: source, type, subject and market time,
unless the producer gives an explicit ``identity`` (a REMIT message keeps its message id across
revisions even when its start time moves). ``content_hash`` is a hash of what the event says
(payload, dependency keys, input class, market time). Publication and ingestion times are not
content: the same fact re-published later is the same fact.

Revisions
---------
:func:`decide_publication` compares an incoming event with the revisions already held for its
``event_key``:

* same content as the latest revision: ``duplicate`` (idempotent; nothing is written);
* content equal to an older revision, or published strictly before the latest revision: the
  source is replaying history out of order: ``out_of_order`` (nothing is written, the latest
  revision stands);
* otherwise ``revision`` ``n + 1`` superseding ``n`` (``new`` with revision 1 when nothing is
  held).

The event id of a revision is derived from ``event_key`` and the revision number, so replaying
the same source history reproduces the same ids.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Any

#: The input classes of the opportunity evaluation (``application/opportunities/schedule``).
#: Kept here so the domain does not import the application; a test holds the two equal.
INPUT_CLASSES = frozenset(
    {
        "prices",
        "tariffs",
        "outages",
        "book",
        "marks",
        "assumptions",
        "limits",
        "fx",
        "rates",
        "capacity",
        "freight",
    }
)

#: Event types and the input class each one changes by default (``None``: no evaluator input;
#: a ``source.ingested`` event states its class explicitly from the source's category).
INPUT_CLASS_OF_EVENT_TYPE: dict[str, str | None] = {
    "price.updated": "prices",
    "fx.updated": "fx",
    "rate.updated": "rates",
    "tariff.changed": "tariffs",
    "outage.published": "outages",
    "capacity.changed": "capacity",
    "contract.changed": "book",
    "mark.changed": "marks",
    "assumption.changed": "assumptions",
    "limit.changed": "limits",
    "freight.changed": "freight",
    "source.ingested": None,
    "fundamental.updated": None,
    "weather.updated": None,
}
EVENT_TYPES = frozenset(INPUT_CLASS_OF_EVENT_TYPE)

#: Lower is more urgent. An outage can strand a position within the gas day; a book or limit
#: change alters what the firm holds; a price moves values; reference rates move them least.
_PRIORITY = {
    "outage.published": 0,
    "contract.changed": 1,
    "limit.changed": 1,
    "mark.changed": 1,
    "price.updated": 2,
    "tariff.changed": 2,
    "capacity.changed": 2,
    "source.ingested": 3,
    "fx.updated": 3,
    "rate.updated": 3,
    "assumption.changed": 3,
    "freight.changed": 3,
}
LOWEST_PRIORITY = 4

#: How far a source's publication time may run ahead of our ingestion clock before the
#: timeline is reported as inconsistent (source clocks are not ours).
CLOCK_SKEW = timedelta(minutes=5)

_KEY_PREFIXES = ("hub:", "fx:", "rate:", "tariff:", "outage:", "contract:", "assumption:")


class MarketEventError(ValueError):
    """An event that cannot be published as stated (names the rule broken)."""


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _plain(value: Any) -> Any:
    """A JSON-safe, order-stable copy (Decimals as strings, times as ISO 8601 UTC)."""

    if isinstance(value, Mapping):
        return {str(key): _plain(value[key]) for key in sorted(value, key=str)}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted(_plain(item) for item in value)
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise MarketEventError("payload holds a non-finite number")
        return format(value.normalize(), "f")
    if isinstance(value, datetime):
        return _aware(value).astimezone(UTC).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise MarketEventError("payload holds a non-finite number")
        return value
    if value is None or isinstance(value, (str, int, bool)):
        return value
    raise MarketEventError(f"payload value of type {type(value).__name__} is not JSON-safe")


def canonical_json(value: Any) -> str:
    """The canonical text an event's hashes are taken over."""

    return json.dumps(_plain(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("ascii")).hexdigest()[:40]


def default_priority(event_type: str) -> int:
    """The default urgency of an event type (0 is the most urgent)."""

    return _PRIORITY.get(event_type, LOWEST_PRIORITY)


@dataclass(frozen=True)
class MarketEvent:
    """One canonical market event, as a producer states it.

    Attributes:
        source_id: The source or writer (``src-eex``, ``src-remit-umm``, ``firm-marks``).
        event_type: One of :data:`EVENT_TYPES`.
        subject_key: What changed (``hub:TTF:2027-01``, ``outage:<message>``,
            ``ingestion:src-eex``).
        ingested_at_utc: When this platform recorded it.
        market_time_utc: When the fact applies (``None`` when it has no single time).
        published_at_utc: When the source published it (``None``: not stated by the source).
        payload: What the event says (JSON-safe; Decimals and times are canonicalised).
        dependency_keys: The snapshot input keys the change touches (design J.2 key format).
            Defaults to the subject key when it is one.
        input_class: The opportunity input class it changes (defaults from the event type).
        priority: 0 (most urgent) to 4; defaults from the event type.
        identity: An explicit identity (a message id that survives revisions); defaults to
            source, type, subject and market time.
        correlation_id: What produced it (an ingestion run, a request).
    """

    source_id: str
    event_type: str
    subject_key: str
    ingested_at_utc: datetime
    market_time_utc: datetime | None = None
    published_at_utc: datetime | None = None
    payload: Mapping[str, Any] = field(default_factory=dict)
    dependency_keys: tuple[str, ...] = ()
    input_class: str | None = None
    priority: int | None = None
    identity: str | None = None
    correlation_id: str | None = None

    def __post_init__(self) -> None:
        if not self.source_id or len(self.source_id) > 64:
            raise MarketEventError("source_id must be 1-64 characters")
        if self.event_type not in EVENT_TYPES:
            raise MarketEventError(f"unknown event type {self.event_type!r}")
        if not self.subject_key or len(self.subject_key) > 160:
            raise MarketEventError("subject_key must be 1-160 characters")
        if self.ingested_at_utc is None:
            raise MarketEventError("ingested_at_utc is required")
        for name in ("ingested_at_utc", "market_time_utc", "published_at_utc"):
            object.__setattr__(self, name, _aware(getattr(self, name)))
        keys = tuple(sorted(set(self.dependency_keys)))
        if not keys and self.subject_key.startswith(_KEY_PREFIXES):
            keys = (self.subject_key,)
        for key in keys:
            if not key or len(key) > 160:
                raise MarketEventError("dependency keys must be 1-160 characters")
        object.__setattr__(self, "dependency_keys", keys)
        input_class = self.input_class or INPUT_CLASS_OF_EVENT_TYPE[self.event_type]
        if input_class is not None and input_class not in INPUT_CLASSES:
            raise MarketEventError(f"unknown input class {input_class!r}")
        object.__setattr__(self, "input_class", input_class)
        priority = default_priority(self.event_type) if self.priority is None else self.priority
        if not 0 <= priority <= LOWEST_PRIORITY:
            raise MarketEventError("priority must be 0-4")
        object.__setattr__(self, "priority", priority)
        object.__setattr__(self, "payload", _plain(dict(self.payload)))
        if (
            self.published_at_utc is not None
            and self.published_at_utc - CLOCK_SKEW > self.ingested_at_utc
        ):
            raise MarketEventError("published after it was ingested (beyond clock skew)")

    @property
    def event_key(self) -> str:
        """The stable identity every revision of this event shares."""

        if self.identity:
            return _digest(["identity", self.source_id, self.event_type, self.identity])
        return _digest(
            [self.source_id, self.event_type, self.subject_key, _plain(self.market_time_utc)]
        )

    @property
    def content_hash(self) -> str:
        """What the event says (publication and ingestion times excluded)."""

        return _digest(
            {
                "payload": self.payload,
                "dependency_keys": list(self.dependency_keys),
                "input_class": self.input_class,
                "market_time_utc": _plain(self.market_time_utc),
                "subject_key": self.subject_key,
            }
        )

    def event_id(self, revision: int) -> str:
        """The deterministic id of this event's ``revision``."""

        if revision < 1:
            raise MarketEventError("revisions start at 1")
        return f"mev-{self.event_key[:24]}-r{revision}"


class PublishKind(StrEnum):
    """What publishing an event does to the store."""

    NEW = "new"
    REVISION = "revision"
    DUPLICATE = "duplicate"
    OUT_OF_ORDER = "out_of_order"


@dataclass(frozen=True)
class HeldRevision:
    """A revision already in the store for the same ``event_key``."""

    revision: int
    content_hash: str
    published_at_utc: datetime | None = None


@dataclass(frozen=True)
class PublishDecision:
    """The outcome of :func:`decide_publication`."""

    kind: PublishKind
    revision: int
    supersedes_revision: int | None = None
    reason: str = ""

    @property
    def writes(self) -> bool:
        """Whether the store gains a row."""

        return self.kind in {PublishKind.NEW, PublishKind.REVISION}


def decide_publication(event: MarketEvent, held: Sequence[HeldRevision]) -> PublishDecision:
    """Decide whether ``event`` is new, a revision, a duplicate or an out-of-order replay."""

    if not held:
        return PublishDecision(PublishKind.NEW, 1)
    ordered = sorted(held, key=lambda item: item.revision)
    latest = ordered[-1]
    if event.content_hash == latest.content_hash:
        return PublishDecision(
            PublishKind.DUPLICATE, latest.revision, reason="same content as the latest revision"
        )
    if any(item.content_hash == event.content_hash for item in ordered[:-1]):
        return PublishDecision(
            PublishKind.OUT_OF_ORDER,
            latest.revision,
            reason="content of an older revision; the latest revision stands",
        )
    latest_published = _aware(latest.published_at_utc)
    if (
        event.published_at_utc is not None
        and latest_published is not None
        and event.published_at_utc < latest_published
    ):
        return PublishDecision(
            PublishKind.OUT_OF_ORDER,
            latest.revision,
            reason="published before the latest revision; the latest revision stands",
        )
    return PublishDecision(
        PublishKind.REVISION, latest.revision + 1, supersedes_revision=latest.revision
    )


@dataclass(frozen=True)
class EventTimeline:
    """The five times of one event as one consumer saw it, and the latencies between them."""

    market_time_utc: datetime | None
    published_at_utc: datetime | None
    ingested_at_utc: datetime
    processed_at_utc: datetime | None = None
    notified_at_utc: datetime | None = None

    def latencies_seconds(self) -> dict[str, float | None]:
        """Publication to ingestion, ingestion to processing, processing to notification."""

        def gap(start: datetime | None, end: datetime | None) -> float | None:
            if start is None or end is None:
                return None
            return (_aware(end) - _aware(start)).total_seconds()

        return {
            "publication_to_ingestion": gap(self.published_at_utc, self.ingested_at_utc),
            "ingestion_to_processing": gap(self.ingested_at_utc, self.processed_at_utc),
            "processing_to_notification": gap(self.processed_at_utc, self.notified_at_utc),
        }

    def issues(self) -> list[str]:
        """Orderings that cannot be true (each named), empty when the timeline is consistent."""

        found: list[str] = []
        ingested = _aware(self.ingested_at_utc)
        published = _aware(self.published_at_utc)
        processed = _aware(self.processed_at_utc)
        notified = _aware(self.notified_at_utc)
        if published is not None and published - CLOCK_SKEW > ingested:
            found.append("published_after_ingested")
        if processed is not None and processed < ingested:
            found.append("processed_before_ingested")
        if notified is not None and (processed is None or notified < processed):
            found.append("notified_before_processed")
        return found


__all__ = [
    "CLOCK_SKEW",
    "EVENT_TYPES",
    "INPUT_CLASSES",
    "INPUT_CLASS_OF_EVENT_TYPE",
    "LOWEST_PRIORITY",
    "EventTimeline",
    "HeldRevision",
    "MarketEvent",
    "MarketEventError",
    "PublishDecision",
    "PublishKind",
    "canonical_json",
    "decide_publication",
    "default_priority",
]
