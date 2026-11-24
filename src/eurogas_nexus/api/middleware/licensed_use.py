"""One licensed-data usage meter per API request (GOV-1, lesson P6).

The entitlement checks note each licensed source family they let the caller read; when the
response has been sent, the families are counted once each in ``licensed_data_use`` under
the caller and the route template (``application/licensed_use.record_request_use``), off the
event loop. A request that read no licensed family writes nothing.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from anyio import to_thread

from eurogas_nexus.application.licensed_use import record_request_use
from eurogas_nexus.governance.usage import metering


def _route(scope: dict[str, Any]) -> str:
    route = scope.get("route")
    template = getattr(route, "path_format", None) or getattr(route, "path", None)
    return f"{scope.get('method', 'GET')} {template or scope.get('path', '')}"


class LicensedUseMiddleware:
    """Meter the licensed families a request reads and record them when it ends."""

    def __init__(self, app: Callable[..., Awaitable[None]]) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http" or not str(scope.get("path", "")).startswith("/api/"):
            await self.app(scope, receive, send)
            return
        with metering() as meter:
            await self.app(scope, receive, send)
        if meter.families:
            identity = (scope.get("state") or {}).get("identity")
            await to_thread.run_sync(
                lambda: record_request_use(
                    meter,
                    principal_id=getattr(identity, "principal_id", None),
                    route=_route(scope),
                )
            )
