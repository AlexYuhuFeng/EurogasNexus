"""Tests for the bounded EEX public-download transport and acquisition CLI.

Every response below is a synthetic ``httpx.MockTransport`` response. No test contacts EEX, uses
a live credential, writes a database or claims that the captured prices are live/ready data.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType

import httpx
import pytest

from eurogas_nexus.ingestion.eex_ngp import SOURCE_FILE_URL, SOURCE_PAGE_URL
from eurogas_nexus.ingestion.eex_ngp_capture import (
    MAX_CAPTURE_BYTES,
    EexNgpCaptureError,
    inspect_eex_ngp_capture,
)
from eurogas_nexus.ingestion.eex_public_download import (
    EexPublicDownloadError,
    fetch_eex_public_capture,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
TRANSPORT_MODULE = REPO_ROOT / "src" / "eurogas_nexus" / "ingestion" / "eex_public_download.py"
CLI_MODULE = REPO_ROOT / "scripts" / "ops" / "fetch_eex_public_capture.py"
HEADER = "Gasday;IndexValue (€/MWh);IndexVolume (MWh);Status;Timestamp Let"
RETRIEVED_AT = datetime(2026, 5, 29, 15, 5, tzinfo=UTC)
ROW = "29/05/2026;31.400;1200.5;Final NGP;29/05/2026 14:30"


def _csv_bytes(
    *rows: str,
    bom: bool = True,
    newline: str = "\r\n",
) -> bytes:
    text = newline.join([HEADER, *(rows or (ROW,))]) + newline
    encoded = text.encode("utf-8")
    return (b"\xef\xbb\xbf" + encoded) if bom else encoded


def _load_cli() -> ModuleType:
    spec = importlib.util.spec_from_file_location("eex_public_capture_cli", CLI_MODULE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _error(
    handler: object,
    *,
    sleeps: list[float] | None = None,
) -> EexPublicDownloadError:
    def sleep_never(seconds: float) -> None:
        if sleeps is not None:
            sleeps.append(seconds)

    with pytest.raises(EexPublicDownloadError) as raised:
        fetch_eex_public_capture(
            transport=httpx.MockTransport(handler),  # type: ignore[arg-type]
            clock=lambda: RETRIEVED_AT,
            sleep=sleep_never,
        )
    return raised.value


def _ok_response(body: bytes, media_type: str = "text/csv") -> httpx.Response:
    return httpx.Response(
        200,
        headers={
            "Content-Type": f"{media_type}; charset=utf-8",
            "Content-Length": str(len(body)),
        },
        stream=httpx.ByteStream(body),
    )


def test_download_preserves_exact_bom_crlf_bytes_hash_and_source_urls() -> None:
    body = _csv_bytes(newline="\r\n")
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return _ok_response(body)

    capture = fetch_eex_public_capture(
        transport=httpx.MockTransport(handler),
        clock=lambda: RETRIEVED_AT,
        sleep=lambda _seconds: pytest.fail("a successful request must not sleep"),
    )

    assert len(seen) == 1
    request = seen[0]
    assert request.method == "GET"
    assert str(request.url) == SOURCE_FILE_URL
    assert request.url.query == b""
    assert request.headers.get("accept-encoding") == "identity"
    assert request.headers.get("cookie") is None
    assert request.headers.get("authorization") is None

    assert capture.raw_bytes == body
    assert capture.raw_byte_length == len(body)
    assert capture.raw_sha256 == hashlib.sha256(body).hexdigest()
    assert capture.bom_present is True
    assert capture.source_url == SOURCE_FILE_URL
    assert capture.final_url == SOURCE_FILE_URL
    assert capture.retrieved_at_utc == RETRIEVED_AT
    assert capture.content_type == "text/csv"
    assert capture.content_encoding == "identity"
    assert capture.status_code == 200
    assert capture.http_attempts == 1
    assert capture.redirect_count == 0

    report = inspect_eex_ngp_capture(body, retrieved_at_utc=capture.retrieved_at_utc)
    assert report["ok"] is True
    assert report["raw_sha256"] == capture.raw_sha256
    assert report["raw_byte_length"] == capture.raw_byte_length
    assert report["bom_present"] is True
    assert report["source_page_url"] == SOURCE_PAGE_URL
    assert report["source_file_url"] == SOURCE_FILE_URL


@pytest.mark.parametrize(
    "media_type",
    ["text/csv", "Text/Plain", "application/octet-stream"],
)
def test_accepted_csv_media_types_still_require_the_existing_parser(media_type: str) -> None:
    capture = fetch_eex_public_capture(
        transport=httpx.MockTransport(lambda _request: _ok_response(_csv_bytes(), media_type)),
        clock=lambda: RETRIEVED_AT,
        sleep=lambda _seconds: None,
    )

    report = inspect_eex_ngp_capture(
        capture.raw_bytes, retrieved_at_utc=capture.retrieved_at_utc
    )
    assert report["ok"] is True
    assert report["row_count"] == 1


def test_an_html_body_is_refused_even_when_the_media_type_lies() -> None:
    body = b"<!DOCTYPE html><html><body>not the EEX CSV</body></html>"

    error = _error(lambda _request: _ok_response(body))

    assert error.code == "html_payload"


def test_an_html_media_type_is_refused_before_the_body_is_treated_as_csv() -> None:
    error = _error(lambda _request: _ok_response(_csv_bytes(), "text/html"))

    assert error.code == "unexpected_content_type"


def test_oversized_content_length_is_refused_without_accepting_a_body() -> None:
    error = _error(
        lambda _request: _ok_response(b"x" * (MAX_CAPTURE_BYTES + 1)),
    )

    assert error.code == "payload_too_large"
    assert str(MAX_CAPTURE_BYTES) in error.message


@pytest.mark.parametrize(
    ("location", "code"),
    [
        ("http://gasandregistry.eex.com/Gas/NGP/TTF_NGP_15_Mins.csv", "redirect_not_https"),
        ("https://user:secret@gasandregistry.eex.com/Gas/NGP/file.csv", "redirect_userinfo"),
        ("https://evil.example/Gas/NGP/file.csv", "redirect_host_not_approved"),
        ("https://gasandregistry.eex.com:444/Gas/NGP/file.csv", "redirect_port_not_approved"),
    ],
)
def test_each_redirect_is_validated_against_https_official_hosts(
    location: str, code: str
) -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(302, headers={"Location": location})

    error = _error(handler)

    assert error.code == code
    assert len(calls) == 1


def test_a_redirect_to_the_approved_eex_page_host_is_followed_once_manually() -> None:
    calls: list[str] = []
    body = _csv_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if len(calls) == 1:
            return httpx.Response(
                302,
                headers={
                    "Location": "https://www.eex.com/en/markets/natural-gas/gas-market-transparency"
                },
            )
        return _ok_response(body)

    capture = fetch_eex_public_capture(
        transport=httpx.MockTransport(handler),
        clock=lambda: RETRIEVED_AT,
        sleep=lambda _seconds: pytest.fail("redirects must not sleep"),
    )

    assert len(calls) == 2
    assert capture.raw_bytes == body
    assert capture.redirect_count == 1
    assert capture.final_url.startswith("https://www.eex.com/")
    # The query/fragment is absent and the approved host is reported, not invented.
    assert "gasandregistry.eex.com" not in capture.final_url


def test_redirect_without_a_location_is_refused() -> None:
    error = _error(lambda _request: httpx.Response(301))

    assert error.code == "redirect_refused"


def test_transient_5xx_is_retried_with_bounded_backoff_then_succeeds() -> None:
    calls: list[int] = []
    sleeps: list[float] = []

    def handler(_request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(503)
        return _ok_response(_csv_bytes())

    capture = fetch_eex_public_capture(
        transport=httpx.MockTransport(handler),
        clock=lambda: RETRIEVED_AT,
        sleep=sleeps.append,
    )

    assert len(calls) == 2
    assert sleeps == [1.0]
    assert capture.http_attempts == 2


def test_429_retry_after_is_capped_and_then_the_request_may_succeed() -> None:
    calls: list[int] = []
    sleeps: list[float] = []

    def handler(_request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(429, headers={"Retry-After": "9999"})
        return _ok_response(_csv_bytes())

    capture = fetch_eex_public_capture(
        transport=httpx.MockTransport(handler),
        clock=lambda: RETRIEVED_AT,
        sleep=sleeps.append,
    )

    assert len(calls) == 2
    assert sleeps == [5.0]
    assert capture.http_attempts == 2


def test_a_4xx_is_not_retried() -> None:
    calls: list[int] = []

    def handler(_request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(400)

    error = _error(handler)

    assert error.code == "upstream_client_error"
    assert error.status_code == 400
    assert len(calls) == 1


def test_timeouts_are_retried_only_within_the_bound_and_use_a_stable_code() -> None:
    calls: list[int] = []
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        raise httpx.ReadTimeout("synthetic timeout", request=request)

    error = _error(handler, sleeps=sleeps)

    assert error.code == "timeout"
    assert len(calls) == 3
    assert sleeps == [1.0, 2.0]


def test_malformed_csv_bytes_are_refused_by_the_existing_inspection_seam() -> None:
    body = b"Gasday,IndexValue\n29/05/2026,31.4\n"
    capture = fetch_eex_public_capture(
        transport=httpx.MockTransport(lambda _request: _ok_response(body)),
        clock=lambda: RETRIEVED_AT,
        sleep=lambda _seconds: pytest.fail("a malformed body is not retried"),
    )

    with pytest.raises(EexNgpCaptureError) as raised:
        inspect_eex_ngp_capture(capture.raw_bytes, retrieved_at_utc=capture.retrieved_at_utc)
    assert raised.value.code == "malformed_csv"


def test_cli_writes_exact_raw_bytes_and_no_rows_in_sanitized_metadata(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cli = _load_cli()
    body = _csv_bytes(newline="\r\n")
    output = tmp_path / "capture.csv"

    result = cli.main(
        ["--output", str(output)],
        transport=httpx.MockTransport(lambda _request: _ok_response(body)),
        clock=lambda: RETRIEVED_AT,
        sleep=lambda _seconds: pytest.fail("a successful CLI must not sleep"),
    )

    assert result == 0
    assert output.read_bytes() == body
    metadata_path = Path(f"{output}.metadata.json")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    printed = json.loads(capsys.readouterr().out)

    assert metadata == printed
    assert "rows" not in metadata
    assert "rejections" not in metadata
    assert "31.400" not in metadata_path.read_text(encoding="utf-8")
    assert "Final NGP" not in metadata_path.read_text(encoding="utf-8")
    assert metadata["raw_artifact"]["raw_sha256"] == hashlib.sha256(body).hexdigest()
    assert metadata["raw_artifact"]["raw_byte_length"] == len(body)
    assert metadata["raw_artifact"]["bom_present"] is True
    assert metadata["raw_artifact"]["line_endings"] == "preserved_in_raw_bytes"
    assert metadata["retrieved_at_utc"] == RETRIEVED_AT.isoformat()
    assert metadata["source_page_url"] == SOURCE_PAGE_URL
    assert metadata["source_file_url"] == SOURCE_FILE_URL
    assert metadata["inspection"]["row_count"] == 1
    assert metadata["canonicalization_allowed"] is False
    assert metadata["executable_quote"] is False
    assert metadata["source_activation"] is False
    assert metadata["download"]["content_type"] == "text/csv"
    assert metadata["download"]["http_attempts"] == 1


def test_cli_refuses_an_existing_output_before_any_network_request(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cli = _load_cli()
    output = tmp_path / "existing.csv"
    output.write_bytes(b"operator-owned")

    def handler(_request: httpx.Request) -> httpx.Response:
        pytest.fail("an invalid output path must not start a download")

    result = cli.main(
        ["--output", str(output)],
        transport=httpx.MockTransport(handler),
    )

    assert result == 2
    assert output.read_bytes() == b"operator-owned"
    error = json.loads(capsys.readouterr().out)["error"]
    assert error["code"] == "output_exists"


def test_cli_refuses_an_existing_output_symlink_without_following_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cli = _load_cli()
    target = tmp_path / "target.csv"
    target.write_bytes(b"keep-me")
    link = tmp_path / "link.csv"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("this platform does not permit synthetic symlink creation")

    def handler(_request: httpx.Request) -> httpx.Response:
        pytest.fail("a symlink output must not start a download")

    result = cli.main(
        ["--output", str(link)],
        transport=httpx.MockTransport(handler),
    )

    assert result == 2
    assert target.read_bytes() == b"keep-me"
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "output_symlink"


def test_cli_refuses_malformed_payload_and_writes_no_files(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cli = _load_cli()
    output = tmp_path / "capture.csv"
    body = b"Gasday,IndexValue\n29/05/2026,31.4\n"

    result = cli.main(
        ["--output", str(output)],
        transport=httpx.MockTransport(lambda _request: _ok_response(body)),
        clock=lambda: RETRIEVED_AT,
        sleep=lambda _seconds: pytest.fail("a malformed body is not retried"),
    )

    assert result == 1
    assert not output.exists()
    assert not Path(f"{output}.metadata.json").exists()
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "malformed_csv"


def test_cli_rejects_existing_metadata_sidecar_before_any_network_request(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cli = _load_cli()
    output = tmp_path / "capture.csv"
    metadata = Path(f"{output}.metadata.json")
    metadata.write_text("operator-owned", encoding="utf-8")

    def handler(_request: httpx.Request) -> httpx.Response:
        pytest.fail("an existing metadata path must not start a download")

    result = cli.main(
        ["--output", str(output)],
        transport=httpx.MockTransport(handler),
    )

    assert result == 2
    assert not output.exists()
    assert metadata.read_text(encoding="utf-8") == "operator-owned"
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "metadata_output_exists"


def test_transport_and_cli_import_no_database_or_session_authority() -> None:
    forbidden = {"sqlalchemy", "psycopg", "psycopg2", "alembic", "subprocess"}
    for path in (TRANSPORT_MODULE, CLI_MODULE):
        source = path.read_text(encoding="utf-8")
        imported: set[str] = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        assert imported.isdisjoint(forbidden)
        assert "eex_ttf_ngp_market_observations" not in source
