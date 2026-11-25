"""Transport-neutral envelopes for optional streaming and internal invalidation."""

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, StringConstraints, field_validator


@dataclass(frozen=True)
class StreamingEnvelope:
    """Minimal envelope for future optional streaming integrations."""

    topic: str
    key: str
    payload_json: str
    published_at_utc: datetime
    research_only: bool = True


class OpportunityInputClass(StrEnum):
    PRICES = "prices"
    TARIFFS = "tariffs"
    OUTAGES = "outages"
    BOOK = "book"
    MARKS = "marks"
    ASSUMPTIONS = "assumptions"
    LIMITS = "limits"
    FX = "fx"
    RATES = "rates"
    CAPACITY = "capacity"
    FREIGHT = "freight"


EventIdentifier = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)
]


class IngestionInvalidationV1(BaseModel):
    """One source ingestion run that dirtied an opportunity input class.

    Identity is the source/run pair. Noticed time belongs to the scheduler and
    makes no claim about individual observations' effective or publication time.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    event_type: Literal["opportunity.input.invalidated"]
    schema_version: Literal[1]
    source_id: EventIdentifier
    run_id: EventIdentifier
    input_class: OpportunityInputClass
    noticed_at_utc: AwareDatetime

    @field_validator("noticed_at_utc")
    @classmethod
    def _utc(cls, value: datetime) -> datetime:
        return value.astimezone(UTC)
