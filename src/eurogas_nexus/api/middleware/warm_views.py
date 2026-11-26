"""A successful write through the API makes the warm views due (``application/warm_views``).

Any POST, PUT, PATCH or DELETE under ``/api/`` that answers below 400 and is not a pure
computation (``COMPUTE_ONLY_PATHS``) counts: every kept view is refreshed before it is
fresh again, and the writer's own views are recomputed before they are served at all.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from eurogas_nexus.application.warm_views import COMPUTE_ONLY_PATHS, views

_READ_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


class WarmViewWriteMiddleware:
    def __init__(self, app: Callable[..., Awaitable[None]]) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        path = str(scope.get("path", ""))
        if (
            scope["type"] != "http"
            or scope.get("method", "GET") in _READ_METHODS
            or not path.startswith("/api/")
            or any(marker in path for marker in COMPUTE_ONLY_PATHS)
        ):
            await self.app(scope, receive, send)
            return
        status: list[int] = []

        async def capture(message: dict[str, Any]) -> None:
            if message.get("type") == "http.response.start":
                status.append(int(message.get("status", 500)))
            await send(message)

        try:
            await self.app(scope, receive, capture)
        finally:
            if status and status[0] < 400:
                identity = (scope.get("state") or {}).get("identity")
                views().note_write(getattr(identity, "principal_id", None))
