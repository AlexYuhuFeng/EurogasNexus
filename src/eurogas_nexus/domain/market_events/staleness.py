"""Which event subjects have gone stale (M4).

A subject is stale when its newest event was ingested longer ago than the expectation for its
input class. The three-state rule is the product's one freshness rule
(:func:`eurogas_nexus.domain.monitoring.freshness.evaluate_freshness`): no expectation or no
event is ``unknown``, never ``live``.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime

from eurogas_nexus.domain.monitoring.freshness import FreshnessStatus, evaluate_freshness

#: Minutes an input class may go without a new event before it is stale. Prices and outages
#: move within the gas day; tariffs and assumptions change rarely and have no expectation.
DEFAULT_EXPECTATION_MINUTES: dict[str, int] = {
    "prices": 24 * 60,
    "fx": 3 * 24 * 60,
    "rates": 3 * 24 * 60,
    "outages": 6 * 60,
    "capacity": 24 * 60,
}


@dataclass(frozen=True)
class SubjectLatest:
    """The newest event held for one subject."""

    subject_key: str
    source_id: str
    input_class: str | None
    last_ingested_at_utc: datetime | None


@dataclass(frozen=True)
class StalenessFinding:
    """One subject's freshness."""

    subject_key: str
    source_id: str
    input_class: str | None
    status: FreshnessStatus
    expectation_minutes: int | None
    last_ingested_at_utc: datetime | None

    def to_json(self) -> dict:
        return {
            "subject_key": self.subject_key,
            "source_id": self.source_id,
            "input_class": self.input_class,
            "status": self.status.value,
            "expectation_minutes": self.expectation_minutes,
            "last_ingested_at_utc": (
                self.last_ingested_at_utc.isoformat() if self.last_ingested_at_utc else None
            ),
        }


def evaluate_staleness(
    latest: Iterable[SubjectLatest],
    *,
    now_utc: datetime,
    expectations: Mapping[str, int] | None = None,
) -> list[StalenessFinding]:
    """Every subject's freshness, stale first, then unknown, then live (each by subject)."""

    minutes_by_class = DEFAULT_EXPECTATION_MINUTES if expectations is None else expectations
    order = {FreshnessStatus.STALE: 0, FreshnessStatus.UNKNOWN: 1, FreshnessStatus.LIVE: 2}
    findings = []
    for item in latest:
        minutes = minutes_by_class.get(item.input_class or "")
        status = evaluate_freshness(minutes or 0, item.last_ingested_at_utc, now_utc)
        findings.append(
            StalenessFinding(
                subject_key=item.subject_key,
                source_id=item.source_id,
                input_class=item.input_class,
                status=status,
                expectation_minutes=minutes,
                last_ingested_at_utc=item.last_ingested_at_utc,
            )
        )
    return sorted(findings, key=lambda item: (order[item.status], item.subject_key))


__all__ = [
    "DEFAULT_EXPECTATION_MINUTES",
    "StalenessFinding",
    "SubjectLatest",
    "evaluate_staleness",
]
