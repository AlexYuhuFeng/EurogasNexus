"""Deterministic, time-bounded audit retrieval (#59).

An investigator walks every matching audit event exactly once, past any page size:

- the walk is anchored to a high-water mark fixed on the first page, so events written while
  it runs (including the audit of the read itself) never shift it;
- events are ordered by (timestamp, event id), so tied timestamps have a stable order;
- the continuation cursor carries the anchor and the last (timestamp, id) seen, and a digest
  of the filters it was issued for; using it with other filters is refused.

The cursor is position, not authority: every page re-checks ``audit.read`` on the server.
"""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

CURSOR_VERSION = 1


class AuditCursorError(ValueError):
    """A cursor or window bound the server refuses, with a stable error code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class AuditFilters:
    actor: str = ""
    action: str = ""
    resource: str = ""
    outcome: str = ""
    start_utc: str = ""
    end_utc: str = ""

    def digest(self) -> str:
        canonical = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]


@dataclass(frozen=True)
class AuditPosition:
    anchor: datetime
    last_ts: datetime
    last_id: str


def _utc(value: datetime) -> datetime:
    return (value if value.tzinfo else value.replace(tzinfo=UTC)).astimezone(UTC)


def parse_window_bound(value: str | None, name: str) -> datetime | None:
    """A UTC window bound from an ISO-8601 instant with an explicit offset, or None."""

    if value is None or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise AuditCursorError(
            "audit_window_invalid", f"{name} is not an ISO-8601 instant"
        ) from exc
    if parsed.tzinfo is None:
        raise AuditCursorError(
            "audit_window_timezone_required", f"{name} needs an explicit UTC offset"
        )
    return parsed.astimezone(UTC)


def encode_cursor(
    *, anchor: datetime, last_ts: datetime, last_id: str, filters: AuditFilters
) -> str:
    payload = {
        "v": CURSOR_VERSION,
        "a": _utc(anchor).isoformat(),
        "t": _utc(last_ts).isoformat(),
        "i": last_id,
        "f": filters.digest(),
    }
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_cursor(cursor: str, filters: AuditFilters) -> AuditPosition:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
        if payload.get("v") != CURSOR_VERSION:
            raise ValueError("version")
        position = AuditPosition(
            anchor=_utc(datetime.fromisoformat(payload["a"])),
            last_ts=_utc(datetime.fromisoformat(payload["t"])),
            last_id=str(payload["i"]),
        )
        digest = str(payload["f"])
    except (ValueError, KeyError, TypeError) as exc:
        raise AuditCursorError(
            "audit_cursor_invalid", "the continuation cursor is not valid"
        ) from exc
    if digest != filters.digest():
        raise AuditCursorError(
            "audit_cursor_filter_mismatch",
            "the continuation cursor was issued for other filters; start a new search",
        )
    return position
