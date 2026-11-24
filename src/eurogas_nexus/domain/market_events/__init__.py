"""Canonical market events: identity, revisions, timestamps, priority and staleness (M4).

Pure and deterministic: no database, no network, no clock. The application layer
(:mod:`eurogas_nexus.application.market_events`) persists events in the PostgreSQL outbox
and delivers them to consumers; this package only decides what an event *is*.
"""

from eurogas_nexus.domain.market_events.model import (
    EVENT_TYPES,
    INPUT_CLASS_OF_EVENT_TYPE,
    INPUT_CLASSES,
    EventTimeline,
    HeldRevision,
    MarketEvent,
    MarketEventError,
    PublishDecision,
    PublishKind,
    canonical_json,
    decide_publication,
    default_priority,
)
from eurogas_nexus.domain.market_events.staleness import (
    DEFAULT_EXPECTATION_MINUTES,
    StalenessFinding,
    SubjectLatest,
    evaluate_staleness,
)

__all__ = [
    "DEFAULT_EXPECTATION_MINUTES",
    "EVENT_TYPES",
    "INPUT_CLASSES",
    "INPUT_CLASS_OF_EVENT_TYPE",
    "EventTimeline",
    "HeldRevision",
    "MarketEvent",
    "MarketEventError",
    "PublishDecision",
    "PublishKind",
    "StalenessFinding",
    "SubjectLatest",
    "canonical_json",
    "decide_publication",
    "default_priority",
    "evaluate_staleness",
]
