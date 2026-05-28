"""Runtime-store interface shells (import-safe, optional)."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class HeartbeatRecord:
    """Ephemeral service heartbeat record."""

    service_name: str
    instance_id: str
    observed_at_utc: str


class RuntimeStore(Protocol):
    """Optional runtime-store abstraction for ephemeral state."""

    def get_heartbeat(self, service_name: str, instance_id: str) -> HeartbeatRecord | None: ...
