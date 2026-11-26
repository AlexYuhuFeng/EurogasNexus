"""Optional OpenTelemetry tracing: off by default, and a seam rather than a dependency.

``EUROGAS_NEXUS_OTEL_ENABLED=1`` turns it on. The OpenTelemetry packages are not in the
product's locks (decision P1-C-3 in the execution state: their licences pass the gate, but
the SDK with the OTLP exporter adds about a dozen packages to every installation for a
setting that is off by default). A deployment that wants traces installs into its image::

    opentelemetry-sdk opentelemetry-exporter-otlp-proto-http

and sets ``OTEL_EXPORTER_OTLP_ENDPOINT`` (and, if it likes, ``OTEL_SERVICE_NAME``); the
exporter reads the standard ``OTEL_*`` variables itself. With the setting on and the
packages missing, the server starts, logs one warning and runs without traces.

When on, each API request is one server span named ``<METHOD> <route template>`` with the
status code; the request id is a span attribute and the trace id is added to every log
record of the request. No header, query string, body, client address or principal is put
on a span.
"""

from __future__ import annotations

import logging
import os
from typing import Any

_LOG = logging.getLogger("eurogas_nexus.tracing")
_TRACER: Any = None
_STATE = {"initialised": False}


def tracing_requested(environ: dict[str, str] | os._Environ | None = None) -> bool:
    env = os.environ if environ is None else environ
    return (env.get("EUROGAS_NEXUS_OTEL_ENABLED") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def initialise(service_name: str = "eurogas-nexus-api") -> bool:
    """Set up the tracer once; returns whether tracing is active."""

    global _TRACER
    if _STATE["initialised"]:
        return _TRACER is not None
    _STATE["initialised"] = True
    if not tracing_requested():
        return False
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:
        _LOG.warning(
            "tracing requested but the OpenTelemetry packages are not installed; "
            "running without traces (docs/operations/MONITORING.md, Tracing)"
        )
        return False
    name = (os.environ.get("OTEL_SERVICE_NAME") or service_name).strip() or service_name
    provider = TracerProvider(resource=Resource.create({"service.name": name}))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)
    _TRACER = trace.get_tracer("eurogas_nexus")
    _LOG.info("tracing on", extra={"otel_service_name": name})
    return True


def tracer() -> Any:
    return _TRACER


def current_trace_id() -> str | None:
    if _TRACER is None:
        return None
    try:
        from opentelemetry import trace

        context = trace.get_current_span().get_span_context()
    except Exception:  # noqa: BLE001
        return None
    if not getattr(context, "is_valid", False):
        return None
    return f"{context.trace_id:032x}"


def reset_for_tests() -> None:
    global _TRACER
    _TRACER = None
    _STATE["initialised"] = False


__all__ = ["current_trace_id", "initialise", "reset_for_tests", "tracer", "tracing_requested"]
