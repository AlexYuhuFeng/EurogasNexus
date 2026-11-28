"""Package G: the publication watch fetches what the terms allow, detects a change by digest,
keeps the previous record, holds the old record when the new document cannot be read, and says
so when a source is unreachable or not permitted.

Every fetch goes through an in-memory fetcher; nothing here touches the network.
"""

from __future__ import annotations

import importlib.util
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from sqlalchemy.orm import Session

from eurogas_nexus.application.publication_watch import (
    calendar_items,
    check_publication,
    confirm_publication,
    queue_deadline_notifications,
    source_status,
    watch_all,
    watch_publications_if_due,
)
from eurogas_nexus.application.tariff_book import refresh_standard_auctions
from eurogas_nexus.db.models import (
    CapacityNoticeRecord,
    MarketEventRecord,
    NotificationOutboxRecord,
    RawPayloadContentRecord,
    WatchedPublicationRecord,
)
from eurogas_nexus.domain.publications.registry import watched_publication
from tests.fixtures.news_seed import store
from tests.fixtures.publication_seed import (
    FILE_2627,
    PAGE_URL,
    PublicationFetcher,
    calendar_xlsx,
)

NOW = datetime(2026, 3, 2, 9, 0, tzinfo=UTC)
ENTSOG = watched_publication("entsog-cam-auction-calendar")


def _session(tmp_path) -> Session:
    _url, engine = store(tmp_path, "watch.sqlite")
    return Session(engine)


def _notes(session, prefix: str) -> list[NotificationOutboxRecord]:
    return [row for row in session.query(NotificationOutboxRecord).all()
            if row.dedupe_key.startswith(prefix)]


def test_a_first_read_records_the_calendar_and_replaces_the_rule_derived_dates(tmp_path):
    fetch = PublicationFetcher({FILE_2627: calendar_xlsx()})
    with _session(tmp_path) as session:
        refresh_standard_auctions(session, now_utc=NOW)
        rule_april = session.get(CapacityNoticeRecord, "cam:monthly:2026-04")
        assert rule_april is not None and rule_april.state == "open"
        outcome = check_publication(session, ENTSOG, fetch=fetch, now=NOW)
        assert outcome.status == "first_read" and outcome.applied["created"] > 10
        # robots.txt first, then the page, then the file it links.
        assert fetch.calls == ["https://www.entsog.eu/robots.txt", PAGE_URL, FILE_2627]
        row = session.get(WatchedPublicationRecord, ENTSOG.publication_id)
        assert row.state == "current" and row.document_url == FILE_2627
        assert row.record["published_on"] == "2025-11-12" and row.previous_record is None
        assert session.get(RawPayloadContentRecord, row.content_sha256) is not None
        notice = session.get(CapacityNoticeRecord,
                             "entsog-auction-calendar:firm:monthly:2026-04-01")
        assert notice.basis == "published" and notice.source_url == FILE_2627
        assert notice.opens_at_utc.replace(tzinfo=UTC) == datetime(2026, 3, 15, 8, tzinfo=UTC)
        assert session.get(CapacityNoticeRecord, "cam:monthly:2026-04").state == "superseded"
        # A later refresh of the rule does not bring the replaced window back.
        refresh_standard_auctions(session, now_utc=NOW + timedelta(days=1))
        assert session.get(CapacityNoticeRecord, "cam:monthly:2026-04").state == "superseded"
        assert session.query(MarketEventRecord).filter_by(source_id="src-publications").count() == 1
        assert _notes(session, "publication:") == []  # a first read is not a change to tell


def test_within_the_interval_nothing_is_read_and_the_same_file_changes_nothing(tmp_path):
    fetch = PublicationFetcher({FILE_2627: calendar_xlsx()})
    with _session(tmp_path) as session:
        check_publication(session, ENTSOG, fetch=fetch, now=NOW)
        assert check_publication(session, ENTSOG, fetch=fetch,
                                 now=NOW + timedelta(hours=2)).status == "skipped"
        assert len(fetch.calls) == 3
        again = check_publication(session, ENTSOG, fetch=fetch, now=NOW + timedelta(days=1))
        assert again.status == "current"
        assert session.get(WatchedPublicationRecord, ENTSOG.publication_id).previous_record is None


def test_a_moved_date_updates_the_record_keeps_the_previous_one_and_tells_the_desk(tmp_path):
    with _session(tmp_path) as session:
        check_publication(session, ENTSOG, fetch=PublicationFetcher({FILE_2627: calendar_xlsx()}),
                          now=NOW)
        moved = PublicationFetcher(
            {FILE_2627: calendar_xlsx(monthly_override={4: date(2026, 4, 21)})}
        )
        later = NOW + timedelta(days=2)
        outcome = check_publication(session, ENTSOG, fetch=moved, now=later)
        assert outcome.status == "changed"
        row = session.get(WatchedPublicationRecord, ENTSOG.publication_id)
        assert row.previous_record is not None and row.previous_fetched_at_utc is not None
        notice = session.get(CapacityNoticeRecord,
                             "entsog-auction-calendar:firm:monthly:2026-05-01")
        assert notice.revision == 2
        assert notice.opens_at_utc.replace(tzinfo=UTC).date() == date(2026, 4, 21)
        [note] = _notes(session, "publication:entsog-cam-auction-calendar:changed:")
        assert "Moved: Monthly auction, firm: May 2026" in note.body
        assert "ENTSOG and/or its members" in note.body


def test_a_layout_the_parser_cannot_read_holds_the_old_record_and_asks_once(tmp_path):
    with _session(tmp_path) as session:
        check_publication(session, ENTSOG, fetch=PublicationFetcher({FILE_2627: calendar_xlsx()}),
                          now=NOW)
        held = dict(session.get(WatchedPublicationRecord, ENTSOG.publication_id).record)
        broken = PublicationFetcher({FILE_2627: calendar_xlsx(rename_header=True)})
        for hours in (24, 48):
            outcome = check_publication(session, ENTSOG, fetch=broken,
                                        now=NOW + timedelta(hours=hours))
            assert outcome.status == "needs_confirmation"
        row = session.get(WatchedPublicationRecord, ENTSOG.publication_id)
        assert row.record == held and row.pending_url == FILE_2627
        assert row.detail.startswith("Source changed on 03 Mar 2026, needs a person to confirm")
        assert len(_notes(session, "publication:entsog-cam-auction-calendar:confirm:")) == 1
        items = calendar_items(session, now=NOW + timedelta(days=2), days=60)
        assert any(item["kind"] == "source_changed" for item in items)
        # A person looks, the dates held stay, the alarm clears; the same file is then quiet.
        confirmed = confirm_publication(session, ENTSOG.publication_id, principal="admin-1",
                                        now=NOW + timedelta(days=3))
        assert confirmed["state"] == "current" and confirmed["confirmed_by"] == "admin-1"
        assert check_publication(session, ENTSOG, fetch=broken,
                                 now=NOW + timedelta(days=4)).status == "current"


def test_an_unreachable_page_is_stated_and_a_robots_refusal_is_respected(tmp_path):
    with _session(tmp_path) as session:
        down = PublicationFetcher({}, page_status=503)
        assert check_publication(session, ENTSOG, fetch=down, now=NOW).status == "unreachable"
        row = session.get(WatchedPublicationRecord, ENTSOG.publication_id)
        assert row.state == "unreachable" and "status 503" in row.detail
        disallowed = PublicationFetcher({FILE_2627: calendar_xlsx()},
                                        robots=(200, b"User-agent: *\nDisallow: /\n"))
        outcome = check_publication(session, ENTSOG, fetch=disallowed,
                                    now=NOW + timedelta(days=1))
        assert outcome.status == "unreachable" and "robots.txt disallows" in outcome.detail
        assert disallowed.calls == ["https://www.entsog.eu/robots.txt"]


def test_publications_the_terms_exclude_are_never_fetched_and_say_so(tmp_path):
    fetch = PublicationFetcher({FILE_2627: calendar_xlsx()})
    with _session(tmp_path) as session:
        watch_all(session, fetch=fetch, now=NOW, pause=lambda _s: None)
        # Not covered by a consent, or no reader yet: never read.
        assert all(host not in url for url in fetch.calls
                   for host in ("gsaplatform.eu", "rbp.eu", "uniper.energy", "gate.nl",
                                "enagas.es", "prisma-capacity.eu", "deutsche-regas.de"))
        states = {row["publication_id"]: row for row in source_status(session, now=NOW)}
        assert states["entsog-cam-auction-calendar"]["state"] == "current"
        assert states["uniper-storage-offers"]["state"] == "link_only"
        assert "link only" in states["uniper-storage-offers"]["fetch_refusal"]
        assert states["fluxys-loenhout-storage"]["state"] == "not_implemented"
        assert states["fluxys-loenhout-storage"]["consent_line"] == (
            "fetched under written consent (reported 2026-11-28, own use, no resale)")
        # A consented source this fetcher does not serve is unreachable, said so, and waits.
        assert states["ice-endex-trading-schedule"]["state"] == "unreachable"
        assert states["ice-endex-trading-schedule"]["next_check_at_utc"] is not None
        assert states["ice-endex-trading-schedule"]["hand_file"]["check_by"] == "2026-12-15"


def test_the_calendar_shows_hand_maintained_holidays_auctions_and_reminders(tmp_path):
    now = datetime(2026, 12, 10, 9, tzinfo=UTC)
    with _session(tmp_path) as session:
        items = calendar_items(session, now=now, days=30)
        closed = [i for i in items if i["kind"] == "non_trading_day"]
        boxing = [i for i in closed if i["key"] == "closed:ICE_FUTURES_EUROPE:2026-12-28"]
        assert boxing and boxing[0]["hubs"] == ["NBP"]
        assert boxing[0]["source"]["basis"] == "hand_maintained"
        assert boxing[0]["source"]["checked"] is False
        assert any(i["kind"] == "early_close" for i in items)
        checks = [i for i in items if i["kind"] == "check_calendar"]
        assert {i["venue"] for i in checks} == {"EEX", "ICE_ENDEX", "ICE_FUTURES_EUROPE"}
        queued = queue_deadline_notifications(session, now=now)
        assert queued >= 3
        assert queue_deadline_notifications(session, now=now) == 0  # once each


def test_the_scheduler_hook_is_off_in_tests_and_never_raises(tmp_path):
    assert watch_publications_if_due(lambda: None, now_utc=NOW) == {"status": "off"}

    def broken():
        raise RuntimeError("no store")

    result = watch_publications_if_due(broken, now_utc=NOW, environ={})
    assert result == {"status": "failed", "error_type": "RuntimeError"}


def test_the_operator_script_dry_runs_and_commits(tmp_path, monkeypatch, capsys):
    url, _engine = store(tmp_path, "script.sqlite")
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    path = Path(__file__).resolve().parents[2] / "scripts" / "ops" / "watch_publications.py"
    spec = importlib.util.spec_from_file_location("watch_publications", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    fetch = PublicationFetcher({FILE_2627: calendar_xlsx()})
    assert module.main(["--publication", "entsog-cam-auction-calendar"], fetch=fetch) == 0
    assert "Dry run" in capsys.readouterr().out
    assert module.main(["--publication", "entsog-cam-auction-calendar", "--commit"],
                       fetch=fetch) == 0
    assert module.main(["--status"], fetch=fetch) == 0
    assert "entsog-cam-auction-calendar" in capsys.readouterr().out
