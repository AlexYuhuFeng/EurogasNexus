"""A read with a memory bound that says so when the bound is reached (backend audit A4).

Calculation inputs were read with ``.limit(N).all()`` as a memory guard: past the bound
the rows silently stopped, and the result was computed on part of its inputs. Worse, some
of those reads were unordered (an arbitrary part) or ascending (the newest rows - the
marks that matter - were the ones dropped). ``read_bounded`` reads one row past the bound
and refuses with :class:`ReadBoundExceeded` when it is there, so the caller narrows the
window instead of trusting a partial answer. The API answers it as 422
``read_bound_exceeded`` with ``params`` ``{"what", "bound"}``.
"""

from __future__ import annotations

from typing import Any


class ReadBoundExceeded(RuntimeError):
    """More rows matched than a calculation reads in one go."""

    code = "read_bound_exceeded"

    def __init__(self, what: str, bound: int) -> None:
        self.what = what
        self.bound = bound
        super().__init__(
            f"More than {bound:,} {what} rows match; narrow the window or the selection."
        )


def read_bounded(query: Any, bound: int, *, what: str) -> list[Any]:
    """All rows of ``query`` if there are at most ``bound``; else :class:`ReadBoundExceeded`."""

    rows = query.limit(bound + 1).all()
    if len(rows) > bound:
        raise ReadBoundExceeded(what, bound)
    return rows
