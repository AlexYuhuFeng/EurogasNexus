"""Faster decoding of PostgreSQL dates and timestamps on pg8000 connections.

pg8000 decodes every ``timestamp``, ``timestamptz`` and ``date`` value with
``datetime.strptime``, which costs some 17 µs a value: a read of 60,000 observation rows
spent about a second on it alone (the forward balance, the NW Europe balance, storage).
``datetime.fromisoformat`` reads PostgreSQL's text form (``2026-11-25 05:00:00+00``) in
well under a microsecond and returns the same value. Anything it does not read (``infinity``,
a BC date, a year past 9999) goes to pg8000's own converter, unchanged. The one difference:
an offset with seconds (local mean time before 1901), which pg8000 returns as text, is read
as the datetime it is.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pg8000 import converters as _pg

DATE_OID = _pg.DATE
TIMESTAMP_OID = _pg.TIMESTAMP
TIMESTAMPTZ_OID = _pg.TIMESTAMPTZ


def timestamptz_in(data: str) -> Any:
    try:
        return datetime.fromisoformat(data)
    except ValueError:
        return _pg.timestamptz_in(data)


def timestamp_in(data: str) -> Any:
    try:
        return datetime.fromisoformat(data)
    except ValueError:
        return _pg.timestamp_in(data)


def date_in(data: str) -> Any:
    try:
        return date.fromisoformat(data)
    except ValueError:
        return _pg.date_in(data)


def register(dbapi_connection: Any) -> None:
    """Install the converters on one pg8000 connection (a SQLAlchemy ``connect`` listener)."""

    register_in = getattr(dbapi_connection, "register_in_adapter", None)
    if register_in is None:  # not a pg8000 connection
        return
    register_in(TIMESTAMPTZ_OID, timestamptz_in)
    register_in(TIMESTAMP_OID, timestamp_in)
    register_in(DATE_OID, date_in)
