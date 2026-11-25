"""Transport-neutral wire contracts for optional streaming (dependency-free).

The runtime source of truth for market changes is the PostgreSQL outbox (ADR Decision 28,
``market_events``); clients outside the monolith read it through the DATA-1 change feed
(``GET /api/market/changes``). :class:`MarketChangeV1` is the versioned form of one change
digest on any later transport, so a broker adapter, should a measured need ever justify one
(doc 15 section 4), carries exactly what the feed serves and nothing more:

* **identity and key**: ``event_key`` is the event's identity across revisions (a hash of
  source, type, subject and market time, or an explicit identity such as a REMIT message id).
  :meth:`MarketChangeV1.broker_key` returns it, so every revision of one fact lands in one
  partition and keeps its order; ``(event_key, revision)`` deduplicates a redelivery.
* **dispatch metadata**: ``kind`` and ``schema_version`` travel with the value. A consumer
  decodes a named version and refuses any other (:meth:`MarketChangeV1.decode`).
* **a digest, never a value**: the fields are the change feed's columns without its cursor
  (a feed position, which a broker replaces with its own offsets). Extra fields are refused,
  so a price, a rate or a contract term cannot ride along; a consumer reads the figure through
  the entitled read it already uses, as the feed's clients do.

The contract was proposed on ``research/agentic-decision-architecture`` as a run-level
``opportunity.input.invalidated`` notice (``IngestionInvalidationV1``). The outbox already
records that fact as a ``source.ingested`` event (identity ``run:<run_id>``, the source and
the input class) with revisions, replay and dead letters, so the run-level notice is not
built; this envelope is the outbox event's transport-neutral form instead (CODEX-1).

Nothing here imports a broker client, opens a connection or runs a consumer.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)


@dataclass(frozen=True)
class StreamingEnvelope:
    """Minimal envelope for future optional streaming integrations (Milestone 12 shell)."""

    topic: str
    key: str
    payload_json: str
    published_at_utc: datetime
    research_only: bool = True


Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]

#: The one kind and version this module encodes and decodes.
MARKET_CHANGE_KIND = "market.change"
MARKET_CHANGE_SCHEMA_VERSION = 1


class MarketChangeV1(BaseModel):
    """One market event's change digest, version 1, as any transport would carry it."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["market.change"]
    schema_version: Literal[1]
    event_id: Text
    event_key: Text
    event_type: Text
    operation: Literal["insert", "update"]
    revision: Annotated[int, Field(strict=True, ge=1)]
    supersedes_event_id: Text | None = None
    subject_key: Text
    source_id: Text
    input_class: Text | None = None
    dependency_keys: tuple[Text, ...] = ()
    content_hash: Text
    market_time_utc: AwareDatetime | None = None
    published_at_utc: AwareDatetime | None = None
    ingested_at_utc: AwareDatetime

    @field_validator("event_type")
    @classmethod
    def _known_type(cls, value: str) -> str:
        from eurogas_nexus.domain.market_events.model import EVENT_TYPES

        if value not in EVENT_TYPES:
            raise ValueError(f"unknown event type {value!r}")
        return value

    @field_validator("market_time_utc", "published_at_utc", "ingested_at_utc")
    @classmethod
    def _utc(cls, value: datetime | None) -> datetime | None:
        return None if value is None else value.astimezone(UTC)

    @model_validator(mode="after")
    def _revision_matches_operation(self) -> MarketChangeV1:
        first = self.revision == 1
        if (self.operation == "insert") != first:
            raise ValueError("operation is insert for revision 1 and update after it")
        if first and self.supersedes_event_id is not None:
            raise ValueError("a first revision supersedes nothing")
        if not first and self.supersedes_event_id is None:
            raise ValueError("a later revision names the revision it supersedes")
        return self

    @classmethod
    def from_change(cls, change: Mapping[str, Any]) -> MarketChangeV1:
        """The envelope of one change the feed served (``change_feed.change_row``)."""

        fields = {key: value for key, value in change.items() if key != "cursor"}
        return cls(
            kind=MARKET_CHANGE_KIND, schema_version=MARKET_CHANGE_SCHEMA_VERSION, **fields
        )

    @classmethod
    def decode(cls, raw: str | bytes) -> MarketChangeV1:
        """Decode a wire value; refuses another kind, another version or an extra field."""

        return cls.model_validate_json(raw)

    def broker_key(self) -> str:
        """The partition key: every revision of one fact shares it."""

        return self.event_key

    def to_wire(self) -> str:
        """The value as compact JSON, times in UTC."""

        return self.model_dump_json()


#: The change feed's columns an envelope carries (the feed's cursor excepted).
def market_change_fields() -> tuple[str, ...]:
    return tuple(
        name for name in MarketChangeV1.model_fields if name not in {"kind", "schema_version"}
    )


__all__ = [
    "MARKET_CHANGE_KIND",
    "MARKET_CHANGE_SCHEMA_VERSION",
    "MarketChangeV1",
    "StreamingEnvelope",
    "market_change_fields",
]
