"""A database failure no route caught answers the coded 503, not a bare 500 (or a 502).

Most routes turn a database error into 503 ``runtime_db_unavailable`` themselves; a route that
does not used to answer 500 ``internal``, and before the socket-timeout fix a slow read under
load ended in a client-side ``TimeoutError`` that the gateway reported as 502. This middleware
sits innermost: an exception the application raised that is a statement the server cancelled
(``statement_timeout``: 503 ``runtime_db_timeout``) or a lost or unreachable store (503
``runtime_db_unavailable``) is answered with the product's error envelope and ``Retry-After``,
and logged as a warning; anything else goes on to the unexpected-failure handler.

By the time the exception reaches here the request's session has closed, so its connection
went back to the pool rolled back (a cancelled statement leaves it usable) or, when the
connection was lost, was dropped by the pool. Classification reads the exception chain
without importing SQLAlchemy (``core/db_errors.py``), so importing the API stays light.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger(__name__)


class DatabaseFailureMiddleware:
    """Answer an uncaught database timeout or outage with the coded 503."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = False

        async def tracking_send(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, receive, tracking_send)
        except Exception as exc:
            if started:
                raise
            from eurogas_nexus.api.error_handlers import database_failure_exception, error_body

            coded = database_failure_exception(exc)
            if coded is None:
                raise
            state: dict[str, Any] = scope.get("state") or {}
            detail = dict(coded.detail)
            detail.pop("error_class", None)  # operators read the class in the log line
            logger.warning(
                "database %s answered 503 on %s %s: %s",
                detail["code"],
                scope.get("method"),
                scope.get("path"),
                type(exc).__name__,
            )
            body = error_body(503, detail, correlation_id=state.get("request_id"))
            payload = json.dumps(body, default=str).encode("utf-8")
            headers = [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(payload)).encode("ascii")),
            ]
            headers += [
                (key.lower().encode("latin-1"), value.encode("latin-1"))
                for key, value in (coded.headers or {}).items()
            ]
            await send({"type": "http.response.start", "status": 503, "headers": headers})
            await send({"type": "http.response.body", "body": payload})
