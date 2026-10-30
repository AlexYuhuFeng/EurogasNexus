"""Declarative, point-in-time feature transforms for training datasets.

A feature whose ``transformation`` is one of :data:`DECLARATIVE_TRANSFORMS` is computed
from its ``input_dependencies`` and its ``metadata`` alone, so an analyst registers a
lag, a change or a rolling volatility as data instead of asking for new code.

Every value a transform reads is resolved *as of an earlier cutoff* (the forecast origin
minus ``k`` steps) by the same point-in-time selection the builder uses at the origin. A
lagged value is therefore what was known at that earlier moment, not today's revised
value placed on an old date; that is what keeps a lag from leaking revisions.

Metadata keys:

- ``step``: ``"1d"`` or ``"1h"`` style spacing between the values a transform reads
  (default ``"1d"``).
- ``lag_steps``: for ``lag`` and ``difference`` (default 1).
- ``window``: for ``rolling_mean`` and ``rolling_std`` (at least 2).
- ``weights``: for ``linear_combination``, one number per dependency.

A missing input at any cutoff the transform needs makes the value missing; nothing is
filled in.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from datetime import timedelta

from eurogas_nexus.domain.research.features import FeatureDefinition

DECLARATIVE_TRANSFORMS = frozenset(
    {"identity", "linear_combination", "lag", "difference", "rolling_mean", "rolling_std"}
)

#: A rolling window longer than this is a different question (a regime filter), and it
#: multiplies the point-in-time selections per origin.
MAX_WINDOW = 400


def is_declarative(feature: FeatureDefinition) -> bool:
    return feature.transformation in DECLARATIVE_TRANSFORMS


def _step(feature: FeatureDefinition) -> timedelta:
    text = str(feature.metadata.get("step", "1d")).strip().lower()
    if len(text) < 2 or text[-1] not in {"h", "d"} or not text[:-1].isdecimal():
        raise ValueError(f"{feature.feature_id}: step must look like '1d' or '6h'")
    amount = int(text[:-1])
    if amount <= 0:
        raise ValueError(f"{feature.feature_id}: step must be positive")
    return timedelta(hours=amount) if text.endswith("h") else timedelta(days=amount)


def _positive_int(feature: FeatureDefinition, key: str, default: int, minimum: int) -> int:
    value = feature.metadata.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{feature.feature_id}: {key} must be an integer >= {minimum}")
    if value > MAX_WINDOW:
        raise ValueError(f"{feature.feature_id}: {key} must be <= {MAX_WINDOW}")
    return value


def validate_declarative_feature(feature: FeatureDefinition) -> None:
    """Raise ``ValueError`` when the declaration cannot be computed as written."""

    kind = feature.transformation
    dependencies = feature.input_dependencies
    if kind not in DECLARATIVE_TRANSFORMS:
        raise ValueError(f"{feature.feature_id}: unknown transformation {kind!r}")
    if not dependencies:
        raise ValueError(f"{feature.feature_id}: needs at least one input dependency")
    if kind != "linear_combination" and len(dependencies) != 1:
        raise ValueError(f"{feature.feature_id}: {kind} takes exactly one input dependency")
    if kind == "linear_combination":
        weights = feature.metadata.get("weights")
        if (
            not isinstance(weights, list)
            or len(weights) != len(dependencies)
            or not all(
                isinstance(w, int | float) and not isinstance(w, bool) and math.isfinite(w)
                for w in weights
            )
            or all(w == 0 for w in weights)
        ):
            raise ValueError(
                f"{feature.feature_id}: weights must be one finite number per dependency"
            )
    _step(feature)
    cutoff_offsets(feature)


def cutoff_offsets(feature: FeatureDefinition) -> list[timedelta]:
    """How far before the origin each value the transform reads is resolved."""

    kind = feature.transformation
    step = _step(feature)
    if kind in {"identity", "linear_combination"}:
        return [timedelta(0)]
    if kind == "lag":
        return [step * _positive_int(feature, "lag_steps", 1, 1)]
    if kind == "difference":
        return [timedelta(0), step * _positive_int(feature, "lag_steps", 1, 1)]
    window = _positive_int(feature, "window", 20, 2)
    return [step * index for index in range(window)]


def apply_transform(
    feature: FeatureDefinition,
    value_at: Callable[[timedelta], Mapping[str, float | None]],
) -> float | None:
    """Compute one feature value; ``value_at(offset)`` returns inputs as of origin-offset."""

    kind = feature.transformation
    offsets = cutoff_offsets(feature)
    dependencies = feature.input_dependencies
    if kind == "linear_combination":
        values = value_at(offsets[0])
        weights = feature.metadata["weights"]
        terms = [values.get(series_id) for series_id in dependencies]
        if any(term is None for term in terms):
            return None
        return round(sum(float(w) * float(t) for w, t in zip(weights, terms, strict=True)), 6)
    series_id = dependencies[0]
    observed = [value_at(offset).get(series_id) for offset in offsets]
    if any(value is None for value in observed):
        return None
    numbers = [float(value) for value in observed]  # type: ignore[arg-type]
    if kind in {"identity", "lag"}:
        return round(numbers[0], 6)
    if kind == "difference":
        return round(numbers[0] - numbers[1], 6)
    mean = sum(numbers) / len(numbers)
    if kind == "rolling_mean":
        return round(mean, 6)
    variance = sum((value - mean) ** 2 for value in numbers) / (len(numbers) - 1)
    return round(math.sqrt(variance), 6)
