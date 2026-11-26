"""Warm views: last good result at once, refreshed on the outbox, a write or its age."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from eurogas_nexus.application import warm_views as wv
from eurogas_nexus.application.warm_views import FRESH, REFRESHING, ViewSpec, WarmViews
from eurogas_nexus.governance.usage import metering, note_licensed_read

SPEC = ViewSpec("test.view", max_age_seconds=60, max_stale_seconds=600, keep_warm_seconds=900)


class Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


class InlineExecutor:
    """Runs a refresh when asked to (``run``), so a test sees the stale answer first."""

    def __init__(self) -> None:
        self.pending = []

    def submit(self, fn, *args):
        from concurrent.futures import Future

        future = Future()
        self.pending.append((future, fn, args))
        return future

    def run(self) -> int:
        done = 0
        while self.pending:
            future, fn, args = self.pending.pop(0)
            future.set_result(fn(*args))
            done += 1
        return done


@pytest.fixture
def store():
    clock = Clock()
    outbox = {"seq": 10}
    executor = InlineExecutor()
    views = WarmViews(watermark=lambda: outbox["seq"], clock=clock, executor=executor,
                      wall_clock=lambda: datetime(2026, 11, 26, 9, 0, tzinfo=UTC),
                      watermark_poll_seconds=0)
    return SimpleNamespace(views=views, clock=clock, outbox=outbox, executor=executor)


def counter(label="v"):
    calls = {"n": 0}

    def compute():
        calls["n"] += 1
        return {"data": {label: calls["n"]}, "meta": {"warnings": []}}

    return compute, calls


def test_second_read_is_served_from_the_first_with_its_computed_time(store):
    compute, calls = counter()
    first = store.views.serve(SPEC, "alice", ("k",), compute)
    second = store.views.serve(SPEC, "alice", ("k",), compute)
    assert calls["n"] == 1
    assert first["data"] == second["data"] == {"v": 1}
    assert second["meta"]["view"] == {
        "state": FRESH, "computed_at_utc": "2026-11-26T09:00:00Z", "max_age_seconds": 60,
    }
    assert second["meta"]["warnings"] == []


def test_entries_never_cross_keys(store):
    compute_a, calls_a = counter("a")
    compute_b, calls_b = counter("b")
    assert store.views.serve(SPEC, "alice", ("alice-principal",), compute_a)["data"] == {"a": 1}
    assert store.views.serve(SPEC, "bob", ("bob-principal",), compute_b)["data"] == {"b": 1}
    assert calls_a["n"] == calls_b["n"] == 1


def test_an_outbox_event_serves_the_kept_answer_marked_refreshing_then_the_new_one(store):
    compute, calls = counter()
    store.views.serve(SPEC, "alice", ("k",), compute)
    store.outbox["seq"] = 11  # a price arrived
    stale = store.views.serve(SPEC, "alice", ("k",), compute)
    assert stale["data"] == {"v": 1} and stale["meta"]["view"]["state"] == REFRESHING
    assert calls["n"] == 1  # nothing computed in the request
    assert store.executor.run() == 1
    fresh = store.views.serve(SPEC, "alice", ("k",), compute)
    assert fresh["data"] == {"v": 2} and fresh["meta"]["view"]["state"] == FRESH


def test_age_past_max_age_refreshes_and_past_max_stale_computes_in_the_request(store):
    compute, calls = counter()
    store.views.serve(SPEC, "alice", ("k",), compute)
    store.clock.t += 61
    assert store.views.serve(SPEC, "alice", ("k",), compute)["meta"]["view"]["state"] == REFRESHING
    store.executor.pending.clear()  # the refresh never ran
    store.clock.t += 600
    answer = store.views.serve(SPEC, "alice", ("k",), compute)
    assert answer["data"] == {"v": 2} and answer["meta"]["view"]["state"] == FRESH


def test_the_writers_own_view_is_recomputed_before_it_is_served_again(store):
    mine, my_calls = counter("mine")
    theirs, their_calls = counter("theirs")
    store.views.serve(SPEC, "alice", ("alice",), mine)
    store.views.serve(SPEC, "bob", ("bob",), theirs)
    store.views.note_write("alice")
    # Alice wrote: her answer is never from before the write.
    assert store.views.serve(SPEC, "alice", ("alice",), mine)["data"] == {"mine": 2}
    # Bob's is served (saying so) and refreshed behind.
    bob = store.views.serve(SPEC, "bob", ("bob",), theirs)
    assert bob["data"] == {"theirs": 1} and bob["meta"]["view"]["state"] == REFRESHING
    store.executor.run()
    assert store.views.serve(SPEC, "bob", ("bob",), theirs)["data"] == {"theirs": 2}


def test_a_failed_refresh_keeps_the_last_good_answer(store):
    state = {"fail": False, "n": 0}

    def compute():
        state["n"] += 1
        if state["fail"]:
            raise RuntimeError("store down")
        return {"data": state["n"], "meta": {}}

    store.views.serve(SPEC, "alice", ("k",), compute)
    state["fail"] = True
    store.outbox["seq"] += 1
    store.views.serve(SPEC, "alice", ("k",), compute)
    store.executor.run()
    kept = store.views.serve(SPEC, "alice", ("k",), compute)
    assert kept["data"] == 1 and kept["meta"]["view"]["state"] == REFRESHING
    assert store.views.stats.refresh_errors == 1


def test_errors_and_non_envelopes_are_not_kept(store):
    def failing():
        raise ValueError("bad")

    with pytest.raises(ValueError):
        store.views.serve(SPEC, "alice", ("k",), failing)
    calls = {"n": 0}

    def file_response():
        calls["n"] += 1
        return b"csv"

    assert store.views.serve(SPEC, "alice", ("f",), file_response) == b"csv"
    assert store.views.serve(SPEC, "alice", ("f",), file_response) == b"csv"
    assert calls["n"] == 2


def test_licensed_families_are_noted_on_every_served_read(store):
    def compute():
        note_licensed_read("ice_endex")
        return {"data": 1, "meta": {}}

    with metering() as first:
        store.views.serve(SPEC, "alice", ("k",), compute)
    with metering() as second:
        store.views.serve(SPEC, "alice", ("k",), compute)
    assert first.families == {"ice_endex"}
    assert second.families == {"ice_endex"}


def test_the_keeper_refreshes_entries_read_lately_when_a_signal_moves(store):
    compute, calls = counter()
    store.views.serve(SPEC, "alice", ("recent",), compute)
    other, other_calls = counter()
    store.views.serve(SPEC, "carol", ("old",), other)
    store.clock.t += 61  # both past max_age...
    store.views.serve(SPEC, "alice", ("recent",), compute)  # ...alice read again (refresh queued)
    store.executor.run()
    store.clock.t += 900  # carol's entry was not read within keep_warm_seconds
    store.outbox["seq"] += 1
    assert store.views.refresh_due() == 1
    store.executor.run()
    assert calls["n"] == 3 and other_calls["n"] == 1


def test_least_recently_used_entries_are_dropped():
    views = WarmViews(watermark=lambda: 1, max_entries=2, watermark_poll_seconds=0)
    for key in ("a", "b", "c"):
        views.serve(SPEC, "alice", (key,), lambda key=key: {"data": key, "meta": {}})
    assert len(views._entries) == 2  # noqa: SLF001
    calls = {"n": 0}

    def again():
        calls["n"] += 1
        return {"data": "a", "meta": {}}

    views.serve(SPEC, "alice", ("a",), again)
    assert calls["n"] == 1


@dataclass(frozen=True)
class Principal:
    principal_id: str
    role: str = "TRADER"
    data_scopes: tuple[str, ...] = ()


def test_serve_view_keys_by_the_whole_principal(monkeypatch):
    store = WarmViews(watermark=lambda: 1, watermark_poll_seconds=0)
    monkeypatch.setattr(wv, "_VIEWS", store)
    monkeypatch.setattr(store, "start_keeper", lambda *a, **k: None)
    monkeypatch.setenv("EUROGAS_NEXUS_WARM_VIEWS", "on")
    calls = {"n": 0}

    def compute():
        calls["n"] += 1
        return {"data": calls["n"], "meta": {}}

    def request(principal):
        return SimpleNamespace(state=SimpleNamespace(identity=principal))

    narrow = Principal("p1", data_scopes=("BOOKS:A",))
    wide = Principal("p1", data_scopes=("BOOKS:*",))
    assert wv.serve_view(request(narrow), SPEC, (), compute)["data"] == 1
    assert wv.serve_view(request(narrow), SPEC, (), compute)["data"] == 1
    # Same id, another grant: never the first one's answer.
    assert wv.serve_view(request(wide), SPEC, (), compute)["data"] == 2
    # No identity (the static token): computed every time, never kept.
    assert wv.serve_view(SimpleNamespace(state=SimpleNamespace()), SPEC, (), compute)["data"] == 3
    assert wv.serve_view(SimpleNamespace(state=SimpleNamespace()), SPEC, (), compute)["data"] == 4


def test_switched_off_computes_every_time(monkeypatch):
    monkeypatch.setenv("EUROGAS_NEXUS_WARM_VIEWS", "off")
    calls = {"n": 0}

    def compute():
        calls["n"] += 1
        return {"data": calls["n"], "meta": {}}

    req = SimpleNamespace(state=SimpleNamespace(identity=Principal("p1")))
    wv.serve_view(req, SPEC, (), compute)
    wv.serve_view(req, SPEC, (), compute)
    assert calls["n"] == 2


def test_the_route_decorator_keeps_the_signature_and_keys_by_parameters(monkeypatch):
    import inspect

    from fastapi import Query, Request

    store = WarmViews(watermark=lambda: 1, watermark_poll_seconds=0)
    monkeypatch.setattr(wv, "_VIEWS", store)
    monkeypatch.setattr(store, "start_keeper", lambda *a, **k: None)
    monkeypatch.setenv("EUROGAS_NEXUS_WARM_VIEWS", "on")
    calls = {"n": 0}

    @wv.warm_view(SPEC, skip=wv.not_json)
    def route(request: Request, days: int = Query(14), format: str = "json"):
        calls["n"] += 1
        return {"data": {"days": days, "n": calls["n"]}, "meta": {}}

    assert list(inspect.signature(route).parameters) == ["request", "days", "format"]
    req = SimpleNamespace(state=SimpleNamespace(identity=Principal("p1")))
    assert route(request=req, days=14, format="json")["data"] == {"days": 14, "n": 1}
    assert route(request=req, days=14, format="json")["data"] == {"days": 14, "n": 1}
    assert route(request=req, days=7, format="json")["data"] == {"days": 7, "n": 2}
    route(request=req, days=14, format="csv")
    route(request=req, days=14, format="csv")
    assert calls["n"] == 4
    # A direct call that passes the request positionally is answered directly.
    route(req, days=14, format="json")
    assert calls["n"] == 5


def test_a_successful_write_through_the_api_makes_views_due(monkeypatch):
    import asyncio

    from eurogas_nexus.api.middleware.warm_views import WarmViewWriteMiddleware

    seen = []
    monkeypatch.setattr(wv, "_VIEWS", SimpleNamespace(note_write=seen.append))
    monkeypatch.setattr("eurogas_nexus.api.middleware.warm_views.views", lambda: wv._VIEWS)

    def app_answering(status):
        async def app(scope, receive, send):
            await send({"type": "http.response.start", "status": status, "headers": []})
            await send({"type": "http.response.body", "body": b""})

        return app

    async def noop(message):
        return None

    def call(method, path, status):
        scope = {"type": "http", "method": method, "path": path,
                 "state": {"identity": Principal("p1")}}
        asyncio.run(WarmViewWriteMiddleware(app_answering(status))(scope, None, noop))

    call("PUT", "/api/portfolio/books/b1", 200)
    call("POST", "/api/research/spreads/evaluate", 200)  # a computation
    call("GET", "/api/desk/today", 200)
    call("DELETE", "/api/portfolio/books/b1", 403)  # refused: nothing changed
    assert seen == ["p1"]


def test_a_background_refresh_reads_as_the_reader_of_the_first_request(store):
    # Alert visibility and the book scope read the request principal from context variables:
    # a refresh must run in the first request's context, never in an empty one.
    from eurogas_nexus.application.alert_scope import request_principal, set_request_principal

    seen = []

    def compute():
        seen.append(request_principal())
        return {"data": len(seen), "meta": {}}

    import contextvars

    def as_reader():
        set_request_principal("reader-alice")
        return store.views.serve(SPEC, "alice", ("k",), compute)

    contextvars.copy_context().run(as_reader)
    store.outbox["seq"] += 1
    contextvars.copy_context().run(as_reader)  # stale: refresh queued
    assert request_principal() is None  # this thread holds no reader
    store.executor.run()
    assert seen == ["reader-alice", "reader-alice"]


def test_view_meta_does_not_change_a_conditional_reads_tag() -> None:
    # A kept answer recomputed to the same content keeps its ETag, so a page revalidating it
    # still gets 304 (api/middleware/conditional.py).
    import json

    from eurogas_nexus.api.middleware.conditional import content_etag

    def body(state: str, at: str, value: int = 1) -> bytes:
        meta = {"view": {"state": state, "computed_at_utc": at, "max_age_seconds": 60}}
        return json.dumps({"data": {"x": value}, "meta": meta}).encode()

    kept = content_etag(body("refreshing", "2026-11-26T09:41:00Z"))
    assert kept == content_etag(body("fresh", "2026-11-26T09:42:00Z"))
    assert kept != content_etag(body("fresh", "2026-11-26T09:42:00Z", value=2))
