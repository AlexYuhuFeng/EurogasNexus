"""Structured JSON logs with the request id and the principal id.

One line per record on standard output, so the container runtime collects and rotates it
(the runtime compose file caps each container's log files). Every record written while a
request is served carries ``request_id`` (also the ``X-Request-Id`` response header) and,
once the caller is known, ``principal_id``. Nothing else about the caller is logged: no
client address, no user agent, no header, no query string, no body.

Format, by ``EUROGAS_NEXUS_LOG_FORMAT``: ``json`` (default in the trial and release
environments) or ``text`` (default elsewhere, readable in a developer's terminal).
``EUROGAS_NEXUS_LOG_LEVEL`` sets the level (default ``INFO``).

The message and every extra field pass through the same redaction as the data-operations
events (:func:`eurogas_nexus.application.dataops_observability.redact` key rules) and a
value-level scrub of credentials embedded in URLs or ``Bearer`` headers.
"""

from __future__ import annotations

import contextvars
import json
import logging
import os
import re
import sys
from datetime import UTC, datetime
from typing import Any

_REQUEST: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar(
    "eurogas_request_log_context", default=None
)

#: Record attributes the logging module sets itself; anything else is an ``extra`` field.
_STANDARD_ATTRS = frozenset(
    vars(logging.LogRecord("x", logging.INFO, "x", 0, "x", None, None)).keys()
) | {"message", "asctime", "taskName"}

_SENSITIVE_KEY_MARKERS = ("password", "secret", "token", "credential", "authorization", "cookie")
_URL_CREDENTIALS = re.compile(r"(?P<scheme>[a-zA-Z][a-zA-Z0-9+.-]*://)[^/\s:@]+:[^/\s@]+@")
_BEARER = re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=-]{8,}")

_CONFIGURED = False
_HANDLER_NAME = "eurogas-nexus-structured"


def bind_request(request_id: str, state: dict[str, Any] | None) -> contextvars.Token:
    """Bind a request's id and its (mutable) ASGI state to the current context.

    The state dict is held by reference: the identity dependency stores the resolved caller
    in it later, from a worker thread, and every record after that carries its id.
    """

    return _REQUEST.set({"request_id": request_id, "state": state})


def unbind_request(token: contextvars.Token) -> None:
    try:
        _REQUEST.reset(token)
    except ValueError:  # reset from another context: clear instead
        _REQUEST.set(None)


def current_request_id() -> str | None:
    bound = _REQUEST.get()
    return bound.get("request_id") if bound else None


def current_principal_id() -> str | None:
    bound = _REQUEST.get()
    if not bound:
        return None
    state = bound.get("state") or {}
    identity = state.get("identity") if isinstance(state, dict) else None
    principal_id = getattr(identity, "principal_id", None)
    return str(principal_id) if principal_id else None


def scrub(value: str) -> str:
    """Remove credentials embedded in URLs and authorization headers from free text."""

    value = _URL_CREDENTIALS.sub(r"\g<scheme>[REDACTED]@", value)
    return _BEARER.sub(r"\1 [REDACTED]", value)


def _safe_field(key: str, value: Any) -> Any:
    lowered = key.lower()
    if any(marker in lowered for marker in _SENSITIVE_KEY_MARKERS) or lowered in {
        "database_url",
        "db_url",
        "api_key",
        "apikey",
        "body",
        "payload",
    }:
        return "[REDACTED]"
    if isinstance(value, str):
        return scrub(value)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return scrub(str(value))


class JsonFormatter(logging.Formatter):
    """One JSON object per record."""

    def __init__(self, service: str = "eurogas-nexus") -> None:
        super().__init__()
        self.service = service

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "service": self.service,
            "message": scrub(record.getMessage()),
        }
        request_id = current_request_id()
        if request_id:
            payload["request_id"] = request_id
        principal_id = current_principal_id()
        if principal_id:
            payload["principal_id"] = principal_id
        trace_id = _trace_id()
        if trace_id:
            payload["trace_id"] = trace_id
        for key, value in record.__dict__.items():
            if key in _STANDARD_ATTRS or key.startswith("_") or key in payload:
                continue
            payload[key] = _safe_field(key, value)
        if record.exc_info:
            # The exception class and the frames, never the exception's arguments (they can
            # carry a statement's parameters or a connection string).
            exc_type = record.exc_info[0]
            payload["error_type"] = exc_type.__name__ if exc_type else None
            payload["stack"] = scrub(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False, default=str)


class TextFormatter(logging.Formatter):
    """Readable lines for a terminal, still carrying the request id."""

    def __init__(self) -> None:
        super().__init__("%(asctime)s %(levelname)s %(name)s %(message)s")

    def format(self, record: logging.LogRecord) -> str:
        line = scrub(super().format(record))
        request_id = current_request_id()
        if request_id:
            principal_id = current_principal_id()
            line += f" [request_id={request_id}" + (
                f" principal_id={principal_id}]" if principal_id else "]"
            )
        return line


def _trace_id() -> str | None:
    """The current OpenTelemetry trace id, when tracing is on and installed."""

    from eurogas_nexus.core import tracing

    return tracing.current_trace_id()


def log_format(environ: dict[str, str] | os._Environ | None = None) -> str:
    env = os.environ if environ is None else environ
    configured = (env.get("EUROGAS_NEXUS_LOG_FORMAT") or "").strip().lower()
    if configured in {"json", "text"}:
        return configured
    environment = (env.get("EUROGAS_NEXUS_ENV") or "development").strip().lower()
    return "json" if environment in {"trial", "release", "production"} else "text"


def configure_logging(*, service: str = "eurogas-nexus", force: bool = False) -> str:
    """Route the root, uvicorn and application loggers through one formatter.

    Idempotent (a second call is a no-op unless ``force``). Returns the format in force.
    Uvicorn's own access log is silenced in JSON mode: it carries the client address, and
    the API writes its own access record (route, status, duration, request and principal
    id) instead.
    """

    global _CONFIGURED
    chosen = log_format()
    if _CONFIGURED and not force:
        return chosen
    level_name = (os.environ.get("EUROGAS_NEXUS_LOG_LEVEL") or "INFO").strip().upper()
    level = getattr(logging, level_name, logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter(service) if chosen == "json" else TextFormatter())
    handler.set_name(_HANDLER_NAME)
    root = logging.getLogger()
    # Replace only our own handler: a handler someone else attached (a test's log capture,
    # a host's collector) stays.
    root.handlers = [item for item in root.handlers if item.get_name() != _HANDLER_NAME]
    root.addHandler(handler)
    root.setLevel(level)
    for name in ("uvicorn", "uvicorn.error", "eurogas_nexus"):
        logger = logging.getLogger(name)
        logger.handlers = []
        logger.propagate = True
    access = logging.getLogger("uvicorn.access")
    access.handlers = []
    access.propagate = chosen != "json"
    if chosen == "json":
        access.disabled = True
    _CONFIGURED = True
    return chosen


ACCESS_LOGGER = "eurogas_nexus.access"


def log_access(
    *, method: str, route: str, status: int, duration_ms: float, stream: bool = False
) -> None:
    """One access record per API request (no address, no query string)."""

    logging.getLogger(ACCESS_LOGGER).info(
        "request",
        extra={
            "http_method": method,
            "route": route,
            "status": status,
            "duration_ms": round(duration_ms, 1),
            **({"stream": True} if stream else {}),
        },
    )


__all__ = [
    "ACCESS_LOGGER",
    "JsonFormatter",
    "TextFormatter",
    "bind_request",
    "configure_logging",
    "current_principal_id",
    "current_request_id",
    "log_access",
    "log_format",
    "scrub",
    "unbind_request",
]
