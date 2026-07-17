"""Integrity tests for storage and nomination decision-support prototypes."""

from __future__ import annotations

from datetime import datetime, time

import pytest

from eurogas_nexus.optimization.nomination import (
    NominationInstruction,
    NominationWindow,
    optimize_nomination_schedule,
)
from eurogas_nexus.optimization.storage import (
    StorageFacility,
    StoragePeriod,
    optimize_storage_dispatch,
)


def test_storage_preserves_exact_initial_and_terminal_inventory() -> None:
    facility = StorageFacility(
        initial_inventory_mwh=0.4,
        minimum_inventory_mwh=0.0,
        maximum_inventory_mwh=2.0,
        maximum_injection_mwh=1.0,
        maximum_withdrawal_mwh=1.0,
        terminal_inventory_mwh=0.4,
    )

    result = optimize_storage_dispatch(
        facility,
        [StoragePeriod("gas-day", 30.0)],
        inventory_step_mwh=1.0,
    )

    assert result.status == "optimal"
    assert result.terminal_inventory_mwh == 0.4
    assert result.decisions[0].ending_inventory_mwh == 0.4
    assert result.decisions[0].injection_mwh == 0.0
    assert result.decisions[0].withdrawal_mwh == 0.0


@pytest.mark.parametrize(
    ("facility", "message"),
    [
        (
            StorageFacility(3.0, 0.0, 2.0, 1.0, 1.0),
            "within inventory bounds",
        ),
        (
            StorageFacility(1.0, 0.0, 2.0, 1.0, 1.0, injection_efficiency=0.0),
            "injection_efficiency",
        ),
        (
            StorageFacility(1.0, 2.0, 1.0, 1.0, 1.0),
            "maximum_inventory_mwh",
        ),
    ],
)
def test_invalid_storage_facility_fails_explicitly(
    facility: StorageFacility,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        optimize_storage_dispatch(facility, [])


def test_nomination_applies_change_limit_and_overnight_window() -> None:
    result = optimize_nomination_schedule(
        initial_quantity_mwh=100.0,
        instructions=[NominationInstruction(datetime(2026, 7, 17, 1, 0), 140.0)],
        windows=[NominationWindow("overnight", time(22, 0), time(2, 0), 25.0)],
    )

    assert result.status == "feasible"
    assert result.final_quantity_mwh == 125.0
    assert result.decisions[0].accepted is False
    assert result.decisions[0].reason == "RENOMINATION_CHANGE_LIMIT_APPLIED"


def test_nomination_rejects_negative_quantity_and_duplicate_windows() -> None:
    with pytest.raises(ValueError, match="requested_quantity_mwh"):
        optimize_nomination_schedule(
            initial_quantity_mwh=0.0,
            instructions=[NominationInstruction(datetime(2026, 7, 17, 1, 0), -1.0)],
            windows=[NominationWindow("window", time(0, 0), time(2, 0))],
        )

    duplicate_windows = [
        NominationWindow("same", time(0, 0), time(1, 0)),
        NominationWindow("same", time(1, 0), time(2, 0)),
    ]
    with pytest.raises(ValueError, match="duplicate window_id"):
        optimize_nomination_schedule(0.0, [], duplicate_windows)
