"""Revocation notes: a signed-out session or a disabled identity reaches open streams at once.

The database is the authority on sessions: every request re-reads its session row, so a
revocation holds on every API process for every request as soon as it is committed. A
live-update stream is different: it was authenticated once, when it opened, and then lives
for hours. Its guard re-reads the session and the identity from the database every
``REAUTH_SECONDS`` (``api/routes/public/streaming.py``); between those reads it consults the
notes written here, in the shared cache (``core/shared_cache.py``), on every poll:

* ``rv:s:<session hash>`` when one session is signed out;
* ``rv:p:<principal id>`` (the time) when every session of an identity is revoked (disabled,
  password reset, sign-out everywhere): a stream opened before that time ends.

With a shared backend every process sees a note within one poll; without one, the process
that handled the revocation does. A note that cannot be written or read changes nothing but
the delay: the database check still ends the stream within ``REAUTH_SECONDS``. A note is
written before the revocation commits; if the commit then fails, a stream ends that need not
have, and the client reconnects (the safe direction).

会话撤销标记：登出或停用后，已打开的实时流在下一次轮询即结束；数据库仍是权威。
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import UTC, datetime

logger = logging.getLogger(__name__)

#: How long a note is kept: a session lives at most this long (``SESSION_ABSOLUTE_TTL_HOURS``).
NOTE_TTL_SECONDS = 24 * 3600.0


def _session_key(session_hash: str) -> str:
    return f"rv:s:{session_hash}"


def _principal_key(principal_id: str) -> str:
    return f"rv:p:{principal_id}"


def note_session_revoked(session_hash: str) -> None:
    from eurogas_nexus.core.shared_cache import SharedCacheUnavailable, shared_cache

    try:
        shared_cache().set(_session_key(session_hash), b"1", ttl_seconds=NOTE_TTL_SECONDS)
    except SharedCacheUnavailable:
        logger.warning("session revocation note not written (shared cache unavailable)")


def note_principal_revoked(principal_id: str, at: datetime | None = None) -> None:
    from eurogas_nexus.core.shared_cache import SharedCacheUnavailable, shared_cache

    stamp = (at or datetime.now(UTC)).astimezone(UTC).isoformat()
    try:
        shared_cache().set(
            _principal_key(principal_id), stamp.encode(), ttl_seconds=NOTE_TTL_SECONDS
        )
    except SharedCacheUnavailable:
        logger.warning("identity revocation note not written (shared cache unavailable)")


def revoked_streams(
    streams: Iterable[tuple[str | None, str | None, datetime]],
) -> list[bool | None]:
    """For each ``(session hash, principal id, opened at)``: True when a note revokes it, False
    when none does, None when the cache cannot say (the database check then decides)."""

    from eurogas_nexus.core.shared_cache import SharedCacheUnavailable, shared_cache

    items = list(streams)
    keys: list[str] = []
    for session_hash, principal_id, _opened in items:
        if session_hash:
            keys.append(_session_key(session_hash))
        if principal_id:
            keys.append(_principal_key(principal_id))
    if not keys:
        return [False] * len(items)
    try:
        values = dict(zip(keys, shared_cache().get_many(keys), strict=True))
    except SharedCacheUnavailable:
        return [None] * len(items)
    out: list[bool | None] = []
    for session_hash, principal_id, opened in items:
        revoked = bool(session_hash and values.get(_session_key(session_hash)))
        stamp = values.get(_principal_key(principal_id)) if principal_id else None
        if stamp and not revoked:
            try:
                revoked = datetime.fromisoformat(stamp.decode()) >= opened
            except ValueError:
                revoked = True
        out.append(revoked)
    return out


__all__ = ["note_principal_revoked", "note_session_revoked", "revoked_streams"]
