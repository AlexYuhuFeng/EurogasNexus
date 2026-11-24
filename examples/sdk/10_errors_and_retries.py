"""Handle errors and retry safe reads.

A refusal raises ``eurogas_nexus_sdk.NexusAPIError`` (an ``httpx.HTTPStatusError``) with the
server's stable ``code``, its ``message``, a ``recoverability`` hint and the
``correlation_id`` to quote to an administrator. The SDK does not retry.
"""

import os
import time

import httpx
from eurogas_nexus_sdk import NexusAPIError, SdkProtocolError
from eurogas_nexus_sdk.reference_network import fetch_market_hubs, fetch_node
from pydantic import ValidationError

BASE_URL = os.environ.get("EUROGAS_NEXUS_BASE_URL", "http://127.0.0.1:8000")


def describe(error: NexusAPIError) -> str:
    """One line with the HTTP status, stable code, recoverability and correlation id."""

    return (
        f"HTTP {error.status_code} {error.code or 'unknown'}"
        f" (recoverability {error.recoverability or 'unknown'},"
        f" correlation id {error.correlation_id or '-'})"
    )


def with_retries(call, *, attempts: int = 3, backoff_seconds: float = 0.5):
    """Retry a read on network errors and on 'retry'-class or 5xx answers.

    Use it for reads only. Never wrap a call that records something (a review decision, a
    strategy version): it could be recorded twice.
    """

    for attempt in range(1, attempts + 1):
        try:
            return call()
        except httpx.TransportError:
            if attempt == attempts:
                raise
        except NexusAPIError as error:
            retryable = error.recoverability == "retry" or error.status_code >= 500
            if attempt == attempts or not retryable:
                raise
        time.sleep(backoff_seconds * 2 ** (attempt - 1))
    raise AssertionError("unreachable")


# 1. A stable error code instead of a bare status line.
try:
    fetch_node(BASE_URL, "NO-SUCH-NODE")
except NexusAPIError as error:
    print(describe(error))

# 2. A read that succeeds goes through the retry wrapper unchanged.
hubs = with_retries(lambda: fetch_market_hubs(BASE_URL))
print(f"{len(hubs)} market hubs, for example {hubs[0].hub_code} ({hubs[0].country})")

# 3. A server that is not there: the wrapper retries, then re-raises the network error.
try:
    with_retries(lambda: fetch_node("http://127.0.0.1:9", "TTF"), attempts=2, backoff_seconds=0.1)
except httpx.TransportError as error:
    print(f"network error after retries: {type(error).__name__}")

# 4. The other two exception types the SDK lets through.
for name, exc in (("ValidationError", ValidationError), ("SdkProtocolError", SdkProtocolError)):
    print(f"{name} is a {exc.__mro__[1].__name__}")
