"""#50 extension pack: a cross-day storage case, an LNG delay case and a weather-vintage case.

Each case is generated (no desk data exists yet) and checked against an independent reference
written here, not against the engine's own output: a brute-force search for storage, hand
arithmetic for the LNG replay, and the generating coefficients for the weather fit.
"""

from __future__ import annotations

import itertools
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from eurogas_nexus.application.nwe_balance_scenario import (
    NweBalanceScenarioRequest,
    run_nwe_balance_scenario,
)
from eurogas_nexus.domain.portfolio.desk_replay import DeskReplay, replay
from eurogas_nexus.optimization.storage import (
    StorageFacility,
    StoragePeriod,
    optimize_storage_dispatch,
)

# --- Storage: inventory carried across days ----------------------------------------------

FACILITY = StorageFacility(
    initial_inventory_mwh=100.0,
    minimum_inventory_mwh=0.0,
    maximum_inventory_mwh=300.0,
    maximum_injection_mwh=100.0,
    maximum_withdrawal_mwh=100.0,
    terminal_inventory_mwh=100.0,
)
PRICES = (20.0, 30.0, 25.0, 40.0, 22.0)  # GBP/MWh per gas day


def _brute_force(step: float = 50.0) -> float:
    """Every inject/withdraw sequence on the grid that respects the facility; best cash."""

    moves = [m * step for m in range(-2, 3)]  # -100..+100: negative withdraws
    best = None
    for plan in itertools.product(moves, repeat=len(PRICES)):
        inventory, cash, feasible = FACILITY.initial_inventory_mwh, 0.0, True
        for move, price in zip(plan, PRICES, strict=True):
            inventory += move
            if not FACILITY.minimum_inventory_mwh <= inventory <= FACILITY.maximum_inventory_mwh:
                feasible = False
                break
            cash -= move * price
        if feasible and inventory == FACILITY.terminal_inventory_mwh:
            best = cash if best is None else max(best, cash)
    assert best is not None
    return best


def test_storage_dispatch_matches_brute_force_and_respects_every_constraint():
    periods = [StoragePeriod(f"D{i}", price) for i, price in enumerate(PRICES, start=1)]
    result = optimize_storage_dispatch(FACILITY, periods, inventory_step_mwh=50.0)

    assert result.objective_value_gbp == pytest.approx(_brute_force())
    inventory = FACILITY.initial_inventory_mwh
    for decision in result.decisions:
        assert 0 <= decision.injection_mwh <= FACILITY.maximum_injection_mwh
        assert 0 <= decision.withdrawal_mwh <= FACILITY.maximum_withdrawal_mwh
        assert not (decision.injection_mwh and decision.withdrawal_mwh)
        inventory += decision.injection_mwh - decision.withdrawal_mwh
        assert decision.ending_inventory_mwh == pytest.approx(inventory)
        assert FACILITY.minimum_inventory_mwh <= inventory <= FACILITY.maximum_inventory_mwh
    assert result.terminal_inventory_mwh == FACILITY.terminal_inventory_mwh
    # The day-4 peak is served from gas carried in on cheaper days, not from thin air.
    day4 = result.decisions[3]
    assert day4.withdrawal_mwh == FACILITY.maximum_withdrawal_mwh


def test_storage_cannot_withdraw_gas_it_does_not_hold():
    empty = StorageFacility(
        initial_inventory_mwh=0.0,
        minimum_inventory_mwh=0.0,
        maximum_inventory_mwh=300.0,
        maximum_injection_mwh=100.0,
        maximum_withdrawal_mwh=100.0,
        terminal_inventory_mwh=0.0,
    )
    result = optimize_storage_dispatch(
        empty, [StoragePeriod("D1", 50.0), StoragePeriod("D2", 10.0)], inventory_step_mwh=50.0
    )
    # Day 1 is the dear day but the store is empty: nothing to sell, so nothing is done.
    assert result.decisions[0].withdrawal_mwh == 0
    assert result.objective_value_gbp == pytest.approx(0.0)


# --- LNG delay: terminal access and downstream delivery ------------------------------------

GAS_DAY = date(2026, 12, 3)
FIRST_LOOK = datetime(2026, 12, 2, 8, tzinfo=UTC)
DELAY_KNOWN = datetime(2026, 12, 2, 14, tzinfo=UTC)
CLOSE = datetime(2026, 12, 2, 18, tzinfo=UTC)


def _lng_case(as_of: datetime) -> DeskReplay:
    def evidence(record_id, revision, at, **extra):
        return {
            "record_id": record_id,
            "revision": revision,
            "available_at": at,
            "source_ref": f"demo:{record_id}:{revision}",
            **extra,
        }

    return DeskReplay.model_validate(
        {
            "book_id": "demo-uk-nbp",
            "hub_id": "NBP",
            "gas_day": GAS_DAY,
            "currency": "GBP",
            "as_of": as_of,
            "positions": [
                # The cargo's send-out at the Thames terminal for the day, then the delay revision.
                evidence(
                    "cargo-A-sendout",
                    1,
                    FIRST_LOOK,
                    resource_id="cargo-A",
                    kind="AVAILABLE",
                    mwh=Decimal("90000"),
                ),
                evidence(
                    "cargo-A-sendout",
                    2,
                    DELAY_KNOWN,
                    resource_id="cargo-A",
                    kind="AVAILABLE",
                    mwh=Decimal("0"),
                ),
                evidence(
                    "cargo-A-sale",
                    1,
                    FIRST_LOOK,
                    resource_id="cargo-A",
                    kind="COMMITMENT",
                    mwh=Decimal("60000"),
                ),
            ],
            "alternatives": [
                # Another terminal could take the cargo, but the slot is not confirmed.
                evidence(
                    "alt-zee-slot",
                    1,
                    DELAY_KNOWN,
                    resource_id="cargo-A",
                    kind="CHANGE_ROUTE",
                    quantity_mwh=Decimal("90000"),
                    cost_per_mwh=Decimal("1.40"),
                    deadline=CLOSE,
                    right_confirmed=False,
                    price_basis="CONFIRMED_COST",
                    price_valid_until=CLOSE,
                ),
                evidence(
                    "alt-buy-da",
                    1,
                    DELAY_KNOWN,
                    resource_id="cargo-A",
                    kind="BUY_GAS",
                    quantity_mwh=Decimal("40000"),
                    cost_per_mwh=Decimal("34.10"),
                    deadline=CLOSE,
                    right_confirmed=True,
                    price_basis="EXECUTABLE",
                    price_valid_until=CLOSE,
                ),
                evidence(
                    "alt-withdraw",
                    1,
                    DELAY_KNOWN,
                    resource_id="cargo-A",
                    kind="WITHDRAW_STORAGE",
                    quantity_mwh=Decimal("30000"),
                    cost_per_mwh=Decimal("0.60"),
                    deadline=CLOSE,
                    right_confirmed=True,
                    price_basis="CONFIRMED_COST",
                    price_valid_until=CLOSE,
                ),
            ],
        }
    )


def test_lng_delay_is_invisible_before_it_was_published():
    first = replay(_lng_case(FIRST_LOOK))["resources"][0]
    # Reference: 90,000 send-out against a 60,000 sale leaves 30,000 spare and no gap.
    assert first["deliverable_mwh"] == Decimal("90000")
    assert first["keep_plan_gap_mwh"] == Decimal("0")
    assert first["alternatives"] == []  # the responses were not yet known either


def test_lng_delay_creates_the_downstream_gap_and_blocks_the_unconfirmed_terminal():
    result = replay(_lng_case(DELAY_KNOWN))["resources"][0]
    # Reference: send-out revised to 0, sale 60,000, so 60,000 short at the hub.
    assert result["deliverable_mwh"] == Decimal("0")
    assert result["keep_plan_gap_mwh"] == Decimal("60000")
    responses = {row["record_id"]: row for row in result["alternatives"]}
    assert responses["alt-zee-slot"]["blocked"] == ["RIGHT_UNCONFIRMED"]
    buy = responses["alt-buy-da"]
    assert buy["quantity_mwh"] == Decimal("40000")
    assert buy["remaining_gap_mwh"] == Decimal("20000")
    assert buy["incremental_cost"] == Decimal("40000") * Decimal("34.10")
    withdraw = responses["alt-withdraw"]
    assert withdraw["quantity_mwh"] == Decimal("30000")
    assert withdraw["incremental_cost"] == Decimal("30000") * Decimal("0.60")


def test_lng_replay_is_reproducible_from_its_frozen_inputs():
    one, two = replay(_lng_case(DELAY_KNOWN)), replay(_lng_case(DELAY_KNOWN))
    assert one["input_sha256"] == two["input_sha256"]
    assert replay(_lng_case(FIRST_LOOK))["input_sha256"] != one["input_sha256"]


# --- Weather: vintage-correct forecast against the no-weather baseline ---------------------

ORIGIN = datetime(2026, 12, 1, 9, tzinfo=UTC)
START = date(2026, 12, 1)
INTERCEPT, SLOPE = 2_000.0, 45.0  # GWh/d and GWh/d per HDD: the generating truth


def _hdd(day: date) -> float:
    return 8.0 + 6.0 * ((day.toordinal() * 7) % 11) / 10  # deterministic, varied


def _weather_case(forecast_hdd: float, forecast_at: datetime, threshold: float | None):
    history, hdd_history = [], []
    for back in range(60, 0, -1):
        day = START - timedelta(days=back)
        wiggle = ((day.toordinal() * 13) % 7 - 3) * 4.0  # small, mean-zero residual
        call = INTERCEPT + SLOPE * _hdd(day) + wiggle
        known = datetime.combine(day + timedelta(days=1), datetime.min.time(), tzinfo=UTC)
        history.append(
            {
                "day": day,
                "norway_gwh": call * 0.5,
                "lng_gwh": call * 0.3,
                "storage_net_withdrawal_gwh": call * 0.2,
                "available_at": known,
                "source_reference": f"demo:balance:{day}",
            }
        )
        hdd_history.append(
            {
                "day": day,
                "hdd": _hdd(day),
                "available_at": known,
                "source_reference": f"demo:hdd:{day}",
            }
        )
    forecast = [
        {
            "day": START + timedelta(days=k),
            "hdd": forecast_hdd,
            "available_at": forecast_at,
            "source_reference": f"demo:fc:{k}",
        }
        for k in range(3)
    ]
    return NweBalanceScenarioRequest.model_validate(
        {
            "prediction_origin": ORIGIN,
            "start": START,
            "days": 3,
            "history": history,
            "decision_threshold_gwh": threshold,
            "weather": {
                "region": "NWE",
                "feature_policy_hash": "a" * 64,
                "heating_base_c": 15.5,
                "gas_day_calendar": "EU-CAM-UTC-2025",
                "history": hdd_history,
                "forecast": forecast,
            },
        }
    )


def test_a_forecast_vintage_published_after_the_decision_is_refused():
    with pytest.raises(ValueError, match="unavailable at prediction origin"):
        _weather_case(14.0, ORIGIN + timedelta(hours=3), None)


def test_weather_fit_recovers_the_generating_model_with_an_honest_band():
    result = run_nwe_balance_scenario(_weather_case(14.0, ORIGIN - timedelta(hours=6), None))
    model = result["data"]["model"]
    assert model["slope_per_hdd"] == pytest.approx(SLOPE, rel=0.03)
    assert model["residual_std_gwh"] < 20  # the wiggle is at most 12 GWh/d
    reference = INTERCEPT + SLOPE * 14.0
    for row, band in zip(result["data"]["forecast"], result["data"]["uncertainty"], strict=True):
        assert row["call_gwh"] == pytest.approx(reference, rel=0.01)
        assert band["call_low_gwh"] < row["call_gwh"] < band["call_high_gwh"]


def test_the_result_says_whether_the_forecast_changed_the_desk_decision():
    cold = run_nwe_balance_scenario(_weather_case(14.0, ORIGIN - timedelta(hours=6), 2_500.0))
    decision = cold["data"]["decision"]
    baseline_calls = [row["call_gwh"] for row in cold["data"]["baseline"]]
    # Reference: the cold forecast puts the call near 2,630 GWh/d, over a 2,500 trigger.
    assert decision["weather_days_over"] == 3
    expected_changed = [
        row["day"]
        for row, call in zip(cold["data"]["forecast"], baseline_calls, strict=True)
        if call <= 2_500.0
    ]
    assert decision["changed_days"] == expected_changed
    # The baseline sits just under the trigger (about 2,488), so the forecast flips all 3 days.
    assert decision["baseline_days_over"] == 0
    assert decision["changed"] is True
    assert len(decision["changed_days"]) == 3

    near = run_nwe_balance_scenario(
        _weather_case(14.0, ORIGIN - timedelta(hours=6), INTERCEPT + SLOPE * 14.0)
    )
    # A trigger sitting on the forecast is inside the band: the call is not a firm signal.
    assert near["data"]["decision"]["threshold_inside_band_days"]
