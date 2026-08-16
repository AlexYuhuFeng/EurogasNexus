"""Strategy risk constraint tests."""

from eurogas_nexus.domain.constraints.risk import ocm_day_split, stop_loss_triggered


def test_stop_loss_not_triggered_without_threshold() -> None:
    assert stop_loss_triggered(-1500.0, None) is False


def test_stop_loss_not_triggered_above_threshold() -> None:
    assert stop_loss_triggered(-500.0, 1000.0) is False


def test_stop_loss_triggered_at_or_below_threshold() -> None:
    assert stop_loss_triggered(-1000.0, 1000.0) is True
    assert stop_loss_triggered(-1500.0, 1000.0) is True


def test_stop_loss_uses_cumulative_not_absolute_existing() -> None:
    # Cumulative PnL is positive after a profitable run; no stop-loss.
    assert stop_loss_triggered(42794.0, 1000.0) is False


def test_ocm_day_split_balanced_at_zero_score() -> None:
    assert ocm_day_split(0.0, 80.0, 10.0) == (50.0, 50.0)


def test_ocm_day_split_caps_ocm_at_max() -> None:
    assert ocm_day_split(1.0, 70.0, 20.0) == (70.0, 30.0)


def test_ocm_day_split_floors_day_ahead_at_min() -> None:
    assert ocm_day_split(-1.0, 70.0, 20.0) == (20.0, 80.0)


def test_ocm_day_split_positive_score_prefers_ocm() -> None:
    ocm_pct, day_pct = ocm_day_split(0.42, 70.0, 20.0)
    assert ocm_pct == 62.6
    assert day_pct == 37.4
