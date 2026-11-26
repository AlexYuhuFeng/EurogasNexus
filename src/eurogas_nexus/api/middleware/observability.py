"""HTTP observability middleware: latency histograms, the access record, open streams, spans.

Per request, after the response: one sample in ``eurogas_http_request_duration_seconds`` and
``eurogas_http_requests_total`` labelled by the matched route's group, method and status
class (:mod:`eurogas_nexus.application.process_metrics`, multi-process safe); one access log
record with the request id and principal id (:mod:`eurogas_nexus.core.structured_logging`);
and, when tracing is on, one server span (:mod:`eurogas_nexus.core.tracing`). A
server-sent-events response counts in ``eurogas_stream_connections`` while it is open.

Nothing here reads a header, the query string, the body or the client address.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from contextlib import nullcontext
from typing import Any

from eurogas_nexus.application import process_metrics
from eurogas_nexus.core import structured_logging, tracing


def route_template(scope: dict[str, Any]) -> str | None:
    """The matched route's template (``/api/sources/{source_id}``), if routing matched."""

    route = scope.get("route")
    return getattr(route, "path_format", None) or getattr(route, "path", None)


def _stream_topic(template: str | None) -> str:
    if template and template.startswith("/api/stream/"):
        return template.removeprefix("/api/stream/").split("/", 1)[0] or "stream"
    return "other"


def _quiet(path: str) -> bool:
    """Liveness and readiness probes run every few seconds; they are not access-logged."""

    return path.startswith("/api/health")


class HttpObservabilityMiddleware:
    """ASGI middleware recording safe request metrics, the access record and a span."""

    def __init__(self, app: Callable[..., Awaitable[None]]) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = time.perf_counter()
        status_holder = {"status": 500, "stream": False}
        method = str(scope.get("method", "GET"))

        async def send_with_status(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                status_holder["status"] = int(message["status"])
                content_type = next(
                    (
                        value
                        for key, value in message.get("headers", [])
                        if key.lower() == b"content-type"
                    ),
                    b"",
                )
                if content_type.startswith(b"text/event-stream"):
                    status_holder["stream"] = True
                    process_metrics.stream_opened(_stream_topic(route_template(scope)))
            await send(message)

        active_tracer = tracing.tracer()
        span_context = (
            active_tracer.start_as_current_span(f"HTTP {method}", kind=_server_kind())
            if active_tracer is not None
            else nullcontext(None)
        )
        with span_context as span:
            try:
                await self.app(scope, receive, send_with_status)
            finally:
                elapsed = time.perf_counter() - started
                template = route_template(scope)
                if status_holder["stream"]:
                    process_metrics.stream_closed(_stream_topic(template))
                process_metrics.observe_request(
                    template, method, status_holder["status"], elapsed
                )
                process_metrics.observe_pools()
                if span is not None:
                    _finish_span(span, scope, method, template, status_holder["status"])
                path = str(scope.get("path", ""))
                if path.startswith("/api/") and not _quiet(path):
                    structured_logging.log_access(
                        method=method,
                        route=template or "unmatched",
                        status=status_holder["status"],
                        duration_ms=elapsed * 1000.0,
                        stream=bool(status_holder["stream"]),
                    )


def _server_kind() -> Any:
    from opentelemetry.trace import SpanKind

    return SpanKind.SERVER


def _finish_span(
    span: Any, scope: dict[str, Any], method: str, template: str | None, status: int
) -> None:
    try:
        span.update_name(f"{method} {template or 'unmatched'}")
        span.set_attribute("http.request.method", method)
        span.set_attribute("http.route", template or "unmatched")
        span.set_attribute("http.response.status_code", status)
        request_id = (scope.get("state") or {}).get("request_id")
        if request_id:
            span.set_attribute("eurogas.request_id", str(request_id))
        if status >= 500:
            from opentelemetry.trace import Status, StatusCode

            span.set_status(Status(StatusCode.ERROR))
    except Exception:  # noqa: BLE001 - tracing never fails a request
        return


__all__ = ["HttpObservabilityMiddleware", "route_template"]
