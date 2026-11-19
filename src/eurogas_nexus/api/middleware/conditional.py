"""Conditional reads: an ETag on every JSON read, and 304 Not Modified when it has not changed.

A page that re-reads on return or on a timer (the map, the market context every 10 s) used to
receive the whole answer each time even when nothing had changed. Each successful GET under
``/api/`` now carries a weak ETag of its body and ``Cache-Control: private, no-cache``: the
browser keeps the answer in its private cache and revalidates it on every use (it sends
``If-None-Match``), and the server answers ``304`` with no body when the read is unchanged.

The server still computes the read; what is saved is the transfer, the parse and, on the
client, the re-render of an unchanged answer. The ETag is a hash of the caller's own answer, so
a 304 is only ever given to a caller whose answer is unchanged (another principal's answer has
its own body and its own hash).

Most reads say when they were evaluated (``as_of_utc`` of a projection computed now, a feed's
``evaluated_at_utc``, a schedule's ``next_expected_at_utc`` counted from now). Those moments
(:data:`CLOCK_KEYS`) are left out of the hash: an answer that differs only by when it was
computed is unchanged, and the client keeps the one it holds, which then reads as of its own,
earlier, moment (never newer than it is). The client says when it last confirmed it.

Never on the reads that carry a session secret (``/api/me``: the CSRF token; ``/api/auth/*``,
``/api/dev/*``, ``/api/credentials``), on streams, or on a response that already says how it
may be cached (``no-store`` reports, sign-in).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

#: Never given an ETag: they carry session secrets, or are streams.
_EXCLUDED_PREFIXES = ("/api/me", "/api/auth", "/api/dev", "/api/stream", "/api/credentials")

#: Bodies larger than this are passed through unhashed (exports, documents).
MAX_HASHED_BYTES = 8 * 1024 * 1024

#: Keys that say when an answer was computed, not what it says: not part of its tag.
CLOCK_KEYS = frozenset(
    {"as_of_utc", "evaluated_at_utc", "generated_at_utc", "next_expected_at_utc"}
)


def weak_etag(body: bytes) -> str:
    return f'W/"{hashlib.blake2b(body, digest_size=16).hexdigest()}"'


def _without_clock(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _without_clock(v) for k, v in value.items() if k not in CLOCK_KEYS}
    if isinstance(value, list):
        return [_without_clock(item) for item in value]
    return value


def content_etag(body: bytes) -> str:
    """The tag of a JSON answer's content: its bytes without the clock keys."""

    if not any(key.encode() in body for key in CLOCK_KEYS):
        return weak_etag(body)
    try:
        parsed = json.loads(body)
    except ValueError:
        return weak_etag(body)
    stable = json.dumps(_without_clock(parsed), sort_keys=True, separators=(",", ":"))
    return weak_etag(stable.encode())


def if_none_match_matches(if_none_match: str | None, etag: str) -> bool:
    if not if_none_match:
        return False
    wanted = etag.removeprefix("W/")
    for candidate in if_none_match.split(","):
        candidate = candidate.strip()
        if candidate == "*" or candidate.removeprefix("W/") == wanted:
            return True
    return False


class ConditionalReadMiddleware:
    """Weak ETag and 304 for successful JSON GET reads under ``/api/`` (see module doc)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "") if scope["type"] == "http" else ""
        if not (
            scope["type"] == "http"
            and scope.get("method") == "GET"
            and path.startswith("/api/")
            and not path.startswith(_EXCLUDED_PREFIXES)
        ):
            await self.app(scope, receive, send)
            return
        if_none_match = Headers(scope=scope).get("if-none-match")
        start: Message | None = None
        chunks: list[bytes] = []
        size = 0
        passthrough = False

        async def buffered(message: Message) -> None:
            nonlocal start, size, passthrough
            if passthrough:
                await send(message)
                return
            if message["type"] == "http.response.start":
                headers = Headers(raw=message.get("headers", []))
                cache = headers.get("cache-control", "")
                if (
                    message.get("status") != 200
                    or "etag" in headers
                    or "no-store" in cache
                    or not headers.get("content-type", "").startswith("application/json")
                    or "content-encoding" in headers
                ):
                    passthrough = True
                    await send(message)
                    return
                start = message
                return
            if message["type"] != "http.response.body":
                await send(message)
                return
            chunks.append(message.get("body", b""))
            size += len(chunks[-1])
            more = message.get("more_body", False)
            if size > MAX_HASHED_BYTES:
                # Too large to hold: send what is held and the rest as it comes, unhashed.
                passthrough = True
                assert start is not None
                await send(start)
                await send(
                    {"type": "http.response.body", "body": b"".join(chunks), "more_body": more}
                )
                return
            if more:
                return
            body = b"".join(chunks)
            etag = content_etag(body)
            assert start is not None
            headers = MutableHeaders(raw=list(start.get("headers", [])))
            headers["etag"] = etag
            headers["cache-control"] = "private, no-cache"
            headers.add_vary_header("Cookie")
            headers.add_vary_header("Authorization")
            if if_none_match_matches(if_none_match, etag):
                del headers["content-length"]
                if "content-type" in headers:
                    del headers["content-type"]
                await send({"type": "http.response.start", "status": 304, "headers": headers.raw})
                await send({"type": "http.response.body", "body": b""})
                return
            headers["content-length"] = str(len(body))
            await send({**start, "headers": headers.raw})
            await send({"type": "http.response.body", "body": body})

        await self.app(scope, receive, buffered)
