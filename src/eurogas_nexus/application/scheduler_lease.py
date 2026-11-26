"""One active scheduler per database: a PostgreSQL advisory lock, and a liveness heartbeat.

Two scheduler processes against one database (a second job server, a restarted container
whose old process lingers, an operator's manual run) would both claim and ingest. The
claims are row-locked, so one run is not executed twice, but both processes would scan,
retry and recover runs, and their heartbeats would overwrite each other. The lock makes
the second process a standby: it holds no claims and writes nothing until the active one
stops, then takes over within one interval.

The lock is PostgreSQL's session-level advisory lock (``pg_try_advisory_lock``) on a
connection the scheduler keeps open for as long as it is active. No table is needed and
the lock cannot outlive its holder: when the process dies or its connection drops,
PostgreSQL releases it. On SQLite (development and tests) there is one process by
construction and the lease is a no-op.

While active, a background thread touches the heartbeat row every
``HEARTBEAT_INTERVAL_SECONDS``, so the heartbeat measures "the active scheduler is alive"
even during a long ingestion (an ENTSOG tariff read takes many minutes, and the scan-time
heartbeat alone went silent then). The same thread checks the lock connection; if it is
lost, the scheduler stops claiming and tries to take the lock again.
"""

from __future__ import annotations

import hashlib
import logging
import os
import socket
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

_LOG = logging.getLogger("eurogas_nexus.scheduler")

#: Seconds between liveness heartbeats of the active scheduler.
HEARTBEAT_INTERVAL_SECONDS = 30.0


def advisory_key(name: str) -> int:
    """A stable signed 64-bit key for ``pg_try_advisory_lock`` (from the lock's name)."""

    digest = hashlib.sha256(f"eurogas-nexus:{name}".encode()).digest()
    return int.from_bytes(digest[:8], "big", signed=True)


def holder_label() -> str:
    """Who holds the lease, for logs: host and process id (no user data)."""

    return f"{socket.gethostname()}:{os.getpid()}"


class NoopLease:
    """Single-process databases (SQLite): always active, nothing to keep."""

    postgresql = False

    def __init__(self) -> None:
        self.held = False
        self.lost = threading.Event()

    def acquire(self) -> bool:
        self.held = True
        return True

    def check(self) -> bool:
        return True

    def release(self) -> None:
        self.held = False


class AdvisoryLease:
    """A session-level PostgreSQL advisory lock on a dedicated connection."""

    postgresql = True

    def __init__(self, engine: Any, name: str = "dataops-scheduler") -> None:
        self.engine = engine
        self.name = name
        self.key = advisory_key(name)
        self.held = False
        self.lost = threading.Event()
        self._connection: Any = None
        self._lock = threading.Lock()

    def acquire(self) -> bool:
        from sqlalchemy import text

        with self._lock:
            if self.held:
                return True
            connection = None
            try:
                # Autocommit: the connection must never sit idle inside a transaction (an
                # idle-in-transaction timeout would end it and drop the lock with it).
                connection = self.engine.connect().execution_options(
                    isolation_level="AUTOCOMMIT"
                )
                got = bool(
                    connection.execute(
                        text("SELECT pg_try_advisory_lock(:key)"), {"key": self.key}
                    ).scalar()
                )
            except Exception:  # noqa: BLE001 - database away: not active, retry later
                if connection is not None:
                    _close_quietly(connection)
                return False
            if not got:
                _close_quietly(connection)
                return False
            self._connection = connection
            self.held = True
            self.lost.clear()
            return True

    def check(self) -> bool:
        """True while the lock connection is alive and still holds the lock."""

        from sqlalchemy import text

        with self._lock:
            if not self.held or self._connection is None:
                return False
            try:
                still = bool(
                    self._connection.execute(
                        text(
                            "SELECT EXISTS (SELECT 1 FROM pg_locks WHERE locktype = 'advisory' "
                            "AND pid = pg_backend_pid() AND granted AND objsubid = 1 "
                            "AND ((classid::bigint << 32) | objid::bigint) = :key)"
                        ),
                        {"key": self.key},
                    ).scalar()
                )
            except Exception:  # noqa: BLE001
                still = False
            if not still:
                self.held = False
                _close_quietly(self._connection)
                self._connection = None
                self.lost.set()
            return still

    def release(self) -> None:
        from sqlalchemy import text

        with self._lock:
            if self._connection is not None:
                try:
                    self._connection.execute(
                        text("SELECT pg_advisory_unlock(:key)"), {"key": self.key}
                    )
                except Exception:  # noqa: BLE001 - closing the connection releases it anyway
                    pass
                _close_quietly(self._connection)
            self._connection = None
            self.held = False


def _close_quietly(connection: Any) -> None:
    try:
        connection.close()
    except Exception:  # noqa: BLE001
        pass


def lease_for(session_factory: Any, name: str = "dataops-scheduler") -> NoopLease | AdvisoryLease:
    """The advisory lease on PostgreSQL, the no-op lease otherwise (or for a test double)."""

    keywords = getattr(session_factory, "kw", None)
    engine = keywords.get("bind") if isinstance(keywords, dict) else None
    dialect = getattr(getattr(engine, "dialect", None), "name", "")
    if dialect == "postgresql":
        return AdvisoryLease(engine, name)
    return NoopLease()


def touch_heartbeat(session_factory: Any, *, now_utc: datetime | None = None) -> None:
    """Mark the active data-operations scheduler alive (the scan counts are left as they are)."""

    from eurogas_nexus.db.models import DataOperationsHeartbeatRecord

    now = now_utc or datetime.now(UTC)
    with session_factory() as session:
        row = session.get(DataOperationsHeartbeatRecord, "primary")
        if row is None:
            row = DataOperationsHeartbeatRecord(heartbeat_id="primary")
            session.add(row)
        row.last_heartbeat_at_utc = now
        session.commit()


class HeartbeatKeeper:
    """Background thread: check the lease and touch the heartbeat while active."""

    def __init__(
        self,
        lease: NoopLease | AdvisoryLease,
        beat: Callable[[], None],
        *,
        interval_seconds: float = HEARTBEAT_INTERVAL_SECONDS,
    ) -> None:
        self.lease = lease
        self.beat = beat
        self.interval_seconds = interval_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="scheduler-heartbeat", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self.interval_seconds + 5)
        self._thread = None

    def _run(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            if not self.lease.check():
                _LOG.error(
                    "scheduler lock lost; this process stops claiming work",
                    extra={"event": "scheduler.lock.lost"},
                )
                return
            try:
                self.beat()
            except Exception:  # noqa: BLE001 - a missed beat shows as heartbeat age
                _LOG.warning(
                    "scheduler heartbeat write failed",
                    extra={"event": "scheduler.heartbeat.failed"},
                )


__all__ = [
    "HEARTBEAT_INTERVAL_SECONDS",
    "AdvisoryLease",
    "HeartbeatKeeper",
    "NoopLease",
    "advisory_key",
    "holder_label",
    "lease_for",
    "touch_heartbeat",
]
