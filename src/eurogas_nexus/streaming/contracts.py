"""Optional streaming message contract shell (dependency-free)."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class StreamingEnvelope:
    """Minimal envelope for future optional streaming integrations."""

    topic: str
    key: str
    payload_json: str
    published_at_utc: datetime
    research_only: bool = True
