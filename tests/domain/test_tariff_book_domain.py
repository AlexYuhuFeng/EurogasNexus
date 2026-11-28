"""TAR-1 domain: tariff versions, the CAM auction calendar and the publisher registry.

The calendar is checked offline against a real published calendar (FGSZ 2026/27, fixture with
its source URL and retrieval date). Tariff figures here are made up.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from eurogas_nexus.domain.tariffs import (
    FINAL,
    INDICATIVE,
    PUBLISHERS,
    ChangeKind,
    TariffSpec,
    decide_version,
    publisher,
    standard_auctions,
)
from eurogas_nexus.domain.tariffs.auction_calendar import nth_monday, opening_instant
from eurogas_nexus.domain.tariffs.model import HeldVersion, TariffError, status_change_label
from eurogas_nexus.domain.tariffs.publishers import (
    API,
    MANUAL,
    NEEDS_FIRM_TERMS,
    PARSED,
    PUBLICATION_SEASONS,
    lng_publisher_for,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "fixtures" / "tariffs" / "cam_auction_calendar_2026_27.json"
REGISTRY_DOC = ROOT / "docs" / "data" / "TARIFF_PUBLISHER_REGISTRY.md"
READ = datetime(2026, 11, 24, 9, tzinfo=UTC)


def spec(**changes) -> TariffSpec:
    base = {
        "tariff_key": "entsog-tp:entsog-ITP-1-exit-annual",
        "publisher_id": "entsog-tp",
        "facility_kind": "point",
        "facility_id": "ITP-1",
        "facility_name": "Point one",
        "operator": "Operator A",
        "direction": "EXIT",
        "product": "ANNUAL",
        "unit": "EUR/(kWh/h)/y",
        "currency": "EUR",
        "value": 4.0,
        "period_from": date(2026, 10, 1),
        "period_to": date(2027, 9, 30),
        "status": INDICATIVE,
        "status_basis": "nc_tar_before_yearly_auction",
        "retrieved_at_utc": READ,
        "source_url": "https://transparency.entsog.eu/api/v1/tariffsfulls?pointKey=ITP-1",
    }
    base.update(changes)
    return TariffSpec(**base)


# ------------------------------------------------------------------------------ versions


def test_the_content_hash_ignores_when_it_was_read_and_follows_what_it_says():
    first = spec()
    assert (
        first.content_hash == spec(retrieved_at_utc=datetime(2026, 12, 1, tzinfo=UTC)).content_hash
    )
    assert first.content_hash != spec(value=4.1).content_hash
    final = spec(status=FINAL, status_basis="nc_tar_yearly_auction_held")
    assert first.content_hash != final.content_hash
    assert first.duration == "yearly"


@pytest.mark.parametrize(
    "changes",
    [
        {"status": "PROVISIONAL"},
        {"status_basis": "guessed"},
        {"value": None},
        {"value": -1.0},
        {"period_to": date(2026, 9, 1)},
        {"source_url": "http://insecure.example/tariff"},
        {"facility_kind": "pipeline"},
        {"tariff_key": ""},
    ],
)
def test_a_spec_refuses_what_is_not_a_published_tariff(changes):
    with pytest.raises(TariffError):
        spec(**changes)


def test_a_terminal_tariff_by_cargo_class_needs_no_single_value():
    item = spec(facility_kind="terminal", value=None, by_class={"Q-Flex": 900000.0})
    assert item.content()["by_class"] == {"Q-Flex": "900000.0"}


def test_version_decisions_first_unchanged_revised_status_change_out_of_order():
    item = spec()
    assert decide_version(item, None).kind is ChangeKind.FIRST
    held = HeldVersion(1, item.content_hash, INDICATIVE, READ)
    assert decide_version(item, held).writes is False
    assert decide_version(spec(value=4.2), held).kind is ChangeKind.REVISED
    final = decide_version(spec(status=FINAL, status_basis="nc_tar_yearly_auction_held"), held)
    assert (final.kind, final.version, final.previous_status) == (
        ChangeKind.STATUS_CHANGE,
        2,
        INDICATIVE,
    )
    older = spec(value=3.9, retrieved_at_utc=datetime(2026, 11, 1, tzinfo=UTC))
    assert decide_version(older, held).reason == "out_of_order"
    again = decide_version(item, HeldVersion(3, "withdrawn", INDICATIVE, READ, withdrawn=True))
    assert (again.writes, again.version) == (True, 4)


def test_a_status_change_is_named_never_silent():
    assert status_change_label(INDICATIVE, FINAL) == "INDICATIVE->FINAL"
    assert status_change_label(FINAL, INDICATIVE) == "FINAL->INDICATIVE"
    assert status_change_label(FINAL, FINAL) is None
    assert status_change_label(None, FINAL) is None


# ---------------------------------------------------------------------- auction calendar


def test_mondays_and_the_brussels_opening_hour():
    assert nth_monday(2026, 7, 1) == date(2026, 7, 6)
    assert nth_monday(2026, 11, 3) == date(2026, 11, 16)
    assert opening_instant(date(2026, 7, 6)) == datetime(2026, 7, 6, 7, tzinfo=UTC)
    assert opening_instant(date(2026, 11, 16)) == datetime(2026, 11, 16, 8, tzinfo=UTC)


def test_the_rule_matches_a_published_calendar_both_ways():
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert fixture["source"]["url"].startswith("https://")
    assert fixture["source"]["retrieved_on"] == "2026-11-24"
    published = {
        (row["product"], datetime.fromisoformat(row["opens_at_utc"])) for row in fixture["auctions"]
    }
    for product in ("ANNUAL", "QUARTERLY", "MONTHLY"):
        theirs = sorted(when for kind, when in published if kind == product)
        derived = {
            item.opens_at_utc
            for item in standard_auctions(theirs[0].date(), theirs[-1].date())
            if item.product == product
        }
        assert derived == set(theirs), product


def test_each_window_says_what_it_offers():
    windows = {
        item.notice_key: item for item in standard_auctions(date(2026, 7, 1), date(2026, 11, 30))
    }
    yearly = windows["cam:yearly:2026"]
    assert (yearly.offers_from, yearly.offers_to) == (date(2026, 10, 1), date(2031, 9, 30))
    autumn = windows["cam:quarterly:2026-08-03"]
    assert (autumn.offers_from, autumn.offers_to) == (date(2026, 10, 1), date(2027, 9, 30))
    winter = windows["cam:quarterly:2026-11-02"]
    assert (winter.offers_from, winter.offers_to) == (date(2027, 1, 1), date(2027, 9, 30))
    december = windows["cam:monthly:2026-12"]
    assert december.opens_at_utc == datetime(2026, 11, 16, 8, tzinfo=UTC)
    assert (december.offers_from, december.offers_to) == (date(2026, 12, 1), date(2026, 12, 31))
    assert standard_auctions(date(2026, 2, 1), date(2026, 1, 1)) == []


# ----------------------------------------------------------------------------- registry


def test_the_registry_is_consistent_and_fabricates_nothing():
    ids = [item.publisher_id for item in PUBLISHERS]
    assert len(ids) == len(set(ids))
    for item in PUBLISHERS:
        assert item.page_url == "" or item.page_url.startswith("https://"), item.publisher_id
        assert item.terms.strip(), item.publisher_id
        assert item.publishes, item.publisher_id
        if item.access == MANUAL:
            # A manual publisher is read by a person: no API, no poll, nothing automated.
            assert item.api_url is None and item.poll is None and not item.automated
        if item.reuse == NEEDS_FIRM_TERMS:
            assert not item.automated, item.publisher_id
        if item.automated:
            assert item.poll is not None and item.poll.stale_after_minutes > 0
    assert publisher("entsog-tp").access == API
    assert {item.publisher_id for item in PUBLISHERS if item.access == PARSED} == {
        "fluxys-lng",
        "elengy",
        "det",
        "entsog-auction-calendar",
    }
    assert lng_publisher_for("zeebrugge:term") == "fluxys-lng"
    assert lng_publisher_for("unknown-terminal") is None


def test_entsog_is_polled_hourly_in_publication_windows_and_six_hourly_otherwise():
    # TAR-2: tighter around the windows a new indicative or final appears in.
    poll = publisher("entsog-tp").poll
    assert poll.interval_minutes(date(2026, 6, 2)) == 60  # before the July yearly auction
    assert poll.interval_minutes(date(2026, 12, 20)) == 60
    assert poll.interval_minutes(date(2026, 3, 20)) == 60  # before the April tariff years
    assert poll.interval_minutes(date(2026, 8, 20)) == 360
    assert all(start <= end for start, end in PUBLICATION_SEASONS)


def test_every_publisher_is_in_the_registry_document():
    text = REGISTRY_DOC.read_text(encoding="utf-8")
    table = text.split("## Publishers", 1)[1].split("\n## ", 1)[0]
    documented = {
        line.split("|")[1].strip().strip("`")
        for line in table.splitlines()
        if line.startswith("| `")
    }
    assert documented == {item.publisher_id for item in PUBLISHERS}
