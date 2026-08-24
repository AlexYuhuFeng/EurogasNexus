"""Semantic Kernel v1 value-object tests."""

from datetime import UTC, date, datetime

from eurogas_nexus.domain.ontology.semantic_kernel import (
    EU_JURISDICTION,
    ExternalIdentifier,
    FxConversionRef,
    GasDayRef,
    GasYearRef,
    Measure,
    Money,
    PriceBasis,
    TimeInterval,
    applicable_instrument,
    current_ontology_version,
    gas_day_calendar_versions,
    money_triple_valid,
)


def test_measure_keeps_unit_and_reference_conditions() -> None:
    measure = Measure(value=1_000.0, unit="mcm", reference_conditions="25C/101.325kPa")
    assert measure.unit == "mcm"
    assert measure.reference_conditions == "25C/101.325kPa"


def test_money_and_price_basis_carry_currency() -> None:
    money = Money(amount=31.4, currency="EUR")
    basis = PriceBasis(money=money, unit="EUR/MWh", venue="TTF")
    assert basis.money.currency == "EUR"
    assert basis.unit == "EUR/MWh"


def test_fx_conversion_ref_records_as_of_provenance() -> None:
    fx = FxConversionRef(
        from_currency="EUR",
        to_currency="GBP",
        rate=0.85,
        observation_id="fx-eur-gbp",
        value_date=date(2026, 7, 1),
    )
    assert fx.rate == 0.85
    assert fx.value_date == date(2026, 7, 1)


def test_external_identifier_active_on() -> None:
    identifier = ExternalIdentifier(
        identifier="THE",
        scheme="HUB_CODE",
        valid_from=date(2021, 10, 1),
        valid_to=date(2026, 12, 31),
    )
    assert identifier.active_on(date(2024, 1, 1)) is True
    assert identifier.active_on(date(2020, 1, 1)) is False
    assert identifier.active_on(date(2027, 1, 1)) is False


def test_time_interval_contains_is_half_open() -> None:
    interval = TimeInterval(
        start_utc=datetime(2026, 7, 1, 3, 0, tzinfo=UTC),
        end_utc=datetime(2026, 7, 2, 3, 0, tzinfo=UTC),
    )
    assert interval.contains(datetime(2026, 7, 1, 12, 0, tzinfo=UTC)) is True
    assert interval.contains(datetime(2026, 7, 1, 3, 0, tzinfo=UTC)) is True
    assert interval.contains(datetime(2026, 7, 2, 3, 0, tzinfo=UTC)) is False


def test_gas_day_ref_uses_versioned_cam_calendar() -> None:
    ref = GasDayRef.containing(datetime(2025, 1, 15, 12, 0, tzinfo=UTC))
    assert ref.calendar_version == "EU-CAM-2025"
    assert ref.start_utc == datetime(2025, 1, 15, 4, 0, tzinfo=UTC)
    assert ref.end_utc == datetime(2025, 1, 16, 4, 0, tzinfo=UTC)
    assert ref.label == "2025-01-15"

    summer = GasDayRef.containing(datetime(2025, 7, 15, 12, 0, tzinfo=UTC))
    assert summer.start_utc == datetime(2025, 7, 15, 3, 0, tzinfo=UTC)


def test_gas_year_ref_boundaries() -> None:
    year = GasYearRef.containing(datetime(2025, 6, 1, tzinfo=UTC))
    assert year.year == 2024
    assert year.start_utc == datetime(2024, 10, 1, 5, 0, tzinfo=UTC)
    assert year.end_utc == datetime(2025, 10, 1, 5, 0, tzinfo=UTC)


def test_jurisdiction_carries_recast_instruments() -> None:
    instrument_ids = {i.instrument_id for i in EU_JURISDICTION.instruments}
    assert "REG-2024-1789" in instrument_ids  # recast of 715/2009
    assert "REG-2024-1106" in instrument_ids  # REMIT amendment
    assert "REG-2017-459" in instrument_ids  # CAM
    assert "REG-2015-703" in instrument_ids  # interoperability


def test_applicable_instrument_resolves_supersession() -> None:
    # After the recast effective date, 2009/715 resolves to 2024/1789.
    resolved = applicable_instrument("REG-2009-715", date(2025, 1, 1))
    assert resolved is not None
    assert resolved.instrument_id == "REG-2024-1789"
    assert resolved.supersedes == "REG-2009-715"


def test_applicable_instrument_respects_effective_from() -> None:
    before = applicable_instrument("REG-2024-1789", date(2024, 1, 1))
    assert before is None
    after = applicable_instrument("REG-2024-1789", date(2024, 9, 1))
    assert after is not None


def test_ontology_version_is_v0_3() -> None:
    assert current_ontology_version().label() == "v0.3.0"


def test_gas_day_calendar_versions_exposed() -> None:
    versions = gas_day_calendar_versions()
    assert "EU-CAM-2025" in versions
    assert "UK-NBP-LEGACY" in versions


def test_money_triple_valid() -> None:
    assert money_triple_valid(31.4, "EUR", "EUR/MWh") is True
    assert money_triple_valid(None, None, None) is True
    # Priced but missing currency or unit: silent-mixing hazard, invalid.
    assert money_triple_valid(31.4, None, "EUR/MWh") is False
    assert money_triple_valid(31.4, "EUR", None) is False
    # Unpriced but carrying a unit: inconsistent, invalid.
    assert money_triple_valid(None, "EUR", "EUR/MWh") is False
