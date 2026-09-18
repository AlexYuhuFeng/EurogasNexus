"""Product error envelope for HTTP failures (Architecture V2 Wave 8).

Architecture V2 section 6 of `08_DECISION_APPLICATION_AI.md` requires every failure
to expose a stable code, severity, recoverability, a suggested action and the
correlation id, with operator detail only on operator surfaces.

This module adds that information to the response **without changing the shape
FastAPI already produces**: ``detail`` is passed through exactly as the endpoint
raised it (a string stays a string, a dict keeps every key), and the taxonomy
fields are added alongside it at the top level::

    {
      "detail": {...},                # unchanged, whatever the endpoint raised
      "error": "identity_role_forbidden",
      "family": "AUTH",
      "severity": "error",
      "recoverability": "permanent",
      "message_key": "errors.identity_role_forbidden.message",
      "action_key": "errors.identity_role_forbidden.action",
      "correlation_id": "8f2c…"       # same value as the X-Request-Id header
    }

Additive by construction, so Web, SDK and CLI clients that read ``detail`` keep
working, while a V2 client can explain the failure through the taxonomy.

An **unexpected** failure is enveloped too: status 500, the framework's own
user-facing text in ``detail``, the ``internal`` code from the taxonomy (family
SYSTEM, severity critical), an always-present correlation id echoed on
``X-Request-Id``, and the fault's own type name - never its message - in
``operator_detail``, which only an operator identity receives. The traceback is
still the server's business: Starlette re-raises after the response is sent, so
logging and monitoring keep seeing the real failure.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from eurogas_nexus.domain.operations.error_taxonomy import code_for_status, error_payload
from eurogas_nexus.security.identity import ROLE_RANK, Role

#: Operator surfaces may carry technical detail; business surfaces never do.
_OPERATOR_ROLES = frozenset({Role.OPERATOR.value, Role.ADMIN.value})

#: The catalogued code for an unexpected internal fault (family SYSTEM, critical).
UNHANDLED_ERROR_CODE = "internal"

#: The framework's own user-facing text for a 500, kept so clients that read ``detail``
#: are unaffected by the envelope.
_SERVER_ERROR_DETAIL = "Internal Server Error"


def register_error_handlers(app: FastAPI) -> None:
    """Attach the product error envelope to a FastAPI application."""

    @app.exception_handler(HTTPException)
    async def _http_exception(request: Request, exc: HTTPException) -> JSONResponse:
        code = _code_from_detail(exc.detail) or code_for_status(exc.status_code)
        correlation_id = getattr(request.state, "request_id", None)
        operator = _is_operator_request(request)
        payload = error_payload(
            code,
            correlation_id=correlation_id,
            operator=operator,
            operator_detail=_operator_detail(exc.detail, operator=operator),
        )
        body: dict[str, Any] = {"detail": exc.detail}
        body.update(payload)
        return JSONResponse(
            status_code=exc.status_code,
            content=body,
            headers=dict(exc.headers or {}) or None,
        )

    @app.exception_handler(RequestValidationError)
    async def _request_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """Envelope the framework's own 422 without rewriting its `detail`.

        FastAPI answers a malformed request body with a bare `{"detail": [...]}` list, which a
        client reading the taxonomy cannot classify: it was presented as an unclassified SYSTEM
        fault, when what actually happened is the most ordinary thing there is - the caller's
        input did not match the contract. The status code and the `detail` list are kept exactly
        as FastAPI produces them (clients that read `detail` are unaffected); the taxonomy fields
        are added beside them, so the failure reads as VALIDATION and the caller is told to fix
        the request.
        """

        existing_id = getattr(request.state, "request_id", None)
        correlation_id = existing_id or uuid4().hex
        payload = error_payload("validation_failed", correlation_id=correlation_id)
        return JSONResponse(
            status_code=422,
            # `exc.errors()` is what FastAPI's own 422 body carries, cleaned only where an
            # exception object would not serialise.
            content={"detail": _jsonable_detail(exc.errors()), **payload},
            # The request reached the middleware that stamps an id, so only a generated one is
            # echoed here; otherwise the header would carry the same id twice.
            headers={} if existing_id else {"X-Request-Id": correlation_id},
        )

    @app.exception_handler(Exception)
    async def _unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
        """Envelope an unexpected failure without hiding it or leaking it.

        The client learns a stable code, the family, the severity, what to do next and a
        correlation id; it never learns the exception's text, which can carry commercial
        values (a row, a price, a query fragment). The operator identity additionally sees
        the fault's class, which is what makes it matchable to a server log line.
        """

        correlation_id = getattr(request.state, "request_id", None) or uuid4().hex
        operator = _is_operator_request(request)
        payload = error_payload(
            UNHANDLED_ERROR_CODE,
            correlation_id=correlation_id,
            operator=operator,
            operator_detail=_unhandled_detail(exc, operator=operator),
        )
        return JSONResponse(
            status_code=500,
            content={"detail": _SERVER_ERROR_DETAIL, **payload},
            headers={"X-Request-Id": correlation_id},
        )


def _unhandled_detail(exc: Exception, *, operator: bool) -> str | None:
    """The fault's own type name for an operator identity, never its message."""

    if not operator:
        return None
    return exc.__class__.__name__


def _code_from_detail(detail: Any) -> str | None:
    """The stable code an endpoint declared, when it declared one."""

    if isinstance(detail, dict):
        for key in ("error", "code"):
            value = detail.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _jsonable_detail(detail: Any) -> Any:
    """The framework's validation detail, made JSON-serialisable without being changed.

    FastAPI hands the handler the raw errors, whose `ctx` can hold exception objects. They are
    stringified rather than dropped: an operator diagnosing a refused body needs to see which
    value was rejected, and the field list is the caller's own input, not platform state.
    """

    if isinstance(detail, list):
        cleaned = []
        for item in detail:
            if isinstance(item, dict) and isinstance(item.get("ctx"), dict):
                item = {
                    **item,
                    "ctx": {key: str(value) for key, value in item["ctx"].items()},
                }
            cleaned.append(item)
        return cleaned
    return detail


def _operator_detail(detail: Any, *, operator: bool) -> str | None:
    """Technical text for an operator surface only.

    A string detail is the endpoint's own user-facing message, so it is not
    duplicated into ``detail``; a dict's ``reason``/``message`` may carry internal
    wording, which is why it is gated on an operator identity.
    """

    if not operator or not isinstance(detail, dict):
        return None
    for key in ("reason", "message", "developer_message"):
        value = detail.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _is_operator_request(request: Request) -> bool:
    """Whether the authenticated identity may see technical error detail."""

    identity = getattr(request.state, "identity", None)
    role = getattr(identity, "role", None)
    if not isinstance(role, str):
        return False
    try:
        normalized = Role(role.upper())
    except ValueError:
        return False
    return normalized.value in _OPERATOR_ROLES and ROLE_RANK[normalized] >= ROLE_RANK[Role.OPERATOR]
