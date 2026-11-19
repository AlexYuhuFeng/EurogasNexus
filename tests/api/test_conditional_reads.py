"""Conditional reads (api/middleware/conditional.py): an ETag on JSON reads, 304 when unchanged."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from eurogas_nexus.api.middleware.compression import ApiReadCompressionMiddleware
from eurogas_nexus.api.middleware.conditional import ConditionalReadMiddleware


def _app(state: dict) -> TestClient:
    app = FastAPI()

    @app.get("/api/read")
    def read() -> dict:
        return {"data": {"value": state["value"], "pad": "x" * 4000}}

    @app.get("/api/me")
    def me() -> dict:
        return {"data": {"csrf": "secret"}}

    @app.get("/api/report")
    def report() -> JSONResponse:
        return JSONResponse({"data": 1}, headers={"Cache-Control": "private, no-store"})

    app.add_middleware(ConditionalReadMiddleware)
    app.add_middleware(ApiReadCompressionMiddleware)
    return TestClient(app)


def test_an_unchanged_read_answers_304_and_a_changed_one_its_new_body():
    state = {"value": 1}
    client = _app(state)
    first = client.get("/api/read", headers={"Accept-Encoding": "gzip"})
    assert first.status_code == 200
    etag = first.headers["etag"]
    assert etag.startswith('W/"')
    assert first.headers["cache-control"] == "private, no-cache"
    # Hashed before compression: the compressed answer carries the same tag.
    assert first.headers["content-encoding"] == "gzip"
    again = client.get("/api/read", headers={"If-None-Match": etag, "Accept-Encoding": "gzip"})
    assert again.status_code == 304
    assert again.content == b""
    assert again.headers["etag"] == etag
    state["value"] = 2
    changed = client.get("/api/read", headers={"If-None-Match": etag})
    assert changed.status_code == 200
    assert changed.json()["data"]["value"] == 2
    assert changed.headers["etag"] != etag


def test_secret_carrying_and_no_store_reads_get_no_tag():
    client = _app({"value": 1})
    assert "etag" not in client.get("/api/me").headers
    report = client.get("/api/report")
    assert "etag" not in report.headers
    assert report.headers["cache-control"] == "private, no-store"


def test_an_answer_that_differs_only_by_when_it_was_computed_is_unchanged():
    from datetime import UTC, datetime

    app = FastAPI()

    @app.get("/api/projection")
    def projection() -> dict:
        now = datetime.now(UTC).isoformat()
        return {"data": {"as_of_utc": now, "rows": [{"value": 1, "evaluated_at_utc": now}]}}

    app.add_middleware(ConditionalReadMiddleware)
    client = TestClient(app)
    etag = client.get("/api/projection").headers["etag"]
    assert client.get("/api/projection", headers={"If-None-Match": etag}).status_code == 304
