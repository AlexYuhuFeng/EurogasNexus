"""Development-only ENTSOG protocol fixtures; no live API or database use.

The envelope mirrors the official v3.0 metadata and small 2026-10-12 probes.
In particular total is page-local in those probes, not a pagination sentinel.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta, timezone

import httpx
import pytest

from eurogas_nexus.ingestion import entsog_transport as et

RECEIPT = datetime(2026, 10, 12, 15, 30, tzinfo=UTC)


def _body(request: httpx.Request, rows: list[dict], **meta_overrides) -> dict:
    dataset = request.url.path.rsplit("/", 1)[1]
    return {
        "meta": {
            "limit": int(request.url.params["limit"]),
            "offset": int(request.url.params["offset"]),
            "count": len(rows),
            "total": len(rows),
            "sort": "id",
            **meta_overrides,
        },
        dataset: rows,
    }


def _client(handler, *, follow_redirects=False):
    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=follow_redirects)


@pytest.mark.parametrize("dataset", sorted(et.ENTSOG_DATASETS))
def test_offset_traversal_never_treats_page_total_as_grand_total(dataset):
    requests = []
    instants = iter([RECEIPT, RECEIPT + timedelta(seconds=1)])

    def handler(request):
        requests.append(request)
        offset = int(request.url.params["offset"])
        return httpx.Response(
            200, json=_body(request, [{"id": str(i)} for i in range(offset, min(offset + 2, 3))])
        )

    with _client(handler) as client:
        result = et.fetch_entsog_dataset(
            client,
            dataset,
            page_size=2,
            max_records=10,
            filters={"hasData": "1"},
            clock=lambda: next(instants),
        )
    assert [r.url.params["offset"] for r in requests] == ["0", "2"]
    assert all(r.url.params["sort"] == "id" and r.url.params["hasData"] == "1" for r in requests)
    assert [p.provider_total for p in result.pages] == [2, 1]
    assert result.record_count == 3
    assert result.complete and result.stop_reason == "provider_offset_exhausted"
    assert not result.snapshot_consistent
    assert result.completeness_basis == "offset_exhaustion_not_snapshot"
    assert result.received_at_utc == RECEIPT + timedelta(seconds=1)
    assert (
        "complete=true" in result.source_reference and "snapshot=false" in result.source_reference
    )
    result.require_complete()


def test_full_page_followed_by_empty_page_is_exhausted_and_retains_empty_receipt():
    def handler(request):
        rows = [{"id": "one"}] if request.url.params["offset"] == "0" else []
        return httpx.Response(200, json=_body(request, rows))

    with _client(handler) as client:
        result = et.fetch_entsog_dataset(
            client, "connectionpoints", page_size=1, max_records=3, clock=lambda: RECEIPT
        )
    assert result.complete and len(result.pages) == 2
    assert result.pages[-1].record_count == 0
    assert result.pages[-1].raw_archive_values()["record_count"] == 0


@pytest.mark.parametrize("failure", ["http", "malformed"])
def test_failed_later_page_retains_validated_prefix_for_raw_archive_only(failure):
    def handler(request):
        if request.url.params["offset"] == "0":
            return httpx.Response(200, json=_body(request, [{"id": "one"}]))
        if failure == "http":
            return httpx.Response(503, text="Untrusted provider body")
        return httpx.Response(200, content=b"not json: untrusted provider body")

    with _client(handler) as client, pytest.raises(et.EntsogTransportError) as caught:
        et.fetch_entsog_dataset(
            client,
            "connectionpoints",
            page_size=1,
            max_records=3,
            attempts=1,
            clock=lambda: RECEIPT,
        )
    prefix = caught.value.validated_prefix_result
    assert prefix is not None and prefix.record_count == 1 and len(prefix.pages) == 1
    assert not prefix.complete and prefix.stop_reason == "transport_failed"
    assert prefix.pages[0].received_at_utc == RECEIPT
    assert (
        prefix.pages[0].raw_archive_values()["payload_sha256"]
        == hashlib.sha256(prefix.pages[0].raw_body).hexdigest()
    )
    assert "untrusted provider body" not in str(caught.value).lower()
    with pytest.raises(et.EntsogTruncationError):
        prefix.require_complete()


def test_empty_first_page_is_truthful_zero_rows_not_manufactured_data():
    with _client(lambda r: httpx.Response(200, json=_body(r, []))) as client:
        result = et.fetch_entsog_dataset(client, "operationaldatas")
    assert result.complete and result.record_count == 0
    # The ingestor must still reject zero canonical normalization as successful ingestion.
    assert len(result.pages) == 1


@pytest.mark.parametrize("budget,expected_limits", [(1, [1]), (3, [2, 1]), (4, [2, 2])])
def test_record_budget_never_overfetches_or_claims_exhaustion(budget, expected_limits):
    requests = []

    def handler(request):
        requests.append(request)
        offset = int(request.url.params["offset"])
        size = int(request.url.params["limit"])
        return httpx.Response(
            200, json=_body(request, [{"id": str(i)} for i in range(offset, offset + size)])
        )

    with _client(handler) as client:
        result = et.fetch_entsog_dataset(
            client, "connectionpoints", page_size=2, max_records=budget
        )
    assert [int(r.url.params["limit"]) for r in requests] == expected_limits
    assert result.record_count == budget and not result.complete
    assert result.stop_reason == "operator_record_budget"
    assert "complete=false" in result.source_reference
    with pytest.raises(et.EntsogTruncationError):
        result.require_complete()


def test_page_budget_is_independent_of_record_budget():
    with _client(lambda r: httpx.Response(200, json=_body(r, [{"id": "one"}]))) as client:
        result = et.fetch_entsog_dataset(
            client, "connectionpoints", page_size=1, max_records=10, max_pages=1
        )
    assert not result.complete and result.stop_reason == "operator_page_budget"
    assert result.budget_records == 10 and result.budget_pages == 1


def test_raw_receipt_after_body_and_exact_byte_archive_lineage():
    events = []
    raw = (
        b'{ "meta": {"limit":2,"offset":0,"count":1,"total":1,"sort":"id"},'
        b' "connectionpoints": [{"id":"one"}] }\n'
    )

    class Stream(httpx.SyncByteStream):
        def __iter__(self):
            events.append("body_started")
            yield raw[:40]
            yield raw[40:]
            events.append("body_finished")

        def close(self):
            events.append("closed")

    def clock():
        # httpx closes an exhausted stream while iter_bytes finishes.
        assert "body_finished" in events
        events.append("receipt")
        return RECEIPT.astimezone(timezone(timedelta(hours=8)))

    with _client(lambda r: httpx.Response(200, stream=Stream())) as client:
        page = et.fetch_entsog_dataset(client, "connectionpoints", page_size=2, clock=clock).pages[
            0
        ]
    assert events == ["body_started", "body_finished", "closed", "receipt"]
    assert page.raw_body == raw and page.received_at_utc == RECEIPT
    values = page.raw_archive_values()
    assert values["payload_text"].encode() == raw
    assert values["payload_sha256"] == hashlib.sha256(raw).hexdigest()
    assert values["record_count"] == 1 and values["received_at_utc"] == RECEIPT
    payload_copy = page.payload
    payload_copy["connectionpoints"][0]["id"] = "mutated"
    assert page.payload["connectionpoints"][0]["id"] == "one"
    assert raw.decode() not in repr(page)
    lineage = page.lineage_metadata(archive_id="raw-actually-persisted")
    assert lineage["archive_id"] == "raw-actually-persisted"
    assert lineage["payload_sha256"] == values["payload_sha256"]
    assert lineage["source_receipt_at_utc"] == RECEIPT.isoformat()
    assert lineage["source_request_url"] == page.request_url
    assert "request=" in lineage["source_reference"]
    with pytest.raises(ValueError):
        page.lineage_metadata(archive_id="")


@pytest.mark.parametrize(
    "overrides,error",
    [
        ({"limit": 3}, et.EntsogPaginationError),
        ({"offset": 9}, et.EntsogPaginationError),
        ({"count": 0}, et.EntsogPaginationError),
        ({"count": True}, et.EntsogMalformedResponseError),
        ({"total": "1"}, et.EntsogMalformedResponseError),
        ({"total": -1}, et.EntsogMalformedResponseError),
        ({"offset": None}, et.EntsogMalformedResponseError),
        ({"limit": 1.0}, et.EntsogMalformedResponseError),
        ({"sort": ""}, et.EntsogPaginationError),
        ({"sort": "-id"}, et.EntsogPaginationError),
    ],
)
def test_malformed_or_ignored_pagination_refused(overrides, error):
    with _client(
        lambda r: httpx.Response(200, json=_body(r, [{"id": "one"}], **overrides))
    ) as client:
        with pytest.raises(error):
            et.fetch_entsog_dataset(client, "connectionpoints", page_size=2)


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {},
        {"meta": {}, "connectionpoints": {}},
        {"error": "UNTRUSTED_RESPONSE_BODY"},
        {"message": "UNTRUSTED_RESPONSE_BODY"},
        {"meta": {}, "operationaldatas": []},
    ],
)
def test_wrong_or_error_envelope_refused_without_body_echo(payload):
    with _client(lambda r: httpx.Response(200, json=payload)) as client:
        with pytest.raises(et.EntsogMalformedResponseError) as caught:
            et.fetch_entsog_dataset(client, "connectionpoints")
    assert "UNTRUSTED_RESPONSE_BODY" not in str(caught.value)


@pytest.mark.parametrize("raw", [b"<html>UNTRUSTED</html>", b"\xff", b"{", b"null"])
def test_bad_encoding_and_json_are_stable_failures(raw):
    with _client(lambda r: httpx.Response(200, content=raw)) as client:
        with pytest.raises(et.EntsogMalformedResponseError) as caught:
            et.fetch_entsog_dataset(client, "connectionpoints")
    assert "UNTRUSTED" not in str(caught.value)
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None or caught.value.__suppress_context__


@pytest.mark.parametrize(
    "rows,error",
    [
        ([None], et.EntsogMalformedResponseError),
        ([{}], et.EntsogMalformedResponseError),
        ([{"id": 7}], et.EntsogMalformedResponseError),
        ([{"id": ""}], et.EntsogMalformedResponseError),
        ([{"id": "same"}, {"id": "same"}], et.EntsogPaginationError),
        ([{"id": "a"}, {"id": "b"}, {"id": "c"}], et.EntsogPaginationError),
    ],
)
def test_invalid_records_duplicates_and_oversized_page_refused(rows, error):
    with _client(lambda r: httpx.Response(200, json=_body(r, rows))) as client:
        with pytest.raises(error):
            et.fetch_entsog_dataset(client, "connectionpoints", page_size=2)


def test_changed_value_with_repeated_provider_id_aborts_traversal():
    def handler(request):
        offset = int(request.url.params["offset"])
        return httpx.Response(200, json=_body(request, [{"id": "same", "value": offset}]))

    with _client(handler) as client, pytest.raises(et.EntsogPaginationError):
        et.fetch_entsog_dataset(client, "operationaldatas", page_size=1)


def test_distinct_provider_ids_not_collapsed_by_transport():
    # ENTSOG can return distinct NA/actual records that later map to one canonical key.
    rows = [{"id": "key_NA0", "pointKey": "p"}, {"id": "key_NA1", "pointKey": "p"}]
    with _client(lambda r: httpx.Response(200, json=_body(r, rows))) as client:
        result = et.fetch_entsog_dataset(client, "operationaldatas", page_size=3)
    assert result.record_count == 2 and result.pages[0].payload["operationaldatas"] == rows


@pytest.mark.parametrize(
    "status,error",
    [
        (301, et.EntsogRedirectRefusedError),
        (307, et.EntsogRedirectRefusedError),
        (401, et.EntsogHttpError),
        (403, et.EntsogHttpError),
        (404, et.EntsogHttpError),
        (429, et.EntsogRateLimitedError),
        (503, et.EntsogHttpError),
    ],
)
def test_terminal_http_failures_and_redirects_never_return_data(status, error):
    requests, delays = [], []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            status, text="UNTRUSTED_ERROR", headers={"Location": "https://foreign.invalid/"}
        )

    with _client(handler, follow_redirects=True) as client:
        with pytest.raises(error) as caught:
            et.fetch_entsog_dataset(client, "connectionpoints", sleep=delays.append)
    assert caught.value.status_code == status
    assert "UNTRUSTED_ERROR" not in str(caught.value)
    assert all(r.url.host == "transparency.entsog.eu" for r in requests)
    assert len(requests) == (3 if status in [429, 503] else 1)
    assert len(delays) == len(requests) - 1


@pytest.mark.parametrize(
    "retry_after,expected",
    [
        ("99999", 30.0),
        ("nan", 1.0),
        ("-5", 1.0),
        ("nonsense", 1.0),
        ("0.5", 0.5),
    ],
)
def test_retry_after_is_bounded_and_success_keeps_only_successful_receipt(retry_after, expected):
    requests, delays, clock_calls = [], [], []

    def handler(request):
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(429, headers={"Retry-After": retry_after})
        return httpx.Response(200, json=_body(request, [{"id": "one"}]))

    def clock():
        clock_calls.append(True)
        return RECEIPT

    with _client(handler) as client:
        result = et.fetch_entsog_dataset(
            client, "connectionpoints", page_size=2, sleep=delays.append, clock=clock
        )
    assert delays == [expected] and len(clock_calls) == 1
    assert len(result.pages) == 1 and result.received_at_utc == RECEIPT


@pytest.mark.parametrize(
    "exception,error",
    [
        (httpx.ReadTimeout, et.EntsogTimeoutError),
        (httpx.ConnectError, et.EntsogTransportError),
    ],
)
def test_timeout_and_network_failure_retry_then_fail_without_exception_echo(exception, error):
    requests, delays = [], []

    def handler(request):
        requests.append(request)
        raise exception("UNTRUSTED_NETWORK_TEXT", request=request)

    with _client(handler) as client:
        with pytest.raises(error) as caught:
            et.fetch_entsog_dataset(client, "connectionpoints", sleep=delays.append)
    assert len(requests) == 3 and delays == [1.0, 2.0]
    assert caught.value.__suppress_context__ and "UNTRUSTED" not in str(caught.value)


def test_response_byte_ceiling_closes_stream_and_never_returns_page(monkeypatch):
    monkeypatch.setattr(et, "ENTSOG_MAX_RESPONSE_BYTES", 10)
    closed = []

    class Stream(httpx.SyncByteStream):
        def __iter__(self):
            yield b"123456"
            yield b"789012"

        def close(self):
            closed.append(True)

    with _client(lambda r: httpx.Response(200, stream=Stream())) as client:
        with pytest.raises(et.EntsogResponseTooLargeError):
            et.fetch_entsog_dataset(client, "connectionpoints")
    assert closed == [True]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"page_size": 0},
        {"page_size": True},
        {"page_size": 1001},
        {"max_records": 0},
        {"max_records": 50_001},
        {"max_records": 1.0},
        {"max_pages": 0},
        {"max_pages": 51},
        {"max_pages": False},
        {"attempts": 0},
        {"attempts": 4},
        {"timeout_seconds": float("inf")},
        {"timeout_seconds": 0},
        {"timeout_seconds": 61},
        {"timeout_seconds": True},
        {"filters": {"limit": "-1"}},
        {"filters": {"offset": "2"}},
        {"filters": {"sorting": "id"}},
        {"filters": {"sort": "id"}},
        {"filters": {"api_key": "secret"}},
        {"filters": {"indicator": ""}},
        {"filters": {"indicator": 7}},
    ],
)
def test_invalid_limits_or_control_parameter_injection_fail_before_send(kwargs):
    def handler(request):
        pytest.fail("Invalid configuration reached the network")

    with _client(handler) as client, pytest.raises(ValueError):
        et.fetch_entsog_dataset(client, "connectionpoints", **kwargs)


@pytest.mark.parametrize(
    "dataset",
    ["https://foreign.invalid/x", "../connectionpoints", "operationaldatas.csv", "unknown"],
)
def test_foreign_or_unknown_endpoint_fail_before_send(dataset):
    with _client(lambda r: pytest.fail("Unexpected network call")) as client:
        with pytest.raises(ValueError):
            et.fetch_entsog_dataset(client, dataset)


def test_naive_receipt_clock_is_refused():
    with _client(lambda r: httpx.Response(200, json=_body(r, []))) as client:
        with pytest.raises(ValueError, match="timezone-aware"):
            et.fetch_entsog_dataset(client, "connectionpoints", clock=lambda: datetime(2026, 1, 1))


def test_provider_total_is_preserved_without_assuming_its_semantics():
    with _client(
        lambda r: httpx.Response(200, json=_body(r, [{"id": "one"}], total=99999))
    ) as client:
        result = et.fetch_entsog_dataset(client, "connectionpoints", page_size=2)
    assert result.complete and result.pages[0].provider_total == 99999
    assert json.loads(result.pages[0].raw_body)["meta"]["total"] == 99999


@pytest.mark.parametrize("indicator", [None, "Firm Booked", "physical flow", {}, []])
def test_missing_wrong_or_wrong_case_indicator_cannot_become_physical_flow(indicator):
    row = {"id": "one", "indicator": indicator}
    with _client(lambda r: httpx.Response(200, json=_body(r, [row]))) as client:
        with pytest.raises(et.EntsogProductMismatchError):
            et.fetch_entsog_dataset(
                client, "operationaldatas", filters={"indicator": "Physical Flow"}
            )


def test_each_capacity_indicator_has_distinct_request_lineage():
    def handler(request):
        row = {"id": "one", "indicator": request.url.params["indicator"]}
        return httpx.Response(200, json=_body(request, [row]))

    with _client(handler) as client:
        results = [
            et.fetch_entsog_dataset(client, "operationaldatas", filters={"indicator": indicator})
            for indicator in ["Firm Booked", "Firm Technical"]
        ]
    pages = [r.pages[0] for r in results]
    assert pages[0].source_reference != pages[1].source_reference
    assert (
        pages[0].raw_archive_values()["source_reference"]
        != (pages[1].raw_archive_values()["source_reference"])
    )


def test_empty_indicator_component_fails_before_send():
    with _client(lambda r: pytest.fail("Invalid query reached network")) as client:
        with pytest.raises(ValueError):
            et.fetch_entsog_dataset(
                client, "operationaldatas", filters={"indicator": "Nomination,"}
            )
