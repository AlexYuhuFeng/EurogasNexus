"""Import-safe public API token guard (release profile).

Kept FastAPI-free so the security package stays import-safe; the FastAPI
dependency lives in ``eurogas_nexus.api.dependencies.public_auth``.
"""

from __future__ import annotations

import hmac
import os
from dataclasses import dataclass

PUBLIC_API_TOKEN_ENV = "EUROGAS_NEXUS_PUBLIC_API_TOKEN"
API_KEY_HEADER = "X-Eurogas-Api-Key"


@dataclass(frozen=True)
class PublicApiAuthError(Exception):
    """Safe public API auth error that never carries secret values."""

    code: str
    status_code: int
    message: str

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


def public_api_token_configured() -> bool:
    """Return whether the static public API token is configured."""

    return bool(_expected_token())


def verify_public_api_token(provided_token: str | None) -> None:
    """Validate the provided public API token (constant-time compare)."""

    expected = _expected_token()
    if not expected:
        raise PublicApiAuthError(
            code="public_api_token_not_configured",
            status_code=503,
            message=(
                "Public API token is not configured; the release API refuses "
                "unauthenticated operation (fail-closed)."
            ),
        )
    token = (provided_token or "").strip()
    if not token:
        raise PublicApiAuthError(
            code="public_api_token_missing",
            status_code=401,
            message="Public API token is required.",
        )
    if not hmac.compare_digest(token, expected):
        raise PublicApiAuthError(
            code="public_api_token_invalid",
            status_code=403,
            message="Public API token is invalid.",
        )


def _expected_token() -> str:
    return os.environ.get(PUBLIC_API_TOKEN_ENV, "").strip()
