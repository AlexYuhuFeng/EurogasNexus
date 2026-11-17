"""Valuation inputs (CP-07): classes, periods, assumptions, firm marks, snapshot replay."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from eurogas_nexus.domain.valuation.assumptions import (
    ASSUMPTION_CATALOGUE,
    AssumptionError,
    AssumptionValue,
    changed_keys,
    validate_assumption_value,
    values_digest,
)
from eurogas_nexus.domain.valuation.firm_marks import (
    FIRM_MARK_CLASS,
    FirmMark,
    FirmMarkError,
    validate_firm_mark,
)
from eurogas_nexus.domain.valuation.periods import DeliveryPeriod, PeriodError
from eurogas_nexus.domain.valuation.quality import InputClass, weakest
from eurogas_nexus.domain.valuation.snapshot import (
    FixtureReader,
    InputKind,
    ReplayReader,
    SnapshotInput,
    dependency_key,
    price_key,
    tariff_key,
)

AS_OF = datetime(2026, 11, 17, 9, 42, tzinfo=UTC)
JAN27 = DeliveryPeriod.month(2027, 1)


def test_the_weakest_input_decides_the_grade() -> None:
    assert weakest([InputClass.SOURCED, InputClass.SOURCED]) is InputClass.SOURCED
    assert weakest(["sourced", "firm_mark"]) is InputClass.FIRM_MARK
    assert weakest([InputClass.SOURCED, InputClass.SIMULATED]) is InputClass.SIMULATED
    assert weakest([InputClass.DERIVED, InputClass.INDICATIVE]) is InputClass.INDICATIVE
    assert weakest([InputClass.ASSUMPTION, InputClass.MISSING]) is InputClass.MISSING
    assert weakest([]) is InputClass.MISSING


def test_a_firm_mark_is_weaker_than_a_sourced_price_and_never_sourced() -> None:
    entry = validate_firm_mark("ttf", "2027-01", "31.20", "EUR/MWh")
    mark = FirmMark(
        mark_id="m1",
        hub=entry.hub,
        period=entry.period,
        value=entry.value,
        unit=entry.unit,
        currency=entry.currency,
        entered_by="trader",
        entered_at_utc=AS_OF,
    )
    assert mark.input_class is InputClass.FIRM_MARK is FIRM_MARK_CLASS
    assert weakest([InputClass.SOURCED, mark.input_class]) is InputClass.FIRM_MARK
    assert "input_class" not in FirmMark.__dataclass_fields__  # no field can make it sourced


@pytest.mark.parametrize(
    ("hub", "period", "value", "unit", "code"),
    [
        ("XYZ", "2027-01", 30, "EUR/MWh", "unknown_hub"),
        ("TTF", "Jan-27", 30, "EUR/MWh", "period_invalid"),
        ("TTF", "2027-01", 30, "EUR/bbl", "unit_invalid"),
        ("TTF", "2027-01", "abc", "EUR/MWh", "value_not_a_number"),
        ("TTF", "2027-01", 99999, "EUR/MWh", "value_implausible"),
    ],
)
def test_firm_mark_refusals(hub, period, value, unit, code) -> None:
    with pytest.raises(FirmMarkError) as caught:
        validate_firm_mark(hub, period, value, unit)
    assert caught.value.code == code


def test_nbp_marks_keep_the_native_unit() -> None:
    entry = validate_firm_mark("NBP", "2027-01", "78.00", "p/th")
    assert (entry.unit, entry.currency) == ("GBp/th", "GBP")


def test_delivery_periods() -> None:
    assert (JAN27.start, JAN27.end, JAN27.days, JAN27.kind) == (
        date(2027, 1, 1),
        date(2027, 2, 1),
        31,
        "month",
    )
    q4 = DeliveryPeriod.parse("2026-Q4")
    assert (q4.start, q4.end) == (date(2026, 10, 1), date(2027, 1, 1))
    win = DeliveryPeriod.parse("win-27")
    assert (win.start, win.end, win.label) == (date(2027, 10, 1), date(2028, 4, 1), "WIN-27")
    day = DeliveryPeriod.parse("2026-11-18")
    assert (day.days, day.kind) == (1, "day")
    with pytest.raises(PeriodError):
        DeliveryPeriod.parse("2027-13")


def test_assumption_values_are_typed_and_bounded() -> None:
    hire = validate_assumption_value("lng.charter_hire", "174000", currency="usd")
    assert (hire.unit, hire.currency, hire.value) == ("USD/day", "USD", Decimal("174000"))
    load = validate_assumption_value("capacity.load_factor", 80, range_low=60, range_high=100)
    assert (load.unit, load.currency) == ("%", None)
    for args, kwargs, code in (
        (("unknown.key", 1), {}, "unknown_assumption_key"),
        (("lng.charter_hire", 1), {}, "currency_required"),
        (("capacity.load_factor", 80), {"currency": "EUR"}, "currency_not_applicable"),
        (("capacity.load_factor", 120), {}, "value_out_of_bounds"),
        (("capacity.load_factor", 80), {"range_low": 90, "range_high": 70}, "range_inverted"),
        (("capacity.load_factor", 50), {"range_low": 60, "range_high": 90}, "value_outside_range"),
        (("financing.rate", "nan"), {}, "value_not_a_number"),
    ):
        with pytest.raises(AssumptionError) as caught:
            validate_assumption_value(*args, **kwargs)
        assert caught.value.code == code
    assert "financing.rate" in ASSUMPTION_CATALOGUE


def test_the_audit_digest_changes_with_values_but_never_shows_them() -> None:
    first = [AssumptionValue("financing.rate", Decimal("3.0"), "%/yr")]
    second = [AssumptionValue("financing.rate", Decimal("3.5"), "%/yr")]
    assert values_digest(first) != values_digest(second)
    assert "3.5" not in values_digest(second)
    assert changed_keys(first, second) == ["financing.rate"]
    assert changed_keys(first, first) == []


def _inputs() -> list[SnapshotInput]:
    return [
        SnapshotInput(
            key=price_key("TTF", JAN27, "ask"),
            kind=InputKind.PRICE,
            input_class=InputClass.SOURCED,
            value=Decimal("30.00"),
            unit="EUR/MWh",
            currency="EUR",
            as_of_utc=AS_OF,
            source_family="ICE_ENDEX",
            source_ref="q-1",
        ),
        SnapshotInput(
            key=tariff_key("ITP-00063", "EXIT", "FIRM_MONTH", JAN27),
            kind=InputKind.TARIFF,
            input_class=InputClass.SOURCED,
            value=Decimal("0.0101"),
            unit="EUR/(kWh/h)/d",
            currency="EUR",
            as_of_utc=AS_OF,
            source_family="ENTSOG",
            source_ref="t-1",
            detail={"document_id": "doc-1"},
        ),
    ]


def test_a_reader_records_each_key_once_and_misses_are_recorded_too() -> None:
    reader = FixtureReader(_inputs(), as_of_utc=AS_OF)
    first = reader.price("TTF", JAN27, "ask")
    again = reader.price("ttf", JAN27, "ask")
    assert first is again and first.value == Decimal("30.00")
    gap = reader.price("THE", JAN27, "bid")
    assert gap.input_class is InputClass.MISSING and not gap.held
    assert [item.key for item in reader.inputs()] == [
        "price:TTF:2027-01:ask",
        "price:THE:2027-01:bid",
    ]


def test_a_snapshot_replays_to_identical_inputs_and_digest() -> None:
    reader = FixtureReader(_inputs(), as_of_utc=AS_OF)
    reader.price("TTF", JAN27, "ask")
    reader.tariff("ITP-00063", "exit", "firm_month", JAN27)
    reader.price("THE", JAN27, "bid")
    manifest = reader.manifest("vsnap-test")
    rebuilt = type(manifest)(
        snapshot_id=manifest.snapshot_id,
        as_of_utc=manifest.as_of_utc,
        demo_desk=manifest.demo_desk,
        fx_method=manifest.fx_method,
        assumption_version=manifest.assumption_version,
        inputs=tuple(SnapshotInput.from_json(item.to_json()) for item in manifest.inputs),
    )
    assert rebuilt.digest() == manifest.digest()
    replay = ReplayReader(rebuilt)
    assert replay.price("TTF", JAN27, "ask") == reader.price("TTF", JAN27, "ask")
    assert replay.price("THE", JAN27, "bid").input_class is InputClass.MISSING
    assert replay.replay_misses == []
    replay.price("NBP", JAN27, "bid")
    assert replay.replay_misses == ["price:NBP:2027-01:bid"]
    assert manifest.summary()["tariff_documents"] == ["doc-1"]
    assert manifest.quality is InputClass.SOURCED


def test_dependency_keys_follow_the_design() -> None:
    price, tariff = _inputs()
    assert dependency_key(price) == "hub:TTF:2027-01"
    assert dependency_key(tariff) == "tariff:ITP-00063:EXIT:FIRM_MONTH:2026/27"
