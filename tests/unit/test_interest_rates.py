"""Benchmark interest rates: administrator formats, fixing selection, day counts."""

from __future__ import annotations

import json
from datetime import date

import pytest

from eurogas_nexus.domain.market.interest_rates import (
    InterestRateError,
    RateFixing,
    benchmark,
    parse_boe_sonia_csv,
    parse_ecb_estr_csv,
    parse_nyfed_sofr_json,
    resolve_financing_rate,
    simple_interest,
)

# Shapes follow each administrator's documented export format.
BOE_CSV = "DATE,IUDSOIA\n28 Oct 2026,4.7012\n29 Oct 2026,4.7034\n30 Oct 2026,\n"
ECB_CSV = (
    "KEY,FREQ,REF_AREA,TIME_PERIOD,OBS_VALUE,OBS_STATUS\n"
    "EST.B.EU000A2X2A25.WT,B,EU,2026-10-28,1.912,A\n"
    "EST.B.EU000A2X2A25.WT,B,EU,2026-10-29,1.915,A\n"
)
NYFED_JSON = json.dumps(
    {
        "refRates": [
            {"effectiveDate": "2026-10-29", "type": "SOFR", "percentRate": 3.86},
            {"effectiveDate": "2026-10-28", "type": "SOFR", "percentRate": 3.84},
        ]
    }
)


def test_parse_administrator_formats():
    sonia = parse_boe_sonia_csv(BOE_CSV)
    assert [(f.value_date, f.rate_pct) for f in sonia] == [
        (date(2026, 10, 28), 4.7012),
        (date(2026, 10, 29), 4.7034),
    ]
    assert sonia[0].source_system == "BOE"
    estr = parse_ecb_estr_csv(ECB_CSV)
    assert estr[-1].rate_pct == 1.915 and estr[-1].source_system == "ECB"
    sofr = parse_nyfed_sofr_json(NYFED_JSON)
    assert [f.value_date.day for f in sofr] == [28, 29]
    assert sofr[0].as_record()["day_count"] == "ACT/360"


@pytest.mark.parametrize(
    ("parser", "payload"),
    [
        (parse_boe_sonia_csv, "DATE,XYZ\n28 Oct 2026,1\n"),
        (parse_boe_sonia_csv, "DATE,IUDSOIA\n2026-10-28,1\n"),
        (parse_boe_sonia_csv, "DATE,IUDSOIA\n28 Oct 2026,99\n"),
        (parse_ecb_estr_csv, "TIME_PERIOD,OBS_VALUE\n"),
        (parse_nyfed_sofr_json, "not json"),
        (parse_nyfed_sofr_json, json.dumps({"refRates": [
            {"effectiveDate": "2026-10-29", "percentRate": 3.8},
            {"effectiveDate": "2026-10-29", "percentRate": 3.9},
        ]})),
    ],
)
def test_parsers_refuse_bad_payloads(parser, payload):
    with pytest.raises(InterestRateError):
        parser(payload)


def test_resolve_uses_latest_fixing_on_or_before_and_adds_spread():
    fixings = parse_boe_sonia_csv(BOE_CSV)
    # Saturday 31 Oct carries Thursday's published fixing (29 Oct).
    rate = resolve_financing_rate(fixings, "sonia", as_of=date(2026, 10, 31), spread_bps=150)
    assert rate.fixing_date == date(2026, 10, 29)
    assert rate.all_in_pct == pytest.approx(6.2034)
    assert rate.all_in_act365_pct == pytest.approx(6.2034)
    assert rate.day_count == "ACT/365F" and rate.staleness_days == 2
    assert "Bank of England" in rate.attribution


def test_act360_benchmarks_restate_on_act365():
    rate = resolve_financing_rate(
        parse_ecb_estr_csv(ECB_CSV), "€STR", as_of=date(2026, 10, 29), spread_bps=100
    )
    assert rate.all_in_pct == pytest.approx(2.915)
    assert rate.all_in_act365_pct == pytest.approx(2.915 * 365 / 360)
    # Same money: interest over 30 days is identical on either basis.
    assert simple_interest(1_000_000, rate.all_in_pct, 30, 360) == pytest.approx(
        simple_interest(1_000_000, rate.all_in_act365_pct, 30, 365)
    )


def test_resolve_refuses_missing_stale_and_unknown():
    fixings = [RateFixing("SOFR", date(2026, 10, 1), 3.9, "NYFED", "t")]
    with pytest.raises(InterestRateError):
        resolve_financing_rate(fixings, "SOFR", as_of=date(2026, 9, 30))
    with pytest.raises(InterestRateError, match="ingest newer"):
        resolve_financing_rate(fixings, "SOFR", as_of=date(2026, 10, 20))
    with pytest.raises(InterestRateError):
        resolve_financing_rate(fixings, "LIBOR", as_of=date(2026, 10, 2))
    with pytest.raises(InterestRateError):
        resolve_financing_rate(fixings, "SOFR", as_of=date(2026, 10, 2), spread_bps=99999)
    assert benchmark("EUR STR").benchmark_id == "ESTR"
