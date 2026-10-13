"""GIE AGSI/ALSI transport and connector tests (development-only fixtures).

All provider I/O is served by ``httpx.MockTransport``: no test contacts a live
GIE endpoint and no test needs a credential. The fixtures mirror the response
envelope documented in GIE API documentation v013 and the error body observed in
the bounded read-only conformance probe (HTTP 200 +
``{"error": "access denied", "dataset": "storage ERROR"}``).

The negative regressions in this module are the reviewer corrections for the
credential boundary (foreign redirect, plaintext, wrong product host, port,
userinfo), untrusted provider text (the key must never appear in an exception or
a chained traceback) and pagination honesty (whole-page floor budgets, the
absolute page ceiling, envelope validation and overlapping natural keys).
"""

from __future__ import annotations

import time
import traceback
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from eurogas_nexus.ingestion import gie_transport as gt
from eurogas_nexus.ingestion.connectors.base import MockConnector
from eurogas_nexus.ingestion.connectors.gie import GieConnector

AGSI = gt.GieProduct.agsi()
ALSI = gt.GieProduct.alsi()
SECRET = "unit-test-secret-key-value"


def _agsi_record(day: str = "2026-10-09", *, code: str = "EU", gas: str = "650.25") -> dict:
    return {
        "name": "EU",
        "code": code,
        "url": "eu",
        "updatedAt": f"{day}T12:00:00",
        "gasDayStart": day,
        "gasDayEnd": "2026-10-10",
        "gasInStorage": gas,
        "workingGasVolume": "1100.50",
        "full": "59.1",
        "injection": "2.5",
        "withdrawal": "1.2",
        "status": "C",
    }


def _alsi_record(day: str = "2026-10-09") -> dict:
    return {
        "name": "EU LNG",
        "code": "EU",
        "url": "eu",
        "updatedAt": f"{day}T12:00:00",
        "gasDayStart": day,
        "gasDayEnd": "2026-10-10",
        "inventory": {"lng": "9.5", "gwh": "42.5"},
        "sendOut": "3.4",
        "dtmi": {"lng": "14.4", "gwh": "65.0"},
        "status": "C",
    }


def _page_records(page: int, count: int) -> list[dict]:
    prefix = "F" if page == 1 else "G"
    return [
        _agsi_record(code=f"{prefix}{page}-{index}") for index in range(1, count + 1)
    ]


def _envelope(
    records: list[dict],
    *,
    last_page: int = 1,
    dataset: str = "EU",
    total: int | None = None,
) -> dict:
    return {
        "data": records,
        "last_page": last_page,
        "total": len(records) if total is None else total,
        "dataset": dataset,
        "gas_day": "2026-10-09",
    }


def _client(handler, *, follow_redirects: bool = False) -> httpx.Client:
    return httpx.Client(
        transport=httpx.MockTransport(handler),
        headers={"User-Agent": "EurogasNexus-test"},
        follow_redirects=follow_redirects,
    )


def _json(payload: dict, status: int = 200, headers: dict | None = None) -> httpx.Response:
    return httpx.Response(status, json=payload, headers=headers or {})


def _formatted(exc: BaseException) -> str:
    return "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))


# ---------------------------------------------------------------------------
# Credential resolution
# ---------------------------------------------------------------------------


def test_env_key_wins_over_file_and_store(tmp_path: Path) -> None:
    key_file = tmp_path / "gie.txt"
    key_file.write_text("file-key\n", encoding="utf-8")

    resolved = gt.resolve_gie_api_key(
        {"GIE_API_KEY": "env-key", "GIE_API_KEY_FILE": str(key_file)},
        credential_lookup=lambda: "store-key",
    )

    assert resolved is not None
    assert resolved.source == "env"
    assert resolved.value == "env-key"


def test_file_key_used_when_env_missing(tmp_path: Path) -> None:
    key_file = tmp_path / "gie.txt"
    key_file.write_text("file-key\n", encoding="utf-8")

    resolved = gt.resolve_gie_api_key(
        {"GIE_API_KEY_FILE": str(key_file)},
        credential_lookup=lambda: "store-key",
    )

    assert resolved is not None
    assert resolved.source == "file"
    assert resolved.value == "file-key"


def test_store_used_when_env_and_file_missing() -> None:
    resolved = gt.resolve_gie_api_key({}, credential_lookup=lambda: "store-key")

    assert resolved is not None
    assert resolved.source == "credential_store"


def test_no_credential_anywhere_is_none() -> None:
    assert gt.resolve_gie_api_key({}) is None


def test_configured_but_unreadable_key_file_is_explicit(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist.txt"

    with pytest.raises(gt.GieCredentialFileError) as refusal:
        gt.resolve_gie_api_key(
            {"GIE_API_KEY_FILE": str(missing)},
            credential_lookup=lambda: "store-key",
        )

    assert refusal.value.code == "gie_key_file_unreadable"
    # The store is not silently used when the configured file is broken.
    assert "store-key" not in str(refusal.value)


def test_blank_key_file_is_explicit(tmp_path: Path) -> None:
    key_file = tmp_path / "blank.txt"
    key_file.write_text("   \n", encoding="utf-8")

    with pytest.raises(gt.GieCredentialFileError):
        gt.resolve_gie_api_key({"GIE_API_KEY_FILE": str(key_file)})


def test_key_file_with_invalid_utf8_is_redacted_and_unchained(tmp_path: Path) -> None:
    """A binary key file must not leak credential bytes through a decoder traceback."""

    key_file = tmp_path / "binary-key.bin"
    key_file.write_bytes(b"\xff\xfeSECRET-credential-bytes\x80\x81")

    with pytest.raises(gt.GieCredentialFileError) as refusal:
        gt.resolve_gie_api_key({"GIE_API_KEY_FILE": str(key_file)})

    formatted = _formatted(refusal.value)
    assert refusal.value.code == "gie_key_file_unreadable"
    assert "SECRET-credential-bytes" not in formatted
    assert "codec" not in formatted.lower()
    assert "can't decode" not in formatted
    # The decoder exception is suppressed, not chained into the traceback.
    assert refusal.value.__cause__ is None
    assert refusal.value.__suppress_context__ is True


def test_api_key_repr_and_redaction_never_expose_the_value() -> None:
    key = gt.GieApiKey(value=SECRET, source="env")

    assert SECRET not in repr(key)
    assert key.redacted() == "un***ue"
    assert SECRET not in key.redacted()


# ---------------------------------------------------------------------------
# Credential boundary: endpoint validation before send
# ---------------------------------------------------------------------------


def _never_called_handler(calls: list) -> object:
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover - must not run
        calls.append(str(request.url))
        return _json(_envelope([_agsi_record()]))

    return handler


@pytest.mark.parametrize(
    ("product", "endpoint"),
    [
        ("agsi", "http://agsi.gie.eu/api"),
        ("agsi", "https://agsi.gie.eu:8443/api"),
        ("agsi", "https://user:supersecret@agsi.gie.eu/api"),
        ("agsi", "https://agsi.gie.eu/data/EU"),
        ("agsi", "https://agsi.gie.eu/api?type=eu"),
        ("agsi", "https://alsi.gie.eu/api"),
        ("alsi", "https://agsi.gie.eu/api"),
        ("agsi", "https://rogue.example/api"),
    ],
)
def test_endpoint_is_refused_before_the_credential_is_sent(
    product: str, endpoint: str
) -> None:
    calls: list[str] = []
    rogue = (
        gt.GieProduct.agsi(endpoint)
        if product == "agsi"
        else gt.GieProduct.alsi(endpoint)
    )

    with _client(_never_called_handler(calls)) as client:
        with pytest.raises(gt.GieEndpointRefusedError) as refusal:
            gt.fetch_gie_page(client, product=rogue, api_key=SECRET, page=1, size=30)

    assert refusal.value.code == "gie_endpoint_refused"
    assert calls == []
    # The submitted URL is never echoed: it may itself embed a credential.
    assert endpoint not in _formatted(refusal.value)
    assert SECRET not in _formatted(refusal.value)


def test_product_hosts_are_the_official_endpoints() -> None:
    assert AGSI.host == "agsi.gie.eu"
    assert ALSI.host == "alsi.gie.eu"
    assert gt.GIE_ALLOWED_HOSTS == {"agsi.gie.eu", "alsi.gie.eu"}
    assert gt.GIE_PRODUCT_HOSTS == {"AGSI": "agsi.gie.eu", "ALSI": "alsi.gie.eu"}


def test_foreign_redirect_is_refused_and_never_receives_the_key() -> None:
    """Even a client that follows redirects must not forward x-key off-host."""

    seen: list[tuple[str, str | None]] = []
    foreign = "foreign.example"

    def handler(request: httpx.Request) -> httpx.Response:
        host = request.url.host
        seen.append((host, request.headers.get("x-key")))
        if host == "agsi.gie.eu":
            return httpx.Response(
                302, headers={"location": f"https://{foreign}/steal"}
            )
        return _json(_envelope([_agsi_record()]))

    with _client(handler, follow_redirects=True) as client:
        with pytest.raises(gt.GieRedirectRefusedError) as refusal:
            gt.fetch_gie_page(client, product=AGSI, api_key=SECRET, page=1, size=30)

    assert refusal.value.code == "gie_redirect_refused"
    assert seen == [("agsi.gie.eu", SECRET)]
    assert all(host != foreign for host, _ in seen)


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
def test_every_redirect_status_is_refused_explicitly(status: int) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, headers={"location": "https://foreign.example/x"})

    with _client(handler, follow_redirects=True) as client:
        with pytest.raises(gt.GieRedirectRefusedError):
            gt.fetch_gie_page(client, product=AGSI, api_key=SECRET, page=1, size=30)


# ---------------------------------------------------------------------------
# Provider envelope, authentication and failures
# ---------------------------------------------------------------------------


def test_missing_key_is_explicit_not_an_empty_payload() -> None:
    with _client(lambda request: _json(_envelope([_agsi_record()]))) as client:
        with pytest.raises(gt.GieCredentialMissingError):
            gt.fetch_gie_page(client, product=AGSI, api_key="", page=1, size=30)


def test_provider_200_access_denied_body_is_an_auth_failure() -> None:
    body = {
        "data": [],
        "last_page": 0,
        "total": 0,
        "dataset": "storage ERROR",
        "error": "access denied",
        "message": "Invalid or missing API key",
    }

    with _client(lambda request: _json(body)) as client:
        with pytest.raises(gt.GieAuthenticationError) as refusal:
            gt.fetch_gie_page(client, product=AGSI, api_key=SECRET, page=1, size=30)

    assert refusal.value.code == "gie_access_denied"
    assert SECRET not in str(refusal.value)
    assert "access-denied" in str(refusal.value)


def test_authentication_failure_body_echoing_the_key_is_fully_redacted() -> None:
    body = {
        "data": [],
        "last_page": 0,
        "total": 0,
        "dataset": f"storage ERROR {SECRET}",
        "error": f"access denied for key {SECRET}",
        "message": f"Invalid API key: {SECRET}",
    }

    with _client(lambda request: _json(body)) as client:
        with pytest.raises(gt.GieAuthenticationError) as refusal:
            gt.fetch_gie_page(client, product=AGSI, api_key=SECRET, page=1, size=30)

    formatted = _formatted(refusal.value)
    assert SECRET not in str(refusal.value)
    assert SECRET not in formatted
    assert refusal.value.__cause__ is None


def test_generic_provider_error_body_echoing_the_key_is_redacted() -> None:
    body = {
        "data": [],
        "last_page": 0,
        "total": 0,
        "dataset": f"EU {SECRET}",
        "error": f"bad query {SECRET}",
        "message": f"offending key {SECRET}",
    }

    with _client(lambda request: _json(body)) as client:
        with pytest.raises(gt.GieProviderError) as refusal:
            gt.fetch_gie_page(client, product=AGSI, api_key=SECRET, page=1, size=30)

    assert refusal.value.code == "gie_provider_error"
    assert SECRET not in _formatted(refusal.value)
    assert refusal.value.__cause__ is None


def test_dataset_label_echoing_the_key_is_not_interpolated() -> None:
    body = _envelope([_agsi_record()], dataset=SECRET, total=1)

    with _client(lambda request: _json(body)) as client:
        with pytest.raises(gt.GieProductMismatchError) as refusal:
            gt.fetch_gie_page(client, product=AGSI, api_key=SECRET, page=1, size=30)

    assert SECRET not in str(refusal.value)
    assert SECRET not in _formatted(refusal.value)


@pytest.mark.parametrize("status", [401, 403])
def test_http_401_and_403_are_auth_failures(status: int) -> None:
    with _client(lambda request: _json({"detail": "nope"}, status=status)) as client:
        with pytest.raises(gt.GieAuthenticationError):
            gt.fetch_gie_page(client, product=ALSI, api_key=SECRET, page=1, size=30)


def test_non_access_denied_provider_error_is_not_labelled_authentication() -> None:
    body = {"data": [], "last_page": 0, "total": 0, "dataset": "EU", "error": "bad query"}

    with _client(lambda request: _json(body)) as client:
        with pytest.raises(gt.GieProviderError) as refusal:
            gt.fetch_gie_page(client, product=AGSI, api_key=SECRET, page=1, size=30)

    assert refusal.value.code == "gie_provider_error"


def test_429_retries_then_succeeds_with_bounded_delay() -> None:
    sleeps: list[float] = []
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return _json({"error": "slow down"}, status=429, headers={"retry-after": "0"})
        return _json(_envelope([_agsi_record()]))

    with _client(handler) as client:
        page = gt.fetch_gie_page(
            client, product=AGSI, api_key=SECRET, page=1, size=30, sleeper=sleeps.append
        )

    assert calls["n"] == 2
    assert sleeps == [0.0]
    assert len(page.records) == 1


def test_persistent_429_is_rate_limited() -> None:
    sleeps: list[float] = []

    with _client(lambda request: _json({}, status=429)) as client:
        with pytest.raises(gt.GieRateLimitedError) as refusal:
            gt.fetch_gie_page(
                client,
                product=AGSI,
                api_key=SECRET,
                page=1,
                size=30,
                sleeper=sleeps.append,
                attempts=2,
            )

    assert refusal.value.code == "gie_rate_limited"
    assert len(sleeps) == 1


def test_persistent_5xx_is_an_explicit_http_error() -> None:
    sleeps: list[float] = []

    with _client(lambda request: _json({}, status=503)) as client:
        with pytest.raises(gt.GieHttpError) as refusal:
            gt.fetch_gie_page(
                client,
                product=AGSI,
                api_key=SECRET,
                page=1,
                size=30,
                sleeper=sleeps.append,
                attempts=2,
            )

    assert refusal.value.code == "gie_http_error"


def test_timeout_is_an_explicit_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out")

    with _client(handler) as client:
        with pytest.raises(gt.GieTimeoutError) as refusal:
            gt.fetch_gie_page(
                client, product=AGSI, api_key=SECRET, page=1, size=30, attempts=1
            )

    assert refusal.value.code == "gie_timeout"
    assert SECRET not in str(refusal.value)


def test_malformed_json_is_an_explicit_failure_without_a_chained_decoder() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=f"<html>{SECRET}</html>".encode())

    with _client(handler) as client:
        with pytest.raises(gt.GieMalformedResponseError) as refusal:
            gt.fetch_gie_page(client, product=AGSI, api_key=SECRET, page=1, size=30)

    assert refusal.value.__cause__ is None
    assert SECRET not in _formatted(refusal.value)


def test_missing_documented_keys_is_malformed() -> None:
    with _client(lambda request: _json({"dataset": "EU", "data": []})) as client:
        with pytest.raises(gt.GieMalformedResponseError) as refusal:
            gt.fetch_gie_page(client, product=AGSI, api_key=SECRET, page=1, size=30)

    assert "last_page" in str(refusal.value) and "total" in str(refusal.value)


def test_empty_provider_dataset_is_explicit() -> None:
    with _client(
        lambda request: _json(_envelope([], last_page=0, total=0))
    ) as client:
        with pytest.raises(gt.GieEmptyResponseError) as refusal:
            gt.fetch_gie_page(client, product=AGSI, api_key=SECRET, page=1, size=30)

    assert refusal.value.code == "gie_empty_response"


def test_unscoped_response_without_dataset_identity_is_refused() -> None:
    with _client(
        lambda request: _json(_envelope([], last_page=180, dataset="", total=0))
    ) as client:
        with pytest.raises(gt.GieEmptyResponseError):
            gt.fetch_gie_page(client, product=ALSI, api_key=SECRET, page=1, size=30)


def test_empty_page_before_advertised_end_is_truncation() -> None:
    with _client(
        lambda request: _json(_envelope([], last_page=3, total=0))
    ) as client:
        with pytest.raises(gt.GieTruncationError) as refusal:
            gt.fetch_gie_page(client, product=AGSI, api_key=SECRET, page=2, size=30)

    assert refusal.value.code == "gie_truncated_response"


def test_cross_product_response_is_refused() -> None:
    with _client(lambda request: _json(_envelope([_alsi_record()]))) as client:
        with pytest.raises(gt.GieProductMismatchError):
            gt.fetch_gie_page(client, product=AGSI, api_key=SECRET, page=1, size=30)


def test_wrong_dataset_scope_is_refused() -> None:
    with _client(
        lambda request: _json(_envelope([_agsi_record()], dataset="DE"))
    ) as client:
        with pytest.raises(gt.GieProductMismatchError):
            gt.fetch_gie_page(client, product=AGSI, api_key=SECRET, page=1, size=30)


def test_size_above_provider_maximum_is_rejected() -> None:
    with _client(lambda request: _json(_envelope([_agsi_record()]))) as client:
        with pytest.raises(ValueError):
            gt.fetch_gie_page(client, product=AGSI, api_key=SECRET, page=1, size=301)


def test_credential_is_sent_only_in_the_x_key_header() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = dict(request.headers)
        captured["url"] = str(request.url)
        return _json(_envelope([_agsi_record()]))

    with _client(handler) as client:
        gt.fetch_gie_page(client, product=AGSI, api_key=SECRET, page=1, size=30)

    assert captured["headers"]["x-key"] == SECRET
    assert SECRET not in captured["url"]
    assert "page=1" in captured["url"] and "type=eu" in captured["url"]


def test_credential_is_never_sent_to_a_non_official_host() -> None:
    called = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover - must not run
        called["n"] += 1
        return _json(_envelope([_agsi_record()]))

    rogue = gt.GieProduct.agsi("https://rogue.example/api")
    with _client(handler) as client:
        with pytest.raises(gt.GieEndpointRefusedError):
            gt.fetch_gie_page(client, product=rogue, api_key=SECRET, page=1, size=30)

    assert called["n"] == 0


# ---------------------------------------------------------------------------
# Pagination, budget honesty and envelope validation
# ---------------------------------------------------------------------------


def test_page_receipt_is_captured_at_response_time() -> None:
    before = datetime.now(UTC)

    with _client(lambda request: _json(_envelope([_agsi_record()]))) as client:
        page = gt.fetch_gie_page(client, product=AGSI, api_key=SECRET, page=1, size=30)

    after = datetime.now(UTC)
    assert before <= page.received_at_utc <= after


def test_complete_pagination_stops_at_provider_last_page() -> None:
    requested: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        page_number = int(dict(request.url.params)["page"])
        requested.append(page_number)
        day = f"2026-10-{8 + page_number:02d}"
        return _json(_envelope([_agsi_record(day)], last_page=2))

    with _client(handler) as client:
        result = gt.fetch_gie_product(
            client, product=AGSI, api_key=SECRET, max_records=600
        )

    assert requested == [1, 2]
    assert result.complete is True
    assert result.stop_reason == "provider_last_page"
    assert result.partial_reason is None
    assert result.provider_last_page == 2
    assert result.page_size == 300
    assert result.pages_allowed == 2
    assert result.record_capacity == 600
    assert result.budget_records == 600
    assert len(result.pages) == 2
    assert len(result.records) == 2
    assert result.source_reference == "gie-agsi-api:pages=2/2;complete=true"


def test_record_budget_301_fetches_one_page_not_600_records() -> None:
    """The reviewer defect: max_records=301 used to fetch 600 records."""

    requested: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        page_number = int(dict(request.url.params)["page"])
        requested.append(page_number)
        return _json(
            _envelope(_page_records(page_number, 300), last_page=5)
        )

    with _client(handler) as client:
        result = gt.fetch_gie_product(
            client, product=AGSI, api_key=SECRET, max_records=301
        )

    assert requested == [1]
    assert len(result.records) == 300 <= result.budget_records
    assert result.complete is False
    assert result.stop_reason == "operator_record_budget"
    assert result.partial_reason == "record_budget_whole_page_floor"
    assert result.budget_records == 301
    assert result.record_capacity == 300
    assert result.page_size == 300


def test_record_budget_600_fetches_two_pages_of_300() -> None:
    requested: list[int] = []
    sizes: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        requested.append(int(params["page"]))
        sizes.append(int(params["size"]))
        return _json(_envelope(_page_records(int(params["page"]), 300), last_page=5))

    with _client(handler) as client:
        result = gt.fetch_gie_product(
            client, product=AGSI, api_key=SECRET, max_records=600
        )

    assert requested == [1, 2]
    assert sizes == [300, 300]
    assert len(result.records) == 600
    assert result.record_capacity == 600
    assert result.stop_reason == "operator_record_budget"
    assert result.complete is False


def test_explicit_page_size_plus_max_pages_does_not_collapse() -> None:
    requested: list[int] = []
    sizes: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        requested.append(int(params["page"]))
        sizes.append(int(params["size"]))
        return _json(_envelope(_page_records(int(params["page"]), 30), last_page=2))

    with _client(handler) as client:
        result = gt.fetch_gie_product(
            client, product=AGSI, api_key=SECRET, page_size=30, max_pages=2
        )

    # Desired 30x2 must not collapse into 60x1.
    assert requested == [1, 2]
    assert sizes == [30, 30]
    assert result.page_size == 30
    assert result.complete is True


def test_page_count_cap_reports_operator_page_budget() -> None:
    requested: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        page_number = int(dict(request.url.params)["page"])
        requested.append(page_number)
        return _json(_envelope(_page_records(page_number, 1), last_page=100))

    with _client(handler) as client:
        result = gt.fetch_gie_product(
            client, product=AGSI, api_key=SECRET, max_records=100000, max_pages=2
        )

    assert requested == [1, 2]
    assert result.pages_allowed == 2
    assert result.stop_reason == "operator_page_budget"
    assert result.partial_reason == "page_budget_exhausted"
    assert result.complete is False


def test_hard_page_ceiling_cannot_be_raised_by_the_caller() -> None:
    requested: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        page_number = int(dict(request.url.params)["page"])
        requested.append(page_number)
        return _json(_envelope(_page_records(page_number, 1), last_page=1000))

    with _client(handler) as client:
        result = gt.fetch_gie_product(
            client,
            product=AGSI,
            api_key=SECRET,
            max_records=10**9,
            max_pages=10_000,
        )

    assert len(requested) == gt.GIE_HARD_MAX_PAGES == 50
    assert result.pages_allowed == gt.GIE_HARD_MAX_PAGES
    assert result.complete is False
    assert result.stop_reason == "operator_page_budget"


def test_page_size_larger_than_record_budget_is_refused() -> None:
    with _client(lambda request: _json(_envelope([_agsi_record()]))) as client:
        with pytest.raises(ValueError, match="page_size must not exceed max_records"):
            gt.fetch_gie_product(
                client, product=AGSI, api_key=SECRET, max_records=100, page_size=300
            )


def test_operator_budget_yields_an_honest_bounded_partial_result() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _json(_envelope([_agsi_record()], last_page=10))

    with _client(handler) as client:
        result = gt.fetch_gie_product(
            client, product=AGSI, api_key=SECRET, max_records=30
        )

    assert result.complete is False
    assert result.stop_reason == "operator_record_budget"
    assert result.provider_last_page == 10
    assert len(result.pages) == 1
    assert result.budget_records == 30
    assert result.record_capacity == 30


def test_repeated_page_payload_is_refused() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _json(_envelope([_agsi_record()], last_page=5))

    with _client(handler) as client:
        with pytest.raises(gt.GiePaginationError) as refusal:
            gt.fetch_gie_product(client, product=AGSI, api_key=SECRET, max_records=900)

    assert refusal.value.code == "gie_pagination_error"


def test_overlapping_natural_keys_across_pages_are_refused() -> None:
    """Overlap, not only an identical page signature, must abort the fetch."""

    def handler(request: httpx.Request) -> httpx.Response:
        page_number = int(dict(request.url.params)["page"])
        if page_number == 1:
            return _json(_envelope([_agsi_record(code="EU")], last_page=2))
        return _json(
            _envelope(
                [_agsi_record(code="EU"), _agsi_record(day="2026-10-08", code="DE")],
                last_page=2,
            )
        )

    with _client(handler) as client:
        with pytest.raises(gt.GiePaginationError):
            gt.fetch_gie_product(client, product=AGSI, api_key=SECRET, max_records=900)


def test_duplicate_natural_key_within_a_page_is_refused() -> None:
    duplicate = [_agsi_record(code="EU"), _agsi_record(code="EU", gas="700.0")]

    with _client(lambda request: _json(_envelope(duplicate, last_page=3))) as client:
        with pytest.raises(gt.GiePaginationError):
            gt.fetch_gie_product(client, product=AGSI, api_key=SECRET, max_records=900)


def test_changed_last_page_between_pages_is_refused() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        page_number = int(dict(request.url.params)["page"])
        day = f"2026-10-{8 + page_number:02d}"
        last_page = 2 if page_number == 1 else 3
        return _json(_envelope([_agsi_record(day)], last_page=last_page))

    with _client(handler) as client:
        with pytest.raises(gt.GiePaginationError):
            gt.fetch_gie_product(client, product=AGSI, api_key=SECRET, max_records=900)


def test_total_must_equal_len_data() -> None:
    with _client(
        lambda request: _json(_envelope([_agsi_record()], total=99))
    ) as client:
        with pytest.raises(gt.GieMalformedResponseError, match="total"):
            gt.fetch_gie_page(client, product=AGSI, api_key=SECRET, page=1, size=30)


def test_negative_total_is_malformed() -> None:
    with _client(
        lambda request: _json(_envelope([], last_page=0, total=-1))
    ) as client:
        with pytest.raises(gt.GieMalformedResponseError):
            gt.fetch_gie_page(client, product=AGSI, api_key=SECRET, page=1, size=30)


def test_nonempty_data_with_last_page_zero_is_malformed() -> None:
    with _client(
        lambda request: _json(_envelope([_agsi_record()], last_page=0))
    ) as client:
        with pytest.raises(gt.GieMalformedResponseError, match="last_page"):
            gt.fetch_gie_page(client, product=AGSI, api_key=SECRET, page=1, size=30)


def test_requested_page_beyond_last_page_is_refused() -> None:
    with _client(
        lambda request: _json(_envelope([_agsi_record()], last_page=2))
    ) as client:
        with pytest.raises(gt.GiePaginationError, match="beyond the advertised"):
            gt.fetch_gie_page(client, product=AGSI, api_key=SECRET, page=5, size=30)


def test_oversized_page_is_refused() -> None:
    records = [_agsi_record(code=f"F{index}") for index in range(6)]

    with _client(lambda request: _json(_envelope(records, last_page=3))) as client:
        with pytest.raises(gt.GieMalformedResponseError, match="over-sized"):
            gt.fetch_gie_page(client, product=AGSI, api_key=SECRET, page=1, size=5)


# ---------------------------------------------------------------------------
# Connector contract and the no-mock-fallback guard
# ---------------------------------------------------------------------------


def test_gie_connector_is_not_a_mock_connector() -> None:
    assert not issubclass(GieConnector, MockConnector)
    connector = GieConnector()
    assert connector.metadata.source_system == "GIE"
    assert "agsi-storage" in connector.metadata.datasets


def test_gie_connector_without_credential_raises_instead_of_empty_payload() -> None:
    connector = GieConnector(environ={})

    with pytest.raises(gt.GieCredentialMissingError):
        connector.fetch("agsi-storage")


def test_gie_connector_fetches_real_records_through_the_transport() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _json(_envelope([_agsi_record()], last_page=1))

    with _client(handler) as client:
        connector = GieConnector(environ={"GIE_API_KEY": SECRET}, client=client)
        payload = connector.fetch("agsi-storage")

    assert payload.source_system == "GIE"
    assert payload.dataset == "agsi-storage"
    assert len(payload.raw_data) == 1
    assert payload.retrieval_ts_utc
    assert payload.source_reference_id == "gie-agsi-api:pages=1/1;complete=true"


def test_gie_connector_page_size_and_max_pages_are_independent() -> None:
    requested: list[int] = []
    sizes: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        requested.append(int(params["page"]))
        sizes.append(int(params["size"]))
        return _json(_envelope(_page_records(int(params["page"]), 30), last_page=2))

    with _client(handler) as client:
        connector = GieConnector(
            environ={"GIE_API_KEY": SECRET},
            client=client,
            page_size=30,
            max_pages=2,
        )
        payload = connector.fetch("agsi-storage")

    assert requested == [1, 2]
    assert sizes == [30, 30]
    assert len(payload.raw_data) == 60
    assert payload.source_reference_id == "gie-agsi-api:pages=2/2;complete=true"


def test_gie_connector_multi_page_payload_uses_the_last_response_receipt() -> None:
    page_two_started: dict[str, datetime] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        page_number = int(dict(request.url.params)["page"])
        if page_number == 2:
            page_two_started["t"] = datetime.now(UTC)
            time.sleep(0.05)
        return _json(_envelope([_agsi_record(code=f"F{page_number}")], last_page=2))

    with _client(handler) as client:
        connector = GieConnector(
            environ={"GIE_API_KEY": SECRET},
            client=client,
            page_size=10,
            max_pages=2,
        )
        payload = connector.fetch("agsi-storage")

    retrieved = datetime.fromisoformat(payload.retrieval_ts_utc)
    assert retrieved >= page_two_started["t"]
    assert datetime.fromisoformat(payload.retrieval_ts_utc).tzinfo is not None


def test_gie_connector_bounded_partial_reference_is_honest() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _json(_envelope([_agsi_record()], last_page=10))

    with _client(handler) as client:
        connector = GieConnector(
            environ={"GIE_API_KEY": SECRET},
            client=client,
            page_size=30,
            max_pages=1,
        )
        payload = connector.fetch("agsi-storage")

    assert "pages=1/10" in payload.source_reference_id
    assert "complete=false" in payload.source_reference_id
    assert "stop=operator_page_budget" in payload.source_reference_id


def test_gie_connector_clamps_max_pages_to_the_hard_ceiling() -> None:
    connector = GieConnector(
        environ={"GIE_API_KEY": SECRET}, page_size=30, max_pages=10_000
    )

    assert connector._max_pages == gt.GIE_HARD_MAX_PAGES


def test_gie_connector_rejects_an_unknown_dataset() -> None:
    with pytest.raises(ValueError):
        GieConnector(environ={"GIE_API_KEY": SECRET}).fetch("not-a-gie-dataset")


def test_gie_config_contract_declares_the_secret_file_path() -> None:
    from eurogas_nexus.core.config_contract import CONFIG_VARS_BY_NAME

    declared = CONFIG_VARS_BY_NAME["GIE_API_KEY_FILE"]
    assert declared.sensitivity == "internal"
    assert "GIE_API_KEY" in " ".join(declared.notes)

    root = Path(__file__).resolve().parents[2]
    template = (root / ".env.example").read_text(encoding="utf-8")
    assert "GIE_API_KEY_FILE=" in template


# ---------------------------------------------------------------------------
# Bounded one-page connection test (REAL-SOURCES-02)
#
# The connection test is transport + envelope/normalization shape only. These
# tests pin that each product is probed independently, that an HTTP 200
# access-denied body is a failure, and that no provider payload or credential
# ever reaches the returned check.
# ---------------------------------------------------------------------------


def _product_handler(responses: dict[str, object]):
    """Return a MockTransport handler that answers per request host."""

    def handler(request: httpx.Request) -> httpx.Response:
        host = request.url.host or ""
        answer = responses.get(host)
        if answer is None:
            return httpx.Response(404, json={})
        if isinstance(answer, httpx.Response):
            return answer
        if callable(answer):
            return answer(request)
        return _json(answer)  # type: ignore[arg-type]

    return handler


def test_connection_test_probes_both_products_independently() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "agsi.gie.eu":
            return _json(_envelope([_agsi_record()], last_page=192))
        return _json(_envelope([_alsi_record()], last_page=180))

    checks = gt.test_gie_connection(_client(handler), api_key=SECRET)

    assert [check.product for check in checks] == ["AGSI", "ALSI"]
    assert all(check.ok for check in checks)
    assert all(check.http_status == 200 for check in checks)
    assert [check.record_count for check in checks] == [1, 1]
    assert [check.normalized_rows for check in checks] == [1, 1]
    assert [check.provider_last_page for check in checks] == [192, 180]
    # One bounded page is an honest partial, not full history or certification.
    assert all(check.bounded_partial for check in checks)
    assert all(check.complete is False for check in checks)
    assert all(check.error_code is None for check in checks)


def test_connection_test_one_product_failure_does_not_hide_the_other() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "agsi.gie.eu":
            return _json({"error": "access denied", "dataset": "storage ERROR"})
        return _json(_envelope([_alsi_record()], last_page=180))

    checks = gt.test_gie_connection(_client(handler), api_key=SECRET)

    agsi, alsi = checks
    assert agsi.ok is False
    assert agsi.error_code == "gie_access_denied"
    assert agsi.http_status == 200  # a 200 access-denied body is still a failure
    assert alsi.ok is True
    assert alsi.record_count == 1


def test_connection_test_malformed_page_is_a_stable_failure_code() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "agsi.gie.eu":
            return _json(_envelope([_agsi_record()], total=99))
        return _json(_envelope([_alsi_record()], last_page=180))

    checks = gt.test_gie_connection(_client(handler), api_key=SECRET)

    assert checks[0].ok is False
    assert checks[0].error_code == "gie_malformed_response"
    assert checks[1].ok is True


def test_connection_test_blank_key_is_refused_before_any_request() -> None:
    sent: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(str(request.url))
        return _json(_envelope([_agsi_record()]))

    checks = gt.test_gie_connection(_client(handler), api_key="   ")

    assert sent == []
    assert all(check.ok is False for check in checks)
    assert all(check.error_code == "gie_credential_missing" for check in checks)


def test_connection_test_result_carries_no_credential_or_payload_text() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _json(_envelope([_agsi_record(), _alsi_record()]))

    checks = gt.test_gie_connection(_client(handler), api_key=SECRET)

    rendered = repr(checks)
    assert SECRET not in rendered
    assert "gasInStorage" not in rendered
    assert "inventory" not in rendered
    assert "raw_payload" not in rendered


def test_connection_test_normalization_refuses_to_claim_rows_it_did_not_build() -> None:
    """A record whose documented fields normalize to zero rows is a shape failure.

    Reporting the fetch as ``ok=True`` while the normalizer built nothing would
    present "the envelope parsed" as "the product's records are usable". The
    bounded check is a connectivity **and** shape test, so the page fails with an
    explicit stable code while retaining its HTTP status and record count.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        # Missing gasDayStart (and code): the real normalizer builds no canonical row.
        record = _agsi_record()
        record.pop("gasDayStart")
        record.pop("code", None)
        return _json(_envelope([record]))

    checks = gt.test_gie_connection(_client(handler), api_key=SECRET, products=(AGSI,))

    assert checks[0].ok is False
    assert checks[0].error_code == "gie_normalization_incomplete"
    assert checks[0].http_status == 200
    assert checks[0].record_count == 1
    assert checks[0].normalized_rows == 0


def test_connection_test_partial_skipped_rows_are_a_shape_failure() -> None:
    """One skipped record out of two makes the whole page a partial shape failure."""

    good = _agsi_record(code="EU")
    skipped = _agsi_record(code="SKIP")
    skipped.pop("gasDayStart")

    def handler(request: httpx.Request) -> httpx.Response:
        return _json(_envelope([good, skipped]))

    checks = gt.test_gie_connection(_client(handler), api_key=SECRET, products=(AGSI,))

    assert checks[0].ok is False
    assert checks[0].error_code == "gie_normalization_incomplete"
    assert checks[0].record_count == 2
    assert checks[0].normalized_rows == 1
    assert checks[0].http_status == 200


def test_connection_test_malformed_quantitative_shape_fails_the_shape_check() -> None:
    """A row whose primary quantity does not parse is not a usable observation."""

    def handler(request: httpx.Request) -> httpx.Response:
        return _json(_envelope([_agsi_record(gas="not-a-number")]))

    checks = gt.test_gie_connection(_client(handler), api_key=SECRET, products=(AGSI,))

    assert checks[0].ok is False
    assert checks[0].error_code == "gie_malformed_quantitative"
    # The row still normalized; the quantitative column is what failed.
    assert checks[0].normalized_rows == 1
    assert checks[0].record_count == 1


def test_connection_test_shape_failure_does_not_hide_the_other_product() -> None:
    """A shape failure on AGSI leaves the independently probed ALSI result intact."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "agsi.gie.eu":
            return _json(_envelope([_agsi_record(gas="bogus")]))
        return _json(_envelope([_alsi_record()], last_page=180))

    checks = gt.test_gie_connection(_client(handler), api_key=SECRET)

    agsi, alsi = checks
    assert agsi.ok is False
    assert agsi.error_code == "gie_malformed_quantitative"
    assert alsi.ok is True
    assert alsi.normalized_rows == 1


def test_connection_test_normalizes_with_the_page_receipt_not_a_fresh_now(
    monkeypatch,
) -> None:
    """The normalizer's fallback instant is the fetched page's own receipt."""

    receipt = datetime(2026, 10, 10, 8, 30, tzinfo=UTC)
    invented = datetime(2026, 10, 10, 23, 59, tzinfo=UTC)
    captured: list[datetime] = []

    class _Clock:
        def __init__(self) -> None:
            self.moments = [receipt, invented]

        def now(self, tz=None):  # noqa: ANN001, ANN202 - test double for module datetime
            return self.moments.pop(0)

    def fake_normalizer(payload, *, observed_at_utc):
        captured.append(observed_at_utc)
        return [
            {
                "observation_id": "gie-agsi-EU-2026-10-09",
                "inventory_twh": 650.25,
                "working_capacity_twh": 1100.5,
            }
        ]

    monkeypatch.setattr(gt, "datetime", _Clock())
    monkeypatch.setattr(
        "eurogas_nexus.ingestion.public_sources.gie_storage_observations_from_json",
        fake_normalizer,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return _json(_envelope([_agsi_record()]))

    checks = gt.test_gie_connection(_client(handler), api_key=SECRET, products=(AGSI,))

    assert checks[0].ok is True
    # The page receipt (first clock read) is the normalization basis; the fresh
    # "now" that a second read would invent is never used.
    assert captured == [receipt]

