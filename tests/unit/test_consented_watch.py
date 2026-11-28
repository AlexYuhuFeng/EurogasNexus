"""Publications fetched under the publishers' written consents (owner, 2026-11-28).

The watch reads the consented price and calendar publications politely (robots.txt, its own
client name, documented APIs, conditional requests, one request at a time, back-off), stores
what they publish where the board, the chart and My gas day read it, and stops at once when an
administrator withdraws a consent. Every fetch goes through an in-memory fetcher with documents
written for the tests; nothing here touches the network.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from eurogas_nexus.application.public_prices import published_cash_out
from eurogas_nexus.application.publication_watch import (
    PUBLICATION_USER_AGENT,
    calendar_items,
    check_publication,
    effective_trading_calendar,
    source_status,
)
from eurogas_nexus.application.publisher_consents import (
    consent_status,
    restore_consent,
    withdraw_consent,
)
from eurogas_nexus.db.models import (
    AuditEventRecord,
    MarketObservationRecord,
    MarketQuoteRecord,
    WatchedPublicationRecord,
)
from eurogas_nexus.domain.publications.registry import watched_publication
from tests.fixtures import consented_seed as seed
from tests.fixtures.news_seed import store

NOW = datetime(2026, 3, 3, 10, 0, tzinfo=UTC)
NO_PAUSE = lambda _seconds: None  # noqa: E731 - the tests do not wait between requests

THE = watched_publication("the-imbalance-prices")
NG = watched_publication("national-gas-smp")
MIBGAS = watched_publication("mibgas-prices")
EEX_NGP = watched_publication("eex-ngp")


@pytest.fixture()
def session(tmp_path):
    _url, engine = store(tmp_path, "consented.sqlite")
    with Session(engine) as s:
        yield s


def _the_fetcher(days=None):
    days = days or [(date(2026, 3, 1), 30.5, 29.9, 31.1), (date(2026, 3, 2), 31.0, 30.4, 31.6)]
    return seed.ConsentedFetcher({seed.THE_API: seed.the_xml(days)},
                                 robots={"api.tradinghub.eu": (401, b"")})


def test_the_first_read_fetches_the_history_once_and_then_only_the_last_days(session):
    fetch = _the_fetcher()
    outcome = check_publication(session, THE, fetch=fetch, now=NOW, pause=NO_PAUSE)
    assert outcome.status == "first_read"
    assert fetch.urls() == ["https://api.tradinghub.eu/robots.txt",
                            f"{seed.THE_API}?startDate=2021-10-01&endDate=2026-03-03"]
    # Within the interval (six hours) nothing is read again; after it, the last seven days.
    assert check_publication(session, THE, fetch=fetch, now=NOW + timedelta(hours=1),
                             pause=NO_PAUSE).status == "skipped"
    again = _the_fetcher([(date(2026, 3, 2), 31.2, 30.4, 31.6)])
    check_publication(session, THE, fetch=again, now=NOW + timedelta(hours=7), pause=NO_PAUSE)
    assert again.urls()[-1] == f"{seed.THE_API}?startDate=2026-02-24&endDate=2026-03-03"
    rows = session.query(MarketObservationRecord).filter_by(source_system="THE").all()
    assert {r.product for r in rows} == {"THE within-day", "THE imbalance-short",
                                         "THE imbalance-long"}
    revised = next(r for r in rows if r.product == "THE within-day"
                   and r.metadata_json["price_day"] == "2026-03-02")
    assert revised.price == 31.2 and revised.metadata_json["revised_from"] == 31.0
    assert revised.metadata_json["status"] == "preliminary"


def test_the_board_gets_one_dated_quote_per_series_never_a_bid_or_offer(session):
    check_publication(session, THE, fetch=_the_fetcher(), now=NOW, pause=NO_PAUSE)
    quote = session.get(MarketQuoteRecord, "pub:the:vtp-daily-average")
    assert (quote.hub, quote.product, quote.last_price) == ("THE", "within-day", 31.0)
    assert quote.bid_price is None and quote.ask_price is None and quote.simulated is False
    meta = quote.metadata_json
    assert meta["public_price"] and not meta["live"]
    assert (meta["price_day"], meta["price_kind"], meta["consent_publisher"]) == (
        "2026-03-02", "reference_index", "trading-hub-europe")
    assert quote.prior_settlement_price == 30.5 and meta["previous_day"] == "2026-03-01"
    # Imbalance prices price no board row.
    assert session.get(MarketQuoteRecord, "pub:the:imbalance-negative") is None


def test_national_gas_is_read_through_its_documented_api_in_bounded_windows(session):
    body = seed.ng_json([(date(2026, 3, 1), "2.5", "2.6", "2.4")])
    fetch = seed.ConsentedFetcher({seed.NG_API: body})
    assert check_publication(session, NG, fetch=fetch, now=NOW, pause=NO_PAUSE).status == \
        "first_read"
    posts = [b for url, _h, b in fetch.calls if url == seed.NG_API]
    assert len(posts) == 5  # five years, a year a request (days x items under 3,600)
    first = json.loads(posts[0])
    assert first["publicationIds"] == ["PUBOB603", "PUBOB604", "PUBOB605"]
    assert first["latestValue"] == "Y" and first["toDate"] == "2026-03-03"
    sap = session.get(MarketQuoteRecord, "pub:ng:sap")
    # 2.5 p/kWh is 25 GBP/MWh, shown at NBP as 73.27 p/th.
    assert (sap.hub, sap.unit, sap.last_price) == ("NBP", "GBP/MWh", 25.0)
    assert sap.metadata_json["native_last"] == pytest.approx(73.2678, abs=1e-3)
    cash = published_cash_out(session, "NBP", date(2026, 3, 3))
    assert cash["gas_day"] == "2026-03-01" and cash["currency"] == "GBP"
    assert cash["short_premium"] == pytest.approx(1.0) and cash["long_discount"] == \
        pytest.approx(1.0)


def test_mibgas_history_years_not_published_are_noted_and_the_curve_is_mapped(session):
    rows = [(date(2026, 3, 2), "GMAES", date(2026, 4, 1), date(2026, 4, 30), "39.5"),
            (date(2026, 3, 2), "GDAES_D+1", date(2026, 3, 3), date(2026, 3, 3), "40.1")]
    fetch = seed.ConsentedFetcher({seed.mibgas_url(2026): seed.mibgas_csv(rows),
                                   seed.mibgas_url(2025): seed.mibgas_csv(rows[:1])})
    check_publication(session, MIBGAS, fetch=fetch, now=NOW, pause=NO_PAUSE)
    row = session.get(WatchedPublicationRecord, MIBGAS.publication_id)
    assert row.state == "current"
    assert "MIBGAS_Data_2016.csv" in row.record["not_published"]
    month = session.get(MarketQuoteRecord, "pub:mibgas:pvb-ma")
    assert month.product == "apr-26"  # by its delivery, so a month roll never mislabels it
    history = session.query(MarketObservationRecord).filter_by(product="PVB month-ahead").all()
    assert history and history[0].metadata_json["tenor"] == "month-ahead"
    later = check_publication(session, MIBGAS, fetch=fetch, now=NOW + timedelta(hours=7),
                              pause=NO_PAUSE)
    assert later.status == "current"  # the same file: nothing changes
    assert fetch.urls()[-1] == seed.mibgas_url(2026)


def test_eex_ngp_is_located_on_its_page_and_read_conditionally(session):
    fetch = seed.ConsentedFetcher({seed.EEX_NGP_PAGE: seed.eex_ngp_page(),
                                   seed.EEX_NGP_FILE: seed.eex_ngp_csv(
                                       [(date(2026, 3, 2), 30.25)])})
    check_publication(session, EEX_NGP, fetch=fetch, now=NOW, pause=NO_PAUSE)
    assert fetch.urls() == ["https://www.eex.com/robots.txt", seed.EEX_NGP_PAGE,
                            "https://gasandregistry.eex.com/robots.txt", seed.EEX_NGP_FILE]
    assert session.get(MarketQuoteRecord, "pub:eex:ttf-ngp").last_price == 30.25
    check_publication(session, EEX_NGP, fetch=fetch, now=NOW + timedelta(hours=7),
                      pause=NO_PAUSE)
    assert fetch.calls[-1][1] == {"If-None-Match": '"e1"'}


def test_a_refusal_backs_off_and_honours_retry_after_and_robots(session):
    busy = seed.ConsentedFetcher({}, robots={"api.tradinghub.eu": (401, b"")},
                                 statuses={seed.THE_API: (429, {"retry-after": "86400"})})
    assert check_publication(session, THE, fetch=busy, now=NOW, pause=NO_PAUSE).status == \
        "unreachable"
    row = session.get(WatchedPublicationRecord, THE.publication_id)
    assert row.consecutive_failures == 1
    assert row.next_check_at_utc.replace(tzinfo=UTC) == NOW + timedelta(days=1)
    waiting = check_publication(session, THE, fetch=busy, now=NOW + timedelta(hours=7),
                                pause=NO_PAUSE)
    assert waiting.status == "skipped" and "waiting" in waiting.detail
    blocked = seed.ConsentedFetcher({seed.THE_API: b""}, robots={
        "api.tradinghub.eu": (200, b"User-agent: *\nDisallow: /api/\n")})
    outcome = check_publication(session, THE, fetch=blocked, now=NOW + timedelta(days=2),
                                pause=NO_PAUSE)
    assert outcome.status == "unreachable" and "robots.txt disallows" in outcome.detail
    assert blocked.urls() == ["https://api.tradinghub.eu/robots.txt"]
    assert PUBLICATION_USER_AGENT == "EurogasNexus-PublicationWatch/1.0"


def test_withdrawing_a_consent_stops_fetching_at_once_and_marks_the_data(session):
    check_publication(session, THE, fetch=_the_fetcher(), now=NOW, pause=NO_PAUSE)
    withdraw_consent(session, "trading-hub-europe", principal="admin-1",
                     now=NOW + timedelta(hours=1), reason="publisher asked")
    states = {row["publication_id"]: row for row in source_status(session, now=NOW)}
    assert states["the-imbalance-prices"]["state"] == "consent_withdrawn"
    assert states["the-imbalance-prices"]["consent_line"] == "consent withdrawn on 2026-03-03"
    fetch = _the_fetcher()
    outcome = check_publication(session, THE, fetch=fetch, now=NOW + timedelta(days=1),
                                pause=NO_PAUSE, force=True)
    assert outcome.status == "not_fetched" and fetch.calls == []
    # The data held stays.
    assert session.get(MarketQuoteRecord, "pub:the:vtp-daily-average") is not None
    audit = session.query(AuditEventRecord).filter_by(action="publisher_consent.withdraw").one()
    assert audit.principal == "admin-1" and "publisher asked" in audit.detail
    consents = {c["publisher_id"]: c for c in consent_status(session)}
    assert consents["trading-hub-europe"]["state"] == "withdrawn"
    with pytest.raises(ValueError):
        withdraw_consent(session, "trading-hub-europe", principal="admin-1", now=NOW)
    restore_consent(session, "trading-hub-europe", principal="admin-1",
                    now=NOW + timedelta(days=2))
    assert check_publication(session, THE, fetch=_the_fetcher(), now=NOW + timedelta(days=2),
                             pause=NO_PAUSE).status in {"current", "changed"}
    assert session.query(AuditEventRecord).filter_by(
        action="publisher_consent.restore").count() == 1


def _calendars(session, now):
    files = {seed.EEX_CAL_PAGE: seed.eex_calendar_page(),
             seed.EEX_GAS_XLSX: seed.eex_gas_xlsx([(date(2026, 4, 3), "Good Friday"),
                                                  (date(2026, 12, 25), "Christmas day")]),
             seed.EEX_HOLIDAY_PDF: seed.eex_holiday_pdf(),
             seed.ENDEX_PDF: seed.endex_pdf(), seed.IFEU_PDF: seed.ifeu_pdf()}
    fetch = seed.ConsentedFetcher(files)
    for publication_id in ("eex-trading-calendar", "eex-holiday-calendar",
                           "ice-endex-trading-schedule", "ice-futures-europe-trading-schedule"):
        outcome = check_publication(session, watched_publication(publication_id), fetch=fetch,
                                    now=now, pause=NO_PAUSE)
        assert outcome.status == "first_read", (publication_id, outcome)
    return fetch


def test_fetched_calendars_replace_the_hand_file_and_settle_24_and_31_december(session):
    now = datetime(2026, 12, 10, 9, tzinfo=UTC)
    _calendars(session, now)
    calendar = effective_trading_calendar(session)
    venues = {venue.code: venue for venue in calendar.venues}
    eex = venues["EEX"]
    # EEX gas trades shorter hours on 24 and 31 December: an early close, not a closed day.
    assert date(2026, 12, 24) not in eex.closed and date(2026, 12, 31) not in eex.closed
    assert dict(eex.early_closes)[date(2026, 12, 24)] == (
        "gas derivatives trade 09:00-12:30 CET only")
    # 2027 is not in the fetched workbook yet: the hand file's days stay, except the two days
    # the standing EEX rule settles.
    assert date(2027, 3, 26) in eex.closed and date(2027, 12, 24) not in eex.closed
    assert eex.checked and eex.check_by is None
    assert date(2026, 5, 4) in venues["ICE_FUTURES_EUROPE"].closed
    items = calendar_items(session, now=now, days=30)
    closed = {i["key"]: i for i in items if i["kind"] == "non_trading_day"}
    assert closed["closed:EEX:2026-12-25"]["source"]["basis"] == "fetched"
    assert closed["closed:EEX:2026-12-25"]["source"]["consent"].startswith("fetched under")
    assert closed["closed:ICE_FUTURES_EUROPE:2026-12-28"]["source"]["publication_id"] == \
        "ice-futures-europe-trading-schedule"
    early = {i["key"] for i in items if i["kind"] == "early_close"}
    assert {"early:EEX:2026-12-24", "early:ICE_ENDEX:2026-12-24",
            "early:ICE_FUTURES_EUROPE:2026-12-24"} <= early
    assert any(i["kind"] == "expiry" and i["day"] == "2026-12-30" for i in items)
    # Fetched calendars need no hand-file check reminder.
    assert not [i for i in items if i["kind"] == "check_calendar"]


def test_without_a_fetched_calendar_the_hand_file_is_the_fallback(session):
    calendar = effective_trading_calendar(session)
    eex = next(venue for venue in calendar.venues if venue.code == "EEX")
    assert date(2026, 12, 25) in eex.closed and not eex.checked
    # The file itself now carries what EEX's own calendar says about 24 and 31 December.
    assert date(2026, 12, 24) not in eex.closed
    assert dict(eex.early_closes)[date(2026, 12, 31)] == (
        "gas derivatives trade 08:00-13:00 CET only")
