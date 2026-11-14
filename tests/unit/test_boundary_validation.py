"""ONT-03: one boundary check of unit, hub, product and period; every refusal has a code."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime

import pytest

from eurogas_nexus.domain.observations.remit_umm import UmmParseError, parse_umm_export
from eurogas_nexus.domain.ontology.boundary import (
    BoundaryReason,
    check_boundary,
    check_contract,
)
from eurogas_nexus.ingestion.commodity_settlements import (
    SettlementImportError,
    parse_settlements,
)
from eurogas_nexus.ingestion.etrm_trades import EtrmImportError, parse_etrm_trades
from eurogas_nexus.ingestion.licensed_quote_import import (
    QuoteImportError,
    parse_quote_export,
)


def _codes(check) -> list[str]:
    return [issue.code.value for issue in check.issues]


@pytest.mark.parametrize(
    ("kwargs", "code"),
    [
        ({"market": "XYZ"}, BoundaryReason.MARKET_UNKNOWN),
        ({"market": "EUA", "gas_hub_required": True}, BoundaryReason.HUB_NOT_GAS),
        ({"hub_text": "Rotterdam, Netherlands"}, BoundaryReason.HUB_UNRESOLVED),
        ({"price_unit": "EUR/furlong"}, BoundaryReason.UNIT_UNKNOWN),
        ({"quantity_unit": "bbl/d", "allowed_quantity_units": ("MWh",)},
         BoundaryReason.UNIT_NOT_ALLOWED),
        ({"market": "NBP", "price_unit": "EUR/MWh"}, BoundaryReason.UNIT_CURRENCY_MISMATCH),
        ({"product": "", "product_required": True}, BoundaryReason.PRODUCT_MISSING),
        ({"product": "Zap-99", "product_strict": True, "trade_date": date(2026, 11, 14)},
         BoundaryReason.PRODUCT_UNRECOGNISED),
        ({"period_start": None, "period_end": None, "period_required": True},
         BoundaryReason.PERIOD_MISSING),
        ({"period_start": date(2026, 11, 2), "period_end": date(2026, 11, 1)},
         BoundaryReason.PERIOD_REVERSED),
    ],
)
def test_each_reason_code(kwargs, code) -> None:
    check = check_boundary(**kwargs)
    assert _codes(check) == [code.value]
    assert f"[{code.value}]" in check.first.text()


def test_valid_rows_pass_and_resolve() -> None:
    check = check_boundary(
        market="TTF", gas_hub_required=True, price_unit="EUR/MWh", quantity_unit="MWh",
        product="Dec-26", product_strict=True, trade_date=date(2026, 11, 14),
        period_start=date(2026, 12, 1), period_end=date(2026, 12, 31),
    )
    assert check.ok and check.hub == "TTF"
    assert check_boundary(market="NBP", price_unit="GBp/th").ok  # pence per therm is GBP


def test_settlement_refusals_carry_the_code() -> None:
    header = "date,market,product,settlement,unit\n"
    with pytest.raises(SettlementImportError, match=r"not in the reference model") as exc:
        parse_settlements(header + "2026-11-13,XYZ,Dec-26,1.0,\n",
                          source_system="EEX", source_reference="t")
    assert exc.value.reason_code == "market_unknown"
    with pytest.raises(SettlementImportError) as exc:
        parse_settlements(header + "2026-11-13,TTF,Dec-26,1.0,GBP/MWh\n",
                          source_system="EEX", source_reference="t")
    assert exc.value.reason_code == "unit_currency_mismatch"
    with pytest.raises(SettlementImportError) as exc:
        parse_settlements(header + "2026-11-13,TTF,,1.0,\n",
                          source_system="EEX", source_reference="t")
    assert exc.value.reason_code == "product_missing"
    # A free settlement label accepted before is still accepted.
    ok = parse_settlements(header + "2026-11-13,EUA,Dec-26 Spec,80.1,\n",
                           source_system="EEX", source_reference="t")
    assert len(ok.rows) == 1


ETRM_HEADER = (
    "trade_id,book_id,hub,side,delivery_start,delivery_end,quantity,quantity_unit,"
    "price,price_unit\n"
)


@pytest.mark.parametrize(
    ("row", "code"),
    [
        ("T1,B,EUA,BUY,2026-12-01,2026-12-31,10,MWh/d,30,EUR/MWh", "hub_not_a_gas_hub"),
        ("T1,B,XYZ,BUY,2026-12-01,2026-12-31,10,MWh/d,30,EUR/MWh", "market_unknown"),
        ("T1,B,TTF,BUY,2026-12-31,2026-12-01,10,MWh/d,30,EUR/MWh", "period_reversed"),
        ("T1,B,TTF,BUY,2026-12-01,2026-12-31,10,bbl/d,30,EUR/MWh", "unit_not_allowed"),
        ("T1,B,TTF,BUY,2026-12-01,2026-12-31,10,MWh/d,30,GBP/MWh", "unit_currency_mismatch"),
    ],
)
def test_etrm_refusals_carry_the_code(row, code) -> None:
    with pytest.raises(EtrmImportError) as exc:
        parse_etrm_trades(ETRM_HEADER + row + "\n", system="X", source_reference="t")
    assert exc.value.reason_code == code and f"[{code}]" in str(exc.value)


def test_quote_import_refusals_carry_the_code() -> None:
    header = "timestamp,hub,product,bid,ask\n"
    received = datetime(2026, 11, 14, 9, tzinfo=UTC)
    with pytest.raises(QuoteImportError) as exc:
        parse_quote_export(
            header + "2026-11-14T09:00:00+00:00,EUA,Dec-26,1,2\n",
            source_system=_quote_source(), source_reference="t", received_at_utc=received,
        )
    assert exc.value.reason_code == "hub_not_a_gas_hub"
    with pytest.raises(QuoteImportError) as exc:
        parse_quote_export(
            header + "2026-11-14T09:00:00+00:00,TTF,Zap-99,1,2\n",
            source_system=_quote_source(), source_reference="t", received_at_utc=received,
        )
    assert exc.value.reason_code == "product_unrecognised"


def _quote_source() -> str:
    from eurogas_nexus.ingestion.licensed_quote_import import LICENSED_QUOTE_SOURCES

    return sorted(LICENSED_QUOTE_SOURCES)[0]


def _umm(stop: str) -> str:
    return json.dumps([
        {"message_id": "M1", "event_start": "2026-11-14T06:00:00Z", "event_stop": stop,
         "unit": "GWh/d", "unavailable_capacity": 10},
        {"message_id": "M2", "event_start": "2026-11-14T06:00:00Z",
         "event_stop": "2026-11-15T06:00:00Z", "unit": "GWh/d", "unavailable_capacity": 5},
    ])


def test_a_remit_file_with_a_reversed_event_is_refused_with_its_code() -> None:
    with pytest.raises(UmmParseError) as exc:
        parse_umm_export(_umm("2026-11-13T06:00:00Z"), source_reference="t")
    assert exc.value.reason_code == "period_reversed" and "M1" in str(exc.value)


def test_the_collector_quarantines_the_one_bad_message_and_keeps_the_rest() -> None:
    quarantined: list[dict] = []
    messages = parse_umm_export(
        _umm("2026-11-13T06:00:00Z"), source_reference="t", quarantine=quarantined
    )
    assert [m.message_id for m in messages] == ["M2"]
    assert quarantined[0]["message_id"] == "M1"
    assert quarantined[0]["reason"] == "period_reversed"


def test_contract_save_reports_hub_and_gas_year_with_codes() -> None:
    check = check_contract(
        delivery_point_name="Rotterdam, Netherlands", gas_year="next year", price_currency="EUR"
    )
    assert _codes(check) == ["hub_unresolved", "period_missing"]
    assert check_contract(
        delivery_point_name="TTF", gas_year="2026/27", price_currency="EUR"
    ).ok
    mapped = check_contract(
        delivery_point_name="Rotterdam, Netherlands", gas_year="GY-26", price_currency="EUR",
        hub_points={"ROTTERDAM": "TTF"},
    )
    assert mapped.ok and mapped.hub == "TTF"
