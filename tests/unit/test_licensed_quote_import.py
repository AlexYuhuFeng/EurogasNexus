"""Operator import of licensed screen exports (Trayport/ICE/EEX) into market quotes."""

from datetime import UTC, datetime

import pytest

from eurogas_nexus.ingestion.licensed_quote_import import (
    QuoteImportError,
    parse_quote_export,
)

NOW = datetime(2026, 10, 30, 9, 0, tzinfo=UTC)
EXPORT = (
    "Timestamp,Hub,Product,Bid,Ask,Last,Bid Qty,Ask Qty\n"
    "2026-10-30T08:59:58Z,TTF,DA,31.575,31.625,31.60,30,25\n"
    "2026-10-30T08:59:58Z,TTF,Nov-26,32.10,32.15,,60,60\n"
    "2026-10-30T08:59:58Z,NBP,Day Ahead,82.50,82.80,,25000,25000\n"
    "2026-10-30T08:59:58Z,THE,Sum-27,30.40,30.55,,,\n"
)


def _parse(text=EXPORT, **kwargs):
    return parse_quote_export(
        text,
        source_system="Trayport",
        source_reference="operator-export:t.csv",
        received_at_utc=NOW,
        **kwargs,
    )


def test_trayport_export_maps_products_units_and_family():
    result = _parse()
    rows = {(row["hub"], row["metadata_json"]["product_label"]): row for row in result.rows}
    da = rows[("TTF", "2026-11-02")]
    assert da["product"] == "day-ahead"  # Friday DA delivers Monday
    assert da["source_system"] == "Trayport" and da["simulated"] is False
    assert da["currency"] == "EUR" and da["bid_price"] == 31.575
    month = rows[("TTF", "Nov-26")]
    assert month["product"] == "nov-26"
    nbp = rows[("NBP", "2026-11-02")]
    # 82.5 p/th = 82.5 / 100 * 34.1214 GBP/MWh; 25,000 th/d = 732.67 MWh/d.
    assert nbp["currency"] == "GBP"
    assert nbp["bid_price"] == pytest.approx(28.150, abs=1e-3)
    assert nbp["bid_quantity_mwh"] == pytest.approx(732.675, abs=1e-2)
    assert nbp["metadata_json"]["native_unit"] == "GBp/th"
    assert nbp["metadata_json"]["native_bid"] == 82.5
    assert rows[("THE", "Sum-27")]["delivery_start_utc"].month == 4
    assert result.hubs == ["NBP", "THE", "TTF"]


def test_nbp_unit_override_and_explicit_unit_column():
    text = "timestamp,hub,product,bid,ask\n2026-10-30T09:00:00+00:00,NBP,DA,28.1,28.2\n"
    row = _parse(text, default_units={"NBP": "GBP/MWh"}).rows[0]
    assert row["bid_price"] == 28.1
    text = "timestamp,hub,product,bid,ask,unit\n2026-10-30T09:00:00Z,NBP,DA,82.5,82.8,p/th\n"
    assert _parse(text).rows[0]["currency"] == "GBP"


@pytest.mark.parametrize(
    "row",
    [
        "2026-10-30T09:00:00,TTF,DA,31,32",  # naive timestamp
        "2026-10-30T09:00:00Z,XYZ,DA,31,32",  # unknown hub
        "2026-10-30T09:00:00Z,TTF,Sep-26,31,32",  # fully delivered
        "2026-10-30T09:00:00Z,TTF,DA,33,32",  # crossed
        "2026-10-30T09:00:00Z,TTF,DA,,",  # no price
        "2026-10-30T09:00:00Z,TTF,DA,abc,32",
    ],
)
def test_bad_rows_refuse_the_file(row):
    with pytest.raises(QuoteImportError):
        _parse("timestamp,hub,product,bid,ask\n" + row + "\n")


def test_only_licensed_families_and_required_columns():
    with pytest.raises(QuoteImportError):
        parse_quote_export(
            EXPORT, source_system="EEX_Sim", source_reference="x", received_at_utc=NOW
        )
    with pytest.raises(QuoteImportError):
        _parse("timestamp,hub,bid,ask\n")
