"""Artifact export tests: Parquet primary, CSV debug, entitlement-aware."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from eurogas_nexus.domain.research.datasets import (
    DatasetBuildResult,
    DatasetSpec,
)
from eurogas_nexus.domain.research.export import export_csv, export_parquet


def _result() -> DatasetBuildResult:
    spec = DatasetSpec(
        dataset_spec_id="spec-export",
        name="Export fixture",
        description="Export test fixture.",
        target_ids=["TARGET"],
        start=datetime(2026, 1, 1, tzinfo=UTC),
        end=datetime(2026, 1, 2, tzinfo=UTC),
    )
    return DatasetBuildResult(
        dataset_snapshot_id="snapshot-export",
        spec=spec,
        rows=[
            {
                "forecast_origin": datetime(2026, 1, 1, tzinfo=UTC),
                "feature_id": "F1",
                "value": 1.25,
                "is_observed": True,
                "quality_state": "OBSERVED",
                "export_policy": "EXPORT_ALLOWED",
            },
            {
                "forecast_origin": datetime(2026, 1, 1, 1, tzinfo=UTC),
                "feature_id": "F1",
                "value": None,
                "is_observed": False,
                "quality_state": "MISSING",
                "export_policy": "EXPORT_ALLOWED",
            },
        ],
        columns=[
            "export_policy",
            "feature_id",
            "forecast_origin",
            "is_observed",
            "quality_state",
            "value",
        ],
        quality_report={"rows": 2, "coverage": 0.5},
        leakage_issues=[],
        lineage=["test:source"],
        content_hash="a" * 64,
    )


def test_csv_export_keeps_null_masks(tmp_path) -> None:
    target = export_csv(_result(), tmp_path / "dataset.csv")
    text = target.read_text(encoding="utf-8")
    assert text.count("F1") == 2
    assert "MISSING" in text
    assert "EXPORT_ALLOWED" in text


def test_parquet_export_round_trips_columns_and_nulls(tmp_path) -> None:
    pytest.importorskip("pyarrow")
    target = export_parquet(_result(), tmp_path / "dataset.parquet")
    assert target.exists()

    import pyarrow.parquet as pq

    table = pq.read_table(target)
    assert table.num_rows == 2
    assert set(table.column_names) == set(_result().columns)
    assert table.column("value").to_pylist()[0] == 1.25
    assert table.column("value").to_pylist()[1] is None


def test_export_is_entitlement_aware(tmp_path) -> None:
    result = _result()
    result.rows[0]["export_policy"] = "EXPORT_RESTRICTED"
    with pytest.raises(PermissionError, match="EXPORT_DENIED_ENTITLEMENT"):
        export_csv(result, tmp_path / "restricted.csv")
    with pytest.raises(PermissionError, match="EXPORT_DENIED_ENTITLEMENT"):
        export_parquet(result, tmp_path / "restricted.parquet")
