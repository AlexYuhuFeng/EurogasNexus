"""Freeze the clock one module reads, for tests whose fixtures are seeded relative to "now".

A fixture seeded from ``datetime.now(UTC)`` makes the outcome depend on the calendar day (month
ends, weekends, which month contract still trades). Seed from a stated instant instead and, where
the code under test reads the clock itself, freeze that module's ``datetime`` with
:func:`freeze_module_clock` so the code and the fixture agree on the day.
"""

from __future__ import annotations

from datetime import UTC, datetime


def frozen_datetime(instant: datetime) -> type[datetime]:
    """A ``datetime`` subclass whose ``now`` returns ``instant`` (aware, UTC by default)."""

    fixed = instant if instant.tzinfo else instant.replace(tzinfo=UTC)

    class _FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):  # type: ignore[override]
            return fixed.astimezone(tz) if tz else fixed.replace(tzinfo=None)

        @classmethod
        def utcnow(cls):  # type: ignore[override]
            return fixed.astimezone(UTC).replace(tzinfo=None)

    return _FrozenDatetime


def freeze_module_clock(monkeypatch, module, instant: datetime) -> None:
    """Make ``module.datetime.now()`` return ``instant`` for the rest of the test.

    Only for modules that import the class (``from datetime import datetime``) and do not test
    ``isinstance(x, datetime)`` against it.
    """

    monkeypatch.setattr(module, "datetime", frozen_datetime(instant))
