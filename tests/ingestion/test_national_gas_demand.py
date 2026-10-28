"""Contract tests for the National Gas actual-demand ingestion adapter."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import httpx
import pytest

from eurogas_nexus.ingestion.national_gas_demand import (
    DOWNLOAD_URL,
    NationalGasDemandError,
    build_download_url,
    download_national_gas_csv,
    parse_national_gas_csv,
)

RECEIVED = datetime(2026, 10, 27, 13, 0, tzinfo=UTC)
HEADER = "Applicable At,Applicable For,Data Item,Value,Generated Time,Quality Indicator\n"


def csv_document(*rows: str) -> bytes:
    return (HEADER + "\n".join(rows) + "\n").encode()


def d1_row(
    *,
    applicable_at: str = "22/10/2026 12:20:01",
    gas_day: str = "21/10/2026",
    value: str = "176.708",
    generated: str = "22/10/2026 12:20:01",
    quality: str = "",
) -> str:
    return (
        f'{applicable_at},{gas_day},"Demand Actual, NTS, D+1",'
        f"{value},{generated},{quality}"
    )


def d6_row(
    *,
    applicable_at: str = "27/10/2026 10:20:01",
    gas_day: str = "21/10/2026",
    value: str = "176.596",
    generated: str = "27/10/2026 12:00:00",
    quality: str = "",
) -> str:
    return (
        f'{applicable_at},{gas_day},"Demand Actual, NTS, D+6",'
        f"{value},{generated},{quality}"
    )


def test_parser_preserves_exact_decimals_zero_quality_and_unresolved_publish_time():
    payload = csv_document(
        d1_row(value="0", generated="22/10/2026 10:20:00"),
        d1_row(value="176.590", quality="A"),
        d1_row(value="176.708", generated="23/10/2026 12:20:01"),
    )

    rows = parse_national_gas_csv(
        payload,
        provider_item_id="PUBOB637",
        date_from=date(2026, 10, 1),
        date_to=date(2026, 10, 31),
        received_at_utc=RECEIVED,
    )

    assert [row.value_text for row in rows] == ["0", "176.590", "176.708"]
    assert rows[0].value_text == "0"
    assert rows[1].quality_indicator == "A"
    assert rows[2].quality_indicator is None
    assert all(row.published_at_utc is None for row in rows)
    assert all(row.available_at_utc == RECEIVED for row in rows)
    assert rows[0].generated_at_naive == datetime(2026, 10, 22, 10, 20)
    assert rows[0].source_url == build_download_url(
        "PUBOB637", date(2026, 10, 1), date(2026, 10, 31)
    )
    assert rows[0].unit == "mscm"
    assert rows[1].is_provisional is True
    assert rows[1].provisional_status == "PROVISIONAL_INITIAL"


def test_d6_is_not_declared_final_and_revision_identity_is_generated_time_specific():
    payload = csv_document(
        d6_row(generated="27/10/2026 12:00:00"),
        d6_row(generated="28/10/2026 12:00:00", value="176.700"),
    )

    rows = parse_national_gas_csv(
        payload,
        provider_item_id="PUBOB652",
        date_from=date(2026, 10, 1),
        date_to=date(2026, 10, 31),
        received_at_utc=RECEIVED,
    )

    assert len({row.source_publication_id for row in rows}) == 2
    assert len({row.record_id for row in rows}) == 2
    assert rows[0].is_provisional is None
    assert rows[0].provisional_status == "UNRESOLVED_D_PLUS_6"
    assert rows[0].term == "D+6"


def test_gas_day_uses_eu_cam_05_00_gb_local_with_dst():
    # The 25-hour gas day is the one spanning the autumn transition:
    # 05:00 BST on 24 October (04:00 UTC) to 05:00 GMT on 25 October (05:00 UTC).
    payload = csv_document(
        d6_row(gas_day="24/10/2026", applicable_at="25/10/2026 10:20:01")
    )
    rows = parse_national_gas_csv(
        payload,
        provider_item_id="PUBOB652",
        date_from=date(2026, 10, 24),
        date_to=date(2026, 10, 24),
        received_at_utc=RECEIVED,
    )
    assert rows[0].period_end_utc - rows[0].period_start_utc == timedelta(hours=25)
    assert rows[0].period_start_utc.hour == 4

    spring = csv_document(
        d6_row(gas_day="28/03/2026", applicable_at="29/03/2026 10:20:01")
    )
    spring_rows = parse_national_gas_csv(
        spring,
        provider_item_id="PUBOB652",
        date_from=date(2026, 3, 28),
        date_to=date(2026, 3, 28),
        received_at_utc=RECEIVED,
    )
    assert (
        spring_rows[0].period_end_utc - spring_rows[0].period_start_utc
    ).total_seconds() == 23 * 3600


@pytest.mark.parametrize(
    ("payload", "item", "code"),
    [
        (b"", "PUBOB652", "EMPTY_RESPONSE"),
        (b" \n", "PUBOB652", "EMPTY_RESPONSE"),
        (b"wrong,header\n", "PUBOB652", "HEADER_DRIFT"),
        (
            csv_document(d1_row(gas_day="21/10/2026", value="nan")),
            "PUBOB637",
            "INVALID_VALUE",
        ),
        (
            csv_document(d1_row(gas_day="20/09/2026")),
            "PUBOB637",
            "ROW_OUTSIDE_WINDOW",
        ),
        (
            HEADER.replace("Quality Indicator", "Quality").encode(),
            "PUBOB637",
            "HEADER_DRIFT",
        ),
        (
            csv_document(
                '21/10/2026 01:00:00,21/10/2026,"Demand Actual, NTS, D+1 (Energy)",6,'
                "22/10/2026 10:01:01,L"
            ),
            "PUBOB637",
            "UNKNOWN_SERIES",
        ),
    ],
)
def test_parser_refuses_empty_drift_malformed_and_unapproved_series(payload, item, code):
    with pytest.raises(NationalGasDemandError) as exc:
        parse_national_gas_csv(
            payload,
            provider_item_id=item,
            date_from=date(2026, 10, 1),
            date_to=date(2026, 10, 31),
            received_at_utc=RECEIVED,
        )
    assert exc.value.code == code


def test_http_request_is_fixed_origin_bounded_and_retries_429():
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(429, text="rate limited", request=request)
        return httpx.Response(200, content=csv_document(d6_row()), request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = download_national_gas_csv(
            "PUBOB652",
            date_from=date(2026, 10, 1),
            date_to=date(2026, 10, 31),
            client=client,
            max_attempts=2,
            sleep=lambda _seconds: None,
            received_at_utc=RECEIVED,
        )

    assert len(calls) == 2
    request = calls[0]
    assert request.method == "GET"
    assert f"{request.url.scheme}://{request.url.host}{request.url.path}" == DOWNLOAD_URL
    assert dict(request.url.params) == {
        "applicableFor": "Y",
        "dateFrom": "2026-10-01",
        "dateTo": "2026-10-31",
        "dateType": "GASDAY",
        "latestFlag": "N",
        "ids": "PUBOB652",
        "type": "CSV",
    }
    assert request.headers["accept"] == "text/csv"
    assert "authorization" not in request.headers
    assert result.rows[0].value_text == "176.596"
    assert result.source_url == str(request.url)


def test_http_refuses_redirect_oversize_and_unknown_series():
    redirect_calls = 0

    def redirect_handler(request: httpx.Request) -> httpx.Response:
        nonlocal redirect_calls
        redirect_calls += 1
        return httpx.Response(
            302,
            headers={"location": "https://example.invalid/data.csv"},
            request=request,
        )

    with httpx.Client(
        transport=httpx.MockTransport(redirect_handler), follow_redirects=False
    ) as client:
        with pytest.raises(NationalGasDemandError) as redirect:
            download_national_gas_csv(
                "PUBOB652",
                date_from=date(2026, 10, 1),
                date_to=date(2026, 10, 31),
                client=client,
                sleep=lambda _seconds: None,
                received_at_utc=RECEIVED,
            )
    assert redirect.value.code == "REDIRECT_REFUSED"
    assert redirect_calls == 1

    def oversized(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-length": "2097153"},
            request=request,
        )

    with httpx.Client(transport=httpx.MockTransport(oversized)) as client:
        with pytest.raises(NationalGasDemandError) as too_large:
            download_national_gas_csv(
                "PUBOB652",
                date_from=date(2026, 10, 1),
                date_to=date(2026, 10, 31),
                client=client,
                received_at_utc=RECEIVED,
            )
    assert too_large.value.code == "RESPONSE_TOO_LARGE"

    with pytest.raises(NationalGasDemandError) as unknown:
        download_national_gas_csv(
            "PUBOBJ1030",
            date_from=date(2026, 10, 1),
            date_to=date(2026, 10, 31),
            sleep=lambda _seconds: None,
            received_at_utc=RECEIVED,
        )
    assert unknown.value.code == "UNKNOWN_SERIES"
