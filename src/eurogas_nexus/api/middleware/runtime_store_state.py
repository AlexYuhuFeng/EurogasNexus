"""One rule for a read answered without a runtime database (backend audit 2026-11-26, A3).

Before this, a read on a deployment with no runtime database answered in one of four ways:
an empty list with an English warning, an empty list with a code as its warning, an empty
list with nothing at all (``/api/portfolio/books``, ``/api/portfolio/map-situation``,
``/api/research/spread-series``, ``/api/route-cost/tariff-publications``), or a 503 under
one of four spellings of the code. An empty outage list with no warning reads as "no
outages", which a trader acts on.

The rule now: a read that needs the store and cannot do without it refuses with 503
``runtime_db_required`` (the four spellings are reported as that code by the taxonomy's
``CODE_ALIASES``); a read that answers anyway carries
``meta.runtime_store = {"state": "not_configured", "code": "runtime_db_required"}``, added
here for every enveloped ``/api/`` answer so no route can forget it. The route's own
warnings are kept. A deployment with a database configured never enters this path.
"""

from __future__ import annotations

import json
from typing import Any

from starlette.types import ASGIApp, Message, Receive, Scope, Send

RUNTIME_STORE_NOT_CONFIGURED = {"state": "not_configured", "code": "runtime_db_required"}


def _store_configured() -> bool:
    from eurogas_nexus.core.config import resolve_db_dsn_from_env

    return resolve_db_dsn_from_env() is not None


class RuntimeStoreStateMiddleware:
    """Mark every enveloped read answered without a runtime database as such."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or not str(scope.get("path", "")).startswith("/api/")
            or _store_configured()
        ):
            await self.app(scope, receive, send)
            return

        start: dict[str, Any] = {}
        chunks: list[bytes] = []

        async def capture(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = dict(message.get("headers") or [])
                content_type = headers.get(b"content-type", b"")
                if message.get("status") == 200 and content_type.startswith(b"application/json"):
                    start.update(message)
                    return
                await send(message)
                return
            if message["type"] == "http.response.body" and start:
                chunks.append(message.get("body", b""))
                if message.get("more_body"):
                    return
                body = b"".join(chunks)
                body = _marked(body)
                headers = [
                    (name, value)
                    for name, value in start.get("headers") or []
                    if name.lower() != b"content-length"
                ]
                headers.append((b"content-length", str(len(body)).encode("ascii")))
                await send({**start, "headers": headers})
                await send({"type": "http.response.body", "body": body})
                return
            await send(message)

        await self.app(scope, receive, capture)


def _marked(body: bytes) -> bytes:
    try:
        payload = json.loads(body)
    except ValueError:
        return body
    if not isinstance(payload, dict) or not isinstance(payload.get("meta"), dict):
        return body
    payload["meta"]["runtime_store"] = dict(RUNTIME_STORE_NOT_CONFIGURED)
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
