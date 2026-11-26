"""Request-ID ASGI middleware.

Every HTTP response carries ``X-Request-Id`` so operators can correlate policy
decisions, audit events, and logs. The id is also exposed as
``request.state.request_id`` to route handlers, and bound to the logging context
(:mod:`eurogas_nexus.core.structured_logging`) so every log record written while the request
is served carries it, and the principal id once the caller is known.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from eurogas_nexus.core import structured_logging


class RequestIdMiddleware:
    """Attach a short request id to every HTTP response."""

    def __init__(self, app: Callable[..., Awaitable[None]]) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = uuid.uuid4().hex[:16]
        state = scope.setdefault("state", {})
        state["request_id"] = request_id
        token = structured_logging.bind_request(request_id, state)

        async def send_with_request_id(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", request_id.encode("ascii")))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            structured_logging.unbind_request(token)
