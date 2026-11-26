"""One cap on open live streams per person (M7), across API processes when a shared cache exists.

``EUROGAS_NEXUS_MAX_STREAMS_PER_PRINCIPAL`` (default 8: the web client holds one stream per tab).
With a shared cache each stream holds an expiring slot there, so a person cannot hold 8 streams on
each of 4 processes; a process that dies frees its slots when the leases run out. Without one,
each process counts its own.
"""

from __future__ import annotations

import asyncio
import gc

import pytest
from fastapi import HTTPException

from eurogas_nexus.core import shared_cache as cache_module
from eurogas_nexus.security import rate_limit


class _SharedMemory(cache_module.MemoryCache):
    """The memory backend standing in for Valkey: what other processes would see."""

    shared = True

    def __init__(self) -> None:
        self.now = 0.0
        super().__init__(clock=lambda: self.now)


class _Down(_SharedMemory):
    def add(self, *_args, **_kwargs):
        raise cache_module.SharedCacheUnavailable("down")


async def _events():
    yield "event"


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.delenv(rate_limit.STREAM_LIMIT_ENV, raising=False)
    rate_limit._STREAMS.clear()
    yield
    cache_module.use_cache(None)
    rate_limit._STREAMS.clear()


def _open(owner="p-trader"):
    return rate_limit.open_counted_stream(owner, _events())


def _refused(owner="p-trader") -> dict:
    with pytest.raises(HTTPException) as caught:
        _open(owner)
    assert caught.value.status_code == 429
    return caught.value.detail


def test_the_default_cap_is_eight_per_person_in_one_process():
    assert rate_limit.DEFAULT_STREAM_LIMIT == 8
    cache_module.use_cache(cache_module.MemoryCache())
    held = [_open() for _ in range(8)]
    detail = _refused()
    assert detail["code"] == "rate_limited" and detail["reason"] == "stream_limit_reached"
    _open("p-other")  # another person is not affected
    asyncio.run(held[0].aclose())
    _open()  # a closed tab frees its place


def test_the_cap_holds_across_processes_through_the_shared_cache(monkeypatch):
    monkeypatch.setenv(rate_limit.STREAM_LIMIT_ENV, "3")
    shared = _SharedMemory()
    cache_module.use_cache(shared)
    held = [_open() for _ in range(2)]
    rate_limit._STREAMS.clear()  # "another process": nothing counted locally
    third = _open()  # noqa: F841 - an open stream is one its response holds
    _refused()  # the third slot was the last, whichever process holds the others
    asyncio.run(held[0].aclose())
    _open()  # released in the shared cache too


def test_a_dead_process_frees_its_slots_when_the_leases_run_out(monkeypatch):
    monkeypatch.setenv(rate_limit.STREAM_LIMIT_ENV, "2")
    shared = _SharedMemory()
    cache_module.use_cache(shared)
    keep = [_open(), _open()]  # noqa: F841 - held by a process that then dies
    rate_limit._STREAMS.clear()
    _refused()
    shared.now += rate_limit.STREAM_SLOT_TTL_SECONDS + 1
    _open()


def test_a_running_stream_keeps_its_lease(monkeypatch):
    monkeypatch.setenv(rate_limit.STREAM_LIMIT_ENV, "1")
    shared = _SharedMemory()
    cache_module.use_cache(shared)
    stream = _open()
    stream.slot.refreshed -= rate_limit.STREAM_SLOT_REFRESH_SECONDS + 1
    shared.now += rate_limit.STREAM_SLOT_TTL_SECONDS - 1
    assert asyncio.run(stream.__anext__()) == "event"  # sending renews the lease
    shared.now += rate_limit.STREAM_SLOT_TTL_SECONDS - 1
    _refused()


def test_a_stream_that_never_started_is_released_when_collected(monkeypatch):
    monkeypatch.setenv(rate_limit.STREAM_LIMIT_ENV, "1")
    cache_module.use_cache(_SharedMemory())
    stream = _open()
    _refused()
    del stream
    gc.collect()
    again = _open()
    assert rate_limit.open_streams("p-trader") == 1
    del again


def test_an_unreachable_shared_cache_falls_back_to_this_processs_count(monkeypatch):
    monkeypatch.setenv(rate_limit.STREAM_LIMIT_ENV, "2")
    cache_module.use_cache(_Down())
    held = [_open(), _open()]  # noqa: F841
    _refused()


def test_zero_means_no_cap(monkeypatch):
    monkeypatch.setenv(rate_limit.STREAM_LIMIT_ENV, "0")
    cache_module.use_cache(_SharedMemory())
    held = [_open() for _ in range(20)]
    assert rate_limit.open_streams("p-trader") == len(held)


def test_the_write_and_heavy_quotas_count_in_the_shared_cache(monkeypatch):
    """Secfix's per-person quotas go through the same shared counter as the sign-in throttle,
    so they hold across processes when a shared cache is configured."""

    shared = _SharedMemory()
    cache_module.use_cache(shared)
    assert all(rate_limit.rate_limit("write:p-trader", limit=3) for _ in range(3))
    rate_limit._WINDOWS.clear()  # "another process"
    assert rate_limit.rate_limit("write:p-trader", limit=3) is False
