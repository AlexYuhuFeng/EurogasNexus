"""Licensed option-settlement import: columns, validation, implied vol and the simulator."""

from __future__ import annotations

import math
from datetime import UTC, date, datetime

import pytest

from eurogas_nexus.domain.market.options import black76_price
from eurogas_nexus.ingestion.option_settlements import (
    OPTION_SETTLEMENT_SOURCES,
    OptionSettlementImportError,
    parse_option_settlements,
)
from eurogas_nexus.ingestion.simulated_option_settlements import (
    SIMULATED_OPTION_SOURCE,
    generate_simulated_option_settlements,
)

TRADE = date(2026, 11, 20)
EXPIRY = date(2026, 12, 25)  # Jan-27 under the ICE Endex TTF rule
TENOR = (EXPIRY - TRADE).days / 365.0
FORWARD = 31.4


def _settle(option_type: str, strike: float, vol: float, df: float = 1.0) -> float:
    return round(black76_price(option_type, FORWARD, strike, vol, TENOR, df), 6)


def _csv(rows: list[str], header: str) -> str:
    return header + "\n" + "\n".join(rows) + "\n"


def _ice_file(*, with_underlying: bool = True, with_expiry: bool = False) -> str:
    header = "Trade Date,Hub,Contract,Strike,Call/Put,Settlement,Open Interest"
    if with_underlying:
        header += ",Underlying"
    if with_expiry:
        header += ",Expiry"
    lines = []
    for strike in (28.0, 30.0, 31.0, 32.0, 34.0):
        for option_type in ("C", "P"):
            line = (
                f"{TRADE},TTF,Jan-27,{strike},{option_type},{_settle(option_type, strike, 0.5)},"
                f"{100 if option_type == 'C' else 60}"
            )
            if with_underlying:
                line += f",{FORWARD}"
            if with_expiry:
                line += f",{EXPIRY}"
            lines.append(line)
    return _csv(lines, header)


def test_ice_endex_file_solves_black76_without_discounting() -> None:
    result = parse_option_settlements(
        _ice_file(),
        source_system="ICE_ENDEX",
        source_reference="ice.csv",
        received_at_utc=datetime(2026, 11, 20, 19, tzinfo=UTC),
    )
    assert len(result.rows) == 10 and result.solved == 10 and not result.unsolved
    row = result.rows[0]
    assert row["contract"] == "Jan-27" and row["expiry_date"] == EXPIRY
    assert row["metadata_json"]["expiry_basis"] == "ice_endex_ttf_monthly_rule"
    assert row["premium_style"] == "futures_style"
    assert row["metadata_json"]["discount_factor"] == 1.0
    assert row["venue"] == "ICE Endex" and row["simulated"] is False
    assert row["unit"] == "EUR/MWh" and row["underlying_basis"] == "file"
    assert all(item["implied_vol"] == pytest.approx(0.5, abs=1e-5) for item in result.rows)
    assert row["iv_basis"] == "black76" and row["iv_reason"] is None
    assert row["observed_at_utc"] == datetime(2026, 11, 20, 18, tzinfo=UTC)
    assert row["metadata_json"]["official_entitlement_required"] is True


def test_underlying_from_put_call_parity_when_the_file_has_none() -> None:
    result = parse_option_settlements(
        _ice_file(with_underlying=False), source_system="ICE_ENDEX", source_reference="x"
    )
    assert {row["underlying_basis"] for row in result.rows} == {"put_call_parity"}
    assert result.rows[0]["underlying_price"] == pytest.approx(FORWARD, abs=1e-5)
    assert result.solved == 10


def test_stored_futures_settlement_is_used_before_parity() -> None:
    result = parse_option_settlements(
        _ice_file(with_underlying=False),
        source_system="ICE_ENDEX",
        source_reference="x",
        underlying_prices={("TTF", "Jan-27", TRADE): FORWARD},
    )
    assert {row["underlying_basis"] for row in result.rows} == {"futures_settlement"}


def test_exchange_volatility_is_preferred_and_compared() -> None:
    text = (
        "trade_date,hub,contract,expiry,strike,option_type,settlement,underlying,implied_vol\n"
        f"{TRADE},TTF,Jan-27,{EXPIRY},31,C,{_settle('C', 31.0, 0.5)},{FORWARD},53.5\n"
    )
    result = parse_option_settlements(text, source_system="ICE_ENDEX", source_reference="x")
    row = result.rows[0]
    assert row["iv_basis"] == "exchange" and row["implied_vol"] == pytest.approx(0.535)
    assert row["metadata_json"]["solved_iv"] == pytest.approx(0.5, abs=1e-6)
    assert row["metadata_json"]["iv_mismatch_vol_pts"] == pytest.approx(-3.5, abs=1e-3)
    assert result.warnings and "vol points" in result.warnings[0]


def test_premium_style_options_are_discounted_with_the_rate_source() -> None:
    rate_pct = 2.0
    df = math.exp(-rate_pct / 100 * TENOR)
    text = (
        "trade_date,hub,contract,expiry,strike,option_type,settlement,underlying,style\n"
        f"{TRADE},TTF,Jan-27,{EXPIRY},31,C,{_settle('C', 31.0, 0.6, df)},{FORWARD},premium\n"
    )
    result = parse_option_settlements(
        text,
        source_system="CME",
        source_reference="x",
        discount_rate=lambda currency, day: (
            (rate_pct, f"ESTR {day}") if currency == "EUR" else None
        ),
    )
    row = result.rows[0]
    assert row["implied_vol"] == pytest.approx(0.6, abs=1e-6)
    assert row["metadata_json"]["discount_rate"]["reference"] == f"ESTR {TRADE}"
    without_rate = parse_option_settlements(text, source_system="CME", source_reference="x")
    assert without_rate.rows[0]["implied_vol"] is None
    assert without_rate.rows[0]["iv_reason"] == "no_discount_rate"
    assert without_rate.unsolved == {"no_discount_rate": 1}


def test_nbp_options_keep_pence_per_therm() -> None:
    text = (
        "trade_date,hub,contract,expiry,strike,option_type,settlement,underlying,style\n"
        f"{TRADE},NBP,Jan-27,2026-12-24,80,P,3.1,79.5,futures_style\n"
    )
    row = parse_option_settlements(text, source_system="ICE_ENDEX", source_reference="x").rows[0]
    assert row["unit"] == "GBp/th" and row["currency"] == "GBp"
    assert row["implied_vol"] is not None


def test_a_settlement_without_time_value_is_stored_with_its_reason() -> None:
    text = (
        "trade_date,hub,contract,expiry,strike,option_type,settlement,underlying\n"
        f"{TRADE},TTF,Jan-27,{EXPIRY},20,P,0,{FORWARD}\n"
    )
    result = parse_option_settlements(text, source_system="EEX", source_reference="x")
    assert result.rows[0]["implied_vol"] is None
    assert result.rows[0]["iv_reason"] == "at_intrinsic"
    assert result.unsolved == {"at_intrinsic": 1}


HEADER = "trade_date,hub,contract,expiry,strike,option_type,settlement,underlying"


@pytest.mark.parametrize(
    ("body", "message"),
    [
        (f"{TRADE},TTF,Jan-27,{EXPIRY},31,X,1.0,31", "option_type must be C, Call, P or Put"),
        (f"{TRADE},TTF,Jan-27,{EXPIRY},-1,C,1.0,31", "strike must be a positive number"),
        (f"{TRADE},TTF,Jan-27,{EXPIRY},31,C,-0.1,31", "settlement cannot be negative"),
        (f"{TRADE},TTF,Jan-27,{EXPIRY},31,C,abc,31", "settlement 'abc' is not a number"),
        (f"{TRADE},XYZ,Jan-27,{EXPIRY},31,C,1.0,31", "hub 'XYZ' is not a gas hub"),
        (f"{TRADE},TTF,DA,{EXPIRY},31,C,1.0,31", "gas options are listed on month"),
        (f"{TRADE},TTF,Jan-27,2026-11-01,31,C,1.0,31", "is before the trade date"),
        ("20/11/2026,TTF,Jan-27,2026-12-24,31,C,1.0,31", "is not YYYY-MM-DD"),
        (f"{TRADE},TTF,Jan-27,{EXPIRY},31,C,1.0,0", "underlying must be positive"),
    ],
)
def test_bad_rows_refuse_the_whole_file_with_the_line(body: str, message: str) -> None:
    with pytest.raises(OptionSettlementImportError, match="line 2: .*") as caught:
        parse_option_settlements(_csv([body], HEADER), source_system="EEX", source_reference="x")
    assert message in str(caught.value)


def test_file_level_refusals() -> None:
    with pytest.raises(OptionSettlementImportError, match="missing a 'strike' column"):
        parse_option_settlements(
            "trade_date,hub,contract,option_type,settlement\n",
            source_system="EEX",
            source_reference="x",
        )
    with pytest.raises(OptionSettlementImportError, match="no option rows"):
        parse_option_settlements(HEADER + "\n", source_system="EEX", source_reference="x")
    with pytest.raises(OptionSettlementImportError, match="is not one of"):
        parse_option_settlements(_ice_file(), source_system="ICE_ENDEX_Sim", source_reference="x")
    duplicate = _csv(
        [f"{TRADE},TTF,Jan-27,{EXPIRY},31,C,1.0,31", f"{TRADE},TTF,Jan-27,{EXPIRY},31,C,1.1,31"],
        HEADER,
    )
    with pytest.raises(OptionSettlementImportError, match="line 3: duplicate .*first on line 2"):
        parse_option_settlements(duplicate, source_system="EEX", source_reference="x")
    conflicting = _csv(
        [f"{TRADE},TTF,Jan-27,{EXPIRY},31,C,1.0,31", f"{TRADE},TTF,Jan-27,{EXPIRY},32,C,1.0,31.5"],
        HEADER,
    )
    with pytest.raises(OptionSettlementImportError, match="conflicting underlying"):
        parse_option_settlements(conflicting, source_system="EEX", source_reference="x")


def test_expiry_and_style_are_required_where_no_rule_is_documented() -> None:
    no_expiry = (
        "trade_date,hub,contract,strike,option_type,settlement,underlying\n"
        f"{TRADE},TTF,Jan-27,31,C,1.0,31\n"
    )
    with pytest.raises(OptionSettlementImportError, match="expiry is required"):
        parse_option_settlements(no_expiry, source_system="EEX", source_reference="x")
    no_style = _csv([f"{TRADE},TTF,Jan-27,{EXPIRY},31,C,1.0,31"], HEADER)
    with pytest.raises(OptionSettlementImportError, match="no documented premium style"):
        parse_option_settlements(no_style, source_system="CME", source_reference="x")


def test_licensed_sources_cover_exchanges_and_vendors() -> None:
    assert {"ICE_ENDEX", "EEX", "CME"} <= set(OPTION_SETTLEMENT_SOURCES)
    assert not any(name.endswith("_Sim") for name in OPTION_SETTLEMENT_SOURCES)


def test_simulated_settlements_are_flagged_and_priced_consistently() -> None:
    result = generate_simulated_option_settlements(date(2026, 11, 16), date(2026, 11, 20))
    assert result.rows and result.hubs == ["TTF"]
    assert {row["source_system"] for row in result.rows} == {SIMULATED_OPTION_SOURCE}
    assert all(row["simulated"] is True for row in result.rows)
    assert all(row["metadata_json"]["simulated"] is True for row in result.rows)
    assert all(row["freshness"] == "simulated_daily" for row in result.rows)
    assert all(row["source_reference"].startswith("sim:ICE_ENDEX_Sim") for row in result.rows)
    # Most strikes carry time value above the settlement tick and solve.
    assert result.solved > 0.8 * len(result.rows)
    assert {row["trade_date"].weekday() for row in result.rows} <= {0, 1, 2, 3, 4}


def test_an_unchanged_reimport_keeps_the_first_receipt_time() -> None:
    """Dataset builds read ``ingested_at_utc`` as ``available_at``; an identical file again
    must not move it later, while a changed value takes the new receipt."""

    from types import SimpleNamespace

    import scripts.ops.import_option_settlements as script

    first = datetime(2026, 11, 20, 18, 0, tzinfo=UTC)
    again = datetime(2026, 11, 22, 18, 0, tzinfo=UTC)
    row = {"settlement_id": "s1", "settlement_price": 1.25, "strike": 30.0, "ingested_at_utc": again}

    class Session:
        def __init__(self, stored):
            self.stored = stored

        def get(self, _model, key):
            return self.stored if key == "s1" else None

    stored = SimpleNamespace(settlement_id="s1", settlement_price=1.25, strike=30.0, ingested_at_utc=first)
    assert script.keep_first_receipt(Session(stored), row)["ingested_at_utc"] == first
    changed = SimpleNamespace(settlement_id="s1", settlement_price=1.30, strike=30.0, ingested_at_utc=first)
    assert script.keep_first_receipt(Session(changed), row)["ingested_at_utc"] == again
    assert script.keep_first_receipt(Session(None), row)["ingested_at_utc"] == again
