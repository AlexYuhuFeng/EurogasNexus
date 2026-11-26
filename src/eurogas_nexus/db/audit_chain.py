"""Tamper-evident audit trail: a hash chain, its verification, anchors and SIEM forwarding.

Security review H5: the audit trail was append-only by convention. Now:

* **Hash chain.** When a transaction that wrote audit rows commits, its rows are sealed in
  order: each gets a link in ``audit_chain`` with the next ``chain_seq``, the previous link's
  hash (``prev_hash``) and ``row_hash = SHA-256(prev_hash || canonical JSON of the row)``.
  Links are inserted, never updated, so the application role needs only INSERT on both
  ``audit_events`` and ``audit_chain``. Sealing runs inside the
  writing transaction, just before it commits, under a PostgreSQL advisory lock taken after
  the transaction's own statements, so the lock is held only for the seal and cannot
  deadlock with row locks. A row edited, removed or inserted out of order breaks
  :func:`verify_chain`.
* **Anchors.** Pruning records the last removed row as an anchor, so the first remaining row
  still proves its place; :func:`checkpoint` records a signed digest of the chain head for
  export to a SIEM or a WORM store.
* **Database guard.** Migration 0095 adds PostgreSQL triggers that refuse any UPDATE of an
  audit row or a link, and any DELETE outside an approved prune; docs/security/DATABASE_ROLES.md
  takes UPDATE and DELETE away from the application role altogether.
* **SIEM.** ``EUROGAS_NEXUS_AUDIT_SINK`` forwards each sealed row as one JSON line: ``stdout``,
  ``file:/path``, ``syslog://host:port`` (UDP, RFC 5424) or an ``https://`` webhook.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import socket
import threading
import urllib.request
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import event, func, select, text
from sqlalchemy.orm import Session

AUDIT_SINK_ENV = "EUROGAS_NEXUS_AUDIT_SINK"
GENESIS = "0" * 64
#: Advisory-lock key of the chain seal (any constant shared by every writer).
SEAL_LOCK_KEY = 0x45474E41  # "EGNA"
_CONTENT_FIELDS = (
    "event_id",
    "event_type",
    "severity",
    "principal",
    "action",
    "resource",
    "outcome",
    "detail",
    "event_ts_utc",
    "source_system",
    "human_review_required",
    "permission",
    "correlation_id",
    "client_type",
    "before_summary",
    "after_summary",
)
_LOG = logging.getLogger("eurogas_nexus.audit")
_PENDING = "audit_chain_pending"
_SEALED = "audit_chain_sealed"


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        aware = value if value.tzinfo else value.replace(tzinfo=UTC)
        return aware.astimezone(UTC).isoformat(timespec="microseconds")
    return str(value)


def canonical(row: Any) -> dict[str, Any]:
    """The row's content as hashed and as forwarded (no chain fields)."""

    values = {name: getattr(row, name, None) for name in _CONTENT_FIELDS}
    values["event_ts_utc"] = _iso(values["event_ts_utc"])
    values["human_review_required"] = bool(values["human_review_required"])
    return values


def row_digest(prev_hash: str, row: Any) -> str:
    body = json.dumps(canonical(row), sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256((prev_hash + body).encode("utf-8")).hexdigest()


def _models():
    from eurogas_nexus.db.models import (
        AuditChainAnchorRecord,
        AuditChainRecord,
        AuditEventRecord,
    )

    return AuditEventRecord, AuditChainRecord, AuditChainAnchorRecord


def _lock(session: Session) -> None:
    if session.get_bind().dialect.name == "postgresql":
        session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": SEAL_LOCK_KEY})


def _head(session: Session) -> tuple[int, str]:
    _audit, chain, anchors = _models()
    row = session.execute(
        select(chain.chain_seq, chain.row_hash).order_by(chain.chain_seq.desc()).limit(1)
    ).first()
    if row is not None:
        return int(row[0]), str(row[1])
    anchor = _prune_anchor(session)
    return anchor if anchor is not None else (0, GENESIS)


def _prune_anchor(session: Session) -> tuple[int, str] | None:
    _audit, _chain, anchors = _models()
    row = session.execute(
        select(anchors.chain_seq, anchors.row_hash)
        .where(anchors.kind == "prune")
        .order_by(anchors.chain_seq.desc())
        .limit(1)
    ).first()
    return (int(row[0]), str(row[1])) if row is not None else None


def _unsealed(session: Session):
    audit, chain, _anchors = _models()
    return session.query(audit).filter(~audit.event_id.in_(select(chain.event_id)))


def seal_pending(session: Session) -> list[tuple[Any, Any]]:
    """Seal every unsealed audit row in event order; returns ``(event, link)`` pairs."""

    _audit, chain, _anchors = _models()
    audit = _audit
    _lock(session)
    seq, prev = _head(session)
    rows = _unsealed(session).order_by(audit.event_ts_utc, audit.event_id).all()
    now = datetime.now(UTC)
    sealed = []
    for row in rows:
        seq += 1
        link = chain(
            chain_seq=seq,
            event_id=row.event_id,
            prev_hash=prev,
            row_hash=row_digest(prev, row),
            sealed_at_utc=now,
        )
        session.add(link)
        sealed.append((row, link))
        prev = link.row_hash
    if sealed:
        session.flush()
    return sealed


def verify_chain(session: Session) -> dict[str, Any]:
    """Recompute the chain; report the first break, and how many rows are not sealed yet.

    Detects an edited row (its hash no longer matches), a removed row or link (a gap in the
    sequence), a re-ordered or forged link (the previous hash does not match) and a row whose
    link was removed while the row stayed (it reads as unsealed, which is reported).
    """

    audit, chain, _anchors = _models()
    anchor = _prune_anchor(session)
    expected_seq, prev = anchor if anchor is not None else (0, GENESIS)
    checked = 0
    problem: dict[str, Any] | None = None
    query = (
        session.query(chain, audit)
        .outerjoin(audit, audit.event_id == chain.event_id)
        .order_by(chain.chain_seq)
    )
    for link, row in query.yield_per(1000):
        expected_seq += 1
        if link.chain_seq != expected_seq:
            problem = {"chain_seq": link.chain_seq, "reason": f"expected {expected_seq}: a gap"}
            break
        if link.prev_hash != prev:
            problem = {"chain_seq": link.chain_seq, "reason": "previous hash does not match"}
            break
        if row is None:
            problem = {"chain_seq": link.chain_seq, "event_id": link.event_id,
                       "reason": "the audit row of this link is missing"}
            break
        if row_digest(prev, row) != link.row_hash:
            problem = {"chain_seq": link.chain_seq, "event_id": link.event_id,
                       "reason": "row content does not match its hash"}
            break
        prev = link.row_hash
        checked += 1
    unsealed = _unsealed(session).with_entities(func.count(audit.event_id)).scalar()
    return {
        "ok": problem is None,
        "rows_verified": checked,
        "head_seq": expected_seq if problem is None else None,
        "head_hash": prev if problem is None else None,
        "unsealed_rows": int(unsealed or 0),
        "first_break": problem,
        "anchored_from_seq": anchor[0] if anchor is not None else 0,
    }


def _signature(seq: int, digest: str) -> str | None:
    key = os.environ.get("EUROGAS_NEXUS_SECRET_KEY", "").strip()
    if not key:
        return None
    message = f"eurogas-nexus-audit-anchor|{seq}|{digest}".encode()
    return "hmac-sha256:" + hmac.new(key.encode(), message, hashlib.sha256).hexdigest()[:64]


def record_anchor(session: Session, *, kind: str, seq: int, digest: str, by: str,
                  detail: str = "") -> Any:
    _audit, _chain, anchors = _models()
    row = anchors(
        anchor_id=f"anchor-{uuid4().hex[:24]}",
        kind=kind,
        chain_seq=seq,
        row_hash=digest,
        signature=_signature(seq, digest),
        created_at_utc=datetime.now(UTC),
        created_by=by[:64],
        detail=detail[:500],
    )
    session.add(row)
    session.flush()
    return row


def checkpoint(session: Session, *, by: str) -> dict[str, Any]:
    """Seal, verify and record a signed digest of the chain head; returns it for export."""

    seal_pending(session)
    result = verify_chain(session)
    if not result["ok"]:
        return {**result, "anchor": None}
    anchor = record_anchor(
        session, kind="checkpoint", seq=result["head_seq"], digest=result["head_hash"], by=by
    )
    return {
        **result,
        "anchor": {
            "anchor_id": anchor.anchor_id,
            "chain_seq": anchor.chain_seq,
            "row_hash": anchor.row_hash,
            "signature": anchor.signature,
            "created_at_utc": _iso(anchor.created_at_utc),
        },
    }


# ------------------------------------------------------------------- forwarding (SIEM)


def _sink() -> str:
    return (os.environ.get(AUDIT_SINK_ENV) or "").strip()


def forward(records: list[dict[str, Any]], sink: str | None = None) -> None:
    """Send sealed rows to the configured sink as JSON lines (best effort, never raises)."""

    target = _sink() if sink is None else sink
    if not target or not records:
        return
    lines = [json.dumps({"type": "eurogas_nexus.audit", **record}, sort_keys=True,
                        default=str) for record in records]
    try:
        if target == "stdout":
            for line in lines:
                print(line, flush=True)
        elif target.startswith("file:"):
            with open(target[len("file:"):], "a", encoding="utf-8") as handle:
                handle.write("\n".join(lines) + "\n")
        elif target.startswith("syslog://"):
            host, _, port = target[len("syslog://"):].partition(":")
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                for line in lines:
                    # RFC 5424: facility 13 (log audit), severity 6 (informational).
                    stamp = datetime.now(UTC).isoformat()
                    message = f"<110>1 {stamp} - eurogas-nexus - audit - {line}"
                    sock.sendto(message.encode("utf-8"), (host, int(port or 514)))
        elif target.startswith("https://"):
            body = ("\n".join(lines) + "\n").encode("utf-8")
            threading.Thread(target=_post, args=(target, body), daemon=True).start()
        else:
            _LOG.warning("unknown %s value; audit rows not forwarded", AUDIT_SINK_ENV)
    except Exception:  # noqa: BLE001 - forwarding never fails the write it reports
        _LOG.exception("audit forwarding failed")


def _post(url: str, body: bytes) -> None:
    request = urllib.request.Request(
        url, data=body, method="POST", headers={"Content-Type": "application/x-ndjson"}
    )
    try:
        with urllib.request.urlopen(request, timeout=5):  # noqa: S310 - https only
            pass
    except Exception:  # noqa: BLE001
        _LOG.exception("audit webhook failed")


# ------------------------------------------------------------------- session events


def _after_flush(session: Session, _context: Any) -> None:
    audit, _chain, _anchors = _models()
    if any(isinstance(obj, audit) for obj in session.new):
        session.info[_PENDING] = True


def _before_commit(session: Session) -> None:
    if not session.info.pop(_PENDING, False):
        return
    session.flush()
    try:
        if session.get_bind().dialect.name == "postgresql":
            # A savepoint keeps the writing transaction usable if the seal fails (a store
            # not yet migrated to 0095): the rows then stay unsealed until the next seal.
            with session.begin_nested():
                rows = seal_pending(session)
        else:
            rows = seal_pending(session)
    except Exception:  # noqa: BLE001 - never lose the audited change over its seal
        _LOG.exception("audit chain seal failed; rows stay unsealed until the next seal")
        return
    if _sink():
        session.info[_SEALED] = [
            {**canonical(row), "chain_seq": link.chain_seq, "row_hash": link.row_hash,
             "prev_hash": link.prev_hash}
            for row, link in rows
        ]


def _after_commit(session: Session) -> None:
    records = session.info.pop(_SEALED, None)
    if records:
        forward(records)


def _after_rollback(session: Session) -> None:
    session.info.pop(_PENDING, None)
    session.info.pop(_SEALED, None)


_INSTALLED = False


def install() -> None:
    """Install the sealing events on every Session (idempotent)."""

    global _INSTALLED
    if _INSTALLED:
        return
    event.listen(Session, "after_flush", _after_flush)
    event.listen(Session, "before_commit", _before_commit)
    event.listen(Session, "after_commit", _after_commit)
    event.listen(Session, "after_soft_rollback", lambda session, _tx: _after_rollback(session))
    _INSTALLED = True
