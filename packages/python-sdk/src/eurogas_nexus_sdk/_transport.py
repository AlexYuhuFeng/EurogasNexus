"""Shared HTTP transport and response metadata for public SDK clients."""

from dataclasses import dataclass
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from eurogas_nexus_sdk import _http

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

    response = _http.get(url, params=params, timeout=timeout_seconds)
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


class SdkPageLimitError(RuntimeError):
    """A paged read had more pages than the caller allowed; narrow the range."""


def get_pages(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    max_pages: int = 100,
    timeout_seconds: float = 10.0,
) -> tuple[list[Any], ResponseMeta]:
    """GET every page of a keyset-paged read (``meta.continuation``), in order.

    Follows ``meta.continuation.cursor`` until ``has_more`` is false. Raises
    :class:`SdkPageLimitError` rather than return part of the range when more than
    ``max_pages`` pages would be needed. Returns the rows and the first page's meta.
    """

    rows: list[Any] = []
    first_meta: ResponseMeta | None = None
    query = dict(params or {})
    for _page in range(max_pages):
        data, meta = get_envelope(url, params=query, timeout_seconds=timeout_seconds)
        first_meta = first_meta or meta
        rows.extend(data)
        continuation = (meta.model_extra or {}).get("continuation") or {}
        if not continuation.get("has_more") or not continuation.get("cursor"):
            return rows, first_meta
        query = {**(params or {}), "cursor": continuation["cursor"]}
    raise SdkPageLimitError(
        f"more than {max_pages} pages; ask for a narrower from_utc/to_utc range"
    )
