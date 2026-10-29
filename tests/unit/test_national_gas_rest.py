"""Focused contract and transport tests for the National Gas REST adapter."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from decimal import Decimal

import httpx
import pytest

from eurogas_nexus.ingestion.national_gas_rest import (
    API_URL,
    D1_PUBLICATION_ID,
    D6_PUBLICATION_ID,
    EVIDENCE_BASIS,
    MAX_RESPONSE_BYTES,
    NationalGasRestError,
    QualityFlag,
    build_published_time_request,
    fetch_national_gas_rest,
    parse_national_gas_rest,
)

RECEIVED = datetime(2026, 11, 5, 9, 30, tzinfo=UTC)
WINDOW_START = date(2026, 10, 20)
WINDOW_END = date(2026, 10, 26)


def _record(**overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "applicableAt": "2026-10-26T10:20:01+00:00",
        "applicableFor": "2026-10-25",
        "value": "21.2189",
        "generatedTimeStamp": "2026-10-26T10:20:01+00:00",
        "qualityIndicator": "",
        "substituted": "N",
        "createdDate": "2026-10-26T10:20:01+00:00",
    }
    record.update(overrides)
    return record


def _group(
    records: list[dict[str, object]] | None = None,
    *,
    publication_id: str = D1_PUBLICATION_ID,
    publication_name: str = "Demand Actual, NTS, D+1",
    **overrides: object,
) -> dict[str, object]:
    group: dict[str, object] = {
        "publicationId": publication_id,
        "publicationName": publication_name,
        "publications": records if records is not None else [_record()],
    }
    group.update(overrides)
    return group


def _json(groups: list[dict[str, object]]) -> bytes:
    return json.dumps(groups, separators=(",", ":")).encode("utf-8")


def _parse(payload: bytes, **overrides: object):
    arguments: dict[str, object] = {
        "date_from": WINDOW_START,
        "date_to": WINDOW_END,
        "received_at_utc": RECEIVED,
    }
    arguments.update(overrides)
    return parse_national_gas_rest(payload, **arguments)


def test_parser_preserves_exact_value_quality_and_receipt_boundaries() -> None:
    payload = _json(
        [
            _group(
                [
                    _record(value="0", qualityIndicator="", substituted="N"),
                    _record(
                        applicableAt="2026-10-26T11:20:01+00:00",
                        generatedTimeStamp="2026-10-26T11:20:01+00:00",
                        createdDate="2026-10-26T11:20:01+00:00",
                        value="",
                        qualityIndicator="A",
                        substituted="Y",
                    ),
                    _record(
                        applicableAt="2026-10-26T12:20:01+00:00",
                        generatedTimeStamp="2026-10-26T12:20:01+00:00",
                        createdDate="2026-10-26T12:20:01+00:00",
                        value="0.000",
                        qualityIndicator="S",
                        substituted="N",
                    ),
                ]
            )
        ]
    )

    rows = _parse(payload)

    assert len(rows) == 3
    assert [row.value_text for row in rows] == ["0", "", "0.000"]
    assert rows[0].value_decimal == Decimal("0")
    assert rows[1].value_decimal is None
    assert rows[1].value_is_blank is True
    assert [row.quality_flag for row in rows] == [
        QualityFlag.UNKNOWN,
        QualityFlag.AMENDED,
        QualityFlag.SUBSTITUTED,
    ]
    assert rows[1].quality_indicator_raw == "A"
    assert rows[2].quality_indicator_raw == "S"
    assert rows[1].is_substituted is True
    assert rows[2].is_substituted is False
    assert all(row.raw_sha256 == hashlib.sha256(payload).hexdigest() for row in rows)
    assert rows[0].provider_timestamp_upper_bound_utc == datetime(
        2026, 10, 26, 10, 20, 1, tzinfo=UTC
    )
    assert rows[0].received_at_utc == RECEIVED
    assert rows[0].current_received_at_utc == RECEIVED
    assert rows[0].available_at_utc == RECEIVED
    assert rows[0].provider_timestamp_upper_bound_utc != rows[0].received_at_utc
    assert rows[0].evidence_basis == EVIDENCE_BASIS
    assert EVIDENCE_BASIS == "PROVIDER_DECLARED_TIMESTAMP_UPPER_BOUND"
    assert not hasattr(rows[0], "published_at_utc")
    assert rows[0].unit == "mscm"
    assert rows[0].term == "D+1"
    assert rows[0].is_provisional is True


def test_dst_offsets_are_normalized_without_losing_raw_spelling() -> None:
    payload = _json(
        [
            _group(
                [
                    _record(
                        applicableAt="2026-10-25T01:30:00+01:00",
                        generatedTimeStamp="2026-10-25T01:30:00+01:00",
                        createdDate="2026-10-25T01:30:00+01:00",
                    ),
                    _record(
                        applicableAt="2026-10-25T01:30:00+00:00",
                        generatedTimeStamp="2026-10-25T01:30:00+00:00",
                        createdDate="2026-10-25T01:30:00+00:00",
                    ),
                ]
            )
        ]
    )

    first, second = _parse(payload)

    assert first.applicable_at_utc == datetime(2026, 10, 25, 0, 30, tzinfo=UTC)
    assert second.applicable_at_utc == datetime(2026, 10, 25, 1, 30, tzinfo=UTC)
    assert first.applicable_at_raw == "2026-10-25T01:30:00+01:00"
    assert second.applicable_at_raw == "2026-10-25T01:30:00+00:00"
    assert first.generated_at_utc == datetime(2026, 10, 25, 0, 30, tzinfo=UTC)
    assert first.created_at_utc == datetime(2026, 10, 25, 0, 30, tzinfo=UTC)
    assert first.generated_at_raw == "2026-10-25T01:30:00+01:00"
    assert first.created_at_raw == "2026-10-25T01:30:00+01:00"
    assert first.provider_timestamp_upper_bound_utc == first.applicable_at_utc
    assert first.applicable_for == date(2026, 10, 25)
    assert first.applicable_for_raw == "2026-10-25"
    assert first.record_id != second.record_id


def test_divergent_provider_clocks_are_preserved_and_upper_bound_is_latest() -> None:
    payload = _json(
        [
            _group(
                [
                    _record(
                        applicableAt="2026-10-26T11:20:01+01:00",
                        generatedTimeStamp="2026-10-26T11:25:02+01:00",
                        createdDate="2026-10-26T09:00:00+00:00",
                    )
                ]
            )
        ]
    )

    row = _parse(payload)[0]

    assert row.applicable_at_utc == datetime(2026, 10, 26, 10, 20, 1, tzinfo=UTC)
    assert row.generated_at_utc == datetime(2026, 10, 26, 10, 25, 2, tzinfo=UTC)
    assert row.created_at_utc == datetime(2026, 10, 26, 9, 0, 0, tzinfo=UTC)
    assert row.applicable_at_raw == "2026-10-26T11:20:01+01:00"
    assert row.generated_at_raw == "2026-10-26T11:25:02+01:00"
    assert row.created_at_raw == "2026-10-26T09:00:00+00:00"
    assert row.provider_timestamp_upper_bound_utc == datetime(
        2026, 10, 26, 10, 25, 2, tzinfo=UTC
    )
    assert row.received_at_utc == RECEIVED
    assert row.current_received_at_utc == RECEIVED
    assert row.available_at_utc == RECEIVED
    assert row.available_at_utc > row.provider_timestamp_upper_bound_utc
    assert row.evidence_basis == EVIDENCE_BASIS


@pytest.mark.parametrize("field", ["applicableAt", "generatedTimeStamp", "createdDate"])
def test_parser_refuses_naive_provider_timestamps(field: str) -> None:
    payload = _json([_group([_record(**{field: "2026-10-26T10:20:01"})])])

    with pytest.raises(NationalGasRestError) as caught:
        _parse(payload)

    assert caught.value.code == "NAIVE_TIMESTAMP"


def test_parser_refuses_a_time_in_applicable_for() -> None:
    payload = _json(
        [_group([_record(applicableFor="2026-10-25T00:00:00+00:00")])]
    )

    with pytest.raises(NationalGasRestError) as caught:
        _parse(payload)

    assert caught.value.code == "MALFORMED_APPLICABLE_FOR"


def test_late_amendment_is_a_distinct_evidence_revision_and_d6_is_not_final() -> None:
    old = _record(
        applicableAt="2026-10-26T10:20:01+00:00",
        generatedTimeStamp="2026-10-26T10:20:01+00:00",
        createdDate="2026-10-26T10:20:01+00:00",
        value="100",
    )
    amended = _record(
        applicableAt="2026-11-04T15:00:00+00:00",
        generatedTimeStamp="2026-11-04T15:01:00+00:00",
        createdDate="2026-11-04T15:02:00+00:00",
        value="101",
        qualityIndicator="A",
        substituted="N",
    )
    d6 = _record(
        applicableAt="2026-10-26T10:20:01+00:00",
        generatedTimeStamp="2026-10-26T10:20:01+00:00",
        createdDate="2026-10-26T10:20:01+00:00",
    )
    payload = _json(
        [
            _group([old, amended]),
            _group(
                [d6],
                publication_id=D6_PUBLICATION_ID,
                publication_name="Demand Actual, NTS, D+6",
            ),
        ]
    )

    rows = _parse(payload)
    d1_rows = [row for row in rows if row.publication_id == D1_PUBLICATION_ID]
    d6_row = next(row for row in rows if row.publication_id == D6_PUBLICATION_ID)

    assert len(d1_rows) == 2
    assert d1_rows[0].record_id != d1_rows[1].record_id
    assert d1_rows[0].provider_timestamp_upper_bound_utc == datetime(
        2026, 10, 26, 10, 20, 1, tzinfo=UTC
    )
    assert d1_rows[1].provider_timestamp_upper_bound_utc == datetime(
        2026, 11, 4, 15, 2, tzinfo=UTC
    )
    assert d1_rows[0].created_at_raw == "2026-10-26T10:20:01+00:00"
    assert d1_rows[1].created_at_raw == "2026-11-04T15:02:00+00:00"
    assert d1_rows[1].applicable_at_raw == "2026-11-04T15:00:00+00:00"
    assert d1_rows[1].generated_at_raw == "2026-11-04T15:01:00+00:00"
    assert all(row.received_at_utc == RECEIVED for row in d1_rows)
    assert all(row.available_at_utc == RECEIVED for row in d1_rows)
    assert all(row.evidence_basis == EVIDENCE_BASIS for row in d1_rows)
    assert d1_rows[1].quality_flag is QualityFlag.AMENDED
    assert d6_row.term == "D+6"
    assert d6_row.provisional_status == "UNRESOLVED_D_PLUS_6"
    assert d6_row.is_provisional is None
    assert "FINAL" not in d6_row.provisional_status


def test_identical_revision_content_is_stable_across_payload_spelling() -> None:
    first_payload = _json([_group()])
    second_payload = json.dumps([_group()], indent=2).encode("utf-8")

    first = _parse(first_payload)[0]
    second = _parse(second_payload)[0]

    assert first.record_id == second.record_id
    assert first.source_publication_id == second.source_publication_id
    assert first.raw_sha256 != second.raw_sha256


@pytest.mark.parametrize(
    ("groups", "expected_code"),
    [
        (
            [
                _group(
                    publication_id="PUBOB999",
                    publication_name="Unknown publication",
                )
            ],
            "UNKNOWN_PUBLICATION",
        ),
        (
            [_group(publication_name="Demand Actual, NTS, D+2")],
            "PUBLICATION_NAME_MISMATCH",
        ),
        ([_group(unit="kWh")], "UNKNOWN_UNIT"),
        (
            [_group([_record(unit="kWh")])],
            "UNKNOWN_UNIT",
        ),
        (
            [_group([_record(qualityIndicator="L")])],
            "UNKNOWN_QUALITY",
        ),
    ],
)
def test_parser_refuses_unknown_identity_fields(
    groups: list[dict[str, object]], expected_code: str
) -> None:
    with pytest.raises(NationalGasRestError) as caught:
        _parse(_json(groups))

    assert caught.value.code == expected_code


def test_parser_refuses_a_publication_outside_the_requested_scope() -> None:
    payload = _json(
        [
            _group(
                publication_id=D6_PUBLICATION_ID,
                publication_name="Demand Actual, NTS, D+6",
            )
        ]
    )

    with pytest.raises(NationalGasRestError) as caught:
        _parse(payload, publication_ids=[D1_PUBLICATION_ID])

    assert caught.value.code == "UNEXPECTED_PUBLICATION"


def test_parser_refuses_duplicate_publication_groups() -> None:
    payload = _json([_group(), _group()])

    with pytest.raises(NationalGasRestError) as caught:
        _parse(payload)

    assert caught.value.code == "DUPLICATE_PUBLICATION"


def test_parser_refuses_oversize_and_empty_payloads() -> None:
    with pytest.raises(NationalGasRestError) as too_large:
        _parse(b" " * (MAX_RESPONSE_BYTES + 1))
    assert too_large.value.code == "RESPONSE_TOO_LARGE"

    with pytest.raises(NationalGasRestError) as empty:
        _parse(b"[]")
    assert empty.value.code == "NO_DATA"


def test_request_body_has_rfc3339_applicable_at_window_and_never_requests_latest_only() -> None:
    body = build_published_time_request(WINDOW_START, WINDOW_END)

    assert body == {
        "fromDate": "2026-10-20T00:00:00+00:00",
        "toDate": "2026-10-26T23:59:59+00:00",
        "publicationIds": [D1_PUBLICATION_ID, D6_PUBLICATION_ID],
        "latestValue": "N",
    }

    with pytest.raises(NationalGasRestError) as too_long:
        build_published_time_request(date(2026, 10, 1), date(2026, 11, 1))
    assert too_long.value.code == "INVALID_WINDOW"


def test_query_window_uses_applicable_at_without_requiring_gas_day_inside_dates() -> None:
    payload = _json(
        [
            _group(
                [
                    _record(
                        applicableAt="2026-10-26T10:20:01+00:00",
                        applicableFor="2026-09-01",
                    )
                ]
            )
        ]
    )

    row = _parse(payload)[0]

    assert row.applicable_for == date(2026, 9, 1)
    assert row.applicable_for_raw == "2026-09-01"
    assert row.applicable_at_utc == datetime(2026, 10, 26, 10, 20, 1, tzinfo=UTC)


def test_fetch_uses_fixed_post_and_keeps_raw_receipt_independent() -> None:
    payload = _json([_group()])
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            content=payload,
            headers={"Content-Type": "application/json"},
        )

    download = fetch_national_gas_rest(
        WINDOW_START,
        WINDOW_END,
        transport=httpx.MockTransport(handler),
        received_at_utc=RECEIVED,
    )

    assert len(seen) == 1
    request = seen[0]
    assert request.method == "POST"
    assert str(request.url) == API_URL
    assert request.url.query == b""
    assert "authorization" not in request.headers
    assert "cookie" not in request.headers
    assert request.headers["content-type"] == "application/json"
    assert json.loads(request.content) == build_published_time_request(
        WINDOW_START, WINDOW_END
    )
    assert download.raw_json == payload
    assert download.raw_sha256 == hashlib.sha256(payload).hexdigest()
    assert download.request_body == request.content
    assert download.received_at_utc == RECEIVED
    assert download.rows[0].provider_timestamp_upper_bound_utc == datetime(
        2026, 10, 26, 10, 20, 1, tzinfo=UTC
    )
    assert download.rows[0].created_at_raw == "2026-10-26T10:20:01+00:00"
    assert download.rows[0].received_at_utc == RECEIVED
    assert download.rows[0].available_at_utc == RECEIVED


def test_fetch_retries_429_and_5xx_with_a_bound() -> None:
    payload = _json([_group()])
    statuses = [500, 429, 200]
    calls: list[httpx.Request] = []
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        status = statuses[len(calls) - 1]
        if status == 200:
            return httpx.Response(200, content=payload)
        return httpx.Response(status)

    download = fetch_national_gas_rest(
        WINDOW_START,
        WINDOW_END,
        transport=httpx.MockTransport(handler),
        max_attempts=3,
        sleep=sleeps.append,
        received_at_utc=RECEIVED,
    )

    assert len(calls) == 3
    assert sleeps == [0.25, 0.5]
    assert download.raw_sha256 == hashlib.sha256(payload).hexdigest()


def test_fetch_refuses_redirects_without_following_them() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(302, headers={"Location": "https://example.invalid/steal"})

    with pytest.raises(NationalGasRestError) as caught:
        fetch_national_gas_rest(
            WINDOW_START,
            WINDOW_END,
            transport=httpx.MockTransport(handler),
            received_at_utc=RECEIVED,
        )

    assert caught.value.code == "REDIRECT_REFUSED"
    assert len(calls) == 1


def test_fetch_does_not_retry_a_client_error() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(400)

    with pytest.raises(NationalGasRestError) as caught:
        fetch_national_gas_rest(
            WINDOW_START,
            WINDOW_END,
            transport=httpx.MockTransport(handler),
            max_attempts=3,
            received_at_utc=RECEIVED,
        )

    assert caught.value.code == "HTTP_STATUS"
    assert len(calls) == 1


def test_fetch_bounds_declared_response_size_before_reading_it() -> None:
    oversized = str(MAX_RESPONSE_BYTES + 1)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=b"[]", headers={"Content-Length": oversized}
        )

    with pytest.raises(NationalGasRestError) as caught:
        fetch_national_gas_rest(
            WINDOW_START,
            WINDOW_END,
            transport=httpx.MockTransport(handler),
            received_at_utc=RECEIVED,
        )

    assert caught.value.code == "RESPONSE_TOO_LARGE"


def test_fetch_reports_transport_failure_as_a_typed_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with pytest.raises(NationalGasRestError) as caught:
        fetch_national_gas_rest(
            WINDOW_START,
            WINDOW_END,
            transport=httpx.MockTransport(handler),
            max_attempts=1,
            received_at_utc=RECEIVED,
        )

    assert caught.value.code == "HTTP_TRANSPORT_ERROR"


def test_fetch_validates_window_before_any_http_call() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, content=b"[]")

    with pytest.raises(NationalGasRestError) as caught:
        fetch_national_gas_rest(
            date(2026, 10, 1),
            date(2026, 11, 1),
            transport=httpx.MockTransport(handler),
            received_at_utc=RECEIVED,
        )

    assert caught.value.code == "INVALID_WINDOW"
    assert calls == []
