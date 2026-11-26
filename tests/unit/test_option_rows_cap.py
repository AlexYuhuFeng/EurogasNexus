"""A settlement read past the cap is refused, never silently cut to a subset."""

from __future__ import annotations

from datetime import date

import pytest

from eurogas_nexus.application import option_surface


class _Query:
    def __init__(self, count: int) -> None:
        self.count = count
        self.limit_seen: int | None = None

    def filter(self, *_args):
        return self

    def limit(self, value: int):
        self.limit_seen = value
        return self

    def all(self):
        return [object()] * min(self.count, self.limit_seen or self.count)


class _Session:
    def __init__(self, query: _Query) -> None:
        self._query = query

    def query(self, *_args):
        return self._query


def test_a_read_past_the_cap_is_refused(monkeypatch) -> None:
    monkeypatch.setattr(option_surface, "MAX_ROWS", 3)
    query = _Query(count=10)
    with pytest.raises(option_surface.OptionHistoryTooLarge):
        option_surface.option_rows(
            _Session(query), hubs=["TTF"], first=date(2026, 1, 1), last=date(2026, 2, 1)
        )
    assert query.limit_seen == 4
