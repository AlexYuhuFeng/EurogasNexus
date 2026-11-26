"""Dates and timestamps decoded with fromisoformat read the same values pg8000 does."""

from datetime import UTC, date, datetime, timedelta, timezone

import pytest
from pg8000 import converters as pg

from eurogas_nexus.db import pg8000_decoding as fast

TEXTS = [
    "2026-11-25 05:00:00+00",
    "2026-11-25 05:00:00.123456+00",
    "2026-11-25 05:00:00.5+05:30",
    "2026-03-29 01:00:00-04",
    "2026-11-25 05:00:00",
    "2026-11-25 05:00:00.1",
    "2028-02-29 23:59:59.999999+00",
    "infinity",
    "-infinity",
    "0044-03-15 00:00:00+00 BC",
]


@pytest.mark.parametrize("text", TEXTS)
def test_timestamps_read_as_pg8000_reads_them(text):
    pairs = ((fast.timestamptz_in, pg.timestamptz_in), (fast.timestamp_in, pg.timestamp_in))
    for mine, theirs in pairs:
        got, expected = mine(text), theirs(text)
        assert got == expected and type(got) is type(expected)
        if isinstance(got, datetime):
            assert got.utcoffset() == expected.utcoffset()


@pytest.mark.parametrize(
    "text", ["2026-11-25", "2028-02-29", "infinity", "-infinity", "0044-03-15 BC"]
)
def test_dates_read_as_pg8000_reads_them(text):
    assert fast.date_in(text) == pg.date_in(text)


def test_values_are_the_instants_postgres_wrote():
    assert fast.timestamptz_in("2026-11-25 05:00:00+00") == datetime(2026, 11, 25, 5, tzinfo=UTC)
    offset = fast.timestamptz_in("2026-11-25 05:00:00+05:30").utcoffset()
    assert offset == timedelta(hours=5, minutes=30)
    assert fast.date_in("2026-11-25") == date(2026, 11, 25)
    # pg8000 gives up on an offset with seconds (local mean time) and returns the text.
    assert fast.timestamptz_in("1901-01-01 00:00:00-00:01:15").tzinfo == timezone(
        -timedelta(minutes=1, seconds=15)
    )


def test_register_installs_the_converters_on_a_pg8000_connection_only():
    class FakeConnection:
        def __init__(self):
            self.adapters = {}

        def register_in_adapter(self, oid, func):
            self.adapters[oid] = func

    connection = FakeConnection()
    fast.register(connection)
    assert connection.adapters == {
        pg.TIMESTAMPTZ: fast.timestamptz_in,
        pg.TIMESTAMP: fast.timestamp_in,
        pg.DATE: fast.date_in,
    }
    fast.register(object())  # another driver's connection: nothing to do, no error


def test_a_pg8000_engine_registers_the_converters_on_connect():
    from eurogas_nexus.db.session import get_engine

    engine = get_engine("postgresql+pg8000://user:secret@127.0.0.1:1/none")
    listeners = [
        fn for fn in engine.pool.dispatch.connect
        if getattr(fn, "__module__", "") == "eurogas_nexus.db.session"
    ]
    assert len(listeners) == 1

    class FakeConnection:
        adapters: dict = {}

        def register_in_adapter(self, oid, func):
            self.adapters[oid] = func

    connection = FakeConnection()
    for listener in listeners:
        listener(connection, None)
    assert connection.adapters.get(pg.TIMESTAMPTZ) is fast.timestamptz_in
