"""Synthetic loopback HTTP acceptance; no external sockets or real credentials.

The explicit test-only transport routes official request identities to a local
server. Production endpoint validation, parsing, pagination and retries run intact.
This proves protocol behavior, not provider conformance or licensed-data readiness.
"""

import json
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from eurogas_nexus.ingestion import entsog_transport as et
from eurogas_nexus.ingestion import gie_transport as gt


@contextmanager
def provider(responses):
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            calls.append((self.path, dict(self.headers)))
            status, payload, delay = responses[min(len(calls) - 1, len(responses) - 1)]
            time.sleep(delay)
            raw = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Retry-After", "0")
            self.send_header("Location", "https://foreign.invalid/refused")
            self.end_headers()
            try:
                self.wfile.write(raw)
            except (BrokenPipeError, ConnectionResetError):
                pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()

    class LoopbackTransport(httpx.BaseTransport):
        def __init__(self):
            self.inner = httpx.HTTPTransport(retries=0, trust_env=False)

        def handle_request(self, request):
            assert request.url.host in {"transparency.entsog.eu", "agsi.gie.eu"}
            local = request.url.copy_with(scheme="http", host="127.0.0.1", port=server.server_port)
            forwarded = httpx.Request(
                request.method, local, headers=request.headers, extensions=request.extensions
            )
            return self.inner.handle_request(forwarded)

        def close(self):
            self.inner.close()

    try:
        with httpx.Client(transport=LoopbackTransport(), trust_env=False) as client:
            yield client, calls
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)


def envelope(ids, *, offset=0, limit=2):
    return {
        "meta": {"limit": limit, "offset": offset, "count": len(ids), "total": 2, "sort": "id"},
        "operationaldatas": [{"id": identifier} for identifier in ids],
    }


def fetch(client, **kwargs):
    return et.fetch_entsog_dataset(
        client,
        "operationaldatas",
        page_size=2,
        max_pages=3,
        max_records=6,
        sleep=lambda _: None,
        **kwargs,
    )


def test_entsog_socket_pagination_and_replay_preserve_raw_hashes():
    pages = [(200, envelope(["a", "b"]), 0), (200, envelope([], offset=2), 0)]
    with provider(pages + pages) as (client, calls):
        first, replay = fetch(client), fetch(client)
    assert first.complete and replay.complete
    assert first.record_count == replay.record_count == 2
    assert [page.payload_sha256 for page in first.pages] == [
        page.payload_sha256 for page in replay.pages
    ]
    assert [parse_qs(urlsplit(path).query)["offset"] for path, _ in calls] == [
        ["0"],
        ["2"],
        ["0"],
        ["2"],
    ]
    assert all(
        page.request_url.startswith("https://transparency.entsog.eu/") for page in first.pages
    )


@pytest.mark.parametrize("status", [429, 503])
def test_entsog_socket_transient_retry(status):
    with provider([(status, {}, 0), (200, envelope(["a"]), 0)]) as (client, calls):
        result = fetch(client)
    assert result.complete and result.record_count == 1
    assert len(calls) == 2 and calls[0][0] == calls[1][0]


def test_entsog_socket_timeout_exhausts_exact_attempt_budget():
    with provider([(200, envelope(["a"]), 0.08)]) as (client, calls):
        with pytest.raises(et.EntsogTimeoutError):
            fetch(client, attempts=2, timeout_seconds=0.015)
        assert len(calls) == 2


@pytest.mark.parametrize(
    "status,payload,error",
    [
        (200, b"{broken", et.EntsogMalformedResponseError),
        (302, {}, et.EntsogRedirectRefusedError),
        (200, envelope(["a", "a"]), et.EntsogPaginationError),
    ],
)
def test_entsog_socket_fail_closed(status, payload, error):
    with provider([(status, payload, 0)]) as (client, calls):
        with pytest.raises(error):
            fetch(client)
    assert len(calls) == 1


def test_entsog_socket_failure_retains_incomplete_prefix():
    with provider([(200, envelope(["a", "b"]), 0), (200, b"null", 0)]) as (client, calls):
        with pytest.raises(et.EntsogMalformedResponseError) as failure:
            fetch(client)
    prefix = failure.value.validated_prefix_result
    assert prefix.record_count == 2 and not prefix.complete and len(calls) == 2
    with pytest.raises(et.EntsogTruncationError):
        prefix.require_complete()


def test_gie_socket_http_200_denial_and_redirect_are_not_success():
    for status, payload, error in [
        (200, {"error": "access denied", "dataset": "storage ERROR"}, gt.GieAuthenticationError),
        (302, {}, gt.GieRedirectRefusedError),
    ]:
        with provider([(status, payload, 0)]) as (client, calls):
            with pytest.raises(error):
                gt.fetch_gie_page(
                    client,
                    product=gt.GieProduct.agsi(),
                    api_key="synthetic-loopback-only",
                    page=1,
                    size=2,
                    sleeper=lambda _: None,
                )
        assert len(calls) == 1
        assert calls[0][1]["x-key"] == "synthetic-loopback-only"
