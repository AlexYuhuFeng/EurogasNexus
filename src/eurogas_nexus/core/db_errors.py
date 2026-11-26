"""What kind of database failure an exception is, without importing the database layer.

The API must not load SQLAlchemy on import (``tests/contract/test_product_boundary.py``), yet
its error handling has to tell a statement the server cancelled (``statement_timeout``) from a
lost connection and from a programming error. These checks read the exception chain by duck
typing: SQLAlchemy keeps the driver's exception in ``.orig``; pg8000 carries the SQLSTATE in
``args[0]["C"]``, psycopg in ``.sqlstate``, psycopg2 in ``.pgcode``.

数据库错误分类（不导入数据库层）：服务器取消的语句（超时）、连接中断、其他。
"""

from __future__ import annotations

from collections.abc import Iterator

#: ``query_canceled``: PostgreSQL cancelled the statement (``statement_timeout``).
STATEMENT_TIMEOUT_SQLSTATE = "57014"
#: ``lock_not_available``: a statement waited longer than ``lock_timeout`` for a lock.
LOCK_TIMEOUT_SQLSTATE = "55P03"
TIMEOUT_SQLSTATES = frozenset({STATEMENT_TIMEOUT_SQLSTATE, LOCK_TIMEOUT_SQLSTATE})
#: The server or the connection went away (class 08, and an administrator or a failover
#: shutting the server down: 57P01 to 57P03).
CONNECTION_SQLSTATES = frozenset(
    {"08000", "08001", "08003", "08004", "08006", "08007", "57P01", "57P02", "57P03"}
)
#: ``read_only_sql_transaction``: a write reached a standby (or a primary being demoted);
#: nothing was applied (db/resilience.py).
READ_ONLY_SQLSTATE = "25006"

#: The product's error code for a statement the database cancelled after its time limit.
DB_TIMEOUT_CODE = "runtime_db_timeout"
#: A connection lost during COMMIT: the write may or may not have been applied
#: (``db/resilience.py`` ``CommitOutcomeUnknown``).
DB_COMMIT_UNCONFIRMED_CODE = "runtime_db_commit_unconfirmed"
#: The text of the failover connect's refusal when no host is a writable primary.
NO_WRITABLE_PRIMARY = "no writable primary"
#: Seconds a client is told to wait before it tries again (``Retry-After``).
DB_RETRY_AFTER_SECONDS = 5


def _chain(exc: BaseException | None) -> Iterator[BaseException]:
    seen: set[int] = set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        yield exc
        orig = getattr(exc, "orig", None)
        if isinstance(orig, BaseException) and id(orig) not in seen:
            yield orig
            seen.add(id(orig))
        exc = exc.__cause__ or exc.__context__


def sqlstate(exc: BaseException | None) -> str | None:
    """The PostgreSQL SQLSTATE anywhere in the exception chain, or None."""

    for item in _chain(exc):
        for attribute in ("sqlstate", "pgcode"):
            value = getattr(item, attribute, None)
            if isinstance(value, str) and value:
                return value
        args = getattr(item, "args", ())
        if args and isinstance(args[0], dict) and isinstance(args[0].get("C"), str):
            return args[0]["C"]
    return None


def is_statement_timeout(exc: BaseException | None) -> bool:
    """The server cancelled a statement after its ``statement_timeout`` or ``lock_timeout``."""

    return sqlstate(exc) in TIMEOUT_SQLSTATES


_DB_MODULES = ("sqlalchemy", "pg8000", "psycopg", "psycopg2")


def _from_database(item: BaseException) -> bool:
    """Raised by the database layer: its class, or a frame it passed through (pg8000 lets a
    socket ``TimeoutError`` out of the connect unwrapped, and SQLAlchemy wraps only DBAPI
    errors)."""

    if (type(item).__module__ or "").startswith(_DB_MODULES):
        return True
    frame = item.__traceback__
    while frame is not None:
        if str(frame.tb_frame.f_globals.get("__name__", "")).startswith(_DB_MODULES):
            return True
        frame = frame.tb_next
    return False


def is_connection_failure(exc: BaseException | None) -> bool:
    """The connection was lost or could not be made (the store is unreachable).

    Only a failure the database layer raised counts: a network error of some other client
    (a provider's HTTP call) is not the store being unavailable.
    """

    chain = list(_chain(exc))
    if not any(_from_database(item) for item in chain):
        return False
    if sqlstate(exc) in CONNECTION_SQLSTATES | {READ_ONLY_SQLSTATE}:
        return True
    for item in chain:
        if getattr(item, "connection_invalidated", False):
            return True
        if (type(item).__module__ or "").startswith("sqlalchemy") and type(item).__name__ in {
            "OperationalError",
            "InterfaceError",
            "DisconnectionError",
            "TimeoutError",  # the pool's own timeout: no connection came back in time
        }:
            return True
        if isinstance(item, (ConnectionError, TimeoutError)):
            return True
    return False


def is_commit_unconfirmed(exc: BaseException | None) -> bool:
    """A connection lost during COMMIT (``db/resilience.py`` ``CommitOutcomeUnknown``)."""

    return any(getattr(item, "code", None) == DB_COMMIT_UNCONFIRMED_CODE for item in _chain(exc))


def database_failure(exc: BaseException | None) -> str | None:
    """``"commit_unconfirmed"``, ``"timeout"``, ``"unavailable"`` or None (not a database
    failure the API answers).

    ``unavailable`` covers an unreachable or lost store, a failover with no writable primary
    and a write refused by a standby (``25006``): in each case nothing was saved and a retry is
    safe. ``commit_unconfirmed`` is the one case where it may have been saved.
    """

    if exc is None:
        return None
    if is_commit_unconfirmed(exc):
        return "commit_unconfirmed"
    if is_statement_timeout(exc):
        return "timeout"
    if is_connection_failure(exc):
        return "unavailable"
    return None


__all__ = [
    "CONNECTION_SQLSTATES",
    "DB_COMMIT_UNCONFIRMED_CODE",
    "DB_RETRY_AFTER_SECONDS",
    "DB_TIMEOUT_CODE",
    "LOCK_TIMEOUT_SQLSTATE",
    "STATEMENT_TIMEOUT_SQLSTATE",
    "NO_WRITABLE_PRIMARY",
    "READ_ONLY_SQLSTATE",
    "database_failure",
    "is_commit_unconfirmed",
    "is_connection_failure",
    "is_statement_timeout",
    "sqlstate",
]
