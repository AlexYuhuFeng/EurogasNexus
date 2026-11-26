"""A dataset spec refuses fields the builder would silently ignore.

``{"frequency": "1d"}`` (a typo for ``forecast_origin_frequency``) built an hourly dataset,
``timezone="Europe/Amsterdam"`` still produced UTC-midnight origins and
``output_format="wide"`` still produced the long format, all with HTTP 200.
"""

from __future__ import annotations

import pytest
from eurogas_nexus.api.routes.public.research_data import _dataset_spec_error
from eurogas_nexus.domain.research.datasets import DatasetSpec
from pydantic import ValidationError


def _payload(**overrides) -> dict:
    payload = {
        "dataset_spec_id": "spec-fields",
        "name": "n",
        "description": "d",
        "target_ids": ["T"],
        "start": "2026-01-01T00:00:00Z",
        "end": "2026-01-02T00:00:00Z",
    }
    payload.update(overrides)
    return payload


@pytest.mark.parametrize(
    ("override", "field", "code"),
    [
        ({"frequency": "1d"}, "frequency", "dataset_field_unknown"),
        ({"timezone": "Europe/Amsterdam"}, "timezone", "timezone_unsupported"),
        ({"output_format": "wide"}, "output_format", "output_format_unsupported"),
    ],
)
def test_ignored_fields_are_refused_with_a_field_issue(override, field, code) -> None:
    with pytest.raises(ValidationError) as excinfo:
        DatasetSpec.model_validate(_payload(**override))
    detail = _dataset_spec_error(excinfo.value).detail
    assert detail["error"] == "dataset_spec_invalid"
    assert {"field": field, "code": code} == {k: detail["issues"][0][k] for k in ("field", "code")}


def test_utc_in_any_case_is_accepted() -> None:
    assert DatasetSpec.model_validate(_payload(timezone="utc")).timezone == "UTC"
