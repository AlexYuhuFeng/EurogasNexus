"""API-facing name for the keyset-paging primitives.

The primitives live in :mod:`eurogas_nexus.core.keyset_paging` so the ``db`` repositories can
apply a page without importing the ``application`` layer (FF7 layer direction). This module
keeps the historical import path used by the application projections and the API routes.

See :mod:`eurogas_nexus.core.keyset_paging` for the pagination contract.
"""

from __future__ import annotations

from eurogas_nexus.core.keyset_paging import (
    CURSOR_VERSION,
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    KeysetPosition,
    PageCursorError,
    PageRequest,
    continuation,
    decode_cursor,
    encode_cursor,
    filters_digest,
    iso_ts,
    keyset_query,
    page_request,
    page_rows,
    parse_bound,
)

__all__ = [
    "CURSOR_VERSION",
    "DEFAULT_PAGE_SIZE",
    "MAX_PAGE_SIZE",
    "KeysetPosition",
    "PageCursorError",
    "PageRequest",
    "continuation",
    "decode_cursor",
    "encode_cursor",
    "filters_digest",
    "iso_ts",
    "keyset_query",
    "page_request",
    "page_rows",
    "parse_bound",
]
