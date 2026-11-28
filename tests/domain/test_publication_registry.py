"""Package G: the watched-publication registry and the ENTSOG auction calendar parser.

No network: the calendar is a workbook written by ``tests/fixtures/publication_seed``.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from eurogas_nexus.domain.publications.entsog_cam_calendar import (
    CalendarUncertain,
    calendar_link,
    parse_calendar,
)
from eurogas_nexus.domain.publications.registry import (
    CONSENTED,
    FETCH,
    HAND_MAINTAINED,
    HUBS,
    KINDS,
    TERMS_SECTION,
    VERDICTS,
    WATCHED_PUBLICATIONS,
    WatchedPublication,
    fetch_refusal,
)
from eurogas_nexus.domain.publications.xlsx import SpreadsheetError, clock_time, excel_day
from tests.fixtures.publication_seed import FILE_2526, FILE_2627, calendar_xlsx, page_html

ROOT = Path(__file__).resolve().parents[2]
TERMS = (ROOT / "docs" / "legal" / "DATA_SOURCE_TERMS.md").read_text(encoding="utf-8")


def test_every_publication_has_its_finding_in_the_legal_register():
    """No entry, no fetch: every id is in the register's dated section, with its verdict."""

    assert f"## {TERMS_SECTION}" in TERMS
    section = TERMS.split(f"## {TERMS_SECTION}", 1)[1].split("\n## ", 1)[0]
    ids = [item.publication_id for item in WATCHED_PUBLICATIONS]
    assert len(ids) == len(set(ids))
    for item in WATCHED_PUBLICATIONS:
        assert f"`{item.publication_id}`" in section, item.publication_id
        assert item.verdict in VERDICTS and item.kind in KINDS
        assert set(item.hubs) <= set(HUBS)
        assert item.url.startswith("https://") and item.terms_url.startswith("https://")
        assert item.terms_quote


def test_only_publications_whose_terms_or_a_written_consent_allow_storing_are_fetched():
    fetched = [item for item in WATCHED_PUBLICATIONS if fetch_refusal(item) is None]
    # Allowed by the terms themselves: ENTSOG's calendar only.
    assert [i.publication_id for i in fetched if i.verdict == FETCH] == [
        "entsog-cam-auction-calendar"]
    # Everything else fetched rests on a publisher's written consent (owner, 2026-11-28).
    assert all(i.verdict == CONSENTED and i.consent_publisher for i in fetched
               if i.verdict != FETCH)
    assert all(i.consent_publisher == "eex" for i in fetched if "eex.com" in i.url)
    # The exchange calendars are fetched now; the hand file stays as their fallback.
    hand = {item.hand_venue for item in WATCHED_PUBLICATIONS if item.hand_venue}
    assert hand == {"EEX", "ICE_ENDEX", "ICE_FUTURES_EUROPE"}
    assert not [item for item in WATCHED_PUBLICATIONS if item.verdict == HAND_MAINTAINED]


def test_a_publication_without_a_register_entry_is_refused_even_when_marked_fetch():
    item = WatchedPublication(
        publication_id="x", title="x", publisher="x", kind="capacity_auctions", hubs=(),
        url="https://example.org/", document_format="xlsx", verdict=FETCH, terms_section="",
        terms_quote="", terms_url="https://example.org/", verified_live=False,
        interval_minutes=1440, parser="entsog_cam_calendar",
    )
    assert "legal register" in fetch_refusal(item)


def test_the_hand_calendar_names_each_publishers_page_and_a_check_day():
    from eurogas_nexus.domain.deals.position import load_trading_calendar

    calendar = load_trading_calendar()
    venues = {venue.code: venue for venue in calendar.venues}
    for item in WATCHED_PUBLICATIONS:
        if item.hand_venue:
            venue = venues[item.hand_venue]
            assert venue.check_url == item.url and venue.check_by is not None
    # UK natural gas closes on UK bank holidays; ICE Endex on Easter Monday.
    assert date(2026, 5, 4) in venues["ICE_FUTURES_EUROPE"].closed
    assert date(2027, 3, 29) in venues["ICE_ENDEX"].closed
    assert calendar.is_trading_day(date(2026, 5, 4))  # EEX and ICE Endex trade


def test_the_calendar_link_is_the_newest_calendar_file_on_entsogs_host():
    html = page_html(FILE_2526, FILE_2627, "https://elsewhere.example/Auction%20Calendar%202030-2031.xlsx",
                     "/sites/default/files/other.xlsx").decode()
    assert calendar_link(html) == (FILE_2627, 2026)
    with pytest.raises(CalendarUncertain):
        calendar_link("<html>no calendar here</html>")


def test_the_calendar_is_read_into_dated_auctions():
    calendar = parse_calendar(calendar_xlsx())
    assert (calendar.document_id, calendar.status) == ("MAR0369-25", "Final")
    assert calendar.published_on == date(2025, 11, 12)
    assert (calendar.first_year, calendar.last_year) == (2026, 2027)
    yearly = [a for a in calendar.auctions if a.product == "ANNUAL" and a.capacity == "firm"]
    assert yearly[0].opens_at_utc == datetime(2026, 7, 6, 7, 0, tzinfo=UTC)
    assert (yearly[0].offers_from, yearly[0].offers_to) == (date(2026, 10, 1), date(2028, 9, 30))
    assert yearly[0].offer_levels_published_on == date(2026, 6, 6)
    monthly = [a for a in calendar.auctions if a.product == "MONTHLY"]
    assert len(monthly) == 10 and monthly[0].offers_from == date(2026, 4, 1)
    assert monthly[0].offers_to == date(2026, 4, 30) and monthly[0].key == "firm:monthly:2026-04-01"
    assert any(a.capacity == "interruptible" for a in calendar.auctions)
    assert calendar.standing_rules and "within-day" in calendar.standing_rules[0]


@pytest.mark.parametrize(
    "changes",
    [{"drop_sheet": "Monthly"}, {"rename_header": True}],
)
def test_a_changed_layout_is_not_guessed(changes):
    with pytest.raises(CalendarUncertain):
        parse_calendar(calendar_xlsx(**changes))


def test_not_a_spreadsheet_is_uncertain_and_cell_values_are_strict():
    with pytest.raises(CalendarUncertain):
        parse_calendar(b"%PDF-1.4 not a workbook")
    assert excel_day("46209") == date(2026, 7, 6)
    assert clock_time("7:00") == (7, 0) and clock_time("0.6875") == (16, 30)
    with pytest.raises(SpreadsheetError):
        excel_day("12")
