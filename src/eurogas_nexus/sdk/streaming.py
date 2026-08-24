"""SDK streaming client for the SSE decision feeds.

Consumes ``/api/stream/quotes|opportunities|alerts`` with resumable cursors:
the backend emits ``id: <ts>|<pk>`` per event and honors ``Last-Event-ID``,
so a consumer can reconnect at exactly the last seen row (including rows that
share one timestamp).

``iter_sse`` is a pure parser (unit-testable); ``stream_events`` is a thin
HTTP generator that attaches release-profile auth headers.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from typing import Any

import httpx

from eurogas_nexus.sdk._http import auth_headers

SSE_DEFAULT_TIMEOUT = 30.0


def iter_sse(lines: Iterable[str]) -> Iterator[dict[str, Any]]:
    """Parse SSE wire lines into ``{event, id, data}`` events.

    ``data:`` blocks are joined with newlines; comment lines (``:``) are
    dropped; a blank line dispatches the accumulated event.
    """

    event = "message"
    event_id: str | None = None
    data_lines: list[str] = []
    for line in lines:
        stripped = line.rstrip("\n")
        if stripped == "":
            if data_lines:
                yield {
                    "event": event,
                    "id": event_id,
                    "data": "\n".join(data_lines),
                }
            event = "message"
            event_id = None
            data_lines = []
        elif stripped.startswith(":"):
            continue
        elif stripped.startswith("id:"):
            event_id = stripped[3:].strip()
        elif stripped.startswith("event:"):
            event = stripped[6:].strip() or event
        elif stripped.startswith("data:"):
            data_lines.append(stripped[5:].strip())


def stream_events(
    base_url: str,
    path: str,
    *,
    last_event_id: str | None = None,
    timeout: float = SSE_DEFAULT_TIMEOUT,
) -> Iterator[dict[str, Any]]:
    """Yield SSE events from one decision stream, resuming at last_event_id."""

    url = f"{base_url.rstrip('/')}/api/{path.lstrip('/')}"
    headers = {**auth_headers(), "Accept": "text/event-stream"}
    if last_event_id:
        headers["Last-Event-ID"] = last_event_id
    with httpx.stream(
        "GET",
        url,
        headers=headers,
        timeout=timeout,
    ) as response:
        response.raise_for_status()
        for event in iter_sse(response.iter_lines()):
            payload = event["data"]
            try:
                event["data"] = json.loads(payload)
            except ValueError:
                pass  # keep raw text for non-JSON events
            yield event
