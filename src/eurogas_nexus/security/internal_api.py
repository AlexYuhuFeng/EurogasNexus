"""Import-safe internal API token guard."""

from __future__ import annotations

import hmac
import os
from dataclasses import dataclass

INTERNAL_API_TOKEN_ENV = "EUROGAS_NEXUS_INTERNAL_API_TOKEN"


@dataclass(frozen=True)
class InternalApiAuthError(Exception):
    """Safe internal auth error that never carries secret values."""

    code: str
    status_code: int
    message: str

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


def internal_api_token_configured() -> bool:
    """Return whether the static V1 internal API token is configured."""

    return bool(_expected_token())


def verify_internal_api_token(provided_token: str | None) -> None:
    """Validate the provided internal token against the configured token."""

    expected = _expected_token()
    if not expected:
        raise InternalApiAuthError(
            code="internal_api_token_not_configured",
            status_code=503,
            message="Internal API token is not configured.",
        )
    token = (provided_token or "").strip()
    if not token:
        raise InternalApiAuthError(
            code="internal_api_token_missing",
            status_code=401,
            message="Internal API token is required.",
        )
    if not hmac.compare_digest(token, expected):
        raise InternalApiAuthError(
            code="internal_api_token_invalid",
            status_code=403,
            message="Internal API token is invalid.",
        )


def validate_internal_operator_headers(
    *,
    token: str | None,
    principal: str | None,
) -> str:
    """Validate internal token and explicit operator principal headers."""

    verify_internal_api_token(token)
    normalized_principal = (principal or "").strip()
    if not normalized_principal:
        raise InternalApiAuthError(
            code="internal_principal_missing",
            status_code=401,
            message="X-Eurogas-Principal is required for internal imports.",
        )
    return normalized_principal


def _expected_token() -> str:
    return os.environ.get(INTERNAL_API_TOKEN_ENV, "").strip()
