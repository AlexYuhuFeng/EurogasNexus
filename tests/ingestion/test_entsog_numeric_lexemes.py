"""RFC 0005 numeric-lexeme tests for archived ENTSOG pages; no network."""

from __future__ import annotations

import hashlib
import math
from datetime import UTC, datetime

import pytest

from eurogas_nexus.ingestion import entsog_transport as et

RECEIPT = datetime(2026, 10, 12, 15, 30, tzinfo=UTC)

# Hand-written so number spellings survive; json.dumps would normalize them.
RAW_BODY = (
    b"{"
    b'"meta":{"limit":10,"offset":0,"count":1,"total":1,"sort":"id"},'
    b'"operationaldatas":[{'
    b'"id":"obs-1",'
    b'"indicator":"Nomination",'
    b'"valueDecimal":123456789012345678901234567890.123456789012345678901234567890,'
    b'"valueScientific":1e-06,'
    b'"valueUpperScientific":1E+3,'
    b'"valueNegativeZero":-0.000,'
    b'"valueTrailingZeros":1.2300,'
    b'"valueInteger":42,'
    b'"sourceSpelling":"001.2300",'
    b'"plain":"unchanged"'
    b"}]}"
)

HUGE_DECIMAL = "123456789012345678901234567890.123456789012345678901234567890"


def _page(raw_body: bytes = RAW_BODY) -> et.EntsogPage:
    return et.EntsogPage(
        dataset="operationaldatas",
        offset=0,
        requested_limit=10,
        record_count=1,
        provider_total=1,
        request_url="https://example.invalid/api/v1/operationaldatas?limit=10&offset=0",
        received_at_utc=RECEIPT,
        raw_body=raw_body,
    )


def test_numeric_lexeme_payload_preserves_exact_numbers_and_strings():
    lexemes = _page().numeric_lexeme_payload
    row = lexemes["operationaldatas"][0]

    assert row["valueDecimal"] == HUGE_DECIMAL
    assert row["valueScientific"] == "1e-06"
    assert row["valueUpperScientific"] == "1E+3"
    assert row["valueNegativeZero"] == "-0.000"
    assert row["valueTrailingZeros"] == "1.2300"
    assert row["valueInteger"] == "42"
    assert row["sourceSpelling"] == "001.2300"
    assert row["plain"] == "unchanged"
    assert lexemes["meta"] == {
        "limit": "10",
        "offset": "0",
        "count": "1",
        "total": "1",
        "sort": "id",
    }


def test_numeric_lexeme_payload_is_a_fresh_nonarchived_copy():
    page = _page()
    lexemes = page.numeric_lexeme_payload
    lexemes["operationaldatas"][0]["id"] = "mutated"
    assert page.numeric_lexeme_payload["operationaldatas"][0]["id"] == "obs-1"


def test_default_payload_keeps_native_json_numbers_and_integer_total():
    page = _page()
    payload = page.payload
    assert type(payload["meta"]["total"]) is int
    assert payload["meta"]["total"] == 1

    row = payload["operationaldatas"][0]
    assert type(row["valueInteger"]) is int and row["valueInteger"] == 42
    assert type(row["valueScientific"]) is float
    assert row["valueScientific"] == 1e-06
    assert type(row["valueUpperScientific"]) is float
    assert row["valueUpperScientific"] == 1e3
    assert type(row["valueNegativeZero"]) is float
    assert math.copysign(1.0, row["valueNegativeZero"]) == -1.0
    assert type(row["valueTrailingZeros"]) is float
    assert row["valueTrailingZeros"] == 1.23
    assert type(row["valueDecimal"]) is float
    assert row["sourceSpelling"] == "001.2300"

    values = page.raw_archive_values()
    assert values["payload_sha256"] == hashlib.sha256(RAW_BODY).hexdigest()
    assert values["payload_text"] == RAW_BODY.decode("utf-8")
    assert type(values["payload_json"]["meta"]["total"]) is int
    assert values["payload_json"]["meta"]["total"] == 1


def test_lexeme_view_does_not_change_raw_bytes_hash_receipt_or_lineage():
    page = _page()
    lineage_before = page.lineage_metadata(archive_id="raw-1")
    archive_before = page.raw_archive_values()

    _ = page.numeric_lexeme_payload

    assert page.raw_body == RAW_BODY
    assert page.payload_sha256 == hashlib.sha256(RAW_BODY).hexdigest()
    assert page.received_at_utc == RECEIPT
    assert type(page.payload["meta"]["total"]) is int
    assert page.raw_archive_values() == archive_before
    assert page.lineage_metadata(archive_id="raw-1") == lineage_before


@pytest.mark.parametrize(
    "raw_body",
    [
        b'{"operationaldatas": ["\xff"]}',
        b"[]",
        b"null",
        b'"text"',
        b'{"operationaldatas": [}',
        b'{"value": NaN}',
        b'{"value": Infinity}',
        b'{"value": -Infinity}',
    ],
)
def test_numeric_lexeme_payload_refuses_non_utf8_nonobject_invalid_and_nonfinite(raw_body):
    with pytest.raises(et.EntsogMalformedResponseError) as caught:
        _ = _page(raw_body).numeric_lexeme_payload
    assert isinstance(caught.value, et.EntsogTransportError)
    assert caught.value.code == "entsog_malformed_response"
    assert caught.value.__cause__ is None


def test_default_payload_still_accepts_json_nonfinite_constants_unchanged():
    page = _page(b'{"value": NaN}')
    assert math.isnan(page.payload["value"])
    with pytest.raises(et.EntsogMalformedResponseError):
        _ = page.numeric_lexeme_payload
