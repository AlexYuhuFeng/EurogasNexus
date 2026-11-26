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

Translation contract (backend audit 2026-11-26): the envelope also carries ``params``,
the values a sentence for the code interpolates (``{"node_id": "..."}``), and
``fallback_message``, the endpoint's own English text, so a client renders
``errors.<error>.message`` with ``params`` in the user's language and falls back to the
English text only when it has no entry for the code. A route raises
:class:`eurogas_nexus.api.errors.ApiError` (code, English text, params) or a dict
``detail`` with ``code`` and ``message``; a plain string ``detail`` with no code is refused
by ``tests/contract/test_api_error_codes.py``.

Every refusal gets this one shape, the router's own included: a path that matches no route
(404) or a method a route does not take (405) is raised by Starlette, not FastAPI, and used
to answer a bare ``{"detail": "Not Found"}`` that no client could classify.

An **unexpected** failure is enveloped too: status 500, the framework's own
user-facing text in ``detail``, the ``internal`` code from the taxonomy (family
SYSTEM, severity critical), an always-present correlation id echoed on
``X-Request-Id``, and the fault's own type name - never its message - in
``operator_detail``, which only an operator identity receives. The traceback is
still the server's business: Starlette re-raises after the response is sent, so
logging and monitoring keep seeing the real failure.
"""

from __future__ import annotations

import math
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from eurogas_nexus.application.bounded_reads import ReadBoundExceeded
from eurogas_nexus.domain.operations.error_taxonomy import code_for_status, error_payload
from eurogas_nexus.governance.audit import GovernedAuditError
from eurogas_nexus.security.identity import ROLE_RANK, Role

#: Operator surfaces may carry technical detail; business surfaces never do.
_OPERATOR_ROLES = frozenset({Role.OPERATOR.value, Role.ADMIN.value})

#: The catalogued code for an unexpected internal fault (family SYSTEM, critical).
UNHANDLED_ERROR_CODE = "internal"

#: The framework's own user-facing text for a 500, kept so clients that read ``detail``
#: are unaffected by the envelope.
_SERVER_ERROR_DETAIL = "Internal Server Error"


#: Keys of a dict ``detail`` that are not interpolation values: the code itself, and the
#: text fields (``reason``/``developer_message`` may carry internal wording).
_NOT_PARAMS = frozenset(
    {"error", "code", "error_code", "message", "reason", "developer_message", "detail"}
)


def error_body(
    status_code: int,
    detail: Any,
    *,
    code: str | None = None,
    params: dict[str, Any] | None = None,
    correlation_id: str | None = None,
    operator: bool = False,
    operator_detail: str | None = None,
) -> dict[str, Any]:
    """The one error body: ``detail`` as raised, the taxonomy, ``params``, the English text.

    Shared by the exception handlers and the middlewares that answer before routing
    (``origin_csrf``, the web client's static fallback), so no layer builds its own shape.
    """

    resolved = code or _code_from_detail(detail) or code_for_status(status_code)
    payload = error_payload(
        resolved,
        correlation_id=correlation_id,
        operator=operator,
        operator_detail=operator_detail,
        status_code=status_code,
    )
    body: dict[str, Any] = {"detail": detail}
    body.update(payload)
    body["params"] = _json_safe_value(params if params is not None else _params_from(detail))
    fallback = _fallback_message(detail)
    if fallback:
        body["fallback_message"] = fallback
    return body


def register_error_handlers(app: FastAPI) -> None:
    """Attach the product error envelope to a FastAPI application."""

    async def _http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        operator = _is_operator_request(request)
        exc = _as_database_timeout(exc)
        detail = exc.detail
        if isinstance(detail, dict) and "error_class" in detail and not operator:
            # Security review L1: an exception's class name is for operators only, whichever
            # route put it in the detail.
            detail = {key: value for key, value in detail.items() if key != "error_class"}
        body = error_body(
            exc.status_code,
            detail,
            code=getattr(exc, "code", None),
            params=getattr(exc, "params", None),
            correlation_id=getattr(request.state, "request_id", None),
            operator=operator,
            operator_detail=_operator_detail(detail, operator=operator),
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=body,
            headers=dict(exc.headers or {}) or None,
        )

    # Starlette's class covers the router's own 404/405; FastAPI's subclass is named too so
    # the lookup never reaches FastAPI's default handler first.
    app.add_exception_handler(StarletteHTTPException, _http_exception)
    app.add_exception_handler(HTTPException, _http_exception)

    from eurogas_nexus.security.portfolio_scope import BookScopeViolation

    async def _book_scope_violation(request: Request, exc: BookScopeViolation) -> JSONResponse:
        """A write into a book outside the caller's book scope (security review H1)."""

        return await _http_exception(
            request,
            HTTPException(
                status_code=403,
                detail={
                    "code": "book_outside_scope",
                    "message": "This record is held in a book you cannot see.",
                },
            ),
        )

    app.add_exception_handler(BookScopeViolation, _book_scope_violation)

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
        errors = _jsonable_detail(exc.errors())
        # The fields refused, so a client can name them in its own language.
        fields = [
            ".".join(str(part) for part in item.get("loc", ()) if part not in {"body", "query"})
            for item in errors
            if isinstance(item, dict)
        ]
        return JSONResponse(
            status_code=422,
            # `exc.errors()` is what FastAPI's own 422 body carries, cleaned only where an
            # exception object would not serialise.
            content={
                "detail": errors,
                **payload,
                "params": {"fields": [field for field in fields if field]},
            },
            # The request reached the middleware that stamps an id, so only a generated one is
            # echoed here; otherwise the header would carry the same id twice.
            headers={} if existing_id else {"X-Request-Id": correlation_id},
        )

    @app.exception_handler(GovernedAuditError)
    async def _governed_audit_error(request: Request, exc: GovernedAuditError) -> JSONResponse:
        """A governed write whose audit row could not be written did not happen (GOV-1, P5).

        The transaction was not committed, so nothing changed; the caller may retry once the
        audit store is back. The cause's type name goes to an operator identity only.
        """

        correlation_id = getattr(request.state, "request_id", None) or uuid4().hex
        operator = _is_operator_request(request)
        payload = error_payload(
            GovernedAuditError.code,
            correlation_id=correlation_id,
            operator=operator,
            operator_detail=exc.cause_type if operator else None,
        )
        detail = {
            "code": GovernedAuditError.code,
            "action": exc.action,
            "message": "The change was not made because its audit record could not be written.",
        }
        return JSONResponse(
            status_code=503,
            content={
                "detail": detail,
                **payload,
                "params": {"action": exc.action},
                "fallback_message": detail["message"],
            },
            headers={"X-Request-Id": correlation_id},
        )

    @app.exception_handler(ReadBoundExceeded)
    async def _read_bound_exceeded(request: Request, exc: ReadBoundExceeded) -> JSONResponse:
        """A calculation whose inputs exceed its read bound refuses instead of using part."""

        correlation_id = getattr(request.state, "request_id", None) or uuid4().hex
        body = error_body(
            422,
            {"code": exc.code, "message": str(exc), "what": exc.what, "bound": exc.bound},
            correlation_id=correlation_id,
        )
        return JSONResponse(status_code=422, content=body)

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
            content={"detail": _SERVER_ERROR_DETAIL, **payload, "params": {}},
            headers={"X-Request-Id": correlation_id},
        )


def database_failure_exception(exc: BaseException) -> HTTPException | None:
    """The coded 503 for a database failure a route did not catch, or None.

    A statement the server cancelled (``statement_timeout``) answers ``runtime_db_timeout``; a
    lost or unreachable store ``runtime_db_unavailable``; both say when to retry.
    """

    from eurogas_nexus.core.db_errors import (
        DB_RETRY_AFTER_SECONDS,
        DB_TIMEOUT_CODE,
        database_failure,
    )

    kind = database_failure(exc)
    if kind is None:
        return None
    retry = {"Retry-After": str(DB_RETRY_AFTER_SECONDS)}
    if kind == "timeout":
        return HTTPException(
            status_code=503,
            detail={
                "code": DB_TIMEOUT_CODE,
                "message": "The database stopped this read because it took too long.",
                "error_class": type(exc).__name__,
            },
            headers=retry,
        )
    return HTTPException(
        status_code=503,
        detail={
            "code": "runtime_db_unavailable",
            "message": "The runtime database could not be reached.",
            "error_class": type(exc).__name__,
        },
        headers=retry,
    )


def _as_database_timeout(exc: StarletteHTTPException) -> StarletteHTTPException:
    """A route's own 503 for a database error whose cause was a statement timeout.

    Routes answer a database error as ``runtime_db_unavailable`` (``raise ... from exc``);
    when the cause was the server cancelling a slow statement, the store is up and the read
    was slow, so the answer names that and tells the client when to retry.
    """

    if exc.status_code != 503 or exc.__cause__ is None:
        return exc
    from eurogas_nexus.core.db_errors import is_statement_timeout

    if not is_statement_timeout(exc.__cause__):
        return exc
    coded = database_failure_exception(exc.__cause__)
    if coded is None:
        return exc
    headers = {**(exc.headers or {}), **(coded.headers or {})}
    return HTTPException(status_code=503, detail=coded.detail, headers=headers)


def _unhandled_detail(exc: Exception, *, operator: bool) -> str | None:
    """The fault's own type name for an operator identity, never its message."""

    if not operator:
        return None
    return exc.__class__.__name__


def _code_from_detail(detail: Any) -> str | None:
    """The stable code an endpoint declared, when it declared one."""

    if isinstance(detail, dict):
        # Three spellings grew up for the one field; all mean the endpoint's stable code.
        for key in ("error", "code", "error_code"):
            value = detail.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _params_from(detail: Any) -> dict[str, Any]:
    """Interpolation values of a dict ``detail``: its own ``params``, else its plain values.

    Only what ``detail`` already carries to the same caller, so nothing new is disclosed.
    """

    if not isinstance(detail, dict):
        return {}
    explicit = detail.get("params")
    if isinstance(explicit, dict):
        return dict(explicit)
    scalar = (str, int, float, bool, type(None))
    return {
        key: value
        for key, value in detail.items()
        if isinstance(key, str)
        and key not in _NOT_PARAMS
        and (
            isinstance(value, scalar)
            or (isinstance(value, list | tuple) and all(isinstance(v, scalar) for v in value))
        )
    }


def _fallback_message(detail: Any) -> str | None:
    """The endpoint's own English text: a string ``detail``, or a dict's ``message``."""

    if isinstance(detail, str) and detail.strip():
        return detail.strip()
    if isinstance(detail, dict):
        message = detail.get("message")
        if isinstance(message, str) and message.strip():
            return message.strip()
    return None


def _jsonable_detail(detail: Any) -> Any:
    """The framework's validation detail, made JSON-serialisable without being changed.

    FastAPI hands the handler the raw errors, whose `ctx` can hold exception objects. They are
    stringified rather than dropped: an operator diagnosing a refused body needs to see which
    value was rejected, and the field list is the caller's own input, not platform state.
    A non-finite float in the echoed input (`NaN`/±`Infinity` tokens the wire format can carry)
    is echoed as its text form for the same reason: `JSONResponse` cannot serialise it, and a
    refused body must answer 422 rather than break the response.
    """

    if isinstance(detail, list):
        cleaned = []
        for item in detail:
            if isinstance(item, dict) and isinstance(item.get("ctx"), dict):
                item = {
                    **item,
                    "ctx": {key: str(value) for key, value in item["ctx"].items()},
                }
            cleaned.append(_json_safe_value(item))
        return cleaned
    return _json_safe_value(detail)


def _json_safe_value(value: Any) -> Any:
    """Return ``value`` with non-serialisable floats replaced by their text form."""

    if isinstance(value, float) and not math.isfinite(value):
        return repr(value)
    if isinstance(value, dict):
        return {key: _json_safe_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe_value(item) for item in value]
    return value


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
