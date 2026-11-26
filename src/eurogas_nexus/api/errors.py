"""``ApiError``: a refusal with a stable code, its English text and the values it names.

A route raises::

    raise ApiError(404, "reference_node_not_found", f"Node '{node_id}' not found.",
                   params={"node_id": node_id})

The error envelope (``api/error_handlers.py``) reports ``error`` = the code, ``params`` and
``fallback_message`` = the English text; ``detail`` stays the English text, exactly what the
route raised before it had a code, so a client that reads ``detail`` is unaffected. The
client translates ``errors.<code>.message`` with ``params`` and shows the English text only
when it has no entry for the code.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fastapi import HTTPException


class ApiError(HTTPException):
    """An HTTP refusal that names its code and interpolation values."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        *,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(status_code=status_code, detail=message, headers=dict(headers or {}))
        self.code = code
        self.params = dict(params or {})
