"""Written consents (owner, 2026-11-28): the records, the registry that obeys them, and the
parsers of the consented publishers' layouts.

No network: every document is a fixture written for the tests (``tests/fixtures/
consented_seed``) with invented values.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from eurogas_nexus.domain.publications import exchange_calendars as calendars
from eurogas_nexus.domain.publications import public_prices as prices
from eurogas_nexus.domain.publications.consents import (
    CONSENT_SECTION,
    consent_for_family,
    consented_source_families,
    parse_consents,
    publisher_consent,
    publisher_consents,
)
from eurogas_nexus.domain.publications.registry import (
    CONSENTED,
    WATCHED_PUBLICATIONS,
    fetch_refusal,
    unfetched_state,
    watched_publication,
)
from tests.fixtures import consented_seed as seed

ROOT = Path(__file__).resolve().parents[2]
TERMS = (ROOT / "docs" / "legal" / "DATA_SOURCE_TERMS.md").read_text(encoding="utf-8")
TWELVE = {"Trading Hub Europe", "MIBGAS", "National Gas", "Fluxys", "Grain LNG", "Gate terminal",
          "Enagás", "Deutsche Energy Terminal (DET)", "Deutsche ReGas", "PRISMA", "EEX", "ICE"}


def test_the_twelve_consents_ship_as_data_with_the_stated_scope():
    consents = publisher_consents()
    assert len(consents) == 12
    for consent in consents:
        assert consent.scope == ("publicly available data; the firm's own use; no resale or "
                                 "redistribution")
        assert consent.basis == ("written consent held by the owner; not seen by the "
                                 "development team")
        assert consent.reported_on == date(2026, 11, 28) and consent.supersedes
        assert consent.line() == ("fetched under written consent (reported 2026-11-28, own use, "
                                  "no resale)")
    assert consented_source_families() == {"THE", "NATIONAL_GAS_PRICES", "MIBGAS", "EEX_PUBLIC",
                                           "ICE_PUBLIC"}
    assert consent_for_family("MIBGAS").publisher_id == "mibgas"
    assert consent_for_family("NATIONAL_GAS") is None  # the open-data portal family is not it
    one = parse_consents('reported_on = "2026-11-28"\nscope = "s"\nbasis = "b"\n'
                         '[publisher.a]\nname = "A"\nfamilies = ["X"]\n')
    assert one[0].families == ("X",) and one[0].scope == "s"
    with pytest.raises(ValueError):  # a malformed file (two records for one publisher)
        parse_consents('reported_on = "2026-11-28"\nscope = "s"\nbasis = "b"\n'
                       '[publisher.a]\nname = "A"\n[publisher.a]\nname = "B"\n')


def test_the_legal_register_states_every_consent_and_keeps_the_earlier_findings():
    assert f"## {CONSENT_SECTION}" in TERMS
    section = TERMS.split(f"## {CONSENT_SECTION}", 1)[1].split("\n## ", 1)[0]
    rows = [line for line in section.splitlines() if line.startswith("| ") and "---" not in line]
    publishers = {line.split("|")[1].strip() for line in rows[1:13]}
    assert publishers == TWELVE
    assert "not seen by the development team" in section
    flat = " ".join(section.split())
    assert "internal use only" in flat and "daily packs" in flat
    # The findings the consents supersede stay in place.
    assert "## EEX website terms, checked 2026-11-18" in TERMS
    assert "## Imbalance prices, checked 2026-11-19" in TERMS
    assert "single copy for exclusive personal, non-commercial use" in TERMS


def test_a_consented_publication_is_fetched_only_with_its_record_and_a_parser():
    consented = [item for item in WATCHED_PUBLICATIONS if item.verdict == CONSENTED]
    assert {item.consent_publisher for item in consented} == {c.publisher_id
                                                             for c in publisher_consents()}
    fetched = {item.publication_id for item in WATCHED_PUBLICATIONS if fetch_refusal(item) is None}
    assert fetched == {"entsog-cam-auction-calendar", "eex-trading-calendar",
                       "eex-holiday-calendar", "ice-endex-trading-schedule",
                       "ice-futures-europe-trading-schedule", "the-imbalance-prices",
                       "national-gas-smp", "mibgas-prices", "eex-ngp"}
    for item in consented:
        assert publisher_consent(item.consent_publisher) is not None
        if item.parser is None:
            assert fetch_refusal(item) == "consented, not yet implemented"
            assert unfetched_state(item) == "not_implemented"
    # Not in the twelve: left as they were.
    for publication_id in ("gsa-platform-auctions", "rbp-auctions", "uniper-storage-offers"):
        item = watched_publication(publication_id)
        assert item.verdict == "link_only" and item.consent_publisher is None
    # Every price source is stored under a consented family.
    for item in consented:
        if item.kind == "reference_prices":
            assert item.source_family in consent_for_family(item.source_family).families


def test_a_consent_record_missing_or_a_refusing_site_stops_the_fetch():
    from dataclasses import replace

    item = watched_publication("mibgas-prices")
    assert "no written consent" in fetch_refusal(replace(item, consent_publisher="nobody"))
    refusing = replace(item, site_refusal="HTTP 403 'automated access denied'")
    assert "refuses automated reading" in fetch_refusal(refusing)
    assert unfetched_state(refusing) == "site_refuses"


def test_the_published_figures_are_read_with_what_they_are_and_their_day():
    the = prices.parse_the_imbalance(seed.the_xml([
        (date(2026, 3, 1), 30.5, 29.9, 31.1), (date(2026, 3, 2), 31.0, 30.4, 31.6)]),
        today=date(2026, 3, 3))
    by = {(p.series, p.day): p for p in the.points}
    average = by[("the:vtp-daily-average", date(2026, 3, 1))]
    assert (average.hub, average.tenor, average.kind, average.value) == (
        "THE", "within-day", "reference_index", 30.5)
    assert average.status == "final" and by[("the:vtp-daily-average", date(2026, 3, 2))].status \
        == "preliminary"
    assert by[("the:imbalance-negative", date(2026, 3, 1))].tenor == "imbalance-short"
    ng = prices.parse_national_gas(seed.ng_json([(date(2026, 3, 1), "1.0101", "1.2", ".9")]))
    sap = next(p for p in ng.points if p.series == "ng:sap")
    assert (sap.hub, sap.unit, sap.value) == ("NBP", "GBp/kWh", 1.0101)
    assert next(p for p in ng.points if p.series == "ng:smp-sell").value == 0.9
    mib = prices.parse_mibgas(seed.mibgas_csv([
        (date(2026, 3, 2), "GDAES_D+1", date(2026, 3, 3), date(2026, 3, 3), "40.1"),
        (date(2026, 3, 2), "GMAES", date(2026, 4, 1), date(2026, 4, 30), "39.5"),
        (date(2026, 3, 2), "GQES_Q+1", date(2026, 4, 1), date(2026, 6, 30), "38.25"),
        (date(2026, 3, 2), "GYES_Y+1", date(2027, 1, 1), date(2027, 12, 31), "35"),
        (date(2026, 3, 3), "GDAES_D+1", date(2026, 3, 4), date(2026, 3, 4), ""),
    ]))
    labels = {p.series: p.contract_label for p in mib.points}
    assert labels == {"mibgas:pvb-da": "", "mibgas:pvb-ma": "Apr-26", "mibgas:pvb-q1": "Q2-26",
                      "mibgas:pvb-y1": "Cal-27"}
    assert all(p.day == date(2026, 3, 2) and p.kind == "daily_price" for p in mib.points)
    ngp = prices.parse_eex_ngp(seed.eex_ngp_csv([(date(2026, 3, 1), 30.25)]))
    assert ngp.points[0].series == "eex:ttf-ngp" and ngp.points[0].hub == "TTF"
    assert ngp.to_json()["latest"]["eex:ttf-ngp"]["value"] == 30.25


@pytest.mark.parametrize("parse", [
    lambda: prices.parse_the_imbalance(seed.the_xml([(date(2026, 3, 1), 1, 1, 1)],
                                                    unit="EUR/kWh"), today=date(2026, 3, 3)),
    lambda: prices.parse_the_imbalance(seed.the_xml([(date(2026, 3, 1), 1, 1, 1)],
                                                    extra_field=True), today=date(2026, 3, 3)),
    lambda: prices.parse_the_imbalance(b"<html>maintenance</html>", today=date(2026, 3, 3)),
    lambda: prices.parse_national_gas(seed.ng_json([(date(2026, 3, 1), "1", "1", "1")],
                                                   rename=True)),
    lambda: prices.parse_mibgas(seed.mibgas_csv([], header="Day;Product;Price;")),
    lambda: prices.parse_eex_ngp(b"Gasday;Value\n01/03/2026;30\n"),
    lambda: prices.parse_national_gas(seed.ng_json([(date(2026, 3, 1), "1,5", "1", "1")])),
])
def test_a_changed_layout_is_not_guessed(parse):
    with pytest.raises(prices.PricesUncertain):
        parse()


def test_the_exchange_calendars_are_read_from_their_documents():
    gas = calendars.parse_eex_gas_calendar(seed.eex_gas_xlsx(
        [(date(2026, 1, 1), "New Year's Day"), (date(2026, 12, 25), "Christmas day")]))
    assert [d for d, _w in gas.closed] == [date(2026, 1, 1), date(2026, 12, 25)]
    assert gas.expiries[0].last_trading_day == date(2026, 11, 27)
    with pytest.raises(calendars.CalendarUncertain):
        calendars.parse_eex_gas_calendar(seed.eex_gas_xlsx([], drop_column=True))
    short = calendars.parse_eex_holiday_calendar(seed.eex_holiday_pdf(), years=(2026,))
    assert dict(short.early_closes)[date(2026, 12, 24)] == (
        "gas derivatives trade 09:00-12:30 CET only")
    with pytest.raises(calendars.CalendarUncertain):
        calendars.parse_eex_holiday_calendar(seed.eex_holiday_pdf(footnote=False), years=(2026,))
    endex = calendars.parse_ice_endex_schedule(seed.endex_pdf())
    assert date(2026, 4, 3) in dict(endex.closed)
    assert "early settlement 13:40-13:50 CET" in dict(endex.early_closes)[date(2026, 12, 24)]
    ifeu = calendars.parse_ifeu_schedule(seed.ifeu_pdf())
    assert set(dict(ifeu.closed)) == {date(2026, 4, 3), date(2026, 5, 4), date(2026, 12, 28),
                                      date(2027, 1, 1)}
    assert dict(ifeu.early_closes)[date(2026, 12, 24)].startswith(
        "UK natural gas settles 12:40-12:50 GMT")
    with pytest.raises(calendars.CalendarUncertain):
        calendars.parse_ice_endex_schedule(seed.ifeu_pdf())
    page = seed.eex_calendar_page()
    assert calendars.eex_document_link(page, seed.EEX_CAL_PAGE, kind="gas") == seed.EEX_GAS_XLSX
    assert calendars.eex_document_link(page, seed.EEX_CAL_PAGE, kind="holidays") == \
        seed.EEX_HOLIDAY_PDF
    with pytest.raises(calendars.CalendarUncertain):
        calendars.eex_document_link(b"<html></html>", seed.EEX_CAL_PAGE, kind="gas")
