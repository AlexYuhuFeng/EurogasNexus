"""``GET /metrics``: the Prometheus text exposition for a scrape identity, closed by default.

Prometheus cannot sign in, and ``/api/runtime/metrics`` (kept for the Runtime page) wraps the
text in JSON behind a session, so nothing could scrape it. This endpoint answers the plain
text format, but only to a caller the deployment configured:

* ``EUROGAS_NEXUS_METRICS_SCRAPE_TOKEN`` (secret): the scraper sends
  ``Authorization: Bearer <token>`` (Prometheus ``authorization.credentials_file``);
* ``EUROGAS_NEXUS_METRICS_ALLOWED_NETWORKS``: comma-separated addresses or CIDR ranges the
  scraper connects from (the monitoring network). Behind a reverse proxy the address is the
  one uvicorn resolved from the trusted proxy's forwarding header (``FORWARDED_ALLOW_IPS``).

With neither set the endpoint does not exist (404), whatever the profile. With both set, a
scrape needs both. A wrong or missing token is 401, an address outside the ranges 403; the
refusal names no setting and echoes nothing.

It is served here, outside the route table, so the API's sign-in, permission and CSRF
dependencies (which a scraper cannot satisfy) do not apply and the endpoint is not part of
the public API surface. The database work runs off the event loop.
"""

from __future__ import annotations

import hmac
import ipaddress
import os
from collections.abc import Awaitable, Callable
from typing import Any

from anyio import to_thread

METRICS_PATH = "/metrics"
CONTENT_TYPE = b"text/plain; version=0.0.4; charset=utf-8"
TOKEN_ENV = "EUROGAS_NEXUS_METRICS_SCRAPE_TOKEN"
NETWORKS_ENV = "EUROGAS_NEXUS_METRICS_ALLOWED_NETWORKS"


def scrape_token() -> str | None:
    value = (os.environ.get(TOKEN_ENV) or "").strip()
    return value or None


def allowed_networks() -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    """The configured ranges; an unparsable entry is skipped (config check reports it)."""

    networks = []
    for item in (os.environ.get(NETWORKS_ENV) or "").split(","):
        item = item.strip()
        if not item:
            continue
        try:
            networks.append(ipaddress.ip_network(item, strict=False))
        except ValueError:
            continue
    return networks


def invalid_network_entries(value: str | None) -> list[str]:
    """Entries of the networks setting that are not an address or CIDR range."""

    bad = []
    for item in (value or "").split(","):
        item = item.strip()
        if not item:
            continue
        try:
            ipaddress.ip_network(item, strict=False)
        except ValueError:
            bad.append(item)
    return bad


def metrics_enabled() -> bool:
    return scrape_token() is not None or bool(allowed_networks())


def _bearer(scope: dict[str, Any]) -> str:
    for key, value in scope.get("headers", []):
        if key.lower() == b"authorization":
            text = value.decode("latin-1").strip()
            if text[:7].lower() == "bearer ":
                return text[7:].strip()
    return ""


def _client_in(scope: dict[str, Any], networks: list) -> bool:
    client = scope.get("client")
    host = client[0] if client else None
    if not host:
        return False
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return any(address in network for network in networks)


def authorise(scope: dict[str, Any]) -> int:
    """HTTP status for this scrape: 200, 401, 403, or 404 when the endpoint is off."""

    token = scrape_token()
    networks = allowed_networks()
    if token is None and not networks:
        return 404
    if networks and not _client_in(scope, networks):
        return 403
    if token is not None and not hmac.compare_digest(
        _bearer(scope).encode("utf-8"), token.encode("utf-8")
    ):
        return 401
    return 200


def render_exposition() -> str:
    """Process metrics plus, with a runtime database, the database metrics."""

    from eurogas_nexus.application import process_metrics
    from eurogas_nexus.db.session import resolve_database_url

    if resolve_database_url() is None:
        return process_metrics.render() + _database_up(0)
    try:
        from eurogas_nexus.application.dataops_observability import prometheus_metrics
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            body = prometheus_metrics(session)
        return body + _database_up(1)
    except Exception:  # noqa: BLE001 - the process metrics are still worth a scrape
        return process_metrics.render() + _database_up(0)


def _database_up(value: int) -> str:
    return (
        "# HELP eurogas_metrics_database_up 1 when the database metrics could be read.\n"
        "# TYPE eurogas_metrics_database_up gauge\n"
        f"eurogas_metrics_database_up {value}\n"
    )


class MetricsEndpointMiddleware:
    """Answer ``GET /metrics`` before the application's routing and authentication."""

    def __init__(self, app: Callable[..., Awaitable[None]]) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http" or scope.get("path") != METRICS_PATH:
            await self.app(scope, receive, send)
            return
        if scope.get("method") not in {"GET", "HEAD"}:
            await _respond(send, 405, b"method not allowed\n")
            return
        status = authorise(scope)
        if status != 200:
            await _respond(send, status, _REFUSALS[status])
            return
        body = (await to_thread.run_sync(render_exposition)).encode("utf-8")
        await _respond(
            send, 200, b"" if scope.get("method") == "HEAD" else body, CONTENT_TYPE
        )


_REFUSALS = {
    401: b"unauthorized\n",
    403: b"forbidden\n",
    404: b"not found\n",
}


async def _respond(
    send: Any, status: int, body: bytes, content_type: bytes = b"text/plain; charset=utf-8"
) -> None:
    headers = [
        (b"content-type", content_type),
        (b"content-length", str(len(body)).encode("ascii")),
        (b"cache-control", b"no-store"),
    ]
    if status == 401:
        headers.append((b"www-authenticate", b"Bearer"))
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})


__all__ = [
    "METRICS_PATH",
    "MetricsEndpointMiddleware",
    "allowed_networks",
    "authorise",
    "invalid_network_entries",
    "metrics_enabled",
    "render_exposition",
]
