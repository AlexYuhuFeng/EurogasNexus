"""The shared cache seam: what several API processes agree on, and what happens when it is down.

Two "processes" are simulated by two stores (warm views, local counters) over one shared
backend. ``EUROGAS_NEXUS_TEST_VALKEY_URL`` (a scratch Valkey) runs the same checks against a
real server; without it those tests are skipped.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

import pytest

from eurogas_nexus.core import shared_cache as sc
from eurogas_nexus.core.shared_cache import MemoryCache, SharedCacheUnavailable


class SharedMemory(MemoryCache):
    """A memory cache that says it is shared (as Valkey is), and can be switched off."""

    shared = True

    def __init__(self) -> None:
        super().__init__()
        self.down = False

    def _check(self) -> None:
        if self.down:
            raise SharedCacheUnavailable("down")

    def get(self, key):
        self._check()
        return super().get(key)

    def get_many(self, keys):
        self._check()
        return super().get_many(keys)

    def set(self, key, value, ttl_seconds=None):
        self._check()
        return super().set(key, value, ttl_seconds)

    def incr(self, key, ttl_seconds=None):
        self._check()
        return super().incr(key, ttl_seconds)


@pytest.fixture
def shared():
    cache = SharedMemory()
    sc.use_cache(cache)
    yield cache
    sc.use_cache(None)


def test_memory_counter_is_a_fixed_window_from_the_first_count():
    now = [100.0]
    cache = MemoryCache(clock=lambda: now[0])
    assert [cache.incr("k", ttl_seconds=60) for _ in range(3)] == [1, 2, 3]
    now[0] += 59
    assert cache.incr("k", ttl_seconds=60) == 4  # a later count does not extend the window
    now[0] += 1
    assert cache.incr("k", ttl_seconds=60) == 1


def test_no_url_is_this_process_memory_and_a_bad_scheme_is_refused(monkeypatch):
    monkeypatch.delenv(sc.SHARED_CACHE_URL_ENV, raising=False)
    sc.use_cache(None)
    assert sc.shared_cache().name == "memory" and not sc.shared_cache().shared
    monkeypatch.setenv(sc.SHARED_CACHE_URL_ENV, "http://cache:6379")
    with pytest.raises(ValueError):
        sc.shared_cache()
    monkeypatch.setenv(sc.SHARED_CACHE_URL_ENV, "valkey://user:secret@cache:6379/0")
    assert sc.shared_cache().name == "valkey"
    assert sc.describe() == {"backend": "valkey", "shared": True, "host": "cache", "port": 6379}
    sc.use_cache(None)


def test_a_rate_limit_holds_across_processes_and_falls_back_to_the_process_count(shared):
    from eurogas_nexus.security import rate_limit as rl

    key = "auth:198.51.100.7"
    # Ten requests split over "processes": one shared count, the eleventh is refused.
    assert all(rl.rate_limit(key, limit=10) for _ in range(10))
    assert rl.rate_limit(key, limit=10) is False
    # The cache is down: the limit does not disappear, this process counts for itself.
    shared.down = True
    rl._WINDOWS.pop(key, None)
    assert all(rl.rate_limit(key, limit=3) for _ in range(3))
    assert rl.rate_limit(key, limit=3) is False
    rl._WINDOWS.pop(key, None)


def test_the_sign_in_address_throttle_is_shared(shared):
    from eurogas_nexus.application import local_accounts as la

    address = "203.0.113.9"
    for _ in range(la.MAX_ADDRESS_FAILURES):
        la._record_address_failure(address)
    la.reset_address_throttle()  # another process: its own memory knows nothing
    assert la._address_blocked(address) is True
    assert la._address_blocked("203.0.113.10") is False


def _views(generations):
    from eurogas_nexus.application.warm_views import WarmViews

    class Inline:
        def submit(self, fn, *args):
            from concurrent.futures import Future

            fn(*args)
            done = Future()
            done.set_result(None)
            return done

    return WarmViews(watermark=lambda: 1, executor=Inline(), generations=generations)


def test_a_write_through_one_process_reaches_the_kept_views_of_another(shared):
    from eurogas_nexus.application.warm_views import Generations, ViewSpec

    spec = ViewSpec("today")
    process_a = _views(Generations(lambda: shared))
    process_b = _views(Generations(lambda: shared))
    calls = {"n": 0}

    def compute():
        calls["n"] += 1
        return {"data": calls["n"], "meta": {}}

    assert process_a.serve(spec, "p1", "k", compute)["data"] == 1
    assert process_a.serve(spec, "p1", "k", compute)["data"] == 1  # kept
    process_b.note_write("p1")  # p1 writes through the other process
    # p1's own write is never answered from before it, on any process.
    assert process_a.serve(spec, "p1", "k", compute)["data"] == 2


def test_an_unreadable_write_signal_means_no_answer_from_memory(shared):
    from eurogas_nexus.application.warm_views import Generations, ViewSpec

    spec = ViewSpec("today")
    views = _views(Generations(lambda: shared))
    calls = {"n": 0}

    def compute():
        calls["n"] += 1
        return {"data": calls["n"], "meta": {}}

    views.serve(spec, "p1", "k", compute)
    shared.down = True
    assert views.serve(spec, "p1", "k", compute)["data"] == 2
    assert views.serve(spec, "p1", "k", compute)["data"] == 3
    shared.down = False
    # Writes through other processes during the outage are unknown: what was kept before it
    # is gone, and the first read after it computes, then is kept.
    assert views.serve(spec, "p1", "k", compute)["data"] == 4
    assert views.serve(spec, "p1", "k", compute)["data"] == 4


def test_revocation_notes_end_streams_opened_before_them(shared):
    from eurogas_nexus.security.session_revocation import (
        note_principal_revoked,
        note_session_revoked,
        revoked_streams,
    )

    opened = datetime.now(UTC) - timedelta(minutes=5)
    note_session_revoked("hash-a")
    note_principal_revoked("p-disabled")
    assert revoked_streams(
        [
            ("hash-a", "p1", opened),  # this session signed out
            ("hash-b", "p1", opened),  # another session of the same person: still open
            (None, "p-disabled", opened),  # every session of a disabled identity
            (None, "p-disabled", datetime.now(UTC) + timedelta(minutes=1)),  # opened after
        ]
    ) == [True, False, True, False]
    shared.down = True
    assert revoked_streams([("hash-a", "p1", opened)]) == [None]  # the database decides


def test_a_signed_out_session_ends_its_open_stream_at_the_next_poll(shared):
    from types import SimpleNamespace

    from eurogas_nexus.api.routes.public.streaming import StreamGuard
    from eurogas_nexus.application.live_topics import Reads
    from eurogas_nexus.security.identity import AuthenticatedPrincipal
    from eurogas_nexus.security.session_revocation import note_session_revoked

    principal = AuthenticatedPrincipal(
        principal_id="p1",
        name="trader",
        principal_type="USER",
        role="ANALYST",
        status="ACTIVE",
        data_scopes=("EEX",),
        auth_method="session",
    )
    guard = StreamGuard("quotes", principal, session_hash="hash-x")
    db = SimpleNamespace()  # not reached before REAUTH_SECONDS
    reads = Reads(db)
    guard.want(reads)
    assert guard.still_allowed(reads) is True
    note_session_revoked("hash-x")  # signed out through another process
    reads = Reads(db)
    guard.want(reads)
    assert guard.still_allowed(reads) is False
    assert guard(reads, [{"quote_id": "q1", "source_system": "EEX"}]) is None


VALKEY_URL = os.environ.get("EUROGAS_NEXUS_TEST_VALKEY_URL")


@pytest.mark.skipif(not VALKEY_URL, reason="no scratch Valkey (EUROGAS_NEXUS_TEST_VALKEY_URL)")
def test_a_real_valkey_counts_and_expires_like_memory():
    import time
    import uuid

    cache = sc.ValkeyCache(VALKEY_URL)
    key = f"test:{uuid.uuid4().hex}"
    assert cache.ping()
    assert [cache.incr(key, ttl_seconds=1) for _ in range(3)] == [1, 2, 3]
    assert cache.get_many([key, key + ":none"]) == [b"3", None]
    cache.set(key + ":v", b"x", ttl_seconds=0.2)
    assert cache.get(key + ":v") == b"x"
    time.sleep(1.1)
    assert cache.get(key) is None and cache.get(key + ":v") is None


def test_an_unreachable_valkey_fails_fast_after_the_first_timeout():
    import time

    cache = sc.ValkeyCache("valkey://127.0.0.1:1/0")  # nothing listens on port 1
    with pytest.raises(SharedCacheUnavailable):
        cache.get("k")
    started = time.monotonic()
    with pytest.raises(SharedCacheUnavailable):
        cache.incr("k", ttl_seconds=5)
    assert time.monotonic() - started < 0.05  # no second wait on the socket
    assert cache.ping() is False
