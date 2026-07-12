"""Shared HTTP transport and response metadata for public SDK clients."""

from dataclasses import dataclass
from typing import Any, Generic, TypeVar

import httpx
from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ResponseMeta(BaseModel):
    """Metadata preserved from the backend response envelope."""

    model_config = ConfigDict(extra="allow")

    research_only: bool = True
    human_review_required: bool = True
    source_references: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


@dataclass(frozen=True, slots=True)
class SdkResult(Generic[T]):
    """Typed SDK data plus backend lineage and warning metadata."""

    data: T
    meta: ResponseMeta


class SdkProtocolError(RuntimeError):
    """Raised when a backend response violates the public envelope contract."""


def get_envelope(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    timeout_seconds: float = 10.0,
) -> tuple[Any, ResponseMeta]:
    """GET and validate one public API response envelope."""

    response = httpx.get(url, params=params, timeout=timeout_seconds)
    response.raise_for_status()
    try:
        payload = response.json()
    except ValueError as exc:
        raise SdkProtocolError("Backend returned a non-JSON response.") from exc
    if not isinstance(payload, dict) or "data" not in payload or "meta" not in payload:
        raise SdkProtocolError("Backend response is missing data/meta envelope fields.")
    return payload["data"], ResponseMeta.model_validate(payload["meta"])


def api_url(base_url: str, path: str) -> str:
    """Join an operator-provided server URL with one canonical `/api` path."""

    return f"{base_url.rstrip('/')}/api/{path.lstrip('/')}"
