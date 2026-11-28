"""Part C: LNG operators' slot and auction announcements, fetched under their consent, become
capacity notices the regas auction desk opens a case from (window, slot days, terminal, size).

Every document is written for the tests in the operator's layout with invented values; no
network.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from sqlalchemy.orm import Session

from eurogas_nexus.application.publication_watch import calendar_items, check_publication
from eurogas_nexus.application.publisher_consents import withdraw_consent
from eurogas_nexus.application.regas_auction import choices
from eurogas_nexus.db.models import CapacityNoticeRecord
from eurogas_nexus.domain.publications import operator_notices as operators
from eurogas_nexus.domain.publications.registry import watched_publication
from tests.fixtures import consented_seed as seed
from tests.fixtures.news_seed import store

NOW = datetime(2027, 1, 10, 9, tzinfo=UTC)
NO_PAUSE = lambda _seconds: None  # noqa: E731


@pytest.fixture()
def session(tmp_path):
    _url, engine = store(tmp_path, "slots.sqlite")
    with Session(engine) as s:
        yield s


def test_a_fluxys_slot_sale_is_read_with_its_auction_time_and_size():
    offers = operators.parse_fluxys_slot_news(seed.fluxys_news(), seed.FLUXYS_NEWS)
    first, second = offers
    assert (first.terminal_id, first.hub, first.quantity, first.quantity_unit) == (
        "zeebrugge", "ZTP", 99000.0, "m3_lng")
    assert first.offers_from == date(2027, 3, 3) and first.offers_to == date(2027, 3, 9)
    assert first.opens_at_utc == datetime(2027, 1, 14, 10, tzinfo=UTC)  # 11:00 CET
    assert second.opens_at_utc == first.opens_at_utc  # "after the previous auction" that day
    assert "HT902" in second.title and "Belgian time" in second.title
    assert operators.parse_fluxys_slot_news(seed.fluxys_news(), seed.FLUXYS_NEWS,
                                            terminal="dunkerque") == ()
    dunkirk = operators.parse_fluxys_slot_news(seed.fluxys_news(terminal="Dunkirk"), "u")
    assert dunkirk[0].terminal_id == "dunkerque-lng"
    with pytest.raises(operators.NoticesUncertain):
        operators.parse_fluxys_slot_news(b"<html>Zeebrugge LNG Terminal, nothing else</html>",
                                         "u")
    assert operators.fluxys_slot_news_links(seed.fluxys_market_page(seed.FLUXYS_NEWS),
                                            seed.FLUXYS_MARKET) == [seed.FLUXYS_NEWS]


def test_the_grain_board_and_det_status_are_read_and_a_changed_page_is_not_guessed():
    grain = operators.parse_grain_bulletin(seed.grain_board("4th February 2027"),
                                           seed.GRAIN_PAGE, seen_on=date(2027, 1, 10))
    assert grain[0].offers_from == date(2027, 2, 4) and grain[0].window_basis == "seen"
    assert operators.parse_grain_bulletin(seed.grain_board(), "u", seen_on=date(2027, 1, 10)) \
        == ()
    with pytest.raises(operators.NoticesUncertain):
        operators.parse_grain_bulletin(seed.grain_board("1st May 2027", heading=False), "u",
                                       seen_on=date(2027, 1, 10))
    det = operators.parse_det_trader_information(seed.det_page(), seed.DET_PAGE,
                                                 seen_on=date(2027, 1, 1))
    assert [o.terminal_id for o in det] == ["wilhelmshaven:fsru-1"]
    assert det[0].offers_from == date(2028, 1, 1)
    assert det[0].opens_at_utc == datetime(2027, 1, 4, 23, tzinfo=UTC)  # 5 Jan, Berlin
    with pytest.raises(operators.NoticesUncertain):
        operators.parse_det_trader_information(b"<html>moved</html>", "u",
                                               seen_on=date(2027, 1, 1))


def test_a_fetched_slot_offer_opens_a_regas_case_with_its_window_and_terminal(session):
    fetch = seed.ConsentedFetcher({seed.FLUXYS_MARKET: seed.fluxys_market_page(seed.FLUXYS_NEWS),
                                   seed.FLUXYS_NEWS: seed.fluxys_news()})
    item = watched_publication("fluxys-lng-zeebrugge-slots")
    outcome = check_publication(session, item, fetch=fetch, now=NOW, pause=NO_PAUSE)
    assert outcome.status == "first_read" and outcome.applied["created"] == 2
    assert fetch.urls() == ["https://www.fluxys.com/robots.txt", seed.FLUXYS_MARKET,
                            seed.FLUXYS_NEWS]
    notice = session.get(CapacityNoticeRecord,
                         "fluxys-lng-zeebrugge-slots:zeebrugge:ht901:2027-03-03")
    assert (notice.kind, notice.facility_id, notice.quantity_unit) == (
        "lng_slot", "zeebrugge", "m3_lng")
    offered = {n["notice_key"]: n for n in choices(session)["notices"]}
    picked = offered["fluxys-lng-zeebrugge-slots:zeebrugge:ht901:2027-03-03"]
    assert picked["facility_id"] == "zeebrugge" and picked["offers_from"] == "2027-03-03"
    assert picked["publisher_name"] == "Fluxys LNG"
    items = [i for i in calendar_items(session, now=NOW, days=30) if i["kind"] == "slot_offer"]
    assert len(items) == 2 and items[0]["source"]["consent"].startswith("fetched under")
    # A withdrawn consent: no case is opened from its offers, and the calendar drops them.
    withdraw_consent(session, "fluxys", principal="admin", now=NOW)
    assert not [n for n in choices(session)["notices"]
                if n["publisher_id"] == "fluxys-lng-zeebrugge-slots"]
    assert not [i for i in calendar_items(session, now=NOW, days=30) if i["kind"] == "slot_offer"]


def test_a_slot_no_longer_on_the_grain_board_is_withdrawn(session):
    item = watched_publication("grain-lng-uioli-board")
    first = seed.ConsentedFetcher({seed.GRAIN_PAGE: seed.grain_board("4th February 2027",
                                                                     "5th February 2027")})
    check_publication(session, item, fetch=first, now=NOW, pause=NO_PAUSE)
    later = seed.ConsentedFetcher({seed.GRAIN_PAGE: seed.grain_board("5th February 2027")})
    outcome = check_publication(session, item, fetch=later,
                                now=datetime(2027, 1, 11, 9, tzinfo=UTC), pause=NO_PAUSE)
    assert outcome.applied["withdrawn"] == 1
    gone = session.get(CapacityNoticeRecord, "grain-lng-uioli-board:grain-lng:berth:2027-02-04")
    kept = session.get(CapacityNoticeRecord, "grain-lng-uioli-board:grain-lng:berth:2027-02-05")
    assert gone.state == "cancelled" and kept.state == "open"
    # The day it was first seen stays its opening.
    assert kept.opens_at_utc.replace(tzinfo=UTC) == datetime(2027, 1, 10, tzinfo=UTC)
