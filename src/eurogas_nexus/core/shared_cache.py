"""The shared cache: what several API processes must agree on, behind one small interface.

An API process keeps a few things in memory that its siblings must see when the API runs as
several processes behind a load balancer (decision record 2026-11-26, "Several API processes,
one live-update poller per process, and a shared cache"):

* fixed-window counters: the sign-in and administration rate limits, the per-address sign-in
  throttle (``security/rate_limit.py``, ``application/local_accounts.py``);
* generation counters: "a write went through the API", which makes the warm views of every
  process due and the writer's own entries unservable (``application/warm_views.py``);
* revocation notes: a signed-out session or a disabled identity, read by the live-update
  streams every poll (``security/session_revocation.py``).

Two backends, chosen by one setting, ``EUROGAS_NEXUS_SHARED_CACHE_URL``:

* unset: :class:`MemoryCache`, in this process only. Right for one process (development, the
  demo, tests); with several processes each keeps its own (limits per process, invalidation
  per process).
* ``valkey://``, ``valkeys://`` (TLS), ``redis://`` or ``rediss://``: :class:`ValkeyCache`,
  shared by every process that names the same server. Valkey (BSD-3-Clause, the community
  fork of Redis 7.2) or Redis 7.2 or earlier; the client is ``valkey`` (MIT).

The cache is never a store of record: losing it loses counters and notes, never data. A
backend that cannot be reached raises :class:`SharedCacheUnavailable`; each caller decides
what that means for it (a rate limit falls back to this process's own count, the warm views
stop answering from memory, a stream's revocation check falls back to the database, which is
the authority). After a failure the client does not try again for
:data:`RETRY_AFTER_SECONDS`, so an outage costs one timeout, not one per request.

共享缓存：多个 API 进程必须共同看到的计数与标记；未配置时仅在本进程内存中。
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections.abc import Mapping
from typing import Protocol

logger = logging.getLogger(__name__)

SHARED_CACHE_URL_ENV = "EUROGAS_NEXUS_SHARED_CACHE_URL"
#: Every key this product writes starts with this (one server may serve other tenants).
KEY_PREFIX = "egn:"
#: Socket timeouts: the cache sits beside the API; a slower answer is an outage.
CONNECT_TIMEOUT_SECONDS = 0.5
OPERATION_TIMEOUT_SECONDS = 0.5
#: After a failure, calls fail at once for this long instead of waiting on the socket again.
RETRY_AFTER_SECONDS = 2.0
SCHEMES = ("valkey://", "valkeys://", "redis://", "rediss://", "unix://")


class SharedCacheUnavailable(RuntimeError):
    """The shared cache could not be reached; the caller applies its own fallback."""


class SharedCache(Protocol):
    #: ``memory`` or ``valkey``.
    name: str
    #: Whether other processes see the same values.
    shared: bool

    def get(self, key: str) -> bytes | None: ...

    def get_many(self, keys: list[str]) -> list[bytes | None]: ...

    def set(self, key: str, value: bytes, ttl_seconds: float | None = None) -> None: ...

    def delete(self, key: str) -> None: ...

    def incr(self, key: str, ttl_seconds: float | None = None) -> int:
        """Add one and return the new value; a new key expires after ``ttl_seconds`` (a later
        increment does not extend it: a fixed window that starts at the first count)."""
        ...

    def ping(self) -> bool: ...


class MemoryCache:
    """This process's own cache (thread-safe); the default and the tests' backend."""

    name = "memory"
    shared = False

    def __init__(self, clock=time.monotonic) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._values: dict[str, tuple[bytes, float | None]] = {}

    def _live(self, key: str) -> bytes | None:
        held = self._values.get(key)
        if held is None:
            return None
        value, expires = held
        if expires is not None and self._clock() >= expires:
            self._values.pop(key, None)
            return None
        return value

    def get(self, key: str) -> bytes | None:
        with self._lock:
            return self._live(key)

    def get_many(self, keys: list[str]) -> list[bytes | None]:
        with self._lock:
            return [self._live(key) for key in keys]

    def set(self, key: str, value: bytes, ttl_seconds: float | None = None) -> None:
        with self._lock:
            expires = None if ttl_seconds is None else self._clock() + ttl_seconds
            self._values[key] = (value, expires)

    def delete(self, key: str) -> None:
        with self._lock:
            self._values.pop(key, None)

    def incr(self, key: str, ttl_seconds: float | None = None) -> int:
        with self._lock:
            held = self._live(key)
            if held is None:
                count = 1
                expires = None if ttl_seconds is None else self._clock() + ttl_seconds
            else:
                count = int(held) + 1
                expires = self._values[key][1]
            self._values[key] = (str(count).encode(), expires)
            return count

    def ping(self) -> bool:
        return True

    def clear(self) -> None:
        with self._lock:
            self._values.clear()


class ValkeyCache:
    """A Valkey (or Redis 7.2 or earlier) server shared by every API process."""

    name = "valkey"
    shared = True

    def __init__(self, url: str, client=None) -> None:
        self._url = url
        self._client = client
        self._lock = threading.Lock()
        self._down_until = 0.0
        self.failures = 0

    def _connection(self):
        if self._client is None:
            with self._lock:
                if self._client is None:
                    import valkey

                    url = self._url
                    # The client knows the redis schemes; valkey:// is the same protocol.
                    if url.startswith("valkeys://"):
                        url = "rediss://" + url[len("valkeys://") :]
                    elif url.startswith("valkey://"):
                        url = "redis://" + url[len("valkey://") :]
                    self._client = valkey.Valkey.from_url(
                        url,
                        socket_connect_timeout=CONNECT_TIMEOUT_SECONDS,
                        socket_timeout=OPERATION_TIMEOUT_SECONDS,
                        health_check_interval=30,
                        retry_on_timeout=False,
                    )
        return self._client

    def _call(self, operation):
        if time.monotonic() < self._down_until:
            raise SharedCacheUnavailable("shared cache unavailable (recent failure)")
        try:
            return operation(self._connection())
        except SharedCacheUnavailable:
            raise
        except Exception as exc:  # noqa: BLE001 - every client error is "unavailable" here
            self.failures += 1
            self._down_until = time.monotonic() + RETRY_AFTER_SECONDS
            logger.warning("shared cache unavailable: %s", exc.__class__.__name__)
            raise SharedCacheUnavailable(exc.__class__.__name__) from exc

    def get(self, key: str) -> bytes | None:
        return self._call(lambda client: client.get(KEY_PREFIX + key))

    def get_many(self, keys: list[str]) -> list[bytes | None]:
        if not keys:
            return []
        return list(self._call(lambda client: client.mget([KEY_PREFIX + key for key in keys])))

    def set(self, key: str, value: bytes, ttl_seconds: float | None = None) -> None:
        px = None if ttl_seconds is None else max(1, int(ttl_seconds * 1000))
        self._call(lambda client: client.set(KEY_PREFIX + key, value, px=px))

    def delete(self, key: str) -> None:
        self._call(lambda client: client.delete(KEY_PREFIX + key))

    def incr(self, key: str, ttl_seconds: float | None = None) -> int:
        full = KEY_PREFIX + key

        def run(client) -> int:
            pipe = client.pipeline(transaction=True)
            pipe.incr(full)
            if ttl_seconds is not None:
                # NX: only a new key gets the expiry, so the window starts at the first count.
                pipe.pexpire(full, max(1, int(ttl_seconds * 1000)), nx=True)
            return int(pipe.execute()[0])

        return self._call(run)

    def ping(self) -> bool:
        try:
            return bool(self._call(lambda client: client.ping()))
        except SharedCacheUnavailable:
            return False


def configured_url(environ: Mapping[str, str] | None = None) -> str | None:
    if environ is None:
        raw = os.environ.get("EUROGAS_NEXUS_SHARED_CACHE_URL", "")
    else:
        raw = environ.get(SHARED_CACHE_URL_ENV, "")
    value = (raw or "").strip()
    return value or None


def validate_url(url: str) -> None:
    """Refuse a URL the backend cannot use (a startup error, not a silent memory fallback)."""

    if not url.startswith(SCHEMES):
        raise ValueError(
            f"{SHARED_CACHE_URL_ENV} must start with one of {', '.join(SCHEMES)}"
        )


_LOCK = threading.Lock()
_CACHE: SharedCache | None = None
_CACHE_URL: str | None = None


def shared_cache() -> SharedCache:
    """This process's shared cache: Valkey when configured, else its own memory."""

    global _CACHE, _CACHE_URL
    url = configured_url()
    with _LOCK:
        if _CACHE is None or url != _CACHE_URL:
            if url:
                validate_url(url)
                _CACHE = ValkeyCache(url)
            else:
                _CACHE = MemoryCache()
            _CACHE_URL = url
        return _CACHE


def use_cache(cache: SharedCache | None) -> None:
    """Replace the process's cache (tests); ``None`` goes back to the configured one."""

    global _CACHE, _CACHE_URL
    with _LOCK:
        _CACHE = cache
        _CACHE_URL = configured_url() if cache is not None else None


def describe(environ: Mapping[str, str] | None = None) -> dict[str, object]:
    """What the readiness report says about the cache (never the URL's credentials)."""

    url = configured_url(environ)
    if not url:
        return {"backend": "memory", "shared": False}
    from urllib.parse import urlsplit

    parts = urlsplit(url)
    host = parts.hostname or "socket"
    return {"backend": "valkey", "shared": True, "host": host, "port": parts.port}


__all__ = [
    "KEY_PREFIX",
    "SHARED_CACHE_URL_ENV",
    "MemoryCache",
    "SharedCache",
    "SharedCacheUnavailable",
    "ValkeyCache",
    "configured_url",
    "describe",
    "shared_cache",
    "use_cache",
    "validate_url",
]
