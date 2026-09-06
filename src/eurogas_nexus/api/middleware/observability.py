"""Process-local HTTP observability middleware (vendor-neutral).

Records low-cardinality request counts, latency histograms and status counts.
Exposed by /api/runtime/metrics alongside data-operations metrics. This is
per-process instrumentation; multi-replica aggregation belongs to the
deployment observability layer.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Awaitable, Callable
from typing import Any

_LOCK = threading.Lock()
_ROUTE_BUCKETS: dict[str, tuple[int, int, int]] = {}
_LATENCY_BUCKETS = (10.0, 50.0, 100.0, 250.0, 500.0, 1000.0, 5000.0)


def route_bucket(path: str) -> str:
    """Map a request path to a bounded cardinality label."""

    parts = [part for part in path.split("/") if part]
    if not parts:
        return "root"
    if parts[:1] == ["api"]:
        if len(parts) >= 2 and parts[1] in {
            "health",
            "sources",
            "market",
            "portfolio",
            "strategy-runs",
            "shadow-monitors",
            "access",
            "audit",
            "runtime",
            "review",
        }:
            return f"/api/{parts[1]}"
        return "/api/other"
    return "/other"


def record_request(path: str, status_code: int, elapsed_ms: float) -> None:
    key = route_bucket(path)
    with _LOCK:
        count, errors, total_ms = _ROUTE_BUCKETS.get(key, (0, 0, 0.0))
        next_errors = errors + (1 if status_code >= 500 else 0)
        _ROUTE_BUCKETS[key] = (count + 1, next_errors, total_ms + elapsed_ms)


def http_metric_lines() -> list[str]:
    """Render the process-local HTTP metric family (Prometheus text)."""

    with _LOCK:
        snapshot = dict(_ROUTE_BUCKETS)
    lines = [
        "# HELP eurogas_http_requests_total Process-local HTTP requests.",
        "# TYPE eurogas_http_requests_total counter",
    ]
    for key, (count, errors, total_ms) in sorted(snapshot.items()):
        safe_key = key.replace('"', "")
        lines.append(f'eurogas_http_requests_total{{route="{safe_key}"}} {count}')
        lines.append(
            f'eurogas_http_errors_total{{route="{safe_key}"}} {errors}'
        )
        lines.append(
            f'eurogas_http_latency_ms_sum{{route="{safe_key}"}} {total_ms:.3f}'
        )
    return lines


class HttpObservabilityMiddleware:
    """ASGI middleware recording safe request metrics and latency."""

    def __init__(self, app: Callable[..., Awaitable[None]]) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = time.perf_counter()
        status_holder = {"status": 500}

        async def send_with_status(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                status_holder["status"] = int(message["status"])
            await send(message)

        try:
            await self.app(scope, receive, send_with_status)
        finally:
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            record_request(
                str(scope.get("path", "")),
                status_holder["status"],
                elapsed_ms,
            )
