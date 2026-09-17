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

Unhandled exceptions are deliberately left to the framework default: turning them
into a 500 body would change behaviour tests and operators rely on, and the client
already renders an unclassified failure safely. Wiring that path, with its own
always-on correlation and log capture, is a separate bounded step.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from eurogas_nexus.domain.operations.error_taxonomy import code_for_status, error_payload
from eurogas_nexus.security.identity import ROLE_RANK, Role

#: Operator surfaces may carry technical detail; business surfaces never do.
_OPERATOR_ROLES = frozenset({Role.OPERATOR.value, Role.ADMIN.value})


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


def _code_from_detail(detail: Any) -> str | None:
    """The stable code an endpoint declared, when it declared one."""

    if isinstance(detail, dict):
        for key in ("error", "code"):
            value = detail.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


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
