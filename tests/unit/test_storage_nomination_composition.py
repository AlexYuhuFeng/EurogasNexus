"""R34A composition tests for DB-owned storage/nomination masters."""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from types import SimpleNamespace

from eurogas_nexus.application.storage_nomination_composition import (
    compose_nomination_windows,
    compose_storage_dispatch,
)
from eurogas_nexus.db.models.storage_nomination import (
    NominationWindowMasterRecord,
    StorageFacilityMasterRecord,
    StorageInventoryObservationRecord,
)


def _facility() -> StorageFacilityMasterRecord:
    return StorageFacilityMasterRecord(
        facility_id="fac-1",
        name="Test Storage",
        market_hub="TTF",
        country="NL",
        minimum_inventory_mwh=0.0,
        maximum_inventory_mwh=200.0,
        maximum_injection_mwh=50.0,
        maximum_withdrawal_mwh=50.0,
        injection_efficiency=1.0,
        withdrawal_efficiency=1.0,
        injection_cost_gbp_mwh=0.0,
        withdrawal_cost_gbp_mwh=0.0,
        terminal_inventory_mwh=100.0,
        valid_from_utc=datetime(2025, 1, 1, tzinfo=UTC),
        valid_to_utc=None,
        source_system="operator",
        source_reference="test_fixture:not_customer_data",
        active=True,
        created_at_utc=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _inventory() -> StorageInventoryObservationRecord:
    return StorageInventoryObservationRecord(
        observation_id="inv-1",
        facility_id="fac-1",
        inventory_mwh=100.0,
        observed_at_utc=datetime(2026, 1, 1, 6, 0, tzinfo=UTC),
        period_start_utc=datetime(2026, 1, 1, 6, 0, tzinfo=UTC),
        source_system="operator",
        source_reference="test_fixture:not_customer_data",
        research_only=True,
        human_review_required=True,
    )


def _market_row(observation_id: str, price: float) -> SimpleNamespace:
    return SimpleNamespace(
        observation_id=observation_id,
        market_venue="EEX",
        product="TTF Day-Ahead",
        price=price,
        unit="EUR/MWh",
        currency="EUR",
        period_start_utc=datetime(2026, 1, 1, 6, 0, tzinfo=UTC),
        period_end_utc=datetime(2026, 1, 2, 6, 0, tzinfo=UTC),
        observed_at_utc=datetime(2026, 1, 1, 6, 0, tzinfo=UTC),
        source_system="EEX_Sim",
        source_reference="sim:test",
        metadata_json={"hub": "TTF"},
    )


def _fx_row() -> SimpleNamespace:
    return SimpleNamespace(
        pair="EURGBP",
        base_currency="EUR",
        quote_currency="GBP",
        rate=0.85,
        value_date="2026-01-01",
    )


def test_storage_composition_is_complete_with_master_market_and_fx() -> None:
    composed = compose_storage_dispatch(
        facility=_facility(),
        inventory=_inventory(),
        market_rows=[_market_row("m1", 30.0), _market_row("m2", 40.0)],
        fx_rows=[_fx_row()],
        gas_day=date(2026, 1, 1),
        max_periods=5,
    )

    assert composed.is_complete is True
    assert composed.facility is not None
    assert composed.facility.initial_inventory_mwh == 100.0
    assert len(composed.periods) == 2
    assert composed.periods[0].market_price_gbp_mwh == 25.5
    assert "market_observation:m1" in composed.source_refs


def test_storage_composition_blocks_on_missing_inventory() -> None:
    composed = compose_storage_dispatch(
        facility=_facility(),
        inventory=None,
        market_rows=[_market_row("m1", 30.0)],
        fx_rows=[_fx_row()],
        gas_day=date(2026, 1, 1),
        max_periods=5,
    )

    assert composed.is_complete is False
    assert "STORAGE_INVENTORY_MISSING:fac-1" in composed.blockers


def test_storage_composition_blocks_on_missing_fx() -> None:
    composed = compose_storage_dispatch(
        facility=_facility(),
        inventory=_inventory(),
        market_rows=[_market_row("m1", 30.0)],
        fx_rows=[],
        gas_day=date(2026, 1, 1),
        max_periods=5,
    )

    assert composed.is_complete is False
    assert any(
        blocker.startswith("STORAGE_PRICE_FX_MISSING:m1:")
        for blocker in composed.blockers
    )


def test_nomination_window_composition_maps_active_masters() -> None:
    rows = [
        NominationWindowMasterRecord(
            window_id="w1",
            name="Within-day",
            country="NL",
            opens_at=time(0, 0),
            closes_at=time(6, 0),
            maximum_change_mwh=10.0,
            maximum_change_pct=None,
            valid_from_utc=datetime(2025, 1, 1, tzinfo=UTC),
            valid_to_utc=None,
            source_system="operator",
            source_reference="test_fixture:not_customer_data",
            active=True,
            created_at_utc=datetime(2026, 1, 1, tzinfo=UTC),
        )
    ]
    composed = compose_nomination_windows(window_rows=rows)

    assert composed.is_complete is True
    assert composed.windows[0].window_id == "w1"
    assert composed.windows[0].opens_at == time(0, 0)


def test_nomination_window_composition_blocks_when_empty() -> None:
    composed = compose_nomination_windows(window_rows=[])

    assert composed.is_complete is False
    assert "NOMINATION_WINDOWS_MISSING" in composed.blockers
