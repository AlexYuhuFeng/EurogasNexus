"""Settlement imports for carbon, coal, power and gas; EIA Henry Hub parsing."""

import json
from datetime import date

import pytest

from eurogas_nexus.ingestion.commodity_settlements import (
    SettlementImportError,
    parse_settlements,
)
from eurogas_nexus.ingestion.eia import EiaParseError, parse_prices, request_url


def test_settlements_use_market_conventions_and_front_months():
    text = (
        "Date,Market,Product,Settlement,Volume\n"
        "2026-10-29,EUA,Dec-26,71.85,12000\n"
        "2026-10-29,API2,Dec-26,98.50,\n"
        "2026-10-29,NBP,Dec-26,95.10,\n"
        "2026-10-29,TTF,Dec-26,32.40,\n"
    )
    result = parse_settlements(text, source_system="ICE_ENDEX", source_reference="ice.csv")
    by_market = {row["metadata_json"]["hub"]: row for row in result.rows}
    assert by_market["EUA"]["unit"] == "EUR/t" and by_market["EUA"]["price"] == 71.85
    assert by_market["API2"]["unit"] == "USD/t" and by_market["API2"]["currency"] == "USD"
    # p/th stored per MWh in GBP, native value kept.
    assert by_market["NBP"]["unit"] == "GBP/MWh"
    assert by_market["NBP"]["metadata_json"]["native"] == {"price": 95.1, "unit": "GBp/th"}
    assert by_market["TTF"]["product"] == "TTF Dec-26"
    assert by_market["EUA"]["metadata_json"]["volume"] == 12000
    assert result.first_day == date(2026, 10, 29)


def test_settlements_refuse_wrong_currency_unknown_market_and_bad_source():
    with pytest.raises(SettlementImportError, match="quotes in EUR"):
        parse_settlements(
            "date,market,product,settlement,unit\n2026-10-29,EUA,Dec-26,70,USD/t\n",
            source_system="EEX",
            source_reference="x",
        )
    with pytest.raises(SettlementImportError, match="reference model"):
        parse_settlements(
            "date,market,product,settlement\n2026-10-29,XYZ,Dec-26,1\n",
            source_system="EEX",
            source_reference="x",
        )
    with pytest.raises(SettlementImportError, match="source"):
        parse_settlements(
            "date,market,product,settlement\n", source_system="Free", source_reference="x"
        )


def test_eia_henry_hub_parse_and_url_never_logs_without_key():
    payload = json.dumps(
        {
            "response": {
                "data": [
                    {
                        "period": "2026-10-27",
                        "series": "RNGWHHD",
                        "value": "2.91",
                        "units": "$/MMBTU",
                    },
                    {
                        "period": "2026-10-28",
                        "series": "RNGWHHD",
                        "value": None,
                        "units": "$/MMBTU",
                    },
                ]
            }
        }
    )
    (price,) = parse_prices(payload)
    assert price.day == date(2026, 10, 27) and price.price == 2.91 and price.unit == "USD/MMBtu"
    record = price.as_record(source_reference="eia:test")
    assert record["source_system"] == "EIA" and record["metadata_json"]["hub"] == "HH"
    assert "api_key=k" in request_url("k", date(2026, 10, 1))
    with pytest.raises(EiaParseError):
        parse_prices(b"<html>")
