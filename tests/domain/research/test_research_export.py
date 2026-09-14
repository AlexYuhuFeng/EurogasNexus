"""Artifact export tests: Parquet primary, CSV debug, entitlement-aware."""

from __future__ import annotations

import hashlib
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


def test_artifact_store_writes_registered_csv_artifact(tmp_path, monkeypatch) -> None:
    """CR14-ARTIFACT-001: a build registers a real, hash-verified artifact."""

    from eurogas_nexus.application import research_artifacts

    monkeypatch.setenv("EUROGAS_NEXUS_RESEARCH_ARTIFACT_ROOT", str(tmp_path / "artifacts"))

    artifacts = research_artifacts.write_dataset_artifacts(_result())

    formats = [artifact["format"] for artifact in artifacts]
    assert "csv" in formats
    assert set(formats) <= {"csv", "parquet"}
    assert formats == sorted(formats, key=research_artifacts.ARTIFACT_FORMAT_PRECEDENCE.index)
    csv_artifact = next(item for item in artifacts if item["format"] == "csv")
    written = tmp_path / "artifacts" / csv_artifact["artifact_path"]
    assert written.is_file()
    assert csv_artifact["sha256"] == hashlib.sha256(written.read_bytes()).hexdigest()
    # The reference stays relative to the configured root: no host path leaks.
    assert str(tmp_path) not in csv_artifact["artifact_path"]
    assert csv_artifact["artifact_path"].endswith("dataset.csv")
    assert research_artifacts.resolve_artifact_file(csv_artifact["artifact_path"]).is_file()


def test_artifact_store_registers_parquet_only_when_adapter_is_available(
    tmp_path, monkeypatch
) -> None:
    from eurogas_nexus.application import research_artifacts

    monkeypatch.setenv("EUROGAS_NEXUS_RESEARCH_ARTIFACT_ROOT", str(tmp_path / "artifacts"))
    artifacts = research_artifacts.write_dataset_artifacts(_result())
    formats = {artifact["format"] for artifact in artifacts}

    if research_artifacts.parquet_adapter_available():
        assert formats == {"parquet", "csv"}
    else:
        assert formats == {"csv"}
        assert "parquet" not in research_artifacts.artifact_formats()


def test_artifact_store_fails_closed_when_root_is_unusable(tmp_path, monkeypatch) -> None:
    from eurogas_nexus.application import research_artifacts

    blocker = tmp_path / "not-a-directory"
    blocker.write_text("occupied", encoding="utf-8")
    monkeypatch.setenv("EUROGAS_NEXUS_RESEARCH_ARTIFACT_ROOT", str(blocker))

    with pytest.raises(research_artifacts.ArtifactStoreUnavailable):
        research_artifacts.write_dataset_artifacts(_result())


def test_artifact_store_keeps_paths_inside_the_configured_root(
    tmp_path, monkeypatch
) -> None:
    from eurogas_nexus.application import research_artifacts

    monkeypatch.setenv("EUROGAS_NEXUS_RESEARCH_ARTIFACT_ROOT", str(tmp_path / "artifacts"))
    result = _result()
    result.dataset_snapshot_id = "../../escape/attempt"

    artifacts = research_artifacts.write_dataset_artifacts(result)

    assert artifacts
    for artifact in artifacts:
        assert ".." not in artifact["artifact_path"]
        resolved = research_artifacts.resolve_artifact_file(artifact["artifact_path"])
        assert resolved.is_relative_to((tmp_path / "artifacts").resolve())
        assert resolved.is_file()


def test_artifact_reference_outside_root_is_rejected(tmp_path, monkeypatch) -> None:
    from eurogas_nexus.application import research_artifacts

    monkeypatch.setenv("EUROGAS_NEXUS_RESEARCH_ARTIFACT_ROOT", str(tmp_path / "artifacts"))

    with pytest.raises(research_artifacts.ArtifactStoreUnavailable):
        research_artifacts.resolve_artifact_file("../outside.csv")
