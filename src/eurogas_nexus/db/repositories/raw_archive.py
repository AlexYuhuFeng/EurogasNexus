"""Raw payload archive persistence (raw -> canonical lineage), each distinct page stored once.

A fetch writes one small **receipt** (``raw_payload_archives``: what was asked, when the answer
was received, how many records it held, the SHA-256 of its exact bytes) and the **page**
itself (``raw_payload_contents``) only when that digest is new. Before migration
``0095_retention_by_class`` each fetch stored the full page again, as text and as parsed JSON,
so a page read every hour was kept 168 times a week; the parsed JSON is reproducible from the
exact bytes and is no longer stored.

Readers never read the receipt's payload columns directly: :func:`load_raw_payload_bytes`
(and the text and JSON forms) serves a legacy receipt that still holds its page inline, a page
held hot in the database, and a page the retention job offloaded to object storage, verifying
the digest in every case.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import update
from sqlalchemy.orm import Session

from eurogas_nexus.db.models import RawPayloadArchiveRecord, RawPayloadContentRecord

STORED_IN_DATABASE = "database"
STORED_IN_OBJECT_STORE = "object_store"
COMPRESSION_GZIP = "gzip"


class RawArchiveDigestMismatch(ValueError):
    """The digest a caller claims is not the SHA-256 of the bytes it passed."""


class RawPayloadUnavailable(LookupError):
    """The page for a receipt cannot be read (missing, or the object store refused it)."""


def exact_payload_bytes(payload_text: str | None, payload_json: Any | None) -> bytes | None:
    """The bytes a digest covers: the text as UTF-8, else the canonical JSON serialisation.

    The canonical form (sorted keys, no ASCII escaping) is the one the public-source ingestor
    always hashed for a JSON-only payload.
    """

    if payload_text is not None:
        return payload_text.encode("utf-8")
    if payload_json is not None:
        return json.dumps(payload_json, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return None


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def store_payload_content(
    session: Session, *, payload_sha256: str, data: bytes, received_at_utc: datetime
) -> bool:
    """Keep ``data`` once under its digest; return True when this digest was new.

    Concurrent writers of the same page are safe: the insert does nothing on a conflict and
    the later receipt only moves ``last_received_at_utc`` forward.
    """

    received = _as_utc(received_at_utc)
    values = {
        "payload_sha256": payload_sha256,
        "byte_size": len(data),
        "compression": COMPRESSION_GZIP,
        "payload_compressed": gzip.compress(data, mtime=0),
        "stored_in": STORED_IN_DATABASE,
        "object_key": None,
        "first_received_at_utc": received,
        "last_received_at_utc": received,
        "offloaded_at_utc": None,
    }
    dialect = session.get_bind().dialect.name
    table = RawPayloadContentRecord.__table__
    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert as dialect_insert
    elif dialect == "sqlite":
        from sqlalchemy.dialects.sqlite import insert as dialect_insert
    else:  # pragma: no cover - the product runs PostgreSQL; SQLite in tests
        dialect_insert = None
    if dialect_insert is not None:
        result = session.execute(
            dialect_insert(table).values(**values).on_conflict_do_nothing(
                index_elements=["payload_sha256"]
            )
        )
        created = bool(result.rowcount)
    else:  # pragma: no cover
        created = session.get(RawPayloadContentRecord, payload_sha256) is None
        if created:
            session.add(RawPayloadContentRecord(**values))
            session.flush()
    if not created:
        session.execute(
            update(RawPayloadContentRecord)
            .where(
                RawPayloadContentRecord.payload_sha256 == payload_sha256,
                RawPayloadContentRecord.last_received_at_utc < received,
            )
            .values(last_received_at_utc=received)
            .execution_options(synchronize_session=False)
        )
    return created


def archive_raw_payload(
    session: Session,
    *,
    archive_id: str,
    source_system: str,
    dataset: str,
    source_reference: str,
    payload_text: str | None = None,
    payload_json: dict | None = None,
    payload_sha256: str,
    record_count: int,
    received_at_utc: datetime | None = None,
) -> RawPayloadArchiveRecord:
    """Append one immutable receipt and keep its page once.

    Raises:
        ValueError: neither text nor JSON was given.
        RawArchiveDigestMismatch: ``payload_sha256`` is not the digest of the exact bytes;
            the digest is the page's identity, so a wrong one would file it under another page.
    """

    data = exact_payload_bytes(payload_text, payload_json)
    if data is None:
        raise ValueError("a raw archive needs the page's text or JSON")
    if hashlib.sha256(data).hexdigest() != payload_sha256:
        raise RawArchiveDigestMismatch(
            "the archived digest must be the SHA-256 of the exact page bytes"
        )
    received = received_at_utc or datetime.now(UTC)
    store_payload_content(
        session, payload_sha256=payload_sha256, data=data, received_at_utc=received
    )
    record = RawPayloadArchiveRecord(
        archive_id=archive_id,
        source_system=source_system,
        dataset=dataset,
        source_reference=source_reference,
        payload_text=None,
        payload_json=None,
        payload_sha256=payload_sha256,
        record_count=record_count,
        received_at_utc=received,
        research_only=True,
        human_review_required=True,
    )
    session.add(record)
    session.flush()
    return record


def _receipt(session: Session, archive: RawPayloadArchiveRecord | str) -> RawPayloadArchiveRecord:
    if isinstance(archive, str):
        record = session.get(RawPayloadArchiveRecord, archive)
        if record is None:
            raise RawPayloadUnavailable(f"no raw archive receipt {archive}")
        return record
    return archive


def load_content_bytes(
    session: Session, payload_sha256: str, *, object_store=None
) -> bytes:
    """The exact bytes of one stored page, from the database or object storage, verified."""

    content = session.get(RawPayloadContentRecord, payload_sha256)
    if content is None:
        raise RawPayloadUnavailable(f"no stored page for digest {payload_sha256[:12]}")
    if content.payload_compressed is not None:
        data = gzip.decompress(content.payload_compressed)
    elif content.stored_in == STORED_IN_OBJECT_STORE and content.object_key:
        if object_store is None:
            from eurogas_nexus.runtime_store.object_store import object_store_from_environment

            object_store = object_store_from_environment()
        data = gzip.decompress(object_store.get_bytes(content.object_key))
    else:
        raise RawPayloadUnavailable(f"stored page {payload_sha256[:12]} has no location")
    if hashlib.sha256(data).hexdigest() != payload_sha256:
        raise RawPayloadUnavailable(f"stored page {payload_sha256[:12]} failed its digest check")
    return data


def load_raw_payload_bytes(
    session: Session, archive: RawPayloadArchiveRecord | str, *, object_store=None
) -> bytes:
    """The exact bytes a receipt archived, wherever they are now kept."""

    record = _receipt(session, archive)
    inline = exact_payload_bytes(record.payload_text, record.payload_json)
    if inline is not None:
        return inline
    return load_content_bytes(session, record.payload_sha256, object_store=object_store)


def load_raw_payload_text(
    session: Session, archive: RawPayloadArchiveRecord | str, *, object_store=None
) -> str:
    return load_raw_payload_bytes(session, archive, object_store=object_store).decode("utf-8")


def load_raw_payload_json(
    session: Session, archive: RawPayloadArchiveRecord | str, *, object_store=None, **loads
) -> Any:
    record = _receipt(session, archive)
    if record.payload_json is not None and not loads:
        return record.payload_json
    return json.loads(load_raw_payload_text(session, record, object_store=object_store), **loads)


def move_inline_payloads_to_contents(
    session: Session, *, limit: int = 500, dry_run: bool = False
) -> dict[str, int]:
    """Deduplicate receipts written before 0095: move each inline page into the content store.

    Batched (``limit`` receipts per call) because the archive is most of the database. A
    receipt whose inline page does not match its digest is left exactly as it is and counted,
    never rewritten: its digest is the lineage other rows cite.
    """

    rows = (
        session.query(RawPayloadArchiveRecord)
        .filter(
            (RawPayloadArchiveRecord.payload_text.is_not(None))
            | (RawPayloadArchiveRecord.payload_json.is_not(None))
        )
        .order_by(RawPayloadArchiveRecord.received_at_utc)
        .limit(limit)
        .all()
    )
    moved = new_pages = mismatched = 0
    for row in rows:
        data = exact_payload_bytes(row.payload_text, row.payload_json)
        if data is None:
            # Written before ``none_as_null`` with the JSON value ``null`` and no text: there
            # is no inline page to move, only a marker to normalise.
            row.payload_json = None
            continue
        if hashlib.sha256(data).hexdigest() != row.payload_sha256:
            mismatched += 1
            continue
        if dry_run:
            moved += 1
            continue
        new_pages += store_payload_content(
            session,
            payload_sha256=row.payload_sha256,
            data=data,
            received_at_utc=row.received_at_utc,
        )
        row.payload_text = None
        row.payload_json = None
        moved += 1
    session.flush()
    return {
        "receipts_examined": len(rows),
        "receipts_moved": moved,
        "distinct_pages_added": new_pages,
        "receipts_left_digest_mismatch": mismatched,
    }


def restore_inline_payloads(session: Session, *, limit: int = 500) -> int:
    """Put pages back on their receipts (only to downgrade below 0095). Returns receipts done."""

    rows = (
        session.query(RawPayloadArchiveRecord)
        .filter(
            RawPayloadArchiveRecord.payload_text.is_(None),
            RawPayloadArchiveRecord.payload_json.is_(None),
        )
        .limit(limit)
        .all()
    )
    for row in rows:
        row.payload_text = load_content_bytes(session, row.payload_sha256).decode("utf-8")
    session.flush()
    return len(rows)
