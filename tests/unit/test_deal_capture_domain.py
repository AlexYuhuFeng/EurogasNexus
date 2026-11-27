"""The deal capture domain: format files, the row reader, quantities, the sheet, the check."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from eurogas_nexus.domain.deals.eod import CapturedSide, EtrmSide, check
from eurogas_nexus.domain.deals.formats import (
    FormatError,
    detect_format,
    load_formats,
    parse_format,
)
from eurogas_nexus.domain.deals.parse import (
    RowError,
    label_for,
    number,
    parse_deal_file,
    price_per_mwh,
    product_code,
)
from eurogas_nexus.domain.deals.sheet import parse_layout, sheet_csv

MINIMAL = """
name = "broker_x"
title = "Broker X recap"
venue = "BRKX"
delimiter = ";"
decimal_separator = ","
thousands_separator = "."
date_formats = ["%d.%m.%Y"]
[columns]
venue_trade_id = "Ref"
side = "Richtung"
hub = "Markt"
product = "Periode"
volume = "Menge"
volume_unit = "Einheit"
price = "Preis"
trade_date = "Datum"
trader = "Händler"
counterparty = "Gegenpartei"
[values.side]
K = "buy"
V = "sell"
[lot_sizes]
TTF = "1 MW"
"""


def test_a_new_layout_is_a_format_file_without_code():
    fmt = parse_format(MINIMAL)
    text = ("Ref;Datum;Händler;Gegenpartei;Richtung;Markt;Periode;Menge;Einheit;Preis\n"
            "X1;26.11.2026;anna;Example Energy GmbH;K;TTF;Jan-27;1.200;MWh/d;31,125\n"
            "X2;26.11.2026;anna;;V;TTF;Q1 27;3;lots;30,5\n")
    parsed = parse_deal_file(text, fmt, file_name="x.csv", book_id="b")
    assert not parsed.problems
    first, second = parsed.deals
    assert (first.volume, first.total_mwh, first.price) == (Decimal("1200"), Decimal("37200"),
                                                            Decimal("31.125"))
    assert first.cleared is False and first.instrument == "forward"
    assert first.counterparty == "Example Energy GmbH"
    # Three lots of 1 MW over Q1-27 (2,159 hours: no DST change in the quarter).
    assert second.volume_unit == "MW" and second.total_mwh == Decimal("6477")
    assert second.cleared is True  # no counterparty: cleared


def test_format_files_say_what_is_wrong():
    with pytest.raises(FormatError, match="must say which column holds 'price'"):
        parse_format('name="a"\ntitle="a"\nvenue="A"\n[columns]\nvenue_trade_id="x"\n'
                     'side="s"\nvolume="v"\nhub="h"\nproduct="p"\n')
    with pytest.raises(FormatError, match="fields that do not exist: colour"):
        parse_format(MINIMAL.replace('price = "Preis"', 'price = "Preis"\ncolour = "c"'))


def test_the_built_in_formats_load_and_are_labelled_unverified():
    formats, errors = load_formats({})
    assert errors == []
    assert {"eex_trades", "ice_deal_report", "desk_csv"} <= set(formats)
    for name in ("eex_trades", "ice_deal_report"):
        assert formats[name].verified is False
        assert "unverified against the desk's own files" in formats[name].provenance
    assert detect_format(["Deal ID", "B/S", "Hub", "Price"], formats).name == "ice_deal_report"
    assert detect_format(["tranIdNo", "buyCod", "prodId"], formats).name == "eex_trades"
    assert detect_format(["foo"], formats) is None


def test_a_desk_copy_replaces_the_built_in_format(tmp_path):
    (tmp_path / "ice.toml").write_text(
        MINIMAL.replace('name = "broker_x"', 'name = "ice_deal_report"'), encoding="utf-8")
    formats, _errors = load_formats({"EUROGAS_NEXUS_DEAL_FORMATS_DIR": str(tmp_path)})
    assert formats["ice_deal_report"].venue == "BRKX"


def test_numbers_are_exact_and_read_with_the_formats_separators():
    fmt = parse_format(MINIMAL)
    assert number("1.234,50", fmt, "x") == Decimal("1234.50")
    assert number("(10)", None, "x") == Decimal("-10")
    with pytest.raises(RowError) as caught:
        number("1e400x", None, "volume")
    assert caught.value.code == "number_invalid"


def test_desk_labels_from_dates_and_products():
    assert label_for(date(2026, 12, 1), date(2026, 12, 31)) == "Dec-26"
    assert label_for(date(2027, 1, 1), date(2027, 3, 31)) == "Q1-27"
    assert label_for(date(2026, 10, 1), date(2027, 3, 31)) == "Win-26"
    assert label_for(date(2027, 1, 1), date(2027, 12, 31)) == "Cal-27"
    assert label_for(date(2026, 11, 28), date(2026, 11, 29)) == "WE 28-Nov"
    assert product_code("Bal Month") == "BOM"
    assert product_code("2026-12") == "DEC-26"
    assert product_code("Winter 26") == "WIN-26"


def test_a_mw_deal_over_a_clock_change_counts_the_real_hours():
    fmt = parse_format(MINIMAL)
    text = ("Ref;Datum;Händler;Gegenpartei;Richtung;Markt;Periode;Menge;Einheit;Preis\n"
            "X3;26.11.2026;anna;;K;TTF;Mar-27;1;MW;30\n")
    deal = parse_deal_file(text, fmt, file_name="x", book_id="b").deals[0]
    assert deal.total_mwh == Decimal("743")  # 31 days less the hour lost in March


def test_pence_per_therm_is_not_pounds_per_therm():
    fmt = parse_format(MINIMAL)
    text = ("Ref;Datum;Händler;Gegenpartei;Richtung;Markt;Periode;Menge;Einheit;Preis\n"
            "N1;26.11.2026;anna;;V;NBP;Jan-27;1000;th/d;95\n")
    deal = parse_deal_file(text, fmt, file_name="x", book_id="b").deals[0]
    assert deal.price_unit == "GBp/th" and deal.price_currency == "GBP"
    assert price_per_mwh(deal).quantize(Decimal("0.0001")) == Decimal("32.4153")
    # 1,000 th/d x 31 days x 0.0293071... MWh per therm.
    assert deal.total_mwh == Decimal("908.520318")


def _captured(key, hub="TTF", side="buy", mwh="3720", price="31.25", status="live",
              first=date(2026, 12, 1), last=date(2026, 12, 31), counterparty="",
              cleared=True):
    return CapturedSide(
        deal_key=f"ICE:{key}", venue="ICE", venue_trade_id=key, status=status, trader="a",
        counterparty=counterparty, cleared=cleared, hub=hub, product="Dec-26", side=side,
        first_day=first, last_day=last, total_mwh=Decimal(mwh), price_per_mwh=Decimal(price),
        currency="EUR", book_id="b", source="f line 2")


def _etrm(trade_id, reference="", hub="TTF", side="buy", mwh="3720", price="31.25",
          counterparty="ICE Endex", first=date(2026, 12, 1), last=date(2026, 12, 31)):
    return EtrmSide(trade_id=trade_id, reference=reference, hub=hub, side=side, first_day=first,
                    last_day=last, total_mwh=Decimal(mwh), price_per_mwh=Decimal(price),
                    counterparty=counterparty, book_id="b", line=2)


def test_the_check_pairs_by_reference_then_by_terms_and_hides_nothing():
    captured = [
        _captured("1"),                                   # same, by reference
        _captured("2", price="31.30"),                    # price differs, by reference
        _captured("3", mwh="1000"),                       # by terms, volume differs
        _captured("4", status="cancelled"),               # cancelled: fine when absent
        _captured("5", hub="THE"),                        # nothing in the ETRM
        _captured("6", status="cancelled", hub="PEG"),    # cancelled but entered
    ]
    etrm = [
        _etrm("E1", reference="1"),
        _etrm("E2", reference="2"),
        _etrm("E3", mwh="1100"),
        _etrm("E6", reference="6", hub="PEG"),
        _etrm("E9", hub="ZTP"),
    ]
    result = check(captured, etrm)
    found = sorted((d["kind"], d["deal_key"] or d["etrm_trade_id"]) for d in result.differences)
    assert found == [
        ("cancelled_in_capture", "ICE:6"),
        ("missing_in_capture", "E9"),
        ("missing_in_etrm", "ICE:5"),
        ("price", "ICE:2"),
        ("volume", "ICE:3"),
    ]
    assert result.matched == 4 and result.matched_by_terms == 1
    assert result.pairs == {"ICE:1": "E1", "ICE:2": "E2", "ICE:3": "E3", "ICE:6": "E6"}
    # Rounding of a converted unit is not a difference.
    tiny = check([_captured("7", price="32.4494669")], [_etrm("E7", reference="7",
                                                              price="32.449467")])
    assert tiny.differences == []


def test_a_bilateral_counterparty_mismatch_is_listed():
    result = check([_captured("8", counterparty="Northwind Gas Trading", cleared=False)],
                   [_etrm("E8", reference="8", counterparty="Example Energy GmbH")])
    assert [d["kind"] for d in result.differences] == ["counterparty"]


def test_the_sheet_layout_writes_values_as_the_template_wants():
    layout = parse_layout(
        'date_format = "%d.%m.%Y"\n[[column]]\nheader = "Desk"\nvalue = "GAS"\n'
        '[[column]]\nheader = "Side"\nfield = "side"\nvalues = { buy = "K", sell = "V" }\n'
        '[[column]]\nheader = "Physical"\nfield = "physical"\n'
        'values = { true = "P", false = "F" }\n'
        '[[column]]\nheader = "Start"\nfield = "delivery_start"\n'
        '[[column]]\nheader = "Qty"\nfield = "volume"\ndecimals = 1\n')
    content = sheet_csv(layout, [{"side": "sell", "physical": True,
                                  "delivery_start": date(2026, 12, 1),
                                  "volume": Decimal("12.345"), "status": "live"},
                                 {"side": "buy", "status": "cancelled"}])
    assert content.decode("utf-8-sig").splitlines() == ["Desk,Side,Physical,Start,Qty",
                                                        "GAS,V,P,01.12.2026,12.3"]
    with pytest.raises(FormatError, match="unknown field 'colour'"):
        parse_layout('[[column]]\nheader = "x"\nfield = "colour"\n')
