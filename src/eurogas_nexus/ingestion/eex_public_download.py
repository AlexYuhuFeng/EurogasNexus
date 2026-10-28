"""Bounded download of the official EEX TTF NGP public CSV.

This is the first *real transport* for the public EEX TTF NGP file. It performs one fixed
``GET`` for the exact file linked by the official EEX gas-market-transparency page and returns
the exact response bytes, their SHA-256, and the receipt instant. It is deliberately not a
data feed, a scheduler, a canonical mapper or a source activator:

- only the fixed official URL is requested; callers cannot supply a URL, host, path or query;
- redirects are never followed automatically. Each hop is validated against the same small set
  of official EEX hosts, HTTPS only, with no userinfo and no non-443 port;
- no cookie jar, credentials, browser state or authenticated session is used, and environment
  proxy/netrc settings are ignored;
- responses are streamed and refused above the existing
  :data:`eurogas_nexus.ingestion.eex_ngp_capture.MAX_CAPTURE_BYTES` ceiling;
- only ``text/csv``, ``text/plain`` and ``application/octet-stream`` are accepted, and the
  payload is checked for an HTML/XML body as well as the media type;
- retries are bounded and limited to 429 and transient 5xx statuses. A numeric ``Retry-After``
  is capped. Timeouts and network errors are retried only within the same bound; 4xx responses
  and payload/contract refusals are never retried;
- transport errors use stable codes and never interpolate a response body, request URL or
  redirect target into the error text.

The returned bytes are not inspected for CSV rows here. The operator-facing CLI calls the
existing read-only :func:`eurogas_nexus.ingestion.eex_ngp_capture.inspect_eex_ngp_capture` seam
with its exact signature before writing anything. That seam owns the parser-derived report and
the canonicalization prohibition; this module does not duplicate the parser and does not grant
rights, freshness, executable-quote status or source activation.
"""

from __future__ import annotations

import hashlib
import math
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx

from eurogas_nexus.ingestion.eex_ngp import SOURCE_FILE_URL
from eurogas_nexus.ingestion.eex_ngp_capture import MAX_CAPTURE_BYTES

#: The fixed upstream file. It is imported from the parser module so there is one declaration of
#: the official URL rather than a second, potentially drifting copy.
OFFICIAL_SOURCE_URL = SOURCE_FILE_URL
OFFICIAL_HOST = "gasandregistry.eex.com"
OFFICIAL_PATH = "/Gas/NGP/TTF_NGP_15_Mins.csv"

#: Redirects may only land on these official EEX hosts, over HTTPS on the default port.
APPROVED_HOSTS = frozenset({"gasandregistry.eex.com", "www.eex.com"})

#: Application bounds, not claims about provider limits.
MAX_ATTEMPTS = 3
MAX_REDIRECTS = 5
MAX_TIMEOUT_SECONDS = 30.0
MAX_RETRY_AFTER_SECONDS = 5.0
BASE_RETRY_DELAY_SECONDS = 1.0

#: Media types the official file has plausibly been served as. The body still has to pass the
#: existing capture inspector; a matching MIME type alone is never treated as CSV proof.
ALLOWED_CONTENT_TYPES = frozenset({"text/csv", "text/plain", "application/octet-stream"})

_RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})
_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})

_REQUEST_HEADERS = {
    # Ask for the exact bytes; an encoded response would make the SHA-256 a digest of a decoded
    # representation rather than the payload as received.
    "Accept": "text/csv, text/plain;q=0.9, application/octet-stream;q=0.8",
    "Accept-Encoding": "identity",
    "User-Agent": "EurogasNexus/0.5 eex-public-capture",
}


class EexPublicDownloadError(RuntimeError):
    """A bounded download refusal with a stable code and no untrusted response text.

    Attributes:
        code: Stable machine-readable classification.
        status_code: The HTTP status when one was received, otherwise ``None``. The response
            body and URL are deliberately not retained in the error.
    """

    def __init__(
        self, code: str, message: str, *, status_code: int | None = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


@dataclass(frozen=True)
class EexPublicCapture:
    """Exact bytes returned by one bounded official download.

    ``raw_bytes`` is excluded from ``repr`` so an accidental log line does not dump market data.
    The hash is a digest of those exact bytes, including BOM and line endings.
    """

    raw_bytes: bytes = field(repr=False)
    source_url: str
    final_url: str
    retrieved_at_utc: datetime
    content_type: str
    content_encoding: str
    status_code: int
    http_attempts: int
    redirect_count: int

    @property
    def raw_sha256(self) -> str:
        return hashlib.sha256(self.raw_bytes).hexdigest()

    @property
    def raw_byte_length(self) -> int:
        return len(self.raw_bytes)

    @property
    def bom_present(self) -> bool:
        return self.raw_bytes.startswith(b"\xef\xbb\xbf")


def fetch_eex_public_capture(
    *,
    transport: httpx.BaseTransport | None = None,
    attempts: int = MAX_ATTEMPTS,
    timeout_seconds: float = 20.0,
    sleep: Callable[[float], None] | None = None,
    clock: Callable[[], datetime] | None = None,
) -> EexPublicCapture:
    """Download the fixed official EEX TTF NGP CSV under the bounded transport contract.

    Args:
        transport: Optional httpx transport, used by tests with ``httpx.MockTransport``. The
            production path uses httpx's default TLS transport.
        attempts: Maximum attempts for timeout/network/429/transient-5xx handling. Must be
            between 1 and :data:`MAX_ATTEMPTS`.
        timeout_seconds: Per-request timeout. Must be finite and at most
            :data:`MAX_TIMEOUT_SECONDS`.
        sleep: Optional bounded-sleep hook for deterministic tests. The real path uses
            :func:`time.sleep`.
        clock: Optional receipt clock for deterministic tests. It must return a timezone-aware
            instant and is read only after a complete bounded body has arrived.

    Returns:
        The exact bytes, their digest from :attr:`EexPublicCapture.raw_sha256`, and the receipt
        instant normalized to UTC.

    Raises:
        EexPublicDownloadError: For redirect, HTTP, timeout, size, encoding, media-type or
            HTML/XML refusals.
        ValueError: For invalid transport options (a programming error, not a network refusal).
    """

    if type(attempts) is not int or not 1 <= attempts <= MAX_ATTEMPTS:
        raise ValueError(f"attempts must be an integer between 1 and {MAX_ATTEMPTS}.")
    if (
        isinstance(timeout_seconds, bool)
        or not isinstance(timeout_seconds, (int, float))
        or not math.isfinite(timeout_seconds)
        or not 0 < timeout_seconds <= MAX_TIMEOUT_SECONDS
    ):
        raise ValueError(
            f"timeout_seconds must be finite and between 0 and {MAX_TIMEOUT_SECONDS}."
        )

    sleeper = sleep or time.sleep
    receipt_clock = clock or (lambda: datetime.now(UTC))

    with httpx.Client(
        transport=transport,
        follow_redirects=False,
        trust_env=False,
        timeout=timeout_seconds,
        auth=None,
        cookies=None,
        headers=_REQUEST_HEADERS,
    ) as client:
        return _download(
            client,
            attempts=attempts,
            timeout_seconds=timeout_seconds,
            sleep=sleeper,
            clock=receipt_clock,
        )


def _fixed_source_url() -> str:
    """Defensively pin the request to the exact official HTTPS host and path.

    The URL is a module constant, not a caller argument. This check makes an accidental future
    edit fail closed rather than turn the transport into a general URL fetcher.
    """

    try:
        parts = urlsplit(OFFICIAL_SOURCE_URL)
        port = parts.port
    except ValueError:
        raise EexPublicDownloadError(
            "source_url_not_approved", "the configured EEX source URL is not valid."
        ) from None
    if (
        parts.scheme.lower() != "https"
        or parts.hostname != OFFICIAL_HOST
        or parts.path != OFFICIAL_PATH
        or parts.query
        or parts.fragment
        or parts.username is not None
        or parts.password is not None
        or port not in (None, 443)
    ):
        raise EexPublicDownloadError(
            "source_url_not_approved",
            "the configured EEX source URL is not the fixed official HTTPS file.",
        )
    return OFFICIAL_SOURCE_URL


def _download(
    client: httpx.Client,
    *,
    attempts: int,
    timeout_seconds: float,
    sleep: Callable[[float], None],
    clock: Callable[[], datetime],
) -> EexPublicCapture:
    current_url = _fixed_source_url()
    redirect_count = 0
    attempt = 0
    http_attempts = 0

    while True:
        try:
            request = client.build_request("GET", current_url, timeout=timeout_seconds)
        except (httpx.InvalidURL, ValueError):
            raise EexPublicDownloadError(
                "redirect_refused" if redirect_count else "source_url_not_approved",
                "the EEX file request URL is not valid.",
            ) from None
        http_attempts += 1
        try:
            response = client.send(request, stream=True, follow_redirects=False)
        except httpx.TimeoutException:
            if attempt + 1 >= attempts:
                raise EexPublicDownloadError(
                    "timeout", "the official EEX file request timed out."
                ) from None
            sleep(_backoff(attempt))
            attempt += 1
            continue
        except httpx.HTTPError:
            if attempt + 1 >= attempts:
                raise EexPublicDownloadError(
                    "network_error", "the official EEX file request failed in transport."
                ) from None
            sleep(_backoff(attempt))
            attempt += 1
            continue

        try:
            status = response.status_code
            if status in _REDIRECT_STATUSES:
                redirect_count += 1
                if redirect_count > MAX_REDIRECTS:
                    raise EexPublicDownloadError(
                        "redirect_limit", "the official EEX file redirected too many times."
                    )
                location = response.headers.get("Location")
                current_url = _validate_redirect(current_url, location)
                # Redirects are bounded separately from retry attempts. The final target gets
                # its own small retry budget.
                attempt = 0
                continue

            if status in _RETRYABLE_STATUSES:
                if attempt + 1 >= attempts:
                    code = "rate_limited" if status == 429 else "upstream_server_error"
                    raise EexPublicDownloadError(
                        code,
                        "the official EEX file server did not return a usable response "
                        f"(HTTP {status}).",
                        status_code=status,
                    )
                delay = _retry_delay(response, attempt, status=status)
                response.close()
                sleep(delay)
                attempt += 1
                continue

            if status != 200:
                if 400 <= status < 500:
                    raise EexPublicDownloadError(
                        "upstream_client_error",
                        f"the official EEX file request was refused (HTTP {status}).",
                        status_code=status,
                    )
                if 500 <= status < 600:
                    raise EexPublicDownloadError(
                        "upstream_server_error",
                        f"the official EEX file server failed (HTTP {status}).",
                        status_code=status,
                    )
                raise EexPublicDownloadError(
                    "unexpected_status",
                    f"the official EEX file server returned an unexpected status (HTTP {status}).",
                    status_code=status,
                )

            content_type, content_encoding = _validate_success_headers(response)
            raw_bytes = _read_bounded(response)
            retrieved_at = _receipt_instant(clock)
            return EexPublicCapture(
                raw_bytes=raw_bytes,
                source_url=OFFICIAL_SOURCE_URL,
                final_url=str(response.url),
                retrieved_at_utc=retrieved_at,
                content_type=content_type,
                content_encoding=content_encoding,
                status_code=status,
                http_attempts=http_attempts,
                redirect_count=redirect_count,
            )
        finally:
            response.close()


def _validate_success_headers(response: httpx.Response) -> tuple[str, str]:
    raw_content_type = response.headers.get("Content-Type", "")
    media_type = raw_content_type.split(";", 1)[0].strip().lower()
    if media_type not in ALLOWED_CONTENT_TYPES:
        raise EexPublicDownloadError(
            "unexpected_content_type",
            "the official EEX file response does not declare an accepted CSV media type.",
        )

    raw_encoding = response.headers.get("Content-Encoding", "identity").strip().lower()
    if raw_encoding != "identity":
        raise EexPublicDownloadError(
            "unsupported_content_encoding",
            "the official EEX file response is encoded; exact byte preservation requires "
            "identity.",
        )
    return media_type, raw_encoding


def _read_bounded(response: httpx.Response) -> bytes:
    declared_length = response.headers.get("Content-Length")
    if declared_length is not None:
        try:
            length = int(declared_length)
        except ValueError:
            length = None
        if length is not None and length > MAX_CAPTURE_BYTES:
            raise EexPublicDownloadError(
                "payload_too_large",
                f"the official EEX file exceeds the {MAX_CAPTURE_BYTES}-byte capture ceiling.",
            )

    chunks: list[bytes] = []
    total = 0
    if getattr(response, "is_stream_consumed", False):
        # Test transports may hand back an already-buffered response. The production path is
        # always streamed; this branch still applies the same byte bound before returning.
        content = response.content
        total = len(content)
        if total > MAX_CAPTURE_BYTES:
            raise EexPublicDownloadError(
                "payload_too_large",
                f"the official EEX file exceeds the {MAX_CAPTURE_BYTES}-byte capture ceiling.",
            )
        chunks.append(content)
    else:
        try:
            for chunk in response.iter_raw():
                total += len(chunk)
                if total > MAX_CAPTURE_BYTES:
                    raise EexPublicDownloadError(
                        "payload_too_large",
                        f"the official EEX file exceeds the {MAX_CAPTURE_BYTES}-byte capture "
                        "ceiling.",
                    )
                chunks.append(chunk)
        except httpx.TimeoutException:
            raise EexPublicDownloadError(
                "timeout", "the official EEX file response timed out while being read."
            ) from None
        except httpx.HTTPError:
            raise EexPublicDownloadError(
                "network_error", "the official EEX file response failed while being read."
            ) from None

    raw_bytes = b"".join(chunks)
    if not raw_bytes:
        raise EexPublicDownloadError("empty_payload", "the official EEX file response is empty.")
    if _looks_like_html(raw_bytes):
        raise EexPublicDownloadError(
            "html_payload",
            "the official EEX file response begins with an HTML/XML document, not the CSV.",
        )
    return raw_bytes


def _looks_like_html(raw_bytes: bytes) -> bool:
    payload = raw_bytes
    if payload.startswith(b"\xef\xbb\xbf"):
        payload = payload[3:]
    return payload.lstrip().startswith(b"<")


def _receipt_instant(clock: Callable[[], datetime]) -> datetime:
    retrieved_at = clock()
    if (
        not isinstance(retrieved_at, datetime)
        or retrieved_at.tzinfo is None
        or retrieved_at.utcoffset() is None
    ):
        raise EexPublicDownloadError(
            "invalid_clock", "the capture receipt clock did not return an aware instant."
        )
    try:
        return retrieved_at.astimezone(UTC)
    except (OverflowError, OSError, ValueError):
        raise EexPublicDownloadError(
            "invalid_clock", "the capture receipt instant could not be normalized to UTC."
        ) from None


def _validate_redirect(current_url: str, location: str | None) -> str:
    if location is None or not location.strip():
        raise EexPublicDownloadError(
            "redirect_refused", "the official EEX file redirect did not declare a target."
        )
    candidate = location.strip()
    if any(ord(character) < 0x20 or ord(character) == 0x7F for character in candidate):
        raise EexPublicDownloadError(
            "redirect_refused", "the official EEX file redirect target is not a clean URL."
        )
    if "\\" in candidate:
        raise EexPublicDownloadError(
            "redirect_refused", "the official EEX file redirect target is not a clean URL."
        )

    try:
        target = urljoin(current_url, candidate)
        parts = urlsplit(target)
        port = parts.port
    except ValueError:
        raise EexPublicDownloadError(
            "redirect_refused", "the official EEX file redirect target is not a valid URL."
        ) from None

    if parts.scheme.lower() != "https":
        raise EexPublicDownloadError(
            "redirect_not_https", "the official EEX file redirect target is not HTTPS."
        )
    if parts.username is not None or parts.password is not None:
        raise EexPublicDownloadError(
            "redirect_userinfo",
            "the official EEX file redirect target contains credential userinfo.",
        )
    hostname = parts.hostname
    if hostname is None or hostname.lower() not in APPROVED_HOSTS:
        raise EexPublicDownloadError(
            "redirect_host_not_approved",
            "the official EEX file redirect target is not an approved EEX host.",
        )
    if port not in (None, 443):
        raise EexPublicDownloadError(
            "redirect_port_not_approved",
            "the official EEX file redirect target is not on the default HTTPS port.",
        )

    netloc = hostname.lower() if port is None else f"{hostname.lower()}:443"
    return urlunsplit(("https", netloc, parts.path or "/", parts.query, ""))


def _retry_delay(response: httpx.Response, attempt: int, *, status: int) -> float:
    if status == 429:
        retry_after = response.headers.get("Retry-After")
        if retry_after is not None:
            try:
                seconds = float(retry_after)
            except ValueError:
                seconds = None
            if seconds is not None and math.isfinite(seconds) and seconds >= 0:
                return min(seconds, MAX_RETRY_AFTER_SECONDS)
    return _backoff(attempt)


def _backoff(attempt: int) -> float:
    return min(BASE_RETRY_DELAY_SECONDS * (2**attempt), MAX_RETRY_AFTER_SECONDS)


__all__ = [
    "ALLOWED_CONTENT_TYPES",
    "APPROVED_HOSTS",
    "BASE_RETRY_DELAY_SECONDS",
    "EexPublicCapture",
    "EexPublicDownloadError",
    "MAX_ATTEMPTS",
    "MAX_REDIRECTS",
    "MAX_RETRY_AFTER_SECONDS",
    "MAX_TIMEOUT_SECONDS",
    "OFFICIAL_HOST",
    "OFFICIAL_PATH",
    "OFFICIAL_SOURCE_URL",
    "fetch_eex_public_capture",
]
