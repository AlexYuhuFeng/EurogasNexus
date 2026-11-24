"""Which licensed source families one request read (GOV-1, lesson P6). Import-safe, no I/O.

The entitlement checks note a licensed family each time they let a principal read it; the
API opens one meter per request (``api/middleware/licensed_use.py``) and, when the request
ends, records one aggregated usage row per family (``application/licensed_use.py``). Outside
a request (a worker, a script, a test) nothing is open and noting does nothing.

The same meter tells a file export which licensed families the rows it writes came from,
so the export decision follows the data actually read, not a declaration.

许可数据使用计量：每个请求记录其读取的许可数据源族（聚合入库，不逐请求写行）。
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field


@dataclass
class LicensedUseMeter:
    """The licensed families one request read, and whether it wrote them to a file."""

    families: set[str] = field(default_factory=set)
    #: ``csv``, ``xlsx`` or ``pdf`` when the request wrote its rows to a file.
    export_format: str | None = None


_current: ContextVar[LicensedUseMeter | None] = ContextVar("licensed_use_meter", default=None)


def note_licensed_read(family: str) -> None:
    """Note that a licensed family was read in the current request (no-op outside one)."""

    meter = _current.get()
    if meter is not None and family:
        meter.families.add(family)


def current_meter() -> LicensedUseMeter | None:
    return _current.get()


@contextmanager
def metering() -> Iterator[LicensedUseMeter]:
    """Open a meter for one unit of work; nested opens share the outer meter."""

    outer = _current.get()
    if outer is not None:
        yield outer
        return
    meter = LicensedUseMeter()
    token = _current.set(meter)
    try:
        yield meter
    finally:
        _current.reset(token)


@contextmanager
def not_metered() -> Iterator[None]:
    """Checks made only to list or gate sources (not to read them) are not usage."""

    token = _current.set(None)
    try:
        yield
    finally:
        _current.reset(token)


__all__ = ["LicensedUseMeter", "current_meter", "metering", "not_metered", "note_licensed_read"]
