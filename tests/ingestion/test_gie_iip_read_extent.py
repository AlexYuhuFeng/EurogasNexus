"""An interrupted IIP read states how far back it read (backend audit I2)."""

from __future__ import annotations

from datetime import UTC, datetime

from eurogas_nexus.ingestion.gie_iip import IipError, fetch_iip_messages


def test_an_interrupted_read_reports_its_oldest_submission() -> None:
    pages = {
        1: {"data": [{"submitted": "2026-11-26T10:00:00"}, {"submitted": "2026-11-20T09:00:00"}],
            "meta": {"last_page": 9}},
        2: {"data": [{"submitted": "2026-11-15T07:30:00"}], "meta": {"last_page": 9}},
    }

    def get_page(page):
        if page in pages:
            return pages[page]
        raise IipError("iip_upstream_refused", "upstream 429")

    read = fetch_iip_messages(get_page, since=datetime(2026, 10, 27, tzinfo=UTC), max_pages=9,
                              sleep=lambda _s: None)
    assert read.error == "iip_upstream_refused"
    assert read.oldest_submitted == datetime(2026, 11, 15, 7, 30, tzinfo=UTC)
