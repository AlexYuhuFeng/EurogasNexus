"""The Prometheus exposition must contain numbers, not Python `repr` strings.

Why this test exists
--------------------
`prometheus_metrics` emitted

    eurogas_db_pool_checked_out <bound method QueuePool.checkedout of <QueuePool ...>>

because `SQLAlchemy`'s `checkedout` is a method and the code read it with
`getattr(pool, "checkedout", 0) or 0`. A bound method is truthy, so the `or` fallback
never applied and the `repr` went straight into the exposition text.

This is worth a test rather than a one-line fix: Prometheus rejects the whole scrape
when any sample value is not a number, so a single bad line loses every metric in the
family — and a scrape failure is silent to the application, which is why the defect
survived until an operator read the output by hand.

The assertions parse the exposition the way a scraper does, so "looks fine in the
terminal" is not enough to pass.
"""

from __future__ import annotations

import re

import pytest

from eurogas_nexus.application.dataops_observability import prometheus_metrics

#: A sample line: `name` optionally followed by `{labels}`, then a numeric value.
_SAMPLE = re.compile(r"^(?P<name>[a-zA-Z_:][a-zA-Z0-9_:]*)(?:\{[^}]*\})?\s+(?P<value>\S+)$")

#: Prometheus accepts these as sample values.
_NUMERIC = re.compile(
    r"^[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?$|^[+-]?Inf$|^NaN$"
)


class _StubQuery:
    """Mimics the part of `Session.query` this function uses: `.all()`."""

    def all(self) -> list:
        return []


class _StubPool:
    """A pool whose `checkedout` is a method, like SQLAlchemy's `QueuePool`.

    Reproducing that shape is the point: the defect was reading it as an attribute.
    """

    def __init__(self) -> None:
        self._max_overflow = 20

    def checkedout(self) -> int:
        return 0

    @property
    def size(self) -> int:
        return 5


class _StubSession:
    """A session that needs no database, so the test measures rendering only.

    The earlier version of this fixture used a real in-memory SQLite session and failed
    with "no such table: source_runtime_states": the function queries two tables, and a
    bare engine has no schema. The subject here is the exposition text, not the query, so
    the schema is stubbed out rather than migrated.
    """

    def __init__(self) -> None:
        self._bind = type("_Bind", (), {"pool": _StubPool()})()

    def get_bind(self):
        return self._bind

    def query(self, *_args, **_kwargs) -> _StubQuery:
        return _StubQuery()


@pytest.fixture()
def exposition() -> str:
    """Render the metric family without a database."""

    return prometheus_metrics(_StubSession())


def _sample_lines(text: str) -> list[tuple[str, str]]:
    samples = []
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        match = _SAMPLE.match(line.strip())
        if match:
            samples.append((match.group("name"), match.group("value")))
    return samples


def test_every_sample_value_is_numeric(exposition: str) -> None:
    """A single non-numeric value makes the whole scrape fail."""

    samples = _sample_lines(exposition)
    assert samples, "the exposition contained no sample lines at all"

    offending = [
        (name, value) for name, value in samples if not _NUMERIC.match(value)
    ]
    assert not offending, (
        "these samples are not numeric, so a Prometheus scrape of this endpoint would "
        f"be rejected outright: {offending}"
    )


def test_no_sample_carries_a_python_repr(exposition: str) -> None:
    """The specific shape that failed: a bound method or object representation."""

    for name, value in _sample_lines(exposition):
        for marker in ("<bound method", "<function", "object at 0x", "<class "):
            assert marker not in value, (
                f"sample {name!r} carries a Python representation {value!r} "
                f"(contains {marker!r}); it must be a number"
            )


def test_the_pool_metrics_are_present_and_numeric(exposition: str) -> None:
    """The three pool gauges specifically, since one of them was the defect."""

    rendered = dict(_sample_lines(exposition))
    for name in (
        "eurogas_db_pool_checked_out",
        "eurogas_db_pool_size",
        "eurogas_db_pool_overflow",
    ):
        assert name in rendered, f"{name} is missing from the exposition"
        assert _NUMERIC.match(rendered[name]), (
            f"{name} rendered {rendered[name]!r}, which is not a number"
        )


def test_checked_out_is_read_as_a_callable_not_as_a_method_object(exposition: str) -> None:
    """`checkedout` is a method on SQLAlchemy's QueuePool; it must be called.

    With an idle pool the honest value is 0. The failure mode being guarded against
    reported the method object instead, which is neither 0 nor any other number.
    """

    rendered = dict(_sample_lines(exposition))
    value = rendered["eurogas_db_pool_checked_out"]
    assert value == "0", (
        "an idle pool should report 0 checked-out connections, but the exposition "
        f"says {value!r}"
    )
