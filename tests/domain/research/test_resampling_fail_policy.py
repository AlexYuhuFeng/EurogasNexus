"""``missing_data_policy=FAIL`` never fills a gap, but it must keep observed values.

The FAIL branch ran before the observed-value branch and so masked every value: a dataset
built under a FAIL policy was entirely missing.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from eurogas_nexus.domain.research.resampling import (
    MissingDataPolicy,
    ResampledValue,
    ResamplingPolicy,
    bounded_resample,
)


def test_fail_policy_keeps_observed_values_and_never_fills() -> None:
    base = datetime(2026, 1, 1, 6, tzinfo=UTC)
    observed = ResampledValue(timestamp=base, value=10.0, is_observed=True)
    missing = ResampledValue(timestamp=base + timedelta(hours=1), value=11.0, is_observed=False)
    policy = ResamplingPolicy(
        semantic_type="market_price",
        missing_data_policy=MissingDataPolicy.FAIL,
        maximum_carry_seconds=7200,
    )

    (kept,) = bounded_resample([observed], [base + timedelta(minutes=30)], policy)
    assert kept is not None and kept.value == 10.0 and kept.is_observed is True

    (not_filled,) = bounded_resample(
        [observed, missing], [base + timedelta(hours=1, minutes=15)], policy
    )
    assert not_filled is None
