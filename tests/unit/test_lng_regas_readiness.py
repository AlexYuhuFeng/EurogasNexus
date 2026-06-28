"""LNG regas readiness model tests."""

from datetime import UTC, datetime

from eurogas_nexus.domain.route_cost.lng_regas import (
    LngRegasDeliveryMode,
    LngRegasScenario,
    assess_lng_regas_readiness,
)


def _scenario(**overrides) -> LngRegasScenario:
    data = {
        "contract_id": "lng-contract",
        "cargo_id": "cargo-1",
        "terminal_id": "nl-gate",
        "terminal_name": "GATE LNG",
        "terminal_access_confirmed": True,
        "terminal_access_reference": "operator-input",
        "cargo_size_mwh": 900_000,
        "cargo_arrival_window_start_utc": datetime(2026, 6, 29, tzinfo=UTC),
        "cargo_arrival_window_end_utc": datetime(2026, 7, 1, tzinfo=UTC),
        "regas_slot_start_utc": datetime(2026, 6, 30, tzinfo=UTC),
        "regas_slot_end_utc": datetime(2026, 7, 4, tzinfo=UTC),
        "terminal_sendout_capacity_mwh_per_day": 300_000,
        "terminal_capacity_source_system": "GIE ALSI/operator",
        "pricing_method": "TTF",
        "index_name": "TTF day-ahead",
        "delivery_mode": LngRegasDeliveryMode.TERMINAL_TITLE_TRANSFER,
    }
    data.update(overrides)
    return LngRegasScenario(**data)


def test_lng_regas_terminal_title_transfer_does_not_require_physical_entry() -> None:
    result = assess_lng_regas_readiness(_scenario())

    assert result.physical_entry_delivery_required is False
    assert "PHYSICAL_ENTRY_POINT_MISSING" not in result.missing_inputs
    assert result.estimated_regas_duration_days == 3.0
    assert result.crosses_month is True
    assert {item.month for item in result.month_allocations} == {"2026-06", "2026-07"}


def test_lng_regas_physical_entry_delivery_requires_entry_point() -> None:
    result = assess_lng_regas_readiness(
        _scenario(delivery_mode=LngRegasDeliveryMode.PHYSICAL_ENTRY_DELIVERY)
    )

    assert result.physical_entry_delivery_required is True
    assert "PHYSICAL_ENTRY_POINT_MISSING" in result.missing_inputs


def test_lng_regas_blocks_when_tso_access_missing() -> None:
    result = assess_lng_regas_readiness(
        _scenario(
            delivery_mode=LngRegasDeliveryMode.DOWNSTREAM_PHYSICAL_DELIVERY,
            physical_entry_point_name="GTS LNG Entry",
            required_tso_access=["Gasunie Transport Services"],
            company_accessible_tsos=["Fluxys Belgium"],
        )
    )

    assert result.inaccessible_tsos == ["Gasunie Transport Services"]
    assert "TSO_ACCESS_MISSING:Gasunie Transport Services" in result.missing_inputs
